vi.mock("../src/components/document-workspace", () => ({
  DocumentWorkspace: () => null,
}));
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SessionWorkspace } from "../src/components/session-workspace";
import type { ResearchSession } from "../src/lib/sessions";

vi.mock("../src/components/run-panel", () => ({ RunPanel: () => null }));

const record: ResearchSession = {
  id: "9f26c7d0-21f5-4cf6-9536-8a9112adb3ce",
  question: "How does retrieval improve grounded answers?",
  mode: "combined",
  status: "pending",
  created_at: "2026-10-19T00:00:00Z",
  updated_at: "2026-10-19T00:00:00Z",
  error_message: null,
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });
const page = (items: ResearchSession[] = [], offset = 0, hasMore = false) => ({
  items,
  total: hasMore ? 6 : items.length,
  limit: 5,
  offset,
  has_more: hasMore,
});

afterEach(() => vi.unstubAllGlobals());

test("empty history explains how to start and short questions are rejected locally", async () => {
  const fetchMock = vi
    .fn()
    .mockImplementation(() => Promise.resolve(json(page())));
  vi.stubGlobal("fetch", fetchMock);
  render(<SessionWorkspace />);
  expect(
    await screen.findByText(/No sessions on this page/),
  ).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Research question"), {
    target: { value: "short" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save session" }));
  expect(screen.getByRole("alert")).toHaveTextContent("between 10 and 4,000");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("successful submission saves intended mode, displays pending detail and refreshes history", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(json(page()))
    .mockResolvedValueOnce(json(record, 201))
    .mockResolvedValueOnce(json(page([record])));
  vi.stubGlobal("fetch", fetchMock);
  render(<SessionWorkspace />);
  await screen.findByText(/No sessions on this page/);
  fireEvent.change(screen.getByLabelText("Research question"), {
    target: { value: `  ${record.question}  ` },
  });
  fireEvent.change(screen.getByLabelText("Research mode"), {
    target: { value: "combined" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save session" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Session saved as pending",
  );
  expect(await screen.findByText(record.id)).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Save session" })).toBeEnabled(),
  );
  expect(screen.getByLabelText("Research question")).toHaveValue("");
  expect(fetchMock.mock.calls[1][1]).toMatchObject({
    method: "POST",
    body: JSON.stringify({ question: record.question, mode: "combined" }),
  });
});

test("saving has a visible loading state and blocks duplicate submissions", async () => {
  let finish: (value: Response) => void = () => {};
  const pending = new Promise<Response>((resolve) => {
    finish = resolve;
  });
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(json(page()))
    .mockReturnValueOnce(pending)
    .mockResolvedValueOnce(json(page([record])));
  vi.stubGlobal("fetch", fetchMock);
  render(<SessionWorkspace />);
  await screen.findByText(/No sessions on this page/);
  fireEvent.change(screen.getByLabelText("Research question"), {
    target: { value: record.question },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save session" }));
  expect(
    screen.getByRole("button", { name: "Saving session…" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("Research question")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Saving session…" }));
  expect(fetchMock).toHaveBeenCalledTimes(2);
  finish(json(record, 201));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Session saved as pending",
  );
});

test("submission errors keep the question available for correction", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(json(page()))
      .mockResolvedValueOnce(
        json({ error: "Database unavailable. Start PostgreSQL." }, 503),
      ),
  );
  render(<SessionWorkspace />);
  await screen.findByText(/No sessions on this page/);
  fireEvent.change(screen.getByLabelText("Research question"), {
    target: { value: record.question },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save session" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Database unavailable",
  );
  expect(screen.getByLabelText("Research question")).toHaveValue(
    record.question,
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

test("history rows load detail from the actual detail API contract", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(json(page([record])))
    .mockResolvedValueOnce(json(record));
  vi.stubGlobal("fetch", fetchMock);
  render(<SessionWorkspace />);
  fireEvent.click(
    await screen.findByRole("button", { name: /How does retrieval/ }),
  );
  expect(await screen.findByText(record.id)).toBeInTheDocument();
  expect(fetchMock.mock.calls[1][0]).toBe(`/api/sessions/${record.id}`);
  expect(
    screen.getByRole("button", { name: "Refresh status" }),
  ).toBeInTheDocument();
});

test("history failures have an explicit retry path", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockRejectedValueOnce(new TypeError("network failed"))
      .mockResolvedValueOnce(json(page())),
  );
  render(<SessionWorkspace />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not load history",
  );
  fireEvent.click(screen.getByRole("button", { name: /Refresh history/ }));
  expect(
    await screen.findByText(/No sessions on this page/),
  ).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("pagination requests the next stored page", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(json(page([record], 0, true)))
    .mockResolvedValueOnce(json(page([], 5)));
  vi.stubGlobal("fetch", fetchMock);
  render(<SessionWorkspace />);
  await screen.findByRole("button", { name: /How does retrieval/ });
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByText(/Page 2/);
  expect(fetchMock.mock.calls[1][0]).toBe("/api/sessions?limit=5&offset=5");
});
