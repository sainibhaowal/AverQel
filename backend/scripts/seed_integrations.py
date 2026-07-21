from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# Add backend to sys.path to allow imports
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.platform.database.session import get_session_factory
from app.integrations.models.integration import Integration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INTEGRATIONS: list[dict[str, Any]] = [
    {
        "name": "Web Crawler",
        "slug": "web-crawler",
        "description": "Automatically track and index content from public URLs and blogs.",
        "ui_metadata": {
            "icon": "Globe",
            "category": "Web",
            "setup_fields": [
                {
                    "name": "url",
                    "label": "Source URL",
                    "type": "url",
                    "required": True,
                    "section": "primary",
                    "placeholder": "https://docs.example.com",
                    "help_text": "Paste the website, docs, or knowledge source you want AverQel to crawl.",
                },
            ],
        },
    },
    {
        "name": "Google Drive",
        "slug": "google-drive",
        "description": "Connect Google Drive once through MCP and let AverQel read, upload, update, and delete files with approval.",
        "ui_metadata": {
            "icon": "Cloud",
            "category": "Storage",
            "capabilities": ["read", "write", "delete"],
            "setup_fields": [],
        },
    },
    {
        "name": "GitHub Repository",
        "slug": "github",
        "description": "Connect GitHub once through MCP and let AverQel read, manage files, and operate issues with approval.",
        "ui_metadata": {
            "icon": "Github",
            "category": "Development",
            "capabilities": ["read", "write", "delete", "issues"],
            "setup_fields": [],
        },
    },
    {
        "name": "Slack Conversations",
        "slug": "slack",
        "description": "Connect Slack once through MCP and let AverQel read, post, update, and delete channel messages with approval.",
        "ui_metadata": {
            "icon": "Slack",
            "category": "Communication",
            "capabilities": ["read", "write", "delete"],
            "setup_fields": [],
        },
    },
    {
        "name": "Notion Workspace",
        "slug": "notion",
        "description": "Connect Notion once through MCP and let AverQel create pages and append content with approval.",
        "ui_metadata": {
            "icon": "FileText",
            "category": "Knowledge",
            "capabilities": ["read", "write"],
            "setup_fields": [],
        },
    },
    {
        "name": "Gmail Account",
        "slug": "gmail",
        "description": "Connect Gmail once through MCP and let AverQel read, send, delete, archive, trash, and star mail with approval.",
        "ui_metadata": {
            "icon": "Mail",
            "category": "Communication",
            "capabilities": ["read", "write", "manage"],
            "setup_fields": [],
        },
    },
    {
        "name": "Google Calendar",
        "slug": "google-calendar",
        "description": "Connect Google Calendar once through MCP and let AverQel view, create, and schedule events with approval.",
        "ui_metadata": {
            "icon": "Calendar",
            "category": "Planning",
            "capabilities": ["read", "write"],
            "setup_fields": [],
        },
    },
]


def seed_integrations() -> None:
    factory = get_session_factory()
    with factory() as session:
        for int_data in INTEGRATIONS:
            # Check if exists
            result = session.execute(
                select(Integration).where(Integration.slug == int_data["slug"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                logger.info(
                    f"Integration {int_data['slug']} already exists, updating..."
                )
                existing.name = int_data["name"]
                existing.description = int_data["description"]
                existing.ui_metadata = int_data["ui_metadata"]
            else:
                logger.info(f"Creating integration {int_data['slug']}...")
                new_int = Integration(**int_data)
                session.add(new_int)

        session.commit()
        logger.info("Seeding complete.")


if __name__ == "__main__":
    seed_integrations()
