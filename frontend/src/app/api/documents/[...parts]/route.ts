import { documentProxy } from "../../../../lib/document-proxy";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ parts: string[] }> };
export async function GET(request: Request, context: Context) {
  return documentProxy(request, (await context.params).parts);
}
export async function POST(request: Request, context: Context) {
  return documentProxy(request, (await context.params).parts);
}
