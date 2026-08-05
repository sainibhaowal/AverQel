#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_text_pdf(text: str) -> bytes:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = ["Benchmark PDF content."]
    lines = lines[:40]

    content_lines = ["BT", "/F1 11 Tf", "50 780 Td"]
    first = True
    for line in lines:
        escaped = _escape_pdf_text(line[:120])
        if first:
            content_lines.append(f"({escaped}) Tj")
            first = False
        else:
            content_lines.append("0 -14 Td")
            content_lines.append(f"({escaped}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("utf-8")

    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        (
            f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode()
            + stream
            + b"\nendstream\nendobj\n"
        ),
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_start = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n"
        ).encode()
    )
    return bytes(out)


def _doc_type(index: int) -> str:
    sequence = ("txt", "md", "pdf")
    return sequence[index % len(sequence)]


def _build_text_block(doc_index: int, estimated_pages: int) -> str:
    lines_per_page = 35
    # Keep payload size benchmark-safe while preserving estimated page profile in manifest.
    total_lines = min(max(estimated_pages * lines_per_page, 35), 220)
    lines: list[str] = []
    for line_index in range(total_lines):
        lines.append(
            f"Document {doc_index:03d} benchmark line {line_index:04d}. "
            "AI Knowledge Service ingestion and retrieval validation content."
        )
    return "\n".join(lines)


def build_dataset(
    *,
    output_dir: Path,
    documents: int,
    target_pages_total: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    estimated_pages_per_doc = max(1, math.ceil(target_pages_total / documents))
    manifest_docs: list[dict[str, object]] = []
    counts = {"txt": 0, "md": 0, "pdf": 0}
    total_estimated_pages = 0
    total_bytes = 0

    for index in range(documents):
        kind = _doc_type(index)
        counts[kind] += 1
        estimated_pages = estimated_pages_per_doc
        base_name = f"doc_{index + 1:03d}"

        text_block = _build_text_block(index + 1, estimated_pages)
        if kind == "txt":
            path = output_dir / f"{base_name}.txt"
            payload = text_block.encode("utf-8")
        elif kind == "md":
            path = output_dir / f"{base_name}.md"
            payload = f"# {base_name}\n\n{text_block}\n".encode()
        else:
            path = output_dir / f"{base_name}.pdf"
            payload = _build_simple_text_pdf(text_block)

        path.write_bytes(payload)
        total_estimated_pages += estimated_pages
        total_bytes += len(payload)
        manifest_docs.append(
            {
                "file": path.name,
                "type": kind,
                "estimated_pages": estimated_pages,
                "size_bytes": len(payload),
            }
        )

    manifest = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "dataset_profile": {
            "documents": documents,
            "target_pages_total": target_pages_total,
            "estimated_pages_total": total_estimated_pages,
            "types": counts,
            "total_size_bytes": total_bytes,
        },
        "documents": manifest_docs,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return cast(dict[str, Any], manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Week 5 benchmark dataset")
    parser.add_argument(
        "--output-dir",
        default="tmp/week5_benchmark_dataset",
        help="Output directory for generated benchmark corpus",
    )
    parser.add_argument("--documents", type=int, default=100, help="Total number of documents")
    parser.add_argument(
        "--target-pages-total",
        type=int,
        default=5000,
        help="Target total estimated pages for corpus profile",
    )
    args = parser.parse_args()

    manifest = build_dataset(
        output_dir=Path(args.output_dir),
        documents=args.documents,
        target_pages_total=args.target_pages_total,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
