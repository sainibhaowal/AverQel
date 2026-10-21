import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(scriptDirectory, "..");
const workspaceRoot = path.resolve(desktopRoot, "..", "..");
const targetRoot = path.join(desktopRoot, "assets", "brand");
const brandAssets = [
  {
    source: path.join(workspaceRoot, "frontend", "public", "AverQel Logo", "AverQel_Icon.svg"),
    target: "AverQel_Icon.svg",
  },
  {
    source: path.join(workspaceRoot, "frontend", "public", "brand", "AverQel_Text.svg"),
    target: "AverQel_Text.svg",
  },
];

mkdirSync(targetRoot, { recursive: true });

for (const { source, target: targetFileName } of brandAssets) {
  const target = path.join(targetRoot, targetFileName);
  if (!existsSync(source)) {
    throw new Error(`The canonical AverQel brand asset is missing: ${source}`);
  }
  copyFileSync(source, target);
}

console.log(`Staged ${brandAssets.length} canonical AverQel brand assets for Electron.`);
