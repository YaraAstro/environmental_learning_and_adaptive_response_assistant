import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUp,
  ArrowUpRight,
  AudioLines,
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Cpu,
  FileText,
  Image,
  Menu,
  MessageCircle,
  Paperclip,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  Video,
  X,
} from "lucide-react";
import { api } from "./api";
import { prepareFile, validateAttachments } from "./media";
import type { Attachment, Memory, Model, Session, Status, Turn } from "./types";
import "./style.css";

const messageOf = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
const AttachmentIcon = ({ kind }: { kind: Attachment["kind"] }) =>
  kind === "image" ? (
    <Image />
  ) : kind === "video" ? (
    <Video />
  ) : kind === "audio" ? (
    <AudioLines />
  ) : (
    <FileText />
  );

function Drawer({
  title,
  subtitle,
  close,
  children,
}: {
  title: string;
  subtitle: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="drawer"
      onCancel={close}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      aria-label={title}
    >
      <div className="drawer-content">
        <div className="drawer-heading">
          <div>
            <span className="eyebrow">YOUR LOCAL SPACE</span>
            <h2>{title}</h2>
          </div>
          <button
            className="icon-button"
            onClick={close}
            aria-label={`Close ${title}`}
          >
            <X />
          </button>
        </div>
        <p className="muted">{subtitle}</p>
        {children}
      </div>
    </dialog>
  );
}

