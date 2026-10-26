import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { MarkdownReport } from "../src/components/markdown-report";
import type { ResearchSource } from "../src/components/citation-dialog";

const source: ResearchSource = {
  source_id: "S1",
  source_type: "document",
  document_id: "b3de8d8d-6020-43b5-9983-d8c1af2fcb49",
  chunk_id: "a5e6a712-7913-4b14-9f14-f3c0460e1ed1",
  page: 2,
  title: "Juniper pilot handbook",
  url: "http://127.0.0.1:3000/#document",
  excerpt: "The Juniper battery stores 20 kWh.",
  retrieved_at: "2026-10-20T10:00:00Z",
  published_at: null,
};

test("report citations open their saved source and unsafe or unknown links stay inert", () => {
  const onCitation = vi.fn();
  render(
    <MarkdownReport
      markdown="The battery stores 20 kWh [S1]. Unknown [S2]. [unsafe](javascript:alert(1)) [safe](https://example.org/source)."
      sources={[source]}
      onCitation={onCitation}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Open S1 source" }));
  expect(onCitation).toHaveBeenCalledWith(source);
  expect(screen.getByText("[S2]")).toHaveClass("citation-missing");
  expect(
    screen.queryByRole("link", { name: "unsafe" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "safe" })).toHaveAttribute(
    "href",
    "https://example.org/source",
  );
});
