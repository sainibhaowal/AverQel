import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function ProfileDocsPage() {
  return (
    <DocsShell
      title="Profile & sessions"
      intro="Manage the security controls available for your AverQel account. Profile settings are for account access and authentication; collection invitations and workspace content are managed in their respective product areas."
    >
      <DocsSection title="Sign-in and two-factor authentication">
        <p>
          Settings show the account identity recorded by the service and provide password controls.
          Where enabled, you can set up time-based one-time password (TOTP) two-factor
          authentication. Store the recovery codes securely when they are issued; they are intended
          for account recovery and should not be shared with support.
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
          deployment. They are not functions of a collection code or local browser cache. Read the
          confirmation and scope before starting either action; deletion may be irreversible after
          its workflow completes.
        </p>
      </DocsSection>
      <DocsSection title="Collection identifiers">
        <p>
          Collection membership uses the collection and invitation flows shown in Collections. An
          identifier shown there is not a peer-to-peer identity credential or proof that a chat is
          cryptographically end-to-end encrypted.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
