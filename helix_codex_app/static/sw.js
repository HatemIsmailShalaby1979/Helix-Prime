const CACHE_NAME = "helix-codex-shell-v1";

const PRECACHE = [
  "/",
  "/app",
  "/static/css/tokens.css",
  "/static/css/app.css",
  "/static/js/pwa.js",
  "/static/vendor/htmx.min.js",
  "/static/vendor/alpine.min.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/maskable-512.png",
  "/static/offline.html",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  const keep = CACHE_NAME;
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== keep).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") {
    return;
  }

  const url = new URL(event.request.url);

  if (url.pathname.startsWith("/app/api/")) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (!url.pathname.endsWith("/stream")) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return response;
        })
        .catch(() => caches.match(event.request)),
    );
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match("/static/offline.html")),
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      });
    }),
  );
});