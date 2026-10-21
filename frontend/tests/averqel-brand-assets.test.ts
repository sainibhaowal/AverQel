import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";

const publicRoot = resolve(process.cwd(), "public");

it("keeps the requested AverQel icon as the shared web brand asset", () => {
  const icon = readFileSync(resolve(publicRoot, "brand/AverQel_Icon.svg"), "utf8");
  const logoComponent = readFileSync(
    resolve(process.cwd(), "app/components/ui/AverQelLogo.tsx"),
    "utf8",
  );
  const layout = readFileSync(resolve(process.cwd(), "app/layout.tsx"), "utf8");

  expect(icon).toContain('<svg xmlns="http://www.w3.org/2000/svg"');
  expect(icon).toContain('viewBox="0 0 1202 675"');
  expect(logoComponent).toContain('"/AverQel%20Logo/AverQel_Icon.svg"');
  expect(layout).toContain('icon: "/brand/AverQel_Icon.svg"');
});

it("uses the supplied AverQel text logo throughout the shared wordmark components", () => {
  const textLogo = readFileSync(resolve(publicRoot, "brand/AverQel_Text.svg"), "utf8");
  const exactLogo = readFileSync(resolve(publicRoot, "brand/AverQel_Exact_Logo.svg"), "utf8");
  const wordmark = readFileSync(
    resolve(process.cwd(), "app/components/ui/AverQelWordmark.tsx"),
    "utf8",
  );
  const logoComponent = readFileSync(
    resolve(process.cwd(), "app/components/ui/AverQelLogo.tsx"),
    "utf8",
  );
  const titleBar = readFileSync(resolve(process.cwd(), "components/layout/TitleBar.tsx"), "utf8");
  const docsShell = readFileSync(
    resolve(process.cwd(), "app/documentation/_components/DocsShell.tsx"),
    "utf8",
  );
  const deepSpaceMark = readFileSync(
    resolve(process.cwd(), "app/components/ui/DeepSpaceMark.tsx"),
    "utf8",
  );
  const dashboardLayout = readFileSync(resolve(process.cwd(), "app/dashboard/layout.tsx"), "utf8");
  const loginPage = readFileSync(resolve(process.cwd(), "app/auth/login/page.tsx"), "utf8");
  const exactBrand = readFileSync(
    resolve(process.cwd(), "app/components/ui/AverQelExactBrand.tsx"),
    "utf8",
  );
  const qelConnectMark = readFileSync(
    resolve(process.cwd(), "app/components/ui/QelConnectMark.tsx"),
    "utf8",
  );
  const globalStyles = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");

  expect(textLogo).toContain('aria-label="AverQel scalable text-only wordmark"');
  expect(textLogo).toContain("<path");
  expect(exactLogo).toContain('aria-label="AverQel complete logo"');
  expect(wordmark).toContain('const TEXT_LOGO_SOURCE = "/brand/AverQel_Text.svg"');
  expect(wordmark).not.toContain("averqel-text-remove-white");
  expect(logoComponent).toContain('import AverQelWordmark from "./AverQelWordmark"');
  expect(logoComponent).toContain("<AverQelWordmark size={wordmarkSize} />");
  expect(logoComponent).toContain("data-brand-lockup");
  expect(logoComponent).toContain("markWidth: 92");
  expect(logoComponent).toContain('gap: "0rem"');
  expect(titleBar).toContain('import AverQelWordmark from "@/app/components/ui/AverQelWordmark"');
  expect(titleBar).toContain('src="/AverQel%20Logo/AverQel_Icon.svg"');
  expect(titleBar).toContain('<AverQelWordmark size="footer" />');
  expect(docsShell).toContain('import AverQelLogo from "../../components/ui/AverQelLogo"');
  expect(docsShell).not.toContain("AverQel OS");
  expect(deepSpaceMark).toContain(
    'source = "/DeepSpace Logo/DeepSpace_Logo_Only_NoBlack_Exact.svg"',
  );
  expect(dashboardLayout).toContain(
    'source="/DeepSpace Logo/DeepSpace_Logo_Only_NoBlack_Exact.svg"',
  );
  expect(exactBrand).toContain('src="/AverQel%20Logo/AverQel_Icon.svg"');
  expect(exactBrand).toContain('import AverQelWordmark from "./AverQelWordmark"');
  expect(exactBrand).toContain('<AverQelWordmark size="hero"');
  expect(exactBrand).toContain('className="login-brand-wordmark"');
  expect(exactBrand).toContain('className="login-exact-logo--animated login-exact-logo--aver"');
  expect(exactBrand).toContain('className="login-exact-logo--animated login-exact-logo--el"');
  expect(exactBrand).toContain("INTELLIGENCE ALL YOU NEED");
  expect(loginPage).not.toContain('<AverQelLogo size="hero" />');
  expect(globalStyles).toContain(".dark .averqel-wordmark__svg");
  expect(globalStyles).toContain("@keyframes login-brand-rgb");
  expect(globalStyles).toContain(".login-exact-logo--animated");
  expect(qelConnectMark).toContain("qel-connect-mark");
  expect(globalStyles).toContain(".qel-connect-mark");
  expect(globalStyles).toContain("filter: brightness(0.62) saturate(1.2) contrast(1.18);");
  expect(globalStyles).toContain(".dark .qel-connect-mark");
  expect(globalStyles).toContain(".dark .qel-connect-mark {\n  filter: none;");
});

it("does not leave the retired root logo aliases as active brand files", () => {
  expect(existsSync(resolve(publicRoot, "logo_icon.svg"))).toBe(false);
  expect(existsSync(resolve(publicRoot, "logo_icon.png"))).toBe(false);
  expect(existsSync(resolve(publicRoot, "brand/logo_icon.svg"))).toBe(false);
  expect(existsSync(resolve(publicRoot, "brand/logo_icon.png"))).toBe(false);
  expect(existsSync(resolve(publicRoot, "brand/logo_icon_512.png"))).toBe(false);
});

it("keeps the Qel Connect mark on the supplied telemetry parabola asset", () => {
  const mark = readFileSync(
    resolve(publicRoot, "AverQel Logo/deepspace-telemetry-parabola.svg"),
    "utf8",
  );
  const markComponent = readFileSync(
    resolve(process.cwd(), "app/components/ui/QelConnectMark.tsx"),
    "utf8",
  );
  const brand = readFileSync(resolve(process.cwd(), "lib/brand.ts"), "utf8");

  expect(mark).toContain("<svg");
  expect(brand).toContain(
    'QEL_CONNECT_MARK_SOURCE = "/AverQel Logo/deepspace-telemetry-parabola.svg"',
  );
  expect(markComponent).toContain('aria-hidden="true"');
});
