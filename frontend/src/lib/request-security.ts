import { apiError } from "./session-proxy";

export function localWriteError(request: Request): Response | null {
  const url = new URL(request.url);
  let incoming: URL;
  try {
    incoming = new URL(`http://${request.headers.get("host") ?? url.host}`);
  } catch {
    return apiError("Untrusted origin.", 403);
  }
  const origin = request.headers.get("origin");
  if (
    (origin !== null && origin !== incoming.origin) ||
    request.headers.get("sec-fetch-site") === "cross-site" ||
    !["localhost", "127.0.0.1", "[::1]"].includes(incoming.hostname) ||
    incoming.username ||
    incoming.password ||
    incoming.pathname !== "/" ||
    incoming.search ||
    incoming.hash
  )
    return apiError("Untrusted origin.", 403);
  if (request.headers.get("content-type")?.split(";")[0] !== "application/json")
    return apiError("Use application/json.", 415);
  return null;
}

export async function readJsonBody(
  request: Request,
): Promise<{ value?: unknown; error?: Response }> {
  const reader = request.body?.getReader();
  if (!reader)
    return { error: apiError("A JSON request body is required.", 400) };
  let body = "";
  let bytes = 0;
  const decoder = new TextDecoder();
  try {
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      bytes += part.value.byteLength;
      if (bytes > 20000) {
        await reader.cancel();
        return { error: apiError("Request body is too large.", 413) };
      }
      body += decoder.decode(part.value, { stream: true });
    }
    return { value: JSON.parse(body + decoder.decode()) };
  } catch {
    return { error: apiError("Invalid JSON request.", 400) };
  } finally {
    reader.releaseLock();
  }
}
