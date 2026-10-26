import { readBackendStatus } from "../../../lib/system";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return Response.json(await readBackendStatus(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json(
      { error: "Backend unavailable. Start the FastAPI server and try again." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
