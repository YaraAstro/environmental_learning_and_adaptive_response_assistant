"""Authenticated loopback UI; no arbitrary filesystem routes or cloud assets."""

import asyncio
import secrets
import socket
import sqlite3
from importlib.resources import files
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import Field, model_validator
from starlette.middleware.base import RequestResponseEndpoint

from elara.app import build_runtime
from elara.core.contracts import AttachedDocument, Contract, MemoryFact
from elara.core.conversation import ConversationService
from elara.core.inference import InferenceError
from elara.core.media import AttachedMedia, validate_media_batch
from elara.core.sessions import SessionConflict, SessionNotFound
from elara.core.settings import Settings
from elara.inference.ollama import describe_model
from elara.memory.runtime import MemoryRuntime
from elara.memory.store import SQLiteStore


class ChatInput(Contract):
    session_id: UUID
    message: str = Field(min_length=1, max_length=32000)
    recall: bool = True
    attachments: tuple[AttachedDocument, ...] = Field(default=(), max_length=8)
    media: tuple[AttachedMedia, ...] = Field(default=(), max_length=10, repr=False)

    @model_validator(mode="after")
    def bounded_files(self) -> "ChatInput":
        validate_media_batch(self.media)
        if sum(len(item.content) for item in self.attachments) > 16000:
            raise ValueError("Attachments exceed 16,000 characters")
        for item in self.attachments:
            if (
                len(item.path) > 255
                or any(c in item.path for c in "/\\\x00")
                or item.path.startswith(".")
                or "\x00" in item.content
                or item.path.rsplit(".", 1)[-1].lower() not in {"txt", "md", "csv", "json", "toml"}
            ):
                raise ValueError("Unsupported text attachment")
        return self


def authorized(host: str, origin: str | None, authorization: str, token: str, port: int) -> bool:
    expected = f"127.0.0.1:{port}"
    return (
        host == expected
        and origin in (None, f"http://{expected}")
        and secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode())
    )


