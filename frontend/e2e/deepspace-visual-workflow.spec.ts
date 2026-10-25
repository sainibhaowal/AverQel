import { readFileSync } from "node:fs";

import type { Locator, Page } from "@playwright/test";

import { expect, test } from "./fixtures";

const conversationId = "00000000-0000-0000-0000-000000000401";
const messageId = "00000000-0000-0000-0000-000000000499";
const blockId = "visual-workflow-chart";
const galleryImageUrl = "https://images.example.test/research.png";
const galleryOwnedUrl = `/api/v1/deepspace/library/${conversationId}/files/gallery-photo/content`;
const codeFence = String.fromCharCode(96).repeat(3);
const fallbackModelAnswer = [
  "Here is the quarterly revenue chart.",
  "",
  `${codeFence}chart`,
  '{"title":"Quarterly revenue","chart_type":"bar","series":[{"label":"Q1","value":12},{"label":"Q2","value":18},{"label":"Q3","value":16}]}',
  codeFence,
].join("\n");

type VisualBlock = Record<string, unknown> & {
  id: string;
  type: "chart";
  title: string;
  chart_type: string;
  series: Array<{ label: string; value: number }>;
  revision: number;
  schema_version: number;
};

type VisualState = {
  block: VisualBlock;
  revision: number;
  content: string;
  noteHtml: string;
  artifact: Record<string, unknown> | null;
  diagramArtifact: Record<string, unknown> | null;
};

