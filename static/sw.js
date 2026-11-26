// Aobana's page for a tab that loads while Aobana is not running (app.js registers it, app.py
// serves it at /sw.js so it covers every page). The browser's own error page never loads again by
// itself: a phone's browser shows it for a tab it reopens after Termux was closed, and the next
// start then showed that error page instead of Aobana. This page asks once a second while it is on
// screen and loads the address again as soon as Aobana answers. Only a page load that fails is
// answered here; nothing is kept, so a new version of Aobana is never served from a cache.
const TEXT = {
  ja: ['Aobana は起動していません', 'Aobana を起動すると、このページを読み込みます。'],
  en: ['Aobana is not running', 'When you start Aobana, this page loads by itself.'],
};

function page() {
  return `<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>露草</title>
<style>
:root { color-scheme: light dark; }
body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
  font-family: system-ui, sans-serif; background: Canvas; color: CanvasText; }
.box { max-width: 30em; padding: 24px; text-align: center; }
h1 { font-size: 1.3em; margin: 0 0 .6em; }
p { margin: 0; opacity: .75; line-height: 1.6; }
</style></head><body><div class="box"><h1></h1><p></p></div>
<script>
const TEXT = ${JSON.stringify(TEXT)};
let lang = null;
try { lang = localStorage.getItem('lang'); } catch (e) {}
if (lang !== 'ja' && lang !== 'en') lang = /^ja\\b/i.test(navigator.language || '') ? 'ja' : 'en';
document.documentElement.lang = lang;
document.title = TEXT[lang][0];
document.querySelector('h1').textContent = TEXT[lang][0];
document.querySelector('p').textContent = TEXT[lang][1];
let timer = 0;
function ask() {
  clearTimeout(timer);
  if (document.visibilityState !== 'visible') return;
  fetch('/api/alive?shown=1', { cache: 'no-store' }).then(r => r.ok, () => false).then(ok => {
    if (ok) location.reload();
    else timer = setTimeout(ask, 200);
  });
}
document.addEventListener('visibilitychange', ask);
window.addEventListener('pageshow', ask);
ask();
</script></body></html>`;
}

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => e.waitUntil((async () => {
  if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
  await self.clients.claim();
})()));

self.addEventListener('fetch', e => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith((async () => {
    try {
      return (await e.preloadResponse) || await fetch(e.request);
    } catch (err) {
      return new Response(page(), { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });
    }
  })());
});
