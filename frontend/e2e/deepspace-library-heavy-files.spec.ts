import { expect, test } from "./fixtures";

test.describe("DeepSpace heavy Library authenticated matrix", () => {
  test.describe.configure({ timeout: 60_000 });

  for (const viewport of ["desktop", "tablet"] as const) {
    test(`${viewport} keeps Library and artifact surfaces reachable`, async ({
      authenticatedPage,
    }) => {
      await authenticatedPage.setViewportSize(
        viewport === "desktop" ? { width: 1440, height: 900 } : { width: 900, height: 900 },
      );
      await authenticatedPage.goto("/dashboard/deepspace");
      await expect(authenticatedPage.getByText(/DeepSpace/i).first()).toBeVisible();
      await expect(authenticatedPage.locator("body")).not.toContainText("Internal Server Error");
    });
  }

  test("makes a securely stored image sendable while OCR continues", async ({
    authenticatedPage,
  }) => {
    const uploadId = "10000000-0000-4000-8000-000000000001";
    const fileId = "20000000-0000-4000-8000-000000000001";
    const conversationId = "00000000-0000-0000-0000-000000000301";
    let submittedAttachmentIds: string[] | undefined;
    let extractionPolls = 0;

    await authenticatedPage.route("**/api/v1/deepspace/library/**", async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname.replace(/^\/api\/v1/, "");
      if (pathname.endsWith("/uploads") && request.method() === "POST") {
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            id: uploadId,
            chunk_size: 1024,
            total_chunks: 1,
            received_chunks: [],
            status: "uploading",
          }),
        });
        return;
      }
      if (pathname.endsWith(`/uploads/${uploadId}/chunks/0`) && request.method() === "PUT") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: uploadId,
            chunk_size: 1024,
            total_chunks: 1,
            received_chunks: [0],
            bytes_received: 8,
            status: "uploading",
          }),
        });
        return;
      }
      if (pathname.endsWith(`/uploads/${uploadId}/complete`) && request.method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: uploadId,
            status: "completed",
            file_id: fileId,
            extraction_status: { state: "processing", text_available: false, ocr_used: false },
          }),
        });
        return;
      }
      if (pathname.endsWith(`/uploads/${uploadId}`) && request.method() === "GET") {
        extractionPolls += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: uploadId,
            status: "completed",
            file_id: fileId,
            extraction_status:
              extractionPolls > 2
                ? { state: "extracted", text_available: true, ocr_used: true }
                : { state: "processing", text_available: false, ocr_used: false },
          }),
        });
        return;
      }
      await route.fallback();
    });

    await authenticatedPage.route("**/api/v1/deepspace/chats/stream", async (route) => {
      submittedAttachmentIds = route.request().postDataJSON().attachment_file_ids;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream; charset=utf-8",
        headers: { "Cache-Control": "no-cache" },
        body:
          `event: start\ndata: {"conversation_id":"${conversationId}","message_id":"30000000-0000-4000-8000-000000000001"}\n\n` +
          `event: done\ndata: {"conversation_id":"${conversationId}","message_id":"30000000-0000-4000-8000-000000000001","status":"ready"}\n\n`,
      });
    });

    await authenticatedPage.goto("/dashboard/deepspace");
    await authenticatedPage
      .locator('input[type="file"]')
      .first()
      .setInputFiles({
        name: "image.png",
        mimeType: "image/png",
        buffer: Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
      });

    await expect(authenticatedPage.getByText("Uploaded · reading text")).toBeVisible();
    const send = authenticatedPage.getByRole("button", { name: "Send message" });
    await expect(send).toBeEnabled();
    await send.click();
    await expect.poll(() => submittedAttachmentIds).toEqual([fileId]);
  });
});
