/**
 * StreamVault Service Worker
 * Cache-first untuk asset statis, network-first untuk API calls.
 */

const CACHE_NAME = "streamvault-v2.2";

// Asset yang di-cache saat install
const PRECACHE = [
  "/",
  "/extractor.html",
  "/manifest.json",
  "https://fonts.googleapis.com/css2?family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap",
  "https://cdnjs.cloudflare.com/ajax/libs/hls.js/1.5.7/hls.min.js",
];

// ── Install ──────────────────────────────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE).catch((err) => {
        console.warn("[SW] Precache partial fail:", err);
      });
    })
  );
  self.skipWaiting();
});

// ── Activate — hapus cache lama ──────────────────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch strategy ───────────────────────────────────────────────────────────
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API calls → network only (jangan cache data dinamis)
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // Untuk navigasi & asset statis → stale-while-revalidate
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request)
        .then((response) => {
          // Hanya cache response yang valid
          if (response && response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // Offline fallback — return cached jika ada
          return cached;
        });

      // Return cached dulu (instant), update di background
      return cached || fetchPromise;
    })
  );
});
