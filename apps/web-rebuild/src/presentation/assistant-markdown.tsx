"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; text: string }
  | { type: "table"; headers: string[]; rows: string[][] };

export function AssistantMarkdown({ text, id, streaming = false }: { text: string; id: string; streaming?: boolean }) {
  const blocks = parseMarkdown(text);
  if (!blocks.length) return null;
  return (
    <div className={`assistant-copy${streaming ? " is-streaming" : ""}`}>
      {blocks.map((block, index) => (
        <BlockView key={`${id}-${index}`} block={block} />
      ))}
    </div>
  );
}

function BlockView({ block }: { block: Block }) {
  if (block.type === "heading") {
    if (block.level <= 1) return <h2><Inline text={block.text} /></h2>;
    return <h3><Inline text={block.text} /></h3>;
  }
  if (block.type === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    return (
      <Tag>
        {block.items.map((item, index) => (
          <li key={index}><Inline text={item} /></li>
        ))}
      </Tag>
    );
  }
  if (block.type === "code") return <CodeBlock text={block.text} />;
  if (block.type === "table") {
    return (
      <div className="assistant-table" style={{ ["--columns" as string]: String(Math.max(block.headers.length, 1)) }}>
        <div>{block.headers.map((header, index) => <b key={index}><Inline text={header} /></b>)}</div>
        {block.rows.map((row, rowIndex) => (
          <div key={rowIndex}>
            {block.headers.map((_, cellIndex) => <span key={cellIndex}><Inline text={row[cellIndex] ?? ""} /></span>)}
          </div>
        ))}
      </div>
    );
  }
  return <p><Inline text={block.text} /></p>;
}

function CodeBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="code-block">
      <button
        type="button"
        aria-label={copied ? "Copied code" : "Copy code"}
        onClick={() => {
          void navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          }).catch(() => setCopied(false));
        }}
      >
        {copied ? <Check size={13} /> : <Copy size={13} />}
        {copied ? "Copied" : "Copy"}
      </button>
      <pre><code>{text}</code></pre>
    </div>
  );
}

function Inline({ text }: { text: string }) {
  return tokenize(text).map((part, index) => {
    if (part.kind === "code") return <code key={index}>{part.text}</code>;
    if (part.kind === "bold") return <strong key={index}>{part.text}</strong>;
    if (part.kind === "link") {
      return <a key={index} href={part.href} target="_blank" rel="noreferrer">{part.text}</a>;
    }
    return <span key={index}>{part.text}</span>;
  });
}

type Token =
  | { kind: "text" | "code" | "bold"; text: string }
  | { kind: "link"; text: string; href: string };

function tokenize(text: string): Token[] {
  const parts: Token[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: "text", text: text.slice(last, start) });
    const token = match[0];
    if (token.startsWith("`")) parts.push({ kind: "code", text: token.slice(1, -1) });
    else if (token.startsWith("**")) parts.push({ kind: "bold", text: token.slice(2, -2) });
    else {
      const parsed = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(token);
      if (parsed) parts.push({ kind: "link", text: parsed[1], href: parsed[2] });
    }
    last = start + token.length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}

function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (line.trim() === "") {
      index += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const collected: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? "").startsWith("```")) {
        collected.push(lines[index] ?? "");
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: "code", text: collected.join("\n") });
      continue;
    }
    if (isTableStart(lines, index)) {
      const headers = splitRow(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && (lines[index] ?? "").includes("|")) {
        rows.push(splitRow(lines[index] ?? ""));
        index += 1;
      }
      blocks.push({ type: "table", headers, rows });
      continue;
    }
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1]?.length ?? 2, text: heading[2] ?? "" });
      index += 1;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index] ?? "")) {
        items.push((lines[index] ?? "").replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push({ type: "list", ordered: false, items });
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index] ?? "")) {
        items.push((lines[index] ?? "").replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push({ type: "list", ordered: true, items });
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length && keepParagraph(lines[index] ?? "")) {
      paragraph.push(lines[index] ?? "");
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join("\n") });
  }
  return blocks;
}

function keepParagraph(line: string): boolean {
  return line.trim() !== "" && !line.startsWith("```") && !/^(#{1,3})\s+/.test(line) && !/^[-*]\s+/.test(line) && !/^\d+\.\s+/.test(line);
}

function isTableStart(lines: string[], index: number): boolean {
  const current = lines[index] ?? "";
  const separator = lines[index + 1] ?? "";
  return current.includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(separator);
}

function splitRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}
