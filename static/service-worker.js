const CACHE_NAME = "zephyr-cache-v1";
const urlsToCache = [
  "/",
  "/login",
  "/04_dashboard",
  "/static/style.css",
  "/static/icon-192.png",
  "/static/icon-512.png"
];

self.addEventListener("install", function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(urlsToCache);
    })
  );
});

self.addEventListener("fetch", function(event) {
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});
