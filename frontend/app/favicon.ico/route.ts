import { readFile } from "node:fs/promises";
import path from "node:path";

export async function GET(): Promise<Response> {
  const icon = await readFile(path.join(process.cwd(), "public", "logo_icon.svg"));
  return new Response(icon, {
    headers: {
      "Cache-Control": "public, max-age=86400, immutable",
      "Content-Type": "image/svg+xml",
    },
  });
}
