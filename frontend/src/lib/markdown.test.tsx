import { render } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { renderMarkdown, safeHref, type MarkdownOptions } from "./markdown";

function html(source: string, options?: MarkdownOptions): HTMLElement {
  const { container } = render(<div>{renderMarkdown(source, options)}</div>);
  return container.firstElementChild as HTMLElement;
}

describe("blocks", () => {
  test("paragraphs, with a single newline kept as a line break", () => {
    const root = html("first line\nsecond line\n\nanother paragraph");

    const paragraphs = root.querySelectorAll("p");
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[0]?.querySelectorAll("br")).toHaveLength(1);
    expect(paragraphs[0]?.textContent).toBe("first linesecond line");
    expect(paragraphs[1]?.textContent).toBe("another paragraph");
  });

  test("headings are re-levelled below the page's h1, and none skips a level", () => {
    const root = html("# One\n\n## Two\n\n###### Six");

    expect(root.querySelector("h1")).toBeNull();
    expect(root.querySelector("h2")?.textContent).toBe("One");
    expect(root.querySelector("h3")?.textContent).toBe("Two");
    expect(root.querySelector("h4")?.textContent).toBe("Six"); // not an h6 that skips levels
    expect(root.querySelector("h5, h6")).toBeNull();
  });

  test("a reply that starts at ## still starts at h2, so it never skips under the page's h1", () => {
    const root = html("## Plan\n\ntext\n\n#### Details");

    expect(root.querySelector("h2")?.textContent).toBe("Plan");
    expect(root.querySelector("h3")?.textContent).toBe("Details");
    expect(root.querySelector("h4")).toBeNull();
  });

  test("seven hashes are not a heading", () => {
    const root = html("####### nope");

    expect(root.querySelector("h2,h3,h4,h5,h6")).toBeNull();
    expect(root.querySelector("p")?.textContent).toBe("####### nope");
  });

  test("bullet lists and numbered lists, each ending at the next kind of block", () => {
    const root = html("- apples\n- pears\n* plums\n\n1. first\n2. second\n\nafter");

    const lists = root.querySelectorAll("ul, ol");
    expect(lists).toHaveLength(2);
    expect(root.querySelectorAll("ul > li")).toHaveLength(3);
    expect(root.querySelectorAll("ol > li")).toHaveLength(2);
    expect(root.querySelector("ol > li")?.textContent).toBe("first");
    expect(root.querySelector("p")?.textContent).toBe("after");
  });

  test("a fenced code block keeps its text exactly and parses nothing inside", () => {
    const root = html("```js\nconst a = **1**;\n<b>x</b>\n```\ntext after");

    const code = root.querySelector("pre > code");
    expect(code?.textContent).toBe("const a = **1**;\n<b>x</b>");
    expect(root.querySelector("pre b")).toBeNull();
    expect(root.querySelector("strong")).toBeNull();
    expect(root.querySelector("p")?.textContent).toBe("text after");
  });

  test("a code block that is still open shows the code so far while text arrives", () => {
    const root = html("Here:\n```\nconst a", { partial: true });

    expect(root.querySelector("pre > code")?.textContent).toBe("const a");
  });

  test("a code block is keyboard-focusable so it can be scrolled, unless inert", () => {
    expect(html("```\nx\n```").querySelector("pre")?.getAttribute("tabindex")).toBe("0");
    expect(html("```\nx\n```", { inert: true }).querySelector("pre")?.hasAttribute("tabindex")).toBe(false);
  });

  test("nothing renders for empty text", () => {
    expect(html("").childElementCount).toBe(0);
  });
});

