"""Bounded read-only operations for explicitly selected, trusted local folders."""

import os
import stat
from pathlib import Path, PureWindowsPath


class WorkspaceReader:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        self._check_components(self.root)
        if not self.root.is_dir():
            raise ValueError("Workspace root must be a directory")

    @staticmethod
    def _check_components(path: Path) -> None:
        for component in (*reversed(path.parents), path):
            info = component.lstat()
            if stat.S_ISLNK(info.st_mode) or (
                getattr(info, "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            ):
                raise PermissionError("Links and reparse points are not permitted")

    def _path(self, resource: str) -> Path:
        windows = PureWindowsPath(resource)
        parts = resource.replace("\\", "/").split("/")
        if (
            windows.drive
            or windows.root
            or resource.startswith("/")
            or any(
                part == ".."
                or ":" in part
                or part.startswith(".")
                and part != "."
                or part.endswith((" ", "."))
                and part != "."
                for part in parts
            )
        ):
            raise PermissionError("Only visible relative workspace paths are permitted")
        path = self.root.joinpath(*parts)
        self._check_components(path)
        path.resolve(strict=True).relative_to(self.root.resolve(strict=True))
        return path

    def read(self, resource: str) -> str:
        path = self._path(resource)
        if path.suffix.lower() not in {".txt", ".md", ".csv", ".json", ".toml"}:
            raise PermissionError("Unsupported text file type")
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise PermissionError("Only ordinary, single-link files are permitted")
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            self._path(resource)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise PermissionError("File changed during opening")
            content = handle.read(65537)
        if len(content) > 65536 or b"\x00" in content:
            raise ValueError("Expected UTF-8 text up to 64 KiB")
        return content.decode("utf-8")

    def list_files(self, resource: str) -> str:
        path = self._path(resource)
        names = []
        with os.scandir(path) as entries:
            for index, entry in enumerate(entries):
                if index >= 200:
                    raise ValueError("Directory exceeds the 200-entry limit")
                if entry.name.startswith("."):
                    continue
                self._check_components(Path(entry.path))
                names.append(entry.name + ("/" if entry.is_dir(follow_symlinks=False) else ""))
        return "\n".join(sorted(names))
