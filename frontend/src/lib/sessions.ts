export type ResearchMode = "web" | "documents" | "combined";
export type SessionStatus =
  "pending" | "running" | "completed" | "failed" | "cancelled";
export interface ResearchSession {
  id: string;
  document_ids?: string[];
  question: string;
  mode: ResearchMode;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  error_message: string | null;
}
export interface SessionPage {
  items: ResearchSession[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}
export const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parseSession(data: unknown): ResearchSession {
  if (!data || typeof data !== "object")
    throw new Error("Invalid session response");
  const row = data as Record<string, unknown>;
  if (
    typeof row.id !== "string" ||
    !UUID_PATTERN.test(row.id) ||
    typeof row.question !== "string" ||
    row.question.length < 10 ||
    row.question.length > 4000 ||
    !["web", "documents", "combined"].includes(String(row.mode)) ||
    !["pending", "running", "completed", "failed", "cancelled"].includes(
      String(row.status),
    ) ||
    typeof row.created_at !== "string" ||
    !Number.isFinite(Date.parse(row.created_at)) ||
    typeof row.updated_at !== "string" ||
    !Number.isFinite(Date.parse(row.updated_at)) ||
    (row.error_message !== null && typeof row.error_message !== "string")
  )
    throw new Error("Invalid session response");
  return {
    id: row.id,
    document_ids: Array.isArray(row.document_ids)
      ? row.document_ids.filter(
          (id): id is string => typeof id === "string" && UUID_PATTERN.test(id),
        )
      : [],
    question: row.question,
    mode: row.mode as ResearchMode,
    status: row.status as SessionStatus,
    created_at: row.created_at,
    updated_at: row.updated_at,
    error_message: row.error_message as string | null,
  };
}

export function parseSessionPage(data: unknown): SessionPage {
  if (!data || typeof data !== "object")
    throw new Error("Invalid history response");
  const page = data as Record<string, unknown>;
  if (
    !Array.isArray(page.items) ||
    !Number.isInteger(page.total) ||
    Number(page.total) < 0 ||
    !Number.isInteger(page.limit) ||
    Number(page.limit) < 1 ||
    Number(page.limit) > 50 ||
    !Number.isInteger(page.offset) ||
    Number(page.offset) < 0 ||
    typeof page.has_more !== "boolean"
  ) {
    throw new Error("Invalid history response");
  }
  return {
    items: page.items.map(parseSession),
    total: page.total as number,
    limit: page.limit as number,
    offset: page.offset as number,
    has_more: page.has_more,
  };
}

async function responseData(response: Response): Promise<unknown> {
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.error === "string"
        ? data.error
        : "Request failed. Try again.",
    );
  return data;
}

export async function fetchSessionPage(
  offset: number,
  signal?: AbortSignal,
  limit = 50,
): Promise<SessionPage> {
  const response = await fetch(
    `/api/sessions?limit=${Math.min(50, Math.max(1, limit))}&offset=${offset}`,
    {
      cache: "no-store",
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(12000)])
        : AbortSignal.timeout(12000),
    },
  );
  return parseSessionPage(await responseData(response));
}

export async function fetchSession(
  id: string,
  signal?: AbortSignal,
): Promise<ResearchSession> {
  const response = await fetch(`/api/sessions/${id}`, {
    cache: "no-store",
    signal: signal ?? AbortSignal.timeout(12000),
  });
  return parseSession(await responseData(response));
}

export async function saveSession(
  question: string,
  mode: ResearchMode,
  documentIds: string[] = [],
): Promise<ResearchSession> {
  const response = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      mode,
      ...(documentIds.length ? { document_ids: documentIds } : {}),
    }),
    signal: AbortSignal.timeout(12000),
  });
  return parseSession(await responseData(response));
}
