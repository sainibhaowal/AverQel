import { expect, test } from "@playwright/test";

test("landing page cards stay readable across phone, tablet, and desktop widths", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/v1/contact/status", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"available":true}' }),
  );

  for (const width of [390, 640, 768, 900, 1024, 1199, 1200, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    if (width === 390) await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Wherever you need it.", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Into the Unknown", { exact: true })).toHaveCount(0);
    const hero = page.locator("main > div.relative > section").first();
    const particleField = hero.locator("[data-hero-particle-field]");
    await expect(particleField.locator("canvas")).toHaveCount(2);
    await expect(particleField.locator("[data-hero-morphing-background]")).toHaveCount(1);
    await expect(hero.locator("[data-hero-connect-particles]")).toHaveCount(0);
    await expect(particleField.locator('canvas[data-hero-pixel-core="q"]')).toHaveCount(0);
    if (width === 390) {
      await expect
        .poll(async () =>
          particleField.locator("[data-hero-ambient-particles]").evaluate((element) => {
            const canvas = element as HTMLCanvasElement;
            const context = canvas.getContext("2d");
            if (!context) return false;

            const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
            let hasLeftParticles = false;
            let hasRightParticles = false;
            for (let pixel = 0; pixel < pixels.length; pixel += 4) {
              if (!pixels[pixel + 3]) continue;
              const x = (pixel / 4) % canvas.width;
              if (x < canvas.width / 2) hasLeftParticles = true;
              else hasRightParticles = true;
              if (hasLeftParticles && hasRightParticles) return true;
            }

            return false;
          }),
        )
        .toBe(true);
    }
    const heroBackground = await hero.evaluate((element) => {
      const heroBox = element.getBoundingClientRect();
      const field = element.querySelector<HTMLElement>("[data-hero-particle-field]");
      const ambient = element.querySelector<HTMLCanvasElement>("[data-hero-ambient-particles]");
      const artwork = element.querySelector<HTMLElement>("[data-hero-focus-animation]");
      if (!field || !ambient || !artwork) {
        return {
          coversHero: false,
          animationOnRight: false,
          canvasExtendsLeft: false,
          canvasIsWiderThanHero: false,
          animationAnchorRatio: 0,
          backgroundColor: "missing hero field",
          fieldBackgroundColor: "missing hero field",
          bottomBorderWidth: "missing hero field",
          paintContainment: "missing hero field",
          fieldMaskImage: "missing hero field",
          grid: "missing hero field",
        };
      }

      const fieldBox = field.getBoundingClientRect();
      const ambientBox = ambient.getBoundingClientRect();
      const artworkBox = artwork.getBoundingClientRect();
      const focusXRatio = Number.parseFloat(
        getComputedStyle(artwork).getPropertyValue("--hero-focus-x"),
      );
      const animationAnchorRatio =
        (artworkBox.left - heroBox.left + artworkBox.width * focusXRatio) / heroBox.width;
      return {
        coversHero:
          Math.abs(fieldBox.x - heroBox.x) <= 1 &&
          Math.abs(fieldBox.y - heroBox.y) <= 1 &&
          Math.abs(fieldBox.width - heroBox.width) <= 1 &&
          Math.abs(fieldBox.height - heroBox.height) <= 1 &&
          Math.abs(ambientBox.x - heroBox.x) <= 1 &&
          Math.abs(ambientBox.y - heroBox.y) <= 1 &&
          Math.abs(ambientBox.width - heroBox.width) <= 1 &&
          Math.abs(ambientBox.height - heroBox.height) <= 1,
        animationOnRight: animationAnchorRatio > 0.62,
        canvasExtendsLeft: artworkBox.left < heroBox.left,
        canvasIsWiderThanHero: artworkBox.width > heroBox.width * 1.15,
        animationAnchorRatio,
        backgroundColor: getComputedStyle(element).backgroundColor,
        fieldBackgroundColor: getComputedStyle(field).backgroundColor,
        bottomBorderWidth: getComputedStyle(element).borderBottomWidth,
        paintContainment: getComputedStyle(element).contain,
        fieldMaskImage: getComputedStyle(field).maskImage,
        grid: getComputedStyle(element, "::before").backgroundImage,
      };
    });
    expect(heroBackground.coversHero, `particle field covers the hero at ${width}px`).toBe(true);
    expect(heroBackground.animationOnRight, `main animation stays on the right at ${width}px`).toBe(
      true,
    );
    expect(heroBackground.canvasExtendsLeft, `particle canvas extends left at ${width}px`).toBe(
      true,
    );
    expect(
      heroBackground.canvasIsWiderThanHero,
      `particle canvas gains width without stretching artwork at ${width}px`,
    ).toBe(true);
    expect(heroBackground.animationAnchorRatio).toBeCloseTo(width < 640 ? 0.68 : 0.72, 2);
    expect(heroBackground.backgroundColor, `hero stays transparent at ${width}px`).toBe(
      "rgba(0, 0, 0, 0)",
    );
    expect(
      heroBackground.fieldBackgroundColor,
      `particle field stays transparent at ${width}px`,
    ).toBe("rgba(0, 0, 0, 0)");
    expect(heroBackground.bottomBorderWidth, `hero has no boundary at ${width}px`).toBe("0px");
    expect(heroBackground.paintContainment, `hero has no paint shell at ${width}px`).not.toContain(
      "paint",
    );
    expect(heroBackground.fieldMaskImage, `particle layer fades at ${width}px`).not.toBe("none");
    expect(heroBackground.grid, `hero grid is removed at ${width}px`).toBe("none");
    await expect(page.locator("#documents-hub")).toHaveCSS("border-top-width", "0px");
    await expect(page.locator("#deepspace article[data-card-index='0'] img")).toHaveAttribute(
      "src",
      /DeepSpace(?:%20| )Logo.*DeepSpace_Logo_Only_NoBlack_Exact\.svg/,
    );

    const layoutIssues = await page.evaluate(() => {
      const overlaps: string[] = [];
      const overflows: string[] = [];
      const textSelectors = ["h3", "p", "li span", "a"];

      for (const card of document.querySelectorAll<HTMLElement>(
        "section[data-layout] article[data-card-index]",
      )) {
        const textNodes = textSelectors
          .flatMap((selector) => Array.from(card.querySelectorAll<HTMLElement>(selector)))
          .filter((element) => element.getBoundingClientRect().width > 0);

        for (const element of textNodes) {
          if (element.scrollWidth > element.clientWidth + 1) {
            overflows.push(`${card.closest("section")?.id}: ${element.textContent?.trim()}`);
          }
        }

        for (let left = 0; left < textNodes.length; left += 1) {
          for (let right = left + 1; right < textNodes.length; right += 1) {
            const a = textNodes[left].getBoundingClientRect();
            const b = textNodes[right].getBoundingClientRect();
            const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (overlapX > 1 && overlapY > 1) {
              overlaps.push(
                `${card.closest("section")?.id}: ${textNodes[left].textContent?.trim()}`,
              );
            }
          }
        }
      }

      return { overlaps, overflows };
    });

    expect(layoutIssues.overlaps, `text overlap at ${width}px`).toEqual([]);
    expect(layoutIssues.overflows, `text overflow at ${width}px`).toEqual([]);
  }
});

