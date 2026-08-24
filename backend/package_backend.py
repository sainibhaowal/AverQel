import os
import shutil
import subprocess

import PyInstaller.__main__


def get_target_triple() -> str | None:
    try:
        output = subprocess.check_output(["rustc", "-vV"], stderr=subprocess.STDOUT).decode()
        for line in output.splitlines():
            if line.startswith("host:"):
                return line.split(":")[1].strip()
    except Exception as e:
        print(f"Error getting target triple: {e}")
    return None


def main() -> None:
    triple = get_target_triple()
    if not triple:
        print("Could not determine target triple. Sidecar build might fail.")
        return

    base_dir = os.path.dirname(os.path.abspath(__file__))
    entry_point = os.path.join(base_dir, "run_backend.py")

    binary_base_name = "averqel-backend"
    target_name = f"{binary_base_name}-{triple}"

    # On Windows, PyInstaller adds .exe automatically
    if os.name == "nt":
        target_name += ".exe"

    print(f"Packaging backend as sidecar: {target_name}")

    args = [
        entry_point,
        "--onefile",
        "--name",
        target_name,
        "--clean",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols",
        "--hidden-import",
        "uvicorn.protocols.http",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "fastapi",
        "--hidden-import",
        "sqlalchemy",
    ]

    PyInstaller.__main__.run(args)

    # Move the binary to the Electron resources directory.
    dist_dir = os.path.join(base_dir, "dist")
    binary_path = os.path.join(dist_dir, target_name)
    electron_resources_dir = os.path.abspath(
        os.path.join(base_dir, "..", "applications", "desktop", "resources")
    )

    os.makedirs(electron_resources_dir, exist_ok=True)
    destination = os.path.join(electron_resources_dir, target_name)

    print(f"Moving binary to {destination}")
    shutil.move(binary_path, destination)


if __name__ == "__main__":
    main()
