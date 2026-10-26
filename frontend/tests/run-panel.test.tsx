vi.mock("../src/components/verification-panel", () => ({
  VerificationPanel: () => null,
}));
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { RunPanel } from "../src/components/run-panel";
import {
  cancelRun,
  currentSession,
  executeRun,
  getRun,
  parseRun,
  type ResearchRun,
} from "../src/lib/runs";
import type { ResearchSession } from "../src/lib/sessions";

vi.mock("../src/lib/runs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/lib/runs")>();
  return {
    ...actual,
    getRun: vi.fn(),
    executeRun: vi.fn(),
    currentSession: vi.fn(),
    cancelRun: vi.fn(),
  };
});
const session: ResearchSession = {
  id: "9f26c7d0-21f5-4cf6-9536-8a9112adb3ce",
  question: "How does grounded research work?",
  mode: "web",
  status: "pending",
  created_at: "2026-10-19T00:00:00Z",
  updated_at: "2026-10-19T00:00:00Z",
  error_message: null,
};
const completed: ResearchRun = {
  id: session.id,
  session_id: session.id,
  execution_mode: "mock",
  stage: "completed",
  plan: {
    objective: "Demonstrate evidence provenance",
    scope: "Synthetic fixtures only",
    subquestions: [
      { question: "How are citations linked?", search_query: "mock citations" },
    ],
  },
  sources: [
    {
      source_id: "S1",
      source_type: "mock",
      title: "MOCK fixture",
      url: "https://example.org/fixture",
      excerpt: "Synthetic evidence used to demonstrate citation handling only.",
      retrieved_at: "2026-10-19T00:00:00Z",
      published_at: null,
    },
  ],
  investigated_queries: ["mock citations"],
  warnings: [],
  report_markdown: "# MOCK report\n<script>alert('untrusted')</script>",
  error_code: null,
  metrics: {
    llm_calls: 2,
    tool_calls: 3,
    input_tokens: 0,
    output_tokens: 0,
    usage_complete: true,
    estimated_cost_usd: 0,
    elapsed_ms: 20,
    model_inference_ms: 0,
    model_load_ms: 0,
    model_tokens_per_second: null,
  },
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getRun).mockResolvedValue(null);
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({ execution_mode: "mock", search_provider: "mock" }),
          ),
        ),
      ),
  );
});
afterEach(() => vi.unstubAllGlobals());

test("disabled providers expose no execution button", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          execution_mode: "disabled",
          search_provider: "disabled",
        }),
      ),
    ),
  );
  render(<RunPanel session={session} onSessionChange={vi.fn()} />);
  expect(await screen.findByText(/Research is disabled/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Run mock/ }),
  ).not.toBeInTheDocument();
});

test("mock start requires an explicit action and visibly labels synthetic evidence", async () => {
  vi.mocked(executeRun).mockResolvedValue({
    ...completed,
    stage: "accepted",
    report_markdown: null,
  });
  vi.mocked(currentSession).mockResolvedValue({
    ...session,
    status: "running",
  });
  const onChange = vi.fn();
  render(<RunPanel session={session} onSessionChange={onChange} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Run mock demonstration" }),
  );
  expect(
    await screen.findByText(/Execution stage: accepted/),
  ).toBeInTheDocument();
  expect(executeRun).toHaveBeenCalledWith(session.id, "mock");
  expect(screen.getByText(/MOCK DEMONSTRATION:/)).toBeInTheDocument();
  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: "running" }),
    ),
  );
});

test("persisted plans, sources and report are displayed as text with Markdown export", async () => {
  vi.mocked(getRun).mockResolvedValue(completed);
  render(
    <RunPanel
      session={{ ...session, status: "completed" }}
      onSessionChange={vi.fn()}
    />,
  );
  expect(
    await screen.findByText("Demonstrate evidence provenance"),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /MOCK fixture/ })).toHaveAttribute(
    "href",
    "https://example.org/fixture",
  );
  expect(screen.getByRole("link", { name: /Export Markdown/ })).toHaveAttribute(
    "href",
    `/api/sessions/${session.id}/report`,
  );
  expect(screen.getByText(/<script>alert/)).toBeInTheDocument();
  expect(document.querySelector(".report-viewer script")).toBeNull();
});

