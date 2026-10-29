import { expect, test } from "./fixtures";

test.describe("DeepSpace voice controls", () => {
  // A fresh isolated Next server compiles the DeepSpace route and LiveKit chunk on demand.
  test.describe.configure({ timeout: 180_000 });

  test("shows a recoverable error when the isolated voice token request fails", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.route("**/api/v1/voice/token**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "Voice unavailable in isolated browser test" }),
      });
    });

    await authenticatedPage.goto("/dashboard/deepspace");
    const dictationButton = authenticatedPage.getByRole("button", { name: "Dictate to composer" });
    const conversationButton = authenticatedPage.getByRole("button", {
      name: "Voice conversation",
    });
    await expect(dictationButton).toBeVisible();
    await expect(conversationButton).toBeVisible();

    const tokenResponse = authenticatedPage.waitForResponse((response) =>
      response.url().includes("/voice/token"),
    );
    await conversationButton.click();

    expect((await tokenResponse).status()).toBe(503);
    await expect(authenticatedPage.getByText("Voice server unreachable.")).toBeVisible();
    await expect(conversationButton).toHaveAttribute("aria-pressed", "false");
    await expect(dictationButton).toHaveAttribute("aria-pressed", "false");
  });

  test("keeps dictation disabled in the composer when voice setup fails", async ({
    authenticatedPage,
  }) => {
    await authenticatedPage.route("**/api/v1/voice/token**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "Voice unavailable in isolated browser test" }),
      });
    });

    await authenticatedPage.goto("/dashboard/deepspace");
    const dictationButton = authenticatedPage.getByRole("button", { name: "Dictate to composer" });
    await expect(dictationButton).toBeVisible();
    const tokenResponse = authenticatedPage.waitForResponse((response) =>
      response.url().includes("/voice/token"),
    );
    await dictationButton.click();

    expect((await tokenResponse).status()).toBe(503);
    await expect(authenticatedPage.getByText("Voice server unreachable.")).toBeVisible();
    await expect(dictationButton).toHaveAttribute("aria-pressed", "false");
    await expect(authenticatedPage.getByTestId("deepspace-voice-presence")).toHaveCount(0);
    await expect(authenticatedPage.getByTestId("dictation-elapsed")).toHaveCount(0);
  });
});
