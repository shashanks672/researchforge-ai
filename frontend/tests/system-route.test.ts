import { afterEach, expect, test, vi } from "vitest";
import { GET } from "../src/app/api/system/route";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

test("proxy rejects nonlocal backend before making a request", async () => {
  vi.stubEnv("BACKEND_URL", "http://169.254.169.254");
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  expect((await GET()).status).toBe(503);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("proxy hides connection details on failure", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new Error("secret backend credentials")),
  );
  const response = await GET();
  expect(response.status).toBe(503);
  expect(await response.text()).not.toContain("secret");
});

test("proxy allowlists public fields", async () => {
  vi.stubEnv("BACKEND_URL", "http://127.0.0.1:8000");
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "ok",
            service: "researchforge-api",
            version: "0.1.0",
          }),
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            phase: 2,
            access_mode: "single-user-local",
            research_enabled: false,
            sessions_enabled: true,
            execution_mode: "disabled",
            uploads_enabled: true,
            llm_provider: "disabled",
            search_provider: "disabled",
            api_key: "secret",
          }),
        ),
      ),
  );
  const response = await GET();
  expect(response.status).toBe(200);
  expect(await response.text()).not.toContain("secret");
});
