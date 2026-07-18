import os
import shutil
from pathlib import Path

# Categorize base layer
MAPPING_SCHEMAS = {
    "auth": "auth",
    "capabilities": "auth",
    "admin": "auth",
    "documents": "documents",
    "chats": "query",
    "queries": "query",
    "dashboard": "analytics",
    "common": "system",
    "errors": "system",
}

MAPPING_MODELS = {
    "role": "auth",
    "user": "auth",
    "user_role": "auth",
    "refresh_token": "auth",
    "tenant": "auth",
    "document": "documents",
    "document_chunk": "documents",
    "chunk_embedding": "documents",
    "data_deletion": "documents",
    "query": "query",
    "query_citation": "query",
    "conversation": "query",
    "message": "query",
    "ingestion_job": "ingestion",
    "audit_log": "system",
    "idempotency_key": "system",
}

MAPPING_REPOSITORIES = {
    "roles": "auth",
    "users": "auth",
    "tenants": "auth",
    "refresh_tokens": "auth",
    "documents": "documents",
    "chunks": "documents",
    "data_deletions": "documents",
    "queries": "query",
    "chat": "query",
    "ingestion_jobs": "ingestion",
    "audit_logs": "system",
    "idempotency_keys": "system",
    "base": "system",
}

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"


def refactor_folder(folder_name: str, mapping: dict[str, str]) -> None:
    base_path = os.path.join(APP_DIR, folder_name)
    base_path = str(base_path)
    if not os.path.exists(base_path):
        return

    for item, category in mapping.items():
        cat_dir = os.path.join(base_path, category)
        os.makedirs(cat_dir, exist_ok=True)

        init_py = os.path.join(cat_dir, "__init__.py")
        if not os.path.exists(init_py):
            with open(init_py, "w") as f:
                f.write("")

        src_file = os.path.join(base_path, f"{item}.py")
        if os.path.exists(src_file):
            dest = os.path.join(cat_dir, f"{item}.py")
            shutil.move(src_file, dest)


print("Moving files...")
refactor_folder("schemas", MAPPING_SCHEMAS)
refactor_folder("models", MAPPING_MODELS)
refactor_folder("repositories", MAPPING_REPOSITORIES)

print("Updating imports globally...")
ALL_MAPPINGS = [
    ("schemas", MAPPING_SCHEMAS),
    ("models", MAPPING_MODELS),
    ("repositories", MAPPING_REPOSITORIES),
]


def process_file(filepath: str) -> None:
    try:
        with open(filepath) as f:
            content = f.read()
    except Exception:
        return

    new_content = content
    for folder, mapping in ALL_MAPPINGS:
        for item, category in mapping.items():
            # Standard import replacement
            orig_import = f"app.{folder}.{item}"
            new_import = f"app.{folder}.{category}.{item}"
            new_content = new_content.replace(orig_import, new_import)

            # Sub-module imports like `from app.models import something`
            # are usually avoided by strict PEP-8 but just in case:
            # Not needed heavily if codebase explicitly imports files

    if new_content != content:
        with open(filepath, "w") as f:
            f.write(new_content)


search_dirs = [
    str(APP_DIR),
    str(ROOT_DIR / "tests"),
    str(ROOT_DIR / "scripts"),
    str(ROOT_DIR / "alembic"),
]

for directory in search_dirs:
    if not os.path.exists(directory):
        continue
    for root, _, files in os.walk(directory):
        if "__pycache__" in root or ".venv" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                process_file(os.path.join(root, f))

# alembic env.py needs special handling for loading all models
print("Done!")
