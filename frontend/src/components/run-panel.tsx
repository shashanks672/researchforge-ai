"use client";

import { VerificationPanel } from "./verification-panel";
import { useEffect, useRef, useState } from "react";
import {
  cancelRun,
  currentSession,
  executeRun,
  getRun,
  type ResearchRun,
} from "../lib/runs";
import type { ResearchSession } from "../lib/sessions";

const terminal = (run: ResearchRun | null) =>
  run !== null && ["completed", "failed", "cancelled"].includes(run.stage);

export function RunPanel({
  session,
  onSessionChange,
}: {
  session: ResearchSession;
  onSessionChange: (session: ResearchSession) => void;
}) {
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [mode, setMode] = useState<"disabled" | "mock" | "local" | "live">(
    "disabled",
  );
  const [provider, setProvider] = useState({
    model: null as string | null,
    search: "disabled",
    freeSearch: false,
  });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const callback = useRef(onSessionChange);
  const pollEnabled = run !== null && !terminal(run);
  useEffect(() => {
    callback.current = onSessionChange;
  }, [onSessionChange]);

  useEffect(() => {
    let active = true;
    void Promise.all([
      getRun(session.id),
      fetch("/api/system", {
        cache: "no-store",
        signal: AbortSignal.timeout(5000),
      }).then(async (response) => {
        if (!response.ok)
          throw new Error("Could not load research configuration.");
        const data = await response.json();
        if (
          !["disabled", "mock", "local", "live"].includes(data.execution_mode)
        )
          throw new Error("Invalid provider configuration.");
        if (typeof data.search_provider !== "string")
          throw new Error("Invalid search provider configuration.");
        return {
          mode: data.execution_mode as "disabled" | "mock" | "local" | "live",
          model: typeof data.model === "string" ? data.model : null,
          search: data.search_provider,
          freeSearch: data.free_search_enabled === true,
        };
      }),
    ])
      .then(([value, configured]) => {
        if (active) {
          setRun(value);
          setMode(configured.mode);
          setProvider({
            model: configured.model,
            search: configured.search,
            freeSearch: configured.freeSearch,
          });
        }
      })
      .catch(() => {
        if (active)
          setError(
            "Could not load research state. Refresh this session to retry.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [session.id]);

  useEffect(() => {
    if (!pollEnabled) return;
    let active = true;
    let inFlight = false;
    const started = Date.now();
    const interval = setInterval(() => {
      if (inFlight || !active) return;
      if (Date.now() - started > 240000) {
        clearInterval(interval);
        setError(
          "Automatic polling stopped. Refresh the session to check persisted state.",
        );
        return;
      }
      inFlight = true;
      void getRun(session.id)
        .then(async (value) => {
          if (!active) return;
          const saved = terminal(value)
            ? await currentSession(session.id)
            : null;
          if (active) {
            setRun(value);
            if (saved) callback.current(saved);
          }
        })
        .catch(() => {
          if (active)
            setError(
              "Progress could not be refreshed. The run may still be active; refresh before retrying.",
            );
        })
        .finally(() => {
          inFlight = false;
        });
    }, 1500);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [session.id, pollEnabled]);

  async function execute() {
    if (mode === "disabled") return;
    setBusy(true);
    setError("");
    try {
      setRun(await executeRun(session.id, mode));
      callback.current(await currentSession(session.id));
    } catch (failure) {
      setError(
        failure instanceof Error && failure.name === "Error"
          ? failure.message
          : "Could not confirm execution. Refresh before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    setError("");
    try {
      await cancelRun(session.id);
      setRun(await getRun(session.id));
      callback.current(await currentSession(session.id));
    } catch {
      setError(
        "Could not confirm cancellation. Refresh to inspect the saved status.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="run-panel" aria-labelledby="run-title">
      <div className="section-heading">
        <h3 id="run-title">Research execution</h3>
        {run && (
          <span className={`run-badge ${run.execution_mode}`}>
            {run.execution_mode === "mock"
              ? "MOCK WRITER · DEMO"
              : run.execution_mode === "local"
                ? `LOCAL MODEL · ${provider.model ?? "OLLAMA"}`
                : "LIVE PROVIDERS"}
          </span>
        )}
      </div>
      {loading && <p className="empty-copy">Loading research state…</p>}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {!loading && !run && (
        <>
          {mode === "disabled" && (
            <p className="empty-copy">
              Research is disabled. Configure mock providers for an offline
              demonstration, or obtain approval before configuring live
              providers.
            </p>
          )}
          {session.status === "pending" && mode !== "disabled" && (
            <>
              <p className="composer-help">
                {mode === "mock"
                  ? "This demonstration uses a mock writer, synthetic web fixtures and actual uploaded passages. It does not access the internet or establish factual truth."
                  : mode === "local"
                    ? `This run uses the local Ollama model ${provider.model ?? "(configured model)"}. Inference uses this Mac. Search: ${provider.search}${provider.search === "wikipedia" && provider.freeSearch ? " (one request per planned query to the public Wikipedia API)" : ""}.`
                    : "This run uses the approved hosted model and search provider and may incur configured provider costs."}
              </p>
              <button
                className="primary-button"
                disabled={busy}
                onClick={() => void execute()}
              >
                {busy
                  ? "Starting…"
                  : mode === "mock"
                    ? "Run mock demonstration"
                    : mode === "local"
                      ? "Run local research"
                      : "Run live research"}
              </button>
            </>
          )}
        </>
      )}
      {run && (
        <>
          {run.execution_mode === "mock" && (
            <p className="mock-notice">
              MOCK DEMONSTRATION: no live search or model calls. Web fixtures
              are synthetic; document passages are actual uploads. Mock outputs
              do not establish real-world findings.
            </p>
          )}
          {run.execution_mode === "local" && (
            <p className="local-model-notice">
              LOCAL INFERENCE: {provider.model ?? "Ollama model"} runs on this
              machine. Model quality and verification are not guarantees of
              correctness.
            </p>
          )}
          <p className="run-stage" role="status">
            Execution stage: {run.stage.replaceAll("_", " ")}
          </p>
          {!terminal(run) && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void cancel()}
            >
              Cancel run
            </button>
          )}
          {run.error_code && (
            <p className="error-message">
              Run failed: {run.error_code.replaceAll("_", " ")}. Partial
              evidence is retained; no completed report is available.
            </p>
          )}
          {run.plan && (
            <details open>
              <summary>Research plan</summary>
              <p>{run.plan.objective}</p>
              <p className="composer-help">{run.plan.scope}</p>
              <ol>
                {run.plan.subquestions.map((item, index) => (
                  <li key={index}>
                    <strong>{item.question}</strong>
                    <span className="query-text">
                      Search query: {item.search_query}
                      {run.investigated_queries.includes(item.search_query)
                        ? " · searched"
                        : " · not searched / unavailable"}
                    </span>
                  </li>
                ))}
              </ol>
            </details>
          )}
          {run.sources.length > 0 && (
            <details open>
              <summary>Collected sources · {run.sources.length}</summary>
              {run.sources.map((source) => (
                <article
                  className="source-card"
                  id={`source-${session.id}-${source.source_id}`}
                  key={source.source_id}
                >
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    [{source.source_id}] {source.title} ↗
                  </a>
                  <p>{source.excerpt}</p>
                  <span>
                    {source.source_type === "mock"
                      ? "Synthetic fixture"
                      : source.source_type === "document"
                        ? `Document · page ${source.page ?? "not available"} · chunk ${source.chunk_id}`
                        : "Web source"}{" "}
                    · Retrieved {new Date(source.retrieved_at).toLocaleString()}
                  </span>
                </article>
              ))}
            </details>
          )}
          {run.warnings.length > 0 && (
            <details>
              <summary>Evidence status and limitations</summary>
              <ul>
                {run.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </details>
          )}
          <VerificationPanel sessionId={session.id} stage={run.stage} />
          {run.report_markdown && run.stage === "completed" && (
            <details open>
              <summary>Research report</summary>
              <a
                className="text-button"
                href={`/api/sessions/${session.id}/report`}
                download
              >
                Export Markdown ↗
              </a>
              <pre className="report-viewer">{run.report_markdown}</pre>
            </details>
          )}
          <p className="run-metrics">
            {run.metrics.tool_calls} tool attempts ·{" "}
            {run.metrics.input_tokens + run.metrics.output_tokens} reported
            tokens · {(run.metrics.elapsed_ms / 1000).toFixed(1)}s ·{" "}
            {run.execution_mode === "mock" || run.execution_mode === "local"
              ? "Provider cost $0"
              : run.metrics.estimated_cost_usd === null
                ? "LLM cost unavailable; search cost separate"
                : `LLM estimate $${run.metrics.estimated_cost_usd.toFixed(4)}`}
            {run.execution_mode === "local" &&
              run.metrics.model_inference_ms > 0 &&
              ` · Model ${run.metrics.model_inference_ms}ms · ${run.metrics.model_tokens_per_second?.toFixed(1) ?? "?"} tokens/s`}
            {!run.metrics.usage_complete && " · Usage incomplete"}
          </p>
        </>
      )}
    </section>
  );
}