test("contact form uses rounded accessible validation hints and sends valid input", async ({
  page,
}) => {
  let submittedMessage: Record<string, string> | null = null;
  await page.route("**/api/v1/contact/status", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"available":true}' }),
  );
  await page.route("**/api/v1/contact/verification/request", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ challenge_id: "contact-challenge-e2e" }),
    }),
  );
  await page.route("**/api/v1/contact/verification/confirm", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        verified: true,
        verification_token: "contact-verification-token-e2e",
      }),
    }),
  );
  await page.route("**/api/v1/contact", async (route) => {
    submittedMessage = route.request().postDataJSON() as Record<string, string>;
    await route.fulfill({ status: 202, contentType: "application/json", body: "{}" });
  });

  await page.goto("/");
  const emailInput = page.getByLabel("Email for my reply");
  await emailInput.fill("ada@example.com");
  await page.getByRole("button", { name: "Email me a code" }).click();
  await page.getByLabel("Verification code").fill("123456");
  await page.getByRole("button", { name: "Verify email" }).click();
  await expect(page.getByText("Email verified. You can now write and send your message.")).toBeVisible();

  const submit = page.getByRole("button", { name: "Send message" });
  await expect(submit).toBeEnabled();
  await submit.click();

  const nameInput = page.getByLabel("Your name");
  const nameError = page.getByText("Enter your name so I know how to address you.");
  await expect(nameError).toBeVisible();
  await expect(page.getByText("Add a short subject for your message.")).toBeVisible();
  await expect(page.getByText("Write a message before sending.")).toBeVisible();
  await expect(nameInput).toHaveAttribute("aria-invalid", "true");
  await expect(nameInput).toBeFocused();
  const errorRadius = await nameError.evaluate((element) =>
    Number.parseFloat(getComputedStyle(element).borderTopLeftRadius),
  );
  expect(errorRadius).toBeGreaterThanOrEqual(10);

  await nameInput.fill("Ada Lovelace");
  await page.getByRole("textbox", { name: "Subject" }).fill("Product question");
  await page
    .getByRole("textbox", { name: "Your message" })
    .fill("How can I use AverQel with my documents?");
  await submit.click();

  await expect(
    page.getByText("Your message was accepted by the email service. Thank you for reaching out."),
  ).toBeVisible();
  expect(submittedMessage).toEqual({
    name: "Ada Lovelace",
    email: "ada@example.com",
    subject: "Product question",
    message: "How can I use AverQel with my documents?",
    website: "",
    verification_token: "contact-verification-token-e2e",
  });
});

test("hero morphing particles animate without painting a solid canvas background", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.route("**/api/v1/contact/status", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"available":true}' }),
  );

  await page.goto("/");
  const morphingCanvas = page.locator("[data-hero-morphing-background]");
  await expect(morphingCanvas).toBeVisible();
  await expect
    .poll(async () =>
      morphingCanvas.evaluate((element) => {
        const canvas = element as HTMLCanvasElement;
        const context = canvas.getContext("2d");
        if (!context) return 0;

        const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
        let visibleSamples = 0;
        for (let pixel = 3; pixel < pixels.length; pixel += 16) {
          if (pixels[pixel]) visibleSamples += 1;
        }
        return visibleSamples;
      }),
    )
    .toBeGreaterThan(20);
  await expect
    .poll(() => morphingCanvas.evaluate((element) => getComputedStyle(element).backgroundColor))
    .toBe("rgba(0, 0, 0, 0)");
});
