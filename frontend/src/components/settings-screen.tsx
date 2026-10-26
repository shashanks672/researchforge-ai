"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { SystemStatus } from "../lib/system";
import { Icon } from "./icons";

function aiName(status: SystemStatus) {
  if (status.execution_mode === "local")
    return status.model ?? "Ollama local model";
  if (status.execution_mode === "mock") return "Deterministic demo mode";
  if (status.execution_mode === "live")
    return status.model ?? "Approved hosted model";
  return "Not configured";
}

function searchName(status: SystemStatus) {
  if (status.search_provider === "disabled") return "Off in this setup";
  if (status.search_provider === "wikipedia")
    return status.free_search_enabled ? "Public Wikipedia search" : "Off";
  if (status.search_provider === "mock")
    return "Synthetic demonstration sources";
  if (status.search_provider === "brave") return "Approved hosted search";
  return "Not configured";
}

export function SettingsScreen() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/system", {
      cache: "no-store",
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error("Could not connect to the local application.");
        return response.json() as Promise<SystemStatus>;
      })
      .then((value) => {
        if (!controller.signal.aborted) {
          setStatus(value);
          setError("");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "The application status could not be loaded. Start the local API, then try again.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [refresh]);

  return (
    <section aria-labelledby="settings-title">
      <div className="page-header">
        <div>
          <span className="eyebrow">A little context about this workspace</span>
          <h1 className="page-title" id="settings-title">
            Settings
          </h1>
          <p className="page-intro">
            Your research setup is managed on this Mac. These details are
            read-only so model keys and server settings stay private.
          </p>
        </div>
        <button
          className="button button-secondary"
          type="button"
          disabled={loading}
          onClick={() => {
            setLoading(true);
            setRefresh((value) => value + 1);
          }}
        >
          <Icon name="history" size={15} /> Refresh status
        </button>
      </div>
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {loading && (
        <div className="card settings-card" aria-busy="true">
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line" />
        </div>
      )}
      {!loading && status && (
        <div className="settings-grid">
          <section
            className="card settings-card"
            aria-labelledby="setup-heading"
          >
            <h2 id="setup-heading">Your research setup</h2>
            <dl>
              <div className="setting-row">
                <dt>AI provider</dt>
                <dd>
                  {status.execution_mode === "local"
                    ? "Local AI"
                    : status.execution_mode === "mock"
                      ? "Demo mode"
                      : status.execution_mode === "live"
                        ? "Hosted AI"
                        : "Unavailable"}
                </dd>
              </div>
              <div className="setting-row">
                <dt>Model</dt>
                <dd>{aiName(status)}</dd>
              </div>
              <div className="setting-row">
                <dt>Document research</dt>
                <dd>
                  {status.uploads_enabled && status.research_enabled
                    ? "Available"
                    : "Unavailable"}
                </dd>
              </div>
              <div className="setting-row">
                <dt>Web research</dt>
                <dd>{searchName(status)}</dd>
              </div>
              <div className="setting-row">
                <dt>Application connection</dt>
                <dd>
                  {status.status === "ok"
                    ? "Connected on this Mac"
                    : "Unavailable"}
                </dd>
              </div>
            </dl>
            <p className="small-copy">
              A configured local model can take time to answer. This status
              confirms the application configuration; it does not guarantee the
              Ollama service is currently ready to run a request.
            </p>
            <details className="advanced-details">
              <summary>Advanced technical details</summary>
              <dl>
                <div className="setting-row">
                  <dt>Execution mode</dt>
                  <dd>{status.execution_mode}</dd>
                </div>
                <div className="setting-row">
                  <dt>Provider</dt>
                  <dd>{status.llm_provider}</dd>
                </div>
                <div className="setting-row">
                  <dt>Search provider</dt>
                  <dd>{status.search_provider}</dd>
                </div>
                <div className="setting-row">
                  <dt>Application version</dt>
                  <dd>{status.version}</dd>
                </div>
                <div className="setting-row">
                  <dt>Research enabled</dt>
                  <dd>{status.research_enabled ? "Yes" : "No"}</dd>
                </div>
              </dl>
            </details>
          </section>
          <aside className="card settings-card privacy-card">
            <div className="empty-icon">
              <Icon name="check" />
            </div>
            <h2>Designed for a local workspace</h2>
            <p className="small-copy">
              Your files and saved research are handled by services configured
              on this Mac. When Local AI is selected, model inference runs
              through the local Ollama service.
            </p>
            <ul className="privacy-list">
              <li>
                <Icon name="check" size={15} /> Documents are selected
                explicitly for each question.
              </li>
              <li>
                <Icon name="check" size={15} /> Search is only offered when the
                configured provider is available.
              </li>
              <li>
                <Icon name="check" size={15} /> Demo output is labeled and
                separated from local-model research.
              </li>
            </ul>
            {status.execution_mode === "mock" && (
              <p className="info-banner settings-notice">
                Demo mode uses deterministic sample output. It does not call a
                real language model.
              </p>
            )}
            {status.execution_mode === "live" && (
              <p className="info-banner settings-notice">
                Hosted services are enabled on this server and may incur
                provider costs.
              </p>
            )}
            {status.search_provider === "disabled" && (
              <p className="info-banner settings-notice">
                Public search is off. The no-key option searches English
                Wikipedia only, not the whole web. A local operator must
                explicitly enable it and provide a real public contact URL or
                email; no contact is guessed. Selected-document research stays
                available.
              </p>
            )}
            {status.search_provider === "wikipedia" && (
              <p className="info-banner settings-notice">
                Search uses the English Wikipedia API and retrieves the linked
                public article through the guarded fetcher. This is an
                encyclopedia index, not general web search. Reuse article text
                with attribution and follow its applicable license. Planned
                search terms are sent to Wikimedia, so avoid confidential
                questions when using Web or Documents + web.
              </p>
            )}
            <Link className="text-link" href="/library">
              Manage your documents <span aria-hidden="true">→</span>
            </Link>
          </aside>
        </div>
      )}
    </section>
  );
}
