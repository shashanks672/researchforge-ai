import { UUID_PATTERN } from "./sessions";
export interface UploadedDocument {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  checksum: string;
  status: string;
  index_status: string;
  page_count: number | null;
  chunk_count: number;
  embedding_model: string | null;
  error_code: string | null;
  uploaded_at: string;
}
export function parseDocument(value: unknown): UploadedDocument {
  if (!value || typeof value !== "object")
    throw new Error("Invalid document response");
  const d = value as UploadedDocument;
  if (
    !UUID_PATTERN.test(d.id) ||
    typeof d.filename !== "string" ||
    !Number.isInteger(d.size_bytes) ||
    ![
      "queued",
      "processing",
      "ready",
      "failed",
      "deleting",
      "deleted",
    ].includes(d.status) ||
    typeof d.index_status !== "string" ||
    !Number.isInteger(d.chunk_count)
  )
    throw new Error("Invalid document response");
  return {
    id: d.id,
    filename: d.filename,
    content_type: d.content_type,
    size_bytes: d.size_bytes,
    checksum: d.checksum,
    status: d.status,
    index_status: d.index_status,
    page_count: d.page_count,
    chunk_count: d.chunk_count,
    embedding_model: d.embedding_model,
    error_code: d.error_code,
    uploaded_at: d.uploaded_at,
  };
}
export async function documentRequest(
  path = "",
  action?: string,
  signal?: AbortSignal,
): Promise<unknown> {
  const response = await fetch(
    `/api/documents${path}`,
    action
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
          signal: signal
            ? AbortSignal.any([signal, AbortSignal.timeout(12000)])
            : AbortSignal.timeout(12000),
        }
      : {
          cache: "no-store",
          signal: signal
            ? AbortSignal.any([signal, AbortSignal.timeout(12000)])
            : AbortSignal.timeout(12000),
        },
  );
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? "Document request failed");
  return data;
}
