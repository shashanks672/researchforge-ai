import { documentProxy } from "../../../lib/document-proxy";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  return documentProxy(request, []);
}
