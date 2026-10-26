import { backendOrigin } from "./backend";

export interface SystemStatus {
  status: "ok";
  service: "researchforge-api";
  version: string;
  phase: number;
  access_mode: "single-user-local";
  research_enabled: boolean;
  uploads_enabled: true;
  llm_provider: "disabled" | "mock" | "openai" | "ollama";
  search_provider: "disabled" | "mock" | "brave" | "wikipedia";
  model: string | null;
  free_search_enabled: boolean;
  sessions_enabled: true;
  execution_mode: "disabled" | "mock" | "local" | "live";
}

// This module is used only by the server route, never by the browser bundle.
export async function readBackendStatus(): Promise<SystemStatus> {
  const base = backendOrigin();
  const responses = await Promise.all(
    ["/health", "/api/v1/config"].map((path) =>
      fetch(new URL(path, base), {
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(3000),
      }),
    ),
  );
  if (responses.some((response) => !response.ok))
    throw new Error("Backend unavailable");
  const [health, config] = await Promise.all(
    responses.map((response) => response.json()),
  );
  if (
    health.status !== "ok" ||
    health.service !== "researchforge-api" ||
    typeof health.version !== "string" ||
    ![2, 3, 4, 5, 6, 7].includes(Number(config.phase)) ||
    config.sessions_enabled !== true ||
    config.access_mode !== "single-user-local" ||
    typeof config.research_enabled !== "boolean" ||
    !["disabled", "mock", "local", "live"].includes(config.execution_mode) ||
    config.uploads_enabled !== true ||
    !["disabled", "mock", "openai", "ollama"].includes(config.llm_provider) ||
    !["disabled", "mock", "brave", "wikipedia"].includes(
      config.search_provider,
    ) ||
    (config.model !== undefined &&
      config.model !== null &&
      typeof config.model !== "string") ||
    (config.free_search_enabled !== undefined &&
      typeof config.free_search_enabled !== "boolean")
  )
    throw new Error("Unexpected backend contract");
  // Allowlist fields instead of forwarding arbitrary backend configuration.
  return {
    status: "ok",
    service: "researchforge-api",
    version: health.version,
    phase: Number(config.phase),
    access_mode: "single-user-local",
    research_enabled: config.research_enabled,
    uploads_enabled: true,
    llm_provider: config.llm_provider,
    search_provider: config.search_provider,
    model: typeof config.model === "string" ? config.model : null,
    free_search_enabled: config.free_search_enabled === true,
    sessions_enabled: true,
    execution_mode: config.execution_mode,
  };
}
