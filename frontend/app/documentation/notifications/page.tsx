import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function NotificationsDocsPage() {
  return (
    <DocsShell
      title="Notifications"
      intro="The notification centre helps you follow workspace events, support and feedback activity, and selected service alerts. Notification preferences are account-scoped; email availability depends on deployment configuration."
    >
      <DocsSection title="In-app notification centre">
        <p>
          The centre shows the latest available notifications from supported application and
          collection feeds. You can review unread items, mark an item read, and dismiss items. Older
          items may be loaded in pages. Realtime events can update the interface, while durable
          notifications are stored through the notification service.
        </p>
      </DocsSection>
      <DocsSection title="Preferences">
        <p>
          In Settings → Notifications, users can mute supported event categories and choose whether
          to receive email notifications and the available cadence. Muting a category affects its
          notification delivery according to the saved preference. Collection notification settings
          have their own controls where applicable.
        </p>
      </DocsSection>
      <DocsSection title="Email is deployment-dependent">
        <p>
          Email delivery is optional and is available only when the deployment configures an SMTP
          host and sender, enables the required credentials, and runs the notification worker and
          scheduler. If email is unavailable, in-app notifications can still work. Email delivery
          may be retried; the system cannot guarantee exactly-once delivery from an external SMTP
          service.
        </p>
        <p>
          Notifications do not fabricate payment or subscription lifecycle events: the current
          product does not have a paid-subscription source of truth. Provider alerts follow explicit
          health-test failures; this is not a continuous provider uptime monitor.
        </p>
      </DocsSection>
      <DocsSection title="Privacy">
        <p>
          Notification content is designed to avoid including prompts, provider credentials, raw
          exception details, or internal support notes. Notifications are scoped to the account and
          tenant authorized for the underlying event. Support and feedback messages themselves are
          readable by the submitter and authorized support staff; they are not end-to-end encrypted.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
