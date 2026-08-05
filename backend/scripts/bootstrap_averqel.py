from __future__ import annotations

import secrets
import sys
import uuid
from pathlib import Path

# Add backend to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.auth.models.role import Role
from app.auth.models.tenant import Tenant
from app.auth.models.user import User
from app.auth.models.user_role import UserRole
from app.auth.security import hash_password
from app.core.ids import generate_uuid7_with_fallback
from app.platform.database.session import get_session_factory
from scripts.seed_integrations import seed_integrations


def _generate_collection_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


def bootstrap():
    factory = get_session_factory()
    with factory() as session:
        # 1. Create Default Tenant
        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        existing_tenant = session.get(Tenant, tenant_id)
        if not existing_tenant:
            tenant = Tenant(
                id=tenant_id,
                name="AverQel Global",
            )
            session.add(tenant)
            session.flush()
            print(f"Created tenant: {tenant.name} ({tenant_id})")
        else:
            tenant_id = existing_tenant.id
            print(f"Using existing tenant: {existing_tenant.name}")

        # 2. Create Roles
        role_map = {}
        for role_name in ["super_admin", "admin", "user"]:
            result = session.execute(
                select(Role).where(Role.name == role_name)
            ).scalar_one_or_none()
            if not result:
                role = Role(
                    id=generate_uuid7_with_fallback(),
                    name=role_name,
                    description=f"{role_name.capitalize()} role",
                )
                session.add(role)
                session.flush()
                role_map[role_name] = role.id
                print(f"Created role: {role_name}")
            else:
                role_map[role_name] = result.id
                print(f"Using existing role: {role_name}")

        # 3. Create Super Admin User
        import json
        import os

        # Parse bootstrap emails from env
        bootstrap_emails_raw = os.environ.get(
            "AKS_BOOTSTRAP_SUPER_ADMIN_EMAILS", '["admin@averqel.ai"]'
        )
        try:
            bootstrap_emails = json.loads(bootstrap_emails_raw)
            if isinstance(bootstrap_emails, str):
                bootstrap_emails = [bootstrap_emails]
        except Exception:
            bootstrap_emails = [bootstrap_emails_raw]

        admin_email = bootstrap_emails[0] if bootstrap_emails else "admin@averqel.ai"
        admin_password = os.environ.get("AKS_INITIAL_ADMIN_PASSWORD", "Password123!")

        result = session.execute(select(User).where(User.email == admin_email)).scalar_one_or_none()
        if not result:
            user = User(
                id=generate_uuid7_with_fallback(),
                tenant_id=tenant_id,
                email=admin_email,
                password_hash=hash_password(admin_password),
                collection_code=_generate_collection_code(),
                is_active=True,
            )
            session.add(user)
            session.flush()
            print(f"Created user: {admin_email}")

            # Assign Role
            session.add(UserRole(tenant_id=tenant_id, user_id=user.id, role_id=role_map["admin"]))
            print(f"Assigned 'admin' role to {admin_email}")
        else:
            print(f"User {admin_email} already exists.")

        session.commit()
        seed_integrations()
        print("\nBootstrap complete.")
        print("-" * 30)
        print(f"Email: {admin_email}")
        print(f"Password: {admin_password}")
        print(f"Tenant ID: {tenant_id}")
        print("-" * 30)


if __name__ == "__main__":
    bootstrap()
