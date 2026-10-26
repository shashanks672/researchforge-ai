import { afterEach, expect, test, vi } from "vitest";
import { GET, POST } from "../src/app/api/sessions/[id]/[action]/route";

const id = "9f26c7d0-21f5-4cf6-9536-8a9112adb3ce";
const context = (action: string) => ({
  params: Promise.resolve({ id, action }),
});
function request(body: unknown, origin = "http://127.0.0.1:3000") {
  return new Request(`http://127.0.0.1:3000/api/sessions/${id}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: origin },
    body: JSON.stringify(body),
  });
}
afterEach(() => vi.unstubAllGlobals());

test("execution paths, origins and payloads are restricted before network access", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  expect(
    (
      await POST(
        request({ execution_mode: "mock" }, "https://attacker.example"),
        context("execute"),
      )
    ).status,
  ).toBe(403);
  expect(
    (
      await POST(
        request({ execution_mode: "mock", shell: "whoami" }),
        context("execute"),
      )
    ).status,
  ).toBe(422);
  expect(
    (await GET(new Request("http://127.0.0.1:3000"), context("../../config")))
      .status,
  ).toBe(400);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("upstream provider errors are sanitized", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: "private-provider-key" }), {
      status: 503,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const response = await POST(
    request({ execution_mode: "live" }),
    context("execute"),
  );
  expect(response.status).toBe(503);
  expect(await response.text()).not.toContain("private-provider-key");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("Markdown export is a plain attachment", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("# MOCK report")),
  );
  const response = await GET(
    new Request("http://127.0.0.1:3000"),
    context("report"),
  );
  expect(response.headers.get("Content-Type")).toContain("text/markdown");
  expect(response.headers.get("Content-Disposition")).toContain("attachment");
});
