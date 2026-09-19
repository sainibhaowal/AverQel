import http from "node:http";
import net from "node:net";
import { chromium } from "playwright-core";

const token = process.env.RESEARCH_RENDERER_TOKEN;
if (!token || token.length < 32) throw new Error("RESEARCH_RENDERER_TOKEN must be at least 32 characters.");
const proxy = process.env.RESEARCH_EGRESS_PROXY || "http://research-egress-proxy:3128";
const port = Number(process.env.PORT || 3010);
const blockedNames = /(^|\.)(localhost|host\.docker\.internal|api|postgres|redis|minio|clamav|inference|searxng)$/i;

function privateAddress(address) {
  if (net.isIPv4(address)) return /^(0\.|10\.|127\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)/.test(address);
  const value = address.toLowerCase();
  return value === "::1" || value.startsWith("fc") || value.startsWith("fd") || value.startsWith("fe80:") || value.startsWith("::ffff:127.");
}
async function publicHttpUrl(raw) {
  const target = new URL(raw);
  if (target.protocol !== "https:" || !target.hostname || blockedNames.test(target.hostname)) throw new Error("Blocked URL target.");
  // Host names are resolved by the only outbound path, Squid. Its destination
  // ACL evaluates the resolved address and blocks private/rebinding targets.
  // Explicit literal IP addresses are rejected here before Chromium sees them.
  if (net.isIP(target.hostname) && privateAddress(target.hostname)) throw new Error("Blocked non-public address.");
  return target.toString();
}
function response(res, status, payload, contentType = "application/json") {
  res.writeHead(status, { "content-type": contentType, "cache-control": "no-store", "x-content-type-options": "nosniff" });
  res.end(payload);
}
const browser = await chromium.launch({ headless: true, proxy: { server: proxy }, args: ["--disable-dev-shm-usage", "--disable-extensions", "--no-first-run"] });
const server = http.createServer(async (req, res) => {
  if (req.method !== "POST" || req.url !== "/content" || req.headers.authorization !== `Bearer ${token}`) return response(res, 404, "{}");
  let body = "";
  for await (const chunk of req) { body += chunk; if (body.length > 16_384) return response(res, 413, JSON.stringify({ error: "request too large" })); }
  try {
    const input = JSON.parse(body);
    const target = await publicHttpUrl(String(input.url || ""));
    const context = await browser.newContext({ javaScriptEnabled: true, acceptDownloads: false, serviceWorkers: "block" });
    const page = await context.newPage();
    await page.route("**/*", async route => {
      const requestUrl = route.request().url();
      if (/^(about|blob|data):$/i.test(new URL(requestUrl).protocol)) return route.continue();
      try { await publicHttpUrl(requestUrl); await route.continue(); } catch { await route.abort(); }
    });
    await page.goto(target, { waitUntil: "domcontentloaded", timeout: 15_000 });
    // Many public pages hydrate after DOMContentLoaded. Give bounded client
    // rendering a chance to settle without allowing an unbounded page wait.
    await page.waitForLoadState("networkidle", { timeout: 6_000 }).catch(() => {});
    await page.waitForTimeout(1_000);
    const html = (await page.content()).slice(0, 2_000_000);
    await context.close();
    response(res, 200, html, "text/html; charset=utf-8");
  } catch (error) {
    console.warn("Renderer request rejected or failed:", error instanceof Error ? error.message : "unknown error");
    response(res, 422, JSON.stringify({ error: "render failed" }));
  }
});
server.listen(port, "0.0.0.0");
