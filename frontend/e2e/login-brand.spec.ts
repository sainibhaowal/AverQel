import { expect, test } from "@playwright/test";

test("login page uses the selected icon, colored wordmark, and requested tagline", async ({ page }) => {
  await page.goto("/auth/login");

  await expect(page.locator(".login-exact-logo")).toBeVisible();
  await expect(page.locator(".login-exact-logo")).toHaveAttribute("alt", "");
  await expect(page.getByRole("img", { name: "AverQel" })).toBeVisible();
  await expect(page.locator(".login-brand-wordmark")).toBeVisible();
  await expect(page.locator(".login-brand-wordmark image")).toHaveAttribute(
    "href",
    "/brand/AverQel_Text.svg",
  );
  await expect(page.locator(".login-exact-letter-rgb")).toBeVisible();
  await expect(page.locator(".login-exact-letter-rgb")).toHaveCSS(
    "animation-name",
    "login-letter-rgb-sweep",
  );
  await expect(page.locator(".login-brand-wordmark .averqel-wordmark__svg")).toHaveCSS(
    "animation-name",
    "none",
  );

  const tagline = page.getByText("INTELLIGENCE ALL YOU NEED");
  await expect(tagline).toBeVisible();
});

test("signup page uses the same icon, colored wordmark, and tagline", async ({ page }) => {
  await page.goto("/auth/signup");

  await expect(page.locator(".login-exact-logo")).toBeVisible();
  await expect(page.locator(".login-exact-logo")).toHaveAttribute("alt", "");
  await expect(page.getByRole("img", { name: "AverQel" })).toBeVisible();
  await expect(page.locator(".login-brand-wordmark")).toBeVisible();
  await expect(page.locator(".login-brand-wordmark image")).toHaveAttribute(
    "href",
    "/brand/AverQel_Text.svg",
  );
  await expect(page.locator(".login-exact-letter-rgb")).toBeVisible();
  await expect(page.locator(".login-exact-letter-rgb")).toHaveCSS(
    "animation-name",
    "login-letter-rgb-sweep",
  );
  await expect(page.locator(".login-brand-wordmark .averqel-wordmark__svg")).toHaveCSS(
    "animation-name",
    "none",
  );
  await expect(page.getByText("INTELLIGENCE ALL YOU NEED")).toBeVisible();
});

test("login wordmark keeps a static RGB treatment for reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/auth/login");

  await expect(page.locator(".login-exact-letter-rgb")).toHaveCSS("animation-name", "none");
  await expect(page.locator(".login-exact-letter-rgb")).toHaveCSS(
    "background-position",
    "50% 50%",
  );
});
