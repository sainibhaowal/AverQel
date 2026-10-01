self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { body: event.data ? event.data.text() : "New collection activity" };
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || "AverQel collection", {
      body: payload.body || "New collection activity",
      tag: payload.notification_id || "averqel-collection",
      data: { collectionId: payload.collection_id || null },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow("/dashboard/admin/collections"));
});
