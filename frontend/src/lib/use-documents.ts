"use client";

import { useCallback, useEffect, useState } from "react";
import {
  documentRequest,
  parseDocument,
  type UploadedDocument,
} from "./documents";

export function useDocuments() {
  const [documents, setDocuments] = useState<UploadedDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [polling, setPolling] = useState(false);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const value = await documentRequest("", undefined, signal);
      if (!Array.isArray(value))
        throw new Error("The document list was not recognized.");
      if (signal?.aborted) return;
      const parsed = value.map(parseDocument);
      setDocuments(parsed);
      setPolling(
        parsed.some((item) =>
          ["queued", "processing", "deleting"].includes(item.status),
        ),
      );
      setError("");
    } catch (failure) {
      if (!signal?.aborted)
        setError(
          failure instanceof Error
            ? failure.message
            : "Could not load your documents.",
        );
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => void refresh(controller.signal), 0);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [refresh]);

  useEffect(() => {
    if (!polling) return;
    const controller = new AbortController();
    let pending = false;
    const timer = window.setInterval(() => {
      if (pending) return;
      pending = true;
      void refresh(controller.signal).finally(() => {
        pending = false;
      });
    }, 2500);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [polling, refresh]);

  return { documents, loading, error, setError, refresh };
}