function App() {
  const [sessions, setSessions] = useState<Session[]>([]),
    [active, setActive] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]),
    [draft, setDraft] = useState(""),
    [attached, setAttached] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false),
    [preparing, setPreparing] = useState(false),
    [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(""),
    [status, setStatus] = useState<Status | null>(null),
    [model, setModel] = useState<Model | null>(null);
  const [modelError, setModelError] = useState(""),
    [modelLoading, setModelLoading] = useState(false);
  const [recall, setRecall] = useState(true),
    [includeSound, setIncludeSound] = useState(false);
  const [panel, setPanel] = useState<"memory" | "model" | "help" | null>(null),
    [sidebar, setSidebar] = useState(false),
    [search, setSearch] = useState("");
  const [memories, setMemories] = useState<Memory[]>([]),
    [memoryKey, setMemoryKey] = useState(""),
    [memoryValue, setMemoryValue] = useState(""),
    [memoryBusy, setMemoryBusy] = useState(false),
    [panelError, setPanelError] = useState("");
  const version = useRef(0),
    operation = useRef(false),
    fileInput = useRef<HTMLInputElement>(null),
    composer = useRef<HTMLTextAreaElement>(null),
    scroll = useRef<HTMLDivElement>(null);
  const locked = busy || preparing || loading;

  async function refreshSessions() {
    setSessions(await api<Session[]>("sessions"));
  }
  async function refreshModel() {
    setModelLoading(true);
    setModelError("");
    try {
      setModel(await api<Model>("model"));
    } catch (error) {
      setModel(null);
      setModelError(messageOf(error));
    } finally {
      setModelLoading(false);
    }
  }
  useEffect(() => {
    api<Status>("status")
      .then((value) => {
        setStatus(value);
        if (value.provider === "mock") setRecall(false);
      })
      .catch((error) => setNotice(messageOf(error)));
    refreshSessions().catch((error) => setNotice(messageOf(error)));
    void refreshModel();
  }, []);
  useEffect(() => {
    scroll.current?.scrollTo({
      top: scroll.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns, busy]);
  useEffect(() => {
    const input = composer.current;
    if (input) {
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
    }
  }, [draft]);

  function newChat() {
    if (operation.current) return;
    version.current++;
    setLoading(false);
    setActive(null);
    setTurns([]);
    setDraft("");
    setAttached([]);
    setNotice("");
    setSidebar(false);
    composer.current?.focus();
  }
  async function openSession(id: string) {
    if (operation.current) return;
    const current = ++version.current;
    setLoading(true);
    setNotice("");
    try {
      const data = await api<{ turns: Turn[] }>(`sessions/${id}`);
      if (current !== version.current) return;
      setActive(id);
      setTurns(data.turns);
      setDraft("");
      setAttached([]);
      setSidebar(false);
    } catch (error) {
      if (current === version.current) setNotice(messageOf(error));
    } finally {
      if (current === version.current) setLoading(false);
    }
  }
  async function deleteChat() {
    if (
      !active ||
      locked ||
      !confirm(
        "Delete this conversation? Saved memories and backups are retained.",
      )
    )
      return;
    operation.current = true;
    setLoading(true);
    try {
      await api(`sessions/${active}`, "DELETE");
      operation.current = false;
      newChat();
      await refreshSessions();
    } catch (error) {
      setNotice(messageOf(error));
    } finally {
      operation.current = false;
      setLoading(false);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (operation.current || loading || !draft.trim()) return;
    operation.current = true;
    ++version.current;
    setBusy(true);
    setNotice("");
    const message = draft.trim(),
      previous = turns;
    try {
      let id = active;
      if (!id) {
        id = (await api<{ id: string }>("sessions", "POST")).id;
        setActive(id);
      }
      setTurns([...previous, { role: "user", content: message }]);
      const answer = await api<{ message: string }>("chat", "POST", {
        session_id: id,
        message,
        recall,
        attachments: attached.flatMap((item) => (item.text ? [item.text] : [])),
        media: attached.flatMap((item) => item.media),
      });
      setTurns([
        ...previous,
        { role: "user", content: message },
        { role: "assistant", content: answer.message },
      ]);
      setDraft("");
      setAttached([]);
      await refreshSessions().catch((error) => setNotice(messageOf(error)));
    } catch (error) {
      setTurns(previous);
      setNotice(
        `${messageOf(error)} Your draft is kept. If the connection dropped, reopen the chat before retrying.`,
      );
    } finally {
      operation.current = false;
      setBusy(false);
      composer.current?.focus();
    }
  }
  async function addFiles(files: File[]) {
    if (operation.current || loading || !files.length) return;
    operation.current = true;
    setPreparing(true);
    setNotice("");
    try {
      const next = [...attached];
      for (const file of files) {
        next.push(await prepareFile(file, model, includeSound));
        validateAttachments(next);
      }
      setAttached(next);
    } catch (error) {
      setNotice(messageOf(error));
    } finally {
      operation.current = false;
      setPreparing(false);
    }
  }
  async function openMemories() {
    setPanel("memory");
    setPanelError("");
    try {
      setMemories(await api<Memory[]>("memories"));
    } catch (error) {
      setPanelError(messageOf(error));
    }
  }
  async function saveMemory(event: FormEvent) {
    event.preventDefault();
    setMemoryBusy(true);
    setPanelError("");
    try {
      await api("memories", "PUT", {
        key: memoryKey.trim(),
        value: memoryValue.trim(),
      });
      setMemories(await api<Memory[]>("memories"));
      setMemoryKey("");
      setMemoryValue("");
    } catch (error) {
      setPanelError(messageOf(error));
    } finally {
      setMemoryBusy(false);
    }
  }
  async function forgetMemory(key: string) {
    if (
      !confirm(
        `Forget “${key}”? Earlier conversations and backups are retained.`,
      )
    )
      return;
    setMemoryBusy(true);
    setPanelError("");
    try {
      await api(`memories/${encodeURIComponent(key)}`, "DELETE");
      setMemories(await api<Memory[]>("memories"));
      if (memoryKey === key) {
        setMemoryKey("");
        setMemoryValue("");
      }
    } catch (error) {
      setPanelError(messageOf(error));
    } finally {
      setMemoryBusy(false);
    }
  }
  const title = turns[0]?.content || "A little space to think";
  return (
    <div className="shell">
      {sidebar && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setSidebar(false)}
        />
      )}
      <aside className={`sidebar ${sidebar ? "open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(event) => {
            event.preventDefault();
            newChat();
          }}
        >
          <span className="brand-mark">e</span>
          <span>
            ELARA<small>ALWAYS A LITTLE CURIOUS</small>
          </span>
        </a>
        <button className="new-chat" onClick={newChat} disabled={locked}>
          <Plus size={17} /> New conversation <span>↗</span>
        </button>
        <label className="search">
          <Search size={15} />
          <input
            aria-label="Search conversations"
            placeholder="Find a conversation"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div className="section-label">
          YOUR CONVERSATIONS <span>{sessions.length}</span>
        </div>
        <nav className="sessions" aria-label="Conversations">
          {sessions
            .filter((item) =>
              item.title.toLowerCase().includes(search.toLowerCase()),
            )
            .map((item) => (
              <button
                key={item.id}
                className={`session ${item.id === active ? "active" : ""}`}
                disabled={busy || preparing}
                aria-current={item.id === active ? "page" : undefined}
                onClick={() => void openSession(item.id)}
              >
                <MessageCircle size={15} />
                <span>{item.title}</span>
              </button>
            ))}
          {!sessions.length && (
            <p className="empty-sessions">
              Good conversations start somewhere.
              <br />
              This is your somewhere.
            </p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <button className="sidebar-link" onClick={() => void openMemories()}>
            <Brain size={17} /> Memories <ChevronRight size={14} />
          </button>
          <button
            className="model-card"
            onClick={() => {
              setPanel("model");
              void refreshModel();
            }}
          >
            <span
              className={`status-dot ${model && status?.provider === "ollama" ? "online" : ""}`}
            />
            <span>
              <strong>
                {status?.model ||
                  (status ? "Offline simulation" : "Connecting…")}
              </strong>
              <small>
                {model && status?.provider === "ollama"
                  ? "Local model · View details"
                  : "View model details"}
              </small>
            </span>
            <ChevronDown size={14} />
          </button>
        </div>
        <div className="local-note">
          <ShieldCheck size={12} /> A space that stays yours.
        </div>
      </aside>
      <main>
        <header>
          <div className="header-title">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setSidebar(true)}
            >
              <Menu />
            </button>
            <span className="header-emblem">✧</span>
            <div>
              <h1 title={title}>{title.slice(0, 64)}</h1>
              <span className="header-subtitle">
                {active ? "Saved on this device" : "Your personal AI companion"}
              </span>
            </div>
          </div>
          <div className="header-actions">
            <span className="local-badge">
              <span />
              {status?.provider === "mock" ? "SIMULATION" : "LOCAL SPACE"}
            </span>
            {active && (
              <button
                className="icon-button"
                aria-label="Delete conversation"
                disabled={locked}
                onClick={() => void deleteChat()}
              >
                <Trash2 size={16} />
              </button>
            )}
            <button
              className="icon-button"
              aria-label="Help and attachment limits"
              onClick={() => setPanel("help")}
            >
              <CircleHelp size={18} />
            </button>
          </div>
        </header>
        <div className="messages" ref={scroll} aria-busy={busy || loading}>
          {!turns.length && !loading ? (
            <section className="welcome">
              <div className="orb">
                <span>e</span>
                <i />
              </div>
              <div className="eyebrow welcome-eyebrow">
                A THOUGHT. A QUESTION. A POSSIBILITY.
              </div>
              <h2>What’s on your mind?</h2>
              <p>
                Bring your ideas, your everyday questions,
                <br className="desktop-break" /> or something you’re still
                figuring out. I’m here.
              </p>
              <div className="suggestions">
                {[
                  {
                    icon: <Sparkles />,
                    label: "Make something",
                    text: "Turn a little idea into a start",
                    prompt:
                      "Help me turn an idea into a small, achievable project.",
                  },
                  {
                    icon: <Image />,
                    label: "Look a little closer",
                    text: "Explore a photo or a moment",
                    prompt: "What do you notice in this attachment?",
                  },
                  {
                    icon: <MessageCircle />,
                    label: "Think it through",
                    text: "Untangle what’s on your mind",
                    prompt:
                      "Help me think through something. Ask me one question at a time.",
                  },
                ].map((item) => (
                  <button
                    key={item.label}
                    disabled={locked}
                    onClick={() => {
                      setDraft(item.prompt);
                      composer.current?.focus();
                    }}
                  >
                    {item.icon}
                    <strong>{item.label}</strong>
                    <small>{item.text}</small>
                    <ArrowUpRight className="suggestion-arrow" />
                  </button>
                ))}
              </div>
              <div className="welcome-caption">
                <span /> A quiet corner, just for you.
              </div>
            </section>
          ) : (
            <div className="turns">
              {loading && <p className="muted">Opening your conversation…</p>}
              {turns.map((turn, index) => (
                <article className={`turn ${turn.role}`} key={index}>
                  <div className="turn-avatar">
                    {turn.role === "assistant" ? "e" : "Y"}
                  </div>
                  <div className="turn-body">
                    <div className="turn-label">
                      {turn.role === "assistant" ? "ELARA" : "You"}
                      {turn.role === "assistant" && <span>LOCAL</span>}
                    </div>
                    <div className="turn-content">{turn.content}</div>
                  </div>
                </article>
              ))}
              {busy && (
                <article className="turn assistant pending" role="status">
                  <div className="turn-avatar">e</div>
                  <div>
                    <div className="turn-label">ELARA</div>
                    <div className="thinking">
                      <i />
                      <i />
                      <i />
                      <span>Thinking with you</span>
                    </div>
                  </div>
                </article>
              )}
            </div>
          )}
        </div>
        <div className="composer-wrap">
          {notice && (
            <div className="notice" role="alert">
              <span>{notice}</span>
              <button
                className="icon-button"
                aria-label="Dismiss notice"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {status?.provider === "mock" && (
            <div className="mode-notice">
              Offline simulation. Launch with scripts/ui.ps1 to use your local
              Ollama model.
            </div>
          )}
          <form
            className="composer"
            onSubmit={send}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              void addFiles([...event.dataTransfer.files]);
            }}
          >
            {!!attached.length && (
              <div className="attachments">
                {attached.map((item) => (
                  <div className="attachment" key={item.id}>
                    {item.preview ? (
                      <img src={item.preview} alt="Attachment preview" />
                    ) : (
                      <span className="attachment-icon">
                        <AttachmentIcon kind={item.kind} />
                      </span>
                    )}
                    <div>
                      <strong title={item.name}>{item.name}</strong>
                      <small>{item.description}</small>
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      disabled={locked}
                      aria-label={`Remove ${item.name}`}
                      onClick={() =>
                        setAttached(
                          attached.filter((value) => value.id !== item.id),
                        )
                      }
                    >
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <label className="sr-only" htmlFor="message">
              Message ELARA
            </label>
            <textarea
              id="message"
              ref={composer}
              placeholder="Tell me what you’re thinking…"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              disabled={locked}
              rows={2}
              maxLength={32000}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="composer-tools">
              <div>
                <button
                  type="button"
                  className="attach-button"
                  disabled={locked}
                  onClick={() => fileInput.current?.click()}
                >
                  <Paperclip size={17} />
                  <span>{preparing ? "Preparing…" : "Attach"}</span>
                </button>
                <span className="tool-divider" />
                <label
                  className={`recall ${recall ? "enabled" : ""}`}
                  title="Use explicitly saved memories in this message"
                >
                  <input
                    type="checkbox"
                    checked={recall}
                    disabled={locked || status?.provider !== "ollama"}
                    onChange={(event) => setRecall(event.target.checked)}
                  />
                  <Brain size={15} />
                  <span>Memory {recall ? "on" : "off"}</span>
                </label>
              </div>
              <div>
                <span className="enter-hint">
                  {busy ? "Taking a moment" : "Enter to send"}
                </span>
                <button
                  type="submit"
                  className="send"
                  disabled={locked || !draft.trim()}
                  aria-label="Send message"
                >
                  <ArrowUp size={20} />
                </button>
              </div>
            </div>
            <input
              className="sr-only"
              ref={fileInput}
              type="file"
              tabIndex={-1}
              multiple
              accept=".txt,.md,.csv,.json,.toml,image/png,image/jpeg,image/webp,audio/*,video/mp4,video/webm,video/quicktime"
              onChange={(event) => {
                void addFiles([...(event.target.files || [])]);
                event.target.value = "";
              }}
            />
          </form>
          <div className="composer-meta">
            <span>
              <ShieldCheck size={12} /> Local conversations. Your pace.
            </span>
            <button onClick={() => setPanel("help")}>
              Images, audio & short videos <ChevronRight size={12} />
            </button>
          </div>
        </div>
      </main>
      {panel === "model" && (
        <Drawer
          title="Meet your model"
          subtitle="The engine behind the conversation. These details come directly from your local Ollama service."
          close={() => setPanel(null)}
        >
          <div className="model-hero">
            <Cpu />
            <h3>{status?.model || "Offline simulation"}</h3>
            <span className="pill">
              {status?.provider === "ollama"
                ? "Runs on your device"
                : "Simulation"}
            </span>
          </div>
          {modelLoading && (
            <p role="status" className="muted">
              Checking your local model…
            </p>
          )}
          {modelError && (
            <p role="alert" className="notice">
              {modelError}
            </p>
          )}
          {model && (
            <>
              <h4>What you can bring</h4>
              <div className="capability-list">
                {[
                  {
                    label: "Images",
                    info: "Photos, screenshots & visual ideas",
                    supported: model.inputs.images,
                    icon: <Image />,
                  },
                  {
                    label: "Audio",
                    info: "Short clips, prepared as local WAV",
                    supported: model.inputs.audio,
                    icon: <AudioLines />,
                  },
                  {
                    label: "Video frames",
                    info: "Up to 6 sampled moments per clip",
                    supported: model.inputs.video,
                    icon: <Video />,
                  },
                ].map((item) => (
                  <div key={item.label}>
                    {item.icon}
                    <span>
                      <strong>{item.label}</strong>
                      <small>{item.info}</small>
                    </span>
                    <span className={`support ${item.supported ? "yes" : ""}`}>
                      {item.supported ? <Check size={16} /> : "Not reported"}
                    </span>
                  </div>
                ))}
              </div>
              <p className="muted">
                Capability badges reflect Ollama’s metadata. Video is sent as
                sampled images, with optional audio. Replies are text.
              </p>
              <details className="technical">
                <summary>
                  Under the hood <ChevronDown size={15} />
                </summary>
                <dl>
                  {Object.entries(model.details).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>{Array.isArray(value) ? value.join(", ") : value}</dd>
                    </div>
                  ))}
                  {Object.entries(model.model_info).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{value.toLocaleString()}</dd>
                    </div>
                  ))}
                  <div>
                    <dt>Reported capabilities</dt>
                    <dd>{model.capabilities.join(", ") || "None"}</dd>
                  </div>
                  {model.limits && (
                    <>
                      <div>
                        <dt>App text input limit</dt>
                        <dd>
                          {model.limits.text_characters.toLocaleString()}{" "}
                          characters
                        </dd>
                      </div>
                      <div>
                        <dt>Reply limit</dt>
                        <dd>
                          {model.limits.output_tokens.toLocaleString()} tokens
                        </dd>
                      </div>
                      <div>
                        <dt>Request timeout</dt>
                        <dd>{model.limits.timeout_seconds}s</dd>
                      </div>
                    </>
                  )}
                </dl>
              </details>
            </>
          )}
          <button
            className="secondary full"
            onClick={() => void refreshModel()}
            disabled={modelLoading}
          >
            Refresh model details
          </button>
        </Drawer>
      )}
      {panel === "memory" && (
        <Drawer
          title="Little things, remembered"
          subtitle="Choose what ELARA remembers across conversations. You can edit or forget a fact whenever you like."
          close={() => setPanel(null)}
        >
          {panelError && (
            <p className="notice" role="alert">
              {panelError}
            </p>
          )}
          <div className="memory-count">
            <Brain size={17} />
            {memories.length} of 20 memories
          </div>
          {!memories.length && (
            <div className="empty-memory">
              <Sparkles />
              <h3>A fresh start.</h3>
              <p>
                Add your name, a project, or something you’d like me to keep in
                mind.
              </p>
            </div>
          )}
          {memories.map((fact) => (
            <div className="memory-card" key={fact.key}>
              <strong>{fact.key}</strong>
              <p>{fact.value}</p>
              <div>
                <button
                  className="text-button"
                  disabled={memoryBusy}
                  onClick={() => {
                    setMemoryKey(fact.key);
                    setMemoryValue(fact.value);
                  }}
                >
                  Edit
                </button>
                <button
                  className="text-button danger"
                  disabled={memoryBusy}
                  onClick={() => void forgetMemory(fact.key)}
                >
                  Forget
                </button>
              </div>
            </div>
          ))}
          <form id="memory-form" className="memory-form" onSubmit={saveMemory}>
            <h4>
              {memories.some((fact) => fact.key === memoryKey)
                ? "Update a memory"
                : "Add a memory"}
            </h4>
            <label htmlFor="memory-key">A short key</label>
            <input
              id="memory-key"
              placeholder="e.g. name or current_project"
              pattern="[a-z][a-z0-9_-]{0,47}"
              maxLength={48}
              required
              value={memoryKey}
              onChange={(event) => setMemoryKey(event.target.value)}
            />
            <label htmlFor="memory-value">What should I remember?</label>
            <textarea
              id="memory-value"
              placeholder="Something you’d like me to know…"
              maxLength={500}
              rows={3}
              required
              value={memoryValue}
              onChange={(event) => setMemoryValue(event.target.value)}
            />
            <button
              className="primary full"
              disabled={memoryBusy || !memoryKey.trim() || !memoryValue.trim()}
            >
              {memoryBusy ? "Saving…" : "Save memory"}
            </button>
            <p className="muted">
              Saved locally. Earlier replies and backups can still contain a
              forgotten fact.
            </p>
          </form>
        </Drawer>
      )}
      {panel === "help" && (
        <Drawer
          title="A little room for more"
          subtitle="Bring context into your conversation. Selected files are prepared in your browser and sent only to local Ollama."
          close={() => setPanel(null)}
        >
          <div className="help-item">
            <Image />
            <div>
              <h4>Images</h4>
              <p>
                JPEG, PNG or WebP. Resized to fit 1536 pixels and sent as JPEG.
              </p>
            </div>
          </div>
          <div className="help-item">
            <AudioLines />
            <div>
              <h4>Audio</h4>
              <p>
                Up to 30 seconds. Supported browser formats are converted to
                mono 16 kHz WAV.
              </p>
            </div>
          </div>
          <div className="help-item">
            <Video />
            <div>
              <h4>Short videos</h4>
              <p>
                Up to 30 seconds, sampled into at most 6 still frames. This is a
                preview of moments, not full motion analysis.
              </p>
              <label className="sound-option">
                <input
                  type="checkbox"
                  checked={includeSound}
                  disabled={!model?.inputs.audio || locked}
                  onChange={(event) => setIncludeSound(event.target.checked)}
                />
                Include video sound
              </label>
              <small>
                Applies to videos you attach next. The attachment card confirms
                whether sound is included.
              </small>
            </div>
          </div>
          <div className="help-item">
            <FileText />
            <div>
              <h4>Text files</h4>
              <p>
                TXT, Markdown, CSV, JSON and TOML. Up to 8 files and 16,000
                characters in total.
              </p>
            </div>
          </div>
          <div className="privacy-card">
            <ShieldCheck />
            <div>
              <strong>Just for this message</strong>
              <p>
                Attachments clear after sending. Their bytes are not saved in
                chat history; replies may quote them. Reattach a file to inspect
                it again.
              </p>
            </div>
          </div>
          <p className="muted">
            Media files: up to 40 MiB before preparation, ten prepared parts and
            16 MB encoded per message. One audio clip or soundtrack. No
            microphone or camera recording.
          </p>
          <button
            className="secondary full"
            onClick={() => {
              setPanel("model");
              void refreshModel();
            }}
          >
            Check model support <ArrowUpRight size={15} />
          </button>
        </Drawer>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
