import { expect, test } from "@playwright/test";

test("homepage renders the visual workspace hero without hydration failures", async ({ page }) => {
  const hydrationErrors: string[] = [];
  page.on("pageerror", (error) => {
    if (/hydration|Minified React error #418/i.test(error.message)) {
      hydrationErrors.push(error.message);
    }
  });

  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto("/");

  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toHaveText("Intelligence. All you need.");
  await expect(page.getByText("AI grounded in your sources")).toBeVisible();
  await expect(page.getByRole("link", { name: "Create your workspace" })).toBeVisible();

  const lockup = page.locator("[data-brand-lockup]:visible").first();
  const mark = lockup.locator('img[src="/brand/AverQel_Icon.svg"]');
  const wordmark = lockup.locator(".averqel-wordmark__svg");
  await expect(mark).toHaveAttribute("width", "92");
  await expect(mark).toHaveAttribute("height", "46");
  await expect(wordmark).toHaveAttribute("width", "156");
  await expect(wordmark).toHaveAttribute("height", "29");

  const [markBox, wordmarkBox] = await Promise.all([mark.boundingBox(), wordmark.boundingBox()]);
  expect(markBox).not.toBeNull();
  expect(wordmarkBox).not.toBeNull();
  if (markBox && wordmarkBox) {
    const markCenter = markBox.y + markBox.height / 2;
    const wordmarkCenter = wordmarkBox.y + wordmarkBox.height / 2;
    expect(Math.abs(markCenter - wordmarkCenter)).toBeLessThan(3);
    expect(wordmarkBox.x - (markBox.x + markBox.width)).toBeLessThanOrEqual(-12);
  }

  const footerLockup = page.locator("[data-brand-lockup].averqel-logo--footer:visible").first();
  await expect(footerLockup).toBeVisible();
  await footerLockup.scrollIntoViewIfNeeded();
  const footerMark = footerLockup.locator('img[src="/brand/AverQel_Icon.svg"]');
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
