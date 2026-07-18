import os
import shutil
from pathlib import Path

MAPPING = {
    "answer_service": "query",
    "query_service": "query",
    "retrieval_service": "query",
    "ingestion_service": "ingestion",
    "chunking_service": "ingestion",
    "embedding_service": "ingestion",
    "parser_service": "ingestion",
    "ocr_service": "ingestion",
    "vision_service": "ingestion",
    "extraction_quality": "ingestion",
    "conversion_service": "ingestion",
    "extractors": "ingestion",
    "archive_security": "security",
    "malware_scan_service": "security",
    "auth_service": "auth",
    "cache_service": "system",
    "storage_service": "system",
    "rate_limit_service": "system",
    "metrics_service": "system",
    "audit_service": "system",
    "idempotency_service": "system",
    "deletion_service": "documents",
    "pdf_render_service": "documents",
    "dashboard_service": "analytics",
}

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SERVICES_DIR = str(BACKEND_ROOT / "app" / "services")

# 1. Create directories and move files
for item, category in MAPPING.items():
    cat_dir = os.path.join(SERVICES_DIR, category)
    os.makedirs(cat_dir, exist_ok=True)

    init_py = os.path.join(cat_dir, "__init__.py")
    if not os.path.exists(init_py):
        with open(init_py, "w") as f:
            f.write("")

    src_file = os.path.join(SERVICES_DIR, f"{item}.py")
    src_dir = os.path.join(SERVICES_DIR, item)

    if os.path.exists(src_file):
        dest = os.path.join(cat_dir, f"{item}.py")
        print(f"Moving {src_file} -> {dest}")
        shutil.move(src_file, dest)
    elif os.path.exists(src_dir):
        dest = os.path.join(cat_dir, item)
        print(f"Moving {src_dir} -> {dest}")
        shutil.move(src_dir, dest)


# 2. Update imports in all python files
def process_file(filepath):
    try:
        with open(filepath) as f:
            content = f.read()
    except Exception:
        return

    new_content = content
    for item, category in MAPPING.items():
        original_import = f"app.services.{item}"
        new_import = f"app.services.{category}.{item}"
        new_content = new_content.replace(original_import, new_import)

    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)
        print(f"Updated imports in {filepath}")


search_dirs = [
    str(BACKEND_ROOT / "app"),
    str(BACKEND_ROOT / "tests"),
    str(BACKEND_ROOT / "scripts"),
]

for directory in search_dirs:
    if not os.path.exists(directory):
        continue
    for root, _, files in os.walk(directory):
        # skip pycache
        if "__pycache__" in root:
            continue
        for filename in files:
            if filename.endswith(".py"):
                process_file(os.path.join(root, filename))
