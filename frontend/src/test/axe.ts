import axe from "axe-core";
import { expect } from "vitest";

interface AxeOptions {
  /**
   * Check page-level landmarks (every piece of content inside a landmark). Off for a component
   * rendered on its own, which has no page around it.
   */
  page?: boolean;
}

/**
 * Fails the test with a readable list if axe-core finds an accessibility violation in `target`.
 *
 * jsdom has no layout engine, so axe cannot measure colour contrast here and that rule is switched
 * off. Contrast is checked separately, in a real browser, by running axe against the built screens
 * (docs/PROJECT_CONTEXT.md records the result).
 */
export async function expectNoViolations(
  target: Element,
  { page = false }: AxeOptions = {},
): Promise<void> {
  const results = await axe.run(target, {
    rules: {
      "color-contrast": { enabled: false },
      region: { enabled: page },
    },
  });
  const found = results.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact ?? "?"}): ${violation.help}\n    ` +
      violation.nodes.map((node) => node.target.join(" ")).join("\n    "),
  );
  expect(found, found.join("\n")).toEqual([]);
}
