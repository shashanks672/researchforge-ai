"use client";

import { useEffect, useMemo, useState } from "react";
import {
  parseVerification,
  type VerificationArtifacts,
  type StoredVerification,
} from "../lib/verification";
import type { ResearchSource } from "./citation-dialog";
import { Icon } from "./icons";

type ClaimState = NonNullable<
  VerificationArtifacts["verdicts"]
>[number]["status"];
const claimStates: ClaimState[] = [
  "SUPPORTED",
  "CONTRADICTED",
  "INSUFFICIENT_EVIDENCE",
  "NOT_EVALUATED",
];

function friendlyClaimStatus(status: ClaimState) {
  if (status === "SUPPORTED") return "Supported by cited evidence";
  if (status === "CONTRADICTED") return "Conflicts with evidence";
  if (status === "INSUFFICIENT_EVIDENCE") return "Not enough evidence";
  return "Not evaluated";
}

function friendlyFactStatus(status: string) {
  if (status === "SUPPORTED") return "Evidence found";
  if (status === "CONFLICTING") return "Sources disagree";
  return "Not found";
}

export function EvidenceReview({
  sessionId,
  stage,
  sources,
  onCitation,
}: {
  sessionId: string;
  stage: string;
  sources: ResearchSource[];
  onCitation: (source: ResearchSource) => void;
}) {
  const [record, setRecord] = useState<StoredVerification | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"ALL" | ClaimState>("ALL");

  useEffect(() => {
    const controller = new AbortController();
    void fetch(`/api/sessions/${sessionId}/verification`, {
      cache: "no-store",
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(12000)]),
    })
      .then(async (response) => {
        if (response.status === 404) return null;
        if (!response.ok)
          throw new Error("Saved evidence review could not be loaded.");
        return parseVerification(await response.json());
      })
      .then((value) => {
        if (!controller.signal.aborted) {
          setRecord(value);
          setError("");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "Evidence review could not be loaded. Refresh this report to try again.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [sessionId, stage]);

  const artifacts = record?.artifacts;
  const visibleClaims = useMemo(
    () =>
      (artifacts?.claims ?? []).filter((claim) => {
        const status =
          artifacts?.verdicts.find(
            (verdict) => verdict.claim_id === claim.claim_id,
          )?.status ?? "NOT_EVALUATED";
        return filter === "ALL" || status === filter;
      }),
    [artifacts, filter],
  );
  const counts = useMemo(() => {
    const result: Record<string, number> = {
      ALL: artifacts?.claims.length ?? 0,
    };
    for (const claim of artifacts?.claims ?? []) {
      const status =
        artifacts?.verdicts.find((item) => item.claim_id === claim.claim_id)
          ?.status ?? "NOT_EVALUATED";
      result[status] = (result[status] ?? 0) + 1;
    }
    return result;
  }, [artifacts]);
  const sufficiency = artifacts?.evidence_sufficiency ?? [];
  const noAnswer =
    sufficiency.length > 0 &&
    sufficiency.every((item) => item.status === "INSUFFICIENT");
  const partialAnswer = sufficiency.some(
    (item) => item.status === "PARTIAL" || item.status === "CONFLICTING",
  );
  const localOrMock =
    artifacts?.execution_mode === "local" ||
    artifacts?.execution_mode === "mock";

  return (
    <section className="card evidence-summary" aria-labelledby="evidence-title">
      <div className="section-heading">
        <h2 id="evidence-title">Evidence review</h2>
        {record?.status === "completed" && (
          <span className="status-pill status-completed">Reviewed</span>
        )}
        {record?.status === "failed" && (
          <span className="status-pill status-failed">Incomplete</span>
        )}
      </div>
      {loading && (
        <div
          className="skeleton skeleton-line"
          aria-label="Loading evidence review"
        />
      )}
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {!loading && !error && !record && (
        <p className="evidence-explanation">
          This saved report has no stored evidence assessment.
        </p>
      )}
      {record?.status === "failed" && (
        <>
          <p className="evidence-explanation">
            The required evidence review did not finish. This report is not
            marked as verified.
          </p>
          <details className="error-details">
            <summary>Technical details</summary>
            <div className="error-code">
              {record.error_code ?? "verification_failed"}
            </div>
          </details>
        </>
      )}
      {artifacts && (
        <>
          {noAnswer ? (
            <div className="no-answer-note">
              <span className="no-answer-icon">
                <Icon name="search" size={17} />
              </span>
              <div>
                <strong>Not enough evidence to answer</strong>
                <p>
                  The selected sources were checked, but they do not support a
                  factual answer to every requested detail.
                </p>
              </div>
            </div>
          ) : partialAnswer ? (
            <p className="info-banner">
              Some details are missing or the selected sources disagree. Review
              the evidence before relying on those findings.
            </p>
          ) : null}
          <div className="evidence-counts">
            {claimStates.map((status) => (
              <div className="evidence-count" key={status}>
                <strong>{counts[status] ?? 0}</strong>
                <span>
                  {status === "SUPPORTED"
                    ? "Supported"
                    : status === "CONTRADICTED"
                      ? "Conflicting"
                      : status === "INSUFFICIENT_EVIDENCE"
                        ? "Need evidence"
                        : "Not evaluated"}
                </span>
              </div>
            ))}
          </div>
          <p className="evidence-explanation">
            “Supported” means this procedure found support in the cited
            passages. It does not guarantee that a source is factually correct.
            {localOrMock && (
              <span>
                {" "}
                {artifacts.execution_mode === "mock"
                  ? "This was a deterministic demonstration assessment."
                  : "This assessment was produced by a local model."}
              </span>
            )}
          </p>
          {noAnswer && artifacts.claims.length === 0 && (
            <p className="evidence-explanation">
              No factual claims were produced, so claim verification was not
              needed.
            </p>
          )}

          {sufficiency.length > 0 && (
            <details className="evidence-review">
              <summary>
                <span>What the sources could answer</span>
                <span className="section-kicker">
                  {sufficiency.length} question
                  {sufficiency.length === 1 ? "" : "s"}
                </span>
              </summary>
              {sufficiency.map((item) => (
                <article className="sufficiency-item" key={item.question_id}>
                  <div className="sufficiency-heading">
                    <span
                      className={`status-pill status-${item.status.toLocaleLowerCase()}`}
                    >
                      {item.status === "SUFFICIENT"
                        ? "Evidence found"
                        : item.status === "CONFLICTING"
                          ? "Sources disagree"
                          : item.status === "PARTIAL"
                            ? "Partly answered"
                            : "Not found"}
                    </span>
                  </div>
                  <p>{item.question_text}</p>
                  {item.missing_information.length > 0 && (
                    <p className="small-copy">
                      <strong>Still missing:</strong>{" "}
                      {item.missing_information.join("; ")}
                    </p>
                  )}
                  {item.supporting_evidence_ids.length > 0 && (
                    <p className="small-copy">
                      Relevant passages:{" "}
                      {item.supporting_evidence_ids.map((id) => (
                        <button
                          className="inline-button"
                          type="button"
                          key={id}
                          onClick={() => {
                            const source = sources.find(
                              (item) => item.source_id === id,
                            );
                            if (source) onCitation(source);
                          }}
                        >
                          {id}
                        </button>
                      ))}
                    </p>
                  )}
                  <details className="fact-details">
                    <summary>
                      See how each requested detail was assessed
                    </summary>
                    {(item.fact_assessments ?? []).map((fact, factIndex) => (
                      <div
                        className="fact-row"
                        key={`${item.question_id}-${factIndex}`}
                      >
                        <span
                          className={`status-pill status-${fact.status.toLocaleLowerCase()}`}
                        >
                          {friendlyFactStatus(fact.status)}
                        </span>
                        <p>{fact.fact}</p>
                        {fact.evidence.map((quote, quoteIndex) => (
                          <blockquote key={`${quote.source_id}-${quoteIndex}`}>
                            <button
                              className="inline-button"
                              type="button"
                              onClick={() => {
                                const source = sources.find(
                                  (sourceItem) =>
                                    sourceItem.source_id === quote.source_id,
                                );
                                if (source) onCitation(source);
                              }}
                            >
                              {quote.source_id}
                            </button>{" "}
                            “{quote.quote}”
                          </blockquote>
                        ))}
                      </div>
                    ))}
                    <p className="small-copy">{item.explanation}</p>
                  </details>
                </article>
              ))}
            </details>
          )}

          {artifacts.claims.length > 0 && (
            <details className="evidence-review">
              <summary>
                <span>Claim review</span>
                <span className="section-kicker">
                  {artifacts.claims.length} claim
                  {artifacts.claims.length === 1 ? "" : "s"}
                </span>
              </summary>
              <label className="visually-hidden" htmlFor="claim-filter">
                Filter claims by result
              </label>
              <select
                className="claim-filter"
                id="claim-filter"
                value={filter}
                onChange={(event) =>
                  setFilter(event.target.value as "ALL" | ClaimState)
                }
              >
                <option value="ALL">All claims ({counts.ALL ?? 0})</option>
                {claimStates.map((status) => (
                  <option key={status} value={status}>
                    {friendlyClaimStatus(status)} ({counts[status] ?? 0})
                  </option>
                ))}
              </select>
              <div className="claim-list">
                {visibleClaims.map((claim) => {
                  const verdict = artifacts.verdicts.find(
                    (item) => item.claim_id === claim.claim_id,
                  );
                  return (
                    <details className="claim-item" key={claim.claim_id}>
                      <summary>
                        <span
                          className={`status-pill status-${(verdict?.status ?? "NOT_EVALUATED").toLocaleLowerCase()}`}
                        >
                          {friendlyClaimStatus(
                            verdict?.status ?? "NOT_EVALUATED",
                          )}
                        </span>
                        <span>{claim.text}</span>
                      </summary>
                      <p>
                        {verdict?.explanation ??
                          "No completed assessment is available for this claim."}
                      </p>
                      {claim.eligibility_reason && (
                        <p className="small-copy">
                          Assessment note: {claim.eligibility_reason}
                        </p>
                      )}
                      {verdict?.matches.map((match, matchIndex) => (
                        <blockquote key={`${match.source_id}-${matchIndex}`}>
                          <button
                            className="inline-button"
                            type="button"
                            onClick={() => {
                              const source = sources.find(
                                (sourceItem) =>
                                  sourceItem.source_id === match.source_id,
                              );
                              if (source) onCitation(source);
                            }}
                          >
                            {match.source_id}
                          </button>{" "}
                          · {match.role}
                          <br />“{match.quote}”
                        </blockquote>
                      ))}
                    </details>
                  );
                })}
                {visibleClaims.length === 0 && (
                  <p className="small-copy">No claims match this filter.</p>
                )}
              </div>
            </details>
          )}

          {artifacts.contradictions.length > 0 && (
            <details className="evidence-review">
              <summary>
                <span>Sources that may disagree</span>
                <span className="section-kicker">
                  {artifacts.contradictions.length}
                </span>
              </summary>
              {artifacts.contradictions.map((item, index) => (
                <article
                  className="conflict-item"
                  key={`${item.first_source_id}-${item.second_source_id}-${index}`}
                >
                  <blockquote>
                    <button
                      className="inline-button"
                      type="button"
                      onClick={() => {
                        const source = sources.find(
                          (value) => value.source_id === item.first_source_id,
                        );
                        if (source) onCitation(source);
                      }}
                    >
                      {item.first_source_id}
                    </button>{" "}
                    “{item.first_statement}”
                  </blockquote>
                  <blockquote>
                    <button
                      className="inline-button"
                      type="button"
                      onClick={() => {
                        const source = sources.find(
                          (value) => value.source_id === item.second_source_id,
                        );
                        if (source) onCitation(source);
                      }}
                    >
                      {item.second_source_id}
                    </button>{" "}
                    “{item.second_statement}”
                  </blockquote>
                  <p>
                    {item.reason} {item.context_caveat}
                  </p>
                </article>
              ))}
            </details>
          )}

          {artifacts.activities.length > 0 && (
            <details className="advanced-details">
              <summary>Research notes</summary>
              <ul>
                {artifacts.activities.map((activity, index) => (
                  <li key={index}>{activity}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}
