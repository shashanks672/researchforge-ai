import { UUID_PATTERN } from "../../../lib/sessions";
import { localWriteError, readJsonBody } from "../../../lib/request-security";
import { apiError, proxySessionRequest } from "../../../lib/session-proxy";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams;
  if (
    [...query.keys()].some((key) => !["limit", "offset"].includes(key)) ||
    query.getAll("limit").length > 1 ||
    query.getAll("offset").length > 1
  ) {
    return apiError("Use limit and offset for pagination.", 400);
  }
  const limit = query.get("limit") ?? "10";
  const offset = query.get("offset") ?? "0";
  if (
    !/^\d+$/.test(limit) ||
    !/^\d+$/.test(offset) ||
    Number(limit) < 1 ||
    Number(limit) > 50 ||
    Number(offset) > 10000
  )
    return apiError("Invalid pagination.", 400);
  return proxySessionRequest(
    `?limit=${Number(limit)}&offset=${Number(offset)}`,
    undefined,
    true,
  );
}

export async function POST(request: Request) {
  const denied = localWriteError(request);
  if (denied) return denied;
  const body = await readJsonBody(request);
  if (body.error) return body.error;
  const payload = body.value as Record<string, unknown> | null;
  if (
    !payload ||
    typeof payload !== "object" ||
    Array.isArray(payload) ||
    Object.keys(payload).some(
      (key) => !["question", "mode", "document_ids"].includes(key),
    ) ||
    (payload.document_ids !== undefined &&
      (!Array.isArray(payload.document_ids) ||
        payload.document_ids.length > 30 ||
        payload.document_ids.some(
          (id) => typeof id !== "string" || !UUID_PATTERN.test(id),
        ))) ||
    typeof payload.question !== "string" ||
    payload.question.trim().length < 10 ||
    payload.question.trim().length > 4000 ||
    !["web", "documents", "combined"].includes(String(payload.mode))
  ) {
    return apiError(
      "Enter a question between 10 and 4,000 characters and choose a valid mode.",
      422,
    );
  }
  return proxySessionRequest("", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: payload.question.trim(),
      mode: payload.mode,
      ...(payload.document_ids ? { document_ids: payload.document_ids } : {}),
    }),
  });
}
