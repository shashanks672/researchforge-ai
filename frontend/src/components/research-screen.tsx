"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { saveSession, type ResearchSession } from "../lib/sessions";
import {
  cancelRun,
  currentSession,
  executeRun,
  getRun,
  type ResearchRun,
} from "../lib/runs";
import type { SystemStatus } from "../lib/system";
import { CitationDialog, type ResearchSource } from "./citation-dialog";
import { EvidenceReview } from "./evidence-review";
import { Icon } from "./icons";
import { MarkdownReport } from "./markdown-report";

const progressStages = [
  { label: "Planning the research", keys: ["planning", "planned"] },
  {
    label: "Finding relevant evidence",
    keys: ["collecting", "collected", "documents_retrieved"],
  },
  {
    label: "Checking whether evidence is enough",
    keys: ["assessing_sufficiency", "evidence_assessed"],
  },
  {
    label: "Writing the report",
    keys: ["writing", "written", "revised_draft"],
  },
  {
    label: "Reviewing claims and citations",
    keys: [
      "verifying_claims",
      "claims_assessed",
      "followup_research",
      "verification_complete",
    ],
  },
];

function terminal(status?: ResearchSession["status"], stage?: string) {
  return (
    ["completed", "failed", "cancelled"].includes(status ?? "") ||
    ["completed", "failed", "cancelled"].includes(stage ?? "")
  );
}

function progressIndex(stage: string) {
  const index = progressStages.findIndex((item) => item.keys.includes(stage));
  return Math.max(0, index);
}

function stageLabel(stage: string) {
  const found = progressStages.find((item) => item.keys.includes(stage));
  if (found) return found.label;
  if (stage === "queued" || stage === "pending") return "Waiting to start";
  return stage ? stage.replaceAll("_", " ") : "Preparing research";
}

function runErrorMessage(error: unknown) {
  if (!(error instanceof Error))
    return "Research could not be completed. Your saved question remains in History.";
  if (error.name === "TimeoutError" || error.name === "TypeError")
    return "We could not confirm the research status. Refresh this page before starting another attempt.";
  return error.message;
}

function runModeLabel(run: ResearchRun | null, system: SystemStatus | null) {
  const mode = run?.execution_mode ?? system?.execution_mode;
  if (mode === "local") return `LOCAL · ${system?.model ?? "on-device model"}`;
  if (mode === "mock") return "DEMO · synthetic results";
  if (mode === "live") return "HOSTED AI";
  return "Research mode unavailable";
}

