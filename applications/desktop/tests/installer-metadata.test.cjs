const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const desktopRoot = path.resolve(__dirname, "..");
const packageConfig = JSON.parse(
  readFileSync(path.join(desktopRoot, "package.json"), "utf8"),
);
const appstream = readFileSync(
  path.join(desktopRoot, "assets/com.averqel.app.metainfo.xml"),
  "utf8",
);
const frontendLayout = readFileSync(
  path.resolve(desktopRoot, "..", "..", "frontend", "app", "layout.tsx"),
  "utf8",
);
const frontendRoot = path.resolve(desktopRoot, "..", "..", "frontend");
const frontendBrandRoot = path.resolve(desktopRoot, "..", "..", "frontend", "public", "brand");

function readPngDimensions(buffer) {
  assert.equal(buffer.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

test("keeps the stable Debian package ID and configures the human-facing installer name", () => {
  assert.equal(packageConfig.name, "averqel-desktop");
  assert.equal(packageConfig.build.productName, "AverQel");
  assert.equal(
    packageConfig.build.linux.desktop.entry.Name,
    "AverQel",
  );
  assert.ok(
    packageConfig.build.deb.fpm.includes(
      "assets/com.averqel.app.metainfo.xml=/usr/share/metainfo/com.averqel.app.metainfo.xml",
    ),
  );
});

test("uses readable ASCII installer text and matching AppStream identity", () => {
  const { synopsis, description } = packageConfig.build.linux;
  assert.equal(
    synopsis,
    "AI workspace for documents, grounded answers, agent workflows, and team messaging",
  );
  assert.equal(
    description,
    "AverQel is an AI workspace for document management and search, source-grounded questions, DeepSpace conversations and agent workflows, configurable model providers, approved connected apps, Qel Connect shared spaces and messaging, feedback and support, and tenant-aware security and administration. Provider and app integrations require configuration; Qel Connect is experimental beta.",
  );
  assert.equal(packageConfig.description, description);
  assert.doesNotMatch(synopsis, /[^\x00-\x7f]/);
  assert.doesNotMatch(description, /[^\x00-\x7f]/);
  assert.doesNotMatch(`${synopsis} ${description}`, /\?\?/);
  assert.ok(appstream.includes(`<summary>${synopsis}</summary>`));
  assert.ok(appstream.includes(`<p>${description}</p>`));
  assert.ok(frontendLayout.includes(`"${synopsis}"`));
  assert.ok(frontendLayout.includes(`"${description}"`));
  assert.match(appstream, /<id>com\.averqel\.app<\/id>/);
  assert.match(appstream, /<name>AverQel<\/name>/);
  assert.match(
    appstream,
    /<launchable type="desktop-id">AverQel\.desktop<\/launchable>/,
  );
});

test("ships the shared AverQel mark in every desktop icon format", () => {
  const iconPng = readFileSync(path.join(desktopRoot, "assets/icon.png"));
  const iconIco = readFileSync(path.join(desktopRoot, "assets/icon.ico"));
  const iconIcns = readFileSync(path.join(desktopRoot, "assets/icon.icns"));
  const dimensions = readPngDimensions(iconPng);

  assert.deepEqual(dimensions, { width: 512, height: 512 });
  assert.equal(iconIco.subarray(0, 4).toString("hex"), "00000100");
  assert.equal(iconIcns.subarray(0, 4).toString("ascii"), "icns");
});

test("stages both canonical SVG brand sources in the desktop package", () => {
  assert.equal(
    packageConfig.scripts["prepare:brand-assets"],
    "node scripts/prepare-brand-assets.mjs",
  );
  const brandSources = {
    "AverQel_Icon.svg": path.join(
      frontendRoot,
      "public",
      "AverQel Logo",
      "AverQel_Icon.svg",
    ),
    "AverQel_Text.svg": path.join(frontendBrandRoot, "AverQel_Text.svg"),
  };
  for (const [fileName, source] of Object.entries(brandSources)) {
    assert.equal(
      sha256(readFileSync(path.join(desktopRoot, "assets", "brand", fileName))),
      sha256(readFileSync(source)),
      `${fileName} must be copied from the canonical frontend brand source`,
    );
  }
});
