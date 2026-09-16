// 앱 셸만 캐시. 데이터(data/, config/)는 항상 네트워크 우선.
const VERSION = 'v1.8.0';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png',
  './vendor/chart.umd.js'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => Promise.allSettled(SHELL.map(u => c.add(u)))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  const isData = url.origin === location.origin && /\/(data|config)\//.test(url.pathname);
  if (isData || url.hostname === 'api.github.com' || url.hostname === 'ntfy.sh') {
    // 네트워크 우선, 실패 시 캐시(오프라인 열람용)
    e.respondWith(fetch(e.request).then(r => { if (isData && r.ok) { const cp = r.clone(); caches.open(VERSION).then(c => c.put(stripQuery(e.request), cp)); } return r; })
      .catch(() => caches.match(stripQuery(e.request))));
    return;
  }
  // 앱 셸: 캐시 우선 + 백그라운드 갱신
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(cached => {
    const net = fetch(e.request).then(r => { if (r.ok) caches.open(VERSION).then(c => c.put(e.request, r.clone())); return r; }).catch(() => cached);
    return cached || net;
  }));
});
function stripQuery(req){ const u = new URL(req.url); u.search = ''; return new Request(u.toString(), { method: 'GET' }); }
