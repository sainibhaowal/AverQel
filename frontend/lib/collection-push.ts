import { fetchWithAuth } from "@/lib/api";

function decodeVapidKey(value: string): ArrayBuffer {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const normalized = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(normalized);
  const bytes = Uint8Array.from(raw, (char) => char.charCodeAt(0));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
}

export async function enableCollectionPush(deviceId: string): Promise<"enabled" | "unavailable"> {
  if (
    !("serviceWorker" in navigator) ||
    !("PushManager" in window) ||
    !("Notification" in window)
  ) {
    return "unavailable";
  }
  const configResponse = await fetchWithAuth("/collections/security/push-config");
  if (!configResponse.ok) return "unavailable";
  const config = (await configResponse.json()) as { enabled?: boolean; public_key?: string | null };
  if (!config.enabled || !config.public_key) return "unavailable";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "unavailable";
  const registration = await navigator.serviceWorker.register("/collection-push-sw.js");
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: decodeVapidKey(config.public_key),
  });
  const keys = subscription.toJSON().keys;
  if (!subscription.endpoint || !keys?.p256dh || !keys.auth) return "unavailable";
  const response = await fetchWithAuth("/collections/security/push-subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      device_id: deviceId,
      endpoint: subscription.endpoint,
      p256dh: keys.p256dh,
      auth: keys.auth,
    }),
  });
  return response.ok ? "enabled" : "unavailable";
}
