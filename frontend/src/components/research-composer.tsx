"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchSessionPage,
  saveSession,
  type ResearchMode,
} from "../lib/sessions";
import { executeRun } from "../lib/runs";
import type { SystemStatus } from "../lib/system";
import { useDocuments } from "../lib/use-documents";
import { Icon } from "./icons";

const examples = [
  "Summarize the main findings in my research paper",
  "Compare the methods used in these two documents",
  "What does my PDF say about the study results?",
];

function readableError(error: unknown) {
  if (!(error instanceof Error))
    return "Something went wrong. Your saved research is still available in History.";
  if (error.name === "TimeoutError" || error.name === "TypeError")
    return "We could not confirm the request. Check History before trying again to avoid a duplicate.";
  return error.message;
}

export function ResearchComposer() {
  const router = useRouter();
  const { documents, loading: documentsLoading } = useDocuments();
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [systemError, setSystemError] = useState("");
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<ResearchMode>("documents");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [validation, setValidation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [liveApproved, setLiveApproved] = useState(false);
  const busyRef = useRef(false);
  const pickerRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/system", {
      cache: "no-store",
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("Research setup is unavailable.");
        return (await response.json()) as SystemStatus;
      })
      .then((value) => {
        if (controller.signal.aborted) return;
        setSystem(value);
        setSystemError("");
        setMode(value.search_provider === "disabled" ? "documents" : "web");
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setSystemError(
            "Could not check which research sources are available. Refresh to try again.",
          );
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const documentId = new URLSearchParams(window.location.search).get(
      "document",
    );
    if (
      documentId &&
      documents.some(
        (item) => item.id === documentId && item.status === "ready",
      )
    ) {
      const timer = window.setTimeout(() => {
        setSelectedIds((current) =>
          current.includes(documentId) ? current : [...current, documentId],
        );
      }, 0);
      return () => window.clearTimeout(timer);
    }
  }, [documents]);

  const readyDocuments = useMemo(
    () => documents.filter((document) => document.status === "ready"),
    [documents],
  );
  const selectedDocuments = readyDocuments.filter((document) =>
    selectedIds.includes(document.id),
  );
  const webAvailable = Boolean(system && system.search_provider !== "disabled");
  const researchEnabled = Boolean(
    system?.research_enabled && system.execution_mode !== "disabled",
  );
  const hasSources =
    mode === "web" ? webAvailable : selectedDocuments.length > 0;
  const canStart =
    question.trim().length >= 10 &&
    question.trim().length <= 4000 &&
    Boolean(system) &&
    !systemError &&
    researchEnabled &&
    hasSources &&
    (system?.execution_mode !== "live" || liveApproved);

  function toggleDocument(id: string) {
    setSelectedIds((current) => {
      if (current.includes(id)) return current.filter((value) => value !== id);
      if (current.length >= 20) return current;
      return [...current, id];
    });
  }

  async function startResearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busyRef.current) return;
    const trimmed = question.trim();
    if (trimmed.length < 10 || trimmed.length > 4000) {
      setValidation("Write a question between 10 and 4,000 characters.");
      return;
    }
    if (!system || !researchEnabled || !hasSources) {
      setValidation(
        mode === "web"
          ? "Web search is unavailable in this setup. Choose a ready document or open Settings."
          : "Choose at least one ready document before starting.",
      );
      return;
    }
    setValidation("");
    setError("");
    busyRef.current = true;
    setBusy(true);
    let savedId: string | null = null;
    try {
      const session = await saveSession(
        trimmed,
        mode,
        mode === "web" ? [] : selectedIds,
      );
      savedId = session.id;
      try {
        await executeRun(
          session.id,
          system.execution_mode as "mock" | "local" | "live",
        );
        router.push(`/research/${session.id}`);
      } catch (runError) {
        router.push(`/research/${session.id}?notice=not-started`);
        setError(readableError(runError));
      }
    } catch (saveError) {
      if (savedId) router.push(`/research/${savedId}?notice=not-started`);
      else setError(readableError(saveError));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function openPicker() {
    if (pickerRef.current?.showModal) pickerRef.current.showModal();
  }

  const modeChoices: {
    value: ResearchMode;
    title: string;
    icon: "file" | "search" | "library";
    disabled?: boolean;
  }[] = [
    { value: "documents", title: "My documents", icon: "file" },
    { value: "web", title: "Web", icon: "search", disabled: !webAvailable },
    {
      value: "combined",
      title: "Documents + web",
      icon: "library",
      disabled: !webAvailable,
    },
  ];

  return (
    <div className="home-page">
      <section className="home-hero" aria-labelledby="home-title">
        <div>
          <span className="eyebrow">
            A clearer path from question to evidence
          </span>
          <h1 id="home-title">Good questions deserve grounded answers.</h1>
          <p>
            Explore a topic or make sense of your documents. Every answer comes
            with evidence you can inspect.
          </p>
        </div>
        <div className="hero-art" aria-hidden="true" />
      </section>

      <form className="card composer-card" onSubmit={startResearch} noValidate>
        <label className="composer-label" htmlFor="research-question">
          <Icon name="spark" size={18} /> What would you like to research?
        </label>
        <textarea
          id="research-question"
          className="question-input"
          value={question}
          onChange={(event) => {
            setQuestion(event.target.value);
            setValidation("");
          }}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="Ask a focused research question…"
          maxLength={4000}
          aria-invalid={Boolean(validation)}
          aria-describedby="question-hint question-error"
          disabled={busy}
        />
        <div className="composer-controls">
          <div className="composer-tools">
            <div
              className="source-mode-group"
              role="group"
              aria-label="Choose research sources"
            >
              {modeChoices.map((choice) => (
                <button
                  key={choice.value}
                  className="source-mode-option"
                  type="button"
                  aria-pressed={mode === choice.value}
                  disabled={choice.disabled || busy}
                  title={
                    choice.disabled
                      ? "Public search is off. The free Wikipedia option needs explicit setup and a real operator contact."
                      : undefined
                  }
                  onClick={() => {
                    setMode(choice.value);
                    setValidation("");
                  }}
                >
                  <Icon name={choice.icon} size={15} /> {choice.title}
                </button>
              ))}
            </div>
            {mode !== "web" && (
              <button
                className="composer-attach"
                type="button"
                onClick={openPicker}
                disabled={busy}
              >
                <Icon name="plus" size={17} /> Add documents
                {selectedDocuments.length
                  ? ` · ${selectedDocuments.length}`
                  : ""}
              </button>
            )}
          </div>
          <button
            className="button button-primary"
            type="submit"
            disabled={!canStart || busy}
          >
            {busy ? "Starting your research…" : "Start research"}
            {!busy && <Icon name="arrow" size={17} />}
          </button>
        </div>
        {selectedDocuments.length > 0 && (
          <div className="selected-documents" aria-label="Selected documents">
            {selectedDocuments.map((document) => (
              <span className="document-chip" key={document.id}>
                <Icon name="file" size={14} />
                <span title={document.filename}>{document.filename}</span>
                <button
                  type="button"
                  aria-label={`Remove ${document.filename}`}
                  onClick={() => toggleDocument(document.id)}
                >
                  <Icon name="close" size={14} />
                </button>
              </span>
            ))}
          </div>
        )}
        <p className="composer-hint" id="question-hint">
          {mode === "documents"
            ? selectedDocuments.length
              ? `Searching only the ${selectedDocuments.length} document${selectedDocuments.length === 1 ? "" : "s"} you selected.`
              : "Select one or more ready documents to keep the research grounded in your files."
            : mode === "combined"
              ? "Your selected files and the configured public search sources will be used."
              : "The configured web source will be used for this question."}
        </p>
        {system?.search_provider === "disabled" && (
          <p className="availability-note">
            Public search is off in this workspace. The free option searches
            English Wikipedia only and needs an explicit opt-in plus the local
            operator’s real contact URL or email. Your selected documents still
            work on their own.
          </p>
        )}
        {system?.execution_mode === "mock" && (
          <p className="availability-note">
            Demo mode uses deterministic sample research. It does not make real
            model calls or establish factual findings.
          </p>
        )}
        {system?.execution_mode === "local" && (
          <p className="availability-note">
            Local AI · {system.model ?? "Ollama"}. Long questions may take a
            little time while your Mac prepares the report.
          </p>
        )}
        {system?.execution_mode === "live" && (
          <label className="live-acknowledgment">
            <input
              type="checkbox"
              checked={liveApproved}
              onChange={(event) => setLiveApproved(event.target.checked)}
            />{" "}
            I understand this setup uses approved hosted services and may incur
            provider costs.
          </label>
        )}
        {validation && (
          <p className="composer-error" id="question-error" role="alert">
            {validation}
          </p>
        )}
        {systemError && (
          <p className="error-banner" role="alert">
            {systemError}
          </p>
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error} Your session, if saved, is available in History.
          </p>
        )}
      </form>

      <div className="examples">
        <p className="examples-label">A few ideas to get you started</p>
        <div className="example-list">
          {examples.map((example) => (
            <button
              className="example-prompt"
              key={example}
              type="button"
              onClick={() => setQuestion(example)}
            >
              {example}
            </button>
          ))}
        </div>
      </div>

      <RecentResearch />
      <p className="trust-note">
        <Icon name="check" size={16} /> Evidence gaps are shown clearly. We
        never fill them with a guessed answer.
      </p>

      <dialog
        className="picker-dialog"
        ref={pickerRef}
        aria-labelledby="picker-title"
        aria-describedby="picker-description"
      >
        <div className="dialog-content">
          <div className="dialog-head">
            <div>
              <h2 id="picker-title">Choose your documents</h2>
              <p id="picker-description">
                Only ready documents you select will be included in this
                research.
              </p>
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="Close document picker"
              onClick={() => pickerRef.current?.close()}
            >
              <Icon name="close" />
            </button>
          </div>
          {documentsLoading && (
            <p className="small-copy">Loading your library…</p>
          )}
          {!documentsLoading && readyDocuments.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">
                <Icon name="file" />
              </div>
              <h3>Your library is ready when you are</h3>
              <p>
                Upload a PDF, DOCX, text, or Markdown file before starting
                document research.
              </p>
              <Link className="button button-primary" href="/library">
                Open your library <Icon name="arrow" size={16} />
              </Link>
            </div>
          )}
          {readyDocuments.length > 0 && (
            <div className="document-pick-list">
              {readyDocuments.map((document) => (
                <label className="document-pick-row" key={document.id}>
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(document.id)}
                    onChange={() => toggleDocument(document.id)}
                    disabled={
                      !selectedIds.includes(document.id) &&
                      selectedIds.length >= 20
                    }
                  />
                  <span>
                    <strong>{document.filename}</strong>
                    <small>
                      {document.page_count
                        ? `${document.page_count} pages · `
                        : ""}
                      {(document.size_bytes / 1024).toFixed(0)} KB · indexed and
                      ready
                    </small>
                  </span>
                </label>
              ))}
            </div>
          )}
          <div className="dialog-actions">
            <button
              className="button button-secondary"
              type="button"
              onClick={() => pickerRef.current?.close()}
            >
              Done
              {selectedIds.length ? ` · ${selectedIds.length} selected` : ""}
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}

