// Service worker mínimo: permite "instalar" o painel na tela inicial.
// Não guarda dados em cache — o painel sempre mostra informação ao vivo.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
