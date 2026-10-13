const { createHash } = require("node:crypto");
const {
  createReadStream,
  lstatSync,
  readFileSync,
  readdirSync,
} = require("node:fs");
const path = require("node:path");

const DESCRIPTOR_FILE = "desktop-runtime.json";
const PROFILE_PATCH_FILE = "averqel-local-profile.patch.yml";
const REQUIRED_ENTRY = "node_modules/@averqel/neosis/lib/bin.js";

function fail(message) {
  throw new Error(`NeoSIS package verification failed: ${message}`);
}

function readRegularFile(root, relativePath, label) {
  const absolutePath = path.join(root, ...relativePath.split("/"));
  let stats;
  try {
    stats = lstatSync(absolutePath);
  } catch {
    fail(`${label} is missing (${relativePath}).`);
  }
  if (!stats.isFile()) {
    fail(`${label} is not a regular file (${relativePath}).`);
  }
  return { absolutePath, stats };
}

function hashFile(absolutePath) {
  return new Promise((resolve, reject) => {
    const digest = createHash("sha256");
    const stream = createReadStream(absolutePath);
    stream.on("data", (chunk) => digest.update(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolve(digest.digest("hex")));
  });
}

function validateManifestPath(value) {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.includes("\\") ||
    value.includes(":") ||
    path.posix.isAbsolute(value) ||
    value
      .split("/")
      .some((part) => part === "" || part === "." || part === "..")
  ) {
    fail(
      `runtime manifest contains an unsafe file path (${JSON.stringify(value)}).`,
    );
  }
  return value;
}

function listRuntimeFiles(root) {
  const files = [];
  const visit = (directory, prefix) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const relativePath =
        prefix === "" ? entry.name : `${prefix}/${entry.name}`;
      const absolutePath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        visit(absolutePath, relativePath);
      } else if (entry.isFile()) {
        files.push(relativePath);
      } else {
        fail(
          `runtime contains an unsupported filesystem entry (${relativePath}).`,
        );
      }
    }
  };
  visit(root, "");
  return files;
}

