export type LibraryFileKind =
  | "markdown"
  | "code"
  | "diff"
  | "csv"
  | "spreadsheet"
  | "pdf"
  | "docx"
  | "pptx"
  | "image"
  | "svg"
  | "video"
  | "audio"
  | "archive"
  | "text";

const CODE_EXTENSIONS = new Set([
  "py",
  "ts",
  "tsx",
  "js",
  "jsx",
  "mjs",
  "cjs",
  "java",
  "c",
  "h",
  "cc",
  "cpp",
  "cxx",
  "hpp",
  "go",
  "rs",
  "sql",
  "yaml",
  "yml",
  "xml",
  "html",
  "htm",
  "css",
  "scss",
  "sh",
  "bash",
  "toml",
  "ini",
  "env",
  "graphql",
  "vue",
  "svelte",
]);

function extensionFor(name: string) {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

export function libraryFileKind(name: string, contentType: string): LibraryFileKind {
  const extension = extensionFor(name);
  const normalized = contentType.toLowerCase().split(";", 1)[0];
  if (normalized === "text/markdown" || ["md", "mdx"].includes(extension)) return "markdown";
  if (extension === "diff" || extension === "patch" || normalized === "text/x-diff") return "diff";
  if (extension === "csv" || normalized === "text/csv") return "csv";
  if (["xlsx", "xls", "ods"].includes(extension) || normalized.includes("spreadsheet")) {
    return "spreadsheet";
  }
  if (extension === "pdf" || normalized === "application/pdf") return "pdf";
  if (
    ["doc", "docx", "odt", "rtf"].includes(extension) ||
    normalized.includes("wordprocessingml") ||
    normalized === "application/msword" ||
    normalized === "application/rtf" ||
    normalized === "text/rtf"
  )
    return "docx";
  if (
    ["ppt", "pptx", "odp"].includes(extension) ||
    normalized.includes("presentationml") ||
    normalized.includes("powerpoint")
  )
    return "pptx";
  if (extension === "svg" || normalized === "image/svg+xml") return "svg";
  if (
    normalized.startsWith("image/") ||
    ["png", "jpg", "jpeg", "webp", "avif"].includes(extension)
  ) {
    return "image";
  }
  if (normalized.startsWith("video/") || ["mp4", "webm", "mov", "m4v"].includes(extension)) {
    return "video";
  }
  if (normalized.startsWith("audio/") || ["mp3", "wav", "ogg", "m4a", "flac"].includes(extension)) {
    return "audio";
  }
  if (
    ["zip", "tar", "gz", "tgz", "7z", "rar"].includes(extension) ||
    normalized.includes("zip") ||
    normalized.includes("tar") ||
    normalized.includes("gzip") ||
    normalized.includes("7z") ||
    normalized.includes("rar")
  )
    return "archive";
  if (CODE_EXTENSIONS.has(extension) || normalized.startsWith("text/")) return "code";
  return "text";
}

export function libraryKindSupportsEditor(kind: LibraryFileKind) {
  return ![
    "spreadsheet",
    "pdf",
    "docx",
    "pptx",
    "image",
    "svg",
    "video",
    "audio",
    "archive",
  ].includes(kind);
}

export function libraryKindSupportsPreview(kind: LibraryFileKind) {
  return !["code", "text"].includes(kind);
}