function htmlAttribute(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function readGeneratedChart(): { answer: string; block: VisualBlock; noteHtml: string } {
  const fixturePath = process.env.DEEPSPACE_E2E_VISUAL_MARKDOWN_FILE;
  const answer = fixturePath ? readFileSync(fixturePath, "utf8") : fallbackModelAnswer;
  const match = answer.match(/```chart\s*\n([\s\S]*?)\n```/i);
  if (!match) throw new Error("The visual-generation fixture has no chart Markdown fence.");
  const payload = JSON.parse(match[1]!) as Record<string, unknown>;
  if (
    typeof payload.title !== "string" ||
    !["line", "bar", "area", "scatter", "pie"].includes(String(payload.chart_type)) ||
    !Array.isArray(payload.series) ||
    payload.series.length < 2
  ) {
    throw new Error("The visual-generation fixture does not match the DeepSpace chart schema.");
  }
  const block: VisualBlock = {
    ...payload,
    id: blockId,
    type: "chart",
    title: payload.title,
    chart_type: String(payload.chart_type),
    series: payload.series as VisualBlock["series"],
    revision: 0,
    schema_version: 1,
  };
  const markdownBlock = { ...payload, id: blockId, revision: 0, schema_version: 1 };
  const chartFence = `${codeFence}chart\n${JSON.stringify(markdownBlock, null, 2)}\n${codeFence}`;
  const answerWithStableId = answer.replace(match[0], chartFence);
  const richSource = htmlAttribute(JSON.stringify(block));
  const noteHtml = `<pre data-rich-content-kind="chart" data-rich-content-source="${richSource}"><code>${chartFence}</code></pre>`;
  return { answer: answerWithStableId, block, noteHtml };
}

function richNoteHtmlSource(kind: string, source: string): string {
  const fence = `${codeFence}${kind}\n${source}\n${codeFence}`;
  return `<pre data-rich-content-kind="${kind}" data-rich-content-source="${htmlAttribute(source)}"><code>${fence}</code></pre>`;
}

function richNoteHtml(kind: string, payload: Record<string, unknown>): string {
  return richNoteHtmlSource(kind, JSON.stringify(payload));
}

function makeVisualState(): VisualState {
  const generated = readGeneratedChart();
  const card = {
    id: "visual-workflow-card",
    title: "Executive summary",
    subtitle: "Illustrative quarterly result",
    tone: "success",
    content: "Revenue grew through Q2 and held near that level in Q3.",
    metrics: [{ label: "Peak quarter", value: "Q2" }],
  };
  const evaluationCard = {
    id: "visual-workflow-evaluation",
    title: "LarpRouter API evaluation",
    subtitle: "Tests from August 17 to September 21, 2026",
    layout: "evaluation",
    score: { value: 51, max: 100, tone: "error" },
    metrics: [
      { label: "Valid scored tests", value: 15 },
      { label: "Claude signature checks passed", value: "0/10" },
    ],
    content: "Source: Veridrop's publicly reported testing results.",
    sources: [{ title: "Veridrop", url: "https://example.com/veridrop" }],
  };
  const referralCard = {
    id: "visual-workflow-referral",
    title: "LarpRouter referral",
    layout: "referral",
    code: "81D9-627A-11",
    primary_metric: { label: "Gift tokens advertised", value: "10,000,000" },
    details: [
      { label: "Free cash", value: "No" },
      { label: "Credit card required initially", value: "No, according to site" },
      { label: "Inviter's commission", value: "5% first top-up, 2% later" },
      { label: "Gift-token restrictions", value: "Three specified models" },
    ],
    content: "These terms are published by LarpRouter, not independently verified benefits.",
    sources: [{ title: "LarpRouter", url: "https://example.com/referral" }],
  };
  const graph = {
    id: "visual-workflow-graph",
    title: "Release architecture",
    graph: {
      layout: "horizontal",
      nodes: [
        { id: "input", label: "User input", x: 140, y: 150 },
        { id: "output", label: "Generated response", x: 500, y: 150 },
      ],
      edges: [{ source: "input", target: "output", label: "render" }],
    },
  };
  const mermaidSource = [
    "gantt",
    "  title Four-Week Launch (illustrative dates)",
    "  dateFormat YY-MM-D",
    "  axisFormat %b %d",
    "  section Discovery",
    "  Research :done, res, 2026-01-05, 5d",
    "  section Delivery",
    "  Build :active, build, 2026-01-12, 10d",
    "  Review :crit, review, after build, 3d",
    "  Release :rel, after review, 2d",
    "  Launch :milestone, ml, after rel, 0d",
  ].join("\n");
  const gallery = {
    id: "visual-workflow-gallery",
    block_id: "visual-workflow-gallery",
    type: "gallery",
    title: "Research photos",
    items: [{ src: galleryImageUrl, alt: "Microscope", caption: "Research photo" }],
    assets: [
      {
        url: galleryImageUrl,
        owned_url: galleryOwnedUrl,
        mime_type: "image/png",
        status: "owned",
        file_id: "gallery-photo",
        retention: "temporary",
      },
    ],
  };
  const answer = [
    generated.answer,
    codeFence + "card\n" + JSON.stringify(card, null, 2) + "\n" + codeFence,
    codeFence + "card\n" + JSON.stringify(evaluationCard, null, 2) + "\n" + codeFence,
    codeFence + "card\n" + JSON.stringify(referralCard, null, 2) + "\n" + codeFence,
    "```graph\n" + JSON.stringify(graph, null, 2) + "\n```",
    "```gantt\n" + mermaidSource + "\n```",
    "```gallery\n" + JSON.stringify(gallery, null, 2) + "\n```",
  ].join("\n\n");
  return {
    block: generated.block,
    revision: 0,
    content: answer,
    noteHtml: [
      generated.noteHtml,
      richNoteHtml("card", card),
      richNoteHtml("card", evaluationCard),
      richNoteHtml("card", referralCard),
      richNoteHtml("gallery", gallery),
      richNoteHtml("graph", graph),
      richNoteHtmlSource("mermaid", mermaidSource),
    ].join(""),
    artifact: null,
    diagramArtifact: null,
  };
}

function chartFence(block: VisualBlock): string {
  const payload: Record<string, unknown> = { ...block };
  delete payload.type;
  return `${codeFence}chart\n${JSON.stringify(payload, null, 2)}\n${codeFence}`;
}

function currentMessage(state: VisualState) {
  return {
    id: messageId,
    role: "assistant",
    content: state.content,
    metadata_json: {
      visual_blocks:
        state.revision > 0
          ? {
              [blockId]: {
                revision: state.revision,
                schema_version: 1,
                block: state.block,
                history: [{ revision: state.revision, source: "chat" }],
              },
            }
          : {},
    },
    created_at: "2026-10-16T10:00:00Z",
    active_version_id: `message-version-${state.revision + 1}`,
    active_version_index: state.revision + 1,
    version_count: state.revision + 1,
    versions: [],
  };
}

function replaceChart(content: string, block: VisualBlock): string {
  return content.replace(/```chart\s*\n[\s\S]*?\n```/i, chartFence(block));
}

function artifactDocument(state: VisualState, version: number) {
  const content = JSON.stringify(
    {
      block_id: blockId,
      schema_version: 1,
      revision: state.revision,
      kind: "chart",
      data: state.block,
      assets: [],
      history: [{ revision: state.revision, source: "e2e" }],
      undo: {},
    },
    null,
    2,
  );
  return {
    id: "visual-artifact-file",
    name: `${blockId}.visual.json`,
    content_type: "application/json",
    source: "visual_editor",
    size_bytes: content.length,
    content,
    version,
    is_binary: false,
    checksum_sha256: "e2e-checksum",
    metadata_json: {
      visual_document: { block_id: blockId, schema_version: 1, revision: state.revision },
    },
    created_at: "2026-10-16T10:00:00Z",
    updated_at: "2026-10-16T10:00:00Z",
  };
}

async function expectVisualDownload(
  page: Page,
  button: Locator,
  expectedFilename: RegExp,
): Promise<void> {
  const downloadReady = page.waitForEvent("download", { timeout: 15_000 }).catch(() => null);
  await button.click();
  const download = await downloadReady;
  if (!download) {
    const error = await page
      .getByRole("alert")
      .last()
      .textContent()
      .catch(() => "No export error was rendered.");
    throw new Error(`Visual export did not download a file: ${error}`);
  }
  const filename = download.suggestedFilename();
  expect(filename).toMatch(expectedFilename);
  const path = await download.path();
  if (!path) throw new Error(`The downloaded visual file is unavailable: ${filename}`);
  const bytes = readFileSync(path);
  expect(bytes.byteLength).toBeGreaterThan(0);
  if (filename.endsWith(".pdf")) {
    expect(bytes.subarray(0, 5).toString("ascii")).toBe("%PDF-");
  } else if (filename.endsWith(".png")) {
    expect(bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))).toBe(true);
    const imageWidth = bytes.readUInt32BE(16);
    const imageHeight = bytes.readUInt32BE(20);
    expect(imageWidth).toBeGreaterThan(24);
    expect(imageHeight).toBeGreaterThan(24);
    expect(imageWidth * imageHeight).toBeGreaterThan(1_000);
  } else if (filename.endsWith(".svg")) {
    const svg = bytes.toString("utf8");
    expect(svg).toContain("<svg");
    expect(svg).toContain("viewBox");
    expect(svg).not.toContain('viewBox="0 0 24 24"');
  } else if (filename.endsWith(".json")) {
    expect(JSON.parse(bytes.toString("utf8"))).toBeTruthy();
  } else if (filename.endsWith(".mmd")) {
    expect(bytes.toString("utf8")).toContain("gantt");
  }
}

