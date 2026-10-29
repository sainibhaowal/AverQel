import { expect, test } from "@playwright/test";

test("homepage renders the visual workspace hero without hydration failures", async ({ page }) => {
  const hydrationErrors: string[] = [];
  page.on("pageerror", (error) => {
    if (/hydration|Minified React error #418/i.test(error.message)) {
      hydrationErrors.push(error.message);
    }
  });
  page.on("console", (message) => {
    if (message.type() === "error" && /hydration|Minified React error #418/i.test(message.text())) {
      hydrationErrors.push(message.text());
    }
  });

  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto("/");

  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toHaveText("Intelligence. All you need.");
  await expect(page.getByText("AI grounded in your sources")).toBeVisible();
  await expect(page.getByRole("link", { name: "Create your workspace" })).toBeVisible();

  const lockup = page.locator("[data-brand-lockup]:visible").first();
  const mark = lockup.locator("img").first();
  await expect(mark).toHaveAttribute("width", "92");
  await expect(mark).toHaveAttribute("height", "46");
  await expect(lockup.locator(".averqel-wordmark__svg")).toHaveCount(0);

  const footerLockup = page.locator("[data-brand-lockup].averqel-logo--footer:visible").first();
  await expect(footerLockup).toBeVisible();
  await footerLockup.scrollIntoViewIfNeeded();
  const footerMark = footerLockup.locator("img").first();
  const footerWordmark = footerLockup.locator(".averqel-wordmark__svg");
  const [footerMarkBox, footerWordmarkBox] = await Promise.all([
    footerMark.boundingBox(),
    footerWordmark.boundingBox(),
  ]);
  expect(footerMarkBox).not.toBeNull();
  expect(footerWordmarkBox).not.toBeNull();
  if (footerMarkBox && footerWordmarkBox) {
    const footerMarkCenter = footerMarkBox.y + footerMarkBox.height / 2;
    const footerWordmarkCenter = footerWordmarkBox.y + footerWordmarkBox.height / 2;
    expect(Math.abs(footerMarkCenter - footerWordmarkCenter)).toBeLessThan(1.5);
  }

  await expect.poll(() => hydrationErrors).toEqual([]);
});
