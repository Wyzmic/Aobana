    const store = {
      get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
      set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
      del(k) { try { localStorage.removeItem(k); } catch (e) {} },
    };
    (function () {
      const boot = (document.querySelector('meta[name="aobana-boot"]') || {}).content;
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
    function setLang(lang) {
      store.set('lang', lang);
      location.reload();
    }

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
    const MEDIA_ON = { subs: !!MEDIA_BOOT.on.subs, epub: !!MEDIA_BOOT.on.books, manga: !!MEDIA_BOOT.on.manga };
    const MEDIAS_ALL = ['all', 'subs', 'epub', 'manga'];
    const MEDIAS_ON = MEDIAS_ALL.slice(1).filter(m => MEDIA_ON[m]);
    const MEDIAS = MEDIAS_ON.length > 1 ? ['all', ...MEDIAS_ON] : MEDIAS_ON.length ? MEDIAS_ON : ['all'];
    function mediaLabel(m) {
      return t(m === 'all' ? (MEDIAS_ON.length === 2 ? 'media_both' : 'media_all') : 'media_' + m);
    }
    const SORT = SORTS.includes(PARAMS.get('sort')) ? PARAMS.get('sort')
               : (SORTS.includes(store.get('sort')) ? store.get('sort') : 'recommended');
    const MEDIA = MEDIAS.includes(PARAMS.get('media')) ? PARAMS.get('media')
                : (MEDIAS.includes(store.get('media')) ? store.get('media') : MEDIAS[0]);
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
      ruby: ['alpha'], rt: [], rp: [], rb: [], mark: [], b: [], br: [],
      span: ['hl-tail', 'hl-tail-p'], div: ['spacer'],
    };
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
                   p.get('exact') || '', p.getAll('folder').join('\u0001')].join('\u0000');
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
    window.addEventListener('pagehide', () => cancelServerSearch(1));

    let currentSearchController = null;
    let currentOffset = 0;
    let isFetchingMore = false;
    let hasMoreResults = true;
    let loadMoreObserver = null;
    let searchGen = 0;
    let outsideMedia = new Set();

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

    function setTitle(part) {
      document.title = part ? `${part} | ${t('app')}` : t('app');
    }

    async function initFetch(inPage) {
      const q = PARAMS.get('q');
      setTitle(q ? t('title_results', { q }) : t('tab_search'));

      if (currentSearchController) {
          currentSearchController.abort();
      }
      currentSearchController = new AbortController();
      searchGen++;
      hasMoreResults = false;
      stopSearchEta();

      if (!q) {
        document.getElementById('main-loading').style.display = 'none';
        cancelServerSearch(0);
        showSearchHistory(inPage);
        return;
      }
      renderFilterNote();

      saveToHistory(q);
      store.set('aobana_last_search', window.location.pathname + window.location.search);

      document.getElementById('history-state').style.display = 'none';
      document.getElementById('main-loading').style.display = 'flex';
      const resultsBox = document.getElementById('results');
      if (inPage) {
        resultsBox.style.minHeight = resultsBox.offsetHeight + 'px';
        const side = document.querySelector('.sidebar');
        if (side && getComputedStyle(side).position === 'sticky') {
          const stuckAt = Math.max(0, Math.round(side.parentElement.getBoundingClientRect().top + window.scrollY
                                                 - (parseFloat(getComputedStyle(side).top) || 0)));
          if (window.scrollY > stuckAt) window.scrollTo({ top: stuckAt, behavior: 'instant' });
        }
      }
      resultsBox.innerHTML = '';
      document.getElementById('empty-state').style.display = 'none';

      const gen = searchGen;
      startSearchEta(searchParams().toString(), gen);
      serverSearchInFlight++;
      try {
        const response = await fetch(apiSearchUrl(`${searchParams().toString()}&limit=500&offset=0`), {
            signal: currentSearchController.signal
        });
        const data = await response.json();

        if (data.aborted) return;

        outsideMedia = new Set(Array.isArray(data.outside_media) ? data.outside_media : []);
        setEmptyStateForFolders(currentFolders);

        allResults = data.results;
        hasMoreResults = data.has_more;
        currentOffset = 500;

        if (data.scoped) {
          renderSidebar(scopedSidebar(data), inPage);
          fillOtherCounts(data, gen);
        } else {
          renderSidebar(data, inPage);
          if (data.global_total != null) countsGen = gen;
        }
        renderBatches();
        setupLoadMoreSentinel();

      } catch (err) {
        if (err.name === 'AbortError') {
            console.log("Previous search aborted.");
        } else {
            console.error("Fetch error:", err);
        }
      } finally {
        serverSearchInFlight = Math.max(0, serverSearchInFlight - 1);
        if (gen === searchGen) {
          stopSearchEta();
          document.getElementById('results').style.minHeight = '';
        }
        if (currentSearchController && !currentSearchController.signal.aborted) {
            document.getElementById('main-loading').style.display = 'none';
        }
      }
    }

    function scopedSidebar(data) {
      const prev = sidebarData && sidebarData.q === PARAMS.get('q') ? sidebarData : null;
      const counts = { ...(prev ? prev.folder_counts : {}), ...data.folder_counts };
      const folders = prev ? prev.all_folders.slice() : [];
      for (const f of [...(data.all_folders || []), ...currentFolders]) if (!folders.includes(f)) folders.push(f);
      return { ...data, folder_counts: counts, all_folders: folders, q: PARAMS.get('q'),
               global_total: prev ? prev.global_total : null };
    }
    let countingGen = -1;
    let countsGen = -1;
    function knownEmpty(f) {
      return outsideMedia.has(f) || (countsGen === searchGen && !!sidebarData && !((sidebarData.folder_counts || {})[f] > 0));
    }
    function countingRow() {
      return countingGen === searchGen
        ? `<li class="sidebar-more" id="sidebar-counting">${esc(t('counting_others'))}</li>` : '';
    }
    async function fillOtherCounts(scoped, gen) {
      const p = searchParams();
      p.delete('folder');
      countingGen = gen;
      document.getElementById('sidebar-counting')?.remove();
      document.getElementById('folder-list-dynamic')?.insertAdjacentHTML('beforeend', countingRow());
      serverSearchInFlight++;
      try {
        const opts = { signal: currentSearchController.signal };
        let all = await fetch(apiSearchUrl(`${p.toString()}&limit=0&offset=0`).replace('/api/search?', '/api/search/counts?'), opts)
                          .then(r => r.json());
        if (gen === searchGen && all.fallback) {
          all = await fetch(apiSearchUrl(`${p.toString()}&limit=0&offset=0`), opts).then(r => r.json());
        }
        if (gen !== searchGen || all.aborted || !all.all_folders) return;
        countingGen = -1;
        countsGen = gen;
        const counts = { ...all.folder_counts, ...scoped.folder_counts };
        const folders = all.all_folders.slice();
        for (const f of [...(scoped.all_folders || []), ...currentFolders]) if (!folders.includes(f)) folders.push(f);
        renderSidebar({ ...all, folder_counts: counts, all_folders: folders, q: PARAMS.get('q') }, true);
      } catch (e) {
      } finally {
        serverSearchInFlight = Math.max(0, serverSearchInFlight - 1);
        if (countingGen === gen) countingGen = -1;
        if (gen === searchGen) document.getElementById('sidebar-counting')?.remove();
      }
    }

    let searchEtaTimer = null;
    let searchWorkerTimer = null;
    let searchEtaGeneration = 0;
    function startSearchEta(qs, gen, current) {
      stopSearchEta();
      const epoch = searchEtaGeneration;
      const el = document.getElementById('search-eta');
      const live = current || (() => searchGen);
      const poll = async () => {
        if (gen !== live() || epoch !== searchEtaGeneration) return;
        clearTimeout(searchWorkerTimer);
        searchWorkerTimer = null;
        try {
          const p = await fetch(`/api/search/progress?${qs}&seed=${searchSeed}&client=${encodeURIComponent(clientToken)}`).then(r => r.json());
          if (gen !== live() || epoch !== searchEtaGeneration) return;
          if (p.running) {
            el.textContent = fmtEta(p.remaining);
            const active = document.getElementById('search-workers-active');
            const key = p.delay > 0 ? 'search_workers_active' : 'search_workers_active_now';
            if (active) active.textContent = p.workers > 1 ? t(key, { n: fmt(p.workers) }) : '';
          }
        } catch (e) {}
        if (gen === live() && epoch === searchEtaGeneration) searchEtaTimer = setTimeout(poll, 1000);
      };
      searchEtaTimer = setTimeout(poll, 3000);
      const pollWorkers = async () => {
        if (gen !== live() || epoch !== searchEtaGeneration) return;
        try {
          const p = await fetch(`/api/search/progress?${qs}&seed=${searchSeed}&client=${encodeURIComponent(clientToken)}&status=1`).then(r => r.json());
          if (gen !== live() || epoch !== searchEtaGeneration) return;
          const active = document.getElementById('search-workers-active');
          const key = p.delay > 0 ? 'search_workers_active' : 'search_workers_active_now';
          if (active) active.textContent = p.running && p.workers > 1
            ? t(key, { n: fmt(p.workers) }) : '';
        } catch (e) {}
        if (gen === live() && epoch === searchEtaGeneration && searchWorkerTimer !== null) searchWorkerTimer = setTimeout(pollWorkers, 1000);
      };
      searchWorkerTimer = setTimeout(pollWorkers, 500);
    }
    function stopSearchEta() {
      searchEtaGeneration++;
      clearTimeout(searchEtaTimer);
      clearTimeout(searchWorkerTimer);
      searchEtaTimer = null;
      searchWorkerTimer = null;
      const el = document.getElementById('search-eta');
      if (el) el.textContent = '';
      const active = document.getElementById('search-workers-active');
      if (active) active.textContent = '';
    }

    function saveToHistory(q) {
      let history;
      try { history = JSON.parse(store.get('searchHistory', '[]')); } catch (e) { history = []; }
      if (!Array.isArray(history)) history = [];
      history = history.filter(item => item !== q);
      history.unshift(q);
      if (history.length > 50) history.pop();
      store.set('searchHistory', JSON.stringify(history));
    }

    function showSearchHistory(inPage) {
      let history;
      try { history = JSON.parse(store.get('searchHistory', '[]')); } catch (e) { history = []; }
      if (!Array.isArray(history)) history = [];
      const panel = document.getElementById('history-state');
      renderFilterNote();
      if (history.length > 0) {
        const keep = new URLSearchParams();
        currentFolders.forEach(f => keep.append('folder', f));
        const chips = history.slice(0, 15).map(q => {
          const p = new URLSearchParams(keep); p.set('q', q);
          return `<a href="/?${p.toString()}" class="history-chip" draggable="false">${esc(q)}</a>`;
        }).join('');
        panel.innerHTML = `<div class="history-label">${esc(t('recent'))}</div><div class="history-chips">${chips}</div>
          <p class="folder-hint">${esc(t(multiPick ? 'folder_hint' : 'folder_hint_one'))}</p>`;
      } else {
        panel.innerHTML = `<p class="folder-hint">${esc(t(multiPick ? 'folder_hint' : 'folder_hint_one'))}</p>`;
      }
      panel.style.display = 'block';
      if (inPage && sidebarData) { renderSidebar(sidebarData, true); return; }

      const historySignal = currentSearchController ? currentSearchController.signal : undefined;
      fetch(apiSearchUrl(`q=&media=${encodeURIComponent(MEDIA)}&limit=0`), historySignal ? { signal: historySignal } : {})
        .then(r => r.json())
        .then(data => {
          if (!data || data.aborted) return;
          const mediaFolders = new Set(data.all_folders || []);
          outsideMedia = new Set([...currentFolders, ...pinnedFolders].filter(f => !mediaFolders.has(f)));
          renderSidebar(data);
          if (!data.global_total && !(data.all_folders || []).length) showEmptyLibrary();
        })
        .catch(() => {});
    }

    function renderFilterNote() {
      const note = document.getElementById('filter-note');
      if (!note) return;
      const pinnedOnly = multiPick ? pinnedFolders.filter(f => !currentFolders.includes(f)) : [];
      if ((currentFolders.length || pinnedOnly.length) && (multiPick || currentFolders.length > 1)) {
        const shown = [...pinnedFolders.filter(f => currentFolders.includes(f) || pinnedOnly.includes(f)),
                       ...currentFolders.filter(f => !pinnedFolders.includes(f))];
        note.innerHTML = `<span class="filter-label">${esc(t('filtering'))}</span>` + shown.map(f => `
          <span class="filter-chip${currentFolders.includes(f) ? '' : ' dim'}"><span class="filter-chip-name">${esc(f)}</span><button type="button" data-folder="${esc(f)}" title="${esc(t('remove_filter', { f }))}" aria-label="${esc(t('remove_filter', { f }))}">✕</button></span>`).join('');
        note.querySelectorAll('button[data-folder]').forEach(b => b.addEventListener('click', e => {
          const f = b.dataset.folder;
          unpinFolder(f);
          if (currentFolders.includes(f)) { setFolder(f, e); return; }
          e.preventDefault();
          if (sidebarData) renderSidebar(sidebarData, true);
          renderFilterNote();
        }));
        note.hidden = false;
      } else {
        note.hidden = true;
      }
    }

    function showMediaOff() {
      for (const id of ['empty-library', 'media-empty']) {
        const panel = document.getElementById(id);
        if (!panel) continue;
        panel.querySelector('h2').dataset.i18n = 'off_title';
        panel.querySelector('p').dataset.i18n = 'off_body';
        const btn = panel.querySelector('a.btn');
        btn.dataset.i18n = 'off_btn';
        btn.href = '/?tab=settings';
        panel.querySelectorAll('[data-i18n]').forEach(el => el.textContent = t(el.dataset.i18n));
      }
    }

    function showEmptyLibrary() {
      const empty = document.getElementById('empty-library');
      if (empty) empty.hidden = false;
      document.getElementById('history-state').style.display = 'none';
    }

    const SIDEBAR_PAGE = 500;
    let sidebarData = null, sidebarMatches = [], sidebarShown = 0, sidebarPinned = 0;
    function sidebarRows(from, to) {
      let html = '';
      sidebarMatches.slice(from, to).forEach((f, k) => {
        if (from + k === sidebarPinned && sidebarPinned) html += '<li class="side-divider" aria-hidden="true"></li>';
        html += sidebarRow(f);
      });
      return html;
    }

    function sidebarRow(f) {
      const data = sidebarData;
      const isSelected = currentFolders.includes(f) ? 'selected' : '';
      const count = data.folder_counts && data.folder_counts[f] !== undefined ? data.folder_counts[f] : 0;
      const hasCount = data.global_total != null
        || (data.folder_counts && data.folder_counts[f] !== undefined)
        || currentFolders.includes(f)
        || pinnedFolders.includes(f);
      return `
          <li>
            <a href="#" data-folder="${esc(f)}" class="folder-link ${isSelected}" draggable="false">
              <span class="folder-name">${esc(f)}</span>
              ${PARAMS.get('q') && hasCount ? `<span class="count-badge">${fmt(count)}</span>` : ''}
            </a>
          </li>`;
    }

    function renderSidebar(data, inPage) {
      sidebarData = data;
      if (inPage && sidebarShown) {
        if (sidebarSignature(data) === sidebarDrawn) { markSelected(); setTimeout(revealChosen, 0); return; }
        const sidebar = document.querySelector('.sidebar');
        const top = sidebar ? sidebar.scrollTop : 0;
        drawSidebar();
        if (sidebar) sidebar.scrollTop = top;
        setTimeout(revealChosen, 0);
        return;
      }
      sidebarShown = SIDEBAR_PAGE;
      drawSidebar();
      setTimeout(revealChosen, 0);
    }

    function revealChosen() {
      if (multiPick || currentFolders.length !== 1 || !sidebarData) return;
      const f = currentFolders[0];
      const idx = sidebarMatches.indexOf(f);
      if (idx < 0) return;
      if (idx >= sidebarShown) { sidebarShown = idx + 1; drawSidebar(); }
      const side = document.querySelector('.sidebar');
      const row = [...document.querySelectorAll('#folder-list-dynamic .folder-link[data-folder]')].find(a => a.dataset.folder === f);
      if (!side || !row) return;
      const box = side.getBoundingClientRect(), r = row.getBoundingClientRect();
      if (r.top < box.top || r.bottom > box.bottom) side.scrollTop += r.top - box.top - (box.height - r.height) / 2;
    }

    let sidebarDrawn = null;
    function sidebarSignature(data) {
      return JSON.stringify([data.all_folders || [], data.folder_counts || {}, data.global_total || 0,
                             [...pinnedFolders].sort(), [...currentFolders].sort()]);
    }

    function markSelected() {
      document.querySelectorAll('#folder-list-dynamic .folder-link[data-folder]').forEach(a => {
        const f = a.dataset.folder;
        a.classList.toggle('selected', f ? currentFolders.includes(f) : !currentFolders.length);
      });
    }

    function drawSidebar() {
      const list = document.getElementById('folder-list-dynamic');
      if (!list || !sidebarData) return;
      sidebarDrawn = sidebarSignature(sidebarData);
      const input = document.getElementById('folder-filter');
      const needle = input ? input.value.trim().toLowerCase() : '';
      const listed = sidebarData.all_folders || [];
      const unlisted = currentFolders.filter(f => !listed.includes(f) && !pinnedFolders.includes(f));
      const top = [...listed.filter(f => pinnedFolders.includes(f)),
                   ...pinnedFolders.filter(f => !listed.includes(f)),
                   ...(multiPick ? unlisted : [])];
      const rest = [...listed.filter(f => !pinnedFolders.includes(f)), ...(multiPick ? [] : unlisted)];
      const match = f => !needle || f.toLowerCase().includes(needle);
      sidebarPinned = top.filter(match).length;
      sidebarMatches = [...top.filter(match), ...rest.filter(match)];
      let html = `
        <li>
          <a href="#" data-folder="" class="folder-link ${!currentFolders.length ? 'selected' : ''}" id="folder-all" draggable="false">
            <span>${esc(t('all'))}</span>
            ${sidebarData.global_total == null ? '' : `<span class="count-badge">${fmt(sidebarData.global_total)}</span>`}
          </a>
        </li>`;
      html += sidebarRows(0, sidebarShown);
      list.innerHTML = html + sidebarMoreRow() + countingRow();
    }

    function sidebarMoreRow() {
      const left = sidebarMatches.length - sidebarShown;
      return left > 0 ? `<li class="sidebar-more" id="sidebar-more">${esc(t('sidebar_more', { n: fmt(left) }))}</li>` : '';
    }

    function moreSidebar() {
      const more = document.getElementById('sidebar-more');
      if (!more || !sidebarData) return;
      const from = sidebarShown;
      sidebarShown += SIDEBAR_PAGE;
      more.insertAdjacentHTML('beforebegin', sidebarRows(from, sidebarShown));
      more.outerHTML = sidebarMoreRow() || '<li hidden></li>';
    }

    function filterFolders() {
      sidebarShown = SIDEBAR_PAGE;
      drawSidebar();
    }

    function setMediaMode(next) {
      store.set('media', next);
      const url = new URL(window.location);
      url.searchParams.set('media', next);
      window.location.href = url.toString();
    }

    function setFolder(folder, event) {
      if (event && event.preventDefault) event.preventDefault();
      if (!folder) applyFolders([]);
      else if (currentFolders.includes(folder)) applyFolders(currentFolders.filter(f => f !== folder));
      else applyFolders(multiPick ? [...currentFolders, folder] : [folder]);
    }

    function applyFolders(next, replace) {
      const withHits = list => list.filter(f => !knownEmpty(f)).sort().join('\n');
      const q = PARAMS.get('q');
      const unchanged = q && currentFolders.length && next.length && withHits(currentFolders) === withHits(next);
      const empty = q && next.length && next.every(knownEmpty);
      currentFolders = next;
      pinFolders(next);
      const url = new URL(window.location);
      url.searchParams.delete('view');
      url.searchParams.delete('folder');
      next.forEach(f => url.searchParams.append('folder', f));
      history[replace ? 'replaceState' : 'pushState'](null, '', url);
      store.set('aobana_last_search', window.location.pathname + window.location.search);
      syncHiddenFolders();
      markSelected();
      renderFilterNote();
      if (!unchanged && !empty) { initFetch(true); return; }
      if (empty) {
        if (currentSearchController) currentSearchController.abort();
        stopSearchEta();
        document.getElementById('main-loading').style.display = 'none';
        cancelServerSearch(0);
        const hadAllCounts = countsGen === searchGen;
        searchGen++;
        if (hadAllCounts) countsGen = searchGen;
        allResults = [];
        hasMoreResults = false;
        setEmptyStateForFolders(next);
        renderBatches();
      }
      renderSidebar(sidebarData, true);
    }

    function syncHiddenFolders() {
      const box = document.getElementById('hidden-folders');
      if (!box) return;
      box.innerHTML = currentFolders.map(f => `<input type="hidden" name="folder" value="${esc(f)}">`).join('');
    }

    window.addEventListener('popstate', () => { if (TAB === 'search') location.reload(); });

    function toggleFurigana() {
      const off = document.documentElement.classList.toggle('no-furigana');
      store.set('furigana', off ? 'off' : 'on');
      document.querySelectorAll('.furi-btn').forEach(b => b.classList.toggle('off', off));
    }

    function fitSidebar() {
      const s = document.querySelector('.sidebar');
      if (!s) return;
      const cs = getComputedStyle(s);
      if (cs.position !== 'sticky') { s.style.height = s.style.maxHeight = ''; return; }
      const stickyTop = parseFloat(cs.top) || 16;
      const gap = parseFloat(getComputedStyle(document.body).paddingBottom) || 16;
      const topRect = s.getBoundingClientRect().top;
      const h = Math.max(200, window.innerHeight - Math.max(topRect, stickyTop) - gap);
      s.style.transition = 'none';
      s.style.height = s.style.maxHeight = Math.round(h) + 'px';
      requestAnimationFrame(() => { s.style.transition = ''; });
    }
    let fitQueued = false;
    const queueFit = () => { if (!fitQueued) { fitQueued = true; requestAnimationFrame(() => { fitQueued = false; fitSidebar(); }); } };
    window.addEventListener('scroll', queueFit, { passive: true });
    window.addEventListener('resize', queueFit);
    window.addEventListener('load', fitSidebar);
    document.addEventListener('DOMContentLoaded', fitSidebar);
    document.addEventListener('DOMContentLoaded', () => {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      new ResizeObserver(() => {
        document.documentElement.style.setProperty('--topbar-h', bar.offsetHeight + 'px');
        queueFit();
      }).observe(bar);
    });

    function renderBatches() {
      const resultsContainer = document.getElementById('results');
      const emptyState = document.getElementById('empty-state');
      resultsContainer.innerHTML = '';
      starRows.clear();

      if (allResults.length === 0) {
        emptyState.style.display = 'block';
        if (observer) observer.disconnect();
        return;
      } else {
        emptyState.style.display = 'none';
      }

      const numBatches = Math.ceil(allResults.length / BATCH_SIZE);
      for (let i = 0; i < numBatches; i++) {
        const wrapper = document.createElement('div');
        wrapper.className = 'batch-wrapper';
        wrapper.dataset.index = i;
        wrapper.innerHTML = buildBatchHTML(i);
        resultsContainer.appendChild(wrapper);
      }
    }

    function setupLoadMoreSentinel() {
      const resultsContainer = document.getElementById('results');
      let sentinel = document.getElementById('load-more-sentinel');
      if (!sentinel) {
          sentinel = document.createElement('div');
          sentinel.id = 'load-more-sentinel';
          resultsContainer.insertAdjacentElement('afterend', sentinel);
      }

      if (!hasMoreResults && !allResults.length) {
          sentinel.innerHTML = '';
      } else if (!hasMoreResults) {
          sentinel.innerHTML = `<div class="status-line" style="padding-top:4em;">${esc(t('no_more'))}</div>`;
      } else {
          sentinel.innerHTML = '';
      }

      if (loadMoreObserver) loadMoreObserver.disconnect();

      loadMoreObserver = new IntersectionObserver(async (entries) => {
          if (entries[0].isIntersecting && hasMoreResults && !isFetchingMore) {
              isFetchingMore = true;
              setTimeout(async () => {
                  isFetchingMore = false;
                  await fetchMoreResults();
              }, 150);
          }
      }, { rootMargin: '500px 0px 500px 0px' });

      loadMoreObserver.observe(sentinel);
    }

    async function fetchMoreResults() {
        if (!hasMoreResults || isFetchingMore) return;
        isFetchingMore = true;
        const myGen = searchGen;
        const sentinel = document.getElementById('load-more-sentinel');

        serverSearchInFlight++;
        try {
            sentinel.innerHTML = `<div class="status-line" style="padding:1.5em;">${esc(t('loading'))}</div>`;

            const response = await fetch(apiSearchUrl(`${searchParams().toString()}&limit=500&offset=${currentOffset}`));
            const data = await response.json();

            if (myGen !== searchGen) {
                return;
            }

            if (data.results.length > 0) {
                const startIndex = allResults.length;
                allResults = allResults.concat(data.results);
                hasMoreResults = data.has_more;
                currentOffset += 500;
                appendBatches(startIndex, data.results.length);
            } else {
                hasMoreResults = false;
            }

            if (!hasMoreResults) {
                sentinel.innerHTML = `<div class="status-line" style="padding:1.5em;">${esc(t('no_more'))}</div>`;
            } else {
                sentinel.innerHTML = '';
                const rect = sentinel.getBoundingClientRect();
                if (rect.top < window.innerHeight + 500) {
                    setTimeout(fetchMoreResults, 100);
                }
            }
        } catch (err) {
            console.error("Fetch more error:", err);
            sentinel.innerHTML = '';
        } finally {
            serverSearchInFlight = Math.max(0, serverSearchInFlight - 1);
            isFetchingMore = false;
        }
    }

    function appendBatches(startIndex, count) {
      const resultsContainer = document.getElementById('results');
      const startBatch = Math.floor(startIndex / BATCH_SIZE);
      const endBatch = Math.ceil((startIndex + count) / BATCH_SIZE);

      for (let i = startBatch; i < endBatch; i++) {
        if (!document.querySelector(`.batch-wrapper[data-index="${i}"]`)) {
            const wrapper = document.createElement('div');
            wrapper.className = 'batch-wrapper';
            wrapper.dataset.index = i;
            wrapper.innerHTML = buildBatchHTML(i);
            resultsContainer.appendChild(wrapper);
        }
      }
    }

    const starRows = new Map();
    let starSeq = 0;
    function starKey(item) { const k = String(++starSeq); starRows.set(k, item); return k; }
    function starRow(btn) {
      const item = btn && starRows.get(btn.dataset.star);
      return item ? JSON.parse(JSON.stringify(item)) : null;
    }

    function buildBatchHTML(batchIndex) {
      const start = batchIndex * BATCH_SIZE;
      const end = Math.min(start + BATCH_SIZE, allResults.length);
      const currentQ = PARAMS.get('q') || '';
      let html = '';
      for (let i = start; i < end; i++) {
        const r = allResults[i];
        const rId = lineId(r.line);
        const isSaved = savedSentences.some(s => s.id === rId);

        const savedItemData = {...r, id: rId};
        if (!savedItemData.original_q) savedItemData.original_q = currentQ;

        html += `
        <div class="card" id="card-${rId}">
          <div class="card-meta">
            <div class="src">${esc(r.title || r.folder)}${r.page ? ' · ' + pageLabel(r) : ''}</div>
            <div class="chars">${r.char_count !== undefined ? esc(t('chars', { n: r.char_count })) : ''}</div>
          </div>
          <div class="file-title">
            <span class="main-sentence">${r.display_line}</span>
            <div class="actions-box">
              <button class="icon-btn ${isSaved ? 'star-active' : ''}" onclick="toggleSave('${rId}', this)" data-star="${starKey(savedItemData)}" aria-label="${esc(t('sc_save'))}">
                <span>★</span>
              </button>
              <button class="icon-btn" onclick="toggleContext(this)" aria-label="${esc(t('sc_context'))}" data-rowid="${r.rowid}" data-file="${encodeURIComponent(r.file)}" data-media="${esc(r.media_type || '')}" data-saved-context="${r.context ? encodeURIComponent(r.context) : ''}">
                <span>⋯</span>
              </button>
            </div>
          </div>
          <div class="context">${r.context ? r.context : ''}</div>
        </div>
        `;
      }
      return html;
    }

    async function toggleContext(btn) {
      const ctx = btn.parentElement.parentElement.nextElementSibling;
      const isHidden = window.getComputedStyle(ctx).display === 'none';
      if (isHidden) {
        const savedCtx = btn.dataset.savedContext;
        if (savedCtx && !ctx.dataset.loaded) {
           ctx.innerHTML = decodeURIComponent(savedCtx);
           ctx.dataset.loaded = 'true';
        }

        if (!ctx.dataset.loaded) {
          ctx.innerHTML = `<div class="status-line">${esc(t('loading'))}</div>`;
          ctx.style.display = 'block';
          ctx.classList.remove('anim-close');
          ctx.classList.add('anim-open');
          try {
            const rowid = btn.dataset.rowid;
            const fileEnc = btn.dataset.file;
            let q = PARAMS.get('q') || '';
            try {
               const starBtn = btn.previousElementSibling;
               const btnData = starRow(starBtn);
               if (btnData && btnData.original_q) q = btnData.original_q;
            } catch(e) {}
            const media = btn.dataset.media ? `&media=${encodeURIComponent(btn.dataset.media)}` : '';
            const res = await fetch(`/api/context?rowid=${rowid}&file=${fileEnc}&q=${encodeURIComponent(q)}${media}`);
            const data = await res.json();
            if (data.context) {
              ctx.innerHTML = data.context;
            } else {
              ctx.innerHTML = `<div class="error-text">${esc(t('error'))}</div>`;
            }
            ctx.dataset.loaded = 'true';
          } catch (e) {
            ctx.innerHTML = `<div class="error-text">${esc(t('load_failed'))}</div>`;
          }
        } else {
          ctx.style.display = 'block';
          ctx.classList.remove('anim-open');
          ctx.classList.add('anim-open');
        }
      } else {
        ctx.classList.remove('anim-open');
        ctx.classList.add('anim-close');
        setTimeout(() => {
          if (ctx.classList.contains('anim-close')) {
            ctx.style.display = 'none';
            ctx.classList.remove('anim-close');
          }
        }, 140);
      }
    }

    function toggleSave(id, btn) {
      const isSaved = btn.classList.contains('star-active');
      const data = starRow(btn);
      if (!data) return;

      if (isSaved) {
        savedSentences = savedSentences.filter(s => s.id !== id);
        btn.classList.remove('star-active');
      } else {
        savedSentences.unshift(data);
        btn.classList.add('star-active');
      }
      store.set('savedSentences', JSON.stringify(savedSentences));

      if (TAB === 'saved') showSavedSentences();
    }

    function initSavedTab() {
      setTitle(t('tab_saved'));
      document.getElementById('saved-head').after(document.getElementById('empty-state'), document.getElementById('results'));
      showSavedSentences();
      relocateSaved();
    }

    async function relocateSaved() {
      const items = savedSentences.map(s => ({ rowid: s.rowid, file: s.file, line: s.line, media_type: s.media_type }));
      if (!items.length) return;
      const res = await apiPost('/api/relocate', { items }).catch(() => null);
      if (!res || !Array.isArray(res.items)) return;
      let moved = 0;
      res.items.forEach((u, i) => {
        if (u && savedSentences[i]) { savedSentences[i].rowid = u.rowid; savedSentences[i].file = u.file; moved++; }
      });
      if (!moved) return;
      store.set('savedSentences', JSON.stringify(savedSentences));
      if (TAB === 'saved') showSavedSentences();
    }

    function showSavedSentences() {
      allResults = savedSentences;
      document.getElementById('saved-meta').textContent = t('saved_count', { n: fmt(savedSentences.length) });
      const empty = document.getElementById('empty-state');
      empty.dataset.i18n = 'no_saved';
      empty.textContent = t('no_saved');
      renderBatches();
    }

    function mediaTabFilter() {
      const m = store.get('mediaTabFilter');
      return MEDIAS.includes(m) ? m : MEDIAS[0];
    }
    const MEDIA_TAB_FILTER = mediaTabFilter();
    const mediaTabUnfiltered = () => MEDIAS.length === 1 || mediaTabFilter() === 'all';

    function statPills(it) {
      if (it.media === 'manga') {
        return `<span class="stat-pill secondary">${esc(t('stat_vols', { n: fmt(it.episodes) }))}</span>
                <span class="stat-pill">${esc(t('stat_lines', { n: fmt(it.lines) }))}</span>`;
      }
      if (it.media === 'epub') {
        return `<span class="stat-pill secondary">${esc(t('stat_chaps', { n: fmt(it.episodes) }))}</span>
                <span class="stat-pill">${esc(t('stat_sents', { n: fmt(it.lines) }))}</span>`;
      }
      return `<span class="stat-pill secondary">${esc(t('stat_eps', { n: fmt(it.episodes) }))}</span>
              <span class="stat-pill">${esc(t('stat_lines', { n: fmt(it.lines) }))}</span>`;
    }

    const MEDIA_STATE = 'aobana_last_media';
    let mediaRestoring = false;
    let mediaDetailFiles = [];
    let mediaDetailFolder = '';
    let mediaDetailMedia = 'all';
    let mediaDetailMode = store.get('mediaDetailMode') === 'content' ? 'content' : 'title';
    let mediaDetailContentActive = false;
    let mediaDetailCtrl = null;
    let mediaDetailGen = 0;
    function mediaUrl() { return window.location.pathname + window.location.search; }
    function readMediaState() {
      try { const v = JSON.parse(store.get(MEDIA_STATE) || 'null'); return v && typeof v.url === 'string' ? v : null; }
      catch (e) { return null; }
    }
    function saveMediaState() {
      if (TAB !== 'media' || mediaRestoring) return;
      const filterEl = document.getElementById('media-detail-filter');
      const qEl = document.getElementById('media-detail-q');
      const exactEl = document.getElementById('media-detail-exact');
      if (mediaDetailMode === 'content' && mediaDetailContentActive && qEl && qEl.value.trim()) {
        store.set(MEDIA_STATE, JSON.stringify({
          url: mediaUrl(), mode: 'content', q: qEl.value.trim(), exact: !!(exactEl && exactEl.checked),
          open: [], y: Math.round(window.scrollY), at: mediaAnchor()
        }));
        return;
      }
      const open = [];
      document.querySelectorAll('#results .episode-card:not(.collapsed)').forEach(card => {
        const h = card.querySelector('.episode-header');
        const loaded = card.querySelectorAll('.episode-line').length;
        if (h && loaded) open.push({ file: h.dataset.file, loaded });
      });
      const titleQ = (mediaDetailMode === 'title' && filterEl) ? filterEl.value.trim() : '';
      store.set(MEDIA_STATE, JSON.stringify({
        url: mediaUrl(), mode: mediaDetailMode, q: titleQ, open, y: Math.round(window.scrollY), at: mediaAnchor()
      }));
    }
    function mediaAnchor() {
      const bar = document.querySelector('.topbar');
      const probeY = Math.max(0, bar ? bar.getBoundingClientRect().bottom : 0) + 8;
      const hit = document.elementFromPoint(Math.round(window.innerWidth / 2), probeY);
      const el = hit && hit.closest('.episode-line, .episode-header');
      const card = el && el.closest('.episode-card');
      if (!card) return null;
      const header = card.querySelector('.episode-header');
      const idx = el.classList.contains('episode-line') ? [...card.querySelectorAll('.episode-line')].indexOf(el) : -1;
      return { file: header.dataset.file, idx, dy: Math.round(el.getBoundingClientRect().top) };
    }
    function scrollToMediaAnchor(state) {
      const at = state.at;
      const header = at && [...document.querySelectorAll('#results .episode-header')].find(h => h.dataset.file === at.file);
      const el = header && (at.idx < 0 ? header : header.parentElement.querySelectorAll('.episode-line')[at.idx]);
      if (!el) { window.scrollTo(0, state.y || 0); return; }
      el.scrollIntoView({ block: 'start' });
      window.scrollBy(0, el.getBoundingClientRect().top - at.dy);
    }
    let mediaScrollQueued = false;
    window.addEventListener('scroll', () => {
      if (TAB !== 'media' || mediaScrollQueued) return;
      mediaScrollQueued = true;
      setTimeout(() => { mediaScrollQueued = false; saveMediaState(); }, 300);
    }, { passive: true });

    async function restoreMediaState(state) {
      mediaRestoring = true;
      try {
        if (state.mode === 'title' || state.mode === 'content') {
          setMediaDetailMode(state.mode, true);
        }
        if (state.mode === 'content' && state.q) {
          const qEl = document.getElementById('media-detail-q');
          const exactEl = document.getElementById('media-detail-exact');
          const chipEl = document.getElementById('media-detail-exact-chip');
          if (qEl) qEl.value = state.q;
          if (exactEl) exactEl.checked = !!state.exact;
          if (chipEl) chipEl.classList.toggle('on', !!state.exact);
          await runMediaDetailContentSearch(state.q, !!state.exact);
          scrollToMediaAnchor(state);
          return;
        }
        if (state.mode === 'title' && state.q) {
          const filterEl = document.getElementById('media-detail-filter');
          if (filterEl) {
            filterEl.value = state.q;
            filterMediaDetailTitles(state.q);
          }
        }
        for (const o of state.open || []) {
          const header = [...document.querySelectorAll('#results .episode-header')].find(h => h.dataset.file === o.file);
          if (!header) continue;
          await expandEpisode(header);
          const content = header.parentElement.querySelector('.episode-content');
          while (content.querySelectorAll('.episode-line').length < o.loaded) {
            const sentinel = content.querySelector('.ep-sentinel');
            if (!sentinel) break;
            epSentinelObserver.unobserve(sentinel);
            await loadMoreEpisodeSentinel(sentinel, sentinel.dataset.file, parseInt(sentinel.dataset.offset, 10));
          }
        }
        scrollToMediaAnchor(state);
      } finally {
        mediaRestoring = false;
      }
    }

    function handleMediaTabClick(e) {
      if (TAB === 'media') {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      const last = readMediaState();
      if (last) {
        e.preventDefault();
        window.location.href = last.url;
      }
    }

    function fmtEta(sec) {
      if (sec == null) return '';
      if (sec < 2) return t('eta_soon');
      const s = Math.ceil(sec);
      if (s < 60) return t('eta_left', { t: t('eta_s', { n: s }) });
      const m = Math.floor(s / 60), r = s % 60;
      return t('eta_left', { t: r && m < 10 ? t('eta_ms', { m, s: r }) : t('eta_m', { m: Math.round(s / 60) }) });
    }

    const MEDIA_PAGE = '500';
    const MEDIA_SORTS = ['name', 'parts_desc', 'parts_asc', 'lines_desc', 'lines_asc'];
    function mediaSort() {
      const v = store.get('mediaSort', 'name');
      return MEDIA_SORTS.includes(v) ? v : 'name';
    }
    function mediaSortLabel(v) { return t('media_sort_' + v); }
    let mediaGen = 0, mediaCtrl = null, mediaOffset = 0, mediaHasMore = false, mediaBusy = false;
    let mediaMoreObserver = null, mediaFilterTimer = null;

    async function fetchMedia(params, signal, onWait) {
      for (;;) {
        const r = await fetch('/api/media?' + params.toString(), { signal });
        if (r.status !== 202) return r.json();
        const st = await r.json();
        if (onWait) onWait(st);
        await new Promise(res => setTimeout(res, 700));
      }
    }

    function mediaRowHtml(it) {
      const p = new URLSearchParams({ tab: 'media', folder: it.folder, media: it.media });
      return `<a class="media-row" href="/?${p.toString()}" draggable="false">
          <span class="media-kind ${it.media}">${esc(t('kind_' + it.media))}</span>
          <span class="media-names">
            <div class="media-name">${esc(it.folder)}</div>
            ${it.author ? `<div class="media-author">${esc(it.author)}</div>` : ''}
          </span>
          <span class="media-stats">${statPills(it)}</span>
        </a>`;
    }

    async function loadMediaPage(reset) {
      if (reset) {
        mediaGen++;
        if (mediaCtrl) mediaCtrl.abort();
        mediaOffset = 0; mediaHasMore = false; mediaBusy = false;
      }
      if (mediaBusy) return;
      mediaBusy = true;
      const gen = mediaGen;
      mediaCtrl = new AbortController();
      const needle = (document.getElementById('media-filter').value || '').trim();
      const params = new URLSearchParams({ media: mediaTabFilter(), q: needle,
        offset: String(mediaOffset), limit: MEDIA_PAGE, sort: mediaSort() });
      const listEl = document.getElementById('media-list');
      const moreEl = document.getElementById('media-more');
      let data;
      try {
        data = await fetchMedia(params, mediaCtrl.signal, st => {
          if (gen !== mediaGen || mediaOffset) return;
          listEl.innerHTML = `<div class="status-line" style="padding:2em;text-align:center;">${esc(t('media_preparing'))}…` +
            `<div class="load-eta">${esc(fmtEta(st.remaining))}</div></div>`;
        });
      } catch (e) {
        if (e.name !== 'AbortError' && gen === mediaGen) {
          listEl.innerHTML = `<div class="status-line error-text" style="padding:2em;">${esc(t('load_failed'))}</div>`;
        }
        mediaBusy = false;
        return;
      }
      if (gen !== mediaGen) return;
      mediaBusy = false;
      if (!mediaOffset && !needle && !data.total && mediaTabUnfiltered()) {
        document.getElementById('media-body').hidden = true;
        document.getElementById('media-empty').hidden = false;
        return;
      }
      const counts = { subs: data.shows, epub: data.books, manga: data.manga };
      let summary = MEDIAS_ON.map(m => t('media_summary_' + m, { n: fmt(counts[m] || 0) })).join(' · ');
      if (needle || !mediaTabUnfiltered()) summary += ' · ' + t('media_matches', { n: fmt(data.total) });
      document.getElementById('media-summary').textContent = summary;
      const html = data.items.map(mediaRowHtml).join('');
      if (!mediaOffset) {
        listEl.innerHTML = html || `<div class="status-line" style="padding:2em;">${esc(t('media_none'))}</div>`;
      } else {
        listEl.insertAdjacentHTML('beforeend', html);
      }
      mediaOffset += data.items.length;
      mediaHasMore = data.has_more;
      moreEl.textContent = mediaHasMore ? t('loading') : '';
      if (mediaHasMore) watchMediaEnd();
    }

    function watchMediaEnd() {
      const moreEl = document.getElementById('media-more');
      if (!mediaMoreObserver) {
        mediaMoreObserver = new IntersectionObserver(entries => {
          if (entries.some(e => e.isIntersecting) && mediaHasMore && !mediaBusy) loadMediaPage(false);
        }, { rootMargin: '800px 0px' });
      }
      mediaMoreObserver.unobserve(moreEl);
      mediaMoreObserver.observe(moreEl);
    }

    async function initMediaTab() {
      const folder = PARAMS.get('folder');
      if (folder) return initMediaDetail(folder);
      store.set(MEDIA_STATE, JSON.stringify({ url: mediaUrl(), open: [], y: 0 }));
      setTitle(t('tab_media'));
      initMediaSort();
      document.getElementById('media-list').innerHTML = `<div class="status-line" style="padding:2em;">${esc(t('loading'))}</div>`;
      loadMediaPage(true);
    }
    function initMediaSort() {
      makeDropdown(document.getElementById('media-sort'), {
        options: MEDIA_SORTS.map(v => ({ value: v, label: mediaSortLabel(v) })),
        value: mediaSort(), title: t('media_sort_title'), icon: ICON_ROWS,
        onChange: v => { store.set('mediaSort', v); initMediaSort(); loadMediaPage(true); },
      });
    }

    function setMediaTabFilter(m) {
      store.set('mediaTabFilter', m);
      document.querySelectorAll('#media-seg .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.media === m));
      loadMediaPage(true);
    }

    function onMediaFilterInput() {
      clearTimeout(mediaFilterTimer);
      mediaFilterTimer = setTimeout(() => loadMediaPage(true), 150);
    }

    async function initMediaDetail(folder) {
      setTitle(folder);
      document.getElementById('media-body').hidden = true;
      const head = document.getElementById('media-detail');
      head.hidden = false;
      head.after(document.getElementById('main-loading'), document.getElementById('results'));
      const media = MEDIAS_ALL.includes(PARAMS.get('media')) ? PARAMS.get('media') : 'all';
      mediaDetailFolder = folder;
      mediaDetailMedia = media;
      mediaDetailContentActive = false;
      head.innerHTML = `<a class="back-link" href="/?tab=media">← ${esc(t('back_media'))}</a><h1>${esc(folder)}</h1><div id="media-detail-meta"></div>
        <div class="media-detail-search">
          <input id="media-detail-filter" class="folder-filter" type="text" placeholder="${esc(t('media_detail_filter_' + (media === 'all' ? 'subs' : media)))}" spellcheck="false" autocomplete="off" oninput="onMediaDetailTitleInput()" ${mediaDetailMode === 'title' ? '' : 'hidden'}>
          <form id="media-detail-form" class="media-detail-form" autocomplete="off" onsubmit="onMediaDetailContentSubmit(event)" ${mediaDetailMode === 'content' ? '' : 'hidden'}>
            <div class="search-input-wrap">
              <input id="media-detail-q" class="search-input" type="text" placeholder="${esc(t('placeholder'))}" value="" autocomplete="off" spellcheck="false" oninput="onMediaDetailContentInput(this)">
              <span class="search-btn-box">
                <button type="submit" class="search-btn" aria-label="${esc(t('tab_search'))}">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg>
                </button>
              </span>
            </div>
            <label class="exact-chip" id="media-detail-exact-chip" title="${esc(t('exact_title'))}">
              <input type="checkbox" id="media-detail-exact" onchange="onMediaDetailExactChange(this)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>
              <span>${esc(t('exact'))}</span>
            </label>
          </form>
          <div class="seg" id="media-detail-seg">
            <button type="button" class="seg-btn ${mediaDetailMode === 'title' ? 'active' : ''}" data-mode="title" onclick="setMediaDetailMode('title')">${esc(t('media_mode_title'))}</button>
            <button type="button" class="seg-btn ${mediaDetailMode === 'content' ? 'active' : ''}" data-mode="content" onclick="setMediaDetailMode('content')">${esc(t('media_mode_content'))}</button>
          </div>
        </div>`;
      const mdQ = document.getElementById('media-detail-q');
      if (mdQ) {
        mdQ.addEventListener('compositionstart', () => { isComposing = true; });
        mdQ.addEventListener('compositionend', () => {
          isComposing = false;
          justConfirmed = true;
          setTimeout(() => { justConfirmed = false; }, 60);
        });
        mdQ.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && (e.isComposing || e.keyCode === 229 || isComposing || justConfirmed)) {
            e.preventDefault();
            return false;
          }
        });
      }
      document.getElementById('main-loading').style.display = 'flex';
      try {
        const [ep, lib] = await Promise.all([
          fetch(`/api/episodes?folder=${encodeURIComponent(folder)}&media=${encodeURIComponent(media)}`).then(r => r.json()),
          fetchMedia(new URLSearchParams({ folder, media })),
        ]);
        const it = (lib.items || [])[0];
        if (it) {
          if (it.media && mediaDetailMedia === 'all') {
            mediaDetailMedia = it.media;
            const fEl = document.getElementById('media-detail-filter');
            if (fEl) fEl.placeholder = t('media_detail_filter_' + it.media);
          }
          document.getElementById('media-detail-meta').innerHTML =
            `${it.author ? `<div class="muted">${esc(it.author)}</div>` : ''}<div class="media-stats">${statPills(it)}</div>`;
        }
        mediaDetailFiles = ep.files || [];
        renderEpisodesList(mediaDetailFiles);
        const state = readMediaState();
        if (state && state.url === mediaUrl()) {
          document.getElementById('main-loading').style.display = 'none';
          await restoreMediaState(state);
        }
        saveMediaState();
      } catch (e) {
        document.getElementById('results').innerHTML = `<div class="error-text">${esc(t('load_failed'))}</div>`;
      } finally {
        document.getElementById('main-loading').style.display = 'none';
      }
    }

    function setMediaDetailMode(mode, quiet) {
      mediaDetailMode = mode === 'content' ? 'content' : 'title';
      store.set('mediaDetailMode', mediaDetailMode);
      document.querySelectorAll('#media-detail-seg .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mediaDetailMode));
      const filterEl = document.getElementById('media-detail-filter');
      const formEl = document.getElementById('media-detail-form');
      if (filterEl) filterEl.hidden = mediaDetailMode !== 'title';
      if (formEl) formEl.hidden = mediaDetailMode !== 'content';
      if (quiet) return;
      if (mediaDetailMode === 'title') {
        if (mediaDetailCtrl) { mediaDetailCtrl.abort(); cancelServerSearch(); }
        mediaDetailGen++;
        stopSearchEta();
        document.getElementById('main-loading').style.display = 'none';
        mediaDetailContentActive = false;
        filterMediaDetailTitles(filterEl ? filterEl.value : '');
        if (filterEl) filterEl.focus();
      } else {
        const qEl = document.getElementById('media-detail-q');
        const exactEl = document.getElementById('media-detail-exact');
        const qVal = qEl ? qEl.value.trim() : '';
        if (qVal) {
          runMediaDetailContentSearch(qVal, !!(exactEl && exactEl.checked));
        } else {
          renderEpisodesList(mediaDetailFiles);
        }
        if (qEl) qEl.focus();
      }
      saveMediaState();
    }

    function onMediaDetailTitleInput() {
      const filterEl = document.getElementById('media-detail-filter');
      filterMediaDetailTitles(filterEl ? filterEl.value : '');
      saveMediaState();
    }

    function filterMediaDetailTitles(rawNeedle) {
      const needle = (rawNeedle || '').trim().toLowerCase();
      if (!needle) {
        renderEpisodesList(mediaDetailFiles);
        return;
      }
      const matched = mediaDetailFiles.filter(it => (it.title || '').toLowerCase().includes(needle) || (it.file || '').toLowerCase().includes(needle));
      if (!matched.length) {
        document.getElementById('results').innerHTML = `<div class="status-line" style="padding:2em;">${esc(t('media_none'))}</div>`;
        return;
      }
      renderEpisodesList(matched);
    }

    function onMediaDetailContentInput(input) {
      if (!input.value.trim() && mediaDetailContentActive) {
        clearMediaDetailContentSearch();
      }
    }

    function onMediaDetailExactChange(cb) {
      const chip = document.getElementById('media-detail-exact-chip');
      if (chip) chip.classList.toggle('on', cb.checked);
      const qEl = document.getElementById('media-detail-q');
      const qVal = qEl ? qEl.value.trim() : '';
      if (qVal) runMediaDetailContentSearch(qVal, cb.checked);
    }

    function onMediaDetailContentSubmit(e) {
      e.preventDefault();
      if (isComposing || justConfirmed) return;
      const qEl = document.getElementById('media-detail-q');
      const exactEl = document.getElementById('media-detail-exact');
      const qVal = qEl ? qEl.value.trim() : '';
      if (!qVal) {
        clearMediaDetailContentSearch();
        return;
      }
      runMediaDetailContentSearch(qVal, !!(exactEl && exactEl.checked));
    }

    function clearMediaDetailContentSearch() {
      if (mediaDetailCtrl) { mediaDetailCtrl.abort(); cancelServerSearch(); }
      mediaDetailGen++;
      stopSearchEta();
      document.getElementById('main-loading').style.display = 'none';
      mediaDetailContentActive = false;
      renderEpisodesList(mediaDetailFiles);
      saveMediaState();
    }

    const MEDIA_DETAIL_PAGE = 500;
    let mediaDetailSentinelObs = null;

    function appendMediaDetailMatches(results, q) {
      const container = document.getElementById('results');
      const order = new Map(mediaDetailFiles.map((it, i) => [it.file, i]));
      const byFile = new Map();
      for (const r of results) {
        if (!byFile.has(r.file)) byFile.set(r.file, []);
        byFile.get(r.file).push(r);
      }
      for (const [fileKey, rows] of byFile) {
        const safeFile = encodeURIComponent(fileKey);
        let card = [...container.querySelectorAll('.episode-card')].find(c => c.dataset.file === safeFile);
        if (!card) {
          const item = mediaDetailFiles[order.get(fileKey)] || { file: fileKey, title: (rows[0] && rows[0].title) || fileKey };
          const fileHash = btoa(unescape(encodeURIComponent(fileKey))).substring(0, 32).replace(/=/g, '');
          const tpl = document.createElement('template');
          tpl.innerHTML = `
            <div class="card episode-card" id="ep-card-${fileHash}" data-file="${safeFile}">
                <div class="episode-header" data-file="${safeFile}" onclick="expandEpisode(this)">
                    <div class="episode-title">${esc(item.title)}</div>
                    <div class="episode-toggle-icon">▼</div>
                </div>
                <div class="episode-content"></div>
            </div>`.trim();
          card = tpl.content.firstChild;
          const idx = order.has(fileKey) ? order.get(fileKey) : Infinity;
          const next = [...container.querySelectorAll('.episode-card')].find(c => {
            const j = order.get(decodeURIComponent(c.dataset.file));
            return (j === undefined ? Infinity : j) > idx;
          });
          container.insertBefore(card, next || container.querySelector('.md-tail, .md-sentinel'));
        }
        card.querySelector('.episode-content').insertAdjacentHTML('beforeend', renderBrowseLinesHTML(rows, q));
      }
    }

    function addMediaDetailSentinel(qs, offset, gen) {
      const container = document.getElementById('results');
      const sentinel = document.createElement('div');
      sentinel.className = 'md-sentinel';
      sentinel.innerHTML = '<div class="spinner" style="margin:20px auto;"></div>';
      container.insertBefore(sentinel, container.querySelector('.md-tail'));
      if (mediaDetailSentinelObs) mediaDetailSentinelObs.disconnect();
      mediaDetailSentinelObs = new IntersectionObserver(async (entries) => {
        if (!entries.some(e => e.isIntersecting)) return;
        mediaDetailSentinelObs.disconnect();
        const next = new URLSearchParams(qs);
        next.set('offset', String(offset));
        serverSearchInFlight++;
        try {
          const res = await fetch(apiSearchUrl(next.toString()), { signal: mediaDetailCtrl.signal });
          const data = await res.json();
          if (gen !== mediaDetailGen || data.aborted) return;
          sentinel.remove();
          appendMediaDetailMatches(data.results || [], qs.get('q'));
          if (data.has_more) addMediaDetailSentinel(qs, offset + MEDIA_DETAIL_PAGE, gen);
        } catch (e) {
          if (e.name !== 'AbortError' && gen === mediaDetailGen) {
            sentinel.innerHTML = `<div class="error-text" style="padding:1em;">${esc(t('error'))}</div>`;
          }
        } finally {
          serverSearchInFlight = Math.max(0, serverSearchInFlight - 1);
        }
      }, { rootMargin: '800px 0px 800px 0px' });
      mediaDetailSentinelObs.observe(sentinel);
    }

    async function runMediaDetailContentSearch(q, exact) {
      if (mediaDetailSentinelObs) mediaDetailSentinelObs.disconnect();
      if (mediaDetailCtrl) { mediaDetailCtrl.abort(); cancelServerSearch(0); }
      mediaDetailCtrl = new AbortController();
      const gen = ++mediaDetailGen;
      const resultsContainer = document.getElementById('results');
      resultsContainer.innerHTML = '';
      document.getElementById('main-loading').style.display = 'flex';
      const qs = new URLSearchParams({
        q,
        folder: mediaDetailFolder,
        media: mediaDetailMedia,
        sort: 'chrono',
        limit: String(MEDIA_DETAIL_PAGE),
        offset: '0',
      });
      if (exact) qs.set('exact', 'on');
      startSearchEta(qs.toString(), gen, () => mediaDetailGen);
      serverSearchInFlight++;
      try {
        const res = await fetch(apiSearchUrl(qs.toString()), { signal: mediaDetailCtrl.signal });
        const data = await res.json();
        if (gen !== mediaDetailGen || data.aborted) return;
        mediaDetailContentActive = true;
        if (!(data.results || []).length) {
          resultsContainer.innerHTML = `<div class="status-line" style="padding:2em;">${esc(t('no_results'))}</div>`;
          saveMediaState();
          return;
        }
        hasMoreResults = false;
        if (loadMoreObserver) loadMoreObserver.disconnect();
        appendMediaDetailMatches(data.results, q);
        resultsContainer.insertAdjacentHTML('beforeend', '<div class="md-tail" style="height: 4em; width: 100%;"></div>');
        if (data.has_more) addMediaDetailSentinel(qs, MEDIA_DETAIL_PAGE, gen);
        saveMediaState();
      } catch (e) {
        if (e.name !== 'AbortError' && gen === mediaDetailGen) {
          resultsContainer.innerHTML = `<div class="error-text" style="padding:1em;">${esc(t('error'))}</div>`;
        }
      } finally {
        serverSearchInFlight = Math.max(0, serverSearchInFlight - 1);
        if (gen === mediaDetailGen) {
          stopSearchEta();
          document.getElementById('main-loading').style.display = 'none';
        }
      }
    }

    function renderEpisodesList(filesList) {
      const resultsContainer = document.getElementById('results');
      let html = '';
      filesList.forEach(item => {
         const fileHash = btoa(unescape(encodeURIComponent(item.file))).substring(0, 32).replace(/=/g, '');
         const safeFile = encodeURIComponent(item.file);
         html += `
            <div class="card episode-card collapsed" id="ep-card-${fileHash}">
                <div class="episode-header" data-file="${safeFile}" onclick="expandEpisode(this)">
                    <div class="episode-title">${esc(item.title)}</div>
                    <div class="episode-toggle-icon">▼</div>
                </div>
                <div class="episode-content"></div>
            </div>`;
      });
      html += '<div style="height: 4em; width: 100%;"></div>';
      resultsContainer.innerHTML = html;
      hasMoreResults = false;
      if (loadMoreObserver) loadMoreObserver.disconnect();
    }

    async function expandEpisode(header) {
       const fileEnc = header.dataset.file;
       const card = header.parentElement;
       const content = card.querySelector('.episode-content');

       if (card.classList.contains('collapsed')) {
           card.classList.remove('collapsed');

           if (content.innerHTML.trim() === '') {
               content.innerHTML = '<div class="spinner" style="margin-top:20px; margin-bottom:20px;"></div>';
               const folder = PARAMS.get('folder');
               const media = PARAMS.get('media') || 'all';
               try {
                   const response = await fetch(apiSearchUrl(`folder=${encodeURIComponent(folder)}&file=${fileEnc}&media=${encodeURIComponent(media)}&sort=chrono&limit=500&offset=0`));
                   const data = await response.json();
                   content.innerHTML = renderBrowseLinesHTML(data.results);
                   if (data.has_more) {
                       const sentinelHtml = `<div class="ep-sentinel" data-file="${fileEnc}" data-offset="500" style="height:1px;"></div>`;
                       content.insertAdjacentHTML('beforeend', sentinelHtml);
                       const sentinel = content.querySelector('.ep-sentinel');
                       if (sentinel) epSentinelObserver.observe(sentinel);
                   }
               } catch(e) {
                   content.innerHTML = `<div class="error-text" style="padding:1em;">${esc(t('error'))}</div>`;
               }
           }
           saveMediaState();
       } else {
           card.classList.add('collapsed');
           saveMediaState();
       }
    }

    async function loadMoreEpisodeSentinel(sentinel, fileEnc, offset) {
       if (!sentinel.isConnected || sentinel.dataset.loading) return;
       sentinel.dataset.loading = '1';
       const content = sentinel.parentElement;
       const folder = PARAMS.get('folder');
       const media = PARAMS.get('media') || 'all';
       try {
           sentinel.innerHTML = `<div class="status-line" style="padding:1.5em;">${esc(t('loading'))}</div>`;
           const response = await fetch(apiSearchUrl(`folder=${encodeURIComponent(folder)}&file=${fileEnc}&media=${encodeURIComponent(media)}&sort=chrono&limit=500&offset=${offset}`));
           const data = await response.json();
           sentinel.remove();
           content.insertAdjacentHTML('beforeend', renderBrowseLinesHTML(data.results));
           if (data.has_more) {
               const sentinelHtml = `<div class="ep-sentinel" data-file="${fileEnc}" data-offset="${offset + 500}" style="height:1px;"></div>`;
               content.insertAdjacentHTML('beforeend', sentinelHtml);
               const newSentinel = content.querySelector('.ep-sentinel:last-child');
               if (newSentinel) epSentinelObserver.observe(newSentinel);
           }
           saveMediaState();
       } catch(e) {}
    }

    function renderBrowseLinesHTML(results, origQ = '') {
        let linesHtml = '';
        let page = null;
        results.forEach(r => {
            if (r.page && r.page !== page) {
                page = r.page;
                linesHtml += `<div class="page-mark">${pageLabel({...r, media_type: 'manga'})}</div>`;
            }
            const rId = lineId(r.line);
            const isSaved = savedSentences.some(s => s.id === rId);
            const savedItemData = {...r, id: rId, original_q: origQ};
            linesHtml += `
              <div class="episode-line">
                  <span class="main-sentence">${r.display_line}</span>
                  <div class="actions-box">
                    <button class="icon-btn ${isSaved ? 'star-active' : ''}" onclick="toggleSave('${rId}', this)" data-star="${starKey(savedItemData)}" aria-label="${esc(t('sc_save'))}">
                      <span>★</span>
                    </button>
                  </div>
              </div>`;
        });
        return linesHtml;
    }

    let libPoll = null;
    let libWasRunning = false;
    let libLast = null;
    let tableRunStartedHere = false;
    let optimizeDoneThisVisit = false;
    let figPoll = null;

    function pollFigures() {
      if (figPoll) return;
      figPoll = setInterval(async () => {
        let f;
        try { f = await fetch('/api/library/figures').then(r => r.json()); } catch (e) { return; }
        if (!libLast) return;
        Object.assign(libLast, f);
        for (const [which, disk, indexed, path] of [['subs', f.subs_disk, libLast.subs_indexed, libLast.subs_dir],
                                                    ['books', f.books_disk, libLast.books_indexed, libLast.books_dir],
                                                    ['manga', f.manga_disk, libLast.manga_indexed, libLast.manga_dir]]) {
          const box = document.querySelector(`#lib-card-${which} .lib-facts`);
          if (box) box.innerHTML = folderFacts(which, path, disk, indexed, f.counting);
        }
        if (!f.counting) { clearInterval(figPoll); figPoll = null; pollActivity(); }
      }, 500);
    }

    async function initLibraryTab() {
      setTitle(t('tab_library'));
      await refreshLibrary();
      if (location.hash === '#lib-workers') document.getElementById('lib-workers').scrollIntoView({ block: 'start' });
      loadAnalysis();
    }

    let settingsShown = false;
    function renderSettings(lib) {
      folderPicker = !!lib.folder_picker;
      renderMediaCard(lib);
      renderDbCard(lib);
      renderPortCard(lib);
      renderSearchWorkersCard(lib.search_workers);
      settingsShown = true;
    }

    async function initSettingsTab() {
      setTitle(t('tab_settings'));
      try {
        const cached = await fetch('/api/library/settings-snapshot').then(r => r.json());
        if (cached.settings) renderSettings(cached.settings);
      } catch (e) {}
      await refreshSettings();
    }

    async function refreshSettings() {
      let lib;
      try { lib = await fetch('/api/library/settings').then(r => r.json()); }
      catch (e) {
        if (!settingsShown) document.getElementById('lib-data').innerHTML = `<div class="error-text">${esc(t('load_failed'))}</div>`;
        return;
      }
      renderSettings(lib);
    }

    const MEDIA_DB = { subs: 'subs.db', books: 'epub.db', manga: 'manga.db' };
    const MEDIA_KINDS = ['subs', 'books', 'manga'];
    function renderMediaCard(lib, msg) {
      const on = lib.media || { subs: true, books: true, manga: false };
      const rows = MEDIA_KINDS.map(which => {
        const path = lib[which + '_dir'];
        const size = (lib.db_sizes || {})[MEDIA_DB[which]];
        const folder = !on[which] ? '' : `
          ${path == null ? `<div class="facts"><div>${esc(t('set_not_set'))}</div></div>` : `<span class="path">${esc(path)}</span>`}
          <div class="lib-edit" hidden>
            <input type="text" value="${esc(path ?? '')}" placeholder="${esc(t('lib_change_hint'))}" spellcheck="false">
            <div class="btns">
              <button class="btn primary" onclick="saveFolder('${which}')">${esc(t('lib_save'))}</button>
              <button class="btn" onclick="toggleFolderEdit('${which}', false)">${esc(t('lib_cancel'))}</button>
            </div>
            <div class="lib-msg facts" style="margin:0.5em 0 0;"></div>
          </div>
`;
        const drop = size == null ? '' : `<button class="btn set-drop" onclick="askDrop('${which}')">${esc(t('set_drop', { size: fmtBytes(size) }))}</button>`;
        const buttons = `<div class="btns lib-view-btns">
            ${on[which] ? `${ON_PHONE ? '' : `<button class="btn" onclick="openFolder('${which}', this)" ${path == null ? 'disabled' : ''}>${esc(t('lib_open'))}</button>`}
            <button class="btn" onclick="changeFolder('${which}')">${esc(t('lib_change'))}</button>` : ''}
            ${drop}
          </div>
          <div class="lib-open-msg facts" role="status"></div>
          <div class="set-drop-ask" hidden></div>`;
        return `<div class="set-media-row" id="set-media-${which}">
          <div class="btns set-media-head">
            <strong>${esc(t('set_media_' + which))}</strong>
            <div class="seg" style="width:12em;">
              <button type="button" class="seg-btn ${on[which] ? '' : 'active'}" onclick="setMediaOn('${which}', false)">${esc(t('lib_cache_off'))}</button>
              <button type="button" class="seg-btn ${on[which] ? 'active' : ''}" onclick="setMediaOn('${which}', true)">${esc(t('lib_cache_on'))}</button>
            </div>
          </div>
          ${folder}
          ${buttons}
          <div class="lib-pick-msg facts" style="margin:0.5em 0 0;"></div>
        </div>`;
      }).join('');
      document.getElementById('set-media').innerHTML = `
        <h3>${esc(t('set_media_title'))}</h3>
        <div class="facts"><div>${esc(t('set_media_lead'))}</div></div>
        ${rows}
        <div class="lib-msg facts set-media-msg" style="margin:0.5em 0 0;">${msg || ''}</div>`;
    }

    async function setMediaOn(which, on) {
      const res = await apiPost('/api/library', { media: { [which]: on } }).catch(() => ({ error: 'network' }));
      await refreshSettings();
      if (res.error) document.querySelector('#set-media .set-media-msg').innerHTML =
        `<span class="warn">${esc(res.error === 'busy' ? t('lib_err_busy') : t('lib_err_notfound'))}</span>`;
    }

    function askDrop(which) {
      const row = document.getElementById(`set-media-${which}`);
      const size = row.querySelector('.set-drop').textContent.match(/[（(](.*)[）)]/);
      const ask = row.querySelector('.set-drop-ask');
      row.querySelector('.lib-view-btns').hidden = true;
      ask.hidden = false;
      ask.innerHTML = `<div class="notice">${esc(t('set_drop_confirm', { media: t('set_media_' + which), file: MEDIA_DB[which], size: size ? size[1] : '' }))}</div>
        <div class="btns">
          <button class="btn primary" onclick="dropIndex('${which}')">${esc(t('set_drop_yes'))}</button>
          <button class="btn" onclick="cancelDrop('${which}')">${esc(t('lib_cancel'))}</button>
        </div>`;
    }
    function cancelDrop(which) {
      const row = document.getElementById(`set-media-${which}`);
      row.querySelector('.set-drop-ask').hidden = true;
      row.querySelector('.lib-view-btns').hidden = false;
    }

    async function dropIndex(which) {
      document.querySelectorAll('#set-media button').forEach(b => b.disabled = true);
      const res = await apiPost('/api/library/drop', { which }).catch(() => ({ error: 'network' }));
      let msg = esc(t('set_dropped'));
      if (res.error) msg = `<span class="warn">${esc(res.error === 'busy' ? t('set_drop_busy') : t('load_failed'))}</span>`;
      else if ((res.kept || []).length) msg = `<span class="warn">${esc(t('set_drop_kept'))}</span>`;
      let lib;
      try { lib = await fetch('/api/library').then(r => r.json()); } catch (e) { return; }
      renderMediaCard(lib, msg);
      renderDbCard(lib);
    }

    async function refreshLibrary() {
      let lib;
      try { lib = await fetch('/api/library').then(r => r.json()); }
      catch (e) { document.getElementById('lib-folders').innerHTML = `<div class="error-text">${esc(t('load_failed'))}</div>`; return; }
      document.getElementById('lib-folders').innerHTML =
        (MEDIA_ON.subs ? folderCard('subs', t('lib_subs'), lib.subs_dir, lib.subs_disk, lib.subs_indexed, lib.counting) : '') +
        (MEDIA_ON.epub ? folderCard('books', t('lib_books'), lib.books_dir, lib.books_disk, lib.books_indexed, lib.counting) : '') +
        (MEDIA_ON.manga ? folderCard('manga', t('lib_manga'), lib.manga_dir, lib.manga_disk, lib.manga_indexed, lib.counting) : '');
      const scope = document.getElementById('lib-scope');
      scope.hidden = MEDIAS_ON.length < 2;
      scope.querySelectorAll('option[value]').forEach(o => { if (o.value) o.hidden = !MEDIA_ON[o.value]; });
      if (scope.hidden || (scope.value && !MEDIA_ON[scope.value])) scope.value = '';
      syncCheckScope();
      libLast = lib;
      renderWorkersCard(lib.workers);
      if (lib.counting) { pollFigures(); pollActivity(); }
      folderPicker = !!lib.folder_picker;
      renderOutdated(lib);
      renderIndexStatus(lib.index);
      if (lib.index && lib.index.running) startPolling();
    }

    function folderFacts(which, path, disk, indexed, counting) {
      let facts = '';
      if (path == null) {
        facts = `<div>${esc(t('lib_not_set'))}</div>`;
      } else if (!disk) {
        facts = counting ? `<div>${esc(t('lib_counting'))}</div>` : `<div class="warn">${esc(t('lib_missing'))}</div>`;
      } else {
        const more = disk.counting ? ' ' + esc(t('lib_counting')) : '';
        facts += `<div>${esc(t('lib_disk_' + which, { n: fmt(disk.files) }))}${more}</div>`;
        if (disk.other) facts += `<div>${esc(t('lib_other', { n: fmt(disk.other) }))}</div>`;
        if (disk.filtered) facts += `<div>${esc(t('lib_filtered', { n: fmt(disk.filtered) }))}</div>`;
      }
      facts += `<div>${esc(t('lib_indexed_' + which, { files: fmt(indexed.files), rows: fmt(indexed.rows) }))}</div>`;
      return facts;
    }

    function folderCard(which, title, path, disk, indexed, counting) {
      return `<div class="lib-card" id="lib-card-${which}">
        <h3>${esc(title)}</h3>
        ${path == null ? '' : `<span class="path">${esc(path)}</span>`}
        <div class="facts lib-facts">${folderFacts(which, path, disk, indexed, counting)}</div>
        ${ON_PHONE ? '' : `<div class="btns lib-view-btns">
          <button class="btn" onclick="openFolder('${which}', this)" ${disk ? '' : 'disabled'}>${esc(t('lib_open'))}</button>
        </div>`}
        <div class="lib-open-msg facts" role="status"></div>
      </div>`;
    }

    function outdatedMedia(lib) {
      return [['subs', lib.subs_outdated], ['epub', lib.books_outdated], ['manga', lib.manga_outdated]]
        .filter(([kind, count]) => MEDIA_ON[kind] && count > 0);
    }
    function outdatedSummary(outdated) {
      return outdated.map(([kind, count]) => `${t('lib_stage_' + kind)} ${fmt(count)}`).join(' · ');
    }
    function renderOutdated(lib) {
      const box = document.getElementById('lib-outdated');
      const button = document.getElementById('lib-optimize');
      const outdated = outdatedMedia(lib);
      const tables = [['subs', lib.subs_tables], ['epub', lib.books_tables], ['manga', lib.manga_tables]]
        .filter(([, missing]) => (missing || []).length).map(([kind]) => kind);
      button.hidden = !(tables.length || optimizeDoneThisVisit);
      button.disabled = !!(lib.index && lib.index.running) || optimizeDoneThisVisit;
      button.querySelector('span').textContent = t(optimizeDoneThisVisit ? 'lib_tables_done_short' : 'lib_tables_run');
      let html = '';
      if (outdated.length) {
        const only = outdated.length === 1 ? outdated[0][0] : '';
        html += `<div>${esc(t('lib_outdated', { which: outdatedSummary(outdated) }))}</div>
          <div class="btns" style="display:flex; gap:0.5em; margin-top:0.6em;">
            <button class="btn primary" onclick="startIndex('${only}', true)">${esc(t('lib_outdated_run'))}</button></div>`;
      }
      if (tables.length || optimizeDoneThisVisit) {
        const message = optimizeDoneThisVisit ? t('lib_tables_ready')
          : t('lib_tables', { which: tables.map(k => t('lib_stage_' + k)).join(LANG === 'ja' ? '・' : ' · ') });
        html += `<div${outdated.length ? ' style="margin-top:1em;"' : ''}>${esc(message)}</div>`;
      }
      box.innerHTML = html;
      box.hidden = !html;
    }

    let folderPicker = false;
    async function pickFolder(card, which, title) {
      const msg = card.querySelector('.lib-pick-msg') || card.querySelector('.lib-msg');
      const buttons = [...card.querySelectorAll('.lib-view-btns button')];
      const was = buttons.map(b => b.disabled);
      buttons.forEach(b => b.disabled = true);
      msg.textContent = t('lib_picking');
      const res = await apiPost('/api/library/pick', { which, title }).catch(() => ({ status: 'unavailable' }));
      buttons.forEach((b, i) => b.disabled = was[i]);
      msg.textContent = '';
      return res;
    }
    async function changeFolder(which) {
      if (!folderPicker) return toggleFolderEdit(which, true);
      const card = document.getElementById(`set-media-${which}`);
      const res = await pickFolder(card, which, t('lib_' + which));
      if (res.status === 'unavailable') return toggleFolderEdit(which, true);
      if (res.status !== 'ok') return;
      card.querySelector('.lib-edit input').value = res.path;
      if (!(await saveFolder(which))) toggleFolderEdit(which, true);
    }
    async function changeDbFolder() {
      if (!folderPicker) return toggleDbEdit(true);
      const card = document.getElementById('lib-data');
      const res = await pickFolder(card, 'data', t('lib_data'));
      if (res.status === 'unavailable') return toggleDbEdit(true);
      if (res.status !== 'ok') return;
      toggleDbEdit(true);
      card.querySelector('.lib-edit input').value = res.path;
    }

    function toggleFolderEdit(which, on) {
      const card = document.getElementById(`set-media-${which}`);
      card.querySelector('.lib-edit').hidden = !on;
      card.querySelector('.lib-view-btns').hidden = on;
      if (on) card.querySelector('.lib-edit input').focus();
    }

    async function saveFolder(which) {
      const card = document.getElementById(`set-media-${which}`);
      const value = card.querySelector('.lib-edit input').value;
      const msg = card.querySelector('.lib-msg');
      const body = { [which + '_dir']: value };
      const res = await apiPost('/api/library', body).catch(() => ({ error: 'network' }));
      if (res.error) {
        msg.innerHTML = `<span class="warn">${esc(res.error === 'busy' ? t('lib_err_busy') : String(res.error).startsWith('not_full') ? t('lib_err_notfull', { path: (card.querySelector('.path') || {}).textContent || (MEDIA_BOOT.defaults || {})[which] || '' }) : t('lib_err_notfound'))}</span>`;
        return false;
      }
      await refreshSettings();
      document.querySelector('#set-media .set-media-msg').textContent = t('lib_saved');
      return true;
    }

    function fmtBytes(n) {
      if (n == null) return t('lib_db_none');
      return n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(2)} GB` : `${(n / 1024 ** 2).toFixed(1)} MB`;
    }

    function renderDbCard(lib) {
      const sizes = lib.db_sizes || {};
      const facts = ['subs.db', 'epub.db', 'manga.db'].map(n => `<div>${esc(n)}: ${esc(fmtBytes(sizes[n]))}</div>`).join('');
      document.getElementById('lib-data').innerHTML = `
        <h3>${esc(t('lib_data'))}</h3>
        <span class="path">${esc(lib.data_dir)}</span>
        <div class="facts">${lib.db_is_default ? `<div>${esc(t('lib_db_is_default'))}</div>` : ''}${facts}<div>${esc(t('lib_db_lead'))}</div></div>
        <div class="lib-edit" hidden>
          <input type="text" value="" placeholder="${esc(t('lib_change_hint'))}" spellcheck="false">
          <div class="btns">
            <button class="btn primary" onclick="moveDatabases()">${esc(t('lib_db_move'))}</button>
            <button class="btn" onclick="toggleDbEdit(false)">${esc(t('lib_cancel'))}</button>
          </div>
        </div>
        <div class="btns lib-view-btns">
          ${ON_PHONE ? '' : `<button class="btn" onclick="openFolder('data', this)">${esc(t('lib_open'))}</button>`}
          <button class="btn" onclick="changeDbFolder()">${esc(t('lib_change'))}</button>
          ${lib.db_is_default ? '' : `<button class="btn" onclick="moveDatabases('default')">${esc(t('lib_db_default'))}</button>`}
        </div>
        <div class="lib-open-msg facts" role="status"></div>
        <div class="lib-msg facts" style="margin:0.5em 0 0;"></div>`;
      renderCacheCard(lib.search_cache);
    }

    function renderCacheCard(c, msg) {
      c = c || { entries: 0, bytes: 0, on: false };
      document.getElementById('lib-cache').innerHTML = `
        <h3>${esc(t('lib_cache_title'))}</h3>
        <div class="facts"><div>${esc(t('lib_cache_lead'))}</div>
          <div>${esc(t('lib_cache', { n: fmt(c.entries), size: fmtBytes(c.bytes) }))}</div></div>
        <div class="btns" style="align-items:center;">
          <div class="seg" style="width:12em;">
            <button type="button" class="seg-btn ${c.on ? '' : 'active'}" onclick="setSearchCache(false)">${esc(t('lib_cache_off'))}</button>
            <button type="button" class="seg-btn ${c.on ? 'active' : ''}" onclick="setSearchCache(true)">${esc(t('lib_cache_on'))}</button>
          </div>
          <button class="btn" onclick="clearSearchCache()" ${c.entries || c.bytes ? '' : 'disabled'}>${esc(t('lib_cache_clear'))}</button>
        </div>
        <div class="lib-msg facts" style="margin:0.5em 0 0;">${msg ? esc(msg) : ''}</div>`;
    }

    async function setSearchCache(on) {
      const res = await apiPost('/api/search-cache', { on }).catch(() => ({}));
      if (res.search_cache) renderCacheCard(res.search_cache);
    }

    async function clearSearchCache() {
      document.querySelectorAll('#lib-cache button').forEach(b => b.disabled = true);
      const res = await apiPost('/api/search-cache/clear', {}).catch(() => ({}));
      renderCacheCard(res.search_cache, res.ok ? t('lib_cache_cleared') : '');
    }

    function toggleDbEdit(on) {
      const card = document.getElementById('lib-data');
      card.querySelector('.lib-edit').hidden = !on;
      card.querySelector('.lib-view-btns').hidden = on;
      if (on) card.querySelector('.lib-edit input').focus();
    }

    async function moveDatabases(target) {
      const card = document.getElementById('lib-data');
      const value = target ?? card.querySelector('.lib-edit input').value;
      const msg = card.querySelector('.lib-msg');
      card.querySelectorAll('button').forEach(b => b.disabled = true);
      msg.textContent = t('lib_db_moving');
      const res = await apiPost('/api/library', { db_dir: value }).catch(() => ({ error: 'network' }));
      if (res.error) {
        card.querySelectorAll('button').forEach(b => b.disabled = false);
        const key = { busy: 'lib_db_err_busy', same: 'lib_db_err_same', exists: 'lib_db_err_exists',
                      not_found: 'lib_err_notfound', not_writable: 'lib_db_err_notwritable' }[res.error] || 'lib_db_err_failed';
        msg.innerHTML = `<span class="warn">${esc(t(key, { files: (res.files || []).join(', ') }))}</span>`;
        return;
      }
      let st = {};
      for (;;) {
        await new Promise(r => setTimeout(r, 500));
        st = await fetch('/api/library/move').then(r => r.json()).catch(() => ({ running: true }));
        if (!st.running) break;
        const box = document.getElementById('lib-data');
        const m = box && box.querySelector('.lib-msg');
        if (!m || !st.total || !st.done) continue;
        const left = st.elapsed >= 1 ? st.elapsed * (st.total - st.done) / st.done : null;
        m.textContent = t('lib_db_progress', { done: fmtBytes(st.done), total: fmtBytes(st.total),
                                               eta: left == null ? '' : fmtEta(left) });
      }
      await refreshSettings();
      const done = document.getElementById('lib-data').querySelector('.lib-msg');
      if (st.error) {
        done.innerHTML = `<span class="warn">${esc(t('lib_db_err_failed'))}</span>`;
        return;
      }
      done.innerHTML = st.old_kept && st.old_kept.length
        ? `<span class="warn">${esc(t('lib_db_old_kept', { files: st.old_kept.join(', ') }))}</span>`
        : esc(t('lib_db_moved'));
    }

    function exportFavorites() {
      const doc = { app: 'aobana', kind: 'favorites', version: 1, exported_at: new Date().toISOString(), items: savedSentences };
      const blob = new Blob([JSON.stringify(doc, null, 1)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `aobana-favorites-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      favNote(t('fav_exported', { n: fmt(savedSentences.length) }));
    }

    async function importFavorites(input) {
      const file = input.files && input.files[0];
      input.value = '';
      if (!file) return;
      let items;
      try {
        const doc = JSON.parse(await file.text());
        items = Array.isArray(doc) ? doc : (doc && Array.isArray(doc.items) ? doc.items : null);
      } catch (e) { items = null; }
      if (!items) { favNote(t('fav_bad_file'), true); return; }
      const have = new Set(savedSentences.map(s => s.id));
      let added = 0, same = 0;
      const incoming = [];
      for (const orig of items) {
        const s = cleanFavorite(orig);
        if (!s) continue;
        const id = lineId(s.line);
        if (have.has(id)) { same++; continue; }
        have.add(id);
        if (s.id !== id && s.legacy_id === undefined && typeof s.id === 'string') s.legacy_id = s.id;
        s.id = id;
        incoming.push(s);
        added++;
      }
      if (added) {
        if (store.get('savedSentences_backup_v1') === null) store.set('savedSentences_backup_v1', store.get('savedSentences', '[]'));
        savedSentences = savedSentences.concat(incoming);
        store.set('savedSentences', JSON.stringify(savedSentences));
      }
      favNote(t('fav_imported', { added: fmt(added), same: fmt(same) }));
    }

    let handoffPending = document.querySelector('meta[name="aobana-handoff-pending"]').content === '1';
    function profileSnapshot() {
      const items = {};
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k !== 'aobana_boot' && k !== 'handoff_applied') items[k] = localStorage.getItem(k);
        }
      } catch (e) {}
      return items;
    }
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'hidden' || !handoffPending) return;
      const body = JSON.stringify({ items: profileSnapshot() });
      fetch('/api/profile-handoff', { method: 'POST', keepalive: body.length < 60000, headers: { 'Content-Type': 'application/json', 'X-Aobana': '1' }, body }).catch(() => {});
    });
    function renderPortCard(lib) {
      const running = Number(location.port || 80);
      document.getElementById('port-lead').textContent = t('port_lead', { port: running });
      document.getElementById('port-input').value = lib.port;
      const note = document.getElementById('port-note');
      if (lib.port_env) { note.textContent = t('port_env'); note.hidden = false; }
      else if (lib.port !== running) { note.textContent = t('port_restart', { port: lib.port }); note.hidden = false; }
      else note.hidden = true;
    }

    let workersFacts = null;
    function renderWorkersCard(w) {
      if (!w) return;
      workersFacts = w;
      document.getElementById('workers-lead').textContent = t('workers_lead', { cpus: fmt(w.cpus), rec: fmt(w.recommended) });
      const input = document.getElementById('workers-input');
      input.max = w.max;
      input.value = w.saved || w.effective;
      const off = w.env || !w.parallel;
      document.querySelectorAll('#lib-workers input, #lib-workers button').forEach(el => { el.disabled = off; });
      const note = document.getElementById('workers-note');
      note.className = 'notice';
      if (w.env) { note.textContent = t('workers_env'); note.hidden = false; }
      else if (!w.parallel) { note.textContent = t('workers_single'); note.hidden = false; }
      else if (!w.saved) { note.textContent = t('workers_is_auto'); note.hidden = false; }
      else workersHint();
    }

    function workersHint() {
      const w = workersFacts;
      const note = document.getElementById('workers-note');
      const n = Number(document.getElementById('workers-input').value);
      note.className = 'notice';
      if (w && n > w.recommended) { note.textContent = t('workers_over', { rec: fmt(w.recommended) }); note.hidden = false; }
      else note.hidden = true;
    }

    async function saveWorkers(value) {
      const note = document.getElementById('workers-note');
      const v = value || document.getElementById('workers-input').value.trim();
      const res = await apiPost('/api/library', { index_workers: v }).catch(() => ({ error: 'network' }));
      if (res.error) {
        note.textContent = t('workers_bad', { max: workersFacts ? fmt(workersFacts.max) : '' });
        note.className = 'notice warn'; note.hidden = false; return;
      }
      await refreshSettings();
      if (value !== 'auto') { note.textContent = t('workers_saved'); note.className = 'notice ok'; note.hidden = false; }
    }

    let searchWorkersFacts = null;
    function renderSearchWorkersCard(w) {
      if (!w) return;
      searchWorkersFacts = w;
      document.getElementById('search-workers-lead').textContent = t('search_workers_lead', { cpus: fmt(w.cpus), rec: fmt(w.recommended) });
      const count = document.getElementById('search-workers-input');
      count.max = w.cpus;
      count.value = w.workers;
      document.getElementById('search-delay-input').value = w.delay;
      searchWorkersHint();
    }
    function clampSearchWorkersInputs(final = false) {
      const maxW = searchWorkersFacts ? searchWorkersFacts.cpus : 1;
      const countEl = document.getElementById('search-workers-input');
      const delayEl = document.getElementById('search-delay-input');
      if (countEl) {
        const value = countEl.value.trim();
        if (!value || !Number.isFinite(Number(value))) {
          if (final) countEl.value = String(searchWorkersFacts ? searchWorkersFacts.workers : 1);
          else countEl.value = '';
        } else {
          const n = Math.min(maxW, Math.max(1, Math.trunc(Number(value))));
          countEl.value = String(n);
        }
      }
      if (delayEl) {
        const value = delayEl.value.trim();
        if (!value || !Number.isFinite(Number(value))) {
          if (final) delayEl.value = String(searchWorkersFacts ? searchWorkersFacts.delay : 10);
          else delayEl.value = '';
        } else {
          const n = Math.min(60, Math.max(0, Math.trunc(Number(value))));
          delayEl.value = String(n);
        }
      }
    }
    function searchWorkersHint(final = false) {
      clampSearchWorkersInputs(final);
      const countEl = document.getElementById('search-workers-input');
      document.getElementById('search-delay-input').disabled = countEl.value.trim() === '1';
      const w = searchWorkersFacts;
      const note = document.getElementById('search-workers-note');
      const n = Number(countEl.value);
      note.className = 'notice';
      if (w && n > w.recommended) {
        note.textContent = t('search_workers_over', { rec: fmt(w.recommended) });
        note.hidden = false;
      } else {
        note.hidden = true;
      }
    }
    async function saveSearchWorkers(auto = false) {
      clampSearchWorkersInputs(true);
      searchWorkersHint();
      const note = document.getElementById('search-workers-note');
      const count = document.getElementById('search-workers-input').value.trim();
      const delay = document.getElementById('search-delay-input').value.trim();
      const res = await apiPost('/api/library', { search_workers: auto ? 'auto' : count, search_worker_delay: delay })
        .catch(() => ({ error: 'network' }));
      if (res.error) {
        note.textContent = t('error'); note.className = 'notice warn'; note.hidden = false;
        return;
      }
      await refreshSettings();
      const w = searchWorkersFacts;
      const n = Number(document.getElementById('search-workers-input').value);
      const over = w && n > w.recommended ? ' ' + t('search_workers_over', { rec: fmt(w.recommended) }) : '';
      note.textContent = t('search_workers_saved') + over;
      note.className = 'notice ok';
      note.hidden = false;
    }

    async function savePort() {
      const value = document.getElementById('port-input').value.trim();
      const note = document.getElementById('port-note');
      const res = await apiPost('/api/library', { port: value, profile: profileSnapshot() }).catch(() => ({ error: 'network' }));
      if (res.error) { note.textContent = t('port_bad'); note.className = 'notice warn'; note.hidden = false; return; }
      handoffPending = Number(value) !== Number(location.port || 80);
      note.className = 'notice';
      await refreshSettings();
    }

    function openReset() {
      document.getElementById('reset-body').textContent = t('reset_body', { n: fmt(savedSentences.length) });
      document.getElementById('reset-modal').classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }

    async function closeReset(reset) {
      document.getElementById('reset-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (!reset) return;
      await apiPost('/api/profile-handoff', { drop: true }).catch(() => null);
      try { localStorage.clear(); } catch (e) {}
      store.set('setup_again', '1');
      window.location.href = '/';
    }

    function favNote(text, warn) {
      const el = document.getElementById('fav-note');
      el.textContent = text; el.className = warn ? 'notice warn' : 'notice'; el.hidden = false;
    }

    function pageLabel(r) {
      const label = esc(t('page_n', { n: fmt(r.page) }));
      if (r.media_type !== 'manga' || !r.rowid) return label;
      return `<a class="page-link" href="/manga/page/${Number(r.rowid)}" target="aobana-manga-page" title="${esc(t('page_open'))}">${label}</a>`;
    }

    async function openFolder(which, button) {
      const card = button.closest('.set-media-row, .lib-card');
      const msg = card.querySelector('.lib-open-msg');
      msg.textContent = '';
      const res = await apiPost('/api/library/open', { which }).catch(() => ({ error: 'network' }));
      if (res.error) {
        msg.classList.add('warn');
        msg.textContent = res.error === 'not_found' ? t('lib_err_notfound') : t('lib_error', { e: res.error });
      }
    }

    async function runIndex() {
      const only = libScope();
      if (only === 'manga') {
        document.getElementById('lib-note').hidden = true;
        document.getElementById('lib-estimate').innerHTML = '';
        return startIndex(only);
      }
      if (!MEDIA_BOOT.check_asked) {
        MEDIA_BOOT.check_asked = true;
        apiPost('/api/library/check-asked', {}).catch(() => {});
        let d = null;
        try { d = await fetch('/api/library/analysis').then(r => r.json()); } catch (e) {}
        if (d && !d.report && !(d.status && d.status.running)) {
          document.getElementById('checkfirst-modal').classList.add('open');
          document.documentElement.style.overflow = 'hidden';
          return;
        }
      }
      document.getElementById('lib-note').hidden = true;
      const box = document.getElementById('lib-estimate');
      const btn = document.getElementById('lib-run');
      btn.disabled = true;
      box.innerHTML = `<div class="notice">${esc(t('lib_estimating'))}</div>`;
      const est = await fetch('/api/library/estimate' + (only ? `?only=${only}` : '')).then(r => r.json()).catch(() => null);
      btn.disabled = false;
      const media = (est && est.media) || {};
      const newFiles = Object.entries(media).reduce((a, [k, m]) => a + (MEDIA_ON[k] ? m.new_files || 0 : 0), 0);
      if (!est || est.error || !newFiles) { box.innerHTML = ''; return startIndex(only); }
      box.innerHTML = renderEstimate(est, only);
    }

    let stopKind = null;
    function askStop(kind, outdated) {
      stopKind = kind;
      const m = document.getElementById('stop-modal');
      m.querySelector('h2').textContent = t(kind === 'index' ? 'stop_index_title' : 'stop_check_title');
      m.querySelector('p').textContent = t(kind === 'check' ? 'stop_check_body' : outdated ? 'stop_index_outdated' : 'stop_index_body');
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }
    async function closeStop(stop) {
      document.getElementById('stop-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (!stop || !stopKind) return;
      const res = await apiPost(stopKind === 'index' ? '/api/index/stop' : '/api/library/analyse/stop').catch(() => null);
      if (res && stopKind === 'index') renderIndexStatus(res);
      else if (res) renderAnalysisStatus(res);
    }

    function closeCheckFirst(check) {
      document.getElementById('checkfirst-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (!check) return runIndex();
      document.getElementById('lib-analyse').scrollIntoView({ behavior: 'smooth', block: 'start' });
      runAnalysis();
    }

    function fmtDuration(s) {
      if (s < 60) return t('est_sec');
      const m = Math.round(s / 60);
      return m < 60 ? t('est_min', { n: m }) : t('est_hour', { h: Math.floor(m / 60), m: m % 60 });
    }

    function libScope() {
      const scope = document.getElementById('lib-scope');
      if (!scope.hidden) return scope.value;
      return MEDIAS_ON.length === 1 ? MEDIAS_ON[0] : '';
    }

    function renderEstimate(est, only) {
      let rows = '';
      let short = null;
      for (const k of ['subs', 'epub']) {
        const m = est.media[k];
        if (!m || !MEDIA_ON[k] || (only && k !== only)) continue;
        if (!m.new_files && !m.db_now) continue;
        const name = k === 'subs' ? 'subs.db' : 'epub.db';
        rows += `<div>${esc(t('lib_stage_' + k))}</div><div class="num">${esc(t('est_new', { n: fmt(m.new_files) }))}</div>`;
        rows += `<div></div><div class="num">${esc(t('est_db', { name, now: fmtBytes(m.db_now), after: fmtBytes(m.db_now + m.db_add) }))}</div>`;
        if (m.disk_free != null && m.db_add > m.disk_free) short = m.disk_free;
      }
      rows += `<div></div><div class="num"><b>${esc(t('est_total', { n: fmtBytes(est.total_bytes) }))}</b></div>`;
      rows += `<div></div><div class="num"><b>${esc(t('est_time', { t: fmtDuration(est.seconds), w: est.workers }))}</b></div>`;
      const warn = est.warn ? `<div class="notice warn">${esc(t('est_warn'))}</div>` : '';
      const disk = short != null ? `<div class="notice warn">${esc(t('est_disk', { free: fmtBytes(short) }))}</div>` : '';
      return `<div class="notice ${est.warn ? 'warn' : ''}">
        <b>${esc(t('est_title'))}</b>
        <div class="estimate-grid">${rows}</div>
        ${warn}${disk}
        <div style="color:var(--text-muted); font-size:0.9em;">${esc(t('est_note'))}</div>
        <div class="btns" style="display:flex; gap:0.5em; margin-top:0.6em;">
          <button class="btn primary" onclick="startIndex('${only}')">${esc(t('est_start'))}</button>
          <button class="btn" onclick="document.getElementById('lib-estimate').innerHTML=''">${esc(t('est_cancel'))}</button>
        </div></div>`;
    }

    async function startIndex(only, outdated, tables, allowRemoval) {
      document.getElementById('lib-estimate').innerHTML = '';
      if (tables) {
        tableRunStartedHere = true;
        document.getElementById('lib-optimize').disabled = true;
      } else document.getElementById('lib-outdated').hidden = true;
      const body = only ? { only } : {};
      if (outdated) body.outdated = true;
      if (tables) body.tables = true;
      if (allowRemoval) body.allow_removal = true;
      const res = await apiPost('/api/index', body).catch(() => null);
      if (res && res.nothing) {
        tableRunStartedHere = false;
        const note = document.getElementById('lib-note');
        note.textContent = t('lib_nothing'); note.className = 'notice warn'; note.hidden = false;
        refreshLibrary();
        return;
      }
      if (!res || !res.started) { tableRunStartedHere = false; refreshLibrary(); return; }
      if (res) renderIndexStatus(res);
      startPolling();
      pollActivity();
    }

    let anPoll = null;
    const AN_ORDER = ['bilingual', 'other_language', 'language_review', 'image_only', 'duplicate', 'encoding', 'unreadable'];

    function syncCheckScope() {
      const btn = document.getElementById('an-run');
      if (btn) btn.disabled = libScope() === 'manga';
    }

    async function runAnalysis() {
      if (libScope() === 'manga') return;
      const only = libScope();
      const res = await apiPost('/api/library/analyse', only ? { only } : {}).catch(() => null);
      if (res) renderAnalysisStatus(res);
      pollAnalysis();
      pollActivity();
    }

    function pollAnalysis() {
      if (anPoll) return;
      anPoll = setInterval(async () => {
        let d;
        try { d = await fetch('/api/library/analysis').then(r => r.json()); } catch (e) { return; }
        renderAnalysisStatus(d.status);
        if (!d.status.running) { clearInterval(anPoll); anPoll = null; renderAnalysis(d); pollActivity(); }
      }, 700);
    }

    async function loadAnalysis() {
      let d;
      try { d = await fetch('/api/library/analysis').then(r => r.json()); } catch (e) { return; }
      renderAnalysisStatus(d.status);
      if (d.status.running) pollAnalysis(); else renderAnalysis(d);
    }

    function renderAnalysisStatus(s) {
      const btn = document.getElementById('an-run');
      const box = document.getElementById('an-status');
      s = s || {};
      btn.disabled = !!s.running || libScope() === 'manga';
      btn.querySelector('span').textContent = s.running ? t('an_running') : t('an_run');
      if (s.running) {
        const pct = s.total ? Math.round(100 * s.done / s.total) : 0;
        box.innerHTML = `<div class="progress"><div style="width:${pct}%"></div></div>
          <div class="progress-text">${esc(t('an_stage_' + s.stage))} — ${fmt(s.done)} / ${fmt(s.total)} ${s.current ? '· ' + esc(s.current) : ''}</div>
          <div class="btns"><button class="btn" onclick="askStop('check')" ${s.stopping ? 'disabled' : ''}>${esc(t(s.stopping ? 'stopping' : 'stop_btn'))}</button></div>`;
      } else {
        box.innerHTML = s.error ? `<div class="notice err">${esc(t('lib_error', { e: s.error }))}</div>`
          : s.stopped ? `<div class="notice warn">${esc(t('an_stopped'))}</div>` : '';
      }
    }

    function anWhy(it) {
      if (it.reason === 'duplicate_kept') return t('an_kept');
      if (it.reason === 'duplicate') {
        const keep = it.keep.split(/[\\/]/).pop();
        if (it.how === 'subplz') return t('an_why_subplz', { keep });
        return it.how === 'same_bytes' ? t('an_why_bytes', { keep }) : t('an_why_dup', { keep, pct: Math.round(100 * it.share) });
      }
      if (it.reason === 'unreadable') return it.error || '';
      if (it.reason === 'image_only') return t('an_why_image_only');
      return t('an_why_lang', { lines: fmt(it.lines), ja: fmt(it.ja), zh: fmt(it.zh), en: fmt(it.en) });
    }

    const AN_PAGE = 200;
    const AN_FILTERABLE = ['bilingual', 'other_language', 'language_review', 'image_only', 'duplicate', 'duplicate_kept'];
    let anItems = [];
    let anSections = [];
    let anPicked = new Set();
    let anUnpicked = new Set();

    function anRow(it) {
      const label = it.media === 'epub' && it.title ? `${it.title}${it.author ? ' / ' + it.author : ''} — ${it.path}` : it.path;
      const box = AN_FILTERABLE.includes(it.reason)
        ? `<input type="checkbox" class="an-pick" value="${it.id}" ${anPicked.has(Number(it.id)) ? 'checked' : ''} ${it.filtered ? 'disabled' : ''}>`
        : '<span></span>';
      return `<label class="an-row ${it.reason === 'duplicate_kept' ? 'kept' : ''} ${it.filtered ? 'filtered' : ''}">${box}
        <span class="name">${esc(label)}</span><span class="why">${esc(anWhy(it))}</span></label>`;
    }

    function anFilteredRow(i) {
      const f = anFiltered[i];
      return `<label class="an-row"><input type="checkbox" class="an-unpick" value="${i}" ${anUnpicked.has(i) ? 'checked' : ''}>
        <span class="name">${esc(t('an_stage_' + f.media))} · ${esc(f.name)}${f.exists ? '' : ' ' + esc(t('an_missing'))}</span>
        <span class="why">${esc(t('an_reason_' + f.reason))}${f.keep ? ' · ' + esc(t('an_kept_is', { keep: f.keep.split(/[\\/]/).pop() })) : ''}</span></label>`;
    }

    function anSection(units, draw, size, summary, bar = '') {
      const idx = anSections.push({ units, draw, size, shown: 0, left: units.reduce((n, u) => n + size(u), 0) }) - 1;
      return `<details class="an-section" data-an="${idx}"><summary>${summary}</summary>${bar}<div class="an-list"></div></details>`;
    }

    function anDrawMore(details) {
      const sec = anSections[Number(details.dataset.an)];
      const list = details.querySelector('.an-list');
      if (!sec || !list || sec.shown >= sec.units.length) return;
      let html = '', rows = 0;
      while (sec.shown < sec.units.length && rows < AN_PAGE) {
        const u = sec.units[sec.shown++];
        html += sec.draw(u);
        rows += Array.isArray(u) ? u.length : 1;
        sec.left -= sec.size(u);
      }
      list.querySelector('.an-more')?.remove();
      list.insertAdjacentHTML('beforeend', html
        + (sec.shown < sec.units.length ? `<div class="an-more sidebar-more">${esc(t('sidebar_more', { n: fmt(sec.left) }))}</div>` : ''));
    }

    function wireAnalysis(box) {
      if (box.dataset.wired) return;
      box.dataset.wired = '1';
      box.addEventListener('toggle', e => {
        const d = e.target;
        if (d.matches('details.an-section[data-an]') && d.open && !d.querySelector('.an-list').children.length) anDrawMore(d);
      }, true);
      box.addEventListener('scroll', e => {
        const s = e.target;
        if (s.classList && s.classList.contains('an-list') && s.scrollTop + s.clientHeight > s.scrollHeight - 400) anDrawMore(s.closest('details'));
      }, { capture: true, passive: true });
      box.addEventListener('click', e => {
        const more = e.target.closest('.an-more');
        if (more) anDrawMore(more.closest('details'));
      });
      box.addEventListener('change', e => {
        const cb = e.target;
        if (cb.classList.contains('an-pick')) (cb.checked ? anPicked.add(Number(cb.value)) : anPicked.delete(Number(cb.value)));
        else if (cb.classList.contains('an-unpick')) (cb.checked ? anUnpicked.add(Number(cb.value)) : anUnpicked.delete(Number(cb.value)));
        else return;
        anSelectLabel(cb.closest('details.an-section'));
      });
    }

    function renderFiltered(list) {
      if (!list || !list.length) return '';
      const bar = `<div class="btns" style="margin:0.3em 0 0.5em;"><button type="button" class="btn an-all" data-filtered="1" onclick="selectAllSection(this)">${esc(t('an_select_all'))}</button></div>`;
      let html = `<div class="facts" style="margin-top:1.2em; margin-bottom:0.2em;">${esc(t('an_filtered_title'))} (${fmt(list.length)})</div>`;
      for (const media of ['subs', 'epub']) {
        const reasons = [...AN_ORDER, ...new Set(list.filter(f => f.media === media && !AN_ORDER.includes(f.reason)).map(f => f.reason))];
        for (const reason of reasons) {
          const units = [];
          list.forEach((f, i) => { if (f.media === media && f.reason === reason) units.push(i); });
          if (!units.length) continue;
          const summary = `${esc(t('an_stage_' + media))} · ${esc(t('an_reason_' + reason))} (${fmt(units.length)})`;
          html += anSection(units, anFilteredRow, () => 1, summary, bar);
        }
      }
      return html + `<div class="btns an-after"><button class="btn" onclick="unfilterPicked()">${esc(t('an_unfilter'))}</button></div>`;
    }

    let anFiltered = [];

    function renderAnalysis(d) {
      const box = document.getElementById('an-report');
      wireAnalysis(box);
      const r = d && d.report;
      anSections = [];
      anUnpicked = new Set();
      anFiltered = (d && d.filtered) || [];
      const filteredSet = new Set(anFiltered.map(f => `${f.media}\t${f.name}`));
      anItems = ((r && r.items) || []).map(it => filteredSet.has(`${it.media}\t${it.name}`) ? { ...it, filtered: true } : it);
      anPicked = new Set(anItems.filter(it => AN_FILTERABLE.includes(it.reason)
        && it.reason !== 'duplicate_kept' && it.reason !== 'language_review' && !it.filtered).map(it => Number(it.id)));
      const filtered = renderFiltered(anFiltered);
      if (!r) { box.innerHTML = filtered + '<div id="an-move-msg"></div>'; anSelectLabels(box); return; }
      let html = '';
      let files = 0;
      for (const media of ['subs', 'epub']) {
        const sm = r.summary[media];
        if (!sm) continue;
        files += sm.files || 0;
        const items = anItems.filter(i => i.media === media);
        for (const reason of AN_ORDER) {
          let list = items.filter(i => i.reason === reason);
          if (!list.length) continue;
          const summary = `${esc(t('an_stage_' + media))} · ${esc(t('an_reason_' + reason))} (${fmt(list.length)})`;
          if (reason === 'duplicate') {
            const groups = {};
            items.filter(i => i.reason === 'duplicate' || i.reason === 'duplicate_kept')
              .forEach(i => (groups[i.keep] = groups[i.keep] || []).push(i));
            const units = Object.values(groups).map(g => g.sort((a, b) => (a.reason === 'duplicate_kept' ? -1 : 0) - (b.reason === 'duplicate_kept' ? -1 : 0)));
            const bar = `<div class="btns" style="margin:0.3em 0 0.5em;"><button type="button" class="btn an-all" onclick="selectAllSection(this)">${esc(t('an_select_all'))}</button><button type="button" class="btn" onclick="invertDuplicates(this)">${esc(t('an_invert'))}</button></div>`;
            html += anSection(units, g => `<div class="an-group">${g.map(anRow).join('')}</div>`,
              g => g.filter(i => i.reason === 'duplicate').length, summary, bar);
          } else {
            const bar = AN_FILTERABLE.includes(reason)
              ? `<div class="btns" style="margin:0.3em 0 0.5em;"><button type="button" class="btn an-all" onclick="selectAllSection(this)">${esc(t('an_select_all'))}</button></div>`
              : '';
            html += anSection(list, anRow, () => 1, summary, bar);
          }
        }
      }
      const head = `<div class="facts" style="margin-top:0.8em;">${esc(t('an_summary', { files: fmt(files), when: r.generated_at }))}</div>`;
      const found = html
        ? html + `<div class="btns" style="margin-top:0.8em;">
            <button class="btn primary" onclick="filterFlagged()">${esc(t('an_filter'))}</button></div>`
        : `<div class="notice ok">${esc(t('an_none'))}</div>`;
      box.innerHTML = head + found + filtered + '<div id="an-move-msg"></div>';
      anSelectLabels(box);
    }

    function anSectionPicks(details) {
      const sec = details && anSections[Number(details.dataset.an)];
      if (!sec) return null;
      if (details.querySelector('.an-all[data-filtered]')) return { ids: sec.units.map(Number), set: anUnpicked };
      const ids = sec.units.flat().filter(it => it && !it.filtered && it.reason !== 'duplicate_kept').map(it => Number(it.id));
      return { ids, set: anPicked };
    }

    function anAllTicked(p) {
      return p.ids.length > 0 && p.ids.every(id => p.set.has(id));
    }

    function anSelectLabel(details) {
      const btn = details && details.querySelector('.an-all');
      const p = btn && anSectionPicks(details);
      if (p) btn.textContent = t(anAllTicked(p) ? 'an_deselect_all' : 'an_select_all');
    }

    function anSelectLabels(box) {
      box.querySelectorAll('details.an-section').forEach(anSelectLabel);
    }

    function anSyncBoxes(details) {
      details.querySelectorAll('.an-pick').forEach(cb => { cb.checked = anPicked.has(Number(cb.value)); });
      details.querySelectorAll('.an-unpick').forEach(cb => { cb.checked = anUnpicked.has(Number(cb.value)); });
    }

    function selectAllSection(btn) {
      const details = btn.closest('.an-section');
      const p = anSectionPicks(details);
      if (!p) return;
      const untick = anAllTicked(p);
      p.ids.forEach(id => (untick ? p.set.delete(id) : p.set.add(id)));
      anSyncBoxes(details);
      anSelectLabel(details);
    }

    function invertDuplicates(btn) {
      const details = btn.closest('.an-section');
      const sec = details && anSections[Number(details.dataset.an)];
      if (!sec) return;
      sec.units.flat().filter(it => !it.filtered).forEach(it => {
        const id = Number(it.id);
        anPicked.has(id) ? anPicked.delete(id) : anPicked.add(id);
      });
      details.querySelectorAll('.an-pick').forEach(cb => { cb.checked = anPicked.has(Number(cb.value)); });
      anSelectLabel(details);
    }

    function anMessage(html) {
      const el = document.getElementById('an-move-msg');
      if (el) el.innerHTML = html;
    }

    async function filterFlagged() {
      const ids = anItems.filter(it => !it.filtered && anPicked.has(Number(it.id))).map(it => Number(it.id));
      if (!ids.length) return;
      const res = await apiPost('/api/library/filter', { ids }).catch(() => ({ error: 'network' }));
      if (res.error) {
        anMessage(`<div class="notice warn">${esc(res.error === 'busy' ? t('an_err_busy') : t('lib_error', { e: res.error }))}</div>`);
        return;
      }
      await loadAnalysis();
      await refreshLibrary();
      anMessage(`<div class="notice ok">${esc(t('an_filtered_done', { n: fmt(res.filtered.length) }))}</div>`
        + (res.refused.length ? `<div class="notice warn">${esc(t('an_filter_failed'))}<ul>${capList(res.refused)}</ul></div>` : ''));
    }

    async function unfilterPicked() {
      const entries = [...anUnpicked]
        .map(i => anFiltered[i]).filter(Boolean).map(f => ({ media: f.media, name: f.name }));
      if (!entries.length) return;
      const res = await apiPost('/api/library/unfilter', { entries }).catch(() => ({ error: 'network' }));
      if (res.error) {
        anMessage(`<div class="notice warn">${esc(res.error === 'busy' ? t('an_err_busy') : t('lib_error', { e: res.error }))}</div>`);
        return;
      }
      await loadAnalysis();
      await refreshLibrary();
      anMessage(`<div class="notice ok">${esc(t('an_unfiltered', { n: fmt(res.unfiltered) }))}</div>`);
    }

    
function startPolling() {
      if (libPoll) return;
      libWasRunning = true;
      libPoll = setInterval(async () => {
        let s;
        try { s = await fetch('/api/index/status').then(r => r.json()); } catch (e) { return; }
        renderIndexStatus(s);
        if (!s.running) {
          clearInterval(libPoll); libPoll = null;
          pollActivity();
          refreshLibrary();
          loadAnalysis();
        }
      }, 500);
    }

    function renderIndexStatus(s) {
      const btn = document.getElementById('lib-run');
      const box = document.getElementById('lib-status');
      s = s || {};
      if (tableRunStartedHere && s.started_at && !s.running) {
        optimizeDoneThisVisit = !!(s.tables && !s.error && !s.stopped);
        tableRunStartedHere = false;
        if (libLast) renderOutdated(libLast);
      }
      btn.disabled = !!s.running;
      btn.querySelector('span').textContent = s.running ? t('lib_running') : t('lib_run');
      if (!s.started_at) {
        const u = s.unfinished;
        box.innerHTML = u ? `<div class="notice warn">${esc(t(u.outdated ? 'lib_unfinished_outdated' : 'lib_unfinished'))}</div>` : '';
        return;
      }
      let html = '';
      if (s.running) {
        const pct = s.total ? Math.round(100 * s.done / s.total) : 0;
        html += `<div class="progress"><div style="width:${pct}%"></div></div>
          <div class="progress-text">${esc(t('lib_stage_' + s.stage))} — ${s.phase
            ? esc(t('lib_phase_' + s.phase)) + (s.total ? ` ${fmt(s.done)} / ${fmt(s.total)}` : '')
            : `${fmt(s.done)} / ${fmt(s.total)} ${s.current ? '· ' + esc(s.current) : ''}`}</div>
          <div class="btns"><button class="btn" onclick="askStop('index', ${s.outdated ? 'true' : 'false'})" ${s.stopping ? 'disabled' : ''}>${esc(t(s.stopping ? 'stopping' : 'stop_btn'))}</button></div>`;
      } else {
        const results = s.results || {};
        if (s.error) html += `<div class="notice err">${esc(t('lib_error', { e: s.error }))}</div>`;
        else if (s.stopped) html += `<div class="notice warn">${esc(t('lib_stopped'))}</div>`;
        else if (s.tables) html += `<div class="notice ok">${esc(t('lib_tables_ready'))}</div>`;
        else html += `<div class="notice ok">${esc(t('lib_done'))} <a href="/">${esc(t('lib_done_search'))} →</a></div>`;
        const stages = ['subs', 'epub', 'manga'].filter(k => results[k]);
        if (stages.length) {
          html += `<table class="summary-table"><tr><th></th><th>${esc(t('lib_col_new'))}</th><th>${esc(t('lib_col_same'))}</th><th>${esc(t('lib_col_removed'))}</th></tr>`;
          stages.forEach(k => {
            const r = results[k];
            html += `<tr><td>${esc(t('lib_stage_' + k))}</td><td>${fmt(r.indexed)}</td><td>${fmt(r.unchanged)}</td><td>${fmt(r.removed)}</td></tr>`;
          });
          html += '</table>';
        }
      }
      (s.root_not_set || []).forEach(st => {
        html += `<div class="notice">${esc(t('lib_root_not_set', { s: t('lib_stage_' + st) }))}</div>`;
      });
      (s.root_missing || []).forEach(st => {
        html += `<div class="notice warn">${esc(t('lib_root_missing', { s: t('lib_stage_' + st) }))}</div>`;
      });
      const held = Object.keys(s.removal_held || {}).filter(st => ['subs', 'epub', 'manga'].includes(st));
      if (!s.running && held.length) {
        held.forEach(st => {
          const h = s.removal_held[st];
          html += `<div class="notice warn">${esc(t('lib_removal_held', { s: t('lib_stage_' + st), gone: fmt(h.gone), indexed: fmt(h.indexed) }))}</div>`;
        });
        const only = '[' + held.map(st => `'${st}'`).join(',') + ']';
        html += `<div class="btns"><button class="btn" onclick="startIndex(${only}, false, false, true)">${esc(t('lib_remove_anyway'))}</button></div>`;
      }
      if ((s.skipped_clash || []).length) {
        html += `<div class="notice warn">${esc(t('lib_skipped_clash'))}<ul>${capList(s.skipped_clash)}</ul></div>`;
      }
      if ((s.failed || []).length) {
        html += `<div class="notice err">${esc(t('lib_failed'))}<ul>${capList(s.failed)}</ul></div>`;
      }
      if ((s.log || []).length) {
        const open = document.querySelector('#lib-status details.log[open]') ? 'open' : '';
        html += `<details class="log" ${open}><summary>${esc(t('lib_log'))}</summary><pre>${esc(s.log.join('\n'))}</pre></details>`;
      }
      box.innerHTML = html;
    }

    const GUIDE = {
      ja: `
        <h1>ガイド</h1>
        <p class="lead">露草（あおばな）の使い方。</p>

        <h2>露草とは</h2>
        <p>自分の持っている字幕ファイル・電子書籍・漫画から、日本語の例文を検索するアプリです。すべてこのパソコンの中で動き、インターネットには何も送りません（起動時に、新しいバージョンがあるかを GitHub に確認するだけです）。検索は語の活用形や読みにも対応していて、例文はふりがな付きで表示されます。</p>

        <h2>1. ファイルを入れる</h2>
        <p>読み込まれるのは <code>.srt</code>・<code>.ass</code>・<code>.ssa</code>（字幕）、<code>.epub</code>（電子書籍）、<code>.mokuro</code>（漫画）だけです。<code>.pdf</code>、<code>.txt</code> などは無視されます。<code>.ass</code> は日本語の台詞だけを読み込みます（中国語・英語の行、看板、ルビ用の小さな行、図形は除きます）。フォルダの場所は<a href="/?tab=settings">設定</a>タブで確認・変更できます。使わないメディアはそこでオフにできます。</p>
        <pre>字幕フォルダ/
├─ 作品A/
│   ├─ 作品A S01E01.srt
│   └─ 作品A S01E02.srt
└─ 作品B/
    └─ 第1期/                  ← 作品フォルダの中なら、さらに分けてもOK
        └─ 作品B 第01話.srt

書籍フォルダ/
├─ [著者] 書名.epub
└─ 好きなサブフォルダ/
    └─ [著者] 書名.epub

漫画フォルダ/
└─ シリーズA/
    ├─ シリーズA 01.mokuro
    └─ シリーズA 02.mokuro</pre>
        <ul>
          <li><b>字幕は作品ごとにフォルダを作ってください。</b>一番上のフォルダ名が作品名になります。字幕フォルダの直下に置いた字幕ファイルは、ファイル名を作品名とする1つの作品として読み込まれます。</li>
          <li>話数はファイル名の <code>S01E02</code>、<code>第2話</code>、<code>- 02</code> などから読み取ります。</li>
          <li>書籍の題名と著者は EPUB のメタデータから取ります。メタデータがない場合は、ファイル名 <code>[著者] 書名.epub</code> から取ります。</li>
          <li><b>漫画はシリーズごとにフォルダを作ってください。</b>フォルダ名がシリーズ名、ファイル名が巻の名前になります。<code>.mokuro</code> は <a href="https://github.com/kha-white/mokuro" target="_blank" rel="noopener">mokuro</a> が漫画の画像を OCR して書き出すファイルです。Aobana はその文字だけを読むので、画像はなくても構いません。文字は mokuro が読み取ったままなので、読み間違いや読み落としはそのまま表示されます。</li>
        </ul>

        <h2>2. インデックスを作成する</h2>
        <p><a href="/?tab=library">ライブラリ</a>タブで「インデックス作成」を押すと、すべての文を解析して検索用のデータベースを作ります。初回は大きなライブラリで数分かかります。2回目以降は追加・変更・削除されたファイルだけを処理します。ファイルを入れ替えたら、もう一度押してください。</p>
        <p>ボタンの横で、1つのメディアだけを選べます。字幕か書籍が増えるときは、作成前にデータベースの大きさと所要時間の見積もりが出ます（漫画は見積もりなしですぐに始まります）。データベースの合計が 10 GB を超えそうなときは、検索が遅くなるため、始める前に確認が表示されます。同じタブの「点検する」では、字幕と書籍から日本語以外のファイルや重複ファイルを探し、選んだものをインデックスから外せます（ファイルは移動も削除もしません）。二か国語の字幕は日本語の部分だけがインデックスされます。</p>

        <h2>3. 検索する</h2>
        <ul>
          <li><b>語形はまとめて検索されます。</b><code>食べる</code> で「食べた」「食べて」なども見つかります。ひらがなの <code>たべる</code> でも検索できます。</li>
          <li><b>完全一致</b> — 入力した形そのままで探します。<code>"食べて"</code> のように <code>"</code> で囲んでも同じです。</li>
          <li><b>除外</b> — 頭に <code>-</code> を付けた語を含む文は除かれます（例: <code>食べる -肉</code>）。</li>
          <li><b>並べ替え</b> — おすすめ（読みやすい長さ順）、時系列順、長い順、短い順、ランダム。選んだ並べ替えは次回も使われます。</li>
          <li><b>全て / 字幕 / 書籍 / 漫画</b> — サイドバーの上のボタンで、検索対象を切り替えます。これも記憶されます。オンのメディアが2つのときは「両方」と表示されます。</li>
          <li><b>作品で絞り込む</b> — サイドバーの作品名を押すと、その作品の中だけを検索します。いくつでも選べ、もう一度押すと外れます。</li>
        </ul>

        <h2>例文の操作</h2>
        <ul>
          <li><b>★</b> お気に入りに保存します。<a href="/?tab=saved">お気に入り</a>タブで見られます（このブラウザに保存されます）。</li>
          <li><b>⋯</b> 前後の文脈を表示します。</li>
          <li><b>ふ</b> ふりがなの表示・非表示を切り替えます。</li>
        </ul>

        <h2>メディア</h2>
        <p><a href="/?tab=media">メディア</a>タブには、インデックス済みのすべての作品・書籍・漫画が一覧で表示されます。作品を開くと、各話・各章・各巻を最初から順に読めます。漫画の文にはページ番号が付きます。</p>

        <h2>ショートカット</h2>
        <p><span class="kbd-key">Q</span> 検索バー · <span class="kbd-key">D</span>/<span class="kbd-key">↓</span> 次へ · <span class="kbd-key">A</span>/<span class="kbd-key">↑</span> 前へ · <span class="kbd-key">C</span> 文脈 · <span class="kbd-key">S</span> お気に入り · <span class="kbd-key">F</span> ふりがな · <span class="kbd-key">?</span> ヘルプ · <span class="kbd-key">Esc</span> 閉じる</p>

        <h2>Anki アドオン: Aobana Reibun</h2>
        <!--reibun-->
        <p>Aobana Reibun（例文）は、Anki のカードに日本語の例文を入れるアドオンです。Aobana を使うと、手持ちの字幕・書籍・漫画から例文を選び、ふりがな、作品名、前後の文脈を、漫画ならそのページの画像も一緒に入れます。Aobana が動いていなければアドオンが起動し、終わったら止めます。</p>
        <ul>
          <li><b>まとめて入れる</b> — Anki の「Tools → Aobana Reibun → Run」でデッキ全体に、ブラウザでは選んだノートに入れます。フィールドが埋まっているときは、スキップ・置き換え・追加から選べます。</li>
          <li><b>復習中に1枚ずつ</b> — <span class="kbd-key">Ctrl+Shift+W</span> を押すと、今のカードに Aobana の例文が入ります。</li>
          <li><b>ほかの2つのソース</b> — Nadeshiko（API キーが必要）と Immersion Kit（キー不要）の例文も、スクリーンショットと音声つきで入れられます（<span class="kbd-key">Ctrl+Shift+O</span>・<span class="kbd-key">Ctrl+Shift+K</span>）。</li>
        </ul>
        <p>Anki の「ツール → アドオン」で「アドオンを入手...」を押し、上のコードを入力するとインストールできます。AnkiAutoImage をもとに作られました。</p>

        <h2>表示と設定</h2>
        <p>右上のボタンでショートカット一覧（?）、言語（日本語 / English）、テーマ（紙・霞・夜・深夜）を切り替えられます。</p>

        <h2>アプリの終了</h2>
        <p>露草は小さなウィンドウ（「露草 / Aobana」）で動いています。そのウィンドウを閉じると終了します。ブラウザのタブを閉じるだけでは終了しません。</p>
      `,
      en: `
        <h1>Guide</h1>
        <p class="lead">How to use Aobana (露草).</p>

        <h2>What Aobana is</h2>
        <p>An app for searching Japanese example sentences in the subtitle files, e-books and manga you own. Everything runs on this computer, and nothing is sent to the internet (at start it only asks GitHub whether a newer version exists). Searches understand conjugations and readings, and sentences are shown with furigana.</p>

        <h2>1. Add your files</h2>
        <p>Only <code>.srt</code>, <code>.ass</code> and <code>.ssa</code> (subtitles), <code>.epub</code> (e-books) and <code>.mokuro</code> (manga) are read. <code>.pdf</code>, <code>.txt</code> and everything else are ignored. From an <code>.ass</code>, only the Japanese dialogue is read: Chinese and English lines, signs, the small furigana lines and drawings are left out. The <a href="/?tab=settings">Settings</a> tab shows where the folders are and lets you change them, or turn off a media you don't use.</p>
        <pre>Subtitles folder/
├─ Show A/
│   ├─ Show A S01E01.srt
│   └─ Show A S01E02.srt
└─ Show B/
    └─ Season 1/                ← sub-folders inside a show folder are fine
        └─ Show B 第01話.srt

Books folder/
├─ [Author] Title.epub
└─ any sub-folder/
    └─ [Author] Title.epub

Manga folder/
└─ Series A/
    ├─ Series A 01.mokuro
    └─ Series A 02.mokuro</pre>
        <ul>
          <li><b>Give each show its own folder.</b> The top folder's name becomes the show's name. A subtitle file placed directly in the subtitles folder is read as a show of its own, named after the file.</li>
          <li>Episode numbers are read from file names such as <code>S01E02</code>, <code>第2話</code> or <code>- 02</code>.</li>
          <li>A book's title and author come from the EPUB's metadata, or, when that is missing, from the file name <code>[Author] Title.epub</code>.</li>
          <li><b>Give each manga series its own folder.</b> The folder's name becomes the series' name, and each file's name its volume's. A <code>.mokuro</code> file is what <a href="https://github.com/kha-white/mokuro" target="_blank" rel="noopener">mokuro</a> writes when it runs OCR on manga pages. Aobana reads only its text, so the images are not needed. The text is shown as mokuro read it, misread or missed words included.</li>
        </ul>

        <h2>2. Build the index</h2>
        <p>Press "Index library" in the <a href="/?tab=library">Library</a> tab. Every sentence is analyzed into a search database; the first run over a large library takes a few minutes. Later runs only process files that were added, changed or removed, so run it again whenever your files change.</p>
        <p>Beside the button you can choose one media only. When subtitles or books were added, you first see how large the databases will get and how long it will take (manga starts at once, with no estimate); past 10 GB in total, Aobana asks before it starts, as searches get slower. "Check" in the same tab finds subtitles and books that are not Japanese, and duplicates, and leaves the ones you tick out of the index (nothing is moved or deleted). Bilingual subtitles are indexed with their Japanese part only.</p>

        <h2>3. Search</h2>
        <ul>
          <li><b>Every conjugated form is found.</b> <code>食べる</code> also finds 食べた, 食べて and so on, and the reading <code>たべる</code> works too.</li>
          <li><b>Exact</b> matches exactly what you typed. Wrapping the query in quotes (<code>"食べて"</code>) does the same.</li>
          <li><b>Exclude</b> sentences containing a word by putting <code>-</code> in front of it (<code>食べる -肉</code>).</li>
          <li><b>Sort</b>: recommended (easy-to-read lengths first), chronological, longest, shortest, random. Your choice is remembered.</li>
          <li><b>All / Subs / Books / Manga</b>: the buttons at the top of the sidebar choose what to search. Also remembered.</li>
          <li><b>Filter by title</b>: click a title in the sidebar to search inside it only. You can pick several; click one again to remove it.</li>
        </ul>

        <h2>Sentence buttons</h2>
        <ul>
          <li><b>★</b> saves it to the <a href="/?tab=saved">Favorites</a> tab (stored in this browser).</li>
          <li><b>⋯</b> shows the surrounding context.</li>
          <li><b>ふ</b> shows or hides furigana.</li>
        </ul>

        <h2>Media</h2>
        <p>The <a href="/?tab=media">Media</a> tab lists every indexed show, book and manga series. Open one to read its episodes, chapters or volumes in order; manga lines carry their page number.</p>

        <h2>Keyboard shortcuts</h2>
        <p><span class="kbd-key">Q</span> search bar · <span class="kbd-key">D</span>/<span class="kbd-key">↓</span> next · <span class="kbd-key">A</span>/<span class="kbd-key">↑</span> previous · <span class="kbd-key">C</span> context · <span class="kbd-key">S</span> favorite · <span class="kbd-key">F</span> furigana · <span class="kbd-key">?</span> help · <span class="kbd-key">Esc</span> close</p>

        <h2>Anki add-on: Aobana Reibun</h2>
        <!--reibun-->
        <p>Aobana Reibun (例文, "example sentences") is an Anki add-on that fills your cards with Japanese example sentences. With Aobana, it picks a sentence from your own subtitles, books and manga, with its furigana, the title it comes from, the lines around it, and for manga the page's image. If Aobana is not running, the add-on starts it and stops it when done.</p>
        <ul>
          <li><b>A whole deck at once</b>: "Tools → Aobana Reibun → Run" fills a deck, and the Browser fills the notes you select. When a field is already filled, you choose to skip it, replace it or add to it.</li>
          <li><b>One card while reviewing</b>: <span class="kbd-key">Ctrl+Shift+W</span> puts an Aobana sentence on the current card.</li>
          <li><b>Two more sources</b>: Nadeshiko (needs an API key) and Immersion Kit (no key) add sentences with a screenshot and audio (<span class="kbd-key">Ctrl+Shift+O</span>, <span class="kbd-key">Ctrl+Shift+K</span>).</li>
        </ul>
        <p>To install it, open "Tools → Add-ons" in Anki, press "Get Add-ons..." and enter the code above. It is based on AnkiAutoImage.</p>

        <h2>Appearance and settings</h2>
        <p>The buttons at the top right show keyboard shortcuts (?), and switch language (日本語 / English) and theme (Paper, Haze, Night, Midnight).</p>

        <h2>Quitting</h2>
        <p>Aobana runs in a small window titled "露草 / Aobana". Close that window to quit; closing the browser tab alone does not stop it.</p>
      `,
    };
    const REIBUN_CODE = '1429349152';
    function reibunTop() {
      if (!REIBUN_CODE) return `<div class="guide-top"><span class="guide-version">Aobana Reibun</span></div>`;
      const code = esc(REIBUN_CODE);
      return `<div class="guide-top"><span class="guide-version">Aobana Reibun</span>` +
        `<code id="reibun-code">${code}</code>` +
        `<button class="btn" onclick="copyReibunCode(this)">${esc(t('reibun_copy'))}</button>` +
        `<a class="btn" href="https://ankiweb.net/shared/info/${code}" target="_blank" rel="noopener">AnkiWeb</a></div>`;
    }
    async function copyReibunCode(btn) {
      try { await navigator.clipboard.writeText(REIBUN_CODE); }
      catch (e) {
        const r = document.createRange(); r.selectNodeContents(document.getElementById('reibun-code'));
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e2) {}
        if (!ok) return;
      }
      btn.textContent = t('update_copied');
    }
    function initGuideTab() {
      setTitle(t('tab_guide'));
      document.getElementById('guide-body').innerHTML =
        `<div class="guide-top"><span class="guide-version">Aobana ${esc(APP_VERSION)}</span>` +
        `<button class="btn" onclick="openChangelog()">${esc(t('changelog'))}</button>` +
        `<button class="btn" onclick="openWelcome()">${esc(t('welcome_again'))}</button></div>` +
        GUIDE[LANG].replace('<!--reibun-->', reibunTop());
    }

    let activityTimer = null;
    let activityPolling = false;
    let activityAgain = false;
    let activityBusy = false;
    const ACTIVITY_WAKE_KEY = 'aobana_activity_wake';
    function wakeOtherTabs() {
      try { localStorage.setItem(ACTIVITY_WAKE_KEY, `${Date.now()}:${Math.random()}`); } catch (e) {}
    }
    async function pollActivity() {
      if (activityPolling) { activityAgain = true; return; }
      activityPolling = true;
      clearTimeout(activityTimer);
      let a = null;
      try { a = await fetch('/api/activity').then(r => r.json()); } catch (e) {}
      if (a) renderNotices(a.notices || []);
      if (a) {
        const wasBusy = activityBusy;
        activityBusy = !!(a.index || a.check || a.figures);
        if (activityBusy && !wasBusy) wakeOtherTabs();
      }
      activityPolling = false;
      if (activityBusy || activityAgain) activityTimer = setTimeout(pollActivity, 1000);
      activityAgain = false;
    }
    function noticeText(n) {
      const state = n.error ? '_error' : (n.stopped ? '_stopped' : '');
      return t(`notice_${n.kind}${n.kind === 'figures' ? '' : state}`, { time: fmtDuration(n.seconds) });
    }
    function renderNotices(list) {
      const box = document.getElementById('task-notices');
      box.innerHTML = list.map(n => `<div class="task-notice${n.error ? ' warn' : ''}" role="status">
          <span>${esc(noticeText(n))}</span>
          <button class="btn" type="button" onclick="dismissNotice(${Number(n.id)}, this)">${esc(t('close'))}</button>
        </div>`).join('');
    }
    async function dismissNotice(id, btn) {
      btn.closest('.task-notice').remove();
      const result = await apiPost('/api/activity/dismiss', { id }).catch(() => null);
      if (result) wakeOtherTabs();
    }
    document.addEventListener('DOMContentLoaded', pollActivity);
    window.addEventListener('focus', pollActivity);
    window.addEventListener('storage', e => { if (e.key === ACTIVITY_WAKE_KEY) pollActivity(); });

    function openWelcome() {
      const m = document.getElementById('welcome-modal');
      document.getElementById('welcome-btns').hidden = setupMode();
      document.getElementById('welcome-setup-btns').hidden = !setupMode();
      document.getElementById('welcome-s0').hidden = !setupMode();
      const s1 = document.getElementById('welcome-s1');
      s1.dataset.i18nHtml = setupMode() ? 'welcome_s1_setup' : 'welcome_s1';
      s1.innerHTML = t(s1.dataset.i18nHtml);
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }

    function setupMode() { return MEDIA_BOOT.setup || store.get('setup_again') === '1'; }
    const setupState = MEDIA_BOOT.setup ? { subs: true, books: true, manga: false } : { ...MEDIA_BOOT.on };
    function openSetupStep() {
      const card = document.getElementById('welcome-card');
      card.style.minHeight = card.offsetHeight + 'px';
      document.getElementById('welcome-pane').hidden = true;
      document.getElementById('setup-step').hidden = false;
      renderSetupRows();
    }
    let upgradeOpen = false;
    function openUpgradeSetup() {
      upgradeOpen = true;
      document.getElementById('welcome-pane').hidden = true;
      document.getElementById('setup-step').hidden = false;
      for (const [id, key] of [['setup-title', 'upgrade_title'], ['setup-lead', 'upgrade_lead']]) {
        const el = document.getElementById(id);
        el.dataset.i18n = key;
        el.textContent = t(key);
      }
      document.querySelectorAll('#setup-step .setup-first').forEach(b => b.hidden = true);
      document.getElementById('upgrade-save').hidden = false;
      renderSetupRows();
      document.getElementById('welcome-modal').classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }
    async function finishUpgrade() {
      const msg = document.getElementById('setup-msg');
      if (!MEDIA_KINDS.some(k => setupState[k])) { msg.textContent = t('setup_pick_one'); return; }
      const val = which => (document.querySelector(`#setup-rows input[data-which="${which}"]`) || {}).value || '';
      const btn = document.getElementById('upgrade-save');
      btn.disabled = true;
      const res = await apiPost('/api/setup', { upgrade: true, media: setupState, subs_dir: val('subs'), books_dir: val('books'), manga_dir: val('manga') })
        .catch(() => ({ error: 'network' }));
      btn.disabled = false;
      if (res.error) {
        msg.innerHTML = `<span class="warn">${esc(setupError(res.error))}</span>`;
        return;
      }
      window.location.reload();
    }
    function backToWelcome() {
      document.getElementById('setup-step').hidden = true;
      document.getElementById('welcome-pane').hidden = false;
    }
    function renderSetupRows() {
      const defaults = MEDIA_BOOT.defaults || {};
      const box = document.getElementById('setup-rows');
      const kept = {};
      box.querySelectorAll('input[data-which]').forEach(i => kept[i.dataset.which] = i.value);
      box.innerHTML = MEDIA_KINDS.map(which => `<div class="set-media-row">
          <div class="btns set-media-head">
            <strong>${esc(t('set_media_' + which))}</strong>
            <div class="seg" style="width:12em;">
              <button type="button" class="seg-btn ${setupState[which] ? '' : 'active'}" onclick="setSetupOn('${which}', false)">${esc(t('lib_cache_off'))}</button>
              <button type="button" class="seg-btn ${setupState[which] ? 'active' : ''}" onclick="setSetupOn('${which}', true)">${esc(t('lib_cache_on'))}</button>
            </div>
          </div>
          <div class="btns" ${setupState[which] ? '' : 'hidden'}>
            <input type="text" data-which="${which}" value="${esc(kept[which] ?? (MEDIA_BOOT.folders || {})[which] ?? defaults[which] ?? '')}" spellcheck="false" style="flex:1; min-width:0;">
            ${MEDIA_BOOT.picker ? `<button class="btn" onclick="setupBrowse('${which}')">${esc(t('setup_browse'))}</button>` : ''}
          </div>
        </div>`).join('');
    }
    function setSetupOn(which, on) {
      setupState[which] = on;
      renderSetupRows();
    }
    async function setupBrowse(which) {
      const input = document.querySelector(`#setup-rows input[data-which="${which}"]`);
      const msg = document.getElementById('setup-msg');
      msg.textContent = t('lib_picking');
      const res = await apiPost('/api/library/pick', { which, title: t('set_media_' + which) })
        .catch(() => ({ status: 'unavailable' }));
      msg.textContent = '';
      if (res.status === 'ok') input.value = res.path;
    }
    function setupError(error) {
      if (error === 'busy') return t('lib_err_busy');
      if (error === 'none_on') return t('setup_pick_one');
      const which = MEDIA_KINDS.find(k => error.endsWith(k + '_dir')) || 'subs';
      if (error.startsWith('not_full')) return t('lib_err_notfull', { path: (MEDIA_BOOT.defaults || {})[which] || '' });
      return t('setup_err_make');
    }
    async function finishSetup(goGuide) {
      const msg = document.getElementById('setup-msg');
      if (!MEDIA_KINDS.some(k => setupState[k])) { msg.textContent = t('setup_pick_one'); return; }
      const val = which => (document.querySelector(`#setup-rows input[data-which="${which}"]`) || {}).value || '';
      const btns = document.querySelectorAll('#setup-step .setup-finish');
      btns.forEach(b => b.disabled = true);
      const res = await apiPost('/api/setup', { media: setupState, subs_dir: val('subs'), books_dir: val('books'), manga_dir: val('manga') })
        .catch(() => ({ error: 'network' }));
      btns.forEach(b => b.disabled = false);
      if (res.error) {
        msg.innerHTML = `<span class="warn">${esc(setupError(res.error))}</span>`;
        return;
      }
      store.set('welcomed', '1');
      store.set('reindex_told', APP_VERSION);
      store.set('recheck_16_told', '1');
      store.set('seen_version', APP_VERSION);
      store.del('setup_again');
      window.location.href = goGuide ? '/?tab=guide' : '/?tab=library';
    }
    function closeWelcome(goGuide) {
      store.set('welcomed', '1');
      store.set('reindex_told', APP_VERSION);
      store.set('recheck_16_told', '1');
      store.set('seen_version', APP_VERSION);
      if (MEDIA_BOOT.upgrade) apiPost('/api/setup/seen', {}).catch(() => {});
      document.getElementById('welcome-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (goGuide) window.location.href = '/?tab=guide';
      else checkForUpdate();
    }

    async function checkReindex() {
      if ((APP_VERSION !== '1.6' || store.get('recheck_16_told') === '1')
          && store.get('reindex_told') === APP_VERSION) return checkForUpdate();
      let lib = null;
      try { lib = await fetch('/api/library/outdated').then(r => r.json()); } catch (e) {}
      if (APP_VERSION === '1.6' && store.get('recheck_16_told') !== '1' && lib) {
        store.set('recheck_16_told', '1');
        if (lib.has_database) {
          document.getElementById('recheck16-modal').classList.add('open');
          document.documentElement.style.overflow = 'hidden';
          return;
        }
      }
      if (store.get('reindex_told') === APP_VERSION) return checkForUpdate();
      const outdated = lib ? outdatedMedia(lib) : [];
      store.set('reindex_told', APP_VERSION);
      if (!outdated.length) return checkForUpdate();
      const m = document.getElementById('reindex-modal');
      m.querySelector('#reindex-body').innerHTML = t('reindex_body', { which: esc(outdatedSummary(outdated)) });
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }
    function closeReindex(goLibrary) {
      document.getElementById('reindex-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (goLibrary) window.location.href = '/?tab=library';
      else checkForUpdate();
    }
    function closeRecheck16(goLibrary) {
      document.getElementById('recheck16-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (goLibrary) window.location.href = '/?tab=library';
      else checkReindex();
    }

    async function checkForUpdate() {
      const boot = (document.querySelector('meta[name="aobana-boot"]') || {}).content || '';
      if (store.get('update_seen') === boot) return;
      for (let i = 0; i < 10; i++) {
        let info;
        try { info = await (await fetch('/api/update')).json(); } catch (e) { return; }
        if (info.checked) {
          store.set('update_seen', boot);
          if (info.newer && store.get('update_skip') !== info.latest) openUpdate(info);
          return;
        }
        await new Promise(r => setTimeout(r, 1500));
      }
    }
    let updateInfo = null;
    function openUpdate(info) {
      updateInfo = info;
      const m = document.getElementById('update-modal');
      m.querySelector('#update-body').innerHTML = t('update_body', { current: esc(info.current), latest: esc(info.latest) });
      m.querySelector('#update-link').href = info.url;
      if (info.termux) {
        m.querySelector('#update-more').textContent = t(info.self_update ? 'update_more_self' : 'update_more_termux');
        m.querySelector('#update-cmd-text').textContent = info.install_cmd || '';
        m.querySelector('#update-cmd').hidden = !!info.self_update;
        m.querySelector('#update-link').hidden = true;
        m.querySelector('#update-now').hidden = !info.self_update;
      } else if (info.auto) {
        m.querySelector('#update-auto').hidden = false;
        m.querySelector('#update-more').textContent = t('update_more_auto');
        m.querySelector('#update-link').classList.remove('primary');
      }
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }
    function closeUpdate() {
      document.getElementById('update-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
    }
    function skipUpdate() {
      if (updateInfo) store.set('update_skip', updateInfo.latest);
      closeUpdate();
    }
    async function copyUpdateCmd(btn) {
      const text = document.getElementById('update-cmd-text').textContent;
      try { await navigator.clipboard.writeText(text); }
      catch (e) {
        const r = document.createRange(); r.selectNodeContents(document.getElementById('update-cmd-text'));
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e2) {}
        if (!ok) return;
      }
      btn.textContent = t('update_copied');
    }
    async function applyUpdate() {
      const m = document.getElementById('update-modal');
      const from = updateInfo && updateInfo.current;
      try {
        const r = await fetch('/api/update/apply', { method: 'POST', headers: { 'X-Aobana': '1' } });
        if (!r.ok) return;
      } catch (e) { return; }
      m.querySelector('#update-more').textContent = t('update_running');
      m.querySelectorAll('.btns .btn').forEach(b => { b.hidden = true; });
      for (;;) {
        await new Promise(r => setTimeout(r, 3000));
        try {
          const info = await (await fetch('/api/update', { cache: 'no-store' })).json();
          if (info.current !== from) { location.reload(); return; }
        } catch (e) {}
      }
    }

    async function applyAutoUpdate() {
      const m = document.getElementById('update-modal');
      const more = m.querySelector('#update-more'), bar = m.querySelector('#update-progress');
      const from = updateInfo && updateInfo.current;
      const failed = () => {
        bar.hidden = true;
        more.textContent = t('update_failed');
        m.querySelectorAll('.btns .btn').forEach(b => { b.hidden = true; });
        const link = m.querySelector('#update-link');
        link.hidden = false;
        link.classList.add('primary');
      };
      const res = await apiPost('/api/update/apply', { lang: LANG }).catch(() => ({ error: 'network' }));
      if (res.error) return failed();
      m.querySelectorAll('.btns .btn').forEach(b => { b.hidden = true; });
      bar.hidden = false; bar.value = 0;
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      for (;;) {
        await sleep(400);
        let s;
        try { s = await (await fetch('/api/update/status', { cache: 'no-store' })).json(); } catch (e) { break; }
        if (s.state === 'error') return failed();
        if (s.state === 'installing') break;
        const pct = s.total ? Math.min(100, Math.floor(s.done * 100 / s.total)) : 0;
        bar.value = pct;
        more.textContent = t('update_downloading', { pct });
      }
      bar.hidden = true;
      more.textContent = t('update_installing') + (navigator.platform.startsWith('Win') ? ' ' + t('update_installing_admin') : '');
      let wentDown = false;
      for (;;) {
        await sleep(2000);
        try {
          const info = await (await fetch('/api/update?waiting=1', { cache: 'no-store' })).json();
          if (info.current !== from) { location.reload(); return; }
          if (wentDown) return failed();
        } catch (e) { wentDown = true; }
      }
    }

    const APP_VERSION = (document.querySelector('meta[name="aobana-version"]') || {}).content || '';
    function checkWhatsNew() {
      if (!APP_VERSION || store.get('seen_version') === APP_VERSION) return false;
      store.set('seen_version', APP_VERSION);
      openWhatsNew();
      return true;
    }
    function mdInline(s) {
      return esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '$1');
    }
    async function openWhatsNew() {
      const m = document.getElementById('whatsnew-modal');
      m.querySelector('#whatsnew-title').textContent = t('whatsnew_title', { version: APP_VERSION });
      m.querySelector('#whatsnew-sub').hidden = true;
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
      let notes = null;
      try { notes = await (await fetch('/api/release-notes')).json(); } catch (e) {}
      const items = (notes && notes.notable) || [];
      m.querySelector('#whatsnew-list').innerHTML = items.map(s => `<li>${mdInline(s)}</li>`).join('');
      m.querySelector('#whatsnew-sub').hidden = !items.length;
      m.querySelector('#whatsnew-none').hidden = !!items.length;
      if (notes && notes.url) m.querySelector('#whatsnew-more').href = notes.url;
    }
    function mdChangelog(text) {
      const out = []; let item = null, para = null;
      const flush = () => {
        if (item !== null) { out.push(`<li>${mdInline(item)}</li>`); item = null; }
        if (para !== null) { out.push(`<p>${mdInline(para)}</p>`); para = null; }
      };
      let inList = false;
      for (const line of text.split(/\r?\n/)) {
        const h = line.match(/^(#{1,3})\s+(.*)$/);
        if (h) { flush(); if (inList) { out.push('</ul>'); inList = false; }
                 if (h[1].length > 1) out.push(`<h3 class="whatsnew-sub">${mdInline(h[2])}</h3>`); continue; }
        if (line.startsWith('- ')) { flush(); if (!inList) { out.push('<ul class="whatsnew-list">'); inList = true; }
                                     item = line.slice(2).trim(); continue; }
        if (!line.trim()) { flush(); continue; }
        if (item !== null) item += ' ' + line.trim();
        else { if (inList) { out.push('</ul>'); inList = false; } para = (para ? para + ' ' : '') + line.trim(); }
      }
      flush(); if (inList) out.push('</ul>');
      return out.join('');
    }
    async function openChangelog() {
      const m = document.getElementById('changelog-modal');
      m.querySelector('#changelog-body').innerHTML = '';
      m.querySelector('#changelog-lang').hidden = !t('changelog_lang');
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
      let data = null;
      try { data = await (await fetch('/api/changelog')).json(); } catch (e) {}
      m.querySelector('#changelog-body').innerHTML = data && data.text
        ? mdChangelog(data.text) : `<p>${esc(t('changelog_none'))}</p>`;
      if (data && data.url) m.querySelector('#changelog-more').href = data.url;
    }
    function closeChangelog() {
      document.getElementById('changelog-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
    }
    function closeWhatsNew() {
      document.getElementById('whatsnew-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      afterWhatsNew();
    }
    function afterWhatsNew() {
      if (MEDIA_BOOT.upgrade && !setupMode()) openUpgradeSetup();
      else checkReindex();
    }

    const CARET = '<svg class="dd-caret" viewBox="0 0 20 20"><path d="M5.516 7.548a.625.625 0 0 1 .884-.884l3.6 3.6 3.6-3.6a.625.625 0 1 1 .884.884l-4.042 4.042a.625.625 0 0 1-.884 0z"/></svg>';
    function makeDropdown(el, { options, value, icon = '', title = '', onChange, left = false, labelFor }) {
      const cur = options.find(o => o.value === value) || options[0];
      el.classList.add('dd');
      if (left) el.classList.add('left');
      el.innerHTML = `
        <button type="button" class="dd-btn" title="${esc(title)}" aria-haspopup="listbox">
          ${icon ? `<span class="dd-icon">${icon}</span>` : ''}
          <span class="dd-label">${labelFor ? labelFor(cur) : `${cur.pre || ''}${esc(cur.label)}`}</span>${CARET}
        </button>
        <div class="dd-menu" role="listbox">
          ${options.map(o => `<div class="dd-item ${o.value === cur.value ? 'selected' : ''}" role="option" data-value="${esc(o.value)}">${o.pre || ''}<span>${esc(o.label)}</span></div>`).join('')}
        </div>`;
      el.querySelector('.dd-btn').addEventListener('click', e => {
        e.stopPropagation();
        const open = !el.classList.contains('open');
        document.querySelectorAll('.dd.open').forEach(d => d.classList.remove('open'));
        el.classList.toggle('open', open);
      });
      el.querySelectorAll('.dd-item').forEach(item => item.addEventListener('click', e => {
        e.stopPropagation();
        el.classList.remove('open');
        if (item.dataset.value !== cur.value) onChange(item.dataset.value);
      }));
    }
    document.addEventListener('click', e => {
      document.querySelectorAll('.dd.open').forEach(d => d.classList.remove('open'));
      if (!e.target.closest('.topbar')) setMenu(false);
    });

    const LABEL_STAGES = ['c-lang', 'c-theme', 'c-guide', 'c-settings', 'c-library', 'c-saved', 'c-media', 'c-search'];
    const TAB_ORDER = ['search', 'media', 'saved', 'library', 'settings', 'guide'];
    const SETTINGS = ['shortcuts-btn', 'lang-dd', 'theme-dd'];
    const DRAWER_STAGE = LABEL_STAGES.length + 1;
    const TABS_STAGE = DRAWER_STAGE + 1;
    const LAST_STAGE = TABS_STAGE + TAB_ORDER.length;
    window.topbarThresholds = [];
    let topbarThresholds = window.topbarThresholds;
    let currentTopbarStage = -1;

    function applyTopbarStage(stage) {
      const bar = document.querySelector('.topbar');
      const tabs = bar.querySelector('.nav-tabs');
      const menu = document.getElementById('topbar-menu');
      const menuTabs = menu.querySelector('.menu-tabs');
      const menuRight = menu.querySelector('.menu-right');
      const right = bar.querySelector(':scope > .topbar-right');
      const settingsIn = stage < DRAWER_STAGE ? 0 : stage === DRAWER_STAGE ? 2 : 3;
      const tabsIn = Math.max(0, stage - TABS_STAGE);
      const inDrawer = [...SETTINGS.slice(0, settingsIn), ...TAB_ORDER.slice(TAB_ORDER.length - tabsIn)];
      bar.classList.toggle('compact', stage >= DRAWER_STAGE);
      LABEL_STAGES.forEach((c, idx) => {
        let on = idx < stage;
        if (c === 'c-lang' && inDrawer.includes('lang-dd')) on = false;
        if (c === 'c-theme' && inDrawer.includes('theme-dd')) on = false;
        if (inDrawer.includes(c.slice(2))) on = false;
        bar.classList.toggle(c, on);
      });
      TAB_ORDER.forEach(name => {
        const a = document.querySelector(`.nav-tab[data-tab="${name}"]`);
        if (a) (inDrawer.includes(name) ? menuTabs : tabs).appendChild(a);
      });
      SETTINGS.forEach(id => {
        const el = document.getElementById(id);
        if (el) (inDrawer.includes(id) ? menuRight : right).appendChild(el);
      });
      right.classList.toggle('is-empty', settingsIn === SETTINGS.length);
    }

    function topbarGap() {
      const bar = document.querySelector('.topbar');
      const last = bar.querySelector('.nav-tabs').lastElementChild;
      if (!last) return Infinity;
      const right = bar.querySelector(':scope > .topbar-right');
      const next = right.classList.contains('is-empty') ? document.getElementById('menu-btn') : right;
      return next.getBoundingClientRect().left - last.getBoundingClientRect().right;
    }

    function updateTopbarThresholds() {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      if (bar.getBoundingClientRect().width <= 0) return;
      const wasSticky = bar.classList.contains('is-sticky');
      bar.classList.remove('is-sticky');
      const thresholds = [];
      for (let s = 0; s < LAST_STAGE; s++) {
        applyTopbarStage(s);
        thresholds.push(Math.ceil(bar.getBoundingClientRect().width - topbarGap() + 8));
      }
      window.topbarThresholds = topbarThresholds = thresholds;
      bar.classList.toggle('is-sticky', wasSticky);
      applyTopbarStage(Math.max(0, currentTopbarStage));
    }

    function fitTopbar(measuredWidth) {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      if (!topbarThresholds.length) updateTopbarThresholds();
      const cs = getComputedStyle(bar);
      const stickyOffset = -(parseFloat(cs.marginLeft) + parseFloat(cs.marginRight)) || 0;
      const rawW = measuredWidth !== undefined ? measuredWidth : Math.round(bar.offsetWidth);
      const w = rawW - stickyOffset;

      let stage = 0;
      while (stage < topbarThresholds.length && w < topbarThresholds[stage]) stage++;
      applyTopbarStage(stage);
      while (stage < LAST_STAGE && topbarGap() < 8) applyTopbarStage(++stage);
      if (stage < DRAWER_STAGE) setMenu(false);
      const changed = stage !== currentTopbarStage;
      currentTopbarStage = stage;
      if (changed) fitSidebar();
    }

    document.addEventListener('DOMContentLoaded', () => {
      let lastWidth = -1;
      new ResizeObserver(entries => {
        const bar = entries[0].target;
        const w = entries[0].borderBoxSize ? Math.round(entries[0].borderBoxSize[0].inlineSize) : Math.round(bar.offsetWidth);
        if (w !== lastWidth) {
          lastWidth = w;
          fitTopbar(w);
        }
      }).observe(document.querySelector('.topbar'));
      window.addEventListener('resize', () => fitTopbar());
    });
    if (document.fonts) document.fonts.ready.then(() => { updateTopbarThresholds(); fitTopbar(); });
    window.matchMedia('(max-width: 720px)').addEventListener('change', () => { updateTopbarThresholds(); fitTopbar(); });

    document.addEventListener('DOMContentLoaded', () => {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      const sentinel = document.createElement('div');
      sentinel.id = 'topbar-sentinel';
      sentinel.style.cssText = 'height:0;pointer-events:none;';
      bar.parentElement.insertBefore(sentinel, bar);
      new IntersectionObserver(([e]) => {
        const stuck = !e.isIntersecting;
        if (bar.classList.contains('is-sticky') !== stuck) {
          bar.classList.toggle('is-sticky', stuck);
          fitTopbar();
        }
      }, { threshold: 0 }).observe(sentinel);
    });

    function setMenu(open) {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      bar.classList.toggle('open', open);
      document.getElementById('menu-btn').setAttribute('aria-expanded', open ? 'true' : 'false');
      fitSidebar();
    }
    function toggleMenu(e) {
      e.stopPropagation();
      setMenu(!document.querySelector('.topbar').classList.contains('open'));
    }

    const ICON_LANG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h9M8.5 3v2M6 5c.8 3.2 3 5.6 6 7M11 5c-.9 3.6-3.4 6.4-7 8"/><path d="M13 21l4-9 4 9M14.4 18h5.2"/></svg>';
    const ICON_SUN = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
    const ICON_ROWS = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>';
    const ICON_MOON = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

    const SORT_ICONS = {
      recommended: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 16v4M17 18h4"/>',
      chrono: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 2"/><path d="M12 3.5v.5M20.5 12H20M12 20.5V20M3.5 12H4"/>',
      desc: '<path d="M4 6h16M4 12h11M4 18h6"/>',
      asc: '<path d="M4 6h6M4 12h11M4 18h16"/>',
      random: '<path d="M3 7h3c4 0 6 10 10 10h5"/><path d="M3 17h3c1.6 0 2.9-1.6 4-3.5M13.9 9.5C15 8 16.2 7 18 7h3"/><path d="M18.5 4.5L21 7l-2.5 2.5M18.5 14.5L21 17l-2.5 2.5"/>',
    };
    const sortIcon = v => `<svg class="dd-ico" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${SORT_ICONS[v]}</svg>`;

    function renderTopbarControls() {
      makeDropdown(document.getElementById('lang-dd'), {
        options: [{ value: 'ja', label: '日本語' }, { value: 'en', label: 'English' }],
        value: LANG, icon: ICON_LANG, title: 'Language / 言語', onChange: setLang,
        labelFor: o => `<span class="dd-text-optional">${esc(o.label)}</span>`,
      });
      const theme = currentTheme();
      makeDropdown(document.getElementById('theme-dd'), {
        options: THEMES.map(v => ({ value: v, label: t('theme_' + v), pre: `<span class="swatch ${v}"></span>` })),
        value: theme, icon: (theme === 'paper' || theme === 'haze') ? ICON_SUN : ICON_MOON,
        title: t('theme_label'), onChange: setTheme,
        labelFor: o => `<span class="dd-text-optional">${esc(o.label)}</span>`,
      });
      updateTopbarThresholds();
      fitTopbar();
    }

    function renderSearchControls() {
      const seg = document.getElementById('media-seg-side');
      if (seg) {
        seg.innerHTML = MEDIAS.map(m => `<button type="button" class="seg-btn ${m === MEDIA ? 'active' : ''}" data-media="${m}" onclick="setMediaMode('${m}')">${esc(mediaLabel(m))}</button>`).join('');
        seg.hidden = MEDIAS.length === 1;
        seg.classList.toggle('seg-many', MEDIAS.length > 3);
      }
      const sortEl = document.getElementById('sort-select');
      if (sortEl) {
        makeDropdown(sortEl, {
          options: SORTS.map(v => ({ value: v, label: t('sort_' + v), pre: sortIcon(v) })),
          value: SORT, title: t('sort_title'),
          onChange: v => {
            store.set('sort', v);
            document.getElementById('sort-input').value = v;
            document.querySelector('form.search-bar').submit();
          },
        });
      }
      document.getElementById('sort-input').value = SORT;
      document.getElementById('media-input').value = MEDIA;
      syncHiddenFolders();
      const qInput = document.querySelector('input[name="q"]');
      qInput.value = PARAMS.get('q') || '';
      const exact = document.getElementById('exact-check');
      exact.checked = PARAMS.get('exact') === 'on';
      const chip = document.getElementById('exact-chip');
      chip.classList.toggle('on', exact.checked);
      exact.addEventListener('change', () => chip.classList.toggle('on', exact.checked));
      const multi = document.getElementById('multi-check');
      const multiChip = document.getElementById('multi-chip');
      multi.checked = multiPick;
      multiChip.classList.toggle('on', multiPick);
      multi.addEventListener('change', () => {
        multiPick = multi.checked;
        multiChip.classList.toggle('on', multiPick);
        store.set('multiPick', multiPick ? 'on' : 'off');
        clearPins();
        pinFolders(currentFolders);
        if (!multiPick && currentFolders.length > 1) applyFolders(currentFolders.slice(-1), true);
        if (allResults.length === 0 && PARAMS.get('q')) setEmptyStateForFolders(currentFolders);
        if (multiPick && pinnedFolders.length) sidebarShown = SIDEBAR_PAGE;
        if (sidebarData) { drawSidebar(); revealChosen(); }
        if (multiPick && pinnedFolders.length) { const side = document.querySelector('.sidebar'); if (side) side.scrollTop = 0; }
        renderFilterNote();
        document.querySelectorAll('.folder-hint').forEach(p => { p.textContent = t(multiPick ? 'folder_hint' : 'folder_hint_one'); });
      });
      document.querySelectorAll('.furi-btn').forEach(b => b.classList.toggle('off', document.documentElement.classList.contains('no-furigana')));
    }

    document.addEventListener("DOMContentLoaded", () => {
      applyI18n();
      renderTopbarControls();
      document.querySelectorAll('.nav-tab').forEach(a => a.classList.toggle('active', a.dataset.tab === TAB));
      document.querySelectorAll('[data-tab-panel]').forEach(p => { p.hidden = p.dataset.tabPanel !== TAB; });

      if (TAB === 'search') {
        store.set('aobana_last_search', window.location.pathname + window.location.search);
        renderSearchControls();
        initFetch();
        initSidebarTooltip();
        const filter = document.getElementById('folder-filter');
        filter.addEventListener('input', filterFolders);
        document.querySelector('.sidebar').addEventListener('scroll', e => {
          const s = e.currentTarget;
          if (s.scrollTop + s.clientHeight > s.scrollHeight - 600) moreSidebar();
        }, { passive: true });
        document.getElementById('folder-list-dynamic').addEventListener('click', e => {
          const link = e.target.closest('.folder-link[data-folder]');
          if (link) setFolder(link.dataset.folder || null, e);
        });
      } else if (TAB === 'saved') {
        initSavedTab();
      } else if (TAB === 'media') {
        const seg = document.getElementById('media-seg');
        seg.innerHTML = MEDIAS.map(m => `<button type="button" class="seg-btn ${m === MEDIA_TAB_FILTER ? 'active' : ''}" data-media="${m}" onclick="setMediaTabFilter('${m}')">${esc(mediaLabel(m))}</button>`).join('');
        seg.hidden = MEDIAS.length === 1;
        seg.classList.toggle('seg-many', MEDIAS.length > 3);
        document.getElementById('media-filter').addEventListener('input', onMediaFilterInput);
        initMediaTab();
        initSidebarTooltip();
      } else if (TAB === 'library') {
        initLibraryTab();
      } else if (TAB === 'settings') {
        initSettingsTab();
      } else if (TAB === 'guide') {
        initGuideTab();
      }

      if (!MEDIAS_ON.length) showMediaOff();
      if (setupMode() || store.get('welcomed') !== '1') openWelcome();
      else if (!checkWhatsNew()) afterWhatsNew();
    });

    function initSidebarTooltip() {
      const tooltip = document.getElementById('sidebar-tooltip');
      if (!tooltip) return;

      let tooltipTimeout = null;
      let isTooltipActive = false;
      let closeGraceTimeout = null;

      function showTooltip(targetLink, text) {
        tooltip.textContent = text;
        tooltip.style.display = 'block';
        tooltip.style.visibility = 'hidden';

        const rect = targetLink.getBoundingClientRect();
        const tipRect = tooltip.getBoundingClientRect();

        let left = rect.right + 10;
        let top = rect.top + (rect.height - tipRect.height) / 2;

        if (left + tipRect.width > window.innerWidth - 12) {
          left = Math.max(12, Math.min(rect.left, window.innerWidth - tipRect.width - 12));
          top = rect.bottom + 6;
          if (top + tipRect.height > window.innerHeight - 12) {
            top = rect.top - tipRect.height - 6;
          }
        }
        if (top < 12) top = 12;
        if (top + tipRect.height > window.innerHeight - 12) {
          top = window.innerHeight - tipRect.height - 12;
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
        tooltip.style.visibility = 'visible';
        tooltip.classList.add('visible');
        isTooltipActive = true;
      }

      function hideTooltip() {
        clearTimeout(tooltipTimeout);
        tooltip.classList.remove('visible');
        tooltip.style.display = 'none';
      }

      function scheduleHide() {
        clearTimeout(tooltipTimeout);
        hideTooltip();
        clearTimeout(closeGraceTimeout);
        closeGraceTimeout = setTimeout(() => { isTooltipActive = false; }, 200);
      }

      const sidebarEl = document.querySelector('.sidebar');
      if (sidebarEl) {
        sidebarEl.addEventListener('mouseover', (e) => {
          const link = e.target.closest('.folder-link');
          if (!link) { scheduleHide(); return; }
          const span = link.querySelector('.folder-name, span:first-child');
          if (!span) { scheduleHide(); return; }

          if (span.scrollWidth - span.clientWidth > 1) {
            const text = span.textContent.trim();
            clearTimeout(tooltipTimeout);
            clearTimeout(closeGraceTimeout);
            if (isTooltipActive) {
              showTooltip(link, text);
            } else {
              tooltipTimeout = setTimeout(() => { showTooltip(link, text); }, 120);
            }
          } else {
            scheduleHide();
          }
        });

        sidebarEl.addEventListener('mouseout', (e) => {
          const link = e.target.closest('.folder-link');
          if (link) {
            if (e.relatedTarget && link.contains(e.relatedTarget)) return;
            scheduleHide();
          }
        });

        sidebarEl.addEventListener('scroll', () => { hideTooltip(); isTooltipActive = false; }, { passive: true });
      }

      document.addEventListener('mouseover', (e) => {
        const row = e.target.closest('.media-row');
        if (!row) return;
        const el = e.target.closest('.media-name, .media-author');
        if (el && el.scrollWidth - el.clientWidth > 1) {
          clearTimeout(tooltipTimeout);
          clearTimeout(closeGraceTimeout);
          if (isTooltipActive) showTooltip(el, el.textContent.trim());
          else tooltipTimeout = setTimeout(() => { showTooltip(el, el.textContent.trim()); }, 120);
        } else {
          scheduleHide();
        }
      });
      document.addEventListener('mouseout', (e) => {
        const el = e.target.closest('.media-row .media-name, .media-row .media-author');
        if (el && !(e.relatedTarget && el.contains(e.relatedTarget))) scheduleHide();
      });

      window.addEventListener('scroll', () => { hideTooltip(); isTooltipActive = false; }, { passive: true, capture: true });
      document.addEventListener('mousedown', () => { hideTooltip(); isTooltipActive = false; });
    }

    let isComposing = false;
    let justConfirmed = false;
    let activeCardIndex = -1;
    let lastNavTime = 0;

    function getVisibleCards() {
      return Array.from(document.querySelectorAll('#results .card, #results .episode-card'));
    }

    function updateActiveCard(newIndex) {
      const cards = getVisibleCards();
      if (cards.length === 0) return;
      cards.forEach(c => c.classList.remove('keyboard-active'));
      if (newIndex < 0) newIndex = 0;
      if (newIndex >= cards.length) newIndex = cards.length - 1;
      activeCardIndex = newIndex;
      const activeCard = cards[activeCardIndex];
      if (activeCard) {
        activeCard.classList.add('keyboard-active');
        activeCard.scrollIntoView({ behavior: 'auto', block: 'nearest' });
      }
    }

    function toggleShortcutsModal() {
      const modal = document.getElementById('shortcuts-modal');
      if (modal) {
        const isOpen = modal.classList.toggle('open');
        document.documentElement.style.overflow = isOpen ? 'hidden' : '';
      }
    }

    function handleSearchTabClick(e) {
      if (TAB === 'search') {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      const last = store.get('aobana_last_search');
      if (last) {
        e.preventDefault();
        window.location.href = last;
      }
    }

    function handleSearchSubmit(e, form) {
      if (isComposing || justConfirmed) {
        if (e && e.preventDefault) e.preventDefault();
        return false;
      }
      const qInput = form.querySelector('input[name="q"]');
      const exactCheck = form.querySelector('input[name="exact"]');
      let val = qInput.value.trim();
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith('“') && val.endsWith('”')) || (val.startsWith('”') && val.endsWith('”'))) {
        if (val.length > 2) {
          qInput.value = val.substring(1, val.length - 1);
          exactCheck.checked = true;
        }
      }

      const qVal = qInput.value.trim();
      if (qVal) {
        const p = new URLSearchParams();
        p.set('q', qVal);
        if (exactCheck && exactCheck.checked) p.set('exact', 'on');
        if (SORT) p.set('sort', SORT);
        if (MEDIA && MEDIA !== 'all') p.set('media', MEDIA);
        currentFolders.forEach(f => p.append('folder', f));
        const searchUrl = '/?' + p.toString();
        store.set('aobana_last_search', searchUrl);
      } else {
        cancelServerSearch(1);
        store.del('aobana_last_search');
      }
    }

    document.addEventListener("DOMContentLoaded", () => {
      const qInput = document.querySelector('input[name="q"]');
      if (qInput) {
        qInput.addEventListener('compositionstart', () => {
          isComposing = true;
        });
        qInput.addEventListener('compositionend', () => {
          isComposing = false;
          justConfirmed = true;
          setTimeout(() => { justConfirmed = false; }, 60);
        });
        qInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            if (e.isComposing || e.keyCode === 229 || isComposing || justConfirmed) {
              e.preventDefault();
              return false;
            }
          }
        });
      }
    });

    document.addEventListener('keydown', function(e) {
      const activeTag = document.activeElement ? document.activeElement.tagName : '';
      const isInputActive = activeTag === 'INPUT' || activeTag === 'TEXTAREA' || activeTag === 'SELECT';

      if ((e.key === '?' || (e.shiftKey && (e.code === 'Slash' || e.key === '/'))) && !isInputActive && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        toggleShortcutsModal();
        return;
      }

      if (e.key === 'Escape') {
        const modal = document.getElementById('shortcuts-modal');
        if (modal && modal.classList.contains('open')) { toggleShortcutsModal(); return; }
        const welcome = document.getElementById('welcome-modal');
        if (welcome && welcome.classList.contains('open')) { if (!setupMode() && !upgradeOpen) closeWelcome(false); return; }
        const reset = document.getElementById('reset-modal');
        if (reset && reset.classList.contains('open')) { closeReset(false); return; }
        const changelog = document.getElementById('changelog-modal');
        if (changelog && changelog.classList.contains('open')) { closeChangelog(); return; }
        document.querySelectorAll('.dd.open').forEach(d => d.classList.remove('open'));
        setMenu(false);
      }

      if (e.ctrlKey || e.altKey || e.metaKey) {
        return;
      }

      if ((e.key === 'q' || e.key === 'Q' || e.code === 'KeyQ') && !isInputActive && !e.shiftKey) {
        const qInput = [document.querySelector('input[name="q"]'), document.getElementById('media-detail-q'), document.getElementById('media-detail-filter'), document.getElementById('media-filter')].find(el => el && el.offsetParent !== null);
        if (qInput) {
          e.preventDefault();
          qInput.focus();
          qInput.select();
        }
        return;
      }

      if (!isInputActive) {
        const modal = document.getElementById('shortcuts-modal');
        if (modal && modal.classList.contains('open')) return;

        if ((e.key === 'f' || e.key === 'F') && !e.shiftKey) {
          e.preventDefault();
          toggleFurigana();
          return;
        }

        const now = Date.now();
        const isNavKey = ((e.key === 'a' || e.key === 'A') && !e.shiftKey) || e.key === 'ArrowUp' ||
                         ((e.key === 'd' || e.key === 'D') && !e.shiftKey) || e.key === 'ArrowDown';
        if (isNavKey && e.repeat && (now - lastNavTime < 65)) {
          e.preventDefault();
          return;
        }

        if (((e.key === 'd' || e.key === 'D') && !e.shiftKey) || e.key === 'ArrowDown') {
          e.preventDefault();
          lastNavTime = now;
          updateActiveCard(activeCardIndex + 1);
        } else if (((e.key === 'a' || e.key === 'A') && !e.shiftKey) || e.key === 'ArrowUp') {
          e.preventDefault();
          lastNavTime = now;
          updateActiveCard(activeCardIndex - 1);
        } else if ((e.key === 'c' || e.key === 'C') && !e.shiftKey) {
          const cards = getVisibleCards();
          if (activeCardIndex >= 0 && activeCardIndex < cards.length) {
            const card = cards[activeCardIndex];
            const ctxBtn = card.querySelector('button[onclick*="toggleContext"]');
            if (ctxBtn) { e.preventDefault(); ctxBtn.click(); }
            const epHeader = card.querySelector('.episode-header');
            if (epHeader) { e.preventDefault(); epHeader.click(); }
          }
        } else if ((e.key === 's' || e.key === 'S') && !e.shiftKey) {
          const cards = getVisibleCards();
          if (activeCardIndex >= 0 && activeCardIndex < cards.length) {
            const card = cards[activeCardIndex];
            const starBtn = card.querySelector('button[onclick*="toggleSave"]');
            if (starBtn) { e.preventDefault(); starBtn.click(); }
          }
        }
      }
    });