async function expectRoundedRectangle(button: Locator): Promise<void> {
  await expect(button).toHaveClass(/visual-block-action/);
  const dimensions = await button.evaluate((element) => ({
    radius: Number.parseFloat(window.getComputedStyle(element).borderTopLeftRadius),
    height: element.getBoundingClientRect().height,
  }));
  expect(dimensions.radius).toBeGreaterThan(0);
  expect(dimensions.radius).toBeLessThan(dimensions.height / 2);
}

async function installVisualApi(page: Page, state: VisualState) {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname.replace(/^\/api\/v1/, "").replace(/\/$/, "");
    const method = request.method();
    const json = async (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (pathname === "/auth/profile") {
      return json({
        user_id: "e2e-local-user",
        tenant_id: "e2e-local-tenant",
        email: "e2e@example.org",
        display_name: "E2E User",
        roles: ["user"],
        status: "active",
        onboarding_completed: true,
      });
    }
    if (pathname === "/deepspace/chats" && method === "GET") {
      return json({
        items: [
          {
            id: conversationId,
            title: "Visual acceptance conversation",
            content_html: state.noteHtml,
            updated_at: "2026-10-16T10:00:00Z",
          },
        ],
      });
    }
    if (pathname === `/deepspace/chats/${conversationId}` && method === "PATCH") {
      const payload = request.postDataJSON() as { content_html?: string; title?: string };
      if (typeof payload.content_html === "string") state.noteHtml = payload.content_html;
      return json({
        id: conversationId,
        content_html: state.noteHtml,
        title: payload.title ?? "Visual acceptance conversation",
        updated_at: "2026-10-16T10:00:00Z",
      });
    }
    if (pathname === "/deepspace/chats/operational-summary") return json(null);
    if (pathname === `/deepspace/chats/${conversationId}/messages` && method === "GET") {
      return json({ messages: [currentMessage(state)] });
    }
    if (
      pathname === `/deepspace/chats/${conversationId}/messages/${messageId}/visual-block` &&
      method === "PATCH"
    ) {
      const payload = request.postDataJSON() as {
        block_id: string;
        expected_revision?: number;
        block: VisualBlock;
      };
      if (payload.block_id !== blockId || payload.expected_revision !== state.revision) {
        return json({ detail: { message: "Visual block revision conflict." } }, 409);
      }
      state.revision += 1;
      state.block = { ...payload.block, revision: state.revision };
      state.content = replaceChart(state.content, state.block);
      return json(currentMessage(state));
    }
    if (pathname === `/deepspace/chats/${conversationId}/visual-block` && method === "PATCH") {
      const payload = request.postDataJSON() as {
        block_id: string;
        expected_revision?: number;
        block: VisualBlock;
      };
      if (payload.block_id !== blockId || payload.expected_revision !== state.revision) {
        return json({ detail: { message: "Visual block revision conflict." } }, 409);
      }
      state.revision += 1;
      state.block = { ...payload.block, revision: state.revision };
      state.content = replaceChart(state.content, state.block);
      return json(currentMessage(state));
    }
    if (pathname === `/deepspace/library/${conversationId}/visual-artifacts` && method === "POST") {
      const payload = request.postDataJSON() as {
        block: Record<string, unknown> & { id: string; type?: string };
        expected_version?: number;
      };
      if (payload.block.type === "diagram") {
        state.diagramArtifact = payload.block;
        const content = JSON.stringify(payload.block, null, 2);
        return json({
          id: "mermaid-visual-artifact",
          name: `${payload.block.id}.visual.json`,
          content_type: "application/json",
          source: "visual_editor",
          size_bytes: content.length,
          content,
          version: 1,
        });
      }
      const currentVersion = Number((state.artifact as { version?: number } | null)?.version ?? 0);
      if (
        (state.artifact && payload.expected_version !== currentVersion) ||
        (!state.artifact && payload.expected_version !== undefined)
      ) {
        return json({ detail: { message: "Artifact version conflict." } }, 409);
      }
      const version = currentVersion + 1;
      state.block = { ...payload.block, revision: state.revision } as VisualBlock;
      state.artifact = artifactDocument(state, version);
      return json(state.artifact);
    }
    if (pathname === `/deepspace/library/${conversationId}/entries` && method === "GET") {
      return json({ files: state.artifact ? [state.artifact] : [], folders: [] });
    }
    if (pathname === `/deepspace/library/${conversationId}/uploads` && method === "GET") {
      return json([]);
    }
    if (pathname === `/deepspace/library/${conversationId}/files/gallery-photo/content`) {
      return route.fulfill({
        status: 200,
        contentType: "image/png",
        body: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/G5sAAAAASUVORK5CYII=",
          "base64",
        ),
      });
    }
    if (
      pathname === `/deepspace/library/${conversationId}/files/visual-artifact-file` &&
      method === "GET"
    ) {
      return state.artifact ? json(state.artifact) : json({ detail: "Artifact not found" }, 404);
    }
    if (
      pathname === `/deepspace/library/${conversationId}/files/visual-artifact-file` &&
      method === "PATCH"
    ) {
      const payload = request.postDataJSON() as { content: string; expected_version: number };
      const currentVersion = Number((state.artifact as { version?: number } | null)?.version ?? 0);
      if (!state.artifact || payload.expected_version !== currentVersion) {
        return json({ detail: { message: "Artifact version conflict." } }, 409);
      }
      const version = currentVersion + 1;
      state.artifact = {
        ...state.artifact,
        content: payload.content,
        size_bytes: payload.content.length,
        version,
      };
      return json(state.artifact);
    }
    if (pathname === "/providers" || pathname === "/providers/assignments")
      return json({ items: [] });
    if (pathname === "/notifications" || pathname === "/collections/notifications") return json([]);
    if (/^\/deepspace\/chats\/[^/]+\/queue/.test(pathname)) {
      return json({ items: [], paused: false, reason: null, failed_request_id: null });
    }
    return json({});
  });
}

