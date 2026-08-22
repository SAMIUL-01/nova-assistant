/* Nova service worker.
 *
 * Its only job is to make the app installable, so you get a real app icon and
 * a window with no address bar.
 *
 * It deliberately does NOT cache anything. Caching a chat app causes stale
 * JavaScript after an update, which is far more annoying than the tiny speed
 * win. Every request goes straight to the network.
 */

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", () => {
  // No interception: the browser handles the request normally.
});
