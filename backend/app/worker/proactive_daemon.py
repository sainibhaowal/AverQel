from __future__ import annotations

from app.worker.tasks_proactive import run_proactive_daemon


def main() -> None:
    run_proactive_daemon()


if __name__ == "__main__":
    main()
