    const PAGE_BOOT = (document.querySelector('meta[name="aobana-boot"]') || {}).content || '';
    const RUN_KEYS = new Set(['aobana_last_search', 'aobana_last_media']);
    const store = {
      get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
      set(k, v) {
        if (RUN_KEYS.has(k) && PAGE_BOOT && store.get('aobana_boot') !== PAGE_BOOT) return;
        try { localStorage.setItem(k, v); } catch (e) {}
      },
      del(k) { try { localStorage.removeItem(k); } catch (e) {} },
    };
    (function () {
      const boot = PAGE_BOOT;
      if (boot && store.get('aobana_boot') !== boot) {
        store.del('aobana_last_search');
        store.del('aobana_last_media');
        store.set('aobana_boot', boot);
      }
    })();
    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    }
    function fmt(n) { return Number(n || 0).toLocaleString(LANG === 'ja' ? 'ja-JP' : 'en-US'); }
    if (document.getAnimations) {
      let animSync = 0;
      new MutationObserver(() => {
        if (animSync) return;
        animSync = requestAnimationFrame(() => {
          animSync = 0;
          for (const a of document.getAnimations()) {
            if (a.startTime !== 0 && 'animationName' in a && a.effect && a.effect.getTiming().iterations === Infinity) a.startTime = 0;
          }
        });
      }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden'] });
    }
    const ON_PHONE = (document.querySelector('meta[name="aobana-termux"]') || {}).content === '1';

    const LIST_CAP = 100;
    function capList(list) {
      return list.slice(0, LIST_CAP).map(f => `<li>${esc(f)}</li>`).join('')
        + (list.length > LIST_CAP ? `<li>${esc(t('list_more', { n: fmt(list.length - LIST_CAP) }))}</li>` : '');
    }

    let LANG = document.documentElement.getAttribute('lang') === 'en' ? 'en' : 'ja';
    function t(key, vars) {
      let s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.ja[key] ?? key;
      if (vars) s = s.replace(/\{(\w+)\|([^|}]*)\|([^}]*)\}/g, (m, k, one, many) =>
        k in vars ? (Number(String(vars[k]).replace(/[^\d.-]/g, '')) === 1 ? one : many) : m);
      if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(v);
      return s;
    }
    function applyI18n(root = document) {
      root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
      root.querySelectorAll('[data-i18n-html]').forEach(el => { el.innerHTML = t(el.dataset.i18nHtml); });
      root.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
      root.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
      root.querySelectorAll('[data-i18n-aria]').forEach(el => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
    }

    const LABEL_CONTROLS = '.brand, .nav-tab, .seg-btn, .dd-btn, .dd-item, .exact-chip, .sq-btn, .btn, .icon-btn, '
      + '.search-btn, .reveal-btn, .path-back, .modal-close, .menu-btn, .sidebar-more, summary, label[for]';
    function hideLabelText(node) {
      const parent = node.parentElement;
      if (!parent || !node.data.trim() || parent.closest('svg, style, script, textarea')) return;
      const span = document.createElement('span');
      span.className = 'lbl';
      span.dataset.label = node.data;
      node.replaceWith(span);
    }
    function hideLabels(root) {
      const controls = root.matches?.(LABEL_CONTROLS) ? [root] : [];
      controls.push(...(root.querySelectorAll?.(LABEL_CONTROLS) || []));
      for (const el of controls) {
        const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        const texts = [];
        while (walk.nextNode()) texts.push(walk.currentNode);
        texts.forEach(hideLabelText);
      }
    }
    function labelText(el) {
      return [...el.querySelectorAll('.lbl')].map(s => s.dataset.label).join('') || el.textContent;
    }
    function startHidingLabels() {
      hideLabels(document.body);
      new MutationObserver(records => {
        for (const r of records) {
          if (r.type === 'characterData') {
            if (r.target.parentElement?.closest(LABEL_CONTROLS)) hideLabelText(r.target);
            continue;
          }
          for (const n of r.addedNodes) {
            if (n.nodeType === 3) { if (n.parentElement?.closest(LABEL_CONTROLS)) hideLabelText(n); }
            else if (n.nodeType === 1) {
              if (n.parentElement?.closest(LABEL_CONTROLS)) hideLabels(n.parentElement.closest(LABEL_CONTROLS));
              else hideLabels(n);
            }
          }
        }
      }).observe(document.body, { childList: true, subtree: true, characterData: true });
    }
    if (document.body) startHidingLabels();
    else document.addEventListener('DOMContentLoaded', startHidingLabels);
    function setLang(lang) {
      store.set('lang', lang);
      location.reload();
    }
    document.documentElement.style.setProperty('--no-more', JSON.stringify(t('no_more')));

    const THEMES = ['paper', 'haze', 'night', 'midnight'];
    function currentTheme() { return document.documentElement.getAttribute('data-theme') || 'night'; }
    function setTheme(name) {
      document.documentElement.setAttribute('data-theme', name);
      store.set('theme', name);
      renderTopbarControls();
    }

    const PARAMS = new URLSearchParams(window.location.search);
    const TAB = PARAMS.get('view') === 'saved' ? 'saved'
              : ['search', 'saved', 'media', 'library', 'settings', 'guide'].includes(PARAMS.get('tab')) ? PARAMS.get('tab') : 'search';
    const SORTS = ['recommended', 'chrono', 'desc', 'asc', 'random'];
    const MEDIA_BOOT = (() => {
      try { return JSON.parse(document.getElementById('aobana-media').textContent); }
      catch (e) { return { on: { subs: true, books: true }, setup: false }; }
    })();
    const MEDIA_ON = { subs: !!MEDIA_BOOT.on.subs, epub: !!MEDIA_BOOT.on.books, manga: !!MEDIA_BOOT.on.manga, custom: !!MEDIA_BOOT.on.custom };
    const MEDIAS_ALL = ['all', 'subs', 'epub', 'manga', 'custom'];
    const MEDIAS_ON = MEDIAS_ALL.slice(1).filter(m => MEDIA_ON[m]);
    const MEDIAS = MEDIAS_ON.length > 1 ? ['all', ...MEDIAS_ON] : MEDIAS_ON.length ? MEDIAS_ON : ['all'];
    function mediaLabel(m) {
      return t(m === 'all' ? (MEDIAS_ON.length === 2 ? 'media_both' : 'media_all') : 'media_' + m);
    }
    const SORT = SORTS.includes(PARAMS.get('sort')) ? PARAMS.get('sort')
               : (SORTS.includes(store.get('sort')) ? store.get('sort') : 'recommended');
    const MEDIA = MEDIAS.includes(PARAMS.get('media')) ? PARAMS.get('media')
                : (MEDIAS.includes(store.get('media')) ? store.get('media') : MEDIAS[0]);
    let KNOWN = (() => {
      try { return JSON.parse(document.getElementById('aobana-known-words').textContent); }
      catch (e) { return { available: false, sources: [] }; }
    })();
    const LEARNS = ['off', 'first', 'only'];
    const LEARN = !KNOWN.available ? 'off' : LEARNS.includes(PARAMS.get('learn')) ? PARAMS.get('learn')
                : (LEARNS.includes(store.get('learn')) ? store.get('learn') : 'off');
    let currentFolders = TAB === 'search' ? PARAMS.getAll('folder').filter(Boolean) : [];
    let pinnedFolders = [];
    try { pinnedFolders = JSON.parse(sessionStorage.getItem('pinnedFolders') || '[]'); } catch (e) {}
    if (!Array.isArray(pinnedFolders)) pinnedFolders = [];
    let multiPick = store.get('multiPick') === 'on';
    function clearPins() {
      pinnedFolders = [];
      try { sessionStorage.removeItem('pinnedFolders'); } catch (e) {}
    }
    function unpinFolder(f) {
      pinnedFolders = pinnedFolders.filter(p => p !== f);
      try { sessionStorage.setItem('pinnedFolders', JSON.stringify(pinnedFolders)); } catch (e) {}
    }
    function pinFolders(list) {
      if (!multiPick) return;
      const before = pinnedFolders.length;
      for (const f of list) if (f && !pinnedFolders.includes(f)) pinnedFolders.push(f);
      if (pinnedFolders.length !== before) {
        try { sessionStorage.setItem('pinnedFolders', JSON.stringify(pinnedFolders)); } catch (e) {}
      }
    }
    if (TAB === 'search') pinFolders(currentFolders);
    function searchParams() {
      const p = new URLSearchParams(window.location.search);
      p.delete('tab');
      p.set('sort', SORT);
      p.set('media', MEDIA);
      if (LEARN !== 'off') p.set('learn', LEARN);
      else p.delete('learn');
      p.delete('pin');
      pinnedFolders.forEach(f => p.append('pin', f));
      return p;
    }

    let allResults = [];
    let observer;
    const BATCH_SIZE = 25;
    function lineId(line) {
      return btoa(unescape(encodeURIComponent(line)));
    }

    const RUBY_HTML_TAGS = {
      ruby: ['alpha'], rt: [], rp: [], rb: [], mark: ['hl-guess'], b: ['hl-guess'], br: [],
      span: ['hl-tail', 'hl-tail-p'], div: ['spacer'],
    };
    // A subtitle's （…） with words after it in its line is a speaker tag (Aobana Reibun's rule): wrapped
    // so Settings can hide it. A line that is only tags, （笑い声）, keeps them; ruby is never a tag
    const SUB_TAG_RE = /（[^（）]*）/g;
    function markSubTags(html) {
      if (typeof html !== 'string' || !html.includes('（')) return html;
      const doc = new DOMParser().parseFromString(`<!doctype html><body>${html}`, 'text/html');
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      let changed = false;
      for (const node of nodes) {
        if (!node.data.includes('（') || node.parentElement.closest('ruby, rt')) continue;
        const block = node.parentElement.closest('div, p') || doc.body;
        const parts = [];
        let last = 0;
        for (const m of node.data.matchAll(SUB_TAG_RE)) {
          const range = doc.createRange();
          range.setStart(node, m.index + m[0].length);
          range.setEndAfter(block.lastChild);
          if (!range.toString().replace(SUB_TAG_RE, '').trim()) continue;
          parts.push(doc.createTextNode(node.data.slice(last, m.index)));
          const span = doc.createElement('span');
          span.className = 'sub-tag';
          span.textContent = m[0];
          parts.push(span);
          last = m.index + m[0].length;
        }
        if (!parts.length) continue;
        parts.push(doc.createTextNode(node.data.slice(last)));
        node.replaceWith(...parts);
        changed = true;
      }
      return changed ? doc.body.innerHTML : html;
    }
    const RUBY_HTML_DROP = new Set(['script', 'style', 'template', 'noscript', 'iframe', 'object', 'embed',
      'svg', 'math', 'textarea', 'title', 'xmp', 'noembed', 'noframes', 'select', 'head']);
    const RUBY_HTML_ESC = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;'};
    function sanitizeRubyHtml(html) {
      if (typeof html !== 'string' || !html) return '';
      const doc = new DOMParser().parseFromString(`<!doctype html><body>${html}`, 'text/html');
      const walk = node => {
        let out = '';
        for (const n of node.childNodes) {
          if (n.nodeType === Node.TEXT_NODE) {
            out += n.data.replace(/[&<>"']/g, c => RUBY_HTML_ESC[c]);
          } else if (n.nodeType === Node.ELEMENT_NODE) {
            const tag = n.localName;
            if (RUBY_HTML_DROP.has(tag)) continue;
            const classes = Object.prototype.hasOwnProperty.call(RUBY_HTML_TAGS, tag) ? RUBY_HTML_TAGS[tag] : null;
            const cls = n.getAttribute('class');
            const keep = classes && (tag === 'span' || tag === 'div' ? classes.includes(cls) : true);
            if (!keep) { out += walk(n); continue; }
            if (tag === 'br') { out += '<br>'; continue; }
            const attr = cls && classes.includes(cls) ? ` class="${cls}"` : '';
            out += `<${tag}${attr}>${walk(n)}</${tag}>`;
          }
        }
        return out;
      };
      return walk(doc.body);
    }

    const FAV_TEXT = new Set(['id', 'legacy_id', 'line', 'file', 'media_type', 'title', 'folder', 'original_q',
      'readings', 'base_forms', 'clean_text']);
    const FAV_INT = new Set(['rowid', 'page', 'char_count']);
    const FAV_HTML = new Set(['display_line', 'context']);
    function cleanFavorite(s) {
      if (!s || typeof s !== 'object' || typeof s.line !== 'string') return null;
      const out = {};
      for (const k of Object.keys(s)) {
        const v = s[k];
        if (FAV_TEXT.has(k)) {
          if (typeof v === 'string') out[k] = v;
        } else if (FAV_INT.has(k)) {
          const n = typeof v === 'number' ? v : parseInt(v, 10);
          if (Number.isSafeInteger(n)) out[k] = n;
        } else if (k === 'score') {
          const n = Number(v);
          if (Number.isFinite(n)) out[k] = n;
        } else if (FAV_HTML.has(k)) {
          if (typeof v === 'string') out[k] = sanitizeRubyHtml(v);
        }
      }
      return out;
    }

    function loadSavedSentences() {
      let raw, list;
      try {
        raw = localStorage.getItem('savedSentences');
        list = JSON.parse(raw || '[]');
      } catch (e) {
        console.error('savedSentences unreadable, left as is:', e);
        return [];
      }
      if (!Array.isArray(list)) return [];
      const seen = new Set();
      const out = [];
      let changed = false;
      for (const orig of list) {
        const s = cleanFavorite(orig);
        if (!s) { changed = true; continue; }
        if (JSON.stringify(s) !== JSON.stringify(orig)) changed = true;
        const id = lineId(s.line);
        if (seen.has(id)) { changed = true; continue; }
        seen.add(id);
        if (s.id !== id) {
          if (s.legacy_id === undefined && typeof orig.id === 'string') s.legacy_id = orig.id;
          s.id = id;
          changed = true;
        }
        out.push(s);
      }
      if (changed) {
        try {
          if (localStorage.getItem('savedSentences_backup_v1') === null) {
            localStorage.setItem('savedSentences_backup_v1', raw);
          }
          localStorage.setItem('savedSentences', JSON.stringify(out));
        } catch (e) {
          console.error('savedSentences re-key not saved:', e);
        }
      }
      return out;
    }

    let savedSentences = loadSavedSentences();

    const searchSeed = (() => {
      const fresh = Math.floor(Math.random() * 2147483647);
      if (TAB !== 'search') return fresh;
      const p = new URLSearchParams(window.location.search);
      const url = [p.get('q') || '', p.get('sort') || 'recommended', p.get('media') || 'all',
                   p.get('exact') || '', p.getAll('folder').join('\u0001'), p.get('ruby_only') || ''].join('\u0000');
      try {
        const last = JSON.parse(sessionStorage.getItem('aobana_seed') || 'null');
        if (last && last.url === url) return last.seed;
        sessionStorage.setItem('aobana_seed', JSON.stringify({ url, seed: fresh }));
      } catch (e) {}
      return fresh;
    })();
    const clientToken = (() => {
      try {
        let tok = sessionStorage.getItem('subsClient');
        if (!tok) {
          tok = Math.random().toString(36).slice(2) + Date.now().toString(36);
          sessionStorage.setItem('subsClient', tok);
        }
        return tok;
      } catch (e) {
        return 'tab-' + Math.random().toString(36).slice(2);
      }
    })();
    function apiSearchUrl(qs) {
      return `/api/search?${qs}&seed=${searchSeed}&client=${encodeURIComponent(clientToken)}`;
    }
    function apiPost(url, body) {
      return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Aobana': '1' }, body: JSON.stringify(body || {}) })
        .then(r => r.json());
    }
    let serverSearchInFlight = 0;
    function cancelServerSearch(grace) {
      if (serverSearchInFlight <= 0) return;
      serverSearchInFlight = 0;
      try {
        fetch(`/api/search/cancel?client=${encodeURIComponent(clientToken)}`, {
          method: 'POST', keepalive: true,
          headers: { 'Content-Type': 'application/json', 'X-Aobana': '1' },
          body: JSON.stringify({ grace: grace || 0 }),
        }).catch(() => {});
      } catch (e) {}
    }
    window.addEventListener('pagehide', () => {
      if (TAB !== 'search') cancelServerSearch(1);
    });

    let currentSearchController = null;
    let currentOffset = 0;
    let isFetchingMore = false;
    let hasMoreResults = true;
    let loadMoreObserver = null;
    let searchGen = 0;
    let outsideMedia = new Set();

    function choiceOutsideMedia() {
      return !multiPick && currentFolders.length > 0 && currentFolders.every(f => outsideMedia.has(f));
    }

    function setEmptyStateForFolders(folders) {
      const empty = document.getElementById('empty-state');
      if (!empty) return;
      if (folders.length && folders.every(f => outsideMedia.has(f))) {
        empty.dataset.i18n = 'no_results_outside_media';
        empty.textContent = t('no_results_outside_media', { n: folders.length });
      } else if (folders.length) {
        empty.dataset.i18n = 'no_results_chosen';
        empty.textContent = t('no_results_chosen');
      } else {
        empty.dataset.i18n = 'no_results';
        empty.textContent = t('no_results');
      }
    }
    function busyLine(pad) {
      return `<div class="status-line" style="padding:${pad};">${esc(t('search_busy'))}</div>`;
    }
    async function busyAnswer(res) {
      if (!res || res.status !== 503) return false;
      try { return !!(await res.clone().json()).busy; } catch (e) { return false; }
    }

    let epSentinelObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const sentinel = entry.target;
                const fileEnc = sentinel.dataset.file;
                const offset = parseInt(sentinel.dataset.offset, 10);
                epSentinelObserver.unobserve(sentinel);
                setTimeout(() => {
                    loadMoreEpisodeSentinel(sentinel, fileEnc, offset);
                }, 100);
            }
        });
    }, { rootMargin: '500px 0px 500px 0px' });
    const epUpObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => { if (entry.isIntersecting) loadEarlierLines(entry.target); });
    }, { rootMargin: '400px 0px 400px 0px' });

    function setTitle(part) {
      document.title = part ? `${part} | ${t('app')}` : t('app');
    }

