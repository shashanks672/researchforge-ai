"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  fetchSessionPage,
  type SessionPage,
  type SessionStatus,
} from "../lib/sessions";
import { Icon } from "./icons";

const filters: { value: "all" | SessionStatus; label: string }[] = [
  { value: "all", label: "All research" },
  { value: "completed", label: "Completed" },
  { value: "running", label: "In progress" },
  { value: "pending", label: "Not started" },
  { value: "failed", label: "Could not finish" },
  { value: "cancelled", label: "Cancelled" },
];

export function HistoryScreen() {
  const [page, setPage] = useState<SessionPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | SessionStatus>("all");
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void fetchSessionPage(offset, controller.signal, 50)
      .then((result) => {
        if (!controller.signal.aborted) {
          setPage(result);
          setError("");
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted)
          setError(
            failure instanceof Error
              ? failure.message
              : "Could not load your History.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [offset, reload]);

  const visible = useMemo(
    () =>
      (page?.items ?? []).filter((item) => {
        const matchesQuery = item.question
          .toLocaleLowerCase()
          .includes(query.trim().toLocaleLowerCase());
        return matchesQuery && (status === "all" || item.status === status);
      }),
    [page, query, status],
  );

  return (
    <section aria-labelledby="history-title">
      <div className="page-header">
        <div>
          <span className="eyebrow">Saved questions and reports</span>
          <h1 className="page-title" id="history-title">
            Research history
          </h1>
          <p className="page-intro">
            Return to a report, continue a saved question, or check on work that
            did not finish.
          </p>
        </div>
        <Link className="button button-primary" href="/">
          <Icon name="plus" size={17} /> New research
        </Link>
      </div>

      <div className="history-tools">
        <label className="search-field">
          <Icon name="search" size={17} />
          <span className="visually-hidden">
            Search this page of research history
          </span>
          <input
            className="search-input"
            type="search"
            placeholder="Search questions on this page"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="visually-hidden" htmlFor="history-status">
          Filter by status
        </label>
        <select
          className="history-filter"
          id="history-status"
          value={status}
          onChange={(event) =>
            setStatus(event.target.value as "all" | SessionStatus)
          }
        >
          {filters.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <button
          className="button button-secondary button-small"
          type="button"
          onClick={() => setReload((value) => value + 1)}
          disabled={loading}
        >
          <Icon name="history" size={15} /> Refresh
        </button>
      </div>

      {error && (
        <p className="error-banner" role="alert">
          {error} Your saved research remains in the local database.{" "}
          <button
            className="inline-button"
            type="button"
            onClick={() => setReload((value) => value + 1)}
          >
            Try again
          </button>
        </p>
      )}
      {loading && (
        <div
          className="card history-skeleton"
          aria-busy="true"
          aria-label="Loading research history"
        >
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line" />
        </div>
      )}
      {!loading && !error && page?.total === 0 && (
        <div className="card empty-state">
          <div className="empty-icon">
            <Icon name="history" />
          </div>
          <h2>Your research will appear here</h2>
          <p>
            When you start with a question, your saved session and report will
            be easy to find.
          </p>
          <Link className="button button-primary" href="/">
            Start your first research <Icon name="arrow" size={16} />
          </Link>
        </div>
      )}
      {!loading && !error && page && page.total > 0 && visible.length === 0 && (
        <div className="card empty-state">
          <div className="empty-icon">
            <Icon name="search" />
          </div>
          <h2>No matching research</h2>
          <p>Try another phrase or choose a different status.</p>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => {
              setQuery("");
              setStatus("all");
            }}
          >
            Clear filters
          </button>
        </div>
      )}
      {!loading && !error && visible.length > 0 && (
        <div className="card history-list" aria-label="Saved research sessions">
          {visible.map((item) => (
            <Link
              className="history-row"
              href={`/research/${item.id}`}
              key={item.id}
            >
              <span className="history-question">{item.question}</span>
              <span className="history-date">
                <Icon name="clock" size={14} />{" "}
                {new Date(item.updated_at).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </span>
              <span className="history-mode">
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
              <Icon className="history-row-arrow" name="arrow" size={17} />
            </Link>
          ))}
        </div>
      )}
      {!loading && !error && page && page.total > page.limit && (
        <div className="pagination">
          <span>
            Showing {page.offset + 1}–
            {Math.min(page.offset + page.items.length, page.total)} of{" "}
            {page.total} sessions
          </span>
          <div className="pagination-actions">
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={loading || page.offset === 0}
              onClick={() => setOffset(Math.max(0, offset - page.limit))}
            >
              Previous
            </button>
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={loading || !page.has_more}
              onClick={() => setOffset(offset + page.limit)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
