import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchWithAuthMock } = vi.hoisted(() => ({ fetchWithAuthMock: vi.fn() }));

vi.mock("@/lib/api", () => ({ fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args) }));

import DeepSpaceComposer from "../app/dashboard/deepspace/_components/DeepSpaceComposer";

describe("DeepSpaceComposer file extraction status", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:scan-preview"),
    });
    fetchWithAuthMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      const method = options?.method ?? "GET";
      if (path.endsWith("/entries"))
        return {
          ok: true,
          json: async () => ({
            files: [
              {
                id: "saved-file-1",
                name: "saved-scan.png",
                content_type: "image/png",
                size_bytes: 12,
                extraction_status: {
                  state: "no_text",
                  text_available: false,
                  extraction_method: "image_ocr",
                  ocr_used: true,
                  vision_used: false,
                  coverage_score: 0,
                  error_code: null,
                },
              },
            ],
          }),
        };
      const payload =
        method === "POST" && path.endsWith("/uploads")
          ? {
              id: "upload-1",
              chunk_size: 1024,
              total_chunks: 1,
              received_chunks: [],
              status: "uploading",
            }
          : method === "PUT"
            ? { id: "upload-1", chunk_size: 1024, total_chunks: 1, received_chunks: [0] }
            : method === "POST"
              ? {
                  id: "upload-1",
                  status: "completed",
                  file_id: "file-1",
                  extraction_status: {
                    state: "extracted",
                    text_available: true,
                    extraction_method: "image_ocr",
                    ocr_used: true,
                    vision_used: false,
                    coverage_score: 0.9,
                    error_code: null,
                  },
                }
              : {
                  id: "upload-1",
                  status: "completed",
                  file_id: "file-1",
                  extraction_status: {
                    state: "extracted",
                    text_available: true,
                    extraction_method: "image_ocr",
                    ocr_used: true,
                    vision_used: false,
                    coverage_score: 0.9,
                    error_code: null,
                  },
                };
      return { ok: true, json: async () => payload };
    });
  });

  it("shows that upload-time OCR ran on a completed image attachment", async () => {
    render(
      <DeepSpaceComposer
        conversationId="conversation-1"
        query=""
        isStreaming={false}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    const input = document.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    fireEvent.change(input!, {
      target: { files: [new File(["image"], "scan.png", { type: "image/png" })] },
    });

    expect(await screen.findByText("Text extracted · OCR used")).toBeInTheDocument();
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      "/deepspace/library/conversation-1/uploads",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("keeps pasted files distinct and submits their metadata in attachment order", async () => {
    let uploadNumber = 0;
    const uploadNames = new Map<string, string>();
    fetchWithAuthMock.mockImplementation(
      async (path: string, options?: { method?: string; body?: string }) => {
        const method = options?.method ?? "GET";
        if (method === "POST" && path.endsWith("/uploads")) {
          uploadNumber += 1;
          const uploadId = `upload-${uploadNumber}`;
          const name = uploadNumber === 1 ? "screenshot.png" : "screenshot (2).png";
          uploadNames.set(uploadId, name);
          return {
            ok: true,
            json: async () => ({
              id: uploadId,
              name,
              chunk_size: 1024,
              total_chunks: 1,
              received_chunks: [],
              status: "pending",
            }),
          };
        }
        if (method === "PUT") {
          const uploadId = path.includes("upload-1") ? "upload-1" : "upload-2";
          return {
            ok: true,
            json: async () => ({
              id: uploadId,
              name: uploadNames.get(uploadId),
              chunk_size: 1024,
              total_chunks: 1,
              received_chunks: [0],
              status: "uploading",
            }),
          };
        }
        if (method === "POST" && path.endsWith("/complete")) {
          const uploadId = path.includes("upload-1") ? "upload-1" : "upload-2";
          const index = uploadId === "upload-1" ? 1 : 2;
          return {
            ok: true,
            json: async () => ({
              id: uploadId,
              name: uploadNames.get(uploadId),
              status: "completed",
              file_id: `file-${index}`,
            }),
          };
        }
        return { ok: true, json: async () => ({}) };
      },
    );
    const onSubmit = vi.fn();

    render(
      <DeepSpaceComposer
        conversationId="conversation-1"
        query=""
        isStreaming={false}
        onQueryChange={vi.fn()}
        onSubmit={onSubmit}
        onStop={vi.fn()}
      />,
    );

    fireEvent.paste(screen.getByPlaceholderText("Message DeepSpace..."), {
      clipboardData: {
        files: [
          new File(["first image"], "screenshot.png", { type: "image/png" }),
          new File(["second image"], "screenshot.png", { type: "image/png" }),
        ],
      },
    });

    await waitFor(() => expect(screen.getByTitle("Preview screenshot.png")).toBeInTheDocument());
    await waitFor(() =>
      expect(screen.getByTitle("Preview screenshot (2).png")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));

    expect(onSubmit).toHaveBeenCalledWith([
      {
        id: "file-1",
        name: "screenshot.png",
        content_type: "image/png",
        size_bytes: 11,
      },
      {
        id: "file-2",
        name: "screenshot (2).png",
        content_type: "image/png",
        size_bytes: 12,
      },
    ]);
    const createCalls = fetchWithAuthMock.mock.calls.filter(
      ([path, options]) =>
        path === "/deepspace/library/conversation-1/uploads" && options?.method === "POST",
    );
    expect(createCalls).toHaveLength(2);
    expect(
      createCalls.map(([, options]) => JSON.parse(options!.body as string).rename_on_conflict),
    ).toEqual([true, true]);
  });

  it("keeps saved extraction status when attaching an existing Library file", async () => {
    render(
      <DeepSpaceComposer
        conversationId="conversation-1"
        query=""
        isStreaming={false}
        onQueryChange={vi.fn()}
        onSubmit={vi.fn()}
        onStop={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Attach an existing Library file" }));
    fireEvent.click(await screen.findByRole("button", { name: "saved-scan.png" }));

    expect(screen.getByText("No readable text found")).toBeInTheDocument();
  });
});
