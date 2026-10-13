const assert = require("node:assert/strict");
const { createHash } = require("node:crypto");
const {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  REQUIRED_ENTRY,
  verifyNeosisRuntime,
} = require("../scripts/verify-neosis-runtime.cjs");
const TEST_PLATFORM = process.platform;

const temporaryRoots = [];

test.afterEach(() => {
  for (const root of temporaryRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true });
  }
});

function createRuntimeFixture(overrides = {}) {
  const root = mkdtempSync(path.join(os.tmpdir(), "averqel-neosis-runtime-"));
  temporaryRoots.push(root);
  const entryPath = path.join(root, ...REQUIRED_ENTRY.split("/"));
  const supportPath = path.join(
    root,
    "node_modules",
    "@averqel",
    "neosis",
    "lib",
    "support.js",
  );
  mkdirSync(path.dirname(entryPath), { recursive: true });
  writeFileSync(entryPath, "#!/usr/bin/env node\n");
  chmodSync(entryPath, 0o755);
  writeFileSync(supportPath, "module.exports = true;\n");
  writeFileSync(
    path.join(root, "averqel-local-profile.patch.yml"),
    "profile: local\n",
  );

  const files = [entryPath, supportPath].map((absolutePath) => {
    const relativePath = path
      .relative(root, absolutePath)
      .split(path.sep)
      .join("/");
    const body = readFileSync(absolutePath);
    return {
      path: relativePath,
      bytes: body.byteLength,
      sha256: createHash("sha256").update(body).digest("hex"),
      executable: TEST_PLATFORM !== "win32" && relativePath === REQUIRED_ENTRY,
    };
  });
  const descriptor = {
    schemaVersion: 1,
    release: { version: "0.2.0-test" },
    platform: TEST_PLATFORM,
    arch: "x64",
    files,
    ...overrides,
  };
  writeFileSync(
    path.join(root, "desktop-runtime.json"),
    JSON.stringify(descriptor),
  );
  return { root, entryPath, descriptor };
}

test("verifies every file, checksum, executable bit, and profile in a packaged runtime", async () => {
  const { root } = createRuntimeFixture();

  const result = await verifyNeosisRuntime(root, {
    platform: TEST_PLATFORM,
    arch: "x64",
  });

  assert.equal(result.fileCount, 2);
  assert.equal(result.manifestVersion, "0.2.0-test");
  assert.ok(result.totalBytes > 0);
  assert.equal(existsSync(result.profilePatchPath), true);
});

test("rejects a runtime when its launcher is missing", async () => {
  const { root, entryPath } = createRuntimeFixture();
  rmSync(entryPath);

  await assert.rejects(
    verifyNeosisRuntime(root, { platform: TEST_PLATFORM, arch: "x64" }),
    /runtime is missing a manifest file \(node_modules\/@averqel\/neosis\/lib\/bin\.js\)/u,
  );
});

test("rejects changed bytes even when the launcher still exists", async () => {
  const { root, entryPath } = createRuntimeFixture();
  writeFileSync(entryPath, Buffer.alloc(statSync(entryPath).size, 0x78));
  chmodSync(entryPath, 0o755);

  await assert.rejects(
    verifyNeosisRuntime(root, { platform: TEST_PLATFORM, arch: "x64" }),
    /runtime file checksum does not match its manifest/u,
  );
});

test(
  "rejects a POSIX runtime entry point without its executable permission",
  {
    skip:
      TEST_PLATFORM === "win32"
        ? "Windows does not expose Unix executable bits"
        : false,
  },
  async () => {
    const { root, entryPath } = createRuntimeFixture();
    chmodSync(entryPath, 0o644);

    await assert.rejects(
      verifyNeosisRuntime(root, { platform: TEST_PLATFORM, arch: "x64" }),
      /runtime executable permission is missing/u,
    );
  },
);

test("rejects unsafe manifest paths and platform mismatches", async () => {
  const unsafe = createRuntimeFixture();
  unsafe.descriptor.files[1].path = "../outside.js";
  writeFileSync(
    path.join(unsafe.root, "desktop-runtime.json"),
    JSON.stringify(unsafe.descriptor),
  );
  await assert.rejects(
    verifyNeosisRuntime(unsafe.root, { platform: TEST_PLATFORM, arch: "x64" }),
    /unsafe file path/u,
  );

  const wrongPlatform = createRuntimeFixture();
  const expectedWrongPlatform = TEST_PLATFORM === "linux" ? "win32" : "linux";
  await assert.rejects(
    verifyNeosisRuntime(wrongPlatform.root, {
      platform: expectedWrongPlatform,
      arch: "x64",
    }),
    new RegExp(
      `runtime targets ${TEST_PLATFORM}, expected ${expectedWrongPlatform}`,
      "u",
    ),
  );

  const wrongArch = createRuntimeFixture();
  await assert.rejects(
    verifyNeosisRuntime(wrongArch.root, {
      platform: TEST_PLATFORM,
      arch: "arm64",
    }),
    /runtime targets x64, expected arm64/u,
  );
});
