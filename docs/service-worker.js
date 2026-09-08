/* Offline-first shell. The page itself is fetched network-first so a shipped
   change shows up on the next visit; everything else is served from cache. */
const CACHE = "agenda-pwa-v23";
const ASSETS = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) =>
      /* {cache:"reload"} bypasses the browser's own HTTP cache. Without it a
         brand-new version can be seeded with the stale bytes the browser
         already had (GitHub Pages serves the app with max-age=600), so the
         version bump lands but the old page keeps being served. */
      c.addAll(ASSETS.map((u) => new Request(u, { cache: "reload" })))
    )
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;

  /* Navigations: network first, cache only as the offline fallback. Serving
     the document cache-first meant a deployed change stayed invisible until
     the cache name happened to change. */
  if (e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      }).catch(() =>
        caches.match(e.request, { ignoreSearch: true }).then(
          (hit) => hit || caches.match("./index.html", { ignoreSearch: true })
        )
      )
    );
    return;
  }

  /* Everything else (icons, manifest): cache first, it rarely changes. */
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(
      (hit) =>
        hit ||
        fetch(e.request).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
          return res;
        }).catch(() => caches.match("./index.html", { ignoreSearch: true }))
    )
  );
});
