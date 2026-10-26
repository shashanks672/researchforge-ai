import type { ResearchSource } from "./citation-dialog";

function unescapeMarkdown(value: string) {
  return value.replace(/\\([!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])/g, "$1");
}

function isSafeDestination(destination: string) {
  try {
    return (
      ["https:", "http:", "mailto:"].includes(
        new URL(destination, "https://local.invalid").protocol,
      ) && !destination.startsWith("//")
    );
  } catch {
    return false;
  }
}

function Inline({
  text,
  sources,
  onCitation,
}: {
  text: string;
  sources: ResearchSource[];
  onCitation: (source: ResearchSource) => void;
}) {
  const normalized = unescapeMarkdown(text);
  const token =
    /(\[S\d+\]|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`)/g;
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const match of normalized.matchAll(token)) {
    const index = match.index ?? 0;
    if (index > cursor) parts.push(normalized.slice(cursor, index));
    const value = match[0];
    if (/^\[S\d+\]$/.test(value)) {
      const source = sources.find(
        (item) => item.source_id === value.slice(1, -1),
      );
      parts.push(
        source ? (
          <button
            className="citation-marker"
            type="button"
            key={`${index}-citation`}
            aria-label={`Open ${value.slice(1, -1)} source`}
            onClick={() => onCitation(source)}
          >
            {value}
          </button>
        ) : (
          <span
            className="citation-missing"
            key={`${index}-citation`}
            title="This source is not available in the saved evidence"
          >
            {value}
          </span>
        ),
      );
    } else if (match[2] && match[3]) {
      const destination = match[3].trim();
      const safe = isSafeDestination(destination);
      parts.push(
        safe ? (
          <a
            href={destination}
            key={`${index}-link`}
            target={destination.startsWith("http") ? "_blank" : undefined}
            rel={
              destination.startsWith("http") ? "noreferrer noopener" : undefined
            }
          >
            {match[2]}
          </a>
        ) : (
          <span key={`${index}-link`}>{match[2]}</span>
        ),
      );
    } else if (match[4])
      parts.push(<strong key={`${index}-strong`}>{match[4]}</strong>);
    else if (match[5]) parts.push(<em key={`${index}-em`}>{match[5]}</em>);
    else if (match[6])
      parts.push(<code key={`${index}-code`}>{match[6]}</code>);
    cursor = index + value.length;
  }
  if (cursor < normalized.length) parts.push(normalized.slice(cursor));
  return <>{parts}</>;
}

function isTableDivider(line: string) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function cells(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function startsBlock(lines: string[], index: number) {
  const line = lines[index] ?? "";
  return (
    !line.trim() ||
    /^#{1,6}\s/.test(line) ||
    /^```/.test(line) ||
    /^\s*[-*+]\s+/.test(line) ||
    /^\s*\d+[.)]\s+/.test(line) ||
    /^>/.test(line) ||
    (index + 1 < lines.length && isTableDivider(lines[index + 1]))
  );
}

export function MarkdownReport({
  markdown,
  sources,
  onCitation,
}: {
  markdown: string;
  sources: ResearchSource[];
  onCitation: (source: ResearchSource) => void;
}) {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (/^```/.test(line)) {
      const language = line.slice(3).trim();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index] ?? ""))
        code.push(lines[index++] ?? "");
      index += 1;
      blocks.push(
        <pre key={`code-${index}`}>
          <code
            className={
              language
                ? `language-${language.replace(/[^\w-]/g, "")}`
                : undefined
            }
          >
            {code.join("\n")}
          </code>
        </pre>,
      );
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = Math.min(4, heading[1]?.length ?? 2);
      const content = (
        <Inline
          text={heading[2] ?? ""}
          sources={sources}
          onCitation={onCitation}
        />
      );
      const key = `heading-${index++}`;
      if (level === 1) blocks.push(<h1 key={key}>{content}</h1>);
      else if (level === 2) blocks.push(<h2 key={key}>{content}</h2>);
      else if (level === 3) blocks.push(<h3 key={key}>{content}</h3>);
      else blocks.push(<h4 key={key}>{content}</h4>);
      continue;
    }
    if (index + 1 < lines.length && isTableDivider(lines[index + 1] ?? "")) {
      const headers = cells(line);
      index += 2;
      const rows: string[][] = [];
      while (
        index < lines.length &&
        (lines[index] ?? "").trim() &&
        (lines[index] ?? "").includes("|")
      )
        rows.push(cells(lines[index++] ?? ""));
      blocks.push(
        <div
          className="report-table-wrap"
          role="region"
          aria-label="Report table"
          tabIndex={0}
          key={`table-${index}`}
        >
          <table>
            <thead>
              <tr>
                {headers.map((cell, cellIndex) => (
                  <th key={cellIndex}>
                    <Inline
                      text={cell}
                      sources={sources}
                      onCitation={onCitation}
                    />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {headers.map((_, cellIndex) => (
                    <td key={cellIndex}>
                      <Inline
                        text={row[cellIndex] ?? ""}
                        sources={sources}
                        onCitation={onCitation}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index] ?? ""))
        items.push((lines[index++] ?? "").replace(/^\s*[-*+]\s+/, ""));
      blocks.push(
        <ul key={`list-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>
              <Inline text={item} sources={sources} onCitation={onCitation} />
            </li>
          ))}
        </ul>,
      );
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index] ?? ""))
        items.push((lines[index++] ?? "").replace(/^\s*\d+[.)]\s+/, ""));
      blocks.push(
        <ol key={`ordered-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>
              <Inline text={item} sources={sources} onCitation={onCitation} />
            </li>
          ))}
        </ol>,
      );
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quotes: string[] = [];
      while (index < lines.length && /^>/.test(lines[index] ?? ""))
        quotes.push((lines[index++] ?? "").replace(/^>\s?/, ""));
      blocks.push(
        <blockquote key={`quote-${index}`}>
          <p>
            <Inline
              text={quotes.join(" ")}
              sources={sources}
              onCitation={onCitation}
            />
          </p>
        </blockquote>,
      );
      continue;
    }
    const paragraph = [line];
    index += 1;
    while (index < lines.length && !startsBlock(lines, index))
      paragraph.push(lines[index++] ?? "");
    blocks.push(
      <p key={`paragraph-${index}`}>
        <Inline
          text={paragraph.join(" ")}
          sources={sources}
          onCitation={onCitation}
        />
      </p>,
    );
  }
  return <div className="report-body">{blocks}</div>;
}
