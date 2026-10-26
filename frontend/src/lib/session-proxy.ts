import { backendFetch } from "./backend";
import { parseSession, parseSessionPage } from "./sessions";

export function apiError(error: string, status: number): Response {
  return Response.json(
    { error },
    { status, headers: { "Cache-Control": "no-store" } },
  );
}

export async function proxySessionRequest(
  path: string,
  init?: RequestInit,
  list = false,
): Promise<Response> {
  try {
    const response = await backendFetch(
      `/api/v1/research/sessions${path}`,
      init,
    );
    if (!response.ok) {
      if (response.status === 404)
        return apiError("Research session not found.", 404);
      if (response.status === 422)
        return apiError(
          "Enter a question between 10 and 4,000 characters and choose a valid mode.",
          422,
        );
      if (response.status === 503)
        return apiError(
          "Database unavailable. Start PostgreSQL and apply migrations, then refresh history.",
          503,
        );
      return apiError("The backend could not complete this request.", 502);
    }
    const data = await response.json();
    const record = list ? parseSessionPage(data) : parseSession(data);
    return Response.json(record, {
      status: response.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return apiError(
      init?.method === "POST"
        ? "Could not confirm the save. Refresh history before trying again."
        : "Backend unavailable. Start FastAPI and try again.",
      503,
    );
  }
}
