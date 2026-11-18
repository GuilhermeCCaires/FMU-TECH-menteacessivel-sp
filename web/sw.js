/* Service worker: guarda a interface para abrir sem internet. */
const VERSAO = "menteacessivel-v4";
const ESTATICOS = ["/", "/buscar", "/inicio.js", "/estilo.css", "/app.js", "/icone.svg", "/icone-192.png", "/icone-512.png", "/apple-touch-icon.png", "/manifest.webmanifest", "/sobre"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSAO).then((c) => c.addAll(ESTATICOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((chaves) =>
    Promise.all(chaves.filter((k) => k !== VERSAO).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  const guardar = (r) => {
    if (r.ok) { const copia = r.clone(); caches.open(VERSAO).then((c) => c.put(e.request, copia)); }
    return r;
  };
  if (url.origin === location.origin) {
    // Páginas, scripts e API: rede primeiro (vê sempre a versão nova); sem rede, usa o cache
    e.respondWith(fetch(e.request).then(guardar).catch(() => caches.match(e.request)));
  } else if (url.hostname === "unpkg.com") {
    // Bibliotecas versionadas: cache primeiro
    e.respondWith(caches.match(e.request).then((salvo) => salvo || fetch(e.request).then(guardar)));
  }
});
