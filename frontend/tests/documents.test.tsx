import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { DocumentWorkspace } from "../src/components/document-workspace";
import { documentProxy } from "../src/lib/document-proxy";
const document = {
  id: "9f26c7d0-21f5-4cf6-9536-8a9112adb3ce",
  filename: "handbook.txt",
  size_bytes: 100,
  checksum: "abc",
  status: "ready",
  index_status: "indexed",
  page_count: null,
  chunk_count: 1,
  embedding_model: "fake-hash-v1",
  error_code: null,
  uploaded_at: "2026-10-19T00:00:00Z",
  content_type: "text/plain",
};
afterEach(() => vi.unstubAllGlobals());
test("document list reflects readiness and requires deletion confirmation", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(
      async (_url: string, init?: RequestInit) =>
        new Response(
          JSON.stringify(
            init?.method === "POST"
              ? { ...document, status: "deleted" }
              : [document],
          ),
        ),
    );
  vi.stubGlobal("fetch", fetcher);
  const selection = vi.fn();
  render(<DocumentWorkspace selected={[]} onSelection={selection} />);
  const check = await screen.findByRole("checkbox", {
    name: "Select handbook.txt",
  });
  fireEvent.click(check);
  expect(selection).toHaveBeenCalledWith([document.id]);
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(fetcher.mock.calls.some((c) => c[1]?.method === "POST")).toBe(false);
  fireEvent.click(
    await screen.findByRole("button", { name: "Remove document" }),
  );
  await waitFor(() =>
    expect(fetcher.mock.calls.some((c) => c[1]?.method === "POST")).toBe(true),
  );
});

test("a ready document can be reindexed only after explicit confirmation", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(async (_url: string, init?: RequestInit) => {
      const response =
        init?.method === "POST"
          ? { ...document, status: "queued" }
          : [document];
      return new Response(JSON.stringify(response));
    });
  vi.stubGlobal("fetch", fetcher);
  render(<DocumentWorkspace />);
  await screen.findByRole("heading", { name: "handbook.txt" });
  fireEvent.click(screen.getByRole("button", { name: "Reindex" }));
  expect(fetcher.mock.calls.some((call) => call[1]?.method === "POST")).toBe(
    false,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Reindex document" }),
  );
  await waitFor(() =>
    expect(
      fetcher.mock.calls.some(
        (call) =>
          String(call[0]).includes("/reindex") && call[1]?.method === "POST",
      ),
    ).toBe(true),
  );
});

test("document proxy rejects cross-site upload and arbitrary paths", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const request = new Request("http://127.0.0.1:3000/api/documents/upload", {
    method: "POST",
    headers: {
      Origin: "https://evil.example",
      "Content-Type": "application/octet-stream",
    },
    body: "bad",
  });
  expect((await documentProxy(request, ["upload"])).status).toBe(403);
  expect(
    (
      await documentProxy(new Request("http://127.0.0.1:3000"), [
        "..",
        "etc",
        "passwd",
      ])
    ).status,
  ).toBe(400);
  expect(fetcher).not.toHaveBeenCalled();
});
test("oversized streamed upload never reaches backend", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const request = new Request("http://127.0.0.1:3000/api/documents/upload", {
    method: "POST",
    headers: {
      "Content-Type": "application/octet-stream",
      "X-Filename": "big.txt",
    },
    body: new Uint8Array(5000001),
  });
  expect((await documentProxy(request, ["upload"])).status).toBe(413);
  expect(fetcher).not.toHaveBeenCalled();
});
