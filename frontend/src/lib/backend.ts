// Server-only configuration. Browser components never import this module.
export function backendOrigin(): URL {
  const base = new URL(process.env.BACKEND_URL ?? "http://127.0.0.1:8000");
  if (
    base.protocol !== "http:" ||
    !["localhost", "127.0.0.1", "[::1]"].includes(base.hostname) ||
    base.username ||
    base.password ||
    base.pathname !== "/" ||
    base.search ||
    base.hash
  )
    throw new Error("Use a local backend origin");
  return base;
}

export function backendFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  return fetch(new URL(path, backendOrigin()), {
    ...init,
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(10000),
  });
}
