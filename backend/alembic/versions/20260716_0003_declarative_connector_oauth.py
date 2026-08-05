"""move legacy connector OAuth provider metadata into integration records"""

import sqlalchemy as sa

from alembic import op

revision = "20260716_0003"
down_revision = "20260716_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for slug, key, label in (
        ("google-drive", "google", "Google Drive"),
        ("gmail", "google", "Gmail"),
        ("google-calendar", "google", "Google Calendar"),
        ("github", "github", "GitHub"),
        ("slack", "slack", "Slack"),
        ("notion", "notion", "Notion"),
    ):
        bind.execute(
            sa.text(
                "UPDATE integrations SET ui_metadata = ui_metadata || jsonb_build_object('oauth_provider_key', CAST(:key AS text), 'oauth_provider_label', CAST(:label AS text)) WHERE slug = CAST(:slug AS text)",
            ),
            {"slug": slug, "key": key, "label": label},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for slug in ("google-drive", "gmail", "google-calendar", "github", "slack", "notion"):
        bind.execute(
            sa.text(
                "UPDATE integrations SET ui_metadata = ui_metadata - 'oauth_provider_key' - 'oauth_provider_label' WHERE slug = CAST(:slug AS text)",
            ),
            {"slug": slug},
        )