function RecentResearch() {
  const [items, setItems] = useState<
    Awaited<ReturnType<typeof fetchSessionPage>>["items"]
  >([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    void fetchSessionPage(0, controller.signal, 3)
      .then((page) => {
        if (!controller.signal.aborted) setItems(page.items);
      })
      .catch(() => {
        if (!controller.signal.aborted) setItems([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);
  return (
    <section className="recent-section" aria-labelledby="recent-title">
      <div className="section-heading">
        <h2 id="recent-title">Pick up where you left off</h2>
        <Link className="text-link" href="/research">
          All research <span aria-hidden="true">→</span>
        </Link>
      </div>
      {loading ? (
        <div
          className="recent-grid"
          aria-busy="true"
          aria-label="Loading recent research"
        >
          <div className="card recent-card skeleton" />
          <div className="card recent-card skeleton" />
          <div className="card recent-card skeleton" />
        </div>
      ) : items.length ? (
        <div className="recent-grid">
          {items.map((item) => (
            <Link
              className="card recent-card"
              href={`/research/${item.id}`}
              key={item.id}
            >
              <p>{item.question}</p>
              <div className="recent-card-footer">
                <span>
                  {new Date(item.updated_at).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })}{" "}
                  ·{" "}
                  {item.mode === "documents"
                    ? "My documents"
                    : item.mode === "combined"
                      ? "Documents + web"
                      : "Web"}
                </span>
                <span className={`status-pill status-${item.status}`}>
                  {item.status === "failed"
                    ? "Could not finish"
                    : item.status === "pending"
                      ? "Not started"
                      : item.status === "running"
                        ? "In progress"
                        : item.status === "completed"
                          ? "Completed"
                          : "Cancelled"}
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="card empty-state">
          <div className="empty-icon">
            <Icon name="history" />
          </div>
          <h3>Your research will appear here</h3>
          <p>
            Start with a question above. Your saved sessions will be ready to
            revisit.
          </p>
          <Link className="text-link" href="/research">
            Browse History
          </Link>
        </div>
      )}
    </section>
  );
}
