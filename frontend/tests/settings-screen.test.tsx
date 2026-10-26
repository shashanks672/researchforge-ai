import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SettingsScreen } from "../src/components/settings-screen";

afterEach(() => vi.unstubAllGlobals());

function systemStatus(overrides: Record<string, unknown> = {}) {
  return {
    status: "ok",
    service: "researchforge-api",
    version: "0.1.0",
    phase: 7,
    access_mode: "single-user-local",
    research_enabled: true,
    uploads_enabled: true,
    llm_provider: "ollama",
    search_provider: "disabled",
    model: "qwen3:8b",
    free_search_enabled: false,
    sessions_enabled: true,
    execution_mode: "local",
    ...overrides,
  };
}

test("explains how to enable free public search without inventing contact details", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify(systemStatus()))),
  );
  render(<SettingsScreen />);
  expect(await screen.findByText(/Public search is off/)).toBeInTheDocument();
  expect(
    screen.getByText(/English Wikipedia only, not the whole web/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      /provide a real public contact URL or email; no contact is guessed/,
    ),
  ).toBeInTheDocument();
});

test("describes Wikipedia's limited public search scope when enabled", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify(
          systemStatus({
            search_provider: "wikipedia",
            free_search_enabled: true,
          }),
        ),
      ),
    ),
  );
  render(<SettingsScreen />);
  expect(
    await screen.findByText(/Search uses the English Wikipedia API/),
  ).toBeInTheDocument();
  expect(screen.getByText(/not general web search/)).toBeInTheDocument();
  expect(screen.getByText(/follow its applicable license/)).toBeInTheDocument();
  expect(
    screen.getByText(/Planned search terms are sent to Wikimedia/),
  ).toBeInTheDocument();
});
