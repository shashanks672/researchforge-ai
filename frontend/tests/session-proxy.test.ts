import { afterEach, expect, test, vi } from "vitest";
import { GET, POST } from "../src/app/api/sessions/route";
import { GET as detail } from "../src/app/api/sessions/[id]/route";

const payload = { question: "Explain evidence-grounded research", mode: "web" };
function request(
  body: unknown = payload,
  headers: Record<string, string> = {},
) {
  return new Request("http://127.0.0.1:3000/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test("cross-site writes and extra execution fields never reach the backend", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  expect(
    (await POST(request(payload, { Origin: "https://attacker.example" })))
      .status,
  ).toBe(403);
  expect(
    (await POST(request({ ...payload, status: "completed" }))).status,
  ).toBe(422);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("normalized Next.js URLs accept the actual local browser origin but reject a remote Host", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response("unavailable", { status: 503 }));
  vi.stubGlobal("fetch", fetchMock);
  const normalized = new Request("http://localhost:3000/api/sessions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Host: "127.0.0.1:3000",
      Origin: "http://127.0.0.1:3000",
    },
    body: JSON.stringify(payload),
  });
  expect((await POST(normalized)).status).toBe(503); // Reached the backend, which is unavailable in this test.
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(
    (await POST(request(payload, { Host: "attacker.example" }))).status,
  ).toBe(403);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("chunked oversized body is rejected before a backend request", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  expect(
    (await POST(request({ question: "x".repeat(21000), mode: "web" }))).status,
  ).toBe(413);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("invalid pagination and IDs cannot construct arbitrary upstream paths", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  for (const query of [
    "limit=0",
    "offset=-1",
    "limit=51",
    "limit=1&limit=2",
    "url=http://evil.example",
  ]) {
    expect(
      (await GET(new Request(`http://127.0.0.1:3000/api/sessions?${query}`)))
        .status,
    ).toBe(400);
  }
  expect(
    (
      await detail(new Request("http://127.0.0.1:3000"), {
        params: Promise.resolve({ id: "../../config" }),
      })
    ).status,
  ).toBe(400);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("database failure is sanitized and writes are never automatically retried", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: "private-password" }), {
      status: 503,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const response = await POST(request());
  expect(response.status).toBe(503);
  const body = await response.text();
  expect(body).toContain("Database unavailable");
  expect(body).not.toContain("private-password");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("unknown sessions keep their 404 status", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("private failure", { status: 404 })),
  );
  const response = await detail(new Request("http://127.0.0.1:3000"), {
    params: Promise.resolve({ id: "9f26c7d0-21f5-4cf6-9536-8a9112adb3ce" }),
  });
  expect(response.status).toBe(404);
  expect(await response.json()).toEqual({
    error: "Research session not found.",
  });
});

test("malformed JSON fails clearly", async () => {
  const response = await POST(
    new Request("http://127.0.0.1:3000/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{broken",
    }),
  );
  expect(response.status).toBe(400);
});
