"use client";

import { useEffect, useState } from "react";

type Connection = "checking" | "connected" | "offline";

async function checkConnection(signal?: AbortSignal): Promise<Connection> {
  try {
    const response = await fetch("/api/system", {
      cache: "no-store",
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(5000)])
        : AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error("Unavailable");
    const data = await response.json();
    if (data.status !== "ok" || data.service !== "researchforge-api")
      throw new Error("Invalid status");
    return "connected";
  } catch {
    return "offline";
  }
}

export function SystemCheck() {
  const [connection, setConnection] = useState<Connection>("checking");

  useEffect(() => {
    const controller = new AbortController();
    void checkConnection(controller.signal).then((value) => {
      if (!controller.signal.aborted) setConnection(value);
    });
    return () => controller.abort();
  }, []);

  return (
    <section className="system-card" aria-labelledby="system-title">
      <div className="section-heading">
        <span className="eyebrow">LIVE CONNECTION</span>
        <span
          className={`connection ${connection}`}
          role="status"
          aria-live="polite"
        >
          <span className="status-dot" />
          {connection === "checking"
            ? "Checking backend…"
            : connection === "connected"
              ? "Backend connected"
              : "Backend offline"}
        </span>
      </div>
      <h2 id="system-title">A foundation you can inspect.</h2>
      <p>
        The dashboard checks the real FastAPI health and configuration
        endpoints. Research availability is controlled by server-side provider
        settings.
      </p>
      <div className="system-details">
        <div>
          <span>API</span>
          <strong>FastAPI · v0.1.0</strong>
        </div>
        <div>
          <span>Access</span>
          <strong>Single user · localhost</strong>
        </div>
        <div>
          <span>Model & search</span>
          <strong>Server-side configuration</strong>
        </div>
      </div>
      {connection === "offline" && (
        <p className="error-message" role="alert">
          Start the backend on port 8000, then check the connection again.
        </p>
      )}
      <button
        className="text-button"
        type="button"
        onClick={() => {
          setConnection("checking");
          void checkConnection().then(setConnection);
        }}
        disabled={connection === "checking"}
      >
        Check connection <span aria-hidden="true">↗</span>
      </button>
    </section>
  );
}
