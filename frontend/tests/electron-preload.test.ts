import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";
import { JSDOM } from "jsdom";
import { describe, expect, it, vi } from "vitest";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const preloadSource = readFileSync(
  resolve(repositoryRoot, "applications/desktop/electron/preload.cjs"),
  "utf-8",
);

function bootPreload(workspace: "averqel" | "neosis", url: string) {
  const dom = new JSDOM(
    "<!doctype html><html><head></head><body><div id='app'></div></body></html>",
    {
      url,
    },
  );
  const exposed: Record<string, unknown> = {};
  const invoke = vi.fn(async (channel: string) => {
    if (channel === "workspace:current") return workspace;
    return { ok: true };
  });
  runInNewContext(preloadSource, {
    clearTimeout,
    document: dom.window.document,
    history: dom.window.history,
    location: dom.window.location,
    MutationObserver: dom.window.MutationObserver,
    process: { platform: "linux" },
    queueMicrotask,
    require: (name: string) => {
      if (name !== "electron") throw new Error(`Unexpected preload import: ${name}`);
      return {
        contextBridge: {
          exposeInMainWorld: (key: string, value: unknown) => {
            exposed[key] = value;
          },
        },
        ipcRenderer: { invoke },
      };
    },
    setTimeout,
    URL,
    URLSearchParams,
    window: dom.window,
  });
  dom.window.dispatchEvent(new dom.window.Event("DOMContentLoaded"));

  return { dom, exposed, invoke };
}

async function waitForTitlebarButton(dom: JSDOM): Promise<HTMLButtonElement> {
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const button = dom.window.document.querySelector<HTMLButtonElement>(
      "#averqel-electron-titlebar button",
    );
    if (button) return button;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 0));
  }
  throw new Error("Electron workspace switch was not mounted.");
}

describe("Electron titlebar workspace switch", () => {
  it("offers NeoSIS from AverQel and sends the open request", async () => {
    const { dom, invoke } = bootPreload("averqel", "https://averqel.com/");
    const button = await waitForTitlebarButton(dom);

    expect(button.getAttribute("aria-label")).toBe("Switch to NeoSIS workspace");
    button.click();
    await vi.waitFor(() => expect(invoke).toHaveBeenCalledWith("workspace:open-neosis"));
    dom.window.close();
  });

  it("offers AverQel from NeoSIS and sends the return request", async () => {
    const { dom, invoke } = bootPreload("neosis", "http://127.0.0.1:43127/?token=test-token");
    const button = await waitForTitlebarButton(dom);

    expect(button.getAttribute("aria-label")).toBe("Switch to AverQel workspace");
    button.click();
    await vi.waitFor(() => expect(invoke).toHaveBeenCalledWith("workspace:open-averqel"));
    dom.window.close();
  });
});
