// Read-only browser regression check. All API/provider responses are mocked.
// Install Playwright separately, or set PLAYWRIGHT_MODULE to its index.mjs.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { MODEL_CATALOG } from "../web/src/lib/model-catalog.ts";

const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const root = fileURLToPath(new URL("../", import.meta.url));
const output = await mkdtemp(join(tmpdir(), "vadat-ui-parity-"));
const reference = createServer(async (request, response) => {
  const path = request.url?.split("?")[0];
  if (path !== "/" && path !== "/styles.css") {
    response.writeHead(404).end();
    return;
  }
  response.setHeader("Content-Type", path === "/" ? "text/html" : "text/css");
  response.end(
    await readFile(join(root, path === "/" ? "index.html" : "styles.css")),
  );
});
await new Promise((resolve) => reference.listen(0, "127.0.0.1", resolve));
const original = `http://127.0.0.1:${reference.address().port}`;
const target = process.env.UI_URL || "http://127.0.0.1:3318";
const result = {
  success: true,
  summary: {
    programmatic_count: 1,
    llm_prompts_run: 1,
    estimated_cost_usd: 0.0123,
  },
  programmatic_findings: [
    {
      rule_id: "IMG",
      rule_name: "Image alternative",
      description: "Missing alt",
    },
  ],
  llm_results: {
    image_check: {
      status: "success",
      checklist: "Images",
      wcag_criteria: ["1.1.1"],
      parsed: {
        issues: [
          {
            description: "<img src=x onerror=alert(1)>",
            element: "<img>",
            recommended_fix: "Add descriptive alt text",
            impact: "serious",
          },
        ],
      },
    },
  },
  csv_report: "rule,description\nIMG,Missing alt",
};
const browser = await chromium.launch();
try {
  const boxes = {};
  for (const width of [1280, 390]) {
    for (const [name, url] of [
      ["original", original],
      ["react", target],
    ]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.route("**/api/**", (route) => {
        const path = new URL(route.request().url()).pathname;
        const json =
          path === "/api/models"
            ? { models: MODEL_CATALOG, defaultModelId: MODEL_CATALOG[0].id }
            : path === "/api/validate-key"
              ? { valid: true }
              : path.startsWith("/api/auth/")
                ? null
                : result;
        return route.fulfill({ json });
      });
      // Use the same locally hosted original font files in both pages.
      await page.route("**/fonts/*.ttf", async (route) => {
        const filename = new URL(route.request().url()).pathname
          .split("/")
          .pop();
        assert.match(
          filename,
          /^(dm-sans-(400|500|600|700)|dm-serif-display)\.ttf$/,
        );
        await route.fulfill({
          contentType: "font/ttf",
          headers: { "Access-Control-Allow-Origin": "*" },
          body: await readFile(join(root, "web/public/fonts", filename)),
        });
      });
      await page.route("https://fonts.googleapis.com/**", async (route) => {
        const css = await readFile(
          join(root, "web/src/app/legacy.css"),
          "utf8",
        );
        const faces = css.match(/@font-face\s*\{[^}]+\}/g).join("\n");
        await route.fulfill({
          contentType: "text/css",
          body: faces.replaceAll("url('/fonts/", `url('${target}/fonts/`),
        });
      });
      await page.goto(name === "react" ? `${url}/audit` : url);
      await page.locator(".audit-form").waitFor();
      if (name === "react")
        await page.waitForFunction(
          () => !document.querySelector("#modelSelect").disabled,
        );
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({
        path: join(output, `${name}-${width}-form.png`),
        fullPage: true,
      });
      if (width === 1280) {
        boxes[name] = await page.evaluate(() =>
          Object.fromEntries(
            [
              ".section-header",
              ".audit-form",
              ".drop-zone",
              ".form-row",
              ".audit-btn",
              ".site-footer",
            ].map((selector) => {
              const element = [...document.querySelectorAll(selector)].find(
                (el) => el.getBoundingClientRect().height > 0,
              );
              const rect = element.getBoundingClientRect();
              // Shared P5 navbar includes additional auth actions. Compare
              // audit content geometry independently of their header heights.
              const top = document
                .querySelector("#auditTool")
                .getBoundingClientRect().top;
              return [
                selector,
                [rect.x, rect.y - top, rect.width, rect.height],
              ];
            }),
          ),
        );
      }
      if (name === "react") {
        assert.equal(
          await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth,
          ),
          false,
          `Horizontal overflow at ${width}px`,
        );
        if (width === 390)
          await page
            .getByRole("button", { name: "Open navigation menu" })
            .click();
        await page.getByRole("link", { name: "About", exact: true }).click();
        await page
          .getByRole("heading", { name: "About the Project" })
          .waitFor();
        assert.equal(new URL(page.url()).pathname, "/");
        assert.equal(await page.locator(".audit-form").count(), 0);
        if (width === 390)
          await page
            .getByRole("button", { name: "Open navigation menu" })
            .click();
        await page
          .getByRole("link", { name: "Audit Tool", exact: true })
          .click();
        await page
          .getByRole("heading", { name: "Accessibility Audit Tool" })
          .waitFor();
        assert.equal(new URL(page.url()).pathname, "/audit");
        assert.equal(await page.locator("#about").count(), 0);
        if (width === 390)
          await page
            .getByRole("button", { name: "Open navigation menu" })
            .click();
        await page
          .getByRole("navigation", { name: "Primary navigation" })
          .getByRole("link", { name: "Team", exact: true })
          .click();
        await page.waitForURL("**/#team");
        await page.locator("#team").waitFor();
        assert.equal(await page.locator(".audit-form").count(), 0);
        if (width === 390)
          await page
            .getByRole("button", { name: "Open navigation menu" })
            .click();
        await page
          .getByRole("navigation", { name: "Primary navigation" })
          .getByRole("link", { name: "Lighthouse", exact: true })
          .click();
        await page.waitForURL("**/#lighthouse");
        await page.locator("#lighthouse").waitFor();
        assert.equal(await page.getByRole("banner").count(), 1);
        assert.equal(await page.locator('header a[href="/signin"]').count(), 1);
        if (width === 390)
          await page
            .getByRole("button", { name: "Open navigation menu" })
            .click();
        await page
          .getByRole("link", { name: "Audit Tool", exact: true })
          .click();
        await page.waitForURL("**/audit");
        await page.getByRole("button", { name: "Show API key" }).click();
        assert.equal(
          await page.locator("#apiKeyInput").getAttribute("type"),
          "text",
        );
        await page.getByRole("button", { name: "Hide API key" }).click();
        await page.locator("#fileInput").setInputFiles({
          name: "test.html",
          mimeType: "text/html",
          buffer: Buffer.from("<p>Test</p>"),
        });
        await page.locator(".drop-zone.has-file").waitFor();
        await page.getByRole("button", { name: "Remove file" }).click();
        await page.locator(".drop-zone:not(.has-file)").waitFor();
      }
      await page.getByText("URL — Single Page", { exact: true }).click();
      await page.locator("#urlInput").fill("https://example.org");
      await page
        .getByRole("button", { name: "Run Audit", exact: true })
        .click();
      await page.locator(".findings-table").waitFor();
      await page.getByRole("button", { name: /image check/ }).click();
      await page.locator(".llm-prompt.open .issue-card").waitFor();
      assert.equal(await page.locator(".audit-results img").count(), 0);
      await page
        .locator(".audit-results")
        .screenshot({ path: join(output, `${name}-${width}-results.png`) });
      const downloading = page.waitForEvent("download");
      await page.getByText("Download Report (CSV)", { exact: true }).click();
      assert.match((await downloading).suggestedFilename(), /\.csv$/);
      assert.deepEqual(errors, []);
      await page.close();
    }
  }
  for (const [selector, expected] of Object.entries(boxes.original)) {
    boxes.react[selector].forEach((value, index) =>
      assert.ok(
        Math.abs(value - expected[index]) < 1,
        `${selector} differs: ${boxes.react[selector]} vs ${expected}`,
      ),
    );
  }
  console.log(
    `PASS: desktop geometry matches original; mobile, navigation, upload, key visibility, results, CSV and safe rendering pass. Screenshots: ${output}`,
  );
} finally {
  await browser.close();
  await new Promise((resolve) => reference.close(resolve));
}
