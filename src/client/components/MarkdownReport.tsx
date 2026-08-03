import { ReactNode, useMemo } from "react";
import { TermTooltip } from "./TermTooltip";
import { TERMINOLOGY_INDEX, TERMINOLOGY_PATTERN } from "../lib/terminology";

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "quote"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; headers: string[]; rows: string[][] }
  | { type: "code"; text: string };

export function MarkdownReport({ content }: { content: string }) {
  const blocks = useMemo(() => parseMarkdown(content), [content]);
  return (
    <div>
      {blocks.map((block, index) => (
        <MarkdownBlockView key={index} block={block} />
      ))}
    </div>
  );
}

function MarkdownBlockView({ block }: { block: MarkdownBlock }) {
  if (block.type === "heading") {
    const level = Math.min(Math.max(block.level, 2), 4);
    const Tag = `h${level}` as "h2" | "h3" | "h4";
    const className =
      level === 2
        ? "my-3 mt-6 text-lg font-semibold tracking-normal text-gold-dim"
        : level === 3
          ? "my-2.5 mt-5 text-base font-semibold tracking-normal text-ink"
          : "my-2 mt-4 text-sm font-semibold tracking-normal text-ink";
    return <Tag className={className}>{renderInline(block.text)}</Tag>;
  }
  if (block.type === "quote") {
    return (
      <blockquote className="my-3.5 rounded-r border-l-[3px] border-gold bg-gold/10 px-4 py-3 text-[13px] leading-[1.8] text-body">
        {renderInline(block.text)}
      </blockquote>
    );
  }
  if (block.type === "list") {
    return (
      <ul className="my-3.5 list-disc pl-5">
        {block.items.map((item, index) => (
          <li key={index} className="text-sm leading-[1.85] text-body marker:text-gold">
            {renderInline(item)}
          </li>
        ))}
      </ul>
    );
  }
  if (block.type === "table") {
    return (
      <div
        className="my-4 overflow-x-auto rounded-md border border-gold/25 bg-cream-2"
        role="region"
        tabIndex={0}
        aria-label="Report table"
      >
        <table className="min-w-full border-collapse text-left text-[12.5px] text-body">
          <thead className="bg-gold/10 text-[11px] uppercase tracking-[0.08em] text-gold-dim">
            <tr>
              {block.headers.map((cell, index) => (
                <th key={index} className="border-b border-gold/20 px-3 py-2.5 font-semibold">
                  {renderInline(cell)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="even:bg-cream/60">
                {block.headers.map((_, cellIndex) => (
                  <td
                    key={cellIndex}
                    className="border-b border-gold/15 px-3 py-2.5 align-top last:border-0"
                  >
                    {renderInline(row[cellIndex] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (block.type === "code") {
    return (
      <pre className="my-3.5 overflow-x-auto whitespace-pre rounded-md border border-gold/25 bg-cream-2 p-3 font-mono text-[12.5px] text-body">
        {block.text}
      </pre>
    );
  }
  return <p className="my-2.5 text-sm leading-[1.9] text-body">{renderInline(block.text)}</p>;
}

function parseMarkdown(content: string): MarkdownBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      index += 1;
      const code: string[] = [];
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push({ type: "code", text: code.join("\n") });
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length + 1, text: heading[2] });
      index += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quote: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quote.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "quote", text: quote.join(" ") });
      continue;
    }

    if (isTableLine(trimmed)) {
      const table: string[] = [];
      while (index < lines.length && isTableLine(lines[index].trim())) {
        table.push(lines[index]);
        index += 1;
      }
      const parsedTable = parseTable(table);
      if (parsedTable) {
        blocks.push(parsedTable);
      } else {
        blocks.push({ type: "paragraph", text: table.join(" ") });
      }
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith("```") &&
      !lines[index].trim().startsWith(">") &&
      !lines[index].trim().match(/^(#{1,4})\s+/) &&
      !/^[-*]\s+/.test(lines[index].trim()) &&
      !isTableLine(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

function isTableLine(line: string) {
  return line.includes("|") && line.split("|").length >= 3;
}

function parseTable(lines: string[]): Extract<MarkdownBlock, { type: "table" }> | null {
  if (lines.length < 2) return null;
  const rows = lines.map(parseTableCells);
  const separatorIndex = rows.findIndex((row) => row.length > 0 && row.every(isTableSeparator));
  if (separatorIndex !== 1 || rows[0].length === 0) return null;
  const width = rows[0].length;
  return {
    type: "table",
    headers: rows[0],
    rows: rows
      .slice(2)
      .map((row) => [...row, ...Array(Math.max(0, width - row.length)).fill("")].slice(0, width))
  };
}

function parseTableCells(line: string) {
  const source = line.replace(/^\s*\|/, "").replace(/\|\s*$/, "");
  const cells: string[] = [];
  let cell = "";
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === "\\" && source[index + 1] === "|") {
      cell += "|";
      index += 1;
    } else if (character === "|") {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += character;
    }
  }
  cells.push(cell.trim());
  return cells;
}

function isTableSeparator(cell: string) {
  return /^:?-{3,}:?$/.test(cell);
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={index}
          className="rounded bg-cream-3 px-1.5 py-0.5 font-mono text-[0.88em] text-gold-dim"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**"))
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    return <span key={index}>{renderTerms(part, `t${index}`)}</span>;
  });
}

/** Wraps known Jyotish terms inside a plain-text run with a wiki-card popover. */
function renderTerms(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let matchCount = 0;
  for (const match of text.matchAll(TERMINOLOGY_PATTERN)) {
    const matched = match[0];
    const start = match.index ?? 0;
    if (start > lastIndex) {
      nodes.push(text.slice(lastIndex, start));
    }
    const term = TERMINOLOGY_INDEX.get(matched);
    if (term) {
      nodes.push(
        <TermTooltip key={`${keyPrefix}-${matchCount}`} term={term}>
          {matched}
        </TermTooltip>
      );
    } else {
      nodes.push(matched);
    }
    lastIndex = start + matched.length;
    matchCount += 1;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes.length > 0 ? nodes : [text];
}
