// Browser-only regression check; session data is mocked, no account is changed.
import assert from "node:assert/strict";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const browser = await chromium.launch();
try {
  for (const [width, height] of [
    [1280, 900],
    [390, 700],
    [320, 480],
  ]) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.route("**/api/auth/**", (route) =>
      route.fulfill({
        json: {
          user: {
            id: "mock-user",
            name: "Test Administrator",
            email: "test@example.org",
            role: "ADMIN",
            emailVerified: true,
          },
          session: {
            id: "mock-session",
            userId: "mock-user",
            expiresAt: "2099-01-01T00:00:00.000Z",
          },
        },
      }),
    );
    await page.goto(process.env.UI_URL || "http://127.0.0.1:3318");
    if (width < 1101)
      await page.getByRole("button", { name: "Open navigation menu" }).click();
    const trigger = page.getByRole("button", { name: "Account menu" });
    await trigger.click();
    const menu = page.getByRole("menu");
    await menu.waitFor();
    await page.waitForTimeout(250);
    const rect = await menu.boundingBox();
    assert.ok(
      rect &&
        rect.x >= 0 &&
        rect.y >= 0 &&
        rect.x + rect.width <= width &&
        rect.y + rect.height <= height,
    );
    if (width === 1280)
      assert.ok(rect.y >= 65, "Desktop menu should clear navbar");
    for (const name of [
      "Edit Profile",
      "Notifications",
      "Passkeys",
      "Sign out",
    ]) {
      const item = page.getByRole("menuitem", { name, exact: true });
      await item.scrollIntoViewIfNeeded();
      assert.ok(
        await item.evaluate((element) => {
          const r = element.getBoundingClientRect();
          return element.contains(
            document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2),
          );
        }),
        `${name} is obscured at ${width}px`,
      );
    }
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "hidden" });
    assert.ok(
      await trigger.evaluate((element) => element === document.activeElement),
      "Escape restores trigger focus",
    );
    await trigger.click();
    await page
      .getByRole("menuitem", { name: "Edit Profile", exact: true })
      .click();
    await page.getByRole("dialog").waitFor();
    assert.equal(
      await page.evaluate(
        () => !!document.elementFromPoint(10, 10)?.closest("header"),
      ),
      false,
      "Dialog overlay covers navbar",
    );
    await page.keyboard.press("Escape");
    await page.close();
    console.log(
      `PASS: ${width}x${height} account menu bounds, hit targets, Escape focus and dialog stacking`,
    );
  }
} finally {
  await browser.close();
}
