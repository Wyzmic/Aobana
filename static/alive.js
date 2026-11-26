// One shared worker for every Aobana tab of a browser (app.js watchServer). It keeps one request
// open to the server (routes_update api_alive_hold), which costs nothing while Aobana runs. When
// the server stops, the request breaks; the worker then asks every 0.2 s until Aobana answers
// again, and its first answer names the open tabs, so the launcher opens no second tab.
const pages = new Map();
let up = true;
let holding = false;

function ids() {
  return [...new Set(pages.values())].join(',');
}

function tell(message) {
  for (const port of pages.keys()) port.postMessage(message);
}

async function hold() {
  let answered = false;
  try {
    const r = await fetch(`/api/alive/hold?pages=${encodeURIComponent(ids())}`, { cache: 'no-store' });
    if (r.ok && r.body) {
      answered = true;
      if (!up) { up = true; tell('back'); }
      const reader = r.body.getReader();
      while (!(await reader.read()).done) {}
    }
  } catch (e) {}
  if (up) { up = false; tell('gone'); }
  setTimeout(hold, answered ? 0 : 200);
}

onconnect = e => {
  const port = e.ports[0];
  port.onmessage = m => {
    const [kind, page] = String(m.data).split(':');
    if (kind === 'hello') {
      pages.set(port, page);
      if (!holding) { holding = true; hold(); }
      else if (up) fetch(`/api/alive?page=${encodeURIComponent(page)}`, { cache: 'no-store' }).catch(() => {});
      else port.postMessage('gone');
    } else if (kind === 'bye') {
      pages.delete(port);
    }
  };
  port.start();
};
