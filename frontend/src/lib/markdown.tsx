import { createElement, type ReactNode } from "react";

/**
 * A small Markdown renderer for chat replies: headings, paragraphs, bullet and numbered lists,
 * fenced code, inline code, bold, italic and links. It is not a full Markdown implementation, and it
 * is written to be safe for text nobody has vouched for:
 *
 * - It builds React elements. Nothing is ever turned into an HTML string, so raw HTML in the text
 *   (`<script>`, `<img onerror=...>`) is shown as plain characters.
 * - Only `http:` and `https:` links are clickable. Anything else (`javascript:`, `data:`, relative
 *   addresses) is shown as its label with no link.
 * - Headings are re-levelled, because the page already owns the `h1`: the shallowest heading in a
 *   reply becomes an `h2`, the others keep their depth relative to it, and none skips a level (so
 *   `##` then `####` gives an `h2` then an `h3`).
 *
 * It also copes with text that is still arriving: with `partial`, an emphasis or code span that has
 * not been closed yet is closed for display, and half of a link is not shown, so the picture does not
 * flicker between raw markers and styled text.
 */

export interface MarkdownOptions {
  /** The text is still arriving. */
  partial?: boolean;
  /**
   * Links become plain text and code blocks are not focusable. Used for text that is hidden from
   * assistive technology while it animates, where nothing focusable may live.
   */
  inert?: boolean;
}

type Block =
  | { kind: "code"; text: string }
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "paragraph"; lines: string[] };

