import { expect, test } from "@playwright/test";

test("login page uses the exact AverQel logo and requested tagline", async ({ page }) => {
  await page.goto("/auth/login");

  await expect(page.getByRole("img", { name: "AverQel" })).toHaveAttribute(
    "src",
    /AverQel_Exact_Logo\.svg/,
  );
  const logo = page.getByRole("img", { name: "AverQel" });
  await expect(logo).toHaveCSS("filter", "none");

  const animatedRegions = page.locator(".login-exact-logo--animated");
  await expect(animatedRegions).toHaveCount(2);
  await expect(animatedRegions.nth(0)).toHaveClass(/login-exact-logo--aver/);
  await expect(animatedRegions.nth(1)).toHaveClass(/login-exact-logo--el/);
  await expect(animatedRegions.nth(0)).toHaveAttribute("aria-hidden", "true");
  await expect(animatedRegions.nth(0)).toHaveCSS("animation-name", "login-logo-rgb-gradient-sweep");
  await expect(animatedRegions.nth(0)).toHaveCSS("background-image", /linear-gradient/);
  await expect(animatedRegions.nth(0)).toHaveCSS("background-size", "200% 100%");

  const clipPaths = await animatedRegions.evaluateAll((elements) =>
    elements.map((element) => getComputedStyle(element).clipPath),
  );
  expect(clipPaths[0]).toContain("56%");
  expect(clipPaths[1]).toContain("70%");

  const tagline = page.getByText("INTELLIGENCE ALL YOU NEED");
  await expect(tagline).toBeVisible();
  await expect(tagline).toHaveCSS("font-size", "10.2px");
});

test("signup page uses the same exact animated AverQel brand", async ({ page }) => {
  await page.goto("/auth/signup");

  await expect(page.getByRole("img", { name: "AverQel" })).toHaveAttribute(
    "src",
    /AverQel_Exact_Logo\.svg/,
  );
  await expect(page.locator(".login-exact-logo--animated")).toHaveCount(2);
  await expect(page.getByText("INTELLIGENCE ALL YOU NEED")).toBeVisible();
});