async function verifyNeosisRuntime(rootPath, expected = {}) {
  const root = path.resolve(rootPath);
  let rootStats;
  try {
    rootStats = lstatSync(root);
  } catch {
    fail(`runtime directory is missing (${root}).`);
  }
  if (!rootStats.isDirectory()) {
    fail(`runtime path is not a directory (${root}).`);
  }

  const descriptorFile = readRegularFile(
    root,
    DESCRIPTOR_FILE,
    "runtime manifest",
  );
  let descriptor;
  try {
    descriptor = JSON.parse(readFileSync(descriptorFile.absolutePath, "utf8"));
  } catch {
    fail("runtime manifest is not valid JSON.");
  }

  if (
    descriptor === null ||
    typeof descriptor !== "object" ||
    descriptor.schemaVersion !== 1 ||
    !Array.isArray(descriptor.files) ||
    typeof descriptor.platform !== "string" ||
    typeof descriptor.arch !== "string" ||
    typeof descriptor.release !== "object" ||
    descriptor.release === null ||
    Array.isArray(descriptor.release) ||
    typeof descriptor.release.version !== "string"
  ) {
    fail("runtime manifest has an unsupported or incomplete schema.");
  }
  if (
    expected.platform !== undefined &&
    descriptor.platform !== expected.platform
  ) {
    fail(
      `runtime targets ${descriptor.platform}, expected ${expected.platform}.`,
    );
  }
  if (expected.arch !== undefined && descriptor.arch !== expected.arch) {
    fail(`runtime targets ${descriptor.arch}, expected ${expected.arch}.`);
  }

  const records = new Map();
  for (const record of descriptor.files) {
    if (
      record === null ||
      typeof record !== "object" ||
      !Number.isSafeInteger(record.bytes) ||
      record.bytes < 0 ||
      typeof record.sha256 !== "string" ||
      !/^[a-f0-9]{64}$/u.test(record.sha256) ||
      typeof record.executable !== "boolean"
    ) {
      fail("runtime manifest contains an invalid file record.");
    }
    const relativePath = validateManifestPath(record.path);
    if (relativePath === DESCRIPTOR_FILE || records.has(relativePath)) {
      fail(
        `runtime manifest contains a duplicate or reserved path (${relativePath}).`,
      );
    }
    records.set(relativePath, record);
  }
  if (!records.has(REQUIRED_ENTRY)) {
    fail(
      `runtime manifest does not include the required entry point (${REQUIRED_ENTRY}).`,
    );
  }

  const profilePatch = readRegularFile(
    root,
    PROFILE_PATCH_FILE,
    "AverQel NeoSIS profile",
  );
  const expectedPaths = new Set([
    ...records.keys(),
    DESCRIPTOR_FILE,
    PROFILE_PATCH_FILE,
  ]);
  const actualPaths = listRuntimeFiles(root);
  const actualPathSet = new Set(actualPaths);
  const unexpected = actualPaths.find(
    (relativePath) => !expectedPaths.has(relativePath),
  );
  if (unexpected !== undefined) {
    fail(`runtime contains a file absent from its manifest (${unexpected}).`);
  }
  const missing = [...expectedPaths].find(
    (relativePath) => !actualPathSet.has(relativePath),
  );
  if (missing !== undefined) {
    fail(`runtime is missing a manifest file (${missing}).`);
  }

  const recordPaths = [...records.keys()];
  let nextIndex = 0;
  let firstError;
  const workers = Array.from(
    { length: Math.min(8, records.size) },
    async () => {
      while (firstError === undefined) {
        const relativePath = recordPaths[nextIndex];
        nextIndex += 1;
        if (relativePath === undefined) return;

        const record = records.get(relativePath);
        try {
          const { absolutePath, stats } = readRegularFile(
            root,
            relativePath,
            "runtime file",
          );
          if (stats.size !== record.bytes) {
            fail(
              `runtime file size does not match its manifest (${relativePath}).`,
            );
          }
          if (
            descriptor.platform !== "win32" &&
            record.executable &&
            (stats.mode & 0o111) === 0
          ) {
            fail(`runtime executable permission is missing (${relativePath}).`);
          }
          const actualHash = await hashFile(absolutePath);
          if (actualHash !== record.sha256) {
            fail(
              `runtime file checksum does not match its manifest (${relativePath}).`,
            );
          }
        } catch (error) {
          firstError ??= error;
        }
      }
    },
  );
  await Promise.all(workers);
  if (firstError !== undefined) throw firstError;

  let totalBytes = 0;
  for (const record of records.values()) {
    totalBytes += record.bytes;
    if (!Number.isSafeInteger(totalBytes)) {
      fail("runtime manifest total size exceeds the supported range.");
    }
  }
  return {
    fileCount: records.size,
    totalBytes,
    manifestVersion: descriptor.release.version,
    profilePatchPath: profilePatch.absolutePath,
  };
}

module.exports = { REQUIRED_ENTRY, verifyNeosisRuntime };

if (require.main === module) {
  const [, , root, platform, arch] = process.argv;
  if (root === undefined || platform === undefined || arch === undefined) {
    throw new Error(
      "Usage: node scripts/verify-neosis-runtime.cjs <runtime-dir> <platform> <arch>",
    );
  }

  verifyNeosisRuntime(root, { platform, arch })
    .then(({ fileCount, totalBytes, manifestVersion }) => {
      const mebibytes = (totalBytes / 1024 / 1024).toFixed(1);
      process.stdout.write(
        `Verified NeoSIS ${manifestVersion}: ${fileCount} runtime files, ${mebibytes} MiB (${platform}-${arch}).\n`,
      );
    })
    .catch((error) => {
      process.stderr.write(`${error.message}\n`);
      process.exitCode = 1;
    });
}