const FENCE = /^\s{0,3}(`{3,}|~{3,})\s*[\w+#.-]*\s*$/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const BULLET = /^\s{0,3}[-*+]\s+(.*)$/;
const NUMBERED = /^\s{0,3}\d{1,9}[.)]\s+(.*)$/;

function startsBlock(line: string): boolean {
  return FENCE.test(line) || HEADING.test(line) || BULLET.test(line) || NUMBERED.test(line);
}

/** In a half-written text, drop what is only the start of a construct: a bare `#`, `-` or `1.`. */
function trimDanglingLine(lines: string[]): string[] {
  const last = lines[lines.length - 1];
  if (last !== undefined && /^\s*(#{1,6}|[-*+]|\d{1,9}[.)])\s*$/.test(last)) {
    return lines.slice(0, -1);
  }
  return lines;
}

function parseBlocks(source: string, partial: boolean): Block[] {
  let lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  if (partial) {
    // A fence still open at the end is fine (the code so far is shown). Anything else dangling goes.
    const fences = lines.filter((line) => FENCE.test(line)).length;
    if (fences % 2 === 0) {
      lines = trimDanglingLine(lines);
    }
  }
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    const fence = FENCE.exec(line);
    if (fence !== null) {
      const marker = fence[1] ?? "```";
      const body: string[] = [];
      i += 1;
      while (i < lines.length) {
        const current = lines[i] ?? "";
        const closes = new RegExp(`^\\s{0,3}${marker[0] === "~" ? "~" : "`"}{${marker.length},}\\s*$`);
        if (closes.test(current)) {
          i += 1;
          break;
        }
        body.push(current);
        i += 1;
      }
      blocks.push({ kind: "code", text: body.join("\n") });
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading !== null) {
      blocks.push({ kind: "heading", level: (heading[1] ?? "#").length, text: heading[2] ?? "" });
      i += 1;
      continue;
    }
    if (BULLET.test(line) || NUMBERED.test(line)) {
      const ordered = NUMBERED.test(line);
      const items: string[] = [];
      while (i < lines.length) {
        const current = lines[i] ?? "";
        const match = (ordered ? NUMBERED : BULLET).exec(current);
        if (match === null) {
          break;
        }
        items.push(match[1] ?? "");
        i += 1;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }
    if (line.trim() === "") {
      i += 1;
      continue;
    }
    const paragraph: string[] = [];
    while (i < lines.length) {
      const current = lines[i] ?? "";
      if (current.trim() === "" || startsBlock(current)) {
        break;
      }
      paragraph.push(current);
      i += 1;
    }
    blocks.push({ kind: "paragraph", lines: paragraph });
  }
  return blocks;
}

/** The address of a link, only if it is a plain web address. */
export function safeHref(raw: string): string | null {
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

// The address may contain one level of balanced parentheses, as in `javascript:alert(1)` or a wiki URL.
const LINK = /^\[([^\]\n]+)\]\(((?:[^()\s]|\([^()\s]*\))+)(?:\s+"[^"\n]*")?\)/;

/** In a half-written text, show a link that is not finished as its label alone. */
function trimDanglingLink(text: string): string {
  return text.replace(/\[([^\]\n]*)(?:\]\([^)\n]*)?$/, "$1");
}

function isWordEdge(text: string, index: number): boolean {
  const char = text[index];
  return char === undefined || /[\s\p{P}]/u.test(char);
}

function parseInline(source: string, options: MarkdownOptions, keys: { next: number }): ReactNode[] {
  const partial = options.partial === true;
  const text = partial ? trimDanglingLink(source) : source;
  const out: ReactNode[] = [];
  let plain = "";
  const flush = () => {
    if (plain !== "") {
      out.push(plain);
      plain = "";
    }
  };
  let i = 0;
  while (i < text.length) {
    const char = text[i] ?? "";

    if (char === "`") {
      let run = 1;
      while (text[i + run] === "`") {
        run += 1;
      }
      const ticks = "`".repeat(run);
      const close = text.indexOf(ticks, i + run);
      if (close !== -1 || partial) {
        flush();
        const end = close === -1 ? text.length : close;
        out.push(<code key={keys.next++}>{text.slice(i + run, end)}</code>);
        i = close === -1 ? text.length : close + run;
        continue;
      }
      plain += ticks;
      i += run;
      continue;
    }

    if (char === "*" || char === "_") {
      const double = text[i + 1] === char;
      const marker = double ? char + char : char;
      const inner = i + marker.length;
      const opensEmphasis =
        text[inner] !== undefined &&
        !/\s/.test(text[inner] ?? "") &&
        (char === "*" || isWordEdge(text, i - 1));
      if (opensEmphasis) {
        let close = -1;
        for (let j = inner; j < text.length; j += 1) {
          if (text.startsWith(marker, j) && !/\s/.test(text[j - 1] ?? " ")) {
            // A single marker must not be the first half of a double one.
            if (!double && text[j + 1] === char) {
              j += 1;
              continue;
            }
            close = j;
            break;
          }
        }
        if (close !== -1 || partial) {
          flush();
          const end = close === -1 ? text.length : close;
          const children = parseInline(text.slice(inner, end), options, keys);
          out.push(
            double ? (
              <strong key={keys.next++}>{children}</strong>
            ) : (
              <em key={keys.next++}>{children}</em>
            ),
          );
          i = close === -1 ? text.length : close + marker.length;
          continue;
        }
      }
      plain += marker;
      i += marker.length;
      continue;
    }

    if (char === "[") {
      const link = LINK.exec(text.slice(i));
      if (link !== null) {
        flush();
        const label = parseInline(link[1] ?? "", options, keys);
        const href = options.inert === true ? null : safeHref(link[2] ?? "");
        out.push(
          href === null ? (
            <span key={keys.next++} className="md-link">
              {label}
            </span>
          ) : (
            <a key={keys.next++} href={href} target="_blank" rel="noopener noreferrer nofollow">
              {label}
            </a>
          ),
        );
        i += link[0].length;
        continue;
      }
    }

    plain += char;
    i += 1;
  }
  flush();
  return out;
}

/** The blocks of `source` as React elements. Wrap the result in an element of your own. */
export function renderMarkdown(source: string, options: MarkdownOptions = {}): ReactNode {
  const keys = { next: 0 };
  const interactive = options.inert !== true;
  const blocks = parseBlocks(source, options.partial === true);
  const shallowest = Math.min(...blocks.map((block) => (block.kind === "heading" ? block.level : 6)));
  let previousHeading = 1; // the page's own h1
  return blocks.map((block, index) => {
    switch (block.kind) {
      case "code":
        return (
          <pre key={index} className="md-code" tabIndex={interactive ? 0 : undefined}>
            <code>{block.text}</code>
          </pre>
        );
      case "heading": {
        const level = Math.min(block.level - shallowest + 2, previousHeading + 1, 6);
        previousHeading = level;
        return createElement(
          `h${level}`,
          { key: index, className: "md-heading" },
          parseInline(block.text, options, keys),
        );
      }
      case "list": {
        const items = block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{parseInline(item, options, keys)}</li>
        ));
        return block.ordered ? <ol key={index}>{items}</ol> : <ul key={index}>{items}</ul>;
      }
      case "paragraph":
        return (
          <p key={index}>
            {block.lines.flatMap((line, lineIndex) => [
              ...(lineIndex > 0 ? [<br key={`br${lineIndex}`} />] : []),
              ...parseInline(line, options, keys),
            ])}
          </p>
        );
    }
  });
}
