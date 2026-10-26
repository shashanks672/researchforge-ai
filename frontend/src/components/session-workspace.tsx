"use client";

import { DocumentWorkspace } from "./document-workspace";
import { RunPanel } from "./run-panel";

import { useEffect, useRef, useState } from "react";
import {
  fetchSession,
  fetchSessionPage,
  saveSession,
  type ResearchMode,
  type ResearchSession,
  type SessionPage,
} from "../lib/sessions";

function message(error: unknown, fallback: string): string {
  return error instanceof Error &&
    error.name !== "TimeoutError" &&
    error.name !== "TypeError"
    ? error.message
    : fallback;
}

export function SessionWorkspace() {
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<ResearchMode>("web");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [history, setHistory] = useState<SessionPage | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [selected, setSelected] = useState<ResearchSession | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const historySequence = useRef(0);
  const detailController = useRef<AbortController | null>(null);
  const saveInFlight = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    const sequence = ++historySequence.current;
    void fetchSessionPage(0, controller.signal, 5)
      .then((page) => {
        if (!controller.signal.aborted && sequence === historySequence.current)
          setHistory(page);
      })
      .catch((error) => {
        if (!controller.signal.aborted && sequence === historySequence.current)
          setHistoryError(message(error, "Could not load history. Try again."));
      })
      .finally(() => {
        if (!controller.signal.aborted && sequence === historySequence.current)
          setHistoryLoading(false);
      });
    return () => {
      controller.abort();
      detailController.current?.abort();
    };
  }, []);

  async function loadHistory(offset: number) {
    const sequence = ++historySequence.current;
    setHistoryLoading(true);
    setHistoryError("");
    try {
      const page = await fetchSessionPage(offset, undefined, 5);
      if (sequence === historySequence.current) setHistory(page);
    } catch (error) {
      if (sequence === historySequence.current)
        setHistoryError(message(error, "Could not load history. Try again."));
    } finally {
      if (sequence === historySequence.current) setHistoryLoading(false);
    }
  }

  async function openSession(id: string) {
    detailController.current?.abort();
    const controller = new AbortController();
    detailController.current = controller;
    setSelected(null);
    setDetailLoading(true);
    setDetailError("");
    try {
      const record = await fetchSession(
        id,
        AbortSignal.any([controller.signal, AbortSignal.timeout(12000)]),
      );
      if (!controller.signal.aborted) setSelected(record);
    } catch (error) {
      if (!controller.signal.aborted)
        setDetailError(
          message(error, "Could not load this session. Try again."),
        );
    } finally {
      if (!controller.signal.aborted) setDetailLoading(false);
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saveInFlight.current) return;
    setFormError("");
    setNotice("");
    const trimmed = question.trim();
    if (trimmed.length < 10 || trimmed.length > 4000) {
      setFormError(
        "Enter a research question between 10 and 4,000 characters.",
      );
      return;
    }
    saveInFlight.current = true;
    setSaving(true);
    try {
      const record = await saveSession(
        trimmed,
        mode,
        mode === "web" ? [] : documentIds,
      );
      detailController.current?.abort();
      setSelected(record);
      setDetailLoading(false);
      setDetailError("");
      setQuestion("");
      setNotice(
        "Session saved as pending. Select the session to inspect available execution options.",
      );
      await loadHistory(0);
    } catch (error) {
      setFormError(
        message(
          error,
          "Could not confirm the save. Refresh history before trying again.",
        ),
      );
    } finally {
      saveInFlight.current = false;
      setSaving(false);
    }
  }

  return (
    <>
      <DocumentWorkspace selected={documentIds} onSelection={setDocumentIds} />
      <section className="composer" aria-labelledby="research-title">
        <form onSubmit={submit} noValidate>
          <div className="composer-header">
            <h2 id="research-title">
              <span className="small-mark" aria-hidden="true">
                ✳
              </span>{" "}
              Save a research question
            </h2>
            <span className="muted-pill">PHASE 4 · EVIDENCE ASSESSMENT</span>
          </div>
          <label className="sr-only" htmlFor="question">
            Research question
          </label>
          <textarea
            id="question"
            placeholder="What would you like to understand?"
            rows={3}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={4000}
            disabled={saving}
            aria-invalid={Boolean(formError)}
            aria-describedby="composer-help question-error"
          />
          <div className="composer-footer">
            <div className="mode-picker">
              <label htmlFor="mode">Research mode</label>
              <select
                id="mode"
                value={mode}
                onChange={(event) =>
                  setMode(event.target.value as ResearchMode)
                }
                disabled={saving}
              >
                <option value="web">Web</option>
                <option value="documents">Documents</option>
                <option value="combined">Combined</option>
              </select>
            </div>
            <button className="primary-button" type="submit" disabled={saving}>
              {saving ? "Saving session…" : "Save session"}
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <p id="composer-help" className="composer-help">
            Save your question first, then explicitly start research below.
            Document mode uses indexed passages without web search. Combined
            mode discloses missing documents.
          </p>
          {formError && (
            <p id="question-error" className="error-message" role="alert">
              {formError}
            </p>
          )}
          {notice && (
            <p className="success-message" role="status">
              {notice}
            </p>
          )}
        </form>
      </section>

      <section
        id="history"
        className="history-section"
        aria-labelledby="history-title"
      >
        <div className="section-heading">
          <h2 id="history-title">Saved research sessions</h2>
          <button
            className="text-button"
            onClick={() => void loadHistory(history?.offset ?? 0)}
            disabled={historyLoading}
          >
            Refresh history ↗
          </button>
        </div>
        <div className="session-grid">
          <div className="history-card" aria-busy={historyLoading}>
            {historyLoading && (
              <p className="empty-copy">Loading saved sessions…</p>
            )}
            {historyError && (
              <p className="error-message" role="alert">
                {historyError}
              </p>
            )}
            {!historyLoading &&
              !historyError &&
              history?.items.length === 0 && (
                <p className="empty-copy">
                  No sessions on this page. Save your first research question
                  above, or return to a previous page.
                </p>
              )}
            <ul className="session-list">
              {history?.items.map((record) => (
                <li key={record.id}>
                  <button
                    onClick={() => void openSession(record.id)}
                    className={`session-row ${selected?.id === record.id ? "selected" : ""}`}
                    aria-pressed={selected?.id === record.id}
                  >
                    <span className="session-question">{record.question}</span>
                    <span className="session-meta">
                      <span>
                        {record.mode} ·{" "}
                        {new Date(record.created_at).toLocaleString()}
                      </span>
                      <span
                        className={`session-status status-${record.status}`}
                      >
                        {record.status}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {history && (
              <div className="pagination">
                <span>
                  {history.total} saved · Page{" "}
                  {Math.floor(history.offset / history.limit) + 1}
                </span>
                <div>
                  <button
                    disabled={historyLoading || history.offset === 0}
                    onClick={() =>
                      void loadHistory(
                        Math.max(0, history.offset - history.limit),
                      )
                    }
                  >
                    Previous
                  </button>
                  <button
                    disabled={historyLoading || !history.has_more}
                    onClick={() =>
                      void loadHistory(history.offset + history.limit)
                    }
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
          <section
            className="detail-card"
            aria-labelledby="detail-title"
            aria-busy={detailLoading}
          >
            <div className="section-heading">
              <h3 id="detail-title">Session details</h3>
              {selected && (
                <button
                  className="text-button"
                  onClick={() => void openSession(selected.id)}
                >
                  Refresh status
                </button>
              )}
            </div>
            {detailLoading && (
              <p className="empty-copy">Loading session details…</p>
            )}
            {detailError && (
              <p className="error-message" role="alert">
                {detailError}
              </p>
            )}
            {!selected && !detailLoading && !detailError && (
              <p className="empty-copy">
                Choose a saved session to inspect its question, mode, timestamps
                and status.
              </p>
            )}
            {selected && (
              <>
                <p className="detail-question">{selected.question}</p>
                <dl className="session-facts">
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <span
                        className={`session-status status-${selected.status}`}
                      >
                        {selected.status}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt>Mode</dt>
                    <dd>{selected.mode}</dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd>{new Date(selected.created_at).toLocaleString()}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{new Date(selected.updated_at).toLocaleString()}</dd>
                  </div>
                  <div>
                    <dt>Session ID</dt>
                    <dd className="session-id">{selected.id}</dd>
                  </div>
                </dl>
                {selected.error_message && (
                  <p className="error-message">{selected.error_message}</p>
                )}
                <p className="composer-help">
                  Saved in PostgreSQL. Execution uses only the explicitly
                  configured providers.
                </p>
                <RunPanel
                  key={selected.id}
                  session={selected}
                  onSessionChange={(updated) => {
                    setSelected(updated);
                    void loadHistory(history?.offset ?? 0);
                  }}
                />
              </>
            )}
          </section>
        </div>
      </section>
    </>
  );
}
