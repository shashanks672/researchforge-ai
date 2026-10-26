import { UUID_PATTERN } from "./sessions";
export interface VerificationArtifacts {
  execution_mode: "mock" | "local" | "live";
  method: string;
  iteration: number;
  claims: {
    claim_id: string;
    text: string;
    location: string;
    source_ids: string[];
    checkable: boolean;
    important: boolean;
    eligibility:
      | "VERIFIABLE_CLAIM"
      | "INCOMPLETE_FRAGMENT"
      | "NON_FACTUAL_STATEMENT"
      | "QUESTION_OR_INSTRUCTION"
      | "INSUFFICIENT_CONTEXT";
    eligibility_reason: string;
    reconstructed_claim: string | null;
  }[];
  verdicts: {
    claim_id: string;
    status:
      "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT_EVIDENCE" | "NOT_EVALUATED";
    matches: { source_id: string; quote: string; role: string }[];
    explanation: string;
    method: string;
    evaluated_at: string;
  }[];
  contradictions: {
    first_source_id: string;
    second_source_id: string;
    first_statement: string;
    second_statement: string;
    reason: string;
    context_caveat: string;
    first_observed_at: string;
    second_observed_at: string;
    first_published_at: string | null;
    second_published_at: string | null;
  }[];
  activities: string[];
  evidence_sufficiency?: {
    question_id: string;
    question_text: string;
    sufficient: boolean;
    status: "SUFFICIENT" | "PARTIAL" | "INSUFFICIENT" | "CONFLICTING";
    supporting_evidence_ids: string[];
    missing_information: string[];
    explanation: string;
    evaluator_version: string;
    evaluated_at: string;
    fact_assessments?: {
      fact: string;
      entity: string;
      property: string;
      value: string;
      unit: string;
      time_period: string;
      scope: string;
      negation: string;
      status: "SUPPORTED" | "MISSING" | "CONFLICTING";
      evidence: { source_id: string; quote: string }[];
    }[];
  }[];
}
export interface StoredVerification {
  id: string;
  session_id: string;
  status: "running" | "completed" | "failed";
  error_code: string | null;
  artifacts: VerificationArtifacts | null;
  original_markdown: string | null;
  history: VerificationArtifacts[];
}
export function parseVerification(value: unknown): StoredVerification {
  if (!value || typeof value !== "object")
    throw new Error("Invalid verification response");
  const v = value as StoredVerification;
  if (
    !UUID_PATTERN.test(v.id) ||
    !UUID_PATTERN.test(v.session_id) ||
    !["running", "completed", "failed"].includes(v.status) ||
    !Array.isArray(v.history) ||
    (v.original_markdown !== null && typeof v.original_markdown !== "string")
  )
    throw new Error("Invalid verification response");
  if (v.artifacts) {
    const a = v.artifacts;
    if (
      !["mock", "local", "live"].includes(a.execution_mode) ||
      typeof a.method !== "string" ||
      !Array.isArray(a.claims) ||
      !Array.isArray(a.verdicts) ||
      !Array.isArray(a.contradictions) ||
      !Array.isArray(a.activities) ||
      (a.evidence_sufficiency !== undefined &&
        !Array.isArray(a.evidence_sufficiency))
    )
      throw new Error("Invalid verification artifacts");
    for (const verdict of a.verdicts)
      if (
        ![
          "SUPPORTED",
          "CONTRADICTED",
          "INSUFFICIENT_EVIDENCE",
          "NOT_EVALUATED",
        ].includes(verdict.status) ||
        !Array.isArray(verdict.matches)
      )
        throw new Error("Invalid verdict");
  }
  return {
    id: v.id,
    session_id: v.session_id,
    status: v.status,
    error_code: v.error_code,
    artifacts: v.artifacts,
    original_markdown: v.original_markdown,
    history: v.history,
  };
}