export function ResearchScreen({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [session, setSession] = useState<ResearchSession | null>(null);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedSource, setSelectedSource] = useState<ResearchSource | null>(
    null,
  );
  const busyRef = useRef(false);
  const notice = searchParams.get("notice");

  const refresh = useCallback(
    async (signal?: AbortSignal) => {
      const [sessionResult, runResult] = await Promise.all([
        currentSession(sessionId),
        getRun(sessionId),
      ]);
      if (signal?.aborted) return;
      setSession(sessionResult);
      setRun(runResult);
      setError("");
    },
    [sessionId],
  );

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void Promise.all([
        refresh(controller.signal),
        fetch("/api/system", {
          cache: "no-store",
          signal: AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(5000),
          ]),
        })
          .then(async (response) => {
            if (!response.ok) throw new Error("Setup unavailable");
            return response.json() as Promise<SystemStatus>;
          })
          .then((value) => {
            if (!controller.signal.aborted) setSystem(value);
          })
          .catch(() => undefined),
      ])
        .catch((failure: unknown) => {
          if (!controller.signal.aborted) setError(runErrorMessage(failure));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [refresh]);

  useEffect(() => {
    if (!session || terminal(session.status, run?.stage)) return;
    const timer = window.setInterval(() => {
      void refresh().catch((failure: unknown) =>
        setError(runErrorMessage(failure)),
      );
    }, 1600);
    return () => window.clearInterval(timer);
  }, [session, run?.stage, refresh]);

  const sources = run?.sources ?? [];
  const documentIds = useMemo(
    () => session?.document_ids ?? [],
    [session?.document_ids],
  );
  const inProgress = Boolean(
    session?.status === "running" ||
    (run && !terminal(session?.status, run.stage)),
  );
  const canStart = Boolean(session?.status === "pending" && !run && !busy);

  async function startSavedResearch() {
    if (!session || !canStart || busyRef.current) return;
    if (
      !system?.research_enabled ||
      !["local", "mock", "live"].includes(system.execution_mode)
    ) {
      setError(
        "Research is unavailable in the current setup. Check Settings before starting.",
      );
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await executeRun(
        session.id,
        system.execution_mode as "local" | "mock" | "live",
      );
      setRun(result);
      await refresh();
    } catch (failure) {
      setError(runErrorMessage(failure));
      await refresh().catch(() => undefined);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function cancelResearch() {
    if (!session || !inProgress || busy) return;
    setBusy(true);
    try {
      await cancelRun(session.id);
      await refresh();
    } catch (failure) {
      setError(runErrorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function retryAsNewResearch() {
    if (
      !session ||
      busyRef.current ||
      !system?.research_enabled ||
      !["local", "mock", "live"].includes(system.execution_mode)
    )
      return;
    busyRef.current = true;
    setBusy(true);
    setError("");
    try {
      const next = await saveSession(
        session.question,
        session.mode,
        documentIds,
      );
      await executeRun(
        next.id,
        system.execution_mode as "local" | "mock" | "live",
      );
      router.push(`/research/${next.id}`);
    } catch (failure) {
      setError(runErrorMessage(failure));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  if (loading)
    return (
      <div className="card card-pad report-loading" aria-busy="true">
        <span className="eyebrow">Opening saved research</span>
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line" />
      </div>
    );
  if (!session)
    return (
      <section className="card empty-state">
        <div className="empty-icon">
          <Icon name="search" />
        </div>
        <h1>Research not found</h1>
        <p>
          {error ||
            "This saved research could not be found in the local workspace."}
        </p>
        <Link className="button button-primary" href="/research">
          Open History
        </Link>
      </section>
    );

  const statusClass = inProgress ? "running" : session.status;

  return (
    <div className="research-result" aria-labelledby="research-title">
      <div className="report-toolbar">
        <Link className="text-link back-link" href="/research">
          <Icon name="arrow" size={15} /> Back to History
        </Link>
        <span className={`status-pill status-${statusClass}`}>
          {inProgress
            ? stageLabel(run?.stage ?? "pending")
            : session.status === "completed"
              ? "Completed"
              : session.status === "pending"
                ? "Not started"
                : session.status === "failed"
                  ? "Could not finish"
                  : "Cancelled"}
        </span>
      </div>
      {notice === "not-started" && (
        <p className="info-banner">
          Your question was saved, but we could not confirm that the run
          started. Check its status here before trying again.
        </p>
      )}
      <header className="report-header">
        <span className="eyebrow">
          {session.mode === "documents"
            ? "Document research"
            : session.mode === "combined"
              ? "Documents + web research"
              : "Web research"}
        </span>
        <h1 className="report-title" id="research-title">
          {session.question}
        </h1>
        <div className="report-meta">
          <span>
            {new Date(session.created_at).toLocaleString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </span>
          <span className="run-mode-label">{runModeLabel(run, system)}</span>
          <span>
            {sources.length} source{sources.length === 1 ? "" : "s"}
          </span>
        </div>
      </header>

      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {inProgress && (
        <section
          className="card progress-card"
          aria-live="polite"
          aria-label="Research progress"
        >
          <div className="section-heading">
            <div>
              <span className="eyebrow">Research is underway</span>
              <h2>{stageLabel(run?.stage ?? "pending")}</h2>
            </div>
            {run && (
              <span className="run-mode-label">
                {run.execution_mode === "local"
                  ? "LOCAL"
                  : run.execution_mode === "mock"
                    ? "DEMO"
                    : "HOSTED AI"}
              </span>
            )}
          </div>
          <ol className="progress-list">
            {progressStages.map((stage, index) => (
              <li
                className={
                  index < progressIndex(run?.stage ?? "")
                    ? "is-done"
                    : index === progressIndex(run?.stage ?? "")
                      ? "is-current"
                      : ""
                }
                key={stage.label}
              >
                <span aria-hidden="true">
                  {index < progressIndex(run?.stage ?? "") ? (
                    <Icon name="check" size={13} />
                  ) : (
                    index + 1
                  )}
                </span>
                {stage.label}
              </li>
            ))}
          </ol>
          <p className="small-copy">
            The stages update from the saved run. There is no estimated
            percentage.
          </p>
          <button
            className="button button-secondary button-small"
            type="button"
            onClick={cancelResearch}
            disabled={busy}
          >
            Cancel research
          </button>
        </section>
      )}

      {canStart && (
        <section className="card start-saved-card">
          <div>
            <h2>This question is saved and ready</h2>
            <p>
              Start it using the research provider currently configured in
              Settings.
            </p>
            {session.mode !== "web" && documentIds.length > 0 && (
              <p className="small-copy">
                It will search only {documentIds.length} selected file
                {documentIds.length === 1 ? "" : "s"}.
              </p>
            )}
          </div>
          <button
            className="button button-primary"
            type="button"
            onClick={startSavedResearch}
            disabled={busy || !system?.research_enabled}
          >
            {busy ? "Starting…" : "Start research"}
            <Icon name="arrow" size={16} />
          </button>
        </section>
      )}

      {session.status === "failed" && !inProgress && (
        <section className="card failure-card">
          <div className="failure-icon">
            <Icon name="close" />
          </div>
          <div>
            <h2>Research could not finish</h2>
            <p>
              {session.error_message ||
                (run?.error_code === "no_evidence"
                  ? "No usable evidence was found, so the system did not write a report."
                  : "The research run stopped before a complete report was saved.")}
            </p>
            {run?.error_code && (
              <details className="advanced-details">
                <summary>Technical details</summary>
                <code>{run.error_code}</code>
              </details>
            )}
            <button
              className="button button-secondary button-small"
              type="button"
              onClick={retryAsNewResearch}
              disabled={busy || !system?.research_enabled}
            >
              {busy ? "Starting a new attempt…" : "Start a new attempt"}
            </button>
          </div>
        </section>
      )}
      {session.status === "cancelled" && !inProgress && (
        <p className="info-banner">
          This research was cancelled. No completed report is available.
        </p>
      )}
      {session.status === "pending" && !run && !canStart && (
        <p className="info-banner">
          Waiting for the saved research run to appear. Refreshing its status
          automatically.
        </p>
      )}

      {run && sources.length > 0 && (
        <section className="card source-summary">
          <div className="section-heading">
            <div>
              <h2>Evidence used</h2>
              <p className="small-copy">
                Open a source to inspect its saved passage and page details.
              </p>
            </div>
            <span className="section-kicker">{sources.length} retrieved</span>
          </div>
          <div className="source-list">
            {sources.map((source) => (
              <button
                className="source-row"
                key={source.source_id}
                type="button"
                onClick={() => setSelectedSource(source)}
              >
                <span className="source-label">{source.source_id}</span>
                <span className="source-row-text">
                  <strong>{source.title}</strong>
                  <small>
                    {source.source_type === "document"
                      ? `${source.page ? `Page ${source.page} · ` : ""}Your document`
                      : source.source_type === "mock"
                        ? "Synthetic demo source"
                        : "Web source"}
                  </small>
                </span>
                <Icon name="chevron" size={17} />
              </button>
            ))}
          </div>
        </section>
      )}

      {session.status === "completed" && run?.report_markdown && (
        <>
          <div className="report-layout">
            <article className="card report-card">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">Saved report</span>
                  <h2>Research findings</h2>
                </div>
                <a
                  className="button button-secondary button-small"
                  href={`/api/sessions/${session.id}/report`}
                >
                  <Icon name="download" size={15} /> Download
                </a>
              </div>
              <MarkdownReport
                markdown={run.report_markdown}
                sources={sources}
                onCitation={setSelectedSource}
              />
              {run.warnings.length > 0 && (
                <details className="report-warnings">
                  <summary>
                    Research limitations ({run.warnings.length})
                  </summary>
                  <ul>
                    {run.warnings.map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </details>
              )}
            </article>
            <aside className="report-sidebar">
              <div className="card report-sidebar-card">
                <h2>Research details</h2>
                <dl className="report-details">
                  <dt>Source type</dt>
                  <dd>
                    {session.mode === "documents"
                      ? "Selected documents"
                      : session.mode === "combined"
                        ? "Documents and web"
                        : "Web search"}
                  </dd>
                  <dt>AI mode</dt>
                  <dd>{runModeLabel(run, system)}</dd>
                  <dt>Time taken</dt>
                  <dd>
                    {run.metrics.elapsed_ms > 0
                      ? `${(run.metrics.elapsed_ms / 1000).toFixed(1)} seconds`
                      : "Not recorded"}
                  </dd>
                  <dt>Sources</dt>
                  <dd>{sources.length}</dd>
                </dl>
              </div>
              <div className="card report-sidebar-card">
                <h2>About this report</h2>
                <p>
                  Every citation opens the exact evidence passage saved with
                  this research. Evidence assessment is shown separately from
                  the report text.
                </p>
              </div>
            </aside>
          </div>
          <EvidenceReview
            sessionId={session.id}
            stage={run.stage}
            sources={sources}
            onCitation={setSelectedSource}
          />
        </>
      )}
      {session.status === "completed" && run && !run.report_markdown && (
        <p className="no-answer-note">
          <strong>Not enough evidence to answer.</strong> No report was saved
          because the collected evidence did not meet the research requirements.
        </p>
      )}
      {run &&
        !inProgress &&
        run.stage === "failed" &&
        session.status !== "failed" && (
          <p className="error-banner">
            This run did not produce a completed report. Refresh the saved
            session to check its final status.
          </p>
        )}
      <CitationDialog
        source={selectedSource}
        onClose={() => setSelectedSource(null)}
      />
    </div>
  );
}
