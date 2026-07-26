# Application OAuth login

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
