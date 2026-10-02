import { expect, test } from "./fixtures";

const documentId = "00000000-0000-0000-0000-000000000101";
const shareId = "00000000-0000-0000-0000-000000000202";

const documentRecord = {
  document_id: documentId,
  filename: "quarterly-report.pdf",
  content_type: "application/pdf",
  size_bytes: 4096,
  sha256_hash: "a".repeat(64),
  storage_bucket: "tenant-private",
  storage_object_key: "documents/quarterly-report.pdf",
  status: "indexed",
  processing_progress: 100,
  extraction_method: "pdf_text",
  extraction_coverage_score: 1,
  extraction_ocr_used: true,
  extraction_vision_used: false,
  extraction_warnings: [],
  version: 1,
  parent_document_id: null,
  created_at: "2026-09-27T10:00:00Z",
  updated_at: "2026-09-27T10:00:00Z",
};

async function json(route: import("@playwright/test").Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockDocumentHub(page: import("@playwright/test").Page) {
  // Match both same-origin rewrites and the local API URL used by the desktop
  // runtime. The workflow assertions should exercise the browser contract
  // regardless of which supported frontend transport is active.
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");

    if (path === "/documents" && request.method() === "GET") {
      await json(route, {
        items: [
          {
            document_id: documentId,
            filename: "quarterly-report.pdf",
            content_type: "application/pdf",
            size_bytes: 4096,
            status: "indexed",
            processing_progress: 100,
            quarantined: true,
            information_yield: 1,
            created_at: documentRecord.created_at,
            extraction_coverage_score: 1,
            extraction_ocr_used: true,
            extraction_warnings: [],
          },
        ],
      });
      return;
    }
    if (path === "/documents/ops/observability") {
      await json(route, {
        status_counts: { indexed: 1 },
        active_ingestion_jobs: 0,
        failed_documents: 0,
        quarantined_documents: 1,
        total_documents: 1,
        indexed_documents: 1,
        storage_bytes: 4096,
      });
      return;
    }
    if (path === "/documents/duplicates") {
      await json(route, { total_duplicate_documents: 0, groups: [] });
      return;
    }
    if (path === "/documents/events/ticket") {
      await json(route, { ticket: "e2e-ticket" });
      return;
    }
    if (path === "/documents/organization/tags" || path === "/documents/organization/folders" || path === "/documents/organization/saved-views" || path === "/documents/organization/classification-rules" || path === "/documents/organization/automation-schedules") {
      await json(route, { items: [] });
      return;
    }
    if (path === "/documents/webhooks" && request.method() === "GET") {
      await json(route, [{ id: "webhook-1", endpoint_url: "https://example.test/hooks/documents", active: true, event_types: ["document.indexed"] }]);
      return;
    }
    if (path === "/documents/webhooks/webhook-1/deliveries") {
      await json(route, [{ event_type: "document.indexed", status: "delivered", response_status: 200, attempt_count: 1 }]);
      return;
    }
    if (path === `/documents/${documentId}/share-links` && request.method() === "POST") {
      await json(route, { id: shareId, share_token: "share-token-e2e" });
      return;
    }
    if (path === `/documents/share-links/${shareId}/resolve`) {
      await json(route, { filename: documentRecord.filename, content_type: "application/pdf", expires_at: "2026-09-28T10:00:00Z", content: "Confidential quarterly report content." });
      return;
    }
    if (path === `/documents/${documentId}`) {
      await json(route, documentRecord);
      return;
    }
    if (path === `/documents/${documentId}/status`) {
      await json(route, { document_id: documentId, status: "indexed", processing_progress: 100, active_stage: "indexed", stage_progress: 100, recovery_available: false, total_chunk_count: 2, embedded_chunk_count: 2, extraction_ocr_used: true, extraction_warnings: [] });
      return;
    }
    if (path === `/documents/${documentId}/chunks`) {
      await json(route, { document_id: documentId, total_chunks: 2, offset: 0, limit: 25, has_more: false, chunks: [{ chunk_index: 0, content: "Revenue increased in the second quarter." }, { chunk_index: 1, content: "Operating costs remained stable." }] });
      return;
    }
    if (path === `/documents/${documentId}/quality`) {
      await json(route, { extraction_method: "pdf_text", extraction_coverage_score: 1, ocr_used: true, vision_used: false, warnings: [], total_chunks: 2, low_quality_chunks: 0, page_numbers: [1, 2], missing_page_numbers: [] });
      return;
    }
    if (path === `/documents/${documentId}/comments`) {
      await json(route, []);
      return;
    }
    if (path === `/documents/${documentId}/versions`) {
      await json(route, { root_document_id: documentId, versions: [{ document_id: documentId, version: 1, created_at: documentRecord.created_at, sha256_hash: documentRecord.sha256_hash, status: "indexed" }] });
      return;
    }
    if (path === `/documents/${documentId}/full-text`) {
      await json(route, { content: "Confidential quarterly report content." });
      return;
    }
    if (path === `/documents/${documentId}/actions` && request.method() === "POST") {
      await json(route, { answer: "Revenue increased in the second quarter.", citations: [{ page_number: 2, chunk_index: 0 }] });
      return;
    }
    if (path.startsWith(`/documents/${documentId}/pages/`) && path.endsWith("/thumbnail")) {
      await route.fulfill({ status: 200, contentType: "image/svg+xml", body: "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"80\" height=\"100\"><rect width=\"80\" height=\"100\" fill=\"#d1fae5\"/></svg>" });
      return;
    }
    // Preserve the real shell APIs (notifications, profile, realtime setup,
    // etc.). Only Documents Hub contracts are mocked by this workflow suite.
    await route.continue();
  });
}