def create_app(settings: Settings, token: str, port: int = 8765) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    path = settings.data_dir / "database" / "elara.sqlite3"
    store = SQLiteStore(path)
    runtime = build_runtime(settings)
    memory_runtime = MemoryRuntime(runtime, path)
    generation_lock = asyncio.Lock()

    @app.middleware("http")
    async def guard(request: Request, call_next: RequestResponseEndpoint) -> Response:
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        if host != f"127.0.0.1:{port}" or origin not in (None, f"http://127.0.0.1:{port}"):
            return Response("Forbidden origin", status_code=403)
        if request.url.path.startswith("/api/") and not authorized(
            host, origin, request.headers.get("authorization", ""), token, port
        ):
            return Response(
                "Unlock this window using the launch URL from your terminal.", status_code=401
            )
        # Bound all bodies, including chunked input, before JSON validation.
        if request.method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                limit = 17_000_000 if request.url.path == "/api/chat" else 300_000
                if len(body) > limit:
                    return Response("Request too large", status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> Response:
        # Pydantic's default errors can echo complete base64 inputs back into browser logs.
        return JSONResponse(
            {
                "detail": "Invalid input. Check attachment types and size limits, "
                "message length, and memory key/value format."
            },
            status_code=422,
        )

    @app.exception_handler(InferenceError)
    async def inference_error(request: Request, exc: InferenceError) -> Response:
        return Response(str(exc), status_code=502)

    @app.exception_handler(SessionNotFound)
    async def missing_session(request: Request, exc: SessionNotFound) -> Response:
        return Response("Conversation no longer exists.", status_code=404)

    @app.exception_handler(SessionConflict)
    async def stale_session(request: Request, exc: SessionConflict) -> Response:
        return Response("Conversation changed; reload and retry.", status_code=409)

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request: Request, exc: sqlite3.Error) -> Response:
        return Response("Local storage is unavailable. Check the data directory.", status_code=503)

    @app.get("/")
    def index() -> Response:
        return asset("index.html", "text/html")

    def asset(name: str, media_type: str) -> Response:
        return Response(
            files("elara.api").joinpath("static", name).read_bytes(), media_type=media_type
        )

    @app.get("/app.js")
    def javascript() -> Response:
        return asset("app.js", "text/javascript")

    @app.get("/style.css")
    def stylesheet() -> Response:
        return asset("style.css", "text/css")

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return {
            "name": "ELARA",
            "provider": settings.inference.provider,
            "model": settings.inference.model,
            "saved": True,
        }

    @app.get("/api/model")
    def model_details() -> dict[str, Any]:
        return describe_model(settings.inference)

    @app.get("/api/sessions")
    def sessions() -> list[dict[str, Any]]:
        result = []
        for session in store.list_sessions()[:100]:
            snapshot = store.snapshot(session.id)
            title = snapshot.turns[0].content[:64] if snapshot.turns else "New conversation"
            result.append(
                {
                    "id": str(session.id),
                    "title": title,
                    "created_at": session.created_at.isoformat(),
                }
            )
        return result

    @app.post("/api/sessions")
    def new_session() -> dict[str, Any]:
        return store.create_session().model_dump(mode="json")

    @app.get("/api/sessions/{session_id}")
    def session(session_id: UUID) -> dict[str, Any]:
        return store.snapshot(session_id).model_dump(mode="json")

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: UUID) -> dict[str, bool]:
        if generation_lock.locked():
            raise HTTPException(409, "Wait for the current reply before deleting a conversation.")
        store.delete_session(session_id)
        return {"deleted": True}

    @app.get("/api/memories")
    def memories() -> list[dict[str, str]]:
        return [fact.model_dump() for fact in store.memories()]

    @app.put("/api/memories")
    def remember(fact: MemoryFact) -> dict[str, str]:
        try:
            return store.remember(fact.key, fact.value).model_dump()
        except ValueError:
            raise HTTPException(
                400, "Use a nonempty value up to 500 characters; at most 20 facts."
            ) from None

    @app.delete("/api/memories/{key}")
    def forget(key: str) -> dict[str, bool]:
        return {"deleted": store.forget(key)}

    @app.post("/api/chat")
    async def chat(body: ChatInput) -> dict[str, Any]:
        if body.media and settings.inference.provider != "ollama":
            raise HTTPException(400, "Media attachments require a compatible local Ollama model.")
        if generation_lock.locked():
            raise HTTPException(
                409, "ELARA is already answering. Try again when the reply finishes."
            )
        async with generation_lock:
            selected = (
                memory_runtime
                if body.recall and settings.inference.provider == "ollama"
                else runtime
            )
            result = await ConversationService(selected, store).respond(
                body.session_id, body.message, attachments=body.attachments, media=body.media
            )
        return result.model_dump(mode="json")

    return app


def serve(settings: Settings, port: int) -> None:
    import uvicorn

    # Keep the bound socket open so another process cannot claim the selected port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", port))
            listener.listen(128)
        except OSError as exc:
            code = getattr(exc, "winerror", None) or exc.errno
            raise InferenceError(
                f"Cannot listen on 127.0.0.1:{port} (socket error {code}). "
                "The port may be occupied, reserved, or blocked by Windows/security software. "
                "Try .\\scripts\\ui.ps1 --port 0 to let Windows choose an available port."
            ) from None
        actual_port = listener.getsockname()[1]
        token = secrets.token_urlsafe(32)
        app = create_app(settings, token, actual_port)
        config = uvicorn.Config(
            app, host="127.0.0.1", port=actual_port, access_log=False, log_level="warning"
        )
        print(f"Open ELARA: http://127.0.0.1:{actual_port}/#token={token}", flush=True)
        print("Local UI. Conversations are saved. Press Ctrl+C here to stop.", flush=True)
        uvicorn.Server(config).run(sockets=[listener])
