import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function ProfileDocsPage() {
  return (
    <DocsShell
      title="Profile & sessions"
      intro="Choose the name and avatar shown in your AverQel workspace, then manage the security controls available for your account. Your sign-in email, account role, and permissions are not changed by profile customization."
    >
      <DocsSection title="Display name and avatar">
        <p>
          Open Profile from the account menu in the dashboard header, or visit Settings → Profile.
          Choose one of the built-in avatars or upload a JPEG, PNG, WebP, or AVIF photo. AverQel
          crops the photo to a square and resizes it before saving it to your account profile. Your
          avatar may also appear beside your messages in shared Qel Connect spaces. Your email
          address and assigned role remain unchanged.
        </p>
      </DocsSection>
      <DocsSection title="First sign-in welcome">
        <p>
          New accounts see a short welcome flow after sign-in. It introduces the main workspace
          areas, lets you choose a display name, avatar, and light or dark appearance, and offers
          optional provider setup. The flow follows the selected appearance and uses a short
          transition between steps. You can skip the flow at any time. Your completion choice is
          saved to your account; appearance is saved in this browser. DeepSpace uses your display
          name for its welcome message when one has been saved.
        </p>
      </DocsSection>
      <DocsSection title="Sign-in and two-factor authentication">
        <p>
          The account menu shows your display name, sign-in email, assigned role, account status,
          and whether time-based one-time password (TOTP) two-factor authentication is enabled. In
          Profile settings, you can change your password and, where enabled, set up or disable TOTP.
          Store recovery codes securely when they are issued; they are for account recovery and
          should not be shared with support.
        </p>
      </DocsSection>
      <DocsSection title="Linked sessions">
        <p>
          Review the signed-in browser or device sessions associated with your account. New web
          sign-ins use a random browser ID and a browser/platform label to help distinguish them;
          this does not identify physical hardware. The page also shows the recorded user-agent,
          sign-in time, and most recent token refresh time. Older sessions may not have browser
          details.
        </p>
        <p>
          You can revoke another active session if you no longer recognize or use it. That session’s
          refresh tokens and access tokens are rejected. End the current session through Log out, or
          use Sign out everywhere to end all of your sessions. Old revoked session records are
          removed according to the deployment’s retention setting.
        </p>
      </DocsSection>
      <DocsSection title="Account export and deletion">
        <p>
          Account export and deletion are available from Trust &amp; Privacy when enabled for the
          deployment. They are not functions of a Qel Connect code or local browser cache. Read the
          confirmation and scope before starting either action; deletion may be irreversible after
          its workflow completes.
        </p>
      </DocsSection>
      <DocsSection title="Qel Connect identifiers">
        <p>
          Qel Connect membership uses the invitation flows shown in Qel Connect. An identifier shown
          there is not a peer-to-peer identity credential or proof that a chat is cryptographically
          end-to-end encrypted.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
