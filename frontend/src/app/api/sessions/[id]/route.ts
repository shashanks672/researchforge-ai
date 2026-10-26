import { apiError, proxySessionRequest } from "../../../../lib/session-proxy";
import { UUID_PATTERN } from "../../../../lib/sessions";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  if (!UUID_PATTERN.test(id)) return apiError("Invalid session ID.", 400);
  return proxySessionRequest(`/${id}`);
}
