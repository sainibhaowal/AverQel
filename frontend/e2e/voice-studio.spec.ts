import { expect, test } from "./fixtures";

function makeSilentWav() {
  const sampleRate = 24_000;
  const samples = 2_400;
  const dataSize = samples * 2;
  const wav = Buffer.alloc(44 + dataSize);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(36 + dataSize, 4);
  wav.write("WAVE", 8);
  wav.write("fmt ", 12);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(sampleRate, 24);
  wav.writeUInt32LE(sampleRate * 2, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(dataSize, 40);
  return wav;
}

test.describe("Voice Studio settings", () => {
  test.describe.configure({ timeout: 120_000 });

  test("Voice Studio page loads and shows voice selector", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/dashboard/settings/voice");
    await expect(authenticatedPage.getByText("Voice Studio")).toBeVisible();
    await expect(authenticatedPage.getByText("Voice Selection")).toBeVisible();
    await expect(authenticatedPage.getByText("Built-in Voices")).toBeVisible();
    await expect(authenticatedPage.getByRole("combobox")).toBeVisible();
  });

  test("voice picker uses rounded options with clear labels", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/dashboard/settings/voice");
    const picker = authenticatedPage.getByRole("combobox", { name: "Built-in voices" });
    await picker.click();

    const menu = authenticatedPage.getByRole("listbox", { name: "Built-in voices" });
    await expect(menu).toHaveClass(/rounded-2xl/);
    await expect(
      authenticatedPage.getByRole("option", { name: /Alba.*Warm, natural female/ }),
    ).toBeVisible();
    const optionLabels = await authenticatedPage.getByRole("option").allTextContents();
    expect(optionLabels.join(" ")).not.toContain("—");
  });

  test("Voice Studio page shows playback settings", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/dashboard/settings/voice");
    await expect(authenticatedPage.getByRole("heading", { name: "Playback Settings" })).toBeVisible();
    await expect(authenticatedPage.getByText("Speed", { exact: true })).toBeVisible();
    await expect(
      authenticatedPage.getByText("Pitch adjustment is not supported by the current voice engine."),
    ).toBeVisible();
    await expect(authenticatedPage.getByText("Volume", { exact: true })).toBeVisible();
  });

  test("voice preview sends a short sample and mounts a playable audio element", async ({
    authenticatedPage,
  }) => {
    let requestPayload: Record<string, unknown> | undefined;
    await authenticatedPage.addInitScript(() => {
      HTMLMediaElement.prototype.play = function () {
        const count = Number(this.dataset.e2ePlayCalls ?? "0") + 1;
        this.dataset.e2ePlayCalls = String(count);
        return Promise.resolve();
      };
    });
    await authenticatedPage.route("**/api/v1/deepspace/voice/test", async (route) => {
      requestPayload = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: "audio/wav",
        body: makeSilentWav(),
      });
    });

    await authenticatedPage.goto("/dashboard/settings/voice");
    await authenticatedPage.getByRole("button", { name: "Play Test Sound" }).click();
    const audio = authenticatedPage.locator('audio[aria-label="Voice preview audio"]');
    await expect(audio).toBeVisible();
    await expect(audio).toHaveAttribute("src", /^blob:/);
    await expect.poll(() => audio.getAttribute("data-e2e-play-calls")).toBe("1");
    expect(requestPayload).toMatchObject({ text: "Hello.", voice: "alba" });
  });

  test("Voice Studio page shows voice cloning section", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/dashboard/settings/voice");
    await expect(authenticatedPage.getByText("Voice Cloning")).toBeVisible();
    await expect(authenticatedPage.getByText("Record Voice")).toBeVisible();
    await expect(authenticatedPage.getByText("Upload Audio")).toBeVisible();
  });

  test("Voice Studio page shows test voice section", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/dashboard/settings/voice");
    await expect(authenticatedPage.getByText("Test Voice")).toBeVisible();
    await expect(authenticatedPage.getByText("Play Test Sound")).toBeVisible();
  });

  test("Voice Studio accessible from settings page", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/dashboard/settings");
    await expect(authenticatedPage.getByText("Voice Studio")).toBeVisible();
    await authenticatedPage.getByText("Voice Studio").click();
    await expect(authenticatedPage).toHaveURL(/settings\/voice/);
    await expect(authenticatedPage.getByText("Voice Studio")).toBeVisible();
  });

  test("Voice Studio saves settings", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/dashboard/settings/voice");
    // Change speed
    const speedSlider = authenticatedPage.locator('input[type="range"]').first();
    await speedSlider.fill("1.5");
    // Save
    await authenticatedPage.getByText("Save Voice Settings").click();
    await expect(authenticatedPage.getByText("Voice settings saved successfully.")).toBeVisible();
  });
});
