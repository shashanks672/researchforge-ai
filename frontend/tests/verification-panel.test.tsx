import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { VerificationPanel } from "../src/components/verification-panel";

const sessionId = "9f26c7d0-21f5-4cf6-9536-8a9112adb3ce";
const fixture = {
  id: sessionId,
  session_id: sessionId,
  status: "completed",
  error_code: null,
  original_markdown: null,
  history: [],
  artifacts: {
    execution_mode: "mock",
    method: "mock-literal-relations-v1",
    iteration: 0,
    claims: [
      {
        claim_id: "C1",
        text: "Copyright law regulates protected works.",
        location: "findings:0",
        source_ids: ["S1"],
        checkable: true,
        important: true,
        eligibility: "VERIFIABLE_CLAIM",
        eligibility_reason: "Complete proposition.",
        reconstructed_claim: null,
      },
      {
        claim_id: "C2",
        text: "In addition, it has",
        location: "findings:1",
        source_ids: ["S1"],
        checkable: false,
        important: true,
        eligibility: "INCOMPLETE_FRAGMENT",
        eligibility_reason: "Proposition is incomplete.",
        reconstructed_claim: null,
      },
    ],
    verdicts: [
      {
        claim_id: "C1",
        status: "SUPPORTED",
        matches: [],
        explanation: "A fixture match.",
        method: "mock-literal-relations-v1",
        evaluated_at: "2026-10-19T00:00:00Z",
      },
      {
        claim_id: "C2",
        status: "NOT_EVALUATED",
        matches: [],
        explanation: "Incomplete claim.",
        method: "claim-eligibility-v1",
        evaluated_at: "2026-10-19T00:00:00Z",
      },
    ],
    contradictions: [],
    activities: [],
    evidence_sufficiency: [
      {
        question_id: "Q1",
        question_text: "What is the system's warranty?",
        sufficient: false,
        status: "INSUFFICIENT",
        supporting_evidence_ids: [],
        missing_information: ["warranty duration"],
        explanation: "The retrieved passage does not state a warranty.",
        evaluator_version: "evidence-sufficiency-v1",
        evaluated_at: "2026-10-19T00:00:00Z",
      },
    ],
  },
};

test("verification claims collapse by default and can be filtered by verdict", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify(fixture))),
  );
  render(<VerificationPanel sessionId={sessionId} stage="completed" />);
  expect(await screen.findByText(/MOCK ASSESSMENTS/)).toBeInTheDocument();
  expect(screen.getByText(/Answerability status · 1/)).toBeInTheDocument();
  expect(screen.getByText(/warranty duration/)).toBeInTheDocument();
  expect(screen.getByText(/Claims · 2/)).toBeInTheDocument();
  fireEvent.change(
    screen.getByRole("combobox", { name: "Filter claims by verdict" }),
    {
      target: { value: "NOT_EVALUATED" },
    },
  );
  expect(screen.getByText(/C2 · NOT_EVALUATED/)).toBeInTheDocument();
  expect(screen.queryByText(/C1 · SUPPORTED/)).not.toBeInTheDocument();
  vi.unstubAllGlobals();
});
