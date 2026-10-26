"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { documentRequest, type UploadedDocument } from "../lib/documents";
import { useDocuments } from "../lib/use-documents";
import { Icon } from "./icons";

function friendlyStatus(document: UploadedDocument) {
  if (document.status === "ready") return "Ready to research";
  if (document.status === "queued") return "Preparing document";
  if (document.status === "processing") return "Indexing document";
  if (document.status === "deleting") return "Removing document";
  if (document.status === "deleted") return "Removed";
  return "Could not process document";
}

function friendlyFailure(code: string | null) {
  if (!code)
    return "The file could not be prepared. Check that it is a readable PDF, DOCX, TXT, or Markdown file.";
  if (code.includes("unsupported") || code.includes("format"))
    return "This file type is not supported. Use a PDF, DOCX, TXT, or Markdown file.";
  if (code.includes("empty") || code.includes("text"))
    return "No readable text was found in this file. Scanned PDFs need OCR, which is not available here.";
  return "The file could not be prepared. You can try reindexing it or upload another copy.";
}

function extension(filename: string) {
  return filename.split(".").pop()?.slice(0, 4) || "FILE";
}

export function DocumentWorkspace({
  selected,
  onSelection,
}: {
  selected?: string[];
  onSelection?: (ids: string[]) => void;
} = {}) {
  const {
    documents,
    loading,
    error: listError,
    setError,
    refresh,
  } = useDocuments();
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [query, setQuery] = useState("");
  const [busyId, setBusyId] = useState("");
  const [confirmId, setConfirmId] = useState("");
  const [confirmAction, setConfirmAction] = useState<"delete" | "reindex">(
    "delete",
  );
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLDialogElement>(null);
  const selectedDocument = documents.find(
    (document) => document.id === confirmId,
  );
  const visible = documents.filter((document) =>
    document.filename
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );

  function openConfirmation(id: string, action: "delete" | "reindex") {
    setConfirmId(id);
    setConfirmAction(action);
    window.setTimeout(() => {
      if (confirmRef.current?.showModal) confirmRef.current.showModal();
      else confirmRef.current?.setAttribute("open", "");
    }, 0);
  }

  function closeConfirmation() {
    if (confirmRef.current?.close) confirmRef.current.close();
    else confirmRef.current?.removeAttribute("open");
  }

  function upload(file?: File) {
    if (!file) return;
    if (file.size > 5_000_000) {
      setUploadError(
        "This file is larger than 5 MB. Choose a smaller document.",
      );
      return;
    }
    if (!/\.(pdf|docx|txt|md)$/i.test(file.name)) {
      setUploadError("Choose a PDF, DOCX, TXT, or Markdown file.");
      return;
    }
    setUploadError("");
    setError("");
    setUploadProgress(0);
    const request = new XMLHttpRequest();
    request.open("POST", "/api/documents/upload");
    request.timeout = 35_000;
    request.setRequestHeader("Content-Type", "application/octet-stream");
    request.setRequestHeader("X-Filename", encodeURIComponent(file.name));
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        setUploadProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      setUploadProgress(null);
      if (request.status >= 400) {
        try {
          const response = JSON.parse(request.responseText) as {
            error?: string;
          };
          setUploadError(
            response.error ??
              "The upload did not complete. Refresh your library before trying again.",
          );
        } catch {
          setUploadError(
            "The upload did not complete. Refresh your library before trying again.",
          );
        }
      } else {
        setUploadError("");
      }
      void refresh();
    };
    request.onerror = request.ontimeout = () => {
      setUploadProgress(null);
      setUploadError(
        "We could not confirm the upload. Refresh your library before trying again.",
      );
    };
    request.send(file);
  }

  async function perform(action: "delete" | "reindex") {
    if (!confirmId) return;
    setBusyId(confirmId);
    setUploadError("");
    try {
      await documentRequest(`/${confirmId}/${action}`, action);
      closeConfirmation();
      setConfirmId("");
      await refresh();
    } catch (failure) {
      setUploadError(
        failure instanceof Error
          ? failure.message
          : "The document action could not be confirmed. Refresh and check its status.",
      );
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="library-page" aria-labelledby="library-title">
      <div className="page-header">
        <div>
          <span className="eyebrow">Your research files</span>
          <h1 className="page-title" id="library-title">
            Library
          </h1>
          <p className="page-intro">
            Keep the documents you want to ask questions about close at hand.
            Files are stored in this local workspace.
          </p>
        </div>
        <Link className="button button-primary" href="/">
          <Icon name="plus" size={17} /> New research
        </Link>
      </div>

      <div
        className={`drop-zone${dragging ? " is-dragging" : ""}`}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null))
            setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          upload(event.dataTransfer.files[0]);
        }}
      >
        <div className="empty-icon">
          <Icon name="upload" />
        </div>
        <h2>Bring your documents into the conversation</h2>
        <p>
          Drop files here or choose from your Mac. PDF, DOCX, TXT, and Markdown
          · up to 5 MB each.
        </p>
        <button
          className="button button-secondary"
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploadProgress !== null}
        >
          Choose files <Icon name="arrow" size={15} />
        </button>
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept=".pdf,.docx,.txt,.md"
          aria-label="Choose a document to upload"
          disabled={uploadProgress !== null}
          onChange={(event) => {
            upload(event.currentTarget.files?.[0]);
            event.currentTarget.value = "";
          }}
        />
        {uploadProgress !== null && (
          <div
            className="upload-progress"
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={uploadProgress}
          >
            <span style={{ width: `${Math.max(5, uploadProgress)}%` }} />
          </div>
        )}
        {uploadProgress !== null && (
          <p role="status" className="small-copy">
            Uploading your file · {uploadProgress}%
          </p>
        )}
      </div>
      {(uploadError || listError) && (
        <p className="error-banner" role="alert">
          {uploadError || listError}
        </p>
      )}

      <div className="library-toolbar">
        <div>
          <h2 className="section-title">
            Your documents
            {!loading && (
              <span className="count-label">
                {" "}
                ·{" "}
                {
                  documents.filter((document) => document.status !== "deleted")
                    .length
                }
              </span>
            )}
          </h2>
          <p className="small-copy">
            Documents are searchable after their status reads “Ready to
            research.”
          </p>
        </div>
        <label className="search-field">
          <Icon name="search" size={17} />
          <span className="visually-hidden">Search your documents</span>
          <input
            className="search-input"
            type="search"
            placeholder="Find a document"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      {loading && (
        <div
          className="document-list"
          aria-busy="true"
          aria-label="Loading documents"
        >
          <div className="card document-row skeleton" />
          <div className="card document-row skeleton" />
        </div>
      )}
      {!loading &&
        documents.filter((document) => document.status !== "deleted").length ===
          0 && (
          <div className="card empty-state">
            <div className="empty-icon">
              <Icon name="library" />
            </div>
            <h2>Your library is waiting</h2>
            <p>
              Upload a document to ask questions, compare findings, and review
              the source passages in your research.
            </p>
            <button
              className="button button-primary"
              type="button"
              onClick={() => inputRef.current?.click()}
            >
              Upload your first document <Icon name="upload" size={16} />
            </button>
          </div>
        )}
      {!loading &&
        documents.filter((document) => document.status !== "deleted").length >
          0 &&
        visible.length === 0 && (
          <div className="card empty-state">
            <div className="empty-icon">
              <Icon name="search" />
            </div>
            <h2>No matching documents</h2>
            <p>Try another filename or clear the search field.</p>
            <button
              className="button button-secondary"
              type="button"
              onClick={() => setQuery("")}
            >
              Clear search
            </button>
          </div>
        )}
      {!loading &&
        visible.filter((document) => document.status !== "deleted").length >
          0 && (
          <div className="document-list">
            {visible
              .filter((document) => document.status !== "deleted")
              .map((document) => (
                <article className="card document-row" key={document.id}>
                  {selected && onSelection && document.status === "ready" && (
                    <label className="document-select">
                      <input
                        type="checkbox"
                        aria-label={`Select ${document.filename}`}
                        checked={selected.includes(document.id)}
                        onChange={(event) =>
                          onSelection(
                            event.target.checked
                              ? [...selected, document.id]
                              : selected.filter((id) => id !== document.id),
                          )
                        }
                      />
                      <span className="visually-hidden">
                        Select {document.filename}
                      </span>
                    </label>
                  )}
                  <div className="document-type-icon" aria-hidden="true">
                    {extension(document.filename)}
                  </div>
                  <div className="document-main">
                    <h2 title={document.filename}>{document.filename}</h2>
                    <div className="document-meta">
                      <span className={`status-pill status-${document.status}`}>
                        {friendlyStatus(document)}
                      </span>
                      <span>{(document.size_bytes / 1024).toFixed(0)} KB</span>
                      {document.page_count ? (
                        <span>{document.page_count} pages</span>
                      ) : null}
                      <span>
                        Added{" "}
                        {new Date(document.uploaded_at).toLocaleDateString(
                          undefined,
                          { month: "short", day: "numeric", year: "numeric" },
                        )}
                      </span>
                    </div>
                    {document.status === "failed" && (
                      <p className="file-error">
                        {friendlyFailure(document.error_code)}
                      </p>
                    )}
                    {document.status === "ready" && (
                      <details className="document-advanced">
                        <summary>Document details</summary>
                        <p>
                          {document.chunk_count} searchable passages. Pages are
                          shown in citations when the file provides page
                          structure.
                        </p>
                        <dl>
                          <dt>File type</dt>
                          <dd>{document.content_type}</dd>
                          <dt>Embedding model</dt>
                          <dd>{document.embedding_model ?? "Not available"}</dd>
                          <dt>Document reference</dt>
                          <dd>{document.id}</dd>
                        </dl>
                      </details>
                    )}
                  </div>
                  <div className="document-row-actions">
                    {document.status === "ready" && (
                      <Link
                        className="row-action"
                        href={`/?document=${encodeURIComponent(document.id)}`}
                      >
                        Use in research
                      </Link>
                    )}
                    {document.status === "failed" && (
                      <button
                        className="row-action"
                        type="button"
                        disabled={Boolean(busyId)}
                        onClick={() => openConfirmation(document.id, "reindex")}
                      >
                        Try again
                      </button>
                    )}
                    {document.status === "ready" && (
                      <button
                        className="row-action"
                        type="button"
                        disabled={Boolean(busyId)}
                        onClick={() => openConfirmation(document.id, "reindex")}
                      >
                        Reindex
                      </button>
                    )}
                    {!["queued", "processing", "deleting"].includes(
                      document.status,
                    ) && (
                      <button
                        className="row-action delete"
                        type="button"
                        disabled={Boolean(busyId)}
                        onClick={() => openConfirmation(document.id, "delete")}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </article>
              ))}
          </div>
        )}

      <p className="library-note">
        <Icon name="check" size={15} /> Selecting files is always explicit. A
        research session uses only the documents you choose.
      </p>

      <dialog
        ref={confirmRef}
        className="confirm-dialog"
        aria-labelledby="confirm-title"
      >
        <div className="dialog-content">
          <div className="dialog-head">
            <div>
              <h2 id="confirm-title">
                {confirmAction === "reindex"
                  ? "Reindex this document?"
                  : "Remove this document?"}
              </h2>
              <p>{selectedDocument?.filename}</p>
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="Close dialog"
              onClick={closeConfirmation}
            >
              <Icon name="close" />
            </button>
          </div>
          <p className="small-copy">
            {confirmAction === "reindex"
              ? "The current index will be refreshed using the configured embedding model. Existing research reports keep their saved evidence excerpts."
              : "The file and its searchable passages will be removed. Previously completed reports keep their saved evidence excerpts."}
          </p>
          {uploadError && (
            <p className="file-error" role="alert">
              {uploadError}
            </p>
          )}
          <div className="dialog-actions">
            <button
              className="button button-secondary"
              type="button"
              onClick={closeConfirmation}
              disabled={Boolean(busyId)}
            >
              Keep document
            </button>
            <button
              className="button button-danger"
              type="button"
              disabled={Boolean(busyId)}
              onClick={() => void perform(confirmAction)}
            >
              {busyId
                ? "Working…"
                : confirmAction === "reindex"
                  ? "Reindex document"
                  : "Remove document"}
            </button>
          </div>
        </div>
      </dialog>
    </section>
  );
}
