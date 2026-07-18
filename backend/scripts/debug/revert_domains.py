import os
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"

DOMAINS = ["auth", "documents", "query", "analytics", "system", "ingestion"]
FOLDERS_TO_REVERT = ["schemas", "models", "repositories"]

# 1. Move files back to root of folder
print("Reverting files from domains...")
for folder in FOLDERS_TO_REVERT:
    base_path = os.path.join(APP_DIR, folder)
    base_path = str(base_path)
    if not os.path.exists(base_path):
        continue

    for domain in DOMAINS:
        domain_dir = os.path.join(base_path, domain)
        if not os.path.exists(domain_dir):
            continue

        for file in os.listdir(domain_dir):
            if file == "__init__.py" or file == "__pycache__":
                continue
            src = os.path.join(domain_dir, file)
            dest = os.path.join(base_path, file)
            if os.path.isfile(src):
                shutil.move(src, dest)
                print(f"Moved {src} -> {dest}")

        # Clean up empty domain dirs
        if os.path.exists(domain_dir):
            shutil.rmtree(domain_dir, ignore_errors=True)

# 2. Revert imports globally
print("Reverting imports...")


def process_file(filepath: str) -> None:
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return

    new_content = content
    for folder in FOLDERS_TO_REVERT:
        for domain in DOMAINS:
            bad_import = f"app.{folder}.{domain}."
            good_import = f"app.{folder}."
            new_content = new_content.replace(bad_import, good_import)

    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
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

print("Reversion Done!")
