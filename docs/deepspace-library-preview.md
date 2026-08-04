# DeepSpace Library preview

The Library workspace is the only surface that uses the format-aware preview
system. Chat messages, the live note editor, and generated-media cards keep
their existing renderers.

The Files section includes a secure **Import file** action. Imported files are
stored in the same tenant- and conversation-scoped Library collection and are
limited to 4 MB per browser import.

## Format routing

| File family | Library behavior |
| --- | --- |
| Markdown | CodeMirror editing plus the existing rich Markdown preview |
| Python, JavaScript/TypeScript, JSON, YAML, SQL, XML, HTML, CSS, Go, Rust, C/C++ and shell | Syntax-aware CodeMirror editing with extension-aware labeling; unknown text remains safely editable as text |
| `.diff` / `.patch` | Editable source plus a two-column colored diff preview |
| CSV | Editable source plus a parsed table preview with quoted-cell support |
| XLSX/XLS/ODS | Read-only first-sheet table preview when the stored payload is valid XLSX base64 |
| PDF | Authenticated payload rendered through the browser PDF viewer |
| DOCX | Browser document payload preview when the browser supports it |
| Images and SVG | Contained image preview; raw SVG is rendered as an encoded image URL, not injected HTML |
| Video and audio | Native browser controls with private payload URLs |
| ZIP | Safe central-directory listing only; files are never executed or extracted in the browser |

Binary previews require the file content to be stored as a `data:` URL or
base64 payload. The backend keeps the existing tenant-scoped Library file
authorization, limits browser imports to 4 MB, and rejects unknown content
types. ZIP preview intentionally lists entries without running archive content.

The Library editor never executes code, HTML, SVG scripts, or archive files.
