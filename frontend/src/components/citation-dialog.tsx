"use client";

import { useEffect, useRef } from "react";
import type { ResearchRun } from "../lib/runs";
import { Icon } from "./icons";

export type ResearchSource = ResearchRun["sources"][number];

export function CitationDialog({
  source,
  onClose,
}: {
  source: ResearchSource | null;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (source && dialog.current && !dialog.current.open)
      dialog.current.showModal();
  }, [source]);

  return (
    <dialog
      className="citation-dialog"
      ref={dialog}
      aria-labelledby="citation-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialog.current) dialog.current.close();
      }}
    >
      {source && (
        <div className="dialog-content">
          <div className="dialog-head">
            <div>
              <span className="eyebrow">
                Evidence source · {source.source_id}
              </span>
              <h2 className="citation-title" id="citation-title">
                {source.title}
              </h2>
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="Close source details"
              onClick={() => dialog.current?.close()}
            >
              <Icon name="close" />
            </button>
          </div>
          <div className="citation-meta">
            <span>
              {source.source_type === "document"
                ? "Your document"
                : source.source_type === "mock"
                  ? "Demo source"
                  : "Web source"}
            </span>
            {source.source_type === "document" && (
              <span>
                {source.page ? `Page ${source.page}` : "Page not available"}
              </span>
            )}
            {source.published_at && (
              <span>
                Published {new Date(source.published_at).toLocaleDateString()}
              </span>
            )}
            <span>
              Retrieved {new Date(source.retrieved_at).toLocaleDateString()}
            </span>
          </div>
          {source.excerpt ? (
            <blockquote className="citation-excerpt">
              {source.excerpt}
            </blockquote>
          ) : (
            <p className="info-banner">
              The saved session refers to this source, but its passage is no
              longer available.
            </p>
          )}
          {source.source_type === "web" && /^https?:\/\//i.test(source.url) && (
            <a
              className="citation-link"
              href={source.url}
              target="_blank"
              rel="noreferrer noopener"
            >
              Open original source <Icon name="external" size={15} />
            </a>
          )}
          {source.source_type === "mock" && (
            <p className="small-copy">
              This is a synthetic demonstration source. It is not a real
              publication.
            </p>
          )}
          <details className="citation-advanced">
            <summary>Source details</summary>
            <dl>
              {source.document_id && (
                <>
                  <dt>Document reference</dt>
                  <dd>{source.document_id}</dd>
                </>
              )}
              {source.chunk_id && (
                <>
                  <dt>Passage reference</dt>
                  <dd>{source.chunk_id}</dd>
                </>
              )}
              {source.source_type === "web" && (
                <>
                  <dt>Source address</dt>
                  <dd>{source.url}</dd>
                </>
              )}
            </dl>
          </details>
        </div>
      )}
    </dialog>
  );
}
