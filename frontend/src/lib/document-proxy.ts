import { backendFetch } from "./backend";
import { localWriteError } from "./request-security";
import { apiError } from "./session-proxy";
import { parseDocument } from "./documents";
import { UUID_PATTERN } from "./sessions";
export async function documentProxy(request: Request, parts: string[]) {
  const upload = parts.length === 1 && parts[0] === "upload";
  const valid =
    parts.length === 0 ||
    upload ||
    (UUID_PATTERN.test(parts[0] ?? "") &&
      (parts.length === 1 ||
        (parts.length === 2 && ["delete", "reindex"].includes(parts[1]))));
  if (
    !valid ||
    (request.method === "GET" && (upload || parts.length > 1)) ||
    (request.method === "POST" && !upload && parts.length !== 2)
  )
    return apiError("Invalid document path", 400);
  let init: RequestInit | undefined;
  if (request.method === "POST") {
    const headers = new Headers(request.headers);
    headers.set("Content-Type", "application/json");
    const check = upload
      ? new Request(request.url, { method: "POST", headers })
      : request;
    const denied = localWriteError(check);
    if (denied) return denied;
    if (upload) {
      if (request.headers.get("content-type") !== "application/octet-stream")
        return apiError("Use binary upload", 415);
      const reader = request.body?.getReader();
      if (!reader) return apiError("Empty upload", 422);
      const buffers: Uint8Array[] = [];
      let size = 0;
      try {
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          size += part.value.length;
          if (size > 5000000) {
            await reader.cancel();
            return apiError("Maximum upload is 5 MB", 413);
          }
          buffers.push(part.value);
        }
      } finally {
        reader.releaseLock();
      }
      const joined = new Uint8Array(size);
      let offset = 0;
      for (const b of buffers) {
        joined.set(b, offset);
        offset += b.length;
      }
      init = {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Filename": request.headers.get("x-filename") ?? "",
        },
        body: joined,
      };
    } else
      init = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      };
  }
  try {
    const response = await backendFetch(
      `/api/v1/documents${parts.length ? "/" + parts.join("/") : ""}`,
      init,
    );
    if (!response.ok) {
      const errors: Record<number, string> = {
        404: "Document not found",
        409: "Duplicate upload, busy worker, active research, or storage limit. Refresh before retrying.",
        413: "Maximum upload is 5 MB",
        422: "Invalid filename or document contents",
        503: "Document service unavailable. Check PostgreSQL, Qdrant and the cached embedding model.",
      };
      return apiError(
        errors[response.status] ?? "Document request failed",
        response.status >= 500 ? 503 : response.status,
      );
    }
    const data = await response.json();
    return Response.json(
      Array.isArray(data) ? data.map(parseDocument) : parseDocument(data),
      { status: response.status, headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return apiError(
      "Could not confirm document state. Refresh before retrying.",
      503,
    );
  }
}
