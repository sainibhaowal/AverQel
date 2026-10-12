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

function extensionFor(name: string) {
  return name.split(".").pop()?.toLowerCase() ?? "";
}

const LIBREOFFICE_PAGE_EXTENSIONS = new Set([
  "doc",
  "docx",
  "docm",
  "dot",
  "dotx",
  "dotm",
  "odt",
  "ott",
  "odm",
  "oth",
  "rtf",
  "ppt",
  "pptx",
  "pptm",
  "pot",
  "potx",
  "potm",
  "pps",
  "ppsx",
  "ppsm",
  "odp",
  "otp",
  "xls",
  "xlsx",
  "xlsm",
  "xlt",
  "xltx",
  "xltm",
  "xlm",
  "xla",
  "xlw",
  "xlsb",
  "ods",
  "ots",
  "odg",
  "otg",
  "odc",
  "otc",
  "odf",
  "otf",
  "odi",
  "oti",
]);

export function libraryFileSupportsServerPagePreview(name: string, contentType: string) {
  const extension = extensionFor(name);
  const normalized = contentType.toLowerCase().split(";", 1)[0];
  return (
    extension === "pdf" ||
    normalized === "application/pdf" ||
    LIBREOFFICE_PAGE_EXTENSIONS.has(extension)
  );
}

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

export function libraryFileKind(name: string, contentType: string): LibraryFileKind {
  const extension = extensionFor(name);
  const normalized = contentType.toLowerCase().split(";", 1)[0];
  if (normalized === "text/markdown" || ["md", "mdx"].includes(extension)) return "markdown";
  if (extension === "diff" || extension === "patch" || normalized === "text/x-diff") return "diff";
  if (
    ["csv", "tsv"].includes(extension) ||
    ["text/csv", "text/x-csv", "text/tab-separated-values"].includes(normalized)
  ) {
    return "csv";
  }
  if (
    [
      "xlsx",
      "xls",
      "xlsm",
      "xlt",
      "xltx",
      "xltm",
      "xlm",
      "xla",
      "xlw",
      "xlsb",
      "ods",
      "ots",
    ].includes(extension) ||
    normalized.includes("spreadsheet") ||
    normalized === "application/vnd.ms-excel"
  ) {
    return "spreadsheet";
  }
  if (extension === "pdf" || normalized === "application/pdf") return "pdf";
  if (
    ["doc", "docx", "docm", "dot", "dotx", "dotm", "odt", "ott", "odm", "oth", "rtf"].includes(
      extension,
    ) ||
    normalized.includes("wordprocessingml") ||
    normalized === "application/msword" ||
    normalized === "application/vnd.oasis.opendocument.text" ||
    normalized === "application/rtf" ||
    normalized === "text/rtf"
  )
    return "docx";
  if (
    ["ppt", "pptx", "pptm", "pot", "potx", "potm", "pps", "ppsx", "ppsm", "odp", "otp"].includes(
      extension,
    ) ||
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
  // A MIME type of text/plain is not source code.  Keep source extensions in
  // the editor-only code mode, but give ordinary TXT/log files their split
  // edit + readable preview workspace.
  if (CODE_EXTENSIONS.has(extension)) return "code";
  if (normalized.startsWith("text/")) return "text";
  return "text";
}

export function libraryKindSupportsEditor(kind: LibraryFileKind) {
  return !["pdf", "image", "svg", "video", "audio", "archive"].includes(kind);
}

export function libraryKindSupportsPreview(kind: LibraryFileKind) {
  return kind !== "code";
}