describe("inline text", () => {
  test("code, bold and italic", () => {
    const root = html("use `npm test`, **really**, and *carefully* or _gently_");

    expect(root.querySelector("code")?.textContent).toBe("npm test");
    expect(root.querySelector("strong")?.textContent).toBe("really");
    expect(root.querySelectorAll("em")).toHaveLength(2);
  });

  test("bold and italic nest", () => {
    const root = html("**bold and *both* here**");

    expect(root.querySelector("strong")?.textContent).toBe("bold and both here");
    expect(root.querySelector("strong em")?.textContent).toBe("both");
  });

  test("markers that are not emphasis stay as typed", () => {
    expect(html("2 * 3 * 4").textContent).toBe("2 * 3 * 4");
    expect(html("snake_case_name").querySelector("em")).toBeNull();
    expect(html("snake_case_name").textContent).toBe("snake_case_name");
    expect(html("an unclosed **marker").textContent).toBe("an unclosed **marker");
    expect(html("an unclosed `tick").textContent).toBe("an unclosed `tick");
  });
});

describe("links", () => {
  test("a web link opens safely in a new tab", () => {
    const link = html("see [the docs](https://example.com/a?b=1)").querySelector("a");

    expect(link?.getAttribute("href")).toBe("https://example.com/a?b=1");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toBe("noopener noreferrer nofollow");
    expect(link?.textContent).toBe("the docs");
  });

  test.each([
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:x",
    "/relative/path",
    "example.com",
    "mailto:someone@example.com",
  ])("%s is never a clickable link", (address) => {
    const root = html(`[click me](${address})`);

    expect(root.querySelector("a")).toBeNull();
    expect(root.textContent).toBe("click me");
  });

  test("an inert render shows even a web link as plain text", () => {
    const root = html("[the docs](https://example.com)", { inert: true });

    expect(root.querySelector("a")).toBeNull();
    expect(root.textContent).toBe("the docs");
  });

  test("safeHref accepts only http and https", () => {
    expect(safeHref("https://example.com")).toBe("https://example.com/");
    expect(safeHref("http://example.com")).toBe("http://example.com/");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("not a url")).toBeNull();
  });
});

describe("text nobody has vouched for", () => {
  test("raw HTML is shown as characters and creates no elements", () => {
    const root = html('<script>alert(1)</script><img src=x onerror="alert(1)"> <b>bold?</b>');

    expect(root.querySelector("script, img, b")).toBeNull();
    expect(root.textContent).toContain("<script>alert(1)</script>");
    expect(root.textContent).toContain("<b>bold?</b>");
  });

  test("HTML inside a link label or a heading is also just text", () => {
    const root = html("# <img src=x onerror=alert(1)>\n\n[<i>x</i>](https://example.com)");

    expect(root.querySelector("img, i")).toBeNull();
    expect(root.querySelector("h2")?.textContent).toBe("<img src=x onerror=alert(1)>");
  });
});

describe("text that is still arriving (partial)", () => {
  test("an emphasis not yet closed is shown as emphasis, not as raw markers", () => {
    expect(html("a **bol", { partial: true }).querySelector("strong")?.textContent).toBe("bol");
    expect(html("a *ita", { partial: true }).querySelector("em")?.textContent).toBe("ita");
    expect(html("a `co", { partial: true }).querySelector("code")?.textContent).toBe("co");
    expect(html("a **bol", { partial: true }).textContent).not.toContain("*");
  });

  test("half of a link is shown as its label only", () => {
    expect(html("see [the do", { partial: true }).textContent).toBe("see the do");
    expect(html("see [the docs](https://exa", { partial: true }).textContent).toBe("see the docs");
    expect(html("see [the docs](https://exa", { partial: true }).querySelector("a")).toBeNull();
  });

  test("a bare heading or list marker at the end is not shown yet", () => {
    expect(html("Intro\n\n##", { partial: true }).textContent).toBe("Intro");
    expect(html("Intro\n\n- ", { partial: true }).textContent).toBe("Intro");
    expect(html("Intro\n\n1.", { partial: true }).textContent).toBe("Intro");
  });

  test("the same text, finished, renders the same as it will when complete", () => {
    const full = "# Plan\n\n- **Day 1**: beach\n- Day 2: [map](https://example.com)";

    const partial = html(full, { partial: true });
    const done = html(full);

    expect(partial.innerHTML).toBe(done.innerHTML);
  });
});
