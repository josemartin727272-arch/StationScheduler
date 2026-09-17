/* Offline-first shell, but never at the cost of being out of date: every
   request goes to the network first and the cache is the fallback for when
   there is no network. A version that is live is therefore the version you
   get on the next load, with no tabs to close first. */
const CACHE = "agenda-pwa-v41";
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
  self.skipWaiting();                 // do not wait for the old one to be let go
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())  // take over every open tab at once
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  /* extensions and other schemes cannot be cached, and asking would throw */
  if (!req.url.startsWith("http")) return;

  e.respondWith(
    fetch(req).then((res) => {
      /* Keep a copy for the next time there is no network. Only a complete
         same-origin response is worth storing: a redirect, a partial or a
         cross-origin opaque response either throws on put() or would be
         served back later as something the page cannot use. */
      if (res && res.ok && res.type === "basic") {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      }
      return res;
    }).catch(() =>
      caches.match(req, { ignoreSearch: true }).then((hit) =>
        /* Offline and never cached: a navigation still has somewhere to go —
           the app shell — while anything else is genuinely missing. */
        hit || (req.mode === "navigate"
          ? caches.match("./index.html", { ignoreSearch: true })
          : Response.error())
      )
    )
  );
});
