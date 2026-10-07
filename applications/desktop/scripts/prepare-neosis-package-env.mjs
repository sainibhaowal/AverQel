import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseEnv } from "node:util";
import { fileURLToPath } from "node:url";

const PREPARATION_ORIGIN = "https://test.example.com";
const PLATFORM_FILES = {
  linux: "linux",
  win32: "windows",
};

function requireHttpsOrigin(value, setting) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`NeoSIS package template: ${setting} must be an HTTPS origin`);
  }
  if (
    url.protocol !== "https:" ||
    url.username !== "" ||
    url.password !== "" ||
    url.pathname !== "/" ||
    url.search !== "" ||
    url.hash !== ""
  ) {
    throw new Error(`NeoSIS package template: ${setting} must be an HTTPS origin without credentials, path, query, or fragment`);
  }
}

function readTemplate(template) {
  let values;
  try {
    values = parseEnv(template.replace(/^\uFEFF/u, ""));
  } catch {
    throw new Error("NeoSIS package template: invalid dotenv syntax");
  }

  const appId = values.NEOSIS_DESKTOP_APP_ID?.trim();
  if (!appId) {
    throw new Error("NeoSIS package template: NEOSIS_DESKTOP_APP_ID is required");
  }
  if (values.NEOSIS_DESKTOP_AUTO_UPDATE_ENV !== "test") {
    throw new Error("NeoSIS package template: runtime preparation requires test update mode");
  }

  let policy;
  try {
    policy = JSON.parse(values.NEOSIS_DESKTOP_MANDATORY_UPDATE_CONFIG);
  } catch {
    throw new Error("NeoSIS package template: mandatory-update config must be valid JSON");
  }
  if (
    typeof policy !== "object" ||
    policy === null ||
    Array.isArray(policy) ||
    "origin" in policy ||
    "authentication" in policy ||
    !Array.isArray(policy.allowedAuthOrigins) ||
    policy.allowedAuthOrigins.length === 0
  ) {
    throw new Error("NeoSIS package template: test policy requires allowedAuthOrigins and cannot set origin or authentication");
  }
  for (const origin of policy.allowedAuthOrigins) {
    requireHttpsOrigin(origin, "allowedAuthOrigins");
  }

  return { appId, policy };
}

export async function prepareNeosisPackageEnvironment(neosisRoot, platform) {
  const templatePlatform = PLATFORM_FILES[platform];
  if (templatePlatform === undefined) {
    throw new Error(`NeoSIS runtime preparation does not support ${platform}`);
  }

  const desktopRoot = path.resolve(neosisRoot, "apps", "desktop");
  const templatePath = path.join(desktopRoot, `.env.${templatePlatform}.example`);
  const outputPath = path.join(desktopRoot, `.env.${templatePlatform}`);
  let template;
  try {
    template = await readFile(templatePath, "utf8");
  } catch {
    throw new Error(`NeoSIS package template is missing: ${templatePath}`);
  }

  const { appId, policy } = readTemplate(template);
  const contents = [
    `NEOSIS_DESKTOP_APP_ID=${appId}`,
    "NEOSIS_DESKTOP_AUTO_UPDATE_ENV=test",
    `NEOSIS_DESKTOP_MANDATORY_UPDATE_TEST_ORIGIN=${PREPARATION_ORIGIN}`,
    `NEOSIS_DESKTOP_MANDATORY_UPDATE_CONFIG='${JSON.stringify(policy)}'`,
    "",
  ].join("\n");

  try {
    await writeFile(outputPath, contents, { encoding: "utf8", flag: "wx", mode: 0o600 });
  } catch (error) {
    if (error?.code === "EEXIST") {
      throw new Error(`NeoSIS package configuration already exists; refusing to overwrite ${outputPath}`);
    }
    throw error;
  }

  return outputPath;
}

const entryPath = process.argv[1] === undefined ? undefined : path.resolve(process.argv[1]);
if (entryPath === fileURLToPath(import.meta.url)) {
  const neosisRoot = process.argv[2];
  if (!neosisRoot) {
    throw new Error("Usage: node prepare-neosis-package-env.mjs <pinned-NeoSIS-checkout>");
  }
  const outputPath = await prepareNeosisPackageEnvironment(neosisRoot, process.platform);
  process.stdout.write(`Created temporary NeoSIS ${PLATFORM_FILES[process.platform]} runtime-preparation configuration.\n`);
  process.stdout.write(`${outputPath}\n`);
}
