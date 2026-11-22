type Block =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; text: string }
  | { type: "table"; headers: string[]; rows: string[][] };

export function RichText({ text, id, lead = false }: { text: string; id: string; lead?: boolean }) {
  const blocks = parseMarkdown(text);
  return (
    <div className="space-y-3 leading-7">
      {blocks.map((block, index) => (
        <BlockView key={`${id}-${index}`} block={block} lead={lead && index === 0} />
      ))}
    </div>
  );
}

function BlockView({ block, lead = false }: { block: Block; lead?: boolean }) {
  if (block.type === "heading") {
    const className = lead
      ? "text-[22px] font-normal leading-snug text-foreground"
      : block.level === 1
        ? "text-lg font-semibold"
        : "text-base font-semibold";
    if (block.level === 1) {
      return <h2 className={className}><Inline text={block.text} /></h2>;
    }
    return <h3 className={className}><Inline text={block.text} /></h3>;
  }
  if (block.type === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    const className = block.ordered ? "list-decimal space-y-1 pl-5" : "list-disc space-y-1 pl-5";
    return (
      <Tag className={className}>
        {block.items.map((item, index) => (
          <li key={index}>
            <Inline text={item} />
          </li>
        ))}
      </Tag>
    );
  }
  if (block.type === "code") {
    return (
      <pre className="overflow-x-auto rounded-md border border-border bg-card p-3 text-xs leading-5">
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.type === "table") {
    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr>
              {block.headers.map((header, index) => (
                <th key={index} className="border border-border px-2 py-1 font-medium">
                  <Inline text={header} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="border border-border px-2 py-1">
                    <Inline text={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <p className={lead ? "whitespace-pre-wrap text-[22px] leading-snug text-foreground" : "whitespace-pre-wrap"}>
      <Inline text={block.text} />
    </p>
  );
}

function Inline({ text }: { text: string }) {
  const parts = tokenize(text);
  return parts.map((part, index) => {
    if (part.kind === "code") {
      return (
        <code key={index} className="rounded bg-secondary px-1">
          {part.text}
        </code>
      );
    }
    if (part.kind === "bold") {
      return <strong key={index}>{part.text}</strong>;
    }
    return <span key={index}>{part.text}</span>;
  });
}

function tokenize(text: string): { kind: "text" | "code" | "bold"; text: string }[] {
  const parts: { kind: "text" | "code" | "bold"; text: string }[] = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) {
      parts.push({ kind: "text", text: text.slice(last, start) });
    }
    const token = match[0];
    if (token.startsWith("`")) {
      parts.push({ kind: "code", text: token.slice(1, -1) });
    } else {
      parts.push({ kind: "bold", text: token.slice(2, -2) });
    }
    last = start + token.length;
  }
  if (last < text.length) {
    parts.push({ kind: "text", text: text.slice(last) });
  }
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
      if (index < lines.length) {
        index += 1;
      }
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
  return (
    line.trim() !== "" &&
    !line.startsWith("```") &&
    !/^(#{1,3})\s+/.test(line) &&
    !/^[-*]\s+/.test(line) &&
    !/^\d+\.\s+/.test(line)
  );
}

function isTableStart(lines: string[], index: number): boolean {
  const current = lines[index] ?? "";
  const separator = lines[index + 1] ?? "";
  return current.includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(separator);
}

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}
