"use client";
import { useEffect, useMemo, useState } from "react";
import {
  parseVerification,
  type StoredVerification,
} from "../lib/verification";
export function VerificationPanel({
  sessionId,
  stage,
}: {
  sessionId: string;
  stage: string;
}) {
  const [data, setData] = useState<StoredVerification | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [claimFilter, setClaimFilter] = useState("ALL");
  useEffect(() => {
    let active = true;
    void fetch(`/api/sessions/${sessionId}/verification`, {
      cache: "no-store",
      signal: AbortSignal.timeout(12000),
    })
      .then(async (response) => {
        if (response.status === 404) return null;
        if (!response.ok) throw new Error("Could not load stored verification");
        return parseVerification(await response.json());
      })
      .then((value) => {
        if (active) {
          setData(value);
          setError("");
        }
      })
      .catch(() => {
        if (active)
          setError(
            "Stored verification could not be loaded. Refresh the session; no success is assumed.",
          );
      })
      .finally(() => {
        if (active) setLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [sessionId, stage]);
  const artifacts = data?.artifacts;
  const evidenceLink = (sid: string) => `#source-${sessionId}-${sid}`;
  const claimCounts = useMemo(() => {
    const counts: Record<string, number> = {
      ALL: artifacts?.claims.length ?? 0,
    };
    for (const claim of artifacts?.claims ?? []) {
      const status =
        artifacts?.verdicts.find(
          (verdict) => verdict.claim_id === claim.claim_id,
        )?.status ?? "NOT_EVALUATED";
      counts[status] = (counts[status] ?? 0) + 1;
    }
    return counts;
  }, [artifacts]);
  return (
    <section
      className="verification-panel"
      aria-label="Evidence support assessment"
    >
      <h4>Evidence support assessment</h4>
      {!loaded && <p>Loading stored assessment…</p>}
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      {loaded && !error && !data && (
        <p>
          No stored assessment. Older reports were not retroactively verified.
        </p>
      )}
      {data && (
        <>
          <p className="run-stage">Assessment procedure: {data.status}</p>
          {data.status === "failed" && (
            <p className="error-message">
              Mandatory assessment failed: {data.error_code}. Partial outputs
              are not a completed verification.
            </p>
          )}
          {artifacts ? (
            <>
              <p
                className={
                  artifacts.execution_mode === "mock"
                    ? "mock-notice"
                    : "composer-help"
                }
              >
                {artifacts.execution_mode === "mock"
                  ? "MOCK ASSESSMENTS — deterministic test/demo outputs; no evaluated real-world verification quality."
                  : artifacts.execution_mode === "local"
                    ? "LOCAL MODEL ASSESSMENTS — generated on this machine; no absolute truth guarantee."
                    : "Hosted-model assessments of collected evidence; no absolute truth guarantee."}
              </p>
              <p className="composer-help">
                {artifacts.method} · Follow-up iterations: {artifacts.iteration}
                . SUPPORTED means this procedure found support in collected
                passages. Ambiguous or conflicting evidence remains
                insufficient.
              </p>
              {(artifacts.evidence_sufficiency ?? []).length > 0 && (
                <details open>
                  <summary>
                    Answerability status ·{" "}
                    {artifacts.evidence_sufficiency?.length}
                  </summary>
                  <ul>
                    {artifacts.evidence_sufficiency?.map((item) => (
                      <li key={item.question_id}>
                        <strong>
                          {item.question_id} · {item.status}
                        </strong>
                        <p>{item.question_text}</p>
                        {item.supporting_evidence_ids.length > 0 && (
                          <p>
                            Evidence:{" "}
                            {item.supporting_evidence_ids.map((id) => (
                              <a key={id} href={evidenceLink(id)}>
                                [{id}]
                              </a>
                            ))}
                          </p>
                        )}
                        {item.missing_information.length > 0 && (
                          <p>Missing: {item.missing_information.join("; ")}</p>
                        )}
                        {item.fact_assessments?.map((fact, index) => (
                          <div key={`${item.question_id}-fact-${index}`}>
                            <p>
                              <strong>{fact.status}</strong> · {fact.fact}
                              {fact.entity && ` · Entity: ${fact.entity}`}
                              {fact.property && ` · Property: ${fact.property}`}
                              {fact.value && ` · Value: ${fact.value}`}
                              {fact.unit && ` · Unit: ${fact.unit}`}
                              {fact.time_period &&
                                ` · Period: ${fact.time_period}`}
                              {fact.scope && ` · Scope: ${fact.scope}`}
                              {fact.negation && ` · Negation: ${fact.negation}`}
                            </p>
                            {fact.evidence.map((match, quoteIndex) => (
                              <blockquote
                                key={`${match.source_id}-${quoteIndex}`}
                              >
                                <a href={evidenceLink(match.source_id)}>
                                  [{match.source_id}]
                                </a>{" "}
                                “{match.quote}”
                              </blockquote>
                            ))}
                          </div>
                        ))}
                        <p className="composer-help">{item.explanation}</p>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <details>
                <summary>
                  Claims · {artifacts.claims.length} (supported{" "}
                  {claimCounts.SUPPORTED ?? 0}, contradicted{" "}
                  {claimCounts.CONTRADICTED ?? 0}, insufficient{" "}
                  {claimCounts.INSUFFICIENT_EVIDENCE ?? 0}, not evaluated{" "}
                  {claimCounts.NOT_EVALUATED ?? 0})
                </summary>
                <label className="composer-help claim-filter">
                  Filter claims
                  <select
                    aria-label="Filter claims by verdict"
                    value={claimFilter}
                    onChange={(event) => setClaimFilter(event.target.value)}
                  >
                    <option value="ALL">All claims ({claimCounts.ALL})</option>
                    {[
                      "SUPPORTED",
                      "CONTRADICTED",
                      "INSUFFICIENT_EVIDENCE",
                      "NOT_EVALUATED",
                    ].map((status) => (
                      <option key={status} value={status}>
                        {status} ({claimCounts[status] ?? 0})
                      </option>
                    ))}
                  </select>
                </label>
                {artifacts.claims
                  .filter(
                    (claim) =>
                      claimFilter === "ALL" ||
                      (artifacts.verdicts.find(
                        (verdict) => verdict.claim_id === claim.claim_id,
                      )?.status ?? "NOT_EVALUATED") === claimFilter,
                  )
                  .map((c) => {
                    const verdict = artifacts.verdicts.find(
                      (v) => v.claim_id === c.claim_id,
                    );
                    return (
                      <details className="source-card" key={c.claim_id}>
                        <summary>
                          {c.claim_id} · {verdict?.status ?? "NOT_EVALUATED"} ·{" "}
                          {c.eligibility.replaceAll("_", " ")} — {c.text}
                        </summary>
                        <p>{c.eligibility_reason}</p>
                        {c.reconstructed_claim && (
                          <p>
                            Contextual reconstruction: {c.reconstructed_claim}
                          </p>
                        )}
                        <p className="composer-help">
                          Report location: {c.location}
                        </p>
                        <p>{verdict?.explanation}</p>
                        {verdict?.matches.map((m, i) => (
                          <blockquote key={i}>
                            <a href={evidenceLink(m.source_id)}>
                              [{m.source_id}] {m.role}
                            </a>
                            <p>{m.quote}</p>
                          </blockquote>
                        ))}
                        {verdict && (
                          <span>
                            {new Date(verdict.evaluated_at).toLocaleString()}
                          </span>
                        )}
                      </details>
                    );
                  })}
              </details>
              <details open>
                <summary>
                  Possible contradictions · {artifacts.contradictions.length}
                </summary>
                {!artifacts.contradictions.length && (
                  <p>
                    No conflicts identified by this procedure; absence is not
                    proof of consistency.
                  </p>
                )}
                {artifacts.contradictions.map((c, i) => (
                  <article className="source-card" key={i}>
                    <p>
                      <a href={evidenceLink(c.first_source_id)}>
                        [{c.first_source_id}]
                      </a>{" "}
                      {c.first_statement}
                    </p>
                    <p>
                      <a href={evidenceLink(c.second_source_id)}>
                        [{c.second_source_id}]
                      </a>{" "}
                      {c.second_statement}
                    </p>
                    <p>{c.reason}</p>
                    <p>{c.context_caveat}</p>
                    <span>
                      Observed {new Date(c.first_observed_at).toLocaleString()}{" "}
                      / {new Date(c.second_observed_at).toLocaleString()};
                      publication dates {c.first_published_at ?? "unknown"} /{" "}
                      {c.second_published_at ?? "unknown"}
                    </span>
                  </article>
                ))}
              </details>
              <details>
                <summary>Follow-up research activity</summary>
                {artifacts.activities.length ? (
                  <ul>
                    {artifacts.activities.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No targeted follow-up performed.</p>
                )}
              </details>
            </>
          ) : (
            <p>Mandatory claim extraction and evidence matching are pending.</p>
          )}
          {data.original_markdown && (
            <details>
              <summary>Original unassessed draft</summary>
              <pre className="report-viewer">{data.original_markdown}</pre>
            </details>
          )}
          {data.history.length > 1 && (
            <details>
              <summary>
                Assessment history · {data.history.length} passes
              </summary>
              {data.history.map((h, i) => (
                <p key={i}>
                  Pass {i + 1}:{" "}
                  {h.verdicts
                    .map((v) => `${v.claim_id} ${v.status}`)
                    .join(" · ")}
                </p>
              ))}
            </details>
          )}
        </>
      )}
    </section>
  );
}
