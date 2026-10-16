# 02. Application OAuth login

AverQel supports optional Google and GitHub sign-in alongside the existing email/password login. This application-login flow is separate from connector OAuth and MCP OAuth; provider access tokens are exchanged server-side and are never stored.

## Configuration

Set the following backend variables together for each provider:

```dotenv
AKS_AUTH_GOOGLE_OAUTH_CLIENT_ID=
AKS_AUTH_GOOGLE_OAUTH_CLIENT_SECRET=
AKS_AUTH_GITHUB_OAUTH_CLIENT_ID=
AKS_AUTH_GITHUB_OAUTH_CLIENT_SECRET=
AKS_AUTH_OAUTH_REDIRECT_URI=https://your-domain.example.com/api/v1/auth/oauth/{provider}/callback
AKS_AUTH_OAUTH_FRONTEND_REDIRECT_URI=https://your-domain.example.com/auth/login
```

Register these exact callback URLs with the providers:

- `https://your-domain.example.com/api/v1/auth/oauth/google/callback`
- `https://your-domain.example.com/api/v1/auth/oauth/github/callback`

The frontend starts login at `/api/v1/auth/oauth/google/start` or `/api/v1/auth/oauth/github/start`. The backend uses the authorization-code flow with PKCE and a signed, short-lived state cookie. Google and GitHub identities must provide a verified email address. A verified email matching an existing AverQel account links the provider identity to that account; otherwise a new workspace account is created.

OAuth identities are stored in the tenant-scoped `oauth_identities` table. No provider access token or client secret is returned to the browser. Existing password login, refresh cookies, lockout handling, roles, tenant isolation, and TOTP verification remain available.

## Account profile and first-run setup

The authenticated `GET /api/v1/auth/profile` response includes the account's `display_name`, `avatar`, `status`, `totp_enabled`, and `onboarding_completed` values alongside its email, tenant, and roles. The `PUT /api/v1/auth/profile` request can update only `display_name`, `avatar`, and `onboarding_completed`; email and roles are read-only in this route. The endpoint derives the user and tenant from the validated authentication context.

Display names are trimmed, limited to 48 characters, and cannot contain ASCII control characters. Avatar values are limited to 700,000 characters and must be image data or an HTTPS image URL. The frontend crops and resizes uploaded photos before saving them. Avatar data remains on the user record and may be included in shared-collection responses where member avatars are shown. Do not put secrets or sensitive documents in an avatar.

New accounts have no `onboarding_completed_at` timestamp and see the welcome flow after sign-in. The profile update marks that flow complete once; the operation is idempotent. The migration backfills existing accounts as already complete so they are not interrupted by the new flow. The light/dark appearance preference remains local to the browser and is not part of the profile API.