test.describe("DeepSpace visual workflow", () => {
  test("renders, syncs, exports, and reloads a generated visual in the same private account", async ({
    authenticatedPage,
    browser,
  }) => {
    test.setTimeout(240_000);
    await authenticatedPage.setViewportSize({ width: 1440, height: 900 });
    const state = makeVisualState();
    await installVisualApi(authenticatedPage, state);
    await authenticatedPage.goto("/dashboard/deepspace", { waitUntil: "domcontentloaded" });

    await expect(authenticatedPage.getByRole("heading", { name: state.block.title })).toBeVisible({
      timeout: 30_000,
    });
    const evaluationSummary = authenticatedPage.getByTestId("evaluation-card-summary");
    await expect(evaluationSummary).toBeVisible();
    await expect(evaluationSummary.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "51");
    await expect(evaluationSummary.getByTestId("evaluation-card-metric")).toHaveCount(2);
    const referralSummary = authenticatedPage.getByTestId("referral-card-summary");
    await expect(referralSummary).toBeVisible();
    await expect(referralSummary.getByTestId("referral-card-detail")).toHaveCount(4);
    await expect(
      authenticatedPage.getByRole("button", { name: "Copy referral code" }),
    ).toBeVisible();
    const chartTitle = authenticatedPage.getByRole("heading", { name: state.block.title });
    const chartDataAction = authenticatedPage.getByRole("button", { name: "Download chart data" });
    const [chartTitleBounds, chartActionBounds] = await Promise.all([
      chartTitle.boundingBox(),
      chartDataAction.boundingBox(),
    ]);
    if (!chartTitleBounds || !chartActionBounds) {
      throw new Error("The chart title and toolbar need visible layout bounds.");
    }
    expect(
      Math.abs(
        chartTitleBounds.y +
          chartTitleBounds.height / 2 -
          chartActionBounds.y -
          chartActionBounds.height / 2,
      ),
    ).toBeLessThan(3);
    await expectRoundedRectangle(chartDataAction);
    const chartJsonExport = authenticatedPage.getByRole("button", {
      name: "Export chart source as JSON",
    });
    await expectRoundedRectangle(chartJsonExport);
    await expect(chartJsonExport.locator("xpath=..")).toHaveCSS("opacity", "1");
    await expect(
      authenticatedPage.getByRole("heading", { name: "Executive summary" }),
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole("region", { name: "Research photos" }).getByRole("img", {
        name: "Microscope",
      }),
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole("region", { name: "Release architecture" }),
    ).toBeVisible();
    const ganttSvg = authenticatedPage
      .locator('[data-visual-export-source="diagram"] svg')
      .filter({ hasText: "Four-Week Launch" });
    await expect(ganttSvg).toBeVisible({ timeout: 30_000 });
    await expect.poll(async () => await ganttSvg.textContent()).toContain("Research");
    await expect(
      authenticatedPage.locator("pre code").filter({ hasText: '"title": "Executive summary"' }),
    ).toHaveCount(0);

    await authenticatedPage.getByRole("button", { name: "Edit data" }).click();
    const doneChartEdit = authenticatedPage.getByRole("button", { name: "Done" });
    await authenticatedPage.mouse.move(0, 0);
    await expectRoundedRectangle(doneChartEdit);
    await expect(doneChartEdit).toHaveCSS("background-color", "rgb(15, 118, 110)");
    await expect(doneChartEdit).toHaveCSS("color", "rgb(255, 255, 255)");
    await authenticatedPage.getByLabel("Live equation (x → y)").fill("y = 5*x + 1");
    await authenticatedPage.getByRole("button", { name: "Recalculate" }).click();
    await expect(authenticatedPage.getByRole("img", { name: state.block.title })).toBeVisible();
    await authenticatedPage.getByRole("spinbutton", { name: "Chart point 1 value" }).fill("99");
    await doneChartEdit.click();
    await expect.poll(() => state.revision).toBe(1);
    await expect.poll(() => state.noteHtml).toContain("99");
    const savedChartSource = JSON.parse(String(state.block.raw_payload)) as {
      equation: string;
      series: Array<{ label: string; value: number }>;
    };
    expect(savedChartSource.equation).toBe("y = 5*x + 1");
    expect(savedChartSource.series).toEqual(state.block.series);
    expect(savedChartSource.series[0]).toEqual({ label: "Q1", value: 99 });

    for (const format of ["SVG", "PNG", "PDF"] as const) {
      await expectVisualDownload(
        authenticatedPage,
        authenticatedPage.getByRole("button", { name: `Export chart as ${format}` }),
        new RegExp(`quarterly-revenue\\.${format.toLowerCase()}$`),
      );
    }
    const executiveSummaryCard = authenticatedPage.locator(
      '[data-visual-block-id="visual-workflow-card"]',
    );
    await expect(executiveSummaryCard).toHaveCount(1);
    for (const format of ["SVG", "PNG", "PDF"] as const) {
      await expectVisualDownload(
        authenticatedPage,
        executiveSummaryCard.getByRole("button", { name: `Export card as ${format}` }),
        new RegExp(`executive-summary\\.${format.toLowerCase()}$`),
      );
    }
    for (const format of ["SVG", "PNG", "PDF"] as const) {
      await expectVisualDownload(
        authenticatedPage,
        authenticatedPage.getByRole("button", { name: `Export gallery as ${format}` }),
        new RegExp(`research-photos\\.${format.toLowerCase()}$`),
      );
    }
    const graphRegion = authenticatedPage.getByRole("region", { name: "Release architecture" });
    const graphExportTools = graphRegion.locator("xpath=../..");
    for (const format of ["SVG", "PNG", "PDF"] as const) {
      await expectVisualDownload(
        authenticatedPage,
        graphExportTools.getByRole("button", { name: `Export diagram as ${format}` }),
        new RegExp(`release-architecture\\.${format.toLowerCase()}$`),
      );
    }
    const mermaidVisual = authenticatedPage
      .locator('section[data-visual-block-id^="deepspace-mermaid-"]')
      .first();
    const mermaidExport = mermaidVisual.getByRole("button", {
      name: "Export Mermaid diagram",
    });
    const mermaidToolbarExports = [
      ["Export diagram source as JSON", "json"],
      ["Export diagram source as Mermaid", "mmd"],
      ["Export diagram as SVG", "svg"],
      ["Export diagram as PNG", "png"],
      ["Export diagram as PDF", "pdf"],
    ] as const;
    for (const [label, extension] of mermaidToolbarExports) {
      const exportButton = mermaidVisual.getByRole("button", { name: label });
      await expectRoundedRectangle(exportButton);
      await expectVisualDownload(
        authenticatedPage,
        exportButton,
        new RegExp(`diagram\\.${extension}$`),
      );
    }
    await mermaidExport.click();
    for (const format of ["SVG", "PNG", "PDF", "Mermaid (.mmd)"] as const) {
      const extension = format === "Mermaid (.mmd)" ? "mmd" : format.toLowerCase();
      await expectVisualDownload(
        authenticatedPage,
        authenticatedPage.getByRole("button", { name: format, exact: true }),
        new RegExp(`diagram\\.${extension}$`),
      );
      if (format !== "Mermaid (.mmd)") await mermaidExport.click();
    }

    await authenticatedPage.getByRole("button", { name: "Save chart artifact" }).click();
    await expect.poll(() => state.artifact?.version).toBe(1);
    await expect.poll(() => String(state.artifact?.content)).toContain('"value": 99');

    await authenticatedPage.getByRole("button", { name: "Edit data" }).click();
    await authenticatedPage.getByRole("spinbutton", { name: "Chart point 1 value" }).fill("110");
    await authenticatedPage.getByRole("button", { name: "Done" }).click();
    await expect.poll(() => state.revision).toBe(2);
    await expect.poll(() => state.artifact?.version).toBe(2);
    await expect.poll(() => String(state.artifact?.content)).toContain('"value": 110');

    await authenticatedPage.getByRole("button", { name: "Notes" }).click();
    const noteChart = authenticatedPage.locator('[data-rich-content-kind="chart"]');
    await expect(noteChart).toBeVisible();
    await noteChart.getByRole("button", { name: "Payload" }).click();
    await expect(noteChart.locator("pre")).toContainText('"value": 110');
    await expect(
      authenticatedPage
        .locator('[data-rich-content-kind="card"]')
        .getByRole("heading", { name: "Executive summary" }),
    ).toBeVisible();
    await noteChart.getByRole("button", { name: "Edit chart block" }).click();
    const noteChartSource = noteChart.getByRole("textbox", { name: "Edit chart JSON or source" });
    const editedNoteBlock = JSON.parse(await noteChartSource.inputValue()) as VisualBlock;
    editedNoteBlock.series[0]!.value = 115;
    await noteChartSource.fill(JSON.stringify(editedNoteBlock, null, 2));
    await noteChart.getByRole("button", { name: "Save block" }).click();
    await expect.poll(() => state.revision, { timeout: 30_000 }).toBe(3);
    await expect.poll(() => state.artifact?.version).toBe(3);
    await expect.poll(() => String(state.artifact?.content)).toContain('"value": 115');
    await expect.poll(() => state.noteHtml).toContain('"value": 115');
    await noteChart.getByRole("button", { name: "Payload" }).click();
    await expect(noteChart.locator("pre")).toContainText('"value": 115');
    await expect(
      authenticatedPage.getByRole("region", { name: "Research photos" }).getByRole("img", {
        name: "Microscope",
      }),
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole("region", { name: "Release architecture" }),
    ).toBeVisible();
    await expect(
      authenticatedPage.getByRole("button", { name: "Export Mermaid diagram" }),
    ).toBeVisible();

    await authenticatedPage.getByRole("button", { name: "Library", exact: true }).click();
    await authenticatedPage
      .getByRole("button", { name: `${blockId}.visual.json`, exact: true })
      .click();
    const artifactEditor = authenticatedPage.getByRole("button", { name: "Edit data" });
    await expect(artifactEditor).toBeVisible();
    await artifactEditor.click();
    await authenticatedPage.getByRole("spinbutton", { name: "Chart point 1 value" }).fill("123");
    await authenticatedPage.getByRole("button", { name: "Done" }).click();
    await expect.poll(() => state.revision).toBe(4);
    await expect.poll(() => state.artifact?.version).toBe(4);
    await expect.poll(() => state.noteHtml).toContain("123");
    await expect.poll(() => String(state.artifact?.content)).toContain('"value": 123');
    // A delayed BlockNote callback from the earlier note edit must not save its
    // old revision after the artifact edit has synchronized the latest value.
    await authenticatedPage.waitForTimeout(1_800);
    await expect.poll(() => state.noteHtml).toContain("&quot;value&quot;: 123");

    await authenticatedPage.reload();
    await expect(authenticatedPage.getByRole("heading", { name: state.block.title })).toBeVisible();
    await expect(authenticatedPage.getByRole("img", { name: state.block.title })).toBeVisible();

    const authState = await authenticatedPage.evaluate(() => ({
      token: window.localStorage.getItem("averqel_token"),
      tenant: window.localStorage.getItem("averqel_tenant_id"),
      user: window.localStorage.getItem("averqel_user"),
    }));
    const secondContext = await browser.newContext({
      baseURL: new URL(authenticatedPage.url()).origin,
    });
    await secondContext.addInitScript((values) => {
      if (values.token) window.localStorage.setItem("averqel_token", values.token);
      if (values.tenant) window.localStorage.setItem("averqel_tenant_id", values.tenant);
      if (values.user) window.localStorage.setItem("averqel_user", values.user);
    }, authState);
    const secondPage = await secondContext.newPage();
    await installVisualApi(secondPage, state);
    try {
      await secondPage.goto("/dashboard/deepspace");
      await expect(secondPage.getByRole("heading", { name: state.block.title })).toBeVisible();
      await secondPage.getByRole("button", { name: "Edit data" }).click();
      await expect(secondPage.getByRole("spinbutton", { name: "Chart point 1 value" })).toHaveValue(
        "123",
      );
      await secondPage.getByRole("button", { name: "Notes" }).click();
      const secondNoteChart = secondPage.locator('[data-rich-content-kind="chart"]');
      await expect(secondNoteChart).toBeVisible({ timeout: 30_000 });
      await secondNoteChart.getByRole("button", { name: "Payload" }).click();
      await expect(secondNoteChart.locator("pre")).toContainText('"value": 123');
    } finally {
      await secondContext.close();
    }

    const saveMermaidArtifact = mermaidVisual.getByRole("button", {
      name: "Save diagram artifact",
    });
    const artifactSaveResponse = authenticatedPage.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith(
          `/deepspace/library/${conversationId}/visual-artifacts`,
        ),
    );
    await saveMermaidArtifact.click();
    expect((await artifactSaveResponse).status()).toBe(200);
    expect(state.diagramArtifact).toMatchObject({
      type: "diagram",
      source: "mermaid",
      block_id: expect.stringMatching(/^deepspace-mermaid-/),
    });
    await expect(saveMermaidArtifact).toContainText("Saved");
  });
});
