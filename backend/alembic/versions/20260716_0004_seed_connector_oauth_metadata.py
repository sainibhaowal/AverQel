"""ensure declarative OAuth provider metadata is present"""

from alembic import op

revision = "20260716_0004"
down_revision = "20260716_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    values = {
        "google-drive": ("google", "Google Drive"),
        "gmail": ("google", "Gmail"),
        "google-calendar": ("google", "Google Calendar"),
        "github": ("github", "GitHub"),
        "slack": ("slack", "Slack"),
        "notion": ("notion", "Notion"),
    }
    for slug, (key, label) in values.items():
        op.execute(
            f"UPDATE integrations SET ui_metadata = jsonb_set(jsonb_set(ui_metadata, '{{oauth_provider_key}}', to_jsonb('{key}'::text), true), '{{oauth_provider_label}}', to_jsonb('{label}'::text), true) WHERE slug = '{slug}'"
        )


def downgrade() -> None:
    for slug in ("google-drive", "gmail", "google-calendar", "github", "slack", "notion"):
        op.execute(
            f"UPDATE integrations SET ui_metadata = ui_metadata - 'oauth_provider_key' - 'oauth_provider_label' WHERE slug = '{slug}'"
        )