test.describe("Documents Hub production workflows", () => {
  test("reviews quarantined documents from the Hub", async ({ authenticatedPage }) => {
    await mockDocumentHub(authenticatedPage);
    await authenticatedPage.goto("/dashboard/documents");
    await expect(authenticatedPage.getByRole("heading", { name: "Documents Hub" })).toBeVisible();
    await expect(authenticatedPage.getByRole("link", { name: "Open quarterly-report.pdf" }).first()).toBeVisible({ timeout: 10000 });
    const quarantineResponse = authenticatedPage.waitForResponse((response) => response.url().includes("/api/v1/documents?quarantined=true"));
    await authenticatedPage.getByRole("button", { name: "Review quarantine" }).click();
    const quarantinePayload = await quarantineResponse;
    await expect(quarantinePayload.status()).toBe(200);
    await expect(quarantinePayload.json()).resolves.toMatchObject({ items: [{ filename: "quarterly-report.pdf" }] });
    await expect(authenticatedPage.getByText("Showing quarantine")).toBeVisible();
    await expect(authenticatedPage.getByText("Quarantined").first()).toBeVisible();
  });

  test("shows webhook delivery history in organization controls", async ({ authenticatedPage }) => {
    await mockDocumentHub(authenticatedPage);
    await authenticatedPage.goto("/dashboard/documents");
    await authenticatedPage.getByRole("button", { name: "Manage" }).click();
    await authenticatedPage.getByRole("link", { name: "Open page" }).last().click();
    await expect(authenticatedPage.getByRole("heading", { name: "Webhooks", exact: true })).toBeVisible();
    await authenticatedPage.getByRole("button", { name: "Refresh delivery history" }).click();
    await expect(authenticatedPage.getByText("document.indexed")).toBeVisible();
    await expect(authenticatedPage.getByText(/delivered · 1 attempts/)).toBeVisible();
  });

  test("creates and resolves an expiring secure share link", async ({ authenticatedPage }) => {
    await mockDocumentHub(authenticatedPage);
    await authenticatedPage.goto(`/dashboard/documents/${documentId}`);
    await authenticatedPage.getByRole("button", { name: "Create 24h link" }).click();
    await expect(authenticatedPage.getByText(/share-token-e2e/)).toBeVisible();
    await authenticatedPage.goto(`/share/${shareId}?token=share-token-e2e`);
    await expect(authenticatedPage.getByRole("heading", { name: "Shared document" })).toBeVisible();
    await expect(authenticatedPage.getByRole("heading", { name: "quarterly-report.pdf" })).toBeVisible();
    await expect(authenticatedPage.getByText("Confidential quarterly report content.")).toBeVisible();
  });

  test("opens citation page preview and supports zoom controls", async ({ authenticatedPage }) => {
    await mockDocumentHub(authenticatedPage);
    await authenticatedPage.goto(`/dashboard/documents/${documentId}`);
    await authenticatedPage.getByRole("button", { name: "Run grounded action" }).click();
    await authenticatedPage.getByRole("button", { name: "Source 1 · p.2" }).click();
    await expect(authenticatedPage.getByRole("dialog", { name: "PDF page 2 preview" })).toBeVisible();
    await expect(authenticatedPage.getByRole("dialog", { name: "PDF page 2 preview" }).getByText("Page 2")).toBeVisible();
    await authenticatedPage.getByRole("button", { name: "Zoom in" }).click();
    await expect(authenticatedPage.getByRole("dialog", { name: "PDF page 2 preview" }).getByText("125%")).toBeVisible();
  });
});
