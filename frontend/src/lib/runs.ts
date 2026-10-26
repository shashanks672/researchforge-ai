import type { ResearchSession } from "./sessions";
import { parseSession } from "./sessions";

export interface ResearchRun {
  id: string;
  session_id: string;
  execution_mode: "mock" | "local" | "live";
  stage: string;
  plan: {
    objective: string;
    scope: string;
    subquestions: { question: string; search_query: string }[];
  } | null;
  sources: {
    source_id: string;
    source_type: "mock" | "web" | "document";
    document_id?: string;
    chunk_id?: string;
    page?: number | null;
    title: string;
    url: string;
    excerpt: string;
    retrieved_at: string;
    published_at: string | null;
  }[];
  investigated_queries: string[];
  warnings: string[];
  report_markdown: string | null;
  error_code: string | null;
  metrics: {
    llm_calls: number;
    input_tokens: number;
    output_tokens: number;
    tool_calls: number;
    estimated_cost_usd: number | null;
    usage_complete: boolean;
    elapsed_ms: number;
    model_inference_ms: number;
    model_load_ms: number;
    model_tokens_per_second: number | null;
  };
}

export function parseRun(value: unknown): ResearchRun {
  if (!value || typeof value !== "object")
    throw new Error("Invalid run response");
  const run = value as ResearchRun;
  if (
    !run.id ||
    !run.session_id ||
    !["mock", "local", "live"].includes(run.execution_mode) ||
    typeof run.stage !== "string" ||
    !Array.isArray(run.sources) ||
    !Array.isArray(run.warnings) ||
    (run.plan !== null &&
      (!run.plan || !Array.isArray(run.plan.subquestions))) ||
    (run.report_markdown !== null && typeof run.report_markdown !== "string") ||
    !run.metrics
  ) {
    throw new Error("Invalid run response");
  }
  for (const source of run.sources) {
    const url = new URL(source.url);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      !["mock", "web", "document"].includes(source.source_type) ||
      typeof source.excerpt !== "string"
    )
      throw new Error("Invalid source response");
  }
  return run;
}

async function read(response: Response): Promise<unknown> {
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.error === "string" ? data.error : "Research request failed.",
    );
  return data;
}

export async function getRun(id: string): Promise<ResearchRun | null> {
  const response = await fetch(`/api/sessions/${id}/run`, {
    cache: "no-store",
    signal: AbortSignal.timeout(12000),
  });
  if (response.status === 404) return null;
  return parseRun(await read(response));
}

export async function executeRun(
  id: string,
  mode: "mock" | "local" | "live",
): Promise<ResearchRun> {
  const response = await fetch(`/api/sessions/${id}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ execution_mode: mode }),
    signal: AbortSignal.timeout(12000),
  });
  return parseRun(await read(response));
}

export async function cancelRun(id: string): Promise<void> {
  await read(
    await fetch(`/api/sessions/${id}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(12000),
    }),
  );
}

export async function currentSession(id: string): Promise<ResearchSession> {
  return parseSession(
    await read(
      await fetch(`/api/sessions/${id}`, {
        cache: "no-store",
        signal: AbortSignal.timeout(12000),
      }),
    ),
  );
}
