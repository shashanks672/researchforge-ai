import { parseVerification } from "../../../../../lib/verification";
import { backendFetch } from "../../../../../lib/backend";
import {
  localWriteError,
  readJsonBody,
} from "../../../../../lib/request-security";
import { parseRun } from "../../../../../lib/runs";
import { apiError } from "../../../../../lib/session-proxy";
import { UUID_PATTERN } from "../../../../../lib/sessions";

export const dynamic = "force-dynamic";
type Context = { params: Promise<{ id: string; action: string }> };

async function upstream(id: string, action: string, init?: RequestInit) {
  try {
    const response = await backendFetch(
      `/api/v1/research/sessions/${id}/${action}`,
      init,
    );
    if (!response.ok) {
      const errors: Record<number, string> = {
        404: "No execution or completed report is available for this session.",
        409: "The worker is busy, the session already ran, or the execution mode does not match. Refresh before retrying.",
        422: "Selected documents are unavailable or not ready. Check indexing and the configured embedding model.",
        503: "Research is unavailable. Check the database and explicitly configured providers. Live calls need separate approval.",
      };
      return apiError(
        errors[response.status] ?? "Research request failed.",
        response.status < 500 ? response.status : 503,
      );
    }
    if (action === "report")
      return new Response(await response.text(), {
        headers: {
          "Content-Type": "text/markdown; charset=utf-8",
          "Content-Disposition": `attachment; filename="researchforge-${id}.md"`,
          "Cache-Control": "no-store",
        },
      });
    if (action === "cancel")
      return Response.json(
        { status: "cancelled" },
        { headers: { "Cache-Control": "no-store" } },
      );
    return Response.json(
      action === "verification"
        ? parseVerification(await response.json())
        : parseRun(await response.json()),
      {
        status: response.status,
        headers: { "Cache-Control": "no-store" },
      },
    );
  } catch {
    return apiError(
      "Could not confirm research state. Refresh before retrying; no automatic write retry was attempted.",
      503,
    );
  }
}

export async function GET(_request: Request, context: Context) {
  const { id, action } = await context.params;
  if (
    !UUID_PATTERN.test(id) ||
    !["run", "report", "verification"].includes(action)
  )
    return apiError("Invalid research path.", 400);
  return upstream(id, action);
}

export async function POST(request: Request, context: Context) {
  const { id, action } = await context.params;
  if (!UUID_PATTERN.test(id) || !["execute", "cancel"].includes(action))
    return apiError("Invalid research path.", 400);
  const denied = localWriteError(request);
  if (denied) return denied;
  const body = await readJsonBody(request);
  if (body.error) return body.error;
  const value = body.value;
  if (!value || typeof value !== "object" || Array.isArray(value))
    return apiError("Invalid execution request.", 422);
  const payload = value as Record<string, unknown>;
  if (
    action === "execute" &&
    (Object.keys(payload).length !== 1 ||
      !["mock", "local", "live"].includes(String(payload.execution_mode)))
  )
    return apiError(
      "Choose an explicit mock, local or live execution mode.",
      422,
    );
  if (action === "cancel" && Object.keys(payload).length)
    return apiError("Cancel takes no execution parameters.", 422);
  return upstream(id, action, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