test("persisted Combined results render document pages and synthetic web provenance", async () => {
  vi.mocked(getRun).mockResolvedValue({
    ...completed,
    sources: [
      {
        source_id: "S1",
        source_type: "document",
        title: "phase7-local-demo.pdf",
        url: "https://researchforge.local/documents/phase7-local-demo.pdf",
        excerpt: "The Juniper battery has a rated capacity of 12 kWh.",
        retrieved_at: "2026-10-26T00:00:00Z",
        published_at: null,
        page: 1,
        chunk_id: "chunk-phase7-page-1",
        document_id: "document-phase7-demo",
      },
      {
        source_id: "S2",
        source_type: "web",
        title: "Synthetic kilowatt-hour note",
        url: "https://fixtures.example.invalid/kilowatt-hour",
        excerpt:
          "Synthetic test note: The workshop tracks electrical energy use in kilowatt-hours.",
        retrieved_at: "2026-10-26T00:00:00Z",
        published_at: null,
      },
    ],
    report_markdown:
      "# Combined report\nThe battery is rated at 12 kWh [S1]. A kilowatt-hour measures energy [S2].",
  });
  render(
    <RunPanel
      session={{ ...session, mode: "combined", status: "completed" }}
      onSessionChange={vi.fn()}
    />,
  );
  await screen.findByText("Research report");
  expect(document.querySelector(".report-viewer")?.textContent).toContain(
    "The battery is rated at 12 kWh [S1]. A kilowatt-hour measures energy [S2].",
  );
  expect(
    screen.getByRole("link", { name: /phase7-local-demo.pdf/ }),
  ).toHaveAttribute(
    "href",
    "https://researchforge.local/documents/phase7-local-demo.pdf",
  );
  expect(
    screen.getByText(/Document · page 1 · chunk chunk-phase7-page-1/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Synthetic kilowatt-hour note/ }),
  ).toHaveAttribute("href", "https://fixtures.example.invalid/kilowatt-hour");
  expect(
    screen.getByText("The Juniper battery has a rated capacity of 12 kWh."),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "Synthetic test note: The workshop tracks electrical energy use in kilowatt-hours.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByText(/MOCK DEMONSTRATION:/)).toBeInTheDocument();
});

test("failed start displays an error without pretending a report exists", async () => {
  vi.mocked(executeRun).mockRejectedValue(
    new Error("Worker is busy. Refresh before retrying."),
  );
  render(<RunPanel session={session} onSessionChange={vi.fn()} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "Run mock demonstration" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("Worker is busy");
  expect(screen.queryByText("Research report")).not.toBeInTheDocument();
});

test("cancellation updates the persisted status", async () => {
  vi.mocked(getRun)
    .mockResolvedValueOnce({
      ...completed,
      stage: "accepted",
      report_markdown: null,
    })
    .mockResolvedValueOnce({
      ...completed,
      stage: "cancelled",
      report_markdown: null,
    });
  vi.mocked(cancelRun).mockResolvedValue(undefined);
  vi.mocked(currentSession).mockResolvedValue({
    ...session,
    status: "cancelled",
  });
  const onChange = vi.fn();
  render(
    <RunPanel
      session={{ ...session, status: "running" }}
      onSessionChange={onChange}
    />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Cancel run" }));
  expect(
    await screen.findByText(/Execution stage: cancelled/),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: "cancelled" }),
    ),
  );
});

test("polling a terminal stage refreshes parent session status", async () => {
  vi.mocked(getRun)
    .mockResolvedValueOnce({
      ...completed,
      stage: "accepted",
      report_markdown: null,
    })
    .mockResolvedValue(completed);
  vi.mocked(currentSession).mockResolvedValue({
    ...session,
    status: "completed",
  });
  const onChange = vi.fn();
  render(
    <RunPanel
      session={{ ...session, status: "running" }}
      onSessionChange={onChange}
    />,
  );
  await screen.findByText(/Execution stage: accepted/);
  expect(
    await screen.findByText(
      /Execution stage: completed/,
      {},
      { timeout: 3500 },
    ),
  ).toBeInTheDocument();
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ status: "completed" }),
  );
});

test("unexpected executable source URLs are rejected", () => {
  expect(() =>
    parseRun({
      ...completed,
      sources: [{ ...completed.sources[0], url: "javascript:alert(1)" }],
    }),
  ).toThrow();
});
