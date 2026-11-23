    function mediaTabFilter() {
      const m = store.get('mediaTabFilter');
      return MEDIAS.includes(m) ? m : MEDIAS[0];
    }
    const MEDIA_TAB_FILTER = mediaTabFilter();
    const mediaTabUnfiltered = () => MEDIAS.length === 1 || mediaTabFilter() === 'all';

    function statPills(it) {
      if (it.media === 'custom') {
        return `${it.file ? '' : `<span class="stat-pill secondary">${esc(t('custom_files', { n: fmt(it.episodes) }))}</span>`}<span class="stat-pill">${esc(t('stat_lines', { n: fmt(it.lines) }))}</span>`;
      }
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
    const MEDIA_LIST_STATE = 'aobana_media_list';
    if (TAB === 'media' && 'scrollRestoration' in history) history.scrollRestoration = 'manual';
    let mediaRestoring = false;
    let mediaDetailFiles = [];
    const mediaGroupState = new Map();
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
      if (PARAMS.get('media') === 'custom' && PARAMS.get('folder')) {
        // A Custom page keeps its own state (custom.js), the open reader with it.
        if (typeof customSaveState === 'function') customSaveState();
        return;
      }
      if (TAB !== 'media' || mediaRestoring) return;
      if (!PARAMS.get('folder')) {
        const opts = mediaListOptions();
        const listState = { url: mediaUrl(), q: document.getElementById('media-filter')?.value || '',
          media: mediaTabFilter(), sort: mediaSort(), loaded: mediaOffset, y: Math.round(window.scrollY),
          at: mediaListAnchor(), mode: mediaListMode, hits: mediaHitsQ, exact: opts.exact, ruby_only: opts.rubyOnly };
        try { sessionStorage.setItem(MEDIA_LIST_STATE, JSON.stringify(listState)); } catch (e) {}
        store.set(MEDIA_STATE, JSON.stringify({ url: mediaUrl(), open: [], y: listState.y }));
        return;
      }
      const filterEl = document.getElementById('media-detail-filter');
      const qEl = document.getElementById('media-detail-q');
      if (mediaDetailMode === 'content' && mediaDetailContentActive && qEl && qEl.value.trim()) {
        const opts = mediaDetailOptions();
        store.set(MEDIA_STATE, JSON.stringify({
          url: mediaUrl(), mode: 'content', q: qEl.value.trim(), exact: opts.exact, ruby_only: opts.rubyOnly,
          open: [], y: Math.round(window.scrollY), at: mediaAnchor()
        }));
        return;
      }
      const open = [];
      document.querySelectorAll('#results .episode-card:not(.collapsed)').forEach(card => {
        const h = card.querySelector('.episode-header');
        const loaded = card.querySelectorAll('.episode-line').length;
        if (h && loaded) open.push({ file: h.dataset.file, loaded, start: parseInt(card.dataset.start || '0', 10) });
      });
      const titleQ = (mediaDetailMode === 'title' && filterEl) ? filterEl.value.trim() : '';
      const reader = typeof rmCurrentRecipe === 'function' ? rmCurrentRecipe() : null;
      store.set(MEDIA_STATE, JSON.stringify({
        url: mediaUrl(), mode: mediaDetailMode, q: titleQ, open,
        groups: [...mediaGroupState], y: Math.round(window.scrollY), at: mediaAnchor(),
        ...(reader ? { reader } : {}),
      }));
    }
    function mediaAnchor() {
      const bar = document.querySelector('.topbar');
      const slot = bar && bar.querySelector('.topbar-path');
      const probeY = Math.max(0, bar ? bar.getBoundingClientRect().bottom : 0, slot && slot.offsetHeight ? slot.getBoundingClientRect().bottom : 0) + 8;
      const hit = document.elementFromPoint(Math.round(window.innerWidth / 2), probeY);
      const group = hit && hit.closest('.media-subfolder > summary');
      if (group) return { group: group.parentElement.dataset.group, dy: Math.round(group.getBoundingClientRect().top) };
      const el = hit && hit.closest('.episode-line, .episode-header');
      const card = el && el.closest('.episode-card');
      if (!card) return null;
      const header = card.querySelector('.episode-header');
      const idx = el.classList.contains('episode-line') ? [...card.querySelectorAll('.episode-line')].indexOf(el) : -1;
      return { file: header.dataset.file, idx, dy: Math.round(el.getBoundingClientRect().top) };
    }
    function scrollToMediaAnchor(state) {
      const at = state.at;
      if (at && at.group) {
        const group = [...document.querySelectorAll('.media-subfolder')].find(g => g.dataset.group === at.group);
        if (group) {
          const summary = group.querySelector(':scope > summary');
          summary.scrollIntoView({ block: 'start' });
          window.scrollBy(0, summary.getBoundingClientRect().top - at.dy);
          return;
        }
      }
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
        mediaGroupState.clear();
        for (const pair of state.groups || []) {
          if (Array.isArray(pair) && typeof pair[0] === 'string') mediaGroupState.set(pair[0], !!pair[1]);
        }
        renderEpisodesList(mediaDetailFiles);
        if (state.mode === 'title' || state.mode === 'content') {
          setMediaDetailMode(state.mode, true);
        }
        if (state.mode === 'content' && state.q) {
          const qEl = document.getElementById('media-detail-q');
          const filterEl = document.getElementById('media-detail-filter');
          if (qEl) qEl.value = state.q;
          if (filterEl) filterEl.value = state.q;
          setMediaDetailOptions(state.exact, state.ruby_only);
          await runMediaDetailContentSearch(state.q, mediaDetailOptions());
          scrollToMediaAnchor(state);
          return;
        }
        if (state.mode === 'title' && state.q) {
          const filterEl = document.getElementById('media-detail-filter');
          const qEl = document.getElementById('media-detail-q');
          if (qEl) qEl.value = state.q;
          if (filterEl) {
            filterEl.value = state.q;
            filterMediaDetailTitles(state.q);
          }
        }
        for (const o of state.open || []) {
          const header = [...document.querySelectorAll('#results .episode-header')].find(h => h.dataset.file === o.file);
          if (!header) continue;
          await expandEpisode(header, o.start || 0);
          const content = header.parentElement.querySelector('.episode-content');
          while (content.querySelectorAll('.episode-line').length < o.loaded) {
            const sentinel = content.querySelector('.ep-sentinel');
            if (!sentinel) break;
            epSentinelObserver.unobserve(sentinel);
            await loadMoreEpisodeSentinel(sentinel, sentinel.dataset.file, parseInt(sentinel.dataset.offset, 10));
          }
        }
        scrollToMediaAnchor(state);
        if (state.reader && state.reader.media && typeof openReadingMode === 'function' && rmSupportsMedia(state.reader.media)) {
          await openReadingMode({ ...state.reader, fromRestore: true });
        }
      } finally {
        mediaRestoring = false;
        document.documentElement.classList.remove('rm-booting');
      }
    }

    function keepsSearch() {
      const nav = performance.getEntriesByType ? performance.getEntriesByType('navigation')[0] : null;
      return !nav || nav.type === 'back_forward' || nav.type === 'reload';
    }
    function withoutSearch(state) {
      if (!state.q) return state;
      return { ...state, q: '', open: state.mode === 'content' ? [] : (state.open || []), y: 0, at: null };
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
    const MEDIA_SORTS = ['name', 'read_desc', 'parts_desc', 'parts_asc', 'lines_desc', 'lines_asc'];
    function mediaSort() {
      const v = store.get('mediaSort', 'name');
      return MEDIA_SORTS.includes(v) ? v : 'name';
    }
    const CUSTOM_SORTS = ['default', ...MEDIA_SORTS];
    function customSort() {
      const v = store.get('customSort', 'default');
      return CUSTOM_SORTS.includes(v) ? v : 'default';
    }
    function mediaSortLabel(v) { return t('media_sort_' + v); }
    let mediaPartsVary = true;
    let mediaSortFor = '';
    let mediaGen = 0, mediaCtrl = null, mediaOffset = 0, mediaHasMore = false, mediaBusy = false;
    let mediaMoreObserver = null, mediaFilterTimer = null, mediaInnerTimer = null;
    let mediaListMode = store.get('mediaListMode') === 'content' ? 'content' : 'title';
    let mediaHitsQ = '';
    const mediaHitRows = new Map();

    async function fetchMedia(params, signal, onWait) {
      for (;;) {
        await whenShown(signal, true);
        const r = await fetch('/api/media?' + params.toString(), { signal });
        if (r.status !== 202) return r.json();
        const st = await r.json();
        if (onWait) onWait(st);
        if (st.requires_index || st.requires_tables) await whenShown(signal, false);
        else await new Promise(res => setTimeout(res, 700));
      }
    }

    function whenShown(signal, now) {
      return new Promise((resolve, reject) => {
        if (now && !document.hidden) return resolve();
        const stop = () => { document.removeEventListener('visibilitychange', seen); };
        const seen = () => { if (!document.hidden) { stop(); resolve(); } };
        document.addEventListener('visibilitychange', seen);
        if (signal) signal.addEventListener('abort', () => { stop(); reject(new DOMException('Aborted', 'AbortError')); }, { once: true });
      });
    }

    function mediaRowHtml(it, mark = '') {
      const p = new URLSearchParams({ tab: 'media', folder: it.folder, media: it.media });
      // A Custom category of one file under its own name opens the file
      const href = it.file ? customUrl(it.folder, '', it.file) : '/?' + p.toString();
      return `<a class="media-row" href="${esc(href)}" draggable="false">
          <span class="media-kind ${it.media}">${esc(t('kind_' + it.media))}</span>
          <span class="media-names">
            <div class="media-name">${markTitle(it.folder, mark)}</div>
            ${it.author ? `<div class="media-author">${markTitle(it.author, mark)}</div>` : ''}
          </span>
          <span class="media-stats">${statPills(it)}</span>
        </a>`;
    }

    function mediaInnerHtml(it, mark = '') {
      const href = it.media === 'custom' ? customUrl(it.folder, it.path, it.inner === 'file' ? it.file : undefined)
        : '/?' + new URLSearchParams({ tab: 'media', folder: it.folder, media: it.media, at_file: it.file });
      // The work's name leads an episode's or chapter's title; the line under it names the work
      const cut = it.title.indexOf(it.folder + '｜');
      const name = cut >= 0 ? it.title.slice(cut + it.folder.length + 1) : it.title;
      return `<a class="media-row media-inner" href="${esc(href)}" data-key="${esc(['inner', it.media, it.inner, it.path || it.file].join(':'))}" draggable="false">
          <span class="media-kind ${it.media}">${esc(t('kind_' + it.media))}</span>
          <span class="media-names">
            <div class="media-name">${markTitle(name || it.title, mark)}</div>
            <div class="media-author">${markTitle([it.folder, ...it.trail].join(' › '), mark)}</div>
          </span>
          ${it.inner === 'folder' ? `<span class="media-stats"><span class="stat-pill">${esc(t('custom_folder'))}</span></span>` : ''}
        </a>`;
    }

    async function loadMediaPage(reset, quiet) {
      if (reset) {
        mediaGen++;
        clearTimeout(mediaInnerTimer);
        if (mediaCtrl) mediaCtrl.abort();
        cancelServerSearch(0);
        stopSearchEta();
        document.getElementById('main-loading').style.display = 'none';
        mediaOffset = 0; mediaHasMore = false; mediaBusy = false;
      }
      if (mediaBusy) return;
      if (mediaHitsQ) return loadMediaHits();
      mediaBusy = true;
      const gen = mediaGen;
      mediaCtrl = new AbortController();
      const needle = (document.getElementById('media-filter').value || '').trim();
      const params = new URLSearchParams({ media: mediaTabFilter(), q: needle,
        offset: String(mediaOffset), limit: MEDIA_PAGE, sort: mediaSort() });
      const listEl = document.getElementById('media-list');
      const moreEl = document.getElementById('media-more');
      // Not while asking again for the names inside the works: the wait line stays (it flickered)
      if (!quiet && !mediaOffset && !listEl.firstElementChild) {
        listEl.innerHTML = `<div class="status-line" style="padding:2em;text-align:center;">${esc(t('loading'))}</div>`;
      }
      let data;
      try {
        data = await fetchMedia(params, mediaCtrl.signal, st => {
          if (gen !== mediaGen || mediaOffset) return;
          listEl.innerHTML = `<div class="status-line" style="padding:2em;text-align:center;">${esc(t('media_preparing'))}…` +
            `<div class="load-eta">${esc(st.requires_index ? t('media_index_needed') : st.requires_tables ? t('media_tables_needed') : st.remaining == null ? t('duration_unknown') : fmtEta(st.remaining))}</div></div>`;
        });
      } catch (e) {
        if (e.name !== 'AbortError' && gen === mediaGen) {
          listEl.innerHTML = `<div class="status-line error-text" style="padding:2em;">${esc(t('load_failed'))}</div>`;
        }
        if (gen === mediaGen) mediaBusy = false;
        return;
      }
      if (gen !== mediaGen) return;
      mediaBusy = false;
      if (!mediaOffset && !needle && !data.total && mediaTabUnfiltered()) {
        document.getElementById('media-body').hidden = true;
        document.getElementById('media-empty').hidden = false;
        return;
      }
      showMediaSummary(data);
      if (!mediaOffset && (!!data.parts_vary !== mediaPartsVary || mediaSortFor !== mediaTabFilter())) { mediaPartsVary = !!data.parts_vary; initMediaSort(); }
      const head = `<div class="media-inner-head">${esc(t('media_inner_head'))}</div>`;
      const unreadHead = `<div class="media-inner-head">${esc(t('media_unread_head'))}</div>`;
      const html = data.items.map((it, i) => (data.unread_from != null && mediaOffset + i === data.unread_from && !it.inner ? unreadHead : '')
        + (mediaOffset + i === data.works && it.inner ? head : '')
        + (it.inner ? mediaInnerHtml(it, needle) : mediaRowHtml(it, needle))).join('');
      const none = `<div class="status-line" style="padding:2em;">${esc(t('media_none'))}</div>`;
      if (!mediaOffset) {
        listEl.hidden = !html && !!data.inner_pending;
        // Nothing found is said only once the names inside the works are searched too
        listEl.innerHTML = html || (data.inner_pending ? '' : none);
      } else if (html) {
        listEl.insertAdjacentHTML('beforeend', html);
      } else if (!listEl.firstElementChild && !data.inner_pending) {
        listEl.innerHTML = none;
      }
      mediaOffset += data.items.length;
      mediaHasMore = data.has_more;
      moreEl.textContent = mediaHasMore ? t('loading') : '';
      if (mediaHasMore && !mediaRestoring) watchMediaEnd();
      showMediaInnerWait(data, gen);
    }

    function showMediaInnerWait(data, gen) {
      clearTimeout(mediaInnerTimer);
      if (!data.inner_pending || mediaHasMore) return;
      const left = data.inner_pending.remaining;
      document.getElementById('media-more').innerHTML = `<div class="status-line" style="padding:1em;text-align:center;">${esc(t('media_inner_preparing'))}` +
        (left == null ? '' : `<div class="load-eta">${esc(fmtEta(left))}</div>`) + '</div>';
      mediaInnerTimer = setTimeout(() => { if (gen === mediaGen && !mediaBusy) loadMediaPage(false, true); }, 1500);
    }

    function showMediaSummary(data) {
      const counts = { subs: data.shows, epub: data.books, manga: data.manga, custom: data.custom };
      const one = MEDIAS_ON.length === 1 ? MEDIAS_ON[0] : mediaTabFilter() === 'all' ? null : mediaTabFilter();
      const summary = one ? t('media_summary_' + one, { n: fmt(counts[one] || 0) })
        : [t('media_summary_total', { n: fmt(MEDIAS_ON.reduce((sum, m) => sum + (counts[m] || 0), 0)) }),
           ...MEDIAS_ON.map(m => t('media_summary_' + m, { n: fmt(counts[m] || 0) }))].join(' · ');
      document.getElementById('media-summary').textContent = summary;
    }

    function mediaHitHtml(r) {
      const media = r.media_type || 'subs';
      const key = media + ':' + r.rowid;
      mediaHitRows.set(key, r);
      const href = media === 'custom' ? customUrl(r.folder, r.folder) : '/?' + new URLSearchParams({ tab: 'media', folder: r.folder, media });
      // The page as text: pageLabel's link to the image would end the row's own link there
      const page = r.page ? ` · ${esc(t('page_n', { n: fmt(r.page) }))}` : '';
      return `<a class="media-row custom-hit" href="${esc(href)}" data-key="${esc(key)}" draggable="false">
          <span class="media-kind ${media}">${esc(t('kind_' + media))}</span>
          <span class="media-names"><div class="media-name">${esc(r.title || r.folder)}${page}</div><div class="main-sentence">${r.display_line}</div></span>
        </a>`;
    }

    async function loadMediaHits() {
      mediaBusy = true;
      const gen = mediaGen, first = !mediaOffset;
      mediaCtrl = new AbortController();
      const opts = mediaListOptions();
      const qs = new URLSearchParams({ q: mediaHitsQ, origin: 'media', media: mediaTabFilter(), sort: 'chrono',
        limit: MEDIA_PAGE, offset: String(mediaOffset) });
      if (opts.exact) qs.set('exact', 'on');
      if (opts.rubyOnly) qs.set('ruby_only', 'on');
      const listEl = document.getElementById('media-list');
      const moreEl = document.getElementById('media-more');
      const loading = document.getElementById('main-loading');
      if (first) {
        store.del('aobana_last_search');
        mediaHitRows.clear();
        listEl.hidden = true;
        listEl.innerHTML = '';
        moreEl.textContent = '';
        loading.style.display = 'flex';
        startSearchEta(qs.toString(), gen, () => mediaGen);
        fetchMedia(new URLSearchParams({ media: mediaTabFilter(), limit: '0' }), mediaCtrl.signal)
          .then(data => { if (gen === mediaGen && data.items) showMediaSummary(data); }).catch(() => {});
      }
      serverSearchInFlight++;
      try {
        const res = await fetch(apiSearchUrl(qs.toString()), { signal: mediaCtrl.signal });
        const data = await res.json();
        if (gen !== mediaGen || data.aborted) return;
        listEl.hidden = false;
        if (data.busy) {
          if (first) listEl.innerHTML = busyLine('2em');
          else moreEl.innerHTML = busyLine('1em');
          return;
        }
        const html = (data.results || []).map(mediaHitHtml).join('');
        if (first) listEl.innerHTML = html || `<div class="status-line" style="padding:2em;">${esc(t('no_results'))}</div>`;
        else listEl.insertAdjacentHTML('beforeend', html);
        mediaOffset += (data.results || []).length;
        mediaHasMore = !!data.has_more;
        moreEl.textContent = mediaHasMore ? t('loading') : '';
        if (mediaHasMore && !mediaRestoring) watchMediaEnd();
      } catch (e) {
        if (e.name !== 'AbortError' && gen === mediaGen) {
          listEl.hidden = false;
          if (first) listEl.innerHTML = `<div class="status-line error-text" style="padding:2em;">${esc(t('error'))}</div>`;
          else moreEl.textContent = t('error');
        }
      } finally {
        serverSearchInFlight = Math.max(0, serverSearchInFlight - 1);
        if (gen === mediaGen) {
          mediaBusy = false;
          if (first) { stopSearchEta(); loading.style.display = 'none'; }
        }
      }
    }

    async function openMediaHit(e) {
      const a = e.target.closest('#media-list .custom-hit');
      if (!a || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      if (e.target.closest('button')) return;
      const row = mediaHitRows.get(a.dataset.key);
      if (!row) return;
      e.preventDefault();
      if (a.dataset.opening) return;
      a.dataset.opening = '1';
      let got = {};
      try { got = await readerAtUrl(row); } catch (err) {}
      delete a.dataset.opening;
      if (got.busy) { a.querySelector('.main-sentence')?.insertAdjacentHTML('afterend', busyLine('0.4em 0')); return; }
      window.location.href = got.url || a.href;
    }

    async function readerAtUrl(row) {
      const media = row.media_type || 'subs';
      const res = await fetch('/api/reader/at?' + new URLSearchParams({ media, file: row.file, rowid: String(row.rowid), text: row.line || '' }));
      if (await busyAnswer(res)) return { busy: true };
      const d = await res.json();
      if (!d || !d.status) return {};
      if (media === 'custom') {
        const url = d.status === 'file_gone' ? customUrl(row.folder, row.folder) : customUrl(d.folder, d.path, d.file);
        return { url: url + (d.status === 'ok' ? `&at=${encodeURIComponent(d.rowid)}` : `&at_note=${d.status}`) };
      }
      const p = new URLSearchParams({ tab: 'media', folder: d.folder, media });
      if (d.status !== 'file_gone') p.set('at_file', d.file);
      if (d.status === 'ok') { p.set('at', String(d.rowid)); p.set('at_offset', String(d.offset)); }
      else p.set('at_note', d.status);
      return { url: '/?' + p.toString() };
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

    const mediaRowKey = el => el.dataset.key || el.getAttribute('href');
    function mediaListAnchor() {
      const bar = document.querySelector('.topbar');
      const edge = (bar ? bar.getBoundingClientRect().bottom : 0) + 8;
      const row = [...document.querySelectorAll('#media-list .media-row')].find(el => el.getBoundingClientRect().bottom > edge);
      return row ? { url: mediaRowKey(row), dy: row.getBoundingClientRect().top } : null;
    }
    function restoreMediaListScroll(state) {
      const row = state.at && [...document.querySelectorAll('#media-list .media-row')].find(el => mediaRowKey(el) === state.at.url);
      if (row) window.scrollTo({ top: window.scrollY + row.getBoundingClientRect().top - state.at.dy, behavior: 'instant' });
      else window.scrollTo(0, state.y || 0);
    }
    document.addEventListener('click', e => {
      if (TAB === 'media' && e.target.closest('#media-list .media-row')) saveMediaState();
    }, true);

    async function initMediaTab() {
      const folder = PARAMS.get('folder');
      const clean = !keepsSearch();
      // custom.js ends rm-booting once it knows whether Reading mode opens again
      if (folder && PARAMS.get('media') === 'custom') return initCustomBrowser(folder);
      if (folder) return initMediaDetail(folder, clean);
      document.documentElement.classList.remove('rm-booting');
      try { sessionStorage.removeItem('aobana_rm_open'); } catch (e) {}
      document.getElementById('media-list').before(document.getElementById('main-loading'));
      initMediaListSearch();
      watchDockRow(document.querySelector('#media-body .media-toolbar-wrap'));
      let prior = null;
      try { prior = JSON.parse(sessionStorage.getItem(MEDIA_LIST_STATE) || 'null'); } catch (e) {}
      // Opened by a click: the list without its search, at the top; its mode, chips, sort and media stay
      if (clean && prior && (prior.q || prior.hits)) prior = { ...prior, q: '', hits: '', loaded: 0, y: 0, at: null };
      mediaRestoring = true;
      try {
        if (prior) {
          document.getElementById('media-filter').value = prior.q || '';
          document.getElementById('media-q').value = prior.q || '';
          store.set('mediaSort', prior.sort);
          store.set('mediaTabFilter', prior.media);
          document.querySelectorAll('#media-seg .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.media === prior.media));
          if (prior.mode === 'title' || prior.mode === 'content') mediaListMode = prior.mode;
          mediaHitsQ = mediaListMode === 'content' ? (prior.hits || '') : '';
          setMediaListOptions(prior.exact, prior.ruby_only);
        }
        showMediaListMode();
        setTitle(t('tab_media'));
        initMediaSort();
        const firstPage = loadMediaPage(true);
        const restoreGen = mediaGen;
        await firstPage;
        while (prior && mediaGen === restoreGen && mediaHasMore && mediaOffset < prior.loaded) {
          const before = mediaOffset;
          await loadMediaPage(false);
          if (mediaOffset <= before) break;
        }
        if (prior && mediaGen === restoreGen) {
          if (document.fonts) await document.fonts.ready;
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          if (mediaGen === restoreGen) {
            restoreMediaListScroll(prior);
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            if (mediaGen === restoreGen) restoreMediaListScroll(prior);
          }
        }
      } finally { mediaRestoring = false; }
      saveMediaState();
      if (mediaHasMore) watchMediaEnd();
    }
    function initMediaSort() {
      mediaSortFor = mediaTabFilter();
      const sorts = MEDIA_SORTS.filter(v => mediaPartsVary || !v.startsWith('parts'));
      makeDropdown(document.getElementById('media-sort'), {
        options: sorts.map(v => ({ value: v, label: mediaSortLabel(v) })),
        value: sorts.includes(mediaSort()) ? mediaSort() : 'name', title: t('media_sort_title'), icon: ICON_ROWS,
        onChange: v => { store.set('mediaSort', v); initMediaSort(); mediaListTop(); loadMediaPage(true).then(saveMediaState); },
      });
      // Its width decides what fits beside the box and the switch on a phone
      fitDockedRow();
    }

    function setMediaTabFilter(m) {
      store.set('mediaTabFilter', m);
      document.querySelectorAll('#media-seg .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.media === m));
      mediaListTop();
      loadMediaPage(true).then(saveMediaState);
    }
    function mediaListTop() { window.scrollTo({ top: 0, behavior: 'instant' }); }

    function onMediaFilterInput() {
      const q = document.getElementById('media-q');
      if (q) q.value = document.getElementById('media-filter').value;
      clearTimeout(mediaFilterTimer);
      mediaFilterTimer = setTimeout(() => loadMediaPage(true).then(saveMediaState), 150);
    }

    function initMediaListSearch() {
      const form = document.getElementById('media-form'), q = document.getElementById('media-q');
      document.querySelectorAll('#media-mode .seg-btn').forEach(b => { b.onclick = () => setMediaListMode(b.dataset.mode); });
      document.getElementById('media-list').addEventListener('click', openMediaHit);
      q.addEventListener('compositionstart', () => { isComposing = true; });
      q.addEventListener('compositionend', () => { isComposing = false; justConfirmed = true; setTimeout(() => { justConfirmed = false; }, 60); });
      q.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.isComposing || e.keyCode === 229 || isComposing || justConfirmed)) e.preventDefault(); });
      q.addEventListener('input', () => {
        document.getElementById('media-filter').value = q.value;
        // An emptied box shows the works again
        if (!q.value.trim() && mediaHitsQ && !isComposing) runMediaHits('');
      });
      form.onsubmit = e => { e.preventDefault(); if (!isComposing && !justConfirmed) runMediaHits(q.value.trim()); };
      form.querySelectorAll('input[type=checkbox]').forEach(el => {
        el.onchange = () => {
          el.closest('.exact-chip').classList.toggle('on', el.checked);
          if (q.value.trim()) runMediaHits(q.value.trim()); else saveMediaState();
        };
      });
    }
    function runMediaHits(text) {
      mediaHitsQ = text;
      mediaListTop();
      loadMediaPage(true).then(saveMediaState);
    }
    function showMediaListMode() {
      const title = mediaListMode === 'title';
      document.getElementById('media-filter').hidden = !title;
      document.getElementById('media-form').hidden = title;
      document.getElementById('media-sort').hidden = !title;
      document.querySelectorAll('#media-mode .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mediaListMode));
      fitDockedRow();
    }
    function setMediaListMode(mode) {
      if (mode === mediaListMode) return;
      mediaListMode = mode === 'content' ? 'content' : 'title';
      store.set('mediaListMode', mediaListMode);
      showMediaListMode();
      const box = document.getElementById(mediaListMode === 'title' ? 'media-filter' : 'media-q');
      box.focus();
      const text = box.value.trim();
      // Nothing typed and no hits shown: the same list in either mode, nothing to load again
      if (!text && !mediaHitsQ) { saveMediaState(); return; }
      if (mediaListMode === 'title') { mediaHitsQ = ''; mediaListTop(); loadMediaPage(true).then(saveMediaState); }
      else runMediaHits(text);
    }
    function mediaListOptions() {
      return { exact: !!document.getElementById('media-exact')?.checked, rubyOnly: !!document.getElementById('media-ruby-only')?.checked };
    }
    function setMediaListOptions(exact, rubyOnly) {
      for (const [id, on] of [['media-exact', exact], ['media-ruby-only', rubyOnly]]) {
        const cb = document.getElementById(id);
        if (!cb) continue;
        cb.checked = !!on;
        cb.closest('.exact-chip').classList.toggle('on', !!on);
      }
    }

    function mediaPathBar(crumbs, backHref, reveal = '') {
      const parts = crumbs.map((c, i) => i < crumbs.length - 1
        ? `<a class="path-part" href="${esc(c.href)}" draggable="false">${esc(c.label)}</a>`
        : `<span class="path-current"><span class="path-part path-here" aria-current="page">${esc(c.label)}</span><span class="path-reveal">${reveal}</span></span>`);
      const next = pathTrail(crumbs);
      const forward = next
        ? `<a class="path-back" href="${esc(next)}" draggable="false" aria-label="${esc(t('path_forward'))}" title="${esc(t('path_forward'))}">→</a>`
        : `<button type="button" class="path-back" aria-label="${esc(t('path_forward'))}" title="${esc(t('path_forward'))}" disabled>→</button>`;
      return `<div class="path-bar"><a class="path-back" href="${esc(backHref)}" draggable="false" aria-label="${esc(t('path_back'))}" title="${esc(t('path_back'))}">←</a>${forward}<nav class="path-crumbs" aria-label="${esc(t('path_label'))}">${parts.join('<span class="path-sep" aria-hidden="true">›</span>')}</nav></div>`;
    }

    function pathTrail(crumbs) {
      const here = location.pathname + location.search;
      const chain = [...crumbs.slice(0, -1).map(c => c.href), here];
      let trail = [];
      try { trail = JSON.parse(sessionStorage.getItem('aobana_path_trail') || '[]'); } catch (e) {}
      const onTrail = Array.isArray(trail) && trail.length >= chain.length && chain.every((href, i) => trail[i] === href);
      if (!onTrail) trail = chain;
      try { sessionStorage.setItem('aobana_path_trail', JSON.stringify(trail)); } catch (e) {}
      return trail[chain.length] || '';
    }

    function takeOpenTarget() {
      const keys = ['at', 'at_file', 'at_offset', 'at_note'];
      if (!keys.some(k => PARAMS.has(k))) return null;
      const at = { rowid: PARAMS.get('at') || '', file: PARAMS.get('at_file') || '',
        offset: parseInt(PARAMS.get('at_offset') || '0', 10) || 0, note: PARAMS.get('at_note') || '' };
      const url = new URL(window.location);
      keys.forEach(k => url.searchParams.delete(k));
      history.replaceState(null, '', url);
      return at;
    }
    function showOpenNote(at, place) {
      if (at && (at.note === 'line_gone' || at.note === 'file_gone'))
        place.insertAdjacentHTML('beforebegin', `<div class="notice reader-notice">${esc(t('reader_' + at.note))}</div>`);
    }
    function goToTargetLine(line) {
      for (let d = line.closest('details'); d; d = d.parentElement.closest('details')) d.open = true;
      line.classList.add('reader-target');
      line.scrollIntoView({ block: 'center' });
    }
    async function openMediaTarget(at) {
      const results = document.getElementById('results');
      showOpenNote(at, results);
      const header = at.file && [...results.querySelectorAll('.episode-header')].find(h => h.dataset.file === encodeURIComponent(at.file));
      if (!header) return;
      for (let d = header.closest('details'); d; d = d.parentElement.closest('details')) { d.open = true; mediaGroupState.set(d.dataset.group, true); }
      const rowid = at.note ? '' : at.rowid;
      await expandEpisode(header, rowid ? Math.max(0, at.offset - 200) : 0);
      const line = rowid && header.parentElement.querySelector(`.episode-line[data-rowid="${CSS.escape(rowid)}"]`);
      if (line) goToTargetLine(line);
      // Centred as a line is: at the top the pinned bar and its docked rows covered the file's name
      else header.scrollIntoView({ block: 'center' });
    }

    function customUrl(category, path, file, returnPath) {
      const p = new URLSearchParams({ tab: 'media', media: 'custom', folder: category, custom_path: path });
      if (file) p.set('custom_file', file);
      if (file && returnPath) p.set('custom_return', returnPath);
      return '/?' + p.toString();
    }


    // The 保存 tab opens Reading mode on the work's own page: the place goes ahead in the session,
    // the page opens it once loaded, and the list stays hidden meanwhile (rm-booting)
    function jumpToReadingMode(jump) {
      if (!rmSupportsMedia(jump.media) || !jump.folder) return;
      try {
        sessionStorage.setItem('aobana_rm_jump', JSON.stringify(jump));
        sessionStorage.setItem('aobana_rm_open', '1');
      } catch (e) {}
      window.location.href = jump.media === 'custom'
        ? customUrl(jump.folder.split('/')[0], jump.folder)
        : '/?' + new URLSearchParams({ tab: 'media', folder: jump.folder, media: jump.media });
    }
    function takeReadingJump(media, folder) {
      try {
        const j = JSON.parse(sessionStorage.getItem('aobana_rm_jump') || 'null');
        if (!j || j.folder !== folder || (media !== 'all' && j.media !== media)) return null;
        sessionStorage.removeItem('aobana_rm_jump');
        return j;
      } catch (e) { return null; }
    }

    async function initMediaDetail(folder, clean) {
      const at = takeOpenTarget();
      const rmJump = takeReadingJump(MEDIAS_ALL.includes(PARAMS.get('media')) ? PARAMS.get('media') : 'all', folder);
      setTitle(folder);
      document.getElementById('media-body').hidden = true;
      const head = document.getElementById('media-detail');
      head.hidden = false;
      head.after(document.getElementById('main-loading'), document.getElementById('results'));
      document.getElementById('results').classList.add('media-reader');
      const media = MEDIAS_ALL.includes(PARAMS.get('media')) ? PARAMS.get('media') : 'all';
      mediaDetailFolder = folder;
      mediaDetailMedia = media;
      mediaDetailContentActive = false;
      head.innerHTML = `${mediaPathBar([{ label: t('back_media'), href: '/?tab=media' }, { label: folder }], '/?tab=media', revealIconHTML(media, '', folder))}<h1>${esc(folder)}</h1><div id="media-detail-meta"></div>
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
              <input type="checkbox" id="media-detail-exact" onchange="onMediaDetailOptionChange()">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>
              <span>${esc(t('exact'))}</span>
            </label>
            <label class="exact-chip" id="media-detail-ruby-only-chip" title="${esc(t('ruby_only_title'))}">
              <input type="checkbox" id="media-detail-ruby-only" onchange="onMediaDetailOptionChange()">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>
              <span>${esc(t('ruby_only'))}</span>
            </label>
          </form>
          <div class="seg" id="media-detail-seg">
            <button type="button" class="seg-btn ${mediaDetailMode === 'title' ? 'active' : ''}" data-mode="title" onclick="setMediaDetailMode('title')">${esc(t('media_mode_title'))}</button>
            <button type="button" class="seg-btn ${mediaDetailMode === 'content' ? 'active' : ''}" data-mode="content" onclick="setMediaDetailMode('content')">${esc(t('media_mode_content'))}</button>
          </div>
        </div>`;
      watchDockRow(head.querySelector('.path-bar'), head.querySelector('.media-detail-search'));
      fitDockedRow();
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
      const libReq = fetchMedia(new URLSearchParams({ folder, media }), undefined, st => {
        if (st.requires_index || st.requires_tables) throw new Error('no counts before an index');
      }).catch(() => null);
      const showLib = lib => {
        const it = ((lib && lib.items) || [])[0];
        if (!it || mediaDetailFolder !== folder || !document.getElementById('media-detail-meta')) return;
        if (it.media && mediaDetailMedia === 'all') {
          mediaDetailMedia = it.media;
          const fEl = document.getElementById('media-detail-filter');
          if (fEl) fEl.placeholder = t('media_detail_filter_' + it.media);
        }
        document.getElementById('media-detail-meta').innerHTML =
          `${it.author ? `<div class="muted">${esc(it.author)}</div>` : ''}<div class="media-detail-meta-row"><div class="media-stats">${statPills(it)}</div>${rmEntryButtonHTML(it.media, folder)}</div>`;
        head.querySelector('.path-reveal').innerHTML = revealIconHTML(it.media, '', folder);
        rmRefreshEntryButton(it.media, folder);
      };
      try {
        const [ep, lib] = await Promise.all([
          fetch(`/api/episodes?folder=${encodeURIComponent(folder)}&media=${encodeURIComponent(media)}`).then(r => r.json()),
          media === 'all' ? libReq : null,
        ]);
        if (media === 'all') showLib(lib);
        else libReq.then(showLib);
        mediaDetailFiles = ep.files || [];
        renderEpisodesList(mediaDetailFiles);
        const state = readMediaState();
        if (rmJump) {
          document.getElementById('main-loading').style.display = 'none';
          await openReadingMode(rmJump);
        } else if (at) {
          document.getElementById('main-loading').style.display = 'none';
          await openMediaTarget(at);
        } else if (state && state.url === mediaUrl()) {
          document.getElementById('main-loading').style.display = 'none';
          await restoreMediaState(clean ? withoutSearch(state) : state);
        }
        saveMediaState();
      } catch (e) {
        document.getElementById('results').innerHTML = `<div class="error-text">${esc(t('load_failed'))}</div>`;
      } finally {
        document.documentElement.classList.remove('rm-booting');
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
      fitDockedRow();
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
        const qVal = qEl ? qEl.value.trim() : '';
        if (qVal) {
          runMediaDetailContentSearch(qVal, mediaDetailOptions());
        } else {
          renderEpisodesList(mediaDetailFiles);
        }
        if (qEl) qEl.focus();
      }
      saveMediaState();
    }

    function onMediaDetailTitleInput() {
      const filterEl = document.getElementById('media-detail-filter');
      const qEl = document.getElementById('media-detail-q');
      if (filterEl && qEl) qEl.value = filterEl.value;
      filterMediaDetailTitles(filterEl ? filterEl.value : '');
      saveMediaState();
    }

    function filterMediaDetailTitles(rawNeedle) {
      const needle = foldTitleFilter((rawNeedle || '').trim());
      if (!needle) {
        renderEpisodesList(mediaDetailFiles);
        return;
      }
      const matched = mediaDetailFiles.filter(it => foldTitleFilter(it.title).includes(needle) || foldTitleFilter(it.file).includes(needle));
      if (!matched.length) {
        document.getElementById('results').innerHTML = `<div class="status-line" style="padding:2em;">${esc(t('media_none'))}</div>`;
        return;
      }
      renderEpisodesList(matched, rawNeedle.trim());
    }

    function onMediaDetailContentInput(input) {
      const filterEl = document.getElementById('media-detail-filter');
      if (filterEl) filterEl.value = input.value;
      if (!input.value.trim() && mediaDetailContentActive) {
        clearMediaDetailContentSearch();
      }
    }

    function mediaDetailOptions() {
      const exactEl = document.getElementById('media-detail-exact');
      const rubyEl = document.getElementById('media-detail-ruby-only');
      return { exact: !!(exactEl && exactEl.checked), rubyOnly: !!(rubyEl && rubyEl.checked) };
    }

    function setMediaDetailOptions(exact, rubyOnly) {
      for (const [id, on] of [['media-detail-exact', exact], ['media-detail-ruby-only', rubyOnly]]) {
        const cb = document.getElementById(id);
        const chip = document.getElementById(id + '-chip');
        if (cb) cb.checked = !!on;
        if (chip) chip.classList.toggle('on', !!on);
      }
    }

    function onMediaDetailOptionChange() {
      const opts = mediaDetailOptions();
      setMediaDetailOptions(opts.exact, opts.rubyOnly);
      const qEl = document.getElementById('media-detail-q');
      const qVal = qEl ? qEl.value.trim() : '';
      if (qVal) runMediaDetailContentSearch(qVal, opts);
    }

    function onMediaDetailContentSubmit(e) {
      e.preventDefault();
      if (isComposing || justConfirmed) return;
      const qEl = document.getElementById('media-detail-q');
      const qVal = qEl ? qEl.value.trim() : '';
      if (!qVal) {
        clearMediaDetailContentSearch();
        return;
      }
      runMediaDetailContentSearch(qVal, mediaDetailOptions());
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
                ${episodeHeaderHTML(item)}
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
          if (data.busy) { sentinel.innerHTML = busyLine('1em'); return; }
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

    async function runMediaDetailContentSearch(q, { exact = false, rubyOnly = false } = {}) {
      if (mediaDetailSentinelObs) mediaDetailSentinelObs.disconnect();
      if (mediaDetailCtrl) { mediaDetailCtrl.abort(); cancelServerSearch(0); }
      mediaDetailCtrl = new AbortController();
      store.del('aobana_last_search');
      const gen = ++mediaDetailGen;
      const resultsContainer = document.getElementById('results');
      resultsContainer.innerHTML = '';
      document.getElementById('main-loading').style.display = 'flex';
      const qs = new URLSearchParams({
        q,
        origin: 'media',
        folder: mediaDetailFolder,
        media: mediaDetailMedia,
        sort: 'chrono',
        limit: String(MEDIA_DETAIL_PAGE),
        offset: '0',
      });
      if (exact) qs.set('exact', 'on');
      if (rubyOnly) qs.set('ruby_only', 'on');
      startSearchEta(qs.toString(), gen, () => mediaDetailGen);
      serverSearchInFlight++;
      try {
        const res = await fetch(apiSearchUrl(qs.toString()), { signal: mediaDetailCtrl.signal });
        const data = await res.json();
        if (gen !== mediaDetailGen || data.aborted) return;
        if (data.busy) { resultsContainer.innerHTML = busyLine('2em'); return; }
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

    function episodeHeaderHTML(item, mark = '') {
      const safeFile = encodeURIComponent(item.file);
      const readBtn = rmSupportsMedia(mediaDetailMedia)
        ? `<button type="button" class="rm-row-btn" data-file="${safeFile}" onclick="event.stopPropagation(); rmOpenFromRow(this)" title="${esc(t('rm_from_here'))}" aria-label="${esc(t('rm_from_here'))}">${rmBookSvg()}</button>`
        : '';
      return `<div class="episode-header" data-file="${safeFile}" onclick="expandEpisode(this)">
                    <div class="episode-title">${markTitle(item.title, mark)}</div>
                    ${item.lines === 0 ? `<span class="muted">${esc(t('media_no_dialogue'))}</span>` : ''}
                    ${readBtn}
                    ${mediaDetailMedia === 'epub' ? '' : revealIconHTML(mediaDetailMedia, item.file)}
                    <div class="episode-toggle-icon">▼</div>
                </div>`;
    }

    function renderEpisodesList(filesList, filtering = false) {
      const resultsContainer = document.getElementById('results');
      // `filtering` is the title filter's text when one is typed, marked in each title
      const mark = typeof filtering === 'string' ? filtering : '';
      function episodeHTML(item) {
         const fileHash = btoa(unescape(encodeURIComponent(item.file))).substring(0, 32).replace(/=/g, '');
         return `
            <div class="card episode-card collapsed" id="ep-card-${fileHash}">
                ${episodeHeaderHTML(item, mark)}
                <div class="episode-content"></div>
            </div>`;
      }
      const root = { entries: [], folders: new Map(), count: 0 };
      for (const item of filesList) {
        let node = root;
        const group = item.subtitle_group || (item.book_folder && { kind: 'book', label: item.book_folder });
        const nameParts = group && group.kind !== 'other' ? [group.label] : [];
        for (const name of nameParts) {
          if (!node.folders.has(name)) {
            const key = group.kind === 'book' ? 'book:' + name : group.kind + ':' + group.order;
            const shown = group.kind === 'season' ? t('group_season', { n: group.order })
              : group.kind === 'movie' ? t('group_movie') : group.kind === 'ova' ? t('group_ova')
              : group.kind === 'special' ? t('group_special') : name;
            const child = { name: shown, key, order: group.order, book: group.kind === 'book', entries: [], folders: new Map(), count: 0 };
            node.folders.set(name, child);
            node.entries.push(child);
          }
          node = node.folders.get(name);
          node.count++;
        }
        node.entries.push(item);
      }
      const singleGroup = root.entries.filter(entry => entry.entries).length === 1;
      function folderHTML(node) {
        return node.entries.sort((a, b) => (a.order ?? 1003) - (b.order ?? 1003)).map(entry => {
          if (!entry.entries) return episodeHTML(entry);
          const open = filtering || (mediaGroupState.has(entry.key) ? mediaGroupState.get(entry.key) : singleGroup);
          if (!filtering) mediaGroupState.set(entry.key, open);
          return `<details class="media-subfolder" data-group="${esc(entry.key)}" ${open ? 'open' : ''}>
            <summary><span class="media-subfolder-arrow" aria-hidden="true">▸</span><span>${esc(entry.name)}</span>
              <span class="media-subfolder-count">${esc(t(entry.book ? 'stat_chaps' : 'stat_eps', { n: fmt(entry.count) }))}</span></summary>
            <div class="media-subfolder-content">${folderHTML(entry)}</div></details>`;
        }).join('');
      }
      let html = folderHTML(root);
      html += '<div style="height: 4em; width: 100%;"></div>';
      resultsContainer.innerHTML = html;
      if (!filtering) resultsContainer.querySelectorAll('.media-subfolder').forEach(group => {
        group.addEventListener('toggle', () => {
          if (!group.isConnected) return;
          mediaGroupState.set(group.dataset.group, group.open);
          saveMediaState();
        });
      });
      hasMoreResults = false;
      if (loadMoreObserver) loadMoreObserver.disconnect();
    }

    async function expandEpisode(header, start = 0) {
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
                   const response = await fetch(apiSearchUrl(`folder=${encodeURIComponent(folder)}&file=${fileEnc}&media=${encodeURIComponent(media)}&sort=chrono&limit=500&offset=${start}`));
                   const data = await response.json();
                   if (data.busy) { content.innerHTML = busyLine('1.5em'); card.dataset.busy = '1'; return; }
                   if (!response.ok || data.aborted) throw new Error('Episode request failed');
                   content.innerHTML = (data.results || []).length ? renderBrowseLinesHTML(data.results)
                       : `<div class="status-line" style="padding:1.5em;">${esc(t('media_no_dialogue'))}</div>`;
                   card.dataset.start = String(start);
                   if (start > 0) {
                       content.insertAdjacentHTML('afterbegin', `<div class="ep-sentinel-up" data-file="${fileEnc}" data-offset="${start}" style="height:1px;"></div>`);
                       epUpObserver.observe(content.firstElementChild);
                   }
                   if (data.has_more) {
                       const sentinelHtml = `<div class="ep-sentinel" data-file="${fileEnc}" data-offset="${start + 500}" style="height:1px;"></div>`;
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
           if (card.dataset.busy) { delete card.dataset.busy; content.innerHTML = ''; }
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
           if (data.busy) { sentinel.innerHTML = busyLine('1.5em'); delete sentinel.dataset.loading; return; }
           if (!response.ok || data.aborted) throw new Error('Episode request failed');
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

    async function loadEarlierLines(sentinel) {
       if (!sentinel.isConnected || sentinel.dataset.loading) return;
       sentinel.dataset.loading = '1';
       const content = sentinel.parentElement, card = content.parentElement;
       const end = parseInt(sentinel.dataset.offset, 10), from = Math.max(0, end - 500);
       const folder = PARAMS.get('folder');
       const media = PARAMS.get('media') || 'all';
       try {
           const response = await fetch(apiSearchUrl(`folder=${encodeURIComponent(folder)}&file=${sentinel.dataset.file}&media=${encodeURIComponent(media)}&sort=chrono&limit=${end - from}&offset=${from}`));
           const data = await response.json();
           if (data.busy || !response.ok || data.aborted) { delete sentinel.dataset.loading; return; }
           epUpObserver.unobserve(sentinel);
           const box = document.createElement('div');
           box.innerHTML = (from > 0 ? `<div class="ep-sentinel-up" data-file="${sentinel.dataset.file}" data-offset="${from}" style="height:1px;"></div>` : '')
               + renderBrowseLinesHTML(data.results || []);
           // A manga page that runs across the join keeps one page mark
           let anchor = sentinel.nextElementSibling;
           const marks = box.querySelectorAll('.page-mark');
           const twice = anchor && anchor.classList.contains('page-mark') && marks.length && marks[marks.length - 1].textContent === anchor.textContent;
           const keep = twice ? anchor.nextElementSibling : anchor;
           const before = keep ? keep.getBoundingClientRect().top : 0;
           if (twice) anchor.remove();
           const first = box.firstElementChild;
           sentinel.replaceWith(...box.childNodes);
           card.dataset.start = String(from);
           if (keep) window.scrollBy(0, keep.getBoundingClientRect().top - before);
           if (from > 0 && first && first.classList.contains('ep-sentinel-up')) epUpObserver.observe(first);
           saveMediaState();
       } catch (e) { delete sentinel.dataset.loading; }
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
              <div class="episode-line" data-rowid="${r.rowid}">
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

    const RM_ENABLED_MEDIA = new Set(['epub', 'subs', 'manga', 'custom']);
    // A part laid out from HTML sections: a book read from its file, and a Custom file.
    function rmHtmlPart(part) {
      return !!part && part.source === 'file' && (part.media === 'epub' || part.media === 'custom');
    }
    const RM_PREFS_KEY = 'aobana_reader_prefs';
    const RM_DEFAULT_PREFS = {
      theme: 'app',
      font_size: 20,
      font_weight: 400,
      line_height: 1.85,
      font_family: '',
      max_width: 44,
      max_height: 36,
      image_scale: 80,
      furigana: 'on',
      writing_mode: 'auto',
      layout: 'paginated',
      sub_timestamps: false,
      manga_boxes: 'hover',
      manga_layout: 'single',
      edge_click_nav: true,
      edge_click_width: 12,
      show_progress: true,
      auto_hide_bar: false,
      hide_bar_scroll: false,
    };

    // Subtitles, books and manga keep their own display settings.
    const rmPrefsCache = {};
    function rmPrefsMedia(media) {
      return RM_ENABLED_MEDIA.has(media) ? media : (RM_ENABLED_MEDIA.has(rmState.media) ? rmState.media : 'epub');
    }
    // Subtitles scroll by default; the rest turn pages.
    function rmDefaultPrefs(m) {
      return m === 'subs' ? { ...RM_DEFAULT_PREFS, layout: 'continuous' } : { ...RM_DEFAULT_PREFS };
    }
    function rmSetPrefsCache(media, prefs) {
      const m = rmPrefsMedia(media);
      rmPrefsCache[m] = { ...rmDefaultPrefs(m), ...prefs };
      store.set(`${RM_PREFS_KEY}_${m}`, JSON.stringify(rmPrefsCache[m]));
    }
    function rmSupportsMedia(media) {
      return RM_ENABLED_MEDIA.has(media);
    }
    function rmBookSvg() {
      return svgIcon('<path d="M2 5.5A2.5 2.5 0 0 1 4.5 3H11v17H4.5A2.5 2.5 0 0 0 2 22z"/><path d="M22 5.5A2.5 2.5 0 0 0 19.5 3H13v17h6.5a2.5 2.5 0 0 1 2.5 2z"/>');
    }
    // The font: "" is the bundled Noto Sans JP, "serif" the device's Mincho; any other is an installed family.
    const RM_FONT_FALLBACK = "'Noto Sans JP', 'Aobana Sans', 'Hiragino Kaku Gothic ProN', 'Yu Gothic', Meiryo, sans-serif";
    const RM_DEVICE_FONTS = [
      { family: 'Hiragino Mincho ProN', name_ja: 'ヒラギノ明朝 ProN' },
      { family: 'Hiragino Sans', name_ja: 'ヒラギノ角ゴシック' },
      { family: 'Hiragino Maru Gothic ProN', name_ja: 'ヒラギノ丸ゴ ProN' },
      { family: 'Noto Serif CJK JP', name_ja: '' },
      { family: 'Noto Sans CJK JP', name_ja: '' },
      { family: 'Source Han Serif JP', name_ja: '源ノ明朝 JP' },
      { family: 'Source Han Sans JP', name_ja: '源ノ角ゴシック JP' },
    ];
    function rmFontName(family) {
      return (typeof family === 'string' && family && family !== 'mincho' && family !== 'gothic'
        && !/["'\\;{}<>\u0000-\u001f]/.test(family)) ? family : '';
    }
    function rmFontStack(family) {
      const f = rmFontName(family);
      if (!f) return RM_FONT_FALLBACK;
      if (f === 'serif') return 'serif';
      return `"${f}", ${RM_FONT_FALLBACK}`;
    }
    // The server lists the computer's Japanese fonts; the browser keeps those it can draw and
    // merges known phone/Mac families it can draw so a phone still has variety.
    let rmFontList = null;
    let rmFontListLoading = null;
    let rmDeviceFontsCache = null;
    let rmFontPopupState = null;
    let rmFontEventsBound = false;
    function rmFontCanvasCtx() {
      if (rmFontCanvasCtx.ctx !== undefined) return rmFontCanvasCtx.ctx;
      try {
        const cv = document.createElement('canvas');
        cv.width = 200;
        cv.height = 44;
        rmFontCanvasCtx.ctx = cv.getContext('2d', { willReadFrequently: true }) || cv.getContext('2d');
      } catch (e) {
        rmFontCanvasCtx.ctx = null;
      }
      return rmFontCanvasCtx.ctx;
    }
    function rmFontFingerprint(fontCss) {
      const ctx = rmFontCanvasCtx();
      if (!ctx) return null;
      const sample = 'あ永漢の明ゴ';
      ctx.clearRect(0, 0, 200, 44);
      ctx.fillStyle = '#000';
      ctx.textBaseline = 'top';
      ctx.font = fontCss;
      const w = Math.round(ctx.measureText(sample).width * 10);
      ctx.fillText(sample, 2, 6);
      try {
        const data = ctx.getImageData(0, 0, 200, 44).data;
        let h1 = 0x811c9dc5;
        let h2 = 0x01000193;
        for (let i = 3; i < data.length; i += 4) {
          const a = data[i];
          h1 = Math.imul(h1 ^ a, 0x01000193) >>> 0;
          h2 = Math.imul(h2 ^ (a + (i & 255)), 0x85ebca6b) >>> 0;
        }
        return `${w}:${h1.toString(16)}:${h2.toString(16)}`;
      } catch (e) {
        return null;
      }
    }
    function rmFontDrawable(family) {
      const ctx = rmFontCanvasCtx();
      if (!ctx) return false;
      const sample = 'mmmmlli WQ.,あア漢永の';
      const shape = font => {
        const fp = rmFontFingerprint(font);
        if (fp) return fp;
        ctx.font = font;
        const m = ctx.measureText(sample);
        return `${m.width}|${m.actualBoundingBoxAscent}|${m.actualBoundingBoxDescent}`;
      };
      // The three generic families draw the same all page long: drawn once, not once per font
      const baseShape = base => {
        if (!rmFontBaseShapes.has(base)) rmFontBaseShapes.set(base, shape(`28px ${base}`));
        return rmFontBaseShapes.get(base);
      };
      return ['monospace', 'serif', 'sans-serif'].some(base => shape(`28px "${family}", ${base}`) !== baseShape(base));
    }
    const rmFontBaseShapes = new Map();
    function rmMergeFonts(serverFonts) {
      const seen = new Map();
      const drawnHashes = new Set();
      const defFp = rmFontFingerprint(`28px ${RM_FONT_FALLBACK}`);
      const serFp = rmFontFingerprint('28px serif');
      if (defFp) drawnHashes.add(defFp);
      if (serFp) drawnHashes.add(serFp);
      const add = f => {
        const fam = rmFontName(f && f.family);
        if (!fam) return;
        const key = fam.toLowerCase();
        if (key === 'noto sans jp' || key === 'serif') return;
        const prev = seen.get(key);
        if (prev) {
          if (!prev.name_ja && f.name_ja) prev.name_ja = f.name_ja;
          return;
        }
        if (!rmFontDrawable(fam)) return;
        const fp = rmFontFingerprint(`28px ${rmFontStack(fam)}`);
        if (fp) {
          if (drawnHashes.has(fp)) return;
          drawnHashes.add(fp);
        }
        seen.set(key, { family: fam, name_ja: f.name_ja || '' });
      };
      for (const f of (serverFonts || [])) add(f);
      for (const f of RM_DEVICE_FONTS) add(f);
      // Two weights can share one Japanese name (新字源 明朝 W3 and W7): those show their own names.
      const jaCount = new Map();
      for (const f of seen.values()) if (f.name_ja) jaCount.set(f.name_ja, (jaCount.get(f.name_ja) || 0) + 1);
      for (const f of seen.values()) if (f.name_ja && jaCount.get(f.name_ja) > 1) f.name_ja = '';
      return Array.from(seen.values()).sort((a, b) => {
        const ak = a.family.toLowerCase(), bk = b.family.toLowerCase();
        return ak < bk ? -1 : (ak > bk ? 1 : 0);
      });
    }
    function rmDeviceFontsReady() {
      if (!rmDeviceFontsCache) rmDeviceFontsCache = rmMergeFonts([]);
      return rmDeviceFontsCache;
    }
    function rmLoadFonts() {
      if (rmFontList || rmFontListLoading) return rmFontListLoading;
      const fontsReady = (document.fonts && document.fonts.ready)
        ? Promise.race([
          Promise.all([
            document.fonts.load ? document.fonts.load('28px "Aobana Sans"').catch(() => {}) : Promise.resolve(),
            document.fonts.ready.catch(() => {}),
          ]),
          new Promise(r => setTimeout(r, 1500)),
        ])
        : Promise.resolve();
      rmFontListLoading = Promise.all([
        fetch('/api/reading/fonts').then(r => r.ok ? r.json() : { fonts: [] }).catch(() => ({ fonts: [] })),
        fontsReady,
      ]).then(([data]) => {
        rmFontList = rmMergeFonts((data && data.fonts) || []);
        if (typeof renderReaderSettings === 'function') renderReaderSettings();
        if (isReadingModeOpen()) rmRenderSettingsPanel();
        return rmFontList;
      });
      return rmFontListLoading;
    }
    function rmFontOptions(current) {
      const cur = rmFontName(current);
      const fonts = (rmFontList || rmDeviceFontsReady()).slice();
      const out = [
        { value: '', label: t('rm_font_default') },
        { value: 'serif', label: t('rm_font_serif') },
      ];
      if (cur && cur !== 'serif' && !fonts.some(f => f.family === cur)) {
        out.push({ value: cur, label: cur });
      }
      for (const f of fonts) {
        out.push({ value: f.family, label: LANG === 'ja' && f.name_ja ? f.name_ja : f.family });
      }
      return out;
    }
    function rmFontLabel(val) {
      const cur = rmFontName(val);
      if (!cur) return t('rm_font_default');
      if (cur === 'serif') return t('rm_font_serif');
      const list = rmFontList || rmDeviceFontsReady();
      const hit = list.find(f => f.family === cur);
      return hit && LANG === 'ja' && hit.name_ja ? hit.name_ja : cur;
    }
    function rmFontSelectHtml(current, pickerId, media = '') {
      if (!rmFontList) rmLoadFonts();
      const cur = rmFontName(current);
      const open = !!(rmFontPopupState && rmFontPopupState.id === pickerId);
      return `<button type="button" class="rm-font-btn" data-rm-font-id="${esc(pickerId)}" data-rm-font-media="${esc(media)}" data-rm-font-val="${esc(cur)}" aria-haspopup="listbox" aria-expanded="${open ? 'true' : 'false'}" aria-controls="rm-font-popup" onclick="rmToggleFontPopup(this, event)" onkeydown="rmFontBtnKeyDown(this, event)"><span class="rm-font-btn-label" style="font-family:${esc(rmFontStack(cur))}">${esc(rmFontLabel(cur))}</span><svg class="rm-font-caret" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4z"/></svg></button>`;
    }
    function rmBindFontPopupEvents() {
      if (rmFontEventsBound) return;
      rmFontEventsBound = true;
      document.addEventListener('pointerdown', e => {
        if (!rmFontPopupState) return;
        const { popupEl, btnEl } = rmFontPopupState;
        if (popupEl && popupEl.contains(e.target)) return;
        if (btnEl && btnEl.contains(e.target)) return;
        rmCloseFontPopup(false);
      }, true);
      window.addEventListener('scroll', e => {
        if (!rmFontPopupState) return;
        const { popupEl } = rmFontPopupState;
        if (popupEl && (e.target === popupEl || popupEl.contains(e.target))) return;
        rmPositionFontPopup();
      }, { capture: true, passive: true });
      window.addEventListener('resize', () => {
        if (rmFontPopupState) rmPositionFontPopup();
      }, { passive: true });
      document.addEventListener('keydown', e => {
        if (!rmFontPopupState) return;
        const st = rmFontPopupState;
        const n = st.options.length;
        if (e.key === 'Escape') {
          e.preventDefault();
          e.stopPropagation();
          rmCloseFontPopup(true);
          return;
        }
        if (e.key === 'Tab') {
          rmCloseFontPopup(false);
          return;
        }
        if (!n) return;
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          e.stopPropagation();
          rmSetFontActive(Math.min(n - 1, st.activeIndex + 1));
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          e.stopPropagation();
          rmSetFontActive(Math.max(0, st.activeIndex - 1));
        } else if (e.key === 'Home') {
          e.preventDefault();
          e.stopPropagation();
          rmSetFontActive(0);
        } else if (e.key === 'End') {
          e.preventDefault();
          e.stopPropagation();
          rmSetFontActive(n - 1);
        } else if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.stopPropagation();
          const chosen = st.options[st.activeIndex];
          if (chosen) rmPickFontOption(chosen.value);
        }
      }, true);
    }
    function rmFontBtnKeyDown(btn, e) {
      if (rmFontPopupState) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        e.stopPropagation();
        rmOpenFontPopup(btn);
      }
    }
    function rmToggleFontPopup(btn, e) {
      if (e) e.stopPropagation();
      const id = btn.getAttribute('data-rm-font-id') || '';
      if (rmFontPopupState && rmFontPopupState.id === id) {
        rmCloseFontPopup(true);
        return;
      }
      rmOpenFontPopup(btn);
    }
    function rmRenderFontPopupOptions(st, keepScroll = false) {
      const prevScroll = keepScroll && st.popupEl ? st.popupEl.scrollTop : 0;
      const cur = rmFontName(st.btnEl ? st.btnEl.getAttribute('data-rm-font-val') : '');
      const opts = rmFontOptions(cur);
      st.options = opts;
      let selIdx = opts.findIndex(o => o.value === cur);
      if (selIdx < 0) selIdx = 0;
      if (!keepScroll || st.activeIndex < 0 || st.activeIndex >= opts.length) st.activeIndex = selIdx;
      st.popupEl.innerHTML = opts.map((o, i) =>
        `<button type="button" class="rm-font-opt${i === st.activeIndex ? ' rm-font-active' : ''}" id="rm-font-opt-${i}" role="option" aria-selected="${o.value === cur ? 'true' : 'false'}" data-idx="${i}" style="font-family:${esc(rmFontStack(o.value))}">${esc(o.label)}</button>`
      ).join('');
      st.popupEl.setAttribute('aria-activedescendant', `rm-font-opt-${st.activeIndex}`);
      st.popupEl.querySelectorAll('.rm-font-opt').forEach(optEl => {
        optEl.addEventListener('click', ev => {
          ev.stopPropagation();
          const idx = Number(optEl.getAttribute('data-idx'));
          if (st.options[idx]) rmPickFontOption(st.options[idx].value);
        });
        optEl.addEventListener('pointerenter', () => {
          const idx = Number(optEl.getAttribute('data-idx'));
          if (!Number.isNaN(idx)) rmSetFontActive(idx, false);
        });
      });
      if (keepScroll) {
        st.popupEl.scrollTop = prevScroll;
      }
    }
    function rmScrollFontOptIntoView(popupEl, optEl) {
      if (!popupEl || !optEl) return;
      const top = optEl.offsetTop;
      const bottom = top + optEl.offsetHeight;
      if (top < popupEl.scrollTop) popupEl.scrollTop = top;
      else if (bottom > popupEl.scrollTop + popupEl.clientHeight) popupEl.scrollTop = bottom - popupEl.clientHeight;
    }
    function rmSetFontActive(idx, scroll = true) {
      if (!rmFontPopupState) return;
      const st = rmFontPopupState;
      st.activeIndex = idx;
      st.popupEl.querySelectorAll('.rm-font-opt.rm-font-active').forEach(el => el.classList.remove('rm-font-active'));
      const target = document.getElementById(`rm-font-opt-${idx}`);
      if (target) {
        target.classList.add('rm-font-active');
        st.popupEl.setAttribute('aria-activedescendant', target.id);
        if (scroll) rmScrollFontOptIntoView(st.popupEl, target);
      }
    }
    function rmOpenFontPopup(btn) {
      rmBindFontPopupEvents();
      if (rmFontPopupState) rmCloseFontPopup(false);
      const id = btn.getAttribute('data-rm-font-id') || '';
      const media = btn.getAttribute('data-rm-font-media') || '';
      const host = btn.closest('#reading-mode') || document.body;
      let popup = document.getElementById('rm-font-popup');
      if (popup) popup.remove();
      popup = document.createElement('div');
      popup.id = 'rm-font-popup';
      popup.className = 'rm-font-popup';
      popup.setAttribute('role', 'listbox');
      popup.setAttribute('tabindex', '-1');
      popup.setAttribute('aria-label', t('rm_font'));
      host.appendChild(popup);
      const st = { id, media, btnEl: btn, popupEl: popup, options: [], activeIndex: 0 };
      rmFontPopupState = st;
      btn.setAttribute('aria-expanded', 'true');
      rmRenderFontPopupOptions(st, false);
      rmPositionFontPopup();
      rmScrollFontOptIntoView(popup, document.getElementById(`rm-font-opt-${st.activeIndex}`));
      try { popup.focus({ preventScroll: true }); } catch (e) {}
    }
    function rmPositionFontPopup() {
      if (!rmFontPopupState) return;
      const { btnEl, popupEl } = rmFontPopupState;
      if (!btnEl || !btnEl.isConnected || btnEl.offsetParent === null) {
        rmCloseFontPopup(false);
        return;
      }
      const rect = btnEl.getBoundingClientRect();
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      if (rect.bottom <= 0 || rect.top >= vh || rect.right <= 0 || rect.left >= vw) {
        rmCloseFontPopup(false);
        return;
      }
      const scroller = btnEl.closest('.rm-settings-body');
      if (scroller) {
        const sr = scroller.getBoundingClientRect();
        if (rect.bottom <= sr.top || rect.top >= sr.bottom) {
          rmCloseFontPopup(false);
          return;
        }
      }
      const cap = Math.min(Math.floor(vh * 0.4), 320);
      const spaceBelow = vh - rect.bottom - 8;
      const spaceAbove = rect.top - 8;
      const openAbove = spaceBelow < Math.min(cap, 140) && spaceAbove > spaceBelow;
      const maxH = Math.max(80, Math.min(cap, (openAbove ? spaceAbove : spaceBelow) - 4));
      const width = Math.min(Math.max(rect.width, 220), vw - 16);
      const left = Math.max(8, Math.min(rect.left, vw - width - 8));
      popupEl.style.width = `${Math.round(width)}px`;
      popupEl.style.left = `${Math.round(left)}px`;
      popupEl.style.maxHeight = `${Math.round(maxH)}px`;
      if (openAbove) {
        popupEl.style.top = 'auto';
        popupEl.style.bottom = `${Math.round(vh - rect.top + 4)}px`;
      } else {
        popupEl.style.bottom = 'auto';
        popupEl.style.top = `${Math.round(rect.bottom + 4)}px`;
      }
    }
    function rmFontSyncOpenPopup() {
      if (!rmFontPopupState) return;
      const st = rmFontPopupState;
      const btns = document.querySelectorAll('.rm-font-btn');
      let nextBtn = null;
      for (const b of btns) {
        if (b.getAttribute('data-rm-font-id') === st.id) { nextBtn = b; break; }
      }
      if (!nextBtn || nextBtn.offsetParent === null) {
        rmCloseFontPopup(false);
        return;
      }
      st.btnEl = nextBtn;
      nextBtn.setAttribute('aria-expanded', 'true');
      const host = nextBtn.closest('#reading-mode') || document.body;
      if (st.popupEl.parentNode !== host) host.appendChild(st.popupEl);
      rmRenderFontPopupOptions(st, true);
      rmPositionFontPopup();
    }
    function rmCloseFontPopup(restoreFocus = false) {
      if (!rmFontPopupState) return;
      const { btnEl, popupEl } = rmFontPopupState;
      rmFontPopupState = null;
      if (popupEl && popupEl.parentNode) popupEl.remove();
      if (btnEl && btnEl.isConnected) {
        btnEl.setAttribute('aria-expanded', 'false');
        if (restoreFocus) {
          try { btnEl.focus({ preventScroll: true }); } catch (e) {}
        }
      }
    }
    function rmPickFontOption(val) {
      if (!rmFontPopupState) return;
      const { id, media } = rmFontPopupState;
      rmCloseFontPopup(true);
      const done = media && typeof setReaderPref === 'function'
        ? setReaderPref(media, 'font_family', val)
        : rmUpdatePrefs({ font_family: val });
      Promise.resolve(done).then(() => {
        for (const b of document.querySelectorAll('.rm-font-btn')) {
          if (b.getAttribute('data-rm-font-id') === id) {
            try { b.focus({ preventScroll: true }); } catch (e) {}
            break;
          }
        }
      });
    }
    function rmGetPrefs(media) {
      const m = rmPrefsMedia(media);
      if (rmPrefsCache[m]) return { ...rmDefaultPrefs(m), ...rmPrefsCache[m] };
      try {
        const saved = JSON.parse(store.get(`${RM_PREFS_KEY}_${m}`) || 'null');
        if (saved && typeof saved === 'object') {
          rmPrefsCache[m] = { ...rmDefaultPrefs(m), ...saved };
          return { ...rmPrefsCache[m] };
        }
      } catch (e) {}
      return rmDefaultPrefs(m);
    }
    async function rmFetchPrefs() {
      try {
        const r = await fetch('/api/reading/state');
        if (r.ok) {
          const data = await r.json();
          const all = (data && data.prefs_by_media) || {};
          for (const m of RM_ENABLED_MEDIA) if (all[m]) rmSetPrefsCache(m, all[m]);
        }
      } catch (e) {}
    }
    // Settings that leave the text where it is. The click zones are among them: on a wide window a
    // page leaves room for zones of the default width (RM_EDGE_ROOM), whatever they are set to.
    const RM_NO_RELAYOUT_KEYS = new Set(['theme', 'furigana', 'manga_boxes', 'edge_click_width', 'edge_click_nav']);
    const RM_EDGE_ROOM = 0.12;
    let rmDragAnchor = null;
    let rmDragClearTimer = null;
    function rmClearDragAnchor() {
      clearTimeout(rmDragClearTimer);
      rmDragClearTimer = null;
      rmDragAnchor = null;
    }
    async function rmUpdatePrefs(patch, opts = {}) {
      const m = rmPrefsMedia(opts.media);
      const needsRelayout = Object.keys(patch || {}).some(k => !RM_NO_RELAYOUT_KEYS.has(k));
      const anchor = (needsRelayout && isReadingModeOpen() && m === rmState.media && rmState.part)
        ? (opts.anchor || rmDragAnchor || rmLayoutAnchor())
        : null;
      if (opts.endDrag) rmClearDragAnchor();
      const next = { ...rmGetPrefs(m), ...patch };
      rmSetPrefsCache(m, next);
      try {
        const res = await apiPost('/api/reading/state', { media: m, prefs: patch });
        if (res && res.prefs) rmSetPrefsCache(m, res.prefs);
      } catch (e) {}
      if (isReadingModeOpen() && m === rmState.media) rmApplyPrefsToDom(needsRelayout, opts.rebuildSettings !== false, anchor);
      return rmGetPrefs(m);
    }

    // Back to the defaults of the media open now; the other media keep theirs.
    async function rmResetPrefs() {
      if (isReadingModeOpen() && rmState.media !== 'manga' && rmState.work && (rmState.work.writing_mode != null || rmState.work.layout != null)) {
        await rmSaveWorkOverride({ writing_mode: null, layout: null });
      }
      return rmUpdatePrefs(rmDefaultPrefs(rmPrefsMedia()));
    }

    function rmLiveRangePref(key, val, labelEl, text) {
      if (labelEl) labelEl.textContent = text;
      const needsRelayout = !RM_NO_RELAYOUT_KEYS.has(key);
      if (needsRelayout && isReadingModeOpen() && rmState.part && !rmDragAnchor) {
        rmDragAnchor = rmLayoutAnchor();
      }
      if (rmDragAnchor) {
        clearTimeout(rmDragClearTimer);
        rmDragClearTimer = setTimeout(() => { rmDragAnchor = null; }, 1200);
      }
      rmSetPrefsCache(rmState.media, { ...rmGetPrefs(), [key]: val });
      if (isReadingModeOpen()) rmApplyPrefsToDom(needsRelayout, false, rmDragAnchor);
      if (key === 'edge_click_width') rmPreviewEdgeZones();
    }

    // While クリック領域の幅 is dragged, both click zones are tinted so their reach shows.
    let rmEdgePreviewTimer = null;
    function rmPreviewEdgeZones() {
      const dlg = document.getElementById('reading-mode');
      if (!dlg) return;
      clearTimeout(rmEdgePreviewTimer);
      dlg.classList.toggle('rm-edge-preview', rmEdgeNavActive());
      rmEdgePreviewTimer = setTimeout(() => dlg.classList.remove('rm-edge-preview'), 900);
    }

    function rmEntryButtonHTML(media, folder) {
      if (!rmSupportsMedia(media) || !folder) return '';
      return `<button type="button" class="btn primary rm-entry-btn" id="rm-entry-btn" data-media="${esc(media)}" data-folder="${esc(folder)}" aria-label="${esc(t('rm_open'))}" onclick="rmOpenFromEntry(this)">${rmBookSvg()}<span>${esc(t('rm_open'))}</span></button>`;
    }

    async function rmRefreshEntryButton(media, folder) {
      if (!rmSupportsMedia(media) || !folder) return;
      try {
        const r = await fetch(`/api/reading/state?media=${encodeURIComponent(media)}&folder=${encodeURIComponent(folder)}`);
        if (!r.ok) return;
        const data = await r.json();
        if (data.prefs) rmSetPrefsCache(media, data.prefs);
        const btn = document.getElementById('rm-entry-btn');
        if (!btn || btn.dataset.folder !== folder) return;
        if (data.work && data.work.file) {
          btn.dataset.savedFile = data.work.file;
          btn.setAttribute('aria-label', t('rm_continue'));
          btn.innerHTML = `${rmBookSvg()}<span>${esc(t('rm_continue'))}</span>`;
        }
      } catch (e) {}
    }

    function rmOpenFromEntry(btn) {
      const media = btn.dataset.media;
      const folder = btn.dataset.folder;
      // Custom: a file page opens its own file, a folder page its place or first file.
      if (media === 'custom') return openReadingMode({ media, folder, file: btn.dataset.file || '' });
      const file = btn.dataset.savedFile || (mediaDetailFiles[0] && mediaDetailFiles[0].file) || '';
      if (!file) return;
      openReadingMode({ media, folder, file });
    }

    function rmOpenFromRow(btn) {
      const file = decodeURIComponent(btn.dataset.file || '');
      if (!file || !rmSupportsMedia(mediaDetailMedia)) return;
      openReadingMode({ media: mediaDetailMedia, folder: mediaDetailFolder, file, explicitStart: true });
    }

    const RM_PAGE_GAP = 40;
    const rmState = {
      open: false,
      media: '',
      folder: '',
      files: [],
      partIndex: 0,
      part: null,
      work: null,
      dir: 'horizontal',
      layout: 'continuous',
      sections: [],
      secCharStarts: [],
      secCharLens: [],
      totalPlainChars: 0,
      secIndex: 0,
      pageIndex: 0,
      pageCount: 1,
      pageW: 0,
      pageH: 0,
      mangaPage: 1,
      mangaZoom: false,
      saveTimer: null,
      chunkGen: 0,
      toastTimer: null,
      touchStart: null,
      fallbackNoticed: false,
      historySession: 0,
      historyDepth: 0,
    };

    let rmIgnorePopCount = 0;

    const RM_ANCHOR_WS_RE = /[\s\u3000\u200b]/;
    const RM_ANCHOR_SKIP_TAGS = new Set(['RT', 'RP', 'SCRIPT', 'STYLE', 'SVG', 'NOSCRIPT']);

    function rmIsLowSurrogate(c) { return c >= 0xdc00 && c <= 0xdfff; }
    function rmCountNonWs(str, limit = str.length) {
      let n = 0;
      for (let i = 0; i < limit && i < str.length; i++) {
        if (!RM_ANCHOR_WS_RE.test(str[i])) n++;
      }
      return n;
    }

    function rmRawIdxFromNonWs(str, targetNonWs) {
      let n = 0;
      for (let i = 0; i < str.length; i++) {
        if (!RM_ANCHOR_WS_RE.test(str[i])) {
          if (n >= targetNonWs) return i;
          n++;
        }
      }
      return Math.max(0, str.length - 1);
    }

    function rmCollectAnchorNodes(root) {
      const nodes = [];
      let total = 0;
      if (!root) return { nodes, total };
      const walk = (el) => {
        for (let c = el.firstChild; c; c = c.nextSibling) {
          if (c.nodeType === 3) {
            const txt = c.nodeValue || '';
            const n = rmCountNonWs(txt);
            if (n > 0) {
              nodes.push({ node: c, text: txt, nonWsLen: n, cumStart: total });
              total += n;
            }
          } else if (c.nodeType === 1) {
            if (RM_ANCHOR_SKIP_TAGS.has(c.tagName)) continue;
            if (c.classList && (c.classList.contains('rm-sent-break') || c.classList.contains('rm-sub-ts') || c.classList.contains('rm-part-nav-end'))) continue;
            walk(c);
          }
        }
      };
      walk(root);
      return { nodes, total };
    }

    function rmExtractQuoteAt(nodes, startIdx, rawIdx, maxLen = 40) {
      let out = '';
      for (let i = startIdx; i < nodes.length && out.length < maxLen; i++) {
        const chunk = (i === startIdx ? nodes[i].text.slice(rawIdx) : nodes[i].text)
          .replace(/[\r\n\t]+/g, ' ')
          .replace(/\s{2,}/g, ' ');
        out += chunk;
      }
      return out.trim().slice(0, maxLen);
    }

    // Precompute cumulative non-whitespace plain-text character counts across spine sections so
    // continuous and paginated layouts share one layout-independent 0..N coordinate space.
    function rmBuildPartCharIndex(root) {
      const part = rmState.part;
      if (!part || rmState.media === 'manga') {
        rmState.secCharStarts = [];
        rmState.secCharLens = [];
        rmState.totalPlainChars = 0;
        return;
      }
      if (rmHtmlPart(part)) {
        const starts = [];
        const lens = [];
        let acc = 0;
        if (rmState.layout === 'paginated' && rmState.sections.length) {
          for (let i = 0; i < rmState.sections.length; i++) {
            starts.push(acc);
            const doc = rmParseSafeDoc(rmState.sections[i] || '');
            const n = rmCollectAnchorNodes(doc.body).total;
            lens.push(n);
            acc += n;
          }
        } else if (root) {
          const spines = [...root.querySelectorAll(':scope > section.rm-epub-spine')]
            .filter(sec => (sec.textContent || '').trim() || sec.querySelector('img, svg, hr, table'));
          if (spines.length) {
            for (const sec of spines) {
              starts.push(acc);
              const n = rmCollectAnchorNodes(sec).total;
              lens.push(n);
              acc += n;
            }
          } else {
            starts.push(0);
            acc = rmCollectAnchorNodes(root).total;
            lens.push(acc);
          }
        }
        rmState.secCharStarts = starts;
        rmState.secCharLens = lens;
        rmState.totalPlainChars = acc;
        return;
      }
      const total = root ? rmCollectAnchorNodes(root).total : 0;
      rmState.secCharStarts = [0];
      rmState.secCharLens = [total];
      rmState.totalPlainChars = total;
    }

    function rmAnchorTopPad() {
      const dlg = document.getElementById('reading-mode');
      const bar = document.getElementById('rm-topbar');
      if (dlg && dlg.classList.contains('rm-autohide-pad') && !rmBarHidden && bar) {
        return (bar.offsetHeight || 46) + 8;
      }
      return 8;
    }

    function rmRectInViewport(r, vr, vertical, paginated, topPad) {
      if (!r || r.width < 0.2 || r.height < 0.2) return false;
      if (paginated) {
        const cx = (r.left + r.right) * 0.5;
        const cy = (r.top + r.bottom) * 0.5;
        return cx >= vr.left - 2 && cx <= vr.right + 2 && cy >= vr.top - 2 && cy <= vr.bottom + 2;
      }
      if (vertical) {
        return r.left < vr.right - 2 && r.right > vr.left + 2;
      }
      return r.bottom > vr.top + topPad && r.top < vr.bottom - 2;
    }

    function rmRectBeforeStart(r, vr, vertical, paginated, topPad) {
      if (paginated) {
        return vertical ? (r.bottom < vr.top + 2) : (r.right < vr.left + 2);
      }
      if (vertical) return r.left >= vr.right - 2;
      return r.bottom <= vr.top + topPad;
    }

    function rmReadAnchor() {
      const part = rmState.part;
      const item = rmState.files[rmState.partIndex];
      const file = (part && part.file) || (item && item.file) || '';
      if (!part) return null;
      if (rmState.media === 'manga') {
        const pages = part.pages || [];
        let page = rmState.mangaPage || 1;
        let pageFrac = 0;
        const mStage = document.getElementById('rm-manga-stage');
        if (mStage && mStage.classList.contains('rm-manga-strip')) {
          const sr = mStage.getBoundingClientRect();
          const els = mStage.querySelectorAll('[data-page]');
          for (const el of els) {
            const er = el.getBoundingClientRect();
            if (er.bottom > sr.top + 8) {
              page = parseInt(el.dataset.page || String(page), 10) || page;
              pageFrac = Math.max(0, Math.min(1, (sr.top - er.top) / Math.max(1, er.height)));
              break;
            }
          }
        }
        const ratio = pages.length > 1 ? Math.max(0, Math.min(1, (page - 1) / (pages.length - 1))) : 0;
        return {
          file,
          anchor_v: 1,
          char_offset: 0,
          sec_index: 0,
          quote: '',
          scroll_ratio: Number(ratio.toFixed(5)),
          page,
          page_frac: Number(pageFrac.toFixed(5)),
        };
      }
      const sc = rmScrollerEl();
      const root = document.getElementById('rm-epub-root');
      const fallbackRatio = rmReadScrollRatio();
      const baseOff = (rmState.layout === 'paginated' && rmState.secCharStarts[rmState.secIndex]) || 0;
      if (!sc || !root) {
        return {
          file, anchor_v: 1, char_offset: baseOff, sec_index: rmState.secIndex || 0,
          quote: '', scroll_ratio: Number(fallbackRatio.toFixed(5)), page: rmState.pageIndex + 1,
        };
      }
      const { nodes } = rmCollectAnchorNodes(root);
      if (!nodes.length) {
        return {
          file, anchor_v: 1, char_offset: baseOff, sec_index: rmState.secIndex || 0,
          quote: '', scroll_ratio: Number(fallbackRatio.toFixed(5)), page: rmState.pageIndex + 1,
        };
      }
      const vr = sc.getBoundingClientRect();
      const vertical = rmState.dir === 'vertical';
      const paginated = rmState.layout === 'paginated';
      const topPad = (!paginated && !vertical) ? rmAnchorTopPad() : 2;
      const range = document.createRange();

      let startIdx = 0;
      if (nodes.length > 200) {
        let lo = 0, hi = nodes.length - 1;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          range.selectNodeContents(nodes[mid].node);
          const mr = range.getBoundingClientRect();
          if (rmRectBeforeStart(mr, vr, vertical, paginated, topPad)) lo = mid + 1;
          else hi = mid;
        }
        startIdx = Math.max(0, lo - 4);
      }

      let hitIdx = -1;
      let hitRaw = 0;
      for (let i = startIdx; i < nodes.length; i++) {
        const entry = nodes[i];
        range.selectNodeContents(entry.node);
        const nr = range.getBoundingClientRect();
        if (rmRectBeforeStart(nr, vr, vertical, paginated, topPad)) continue;
        const rects = range.getClientRects();
        let anyVis = false;
        for (let k = 0; k < rects.length; k++) {
          if (rmRectInViewport(rects[k], vr, vertical, paginated, topPad)) { anyVis = true; break; }
        }
        if (!anyVis) {
          if (!paginated && (vertical ? nr.right < vr.left : nr.top > vr.bottom)) break;
          continue;
        }
        const txt = entry.text;
        let lo = 0, hi = txt.length - 1;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          // An Ext-B kanji or emoji is two code units: measured whole, never by one half
          const at = mid > 0 && rmIsLowSurrogate(txt.charCodeAt(mid)) ? mid - 1 : mid;
          range.setStart(entry.node, at);
          range.setEnd(entry.node, Math.min(txt.length, at + (txt.codePointAt(at) > 0xffff ? 2 : 1)));
          const cr = range.getBoundingClientRect();
          if (rmRectBeforeStart(cr, vr, vertical, paginated, topPad)) lo = mid + 1;
          else hi = mid;
        }
        let raw = lo > 0 && rmIsLowSurrogate(txt.charCodeAt(lo)) ? lo - 1 : lo;
        while (raw < txt.length && RM_ANCHOR_WS_RE.test(txt[raw])) raw++;
        if (raw >= txt.length) continue;
        hitIdx = i;
        hitRaw = raw;
        break;
      }

      if (hitIdx < 0) {
        hitIdx = Math.min(nodes.length - 1, startIdx);
        hitRaw = rmRawIdxFromNonWs(nodes[hitIdx].text, 0);
      }

      const hitEntry = nodes[hitIdx];
      const localNonWs = rmCountNonWs(hitEntry.text, hitRaw);
      const charOffset = baseOff + hitEntry.cumStart + localNonWs;
      const total = rmState.totalPlainChars || (part.char_count || 0);
      const ratio = total > 0 ? Math.max(0, Math.min(1, charOffset / total)) : fallbackRatio;
      const quote = rmExtractQuoteAt(nodes, hitIdx, hitRaw, 40);
      // In a scrolled layout the anchor also keeps how far its character sat from the leading edge,
      // so a return lands on the same pixel, not a column or line away.
      let edge = null;
      if (!paginated) {
        range.setStart(hitEntry.node, hitRaw);
        range.setEnd(hitEntry.node, Math.min(hitEntry.text.length, hitRaw + 1));
        const hr = range.getBoundingClientRect();
        if (hr.width > 0 || hr.height > 0) edge = Number((vertical ? vr.right - hr.right : hr.top - vr.top).toFixed(1));
      }
      let secIdx = rmState.secIndex || 0;
      if (!paginated && rmState.secCharStarts.length > 1) {
        for (let s = rmState.secCharStarts.length - 1; s >= 0; s--) {
          if (charOffset >= rmState.secCharStarts[s]) { secIdx = s; break; }
        }
      }
      return {
        file,
        anchor_v: 1,
        char_offset: charOffset,
        sec_index: secIdx,
        quote,
        scroll_ratio: Number(ratio.toFixed(5)),
        page: rmState.pageIndex + 1,
        ...(edge != null ? { edge } : {}),
      };
    }

    function rmLocateAnchorOffset(root, localTarget, quote) {
      const { nodes, total } = rmCollectAnchorNodes(root);
      if (!nodes.length) return null;
      const clamped = Math.max(0, Math.min(Math.max(0, total - 1), localTarget || 0));
      let lo = 0, hi = nodes.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (nodes[mid].cumStart <= clamped) lo = mid;
        else hi = mid - 1;
      }
      let entry = nodes[lo];
      let rawIdx = rmRawIdxFromNonWs(entry.text, clamped - entry.cumStart);

      const qClean = (quote || '').replace(/[\s\u3000\u200b]+/g, '');
      if (qClean.length >= 6) {
        const probe = rmExtractQuoteAt(nodes, lo, rawIdx, Math.max(24, qClean.length)).replace(/[\s\u3000\u200b]+/g, '');
        const head = qClean.slice(0, 12);
        if (!probe.startsWith(head)) {
          const allNonWs = nodes.map(e => e.text.replace(/[\s\u3000\u200b]+/g, '')).join('');
          const nearStart = Math.max(0, clamped - 400);
          let found = allNonWs.indexOf(head, nearStart);
          if (found < 0 || found > clamped + 600) found = allNonWs.indexOf(head);
          if (found >= 0) {
            let a = 0, b = nodes.length - 1;
            while (a < b) {
              const m = (a + b + 1) >> 1;
              if (nodes[m].cumStart <= found) a = m;
              else b = m - 1;
            }
            entry = nodes[a];
            rawIdx = rmRawIdxFromNonWs(entry.text, found - entry.cumStart);
          }
        }
      }
      return { node: entry.node, rawIdx };
    }

    function rmAnchorTargetSection(anchor) {
      const count = Math.max(1, rmState.sections.length);
      if (count <= 1) return 0;
      const off = Math.max(0, anchor.char_offset || 0);
      if (rmState.secCharStarts.length === count) {
        if (typeof anchor.sec_index === 'number' && anchor.sec_index >= 0 && anchor.sec_index < count) {
          const s0 = rmState.secCharStarts[anchor.sec_index];
          const l0 = rmState.secCharLens[anchor.sec_index] || 0;
          if (l0 === 0 && off === s0) return anchor.sec_index;
          if (off >= s0 && off < s0 + l0) return anchor.sec_index;
        }
        for (let s = count - 1; s >= 0; s--) {
          if (off >= rmState.secCharStarts[s] && (rmState.secCharLens[s] > 0 || s === 0)) return s;
        }
      }
      if (typeof anchor.sec_index === 'number' && anchor.sec_index >= 0 && anchor.sec_index < count) {
        return anchor.sec_index;
      }
      return rmRatioToSection(anchor.scroll_ratio || 0, count).secIndex;
    }

    // A relayout (resize, a setting, a font or image load) lands on the page or scroll position that
    // holds the anchor. Reading a new anchor from that landing would start at the page's first
    // character, earlier than the old one, so every further relayout crept back a page. The landed
    // anchor is kept until the reader moves.
    let rmLanded = null;
    function rmPositionKey() {
      if (!rmState.part) return '';
      const base = `${rmState.part.file || ''}|${rmState.media}|${rmState.dir}|${rmState.layout}`;
      if (rmState.media === 'manga') {
        const mStage = document.getElementById('rm-manga-stage');
        const strip = mStage && mStage.classList.contains('rm-manga-strip');
        return `${base}|${rmState.mangaPage || 0}|${strip ? Math.round(mStage.scrollTop) : ''}`;
      }
      if (rmState.layout === 'paginated') return `${base}|${rmState.secIndex || 0}|${rmState.pageIndex || 0}`;
      const sc = rmScrollerEl();
      if (!sc) return base;
      return `${base}|${Math.round(rmState.dir === 'vertical' ? rmGetRtlDist(sc) : sc.scrollTop)}`;
    }
    function rmLayoutAnchor() {
      if (rmLanded && rmLanded.key === rmPositionKey()) return rmLanded.anchor;
      rmLanded = null;
      return rmReadAnchor();
    }

    function rmRestoreAnchor(anchor) {
      const ok = rmRestoreAnchorAt(anchor);
      rmLanded = (ok && anchor && anchor.anchor_v) ? { anchor, key: rmPositionKey() } : null;
      return ok;
    }

    // The page of the shown section that holds the anchor's character under the current layout.
    // Strict: -1 when the character is in another section; otherwise the nearest page.
    function rmAnchorPageInSection(anchor, root, strict = false) {
      if (!anchor || !root || rmState.layout !== 'paginated') return -1;
      const baseOff = rmState.secCharStarts[rmState.secIndex] || 0;
      const secLen = rmState.secCharLens[rmState.secIndex];
      const local = (anchor.char_offset || 0) - baseOff;
      if (strict && (local < 0 || (rmState.sections.length > 1 && secLen != null && local >= Math.max(1, secLen)))) return -1;
      const local0 = Math.max(0, local);
      const loc = rmLocateAnchorOffset(root, local0, anchor.quote);
      if (!loc) return -1;
      const prevT = root.style.transform;
      root.style.transform = '';
      const range = document.createRange();
      range.setStart(loc.node, loc.rawIdx);
      range.setEnd(loc.node, Math.min(loc.node.nodeValue.length, loc.rawIdx + 1));
      const cr = range.getBoundingClientRect();
      const rr = root.getBoundingClientRect();
      root.style.transform = prevT;
      const vertical = rmState.dir === 'vertical';
      const stride = Math.max(1, (vertical ? rmState.pageH : rmState.pageW) + RM_PAGE_GAP);
      const axis = vertical ? ((cr.top + cr.bottom) * 0.5 - rr.top) : ((cr.left + cr.right) * 0.5 - rr.left);
      return Math.max(0, Math.min(rmState.pageCount - 1, Math.floor((axis + RM_PAGE_GAP * 0.5) / stride)));
    }

    function rmRestoreAnchorAt(anchor) {
      if (!anchor || !rmState.part) return false;
      if (rmState.media === 'manga') {
        const pno = Math.max(1, Math.min((rmState.part.pages || []).length || 1, anchor.page || 1));
        const mStage = document.getElementById('rm-manga-stage');
        if (mStage && mStage.classList.contains('rm-manga-strip')) {
          const el = mStage.querySelector(`[data-page="${pno}"]`);
          if (el) {
            rmBarIgnoreScrollUntil = Date.now() + 200;
            const targetTop = el.offsetTop + Math.round((anchor.page_frac || 0) * el.offsetHeight);
            mStage.scrollTop = Math.max(0, targetTop);
            rmBarLastPos = mStage.scrollTop;
          }
          rmState.mangaPage = pno;
          rmUpdateProgressUI();
          return true;
        }
        if (typeof rmGoMangaPage === 'function') rmGoMangaPage(pno);
        return true;
      }
      if (!anchor.anchor_v) {
        rmRestoreScrollRatio(anchor.scroll_ratio || 0);
        return true;
      }
      const sc = rmScrollerEl();
      const root = document.getElementById('rm-epub-root');
      if (!sc || !root) return false;
      if (rmState.totalPlainChars <= 0) {
        if (rmState.layout === 'paginated' && rmState.sections.length > 1 && typeof anchor.sec_index === 'number') {
          const sIdx = Math.max(0, Math.min(rmState.sections.length - 1, anchor.sec_index));
          if (sIdx !== rmState.secIndex) rmRenderPaginatedSection(sIdx, { inSecRatio: 0 });
          else rmApplyPaginatedOffset(0);
          return true;
        }
        rmRestoreScrollRatio(anchor.scroll_ratio || 0);
        return true;
      }

      if (rmState.layout === 'paginated') {
        const targetSec = rmAnchorTargetSection(anchor);
        if (rmState.sections.length > 1 && targetSec !== rmState.secIndex) {
          rmRenderPaginatedSection(targetSec, { skipOffset: true });
        }
        const activeRoot = document.getElementById('rm-epub-root');
        const activeSc = rmScrollerEl();
        if (!activeRoot || !activeSc) return false;
        rmApplyPaginatedOffset(Math.max(0, rmAnchorPageInSection(anchor, activeRoot)));
        return true;
      }

      const loc = rmLocateAnchorOffset(root, anchor.char_offset || 0, anchor.quote);
      if (!loc) {
        rmRestoreScrollRatio(anchor.scroll_ratio || 0);
        return true;
      }
      const range = document.createRange();
      range.setStart(loc.node, loc.rawIdx);
      range.setEnd(loc.node, Math.min(loc.node.nodeValue.length, loc.rawIdx + 1));
      const cr = range.getBoundingClientRect();
      const vr = sc.getBoundingClientRect();
      rmBarIgnoreScrollUntil = Date.now() + 200;
      if (rmState.dir === 'vertical') {
        const curDist = rmGetRtlDist(sc);
        const pad = typeof anchor.edge === 'number' ? anchor.edge : 20;
        const delta = (vr.right - pad) - cr.right;
        rmSetRtlDist(sc, curDist + delta, false);
        rmBarLastPos = rmGetRtlDist(sc);
      } else {
        const pad = typeof anchor.edge === 'number' ? anchor.edge : rmAnchorTopPad();
        const targetTop = Math.max(0, sc.scrollTop + (cr.top - vr.top) - pad);
        sc.scrollTo({ top: targetTop, behavior: 'instant' });
        rmBarLastPos = sc.scrollTop;
      }
      return true;
    }

    function rmCapturePos() {
      const sc = rmScrollerEl();
      const item = rmState.files[rmState.partIndex];
      const anchor = rmReadAnchor();
      return {
        partIndex: rmState.partIndex,
        file: (rmState.part && rmState.part.file) || (item && item.file) || '',
        secIndex: rmState.secIndex || 0,
        pageIndex: rmState.pageIndex || 0,
        scrollRatio: rmState.media === 'manga' ? 0 : rmReadScrollRatio(),
        scrollTop: sc ? sc.scrollTop : 0,
        rtlDist: (sc && rmState.dir === 'vertical') ? rmGetRtlDist(sc) : 0,
        anchor,
      };
    }

    async function rmRestoreHistoryPos(pos) {
      if (!pos || !isReadingModeOpen()) return;
      let idx = typeof pos.partIndex === 'number' ? pos.partIndex : -1;
      if (pos.file && (!rmState.files[idx] || rmState.files[idx].file !== pos.file)) {
        const found = rmState.files.findIndex(f => f.file === pos.file);
        if (found >= 0) idx = found;
      }
      if (idx < 0 || idx >= rmState.files.length) return;
      if (idx !== rmState.partIndex || !rmState.part) {
        await rmLoadPart(idx, { restoreExactPos: pos, targetAnchor: pos.anchor || null, fromHistory: true });
        return;
      }
      if (pos.anchor && pos.anchor.anchor_v) {
        rmRestoreAnchor(pos.anchor);
      } else if (rmState.layout === 'paginated') {
        if ((rmState.sections || []).length > 1 && pos.secIndex != null && pos.secIndex !== rmState.secIndex) {
          rmRenderPaginatedSection(pos.secIndex, { inSecRatio: 0 });
        }
        rmApplyPaginatedOffset(pos.pageIndex || 0);
      } else {
        const sc = rmScrollerEl();
        if (sc && rmState.dir === 'vertical' && pos.rtlDist != null) {
          rmSetRtlDist(sc, pos.rtlDist, false);
        } else if (sc && rmState.dir !== 'vertical' && pos.scrollTop != null) {
          sc.scrollTo({ top: pos.scrollTop, behavior: 'instant' });
        } else {
          rmRestoreScrollRatio(pos.scrollRatio || 0);
        }
      }
      rmUpdateProgressUI();
      saveMediaState();
      rmSaveProgressNow(false);
    }

    function rmPushLinkHistory(beforePos, afterPos) {
      if (!rmState.historySession) {
        rmState.historySession = Date.now() + Math.floor(Math.random() * 1000);
        rmState.historyDepth = 0;
      }
      const curDepth = rmState.historyDepth || 0;
      try {
        const base = (history.state && typeof history.state === 'object') ? history.state : {};
        history.replaceState({ ...base, rmSession: rmState.historySession, rmDepth: curDepth, rmPos: beforePos }, '');
        const nextDepth = curDepth + 1;
        history.pushState({ ...base, rmSession: rmState.historySession, rmDepth: nextDepth, rmPos: afterPos }, '');
        rmState.historyDepth = nextDepth;
      } catch (e) {}
    }

    window.addEventListener('popstate', e => {
      if (rmIgnorePopCount > 0) {
        rmIgnorePopCount--;
        return;
      }
      if (!isReadingModeOpen()) return;
      const st = e.state;
      if (st && st.rmSession && st.rmSession === rmState.historySession && st.rmPos) {
        rmState.historyDepth = typeof st.rmDepth === 'number' ? st.rmDepth : 0;
        rmRestoreHistoryPos(st.rmPos);
      }
    });

    function isReadingModeOpen() {
      const dlg = document.getElementById('reading-mode');
      return !!(rmState.open && dlg && !dlg.hidden);
    }

    function rmCurrentRecipe() {
      if (!isReadingModeOpen() || !rmState.part) return null;
      return {
        media: rmState.media,
        folder: rmState.folder,
        file: rmState.part.file,
        page: rmState.media === 'manga' ? rmState.mangaPage : 0,
      };
    }

    function rmToast(msg) {
      const dlg = document.getElementById('reading-mode');
      if (!dlg) return;
      let el = dlg.querySelector('.rm-toast');
      if (!el) {
        el = document.createElement('div');
        el.className = 'rm-toast';
        el.setAttribute('role', 'status');
        dlg.appendChild(el);
      }
      el.textContent = msg;
      el.hidden = false;
      clearTimeout(rmState.toastTimer);
      rmState.toastTimer = setTimeout(() => { el.hidden = true; }, 1800);
    }

    function rmSetSafeHtml(target, htmlStr) {
      const doc = rmParseSafeDoc(htmlStr);
      target.replaceChildren(...doc.body.childNodes);
    }

    function rmRenderChunked(container, items, renderItem, onDone) {
      const gen = ++rmState.chunkGen;
      container.innerHTML = '';
      let idx = 0;
      const step = () => {
        if (gen !== rmState.chunkGen) return;
        const t0 = performance.now();
        const frag = document.createDocumentFragment();
        const tmp = document.createElement('div');
        while (idx < items.length) {
          tmp.innerHTML = renderItem(items[idx], idx);
          while (tmp.firstChild) frag.appendChild(tmp.firstChild);
          idx++;
          if (idx % 16 === 0 && performance.now() - t0 >= 8) break;
        }
        container.appendChild(frag);
        if (idx < items.length) {
          requestAnimationFrame(step);
        } else if (onDone) {
          onDone();
        }
      };
      requestAnimationFrame(step);
    }

    function rmGetRtlDist(el) {
      return Math.max(0, Math.abs(el.scrollLeft));
    }
    function rmSetRtlDist(el, dist, smooth = false) {
      const maxD = Math.max(0, el.scrollWidth - el.clientWidth);
      const clamped = Math.max(0, Math.min(maxD, dist));
      el.scrollTo({ left: -clamped, behavior: smooth ? 'smooth' : 'instant' });
    }

    // A manga volume with no page image shows its pages as text cards, with the text settings
    // subtitles have.
    const RM_PART_CLIENT = Math.random().toString(36).slice(2) + Date.now().toString(36);
    function rmMangaTextOnly(part) {
      const pages = (part && part.pages) || [];
      return pages.length > 0 && pages.every(pg => !pg.image_url);
    }

    function rmResolveDirAndLayout() {
      const p = rmGetPrefs();
      const partWm = (rmState.part && rmState.part.writing_mode) || 'horizontal';
      rmState.dir = (p.writing_mode === 'vertical' || p.writing_mode === 'horizontal') ? p.writing_mode : partWm;
      // The layout is one choice, the text direction another: changing one never changes the other.
      rmState.layout = p.layout === 'continuous' ? 'continuous' : 'paginated';
    }

    let rmFallbackTimer = null;
    let rmFallbackFadeTimer = null;
    function rmHideFallbackBanner() {
      clearTimeout(rmFallbackTimer);
      clearTimeout(rmFallbackFadeTimer);
      const banner = document.getElementById('rm-fallback-banner');
      if (!banner) return;
      banner.classList.remove('rm-fading');
      banner.hidden = true;
    }
    function rmShowFallbackBanner(text) {
      clearTimeout(rmFallbackTimer);
      clearTimeout(rmFallbackFadeTimer);
      const banner = document.getElementById('rm-fallback-banner');
      if (!banner) return;
      if (!text) {
        banner.classList.remove('rm-fading');
        banner.hidden = true;
        banner.innerHTML = '';
        return;
      }
      banner.classList.remove('rm-fading');
      banner.innerHTML = `<strong>!</strong><span>${esc(text)}</span>`;
      banner.hidden = false;
      rmFallbackTimer = setTimeout(() => {
        banner.classList.add('rm-fading');
        rmFallbackFadeTimer = setTimeout(() => {
          banner.hidden = true;
          banner.classList.remove('rm-fading');
        }, 460);
      }, 4500);
    }

    function rmFallbackText(reason) {
      const key = 'rm_fallback_' + String(reason || 'other').split(':')[0];
      return I18N[LANG][key] ? t(key) : t('rm_fallback_other');
    }

    let rmBarHidden = false;
    let rmBarShownBy = 'init';
    let rmBarHoverTimer = null;
    let rmBarLastPos = 0;
    let rmBarIgnoreScrollUntil = 0;

    function rmHasOpenOverlay() {
      const ids = ['rm-settings-panel', 'rm-toc-drawer', 'rm-bm-menu', 'rm-notes-panel'];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && !el.hidden) return true;
      }
      return !!rmFontPopupState;
    }

    function rmIsScrollableBarMode() {
      if (rmState.media === 'manga') {
        const p = rmGetPrefs();
        return p.manga_layout === 'strip' || !!(rmState.part && (rmState.part.source === 'db' || rmMangaTextOnly(rmState.part)));
      }
      return rmState.layout !== 'paginated';
    }

    function rmReadTopbarScrollPos() {
      if (rmState.media === 'manga') {
        const ms = document.getElementById('rm-manga-stage');
        return ms ? Math.max(0, ms.scrollTop) : 0;
      }
      const sc = rmScrollerEl();
      if (!sc) return 0;
      return rmState.dir === 'vertical' ? rmGetRtlDist(sc) : Math.max(0, sc.scrollTop);
    }

    function rmSyncBarHeight() {
      const dlg = document.getElementById('reading-mode');
      const bar = document.getElementById('rm-topbar');
      if (!dlg || !bar) return;
      const h = bar.offsetHeight;
      if (h > 20) dlg.style.setProperty('--rm-bar-h', h + 'px');
    }

    function rmCanHoverTopbar() {
      return !(window.matchMedia && window.matchMedia('(hover: none)').matches);
    }

    function rmBarAutoHideActive(p = rmGetPrefs()) {
      return !!((p.auto_hide_bar && rmCanHoverTopbar()) || (p.hide_bar_scroll && rmIsScrollableBarMode()));
    }

    function rmSyncAutoHideClasses(p = rmGetPrefs()) {
      const dlg = document.getElementById('reading-mode');
      if (!dlg) return false;
      const hoverOn = !!(p.auto_hide_bar && rmCanHoverTopbar());
      const scrollable = rmIsScrollableBarMode();
      const scrollOn = !!(p.hide_bar_scroll && scrollable);
      const active = hoverOn || scrollOn;
      dlg.classList.toggle('rm-autohide', active);
      dlg.classList.toggle('rm-autohide-pad', scrollOn && !hoverOn);
      rmSyncBarHeight();
      if (!active) rmSetTopbarHidden(false, 'off');
      return active;
    }

    function rmSetTopbarHidden(hidden, reason = '') {
      clearTimeout(rmBarHoverTimer);
      rmBarHoverTimer = null;
      const dlg = document.getElementById('reading-mode');
      if (!dlg) return;
      const wantHidden = !!hidden && rmBarAutoHideActive() && !rmHasOpenOverlay();
      rmBarHidden = wantHidden;
      if (!wantHidden && reason) rmBarShownBy = reason;
      dlg.classList.toggle('rm-bar-hidden', wantHidden);
    }

    function rmResetTopbarForMode() {
      rmBarIgnoreScrollUntil = Date.now() + 200;
      const p = rmGetPrefs();
      if (!rmSyncAutoHideClasses(p)) return;
      if (rmHasOpenOverlay()) {
        rmSetTopbarHidden(false, 'overlay');
        return;
      }
      if (p.auto_hide_bar && rmCanHoverTopbar()) {
        if (rmIsScrollableBarMode()) rmBarLastPos = rmReadTopbarScrollPos();
        rmSetTopbarHidden(true);
        return;
      }
      const pos = rmReadTopbarScrollPos();
      rmBarLastPos = pos;
      rmSetTopbarHidden(pos > 24, 'scroll');
    }

    function rmOnBarScroll() {
      const p = rmGetPrefs();
      if (!isReadingModeOpen() || !p.hide_bar_scroll || rmHasOpenOverlay()) return;
      if (!rmIsScrollableBarMode()) return;
      const pos = rmReadTopbarScrollPos();
      if (Date.now() < rmBarIgnoreScrollUntil) {
        rmBarLastPos = pos;
        return;
      }
      if (pos <= 12) {
        rmSetTopbarHidden(false, 'scroll');
        rmBarLastPos = pos;
        return;
      }
      const delta = pos - rmBarLastPos;
      if (delta > 8) {
        rmSetTopbarHidden(true);
        rmBarLastPos = pos;
      } else if (delta < -8) {
        rmSetTopbarHidden(false, 'scroll');
        rmBarLastPos = pos;
      }
    }

    function rmOnDialogMouseMove(e) {
      const p = rmGetPrefs();
      if (!isReadingModeOpen() || !p.auto_hide_bar || !rmCanHoverTopbar() || rmHasOpenOverlay()) return;
      const bar = document.getElementById('rm-topbar');
      const barH = (bar && bar.offsetHeight) || 46;
      if (e.clientY <= barH + 4) {
        clearTimeout(rmBarHoverTimer);
        rmBarHoverTimer = null;
        if (rmBarHidden) rmSetTopbarHidden(false, 'hover');
      } else if (!rmBarHidden && (rmBarShownBy === 'hover' || !p.hide_bar_scroll) && e.clientY > barH + 24 && !e.target.closest('#rm-topbar, #rm-bm-menu')) {
        if (!rmBarHoverTimer) {
          rmBarHoverTimer = setTimeout(() => {
            rmBarHoverTimer = null;
            const cur = rmGetPrefs();
            if (isReadingModeOpen() && cur.auto_hide_bar && !rmHasOpenOverlay() && (rmBarShownBy === 'hover' || !cur.hide_bar_scroll)) {
              rmSetTopbarHidden(true);
            }
          }, 220);
        }
      }
    }

    function rmEnsureDialogShell() {
      const dlg = document.getElementById('reading-mode');
      if (!dlg || dlg.dataset.built) return dlg;
      dlg.dataset.built = '1';
      dlg.innerHTML = `
        <div class="rm-topbar" id="rm-topbar">
          <button type="button" class="btn rm-back-btn" id="rm-back-btn" onclick="closeReadingMode()" aria-label="${esc(t('rm_back'))}"><span aria-hidden="true">←</span><span class="rm-back-text"> ${esc(t('rm_back'))}</span></button>
          <button type="button" class="sq-btn" id="rm-toc-btn" onclick="rmToggleToc()" title="${esc(t('rm_toc'))}" aria-label="${esc(t('rm_toc'))}">${svgIcon('<path d="M4 6h16M4 12h16M4 18h10"/>')}</button>
          <div class="rm-topbar-title">
            <span class="rm-work-title" id="rm-work-title"></span>
            <span class="rm-part-title" id="rm-title"></span>
          </div>
          <div class="rm-bar-actions">
            <button type="button" class="sq-btn" id="rm-prev-btn" onclick="rmStepPart(-1)" title="${esc(t('rm_prev_part'))}" aria-label="${esc(t('rm_prev_part'))}">${svgIcon('<path d="M15 18l-6-6 6-6"/>')}</button>
            <button type="button" class="sq-btn" id="rm-next-btn" onclick="rmStepPart(1)" title="${esc(t('rm_next_part'))}" aria-label="${esc(t('rm_next_part'))}">${svgIcon('<path d="M9 6l6 6-6 6"/>')}</button>
            <button type="button" class="sq-btn" id="rm-notes-btn" onpointerdown="if(typeof rmCaptureNotesSelection==='function')rmCaptureNotesSelection()" onclick="if(typeof rmToggleNotes==='function')rmToggleNotes()" title="${esc(t('rm_notes'))}" aria-label="${esc(t('rm_notes'))}">${svgIcon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/>')}</button>
            <button type="button" class="sq-btn" id="rm-bm-btn" onclick="rmOnBookmarkClick()" title="${esc(t('rm_bookmark_set'))}" aria-label="${esc(t('rm_bookmark_set'))}">${svgIcon('<path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z"/>')}</button>
            <button type="button" class="sq-btn" id="rm-settings-btn" onclick="rmToggleSettings()" title="${esc(t('rm_settings'))}" aria-label="${esc(t('rm_settings'))}">${svgIcon('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.6.85 1 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>')}</button>
          </div>
        </div>
        <div class="rm-bm-menu" id="rm-bm-menu" hidden></div>
        <div class="rm-main" id="rm-main">
          <div class="rm-fallback-banner" id="rm-fallback-banner" hidden onclick="rmHideFallbackBanner()"></div>
          <div class="rm-stage" id="rm-stage" tabindex="-1"></div>
          <div class="rm-edge-hint rm-edge-left" id="rm-edge-left" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 4l-8 8 8 8"/></svg></div>
          <div class="rm-edge-hint rm-edge-right" id="rm-edge-right" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4l8 8-8 8"/></svg></div>
        </div>
        <div class="rm-footer" id="rm-footer" onclick="rmToggleFooterMin()">
          <span id="rm-foot-left"></span>
          <div class="rm-progress-track"><div class="rm-progress-fill" id="rm-progress-fill"></div></div>
          <span id="rm-foot-right"></span>
        </div>
        <div class="rm-drawer-backdrop" id="rm-toc-drawer" hidden onclick="if(event.target===this)rmToggleToc(false)">
          <div class="rm-drawer-panel">
            <div class="rm-drawer-head">
              <span id="rm-toc-head">${esc(t('rm_toc'))}</span>
              <button type="button" class="sq-btn" onclick="rmToggleToc(false)" aria-label="${esc(t('close'))}">✕</button>
            </div>
            <div class="rm-drawer-list" id="rm-toc-list"></div>
          </div>
        </div>
        <div class="rm-settings-backdrop" id="rm-settings-panel" hidden onclick="if(event.target===this)rmToggleSettings(false)">
          <div class="rm-settings-card" id="rm-settings-card"></div>
        </div>
        <div class="rm-notes-backdrop" id="rm-notes-panel" hidden onclick="if(event.target===this && typeof rmToggleNotes==='function')rmToggleNotes(false)">
          <div class="rm-notes-card" id="rm-notes-card"></div>
        </div>
        <style id="rm-epub-style"></style>`;

      dlg.addEventListener('click', e => {
        const bmMenu = document.getElementById('rm-bm-menu');
        if (bmMenu && !bmMenu.hidden && !e.target.closest('#rm-bm-menu, #rm-bm-btn')) {
          bmMenu.hidden = true;
          rmResetTopbarForMode();
        }
      });
      dlg.addEventListener('mousemove', rmOnDialogMouseMove, { passive: true });

      document.addEventListener('keydown', rmOnKeyDown);
      document.addEventListener('keyup', rmOnKeyUp);
      window.addEventListener('blur', rmStopGlide);
      window.addEventListener('resize', rmOnResize);
      window.addEventListener('pagehide', () => { if (isReadingModeOpen()) rmSaveProgressNow(true); });
      return dlg;
    }

    async function openReadingMode({ media, folder, file, page = 0, explicitStart = false, fromRestore = false, target = null, toast = '' }) {
      if (!rmSupportsMedia(media)) return;
      const dlg = rmEnsureDialogShell();
      const openGen = (rmState.openGen = (rmState.openGen || 0) + 1);
      rmState.open = true;
      rmState.media = media;
      rmState.folder = folder;
      rmState.fallbackNoticed = false;
      const hSt = (history.state && typeof history.state === 'object') ? history.state : null;
      if (fromRestore && hSt && hSt.rmSession) {
        rmState.historySession = hSt.rmSession;
        rmState.historyDepth = typeof hSt.rmDepth === 'number' ? hSt.rmDepth : 0;
      } else {
        rmState.historySession = Date.now() + Math.floor(Math.random() * 1000);
        rmState.historyDepth = 0;
      }
      rmHideFallbackBanner();
      rmApplyPrefsToDom(false);
      dlg.hidden = false;
      document.documentElement.classList.add('rm-open');
      document.documentElement.classList.remove('rm-booting');
      document.body.classList.add('rm-open');
      try { sessionStorage.setItem('aobana_rm_open', '1'); } catch (e) {}
      document.getElementById('rm-work-title').textContent = folder;
      document.getElementById('rm-title').textContent = t('loading');
      document.getElementById('rm-stage').innerHTML = `<div class="status-line" style="padding:3em;text-align:center;">${esc(t('loading'))}</div>`;

      try {
        const res = await fetch(`/api/reading/chapters?media=${encodeURIComponent(media)}&folder=${encodeURIComponent(folder)}`);
        if (!res.ok) throw new Error('chapters failed');
        const data = await res.json();
        if (openGen !== rmState.openGen || !isReadingModeOpen()) return;
        rmState.files = data.files || [];
        if (data.prefs) rmSetPrefsCache(media, data.prefs);
        rmState.work = data.work || {};
        let targetFile = file || rmState.work.file || (rmState.files[0] && rmState.files[0].file) || '';
        let idx = rmState.files.findIndex(f => f.file === targetFile);
        if (idx < 0) idx = 0;
        if (!rmState.files.length) {
          document.getElementById('rm-stage').innerHTML = `<div class="status-line" style="padding:3em;text-align:center;">${esc(t('rm_no_content'))}</div>`;
          return;
        }
        rmRenderToc();
        if (typeof rmLoadWorkNotes === 'function') rmLoadWorkNotes();
        // A place from the 保存 tab (a bookmark, a note) opens there, as the reader's own jumps do
        const placed = target && rmState.files[idx].file === target.file;
        await rmLoadPart(idx, placed
          ? { targetAnchor: target.anchor_v ? target : null, targetRatio: target.scroll_ratio, targetPage: target.page || 1 }
          : {
            restorePos: !explicitStart && (fromRestore || (rmState.work && rmState.work.file === rmState.files[idx].file)),
            targetPage: page || (rmState.work && rmState.work.file === rmState.files[idx].file ? (rmState.work.page || 1) : 1),
          });
        // A place whose part is gone (a re-index) opens where the work was left, and says so
        if (openGen === rmState.openGen) {
          if (target && !placed) rmToast(t('rm_place_gone'));
          else if (toast) rmToast(toast);
        }
        try {
          const base = (history.state && typeof history.state === 'object') ? history.state : {};
          history.replaceState({ ...base, rmSession: rmState.historySession, rmDepth: rmState.historyDepth || 0, rmPos: rmCapturePos() }, '');
        } catch (e) {}
        saveMediaState();
      } catch (e) {
        if (openGen !== rmState.openGen || !isReadingModeOpen()) return;
        document.getElementById('rm-stage').innerHTML = `<div class="error-text" style="padding:2em;text-align:center;">${esc(t('load_failed'))}</div>`;
      }
    }

    function closeReadingMode(fromPop = false) {
      const dlg = document.getElementById('reading-mode');
      if (!dlg) return;
      const depthToRewind = (!fromPop && rmState.historyDepth > 0) ? rmState.historyDepth : 0;
      rmState.historyDepth = 0;
      rmState.historySession = 0;
      rmState.openGen = (rmState.openGen || 0) + 1;
      if (rmState.partCtrl) { rmState.partCtrl.abort(); rmState.partCtrl = null; }
      rmStopGlide();
      if (rmState.open) rmSaveProgressNow(false);
      rmState.open = false;
      rmState.chunkGen++;
      clearTimeout(rmState.saveTimer);
      // Nothing of this visit's place carries into the next opening
      rmLanded = null;
      rmClearDragAnchor();
      clearTimeout(rmResizeTimer);
      rmResizeTimer = null;
      rmResizeAnchor = null;
      rmLastWide = window.innerWidth > 720;
      const toc = document.getElementById('rm-toc-drawer');
      const setp = document.getElementById('rm-settings-panel');
      const notesp = document.getElementById('rm-notes-panel');
      rmCloseFontPopup(false);
      rmSetTopbarHidden(false, 'close');
      if (toc) toc.hidden = true;
      if (setp) setp.hidden = true;
      if (notesp) notesp.hidden = true;
      if (typeof rmResetNotesOnClose === 'function') rmResetNotesOnClose();
      dlg.hidden = true;
      document.documentElement.classList.remove('rm-open');
      document.body.classList.remove('rm-open');
      try { sessionStorage.removeItem('aobana_rm_open'); } catch (e) {}
      saveMediaState();
      if (rmState.media && rmState.folder) rmRefreshEntryButton(rmState.media, rmState.folder);
      if (depthToRewind > 0) {
        rmIgnorePopCount += 1;
        try { history.go(-depthToRewind); } catch (e) { rmIgnorePopCount = Math.max(0, rmIgnorePopCount - 1); }
      }
    }

    function rmOpenInSettings() {
      if (isReadingModeOpen()) rmSaveProgressNow(false);
      saveMediaState();
      store.set('reader_settings_media', rmState.media === 'manga' && rmMangaTextOnly(rmState.part) ? 'manga-text' : rmState.media);
      window.location.href = '/?tab=settings#set-reader';
    }

    async function rmLoadPart(index, opts = {}) {
      if (index < 0 || index >= rmState.files.length) return;
      rmLanded = null;
      rmState.partIndex = index;
      const item = rmState.files[index];
      const fullTitle = item.title || item.file;
      const head = rmTocCommonHead(rmState.files.map(it => it.title || it.file));
      const shortTitle = (head && fullTitle.startsWith(head) && fullTitle.length > head.length) ? fullTitle.slice(head.length) : fullTitle;
      const titleEl = document.getElementById('rm-title');
      titleEl.textContent = shortTitle;
      titleEl.title = fullTitle;
      document.getElementById('rm-prev-btn').disabled = index <= 0;
      document.getElementById('rm-next-btn').disabled = index >= rmState.files.length - 1;
      const stage = document.getElementById('rm-stage');
      stage.innerHTML = `<div class="status-line" style="padding:3em;text-align:center;">${esc(t('loading'))}</div>`;
      rmHighlightToc();
      // The index notice belongs to the part it came with: moving to another part clears it.
      rmHideFallbackBanner();

      const gen = rmState.loadGen = (rmState.loadGen || 0) + 1;
      // Skipping through parts loads only the one stopped on: a newer load cancels the one in
      // flight, and waits a moment so a quick run of clicks sends no request for each part passed;
      // the server stops a load once a newer one from this page has started.
      const skipping = !!rmState.partCtrl;
      if (rmState.partCtrl) rmState.partCtrl.abort();
      const ctrl = rmState.partCtrl = new AbortController();
      if (skipping) {
        await new Promise(res => setTimeout(res, 180));
        if (gen !== rmState.loadGen || !isReadingModeOpen()) return;
      }
      let r = null;
      let part = null;
      try {
        r = await fetch(`/api/reading/part?media=${encodeURIComponent(rmState.media)}&folder=${encodeURIComponent(rmState.folder)}&file=${encodeURIComponent(item.file)}&client=${RM_PART_CLIENT}&seq=${gen}`, { signal: ctrl.signal });
        if (r.ok) part = await r.json();
      } catch (e) {}
      if (rmState.partCtrl === ctrl) rmState.partCtrl = null;
      if (gen !== rmState.loadGen || !isReadingModeOpen()) return;
      if (!part) {
        stage.innerHTML = `<div class="error-text" style="padding:2em;text-align:center;">${esc(t('load_failed'))}</div>`;
        return;
      }
      rmState.part = part;
      rmResolveDirAndLayout();

      // The index-fallback notice shows once per entry into reading mode, bottom right, and fades
      // after 4.5 s; a click dismisses it earlier.
      if (part.source === 'db' && !rmState.fallbackNoticed) {
        rmState.fallbackNoticed = true;
        rmShowFallbackBanner(rmFallbackText(part.fallback_reason));
      }

      const styleEl = document.getElementById('rm-epub-style');
      styleEl.textContent = part.media === 'epub' ? (part.css || '') : '';

      rmApplyPrefsToDom(false);
      rmRenderPartContent(opts);
      rmUpdateBookmarkBtn();
      if (typeof rmOnNotesPartChange === 'function') rmOnNotesPartChange();
      saveMediaState();
      if (opts.fromHistory) rmSaveProgressNow(false);
      else rmScheduleSaveProgress();
    }

    function rmApplyPrefsToDom(relayout = true, rebuildSettings = true, anchorOverride = null) {
      const dlg = document.getElementById('reading-mode');
      if (!dlg) return;
      const prevAnchor = (relayout && rmState.part) ? (anchorOverride || rmLayoutAnchor()) : null;
      const p = rmGetPrefs();
      const effTheme = (p.theme && p.theme !== 'app') ? p.theme : currentTheme();
      dlg.setAttribute('data-rm-theme', effTheme);
      const edgePct = Math.max(5, Math.min(35, Number(p.edge_click_width) || 12));
      dlg.style.setProperty('--rm-edge-w', edgePct + '%');
      rmSyncAutoHideClasses(p);

      const stage = document.getElementById('rm-stage');
      if (stage) {
        stage.style.setProperty('--rm-font-size', p.font_size + 'px');
        stage.style.setProperty('--rm-font-weight', String(p.font_weight || 400));
        stage.style.setProperty('--rm-line-height', String(p.line_height));
        stage.style.setProperty('--rm-max-w', p.max_width + 'em');
        stage.style.setProperty('--rm-max-h', (p.max_height || 36) + 'em');
        stage.style.fontFamily = rmFontStack(p.font_family);
        stage.classList.toggle('rm-furi-off', p.furigana === 'off');
        stage.classList.toggle('rm-furi-hover', p.furigana === 'hover');
        stage.classList.toggle('rm-hide-ts', !p.sub_timestamps);
        stage.classList.toggle('rm-boxes-hover', p.manga_boxes === 'hover');
        stage.classList.toggle('rm-boxes-always', p.manga_boxes === 'always');
        stage.classList.toggle('rm-boxes-off', p.manga_boxes === 'off');
      }
      const footer = document.getElementById('rm-footer');
      if (footer) footer.hidden = !p.show_progress;
      rmSetEdgeHint(null);

      if (relayout && rmState.part) {
        const prevDir = rmState.dir;
        const prevLayout = rmState.layout;
        rmResolveDirAndLayout();
        rmSyncAutoHideClasses(p);
        if (rmState.media === 'manga') {
          const curStrip = !!document.querySelector('#rm-manga-stage.rm-manga-strip');
          const wantStrip = p.manga_layout === 'strip' || rmState.part.source === 'db';
          if (curStrip !== wantStrip) {
            rmRenderMangaPart({ restorePos: false, targetPage: (prevAnchor && prevAnchor.page) || rmState.mangaPage, targetAnchor: prevAnchor });
          } else if (!wantStrip && typeof rmMangaFit === 'function') {
            requestAnimationFrame(() => rmMangaFit(false));
          } else if (wantStrip && typeof rmResizeStripPages === 'function') {
            rmResizeStripPages();
            if (prevAnchor) rmRestoreAnchor(prevAnchor);
          }
        } else if (prevDir !== rmState.dir || prevLayout !== rmState.layout) {
          rmRenderPartContent({ targetAnchor: prevAnchor, targetRatio: prevAnchor ? prevAnchor.scroll_ratio : 0 });
        } else if (rmState.layout === 'paginated') {
          rmApplyStageLayoutClasses();
          rmMeasurePagination();
          if (prevAnchor) rmRestoreAnchor(prevAnchor);
          else rmApplyPaginatedOffset(rmState.pageIndex);
          rmUpdateProgressUI();
        } else {
          rmApplyStageLayoutClasses();
          rmMeasurePagination();
          if (prevAnchor) rmRestoreAnchor(prevAnchor);
          rmUpdateProgressUI();
        }
      }
      const setp = document.getElementById('rm-settings-panel');
      if (rebuildSettings && setp && !setp.hidden) rmRenderSettingsPanel();
    }

    function rmEdgeHitSide(clientX, containerEl) {
      if (!containerEl) return null;
      const rect = containerEl.getBoundingClientRect();
      if (rect.width <= 0) return null;
      const pct = Math.max(5, Math.min(35, Number(rmGetPrefs().edge_click_width) || 12)) / 100;
      const edgeW = rect.width * pct;
      const x = clientX - rect.left;
      if (x >= 0 && x <= edgeW) return 'left';
      if (x >= rect.width - edgeW && x <= rect.width) return 'right';
      return null;
    }

    function rmSetEdgeHint(side) {
      const l = document.getElementById('rm-edge-left');
      const r = document.getElementById('rm-edge-right');
      const st = document.getElementById('rm-stage');
      if (l) l.classList.toggle('show', side === 'left');
      if (r) r.classList.toggle('show', side === 'right');
      if (st) st.classList.toggle('rm-edge-hover', !!side);
    }

    function rmEdgeNavActive() {
      if (window.innerWidth <= 720) return false;
      if (rmGetPrefs().edge_click_nav === false) return false;
      if (rmState.media === 'manga') {
        const p = rmGetPrefs();
        if (p.manga_layout === 'strip' || (rmState.part && rmState.part.source === 'db')) return false;
        return rmPz.scale <= rmPz.fitScale * 1.04;
      }
      return rmState.layout === 'paginated';
    }

    function rmApplyStageLayoutClasses() {
      const stage = document.getElementById('rm-stage');
      if (!stage) return;
      stage.classList.toggle('rm-vertical', rmState.dir === 'vertical');
      stage.classList.toggle('rm-horizontal', rmState.dir !== 'vertical');
      stage.classList.toggle('rm-paginated', rmState.layout === 'paginated');
      stage.classList.toggle('rm-continuous', rmState.layout !== 'paginated');
    }

    function rmParseSafeDoc(htmlStr) {
      const doc = new DOMParser().parseFromString(`<!doctype html><body>${String(htmlStr || '')}`, 'text/html');
      doc.querySelectorAll('script,style,iframe,frame,object,embed,form,meta,link,base,template,foreignObject,animate,set').forEach(n => n.remove());
      doc.querySelectorAll('*').forEach(n => {
        for (const a of [...n.attributes]) {
          const nm = a.name.toLowerCase();
          const val = String(a.value || '').replace(/[\u0000- \u007f- ]+/g, '');
          if (nm.startsWith('on') || nm === 'srcdoc' || nm === 'formaction') { n.removeAttribute(a.name); continue; }
          if (/(?:^|:)href$/.test(nm) || nm === 'src') {
            const ok = nm === 'src' || (nm.endsWith('href') && n.tagName.toLowerCase() === 'image')
              ? /^\/api\/reading\/epub-asset\//.test(val)
              : (/^#/.test(val) || /^https?:\/\//i.test(val));
            if (!ok) n.removeAttribute(a.name);
          }
        }
      });
      return doc;
    }

    function rmRatioToSection(ratio, secCount) {
      const r = Math.max(0, Math.min(1, Number(ratio) || 0));
      const count = Math.max(1, secCount);
      if (count === 1) return { secIndex: 0, inSecRatio: r, atEnd: r >= 0.999 };
      if (r >= 0.999) return { secIndex: count - 1, inSecRatio: 1, atEnd: true };
      const scaled = r * count;
      const idx = Math.min(count - 1, Math.floor(scaled));
      return { secIndex: idx, inSecRatio: scaled - idx, atEnd: false };
    }

    function rmReadSectionRatio() {
      if (rmState.layout === 'paginated') {
        return rmState.pageCount > 1 ? rmState.pageIndex / (rmState.pageCount - 1) : 0;
      }
      const sc = rmScrollerEl();
      if (!sc) return 0;
      if (rmState.dir === 'vertical') {
        const maxD = Math.max(0, sc.scrollWidth - sc.clientWidth);
        return maxD > 0 ? Math.min(1, rmGetRtlDist(sc) / maxD) : 0;
      }
      const maxY = Math.max(0, sc.scrollHeight - sc.clientHeight);
      return maxY > 0 ? Math.min(1, sc.scrollTop / maxY) : 0;
    }

    function rmNormalizePaginatedSection(root, scroller) {
      if (!root || !scroller) return;
      root.querySelectorAll('img[loading="lazy"]').forEach(img => img.removeAttribute('loading'));
      root.querySelectorAll('svg[preserveAspectRatio="none"]').forEach(svg => svg.removeAttribute('preserveAspectRatio'));
      const mediaEls = [...root.querySelectorAll('img:not(.gaiji):not([class*="gaiji"]), svg')]
        .filter(el => !(el.tagName.toLowerCase() === 'img' && el.closest('svg')));
      const txt = (root.textContent || '').replace(/[\s\u3000\u200b]+/g, '');
      if (mediaEls.length === 1 && !txt) {
        root.replaceChildren(mediaEls[0]);
        root.classList.add('rm-image-page');
        scroller.classList.add('rm-image-viewport');
      } else {
        root.classList.remove('rm-image-page');
        scroller.classList.remove('rm-image-viewport');
      }
    }

    // Center the current page's visible block-axis content inside the viewport (vertical centering
    // in horizontal writing, horizontal centering in vertical writing).
    function rmCenterPaginatedPage(root, sc, vertical, tx, ty) {
      const vr = sc.getBoundingClientRect();
      if (vr.width < 40 || vr.height < 40) return;
      let minB = Infinity;
      let maxB = -Infinity;
      const range = document.createRange();
      const visit = (node) => {
        if (node.nodeType === 3) {
          if (!node.nodeValue || !node.nodeValue.trim()) return;
          range.selectNodeContents(node);
          const rects = range.getClientRects();
          for (let i = 0; i < rects.length; i++) {
            const r = rects[i];
            if (r.width < 0.5 || r.height < 0.5) continue;
            const c = vertical ? ((r.top + r.bottom) * 0.5) : ((r.left + r.right) * 0.5);
            const lo = vertical ? vr.top : vr.left;
            const hi = vertical ? vr.bottom : vr.right;
            if (c < lo - 2 || c > hi + 2) continue;
            const b0 = vertical ? r.left : r.top;
            const b1 = vertical ? r.right : r.bottom;
            if (b0 < minB) minB = b0;
            if (b1 > maxB) maxB = b1;
          }
          return;
        }
        if (node.nodeType !== 1) return;
        const tag = node.tagName;
        if (tag === 'SCRIPT' || tag === 'STYLE' || (node.classList && node.classList.contains('rm-sent-break'))) return;
        if (tag === 'IMG' || tag === 'SVG' || tag === 'HR') {
          const r = node.getBoundingClientRect();
          if (r.width >= 0.5 && r.height >= 0.5) {
            const c = vertical ? ((r.top + r.bottom) * 0.5) : ((r.left + r.right) * 0.5);
            const lo = vertical ? vr.top : vr.left;
            const hi = vertical ? vr.bottom : vr.right;
            if (c >= lo - 2 && c <= hi + 2) {
              const b0 = vertical ? r.left : r.top;
              const b1 = vertical ? r.right : r.bottom;
              if (b0 < minB) minB = b0;
              if (b1 > maxB) maxB = b1;
            }
          }
          return;
        }
        const br = node.getBoundingClientRect();
        if (vertical ? (br.bottom < vr.top - 4 || br.top > vr.bottom + 4) : (br.right < vr.left - 4 || br.left > vr.right + 4)) return;
        for (let k = node.firstChild; k; k = k.nextSibling) visit(k);
      };
      for (let k = root.firstChild; k; k = k.nextSibling) visit(k);
      if (!(maxB > minB)) return;
      const vpLo = vertical ? vr.left : vr.top;
      const vpHi = vertical ? vr.right : vr.bottom;
      const span = maxB - minB;
      if (span >= (vpHi - vpLo) - 2) return;
      let delta = Math.round(((vpLo + vpHi) - (minB + maxB)) * 0.5);
      delta = Math.max(Math.ceil(vpLo - minB), Math.min(Math.floor(vpHi - maxB), delta));
      if (!delta) return;
      if (vertical) {
        root.style.transform = ty ? `translate(${delta}px, ${ty}px)` : `translateX(${delta}px)`;
      } else {
        root.style.transform = tx ? `translate(${tx}px, ${delta}px)` : `translateY(${delta}px)`;
      }
    }

    function rmApplyPaginatedOffset(pageIdx) {
      const sc = rmScrollerEl();
      const root = document.getElementById('rm-epub-root');
      if (!sc || !root) return;
      const clamped = Math.max(0, Math.min(rmState.pageCount - 1, pageIdx));
      rmState.pageIndex = clamped;
      if (root.classList.contains('rm-image-page')) {
        root.style.transform = '';
        sc.scrollTop = 0;
        sc.scrollLeft = 0;
        return;
      }
      if (rmState.dir === 'vertical') {
        const stride = rmState.pageH + RM_PAGE_GAP;
        const pos = clamped * stride;
        let ty = 0;
        if (pos + rmState.pageH <= sc.scrollHeight + 1) {
          root.style.transform = '';
          sc.scrollTo({ top: pos, behavior: 'instant' });
        } else {
          sc.scrollTo({ top: 0, behavior: 'instant' });
          ty = -pos;
          root.style.transform = `translateY(${ty}px)`;
        }
        rmCenterPaginatedPage(root, sc, true, 0, ty);
      } else {
        const stride = rmState.pageW + RM_PAGE_GAP;
        const pos = clamped * stride;
        let tx = 0;
        if (pos + rmState.pageW <= sc.scrollWidth + 1) {
          root.style.transform = '';
          sc.scrollTo({ left: pos, behavior: 'instant' });
        } else {
          sc.scrollTo({ left: 0, behavior: 'instant' });
          tx = -pos;
          root.style.transform = `translateX(${tx}px)`;
        }
        rmCenterPaginatedPage(root, sc, false, tx, 0);
      }
    }

    function rmWatchPaginatedAssets(root, keepAtEnd) {
      const secSnap = rmState.secIndex;
      const partSnap = rmState.partIndex;
      const recalc = () => {
        if (!isReadingModeOpen() || rmState.layout !== 'paginated') return;
        if (rmState.secIndex !== secSnap || rmState.partIndex !== partSnap) return;
        const snap = keepAtEnd ? null : rmLayoutAnchor();
        rmMeasurePagination();
        if (keepAtEnd) {
          rmApplyPaginatedOffset(rmState.pageCount - 1);
        } else if (snap) {
          rmRestoreAnchor(snap);
        } else {
          rmApplyPaginatedOffset(Math.min(rmState.pageCount - 1, rmState.pageIndex));
        }
        rmUpdateProgressUI();
      };
      root.querySelectorAll('img').forEach(img => {
        if (!img.complete) img.addEventListener('load', recalc, { once: true });
      });
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(recalc).catch(() => {});
      }
    }

    function rmRenderPaginatedSection(secIdx, opts = {}) {
      const scroller = document.getElementById('rm-scroller');
      const root = document.getElementById('rm-epub-root');
      if (!scroller || !root) return;
      rmState.secIndex = Math.max(0, Math.min(Math.max(0, rmState.sections.length - 1), secIdx));
      root.style.transform = '';
      scroller.scrollTop = 0;
      scroller.scrollLeft = 0;
      rmSetSafeHtml(root, rmState.sections[rmState.secIndex] || `<div class="status-line">${esc(t('rm_no_content'))}</div>`);
      rmNormalizePaginatedSection(root, scroller);
      rmMeasurePagination();
      if (!opts.skipOffset) {
        const targetPage = opts.atEnd
          ? (rmState.pageCount - 1)
          : Math.min(rmState.pageCount - 1, Math.round((opts.inSecRatio || 0) * Math.max(0, rmState.pageCount - 1)));
        rmApplyPaginatedOffset(targetPage);
        rmUpdateProgressUI();
      }
      rmWatchPaginatedAssets(root, !!opts.atEnd);
    }

    function rmRenderPartContent(opts = {}) {
      rmSetEdgeHint(null);
      if (rmState.media === 'manga' && typeof rmRenderMangaPart === 'function') {
        rmRenderMangaPart(opts);
        return;
      }
      const part = rmState.part;
      const stage = document.getElementById('rm-stage');
      rmApplyStageLayoutClasses();
      rmState.sections = [];
      rmState.sectionMembers = [];
      rmState.secCharStarts = [];
      rmState.secCharLens = [];
      rmState.totalPlainChars = 0;
      rmState.secIndex = 0;
      rmState.pageIndex = 0;
      rmState.pageCount = 1;

      const resolveAnchor = () => {
        if (opts.atEnd) return null;
        if (opts.targetAnchor && opts.targetAnchor.anchor_v) return opts.targetAnchor;
        if (opts.restoreExactPos && opts.restoreExactPos.anchor && opts.restoreExactPos.anchor.anchor_v) return opts.restoreExactPos.anchor;
        if (opts.restorePos && rmState.work && rmState.work.anchor_v) return rmState.work;
        return null;
      };

      if (rmState.layout === 'paginated') {
        stage.innerHTML = '<div class="rm-page-viewport" id="rm-scroller"><div class="rm-body rm-epub-root rm-page-content" id="rm-epub-root"></div></div>';
        const root = document.getElementById('rm-epub-root');
        const scroller = document.getElementById('rm-scroller');
        const resolveRatio = () => {
          if (opts.atEnd) return 1.0;
          if (opts.targetRatio != null) return opts.targetRatio;
          if (opts.restorePos && rmState.work && typeof rmState.work.scroll_ratio === 'number') return rmState.work.scroll_ratio;
          return 0;
        };
        if (rmHtmlPart(part)) {
          const doc = rmParseSafeDoc(part.html || '');
          const spineEls = [...doc.body.querySelectorAll(':scope > section.rm-epub-spine')]
            .filter(sec => (sec.textContent || '').trim() || sec.querySelector('img, svg, hr, table'));
          rmState.sections = spineEls.length ? spineEls.map(sec => sec.innerHTML) : [doc.body.innerHTML];
          rmState.sectionMembers = spineEls.length ? spineEls.map(sec => sec.getAttribute('data-member') || '') : [''];
          rmBuildPartCharIndex(root);
          const anchor = resolveAnchor();
          if (anchor) {
            const sIdx = rmAnchorTargetSection(anchor);
            rmBindStageInteractions();
            rmRenderPaginatedSection(sIdx, { skipOffset: true });
            rmRestoreAnchor(anchor);
            rmUpdateProgressUI();
            rmResetTopbarForMode();
            rmFocusStage();
            return;
          }
          if (opts.restoreExactPos) {
            const ep = opts.restoreExactPos;
            const sIdx = Math.max(0, Math.min(rmState.sections.length - 1, ep.secIndex || 0));
            rmBindStageInteractions();
            rmRenderPaginatedSection(sIdx, { inSecRatio: 0 });
            if (ep.pageIndex != null) {
              rmApplyPaginatedOffset(ep.pageIndex);
              rmUpdateProgressUI();
            }
            rmResetTopbarForMode();
            rmFocusStage();
            return;
          }
          const target = opts.atEnd
            ? { secIndex: rmState.sections.length - 1, inSecRatio: 1, atEnd: true }
            : rmRatioToSection(resolveRatio(), rmState.sections.length);
          rmBindStageInteractions();
          rmRenderPaginatedSection(target.secIndex, target);
          rmResetTopbarForMode();
          rmFocusStage();
          return;
        }
        rmState.sections = [''];
        const finishPaginatedLines = () => {
          rmBuildPartCharIndex(root);
          rmBindStageInteractions();
          rmNormalizePaginatedSection(root, scroller);
          rmMeasurePagination();
          const anchor = resolveAnchor();
          if (anchor) {
            rmRestoreAnchor(anchor);
          } else {
            const r = resolveRatio();
            const targetPage = opts.atEnd ? (rmState.pageCount - 1) : Math.min(rmState.pageCount - 1, Math.round(r * Math.max(0, rmState.pageCount - 1)));
            rmApplyPaginatedOffset(targetPage);
          }
          rmUpdateProgressUI();
          rmResetTopbarForMode();
          rmFocusStage();
        };
        const lines = part.lines || [];
        if (!lines.length) {
          root.innerHTML = `<div class="status-line">${esc(t('rm_no_content'))}</div>`;
          finishPaginatedLines();
          return;
        }
        if (part.media === 'subs') {
          rmRenderChunked(root, lines, ln => {
            const ts = ln.start ? `<span class="rm-sub-ts">${esc(ln.start)}</span>` : '';
            return `<div class="rm-sub-line">${ts}<span class="rm-sub-text">${markSubTags(ln.html || '')}</span></div>`;
          }, finishPaginatedLines);
        } else {
          rmRenderChunked(root, lines, ln => `<p class="rm-db-line">${ln.html || ''}</p>`, finishPaginatedLines);
        }
        return;
      }

      // Continuous mode (horizontal scroll or vertical RTL scroll)
      stage.innerHTML = rmState.dir === 'vertical'
        ? '<div class="rm-v-viewport" id="rm-scroller"><div class="rm-body rm-epub-root" id="rm-epub-root"></div></div>'
        : '<div class="rm-body rm-epub-root" id="rm-epub-root"></div>';

      const root = document.getElementById('rm-epub-root');
      const finish = () => {
        {
          const vert = rmState.dir === 'vertical';
          const nav = document.createElement('div');
          nav.className = 'rm-part-nav-end';
          nav.innerHTML = `
            <button type="button" class="btn" ${rmState.partIndex <= 0 ? 'disabled' : ''} onclick="rmStepPart(-1)">${vert ? '' : '← '}${esc(t('rm_prev_part'))}</button>
            <button type="button" class="btn primary" ${rmState.partIndex >= rmState.files.length - 1 ? 'disabled' : ''} onclick="rmStepPart(1)">${esc(t('rm_next_part'))}${vert ? '' : ' →'}</button>`;
          root.appendChild(nav);
        }
        rmBuildPartCharIndex(root);
        rmBindStageInteractions();
        rmMeasurePagination();
        const anchor = resolveAnchor();
        if (anchor) {
          rmRestoreAnchor(anchor);
        } else if (opts.restoreExactPos) {
          const ep = opts.restoreExactPos;
          const sc = rmScrollerEl();
          if (sc && rmState.dir === 'vertical' && ep.rtlDist != null) {
            rmSetRtlDist(sc, ep.rtlDist, false);
          } else if (sc && rmState.dir !== 'vertical' && ep.scrollTop != null) {
            sc.scrollTo({ top: ep.scrollTop, behavior: 'instant' });
          } else {
            rmRestoreScrollRatio(ep.scrollRatio || 0);
          }
        } else if (opts.atEnd) {
          rmRestoreScrollRatio(1.0);
        } else if (opts.targetRatio != null) {
          rmRestoreScrollRatio(opts.targetRatio);
        } else if (opts.restorePos && rmState.work && typeof rmState.work.scroll_ratio === 'number') {
          rmRestoreScrollRatio(rmState.work.scroll_ratio);
        } else {
          rmRestoreScrollRatio(0);
        }
        rmUpdateProgressUI();
        rmResetTopbarForMode();
        rmFocusStage();
      };

      if (rmHtmlPart(part)) {
        rmSetSafeHtml(root, part.html || `<div class="status-line">${esc(t('rm_no_content'))}</div>`);
        finish();
      } else if (part.media === 'subs') {
        const lines = part.lines || [];
        if (!lines.length) {
          root.innerHTML = `<div class="status-line">${esc(t('rm_no_content'))}</div>`;
          finish();
          return;
        }
        rmRenderChunked(root, lines, ln => {
          const ts = ln.start ? `<span class="rm-sub-ts">${esc(ln.start)}</span>` : '';
          return `<div class="rm-sub-line">${ts}<span class="rm-sub-text">${markSubTags(ln.html || '')}</span></div>`;
        }, finish);
      } else {
        const lines = part.lines || [];
        if (!lines.length) {
          root.innerHTML = `<div class="status-line">${esc(t('rm_no_content'))}</div>`;
          finish();
          return;
        }
        rmRenderChunked(root, lines, ln => `<p class="rm-db-line">${ln.html || ''}</p>`, finish);
      }
    }

    function rmScrollerEl() {
      return document.getElementById('rm-scroller') || document.getElementById('rm-stage');
    }

    const RM_SENT_OPEN = '「『（(';
    const RM_SENT_CLOSE = '」』）)';
    const RM_SENT_END = '。！？!?';
    const RM_SPEECH_END = '。！？!?…‥―─';
    const RM_SENT_WS_RE = /[\s\u3000\u200b]/;
    const RM_SENT_INLINE_TAGS = new Set(['SPAN', 'RUBY', 'RB', 'A', 'EM', 'STRONG', 'B', 'I', 'SMALL', 'SUB', 'SUP', 'MARK', 'U', 'S', 'FONT', 'ABBR', 'CITE', 'Q']);

    function rmClearSentenceBreaks(root) {
      if (!root) return;
      const parents = new Set();
      root.querySelectorAll('.rm-sent-break').forEach(el => {
        if (el.parentNode) parents.add(el.parentNode);
        el.remove();
      });
      parents.forEach(p => { try { p.normalize(); } catch (_) {} });
      root.querySelectorAll('.rm-page-push').forEach(el => el.classList.remove('rm-page-push'));
    }

    function rmCollectBlockSentences(block) {
      const items = [];
      (function walk(node) {
        for (let c = node.firstChild; c; c = c.nextSibling) {
          if (c.nodeType === 3) {
            if (c.nodeValue) items.push({ type: 'text', node: c, text: c.nodeValue });
          } else if (c.nodeType === 1) {
            const tag = c.tagName;
            if (tag === 'RT' || tag === 'RP' || tag === 'CODE' || tag === 'PRE' || tag === 'SVG' || tag === 'SCRIPT' || tag === 'STYLE') continue;
            if (c.classList && c.classList.contains('rm-sent-break')) continue;
            if (tag === 'BR') {
              items.push({ type: 'br', node: c });
            } else {
              walk(c);
            }
          }
        }
      })(block);

      const nextNonWs = (itemIdx, charIdx) => {
        for (let k = itemIdx; k < items.length; k++) {
          const it = items[k];
          if (it.type === 'br') return '';
          const s = it.text;
          for (let j = (k === itemIdx ? charIdx : 0); j < s.length; j++) {
            if (!RM_SENT_WS_RE.test(s[j])) return s[j];
          }
        }
        return '';
      };

      const sentences = [];
      let quoteDepth = 0;
      let ended = false;
      let prevChar = '';
      let cur = null;

      for (let k = 0; k < items.length; k++) {
        const it = items[k];
        if (it.type === 'br') {
          if (quoteDepth === 0 && cur) ended = true;
          continue;
        }
        const s = it.text;
        for (let i = 0; i < s.length; i++) {
          const ch = s[i];
          const isWs = RM_SENT_WS_RE.test(ch);
          if (ended) {
            if (isWs) continue;
            if (RM_SENT_END.includes(ch)) {
              if (cur) { cur.endNode = it.node; cur.endOffset = i + 1; }
              prevChar = ch;
              continue;
            }
            if (quoteDepth > 0 && RM_SENT_CLOSE.includes(ch)) {
              quoteDepth--;
              if (cur) { cur.endNode = it.node; cur.endOffset = i + 1; }
              prevChar = ch;
              continue;
            }
            if (cur) sentences.push(cur);
            cur = { startNode: it.node, startOffset: i, endNode: it.node, endOffset: i + 1 };
            ended = false;
          } else if (!isWs) {
            if (!cur) cur = { startNode: it.node, startOffset: i, endNode: it.node, endOffset: i + 1 };
            else { cur.endNode = it.node; cur.endOffset = i + 1; }
          }

          if (RM_SENT_OPEN.includes(ch)) {
            quoteDepth++;
          } else if (RM_SENT_CLOSE.includes(ch)) {
            if (quoteDepth > 0) {
              quoteDepth--;
              if (quoteDepth === 0 && (ch === '」' || ch === '』') && RM_SPEECH_END.includes(prevChar)) {
                const nxt = nextNonWs(k, i + 1);
                if (nxt === '「' || nxt === '『') ended = true;
              }
            }
          } else if (quoteDepth === 0 && RM_SENT_END.includes(ch)) {
            ended = true;
          }
          if (!isWs) prevChar = ch;
        }
      }
      if (cur) sentences.push(cur);
      return sentences;
    }

    function rmIsFirstMeaningfulChild(node) {
      for (let p = node.previousSibling; p; p = p.previousSibling) {
        if (p.nodeType === 3 && !p.nodeValue.replace(/[\s\u3000\u200b]+/g, '')) continue;
        if (p.nodeType === 1 && p.classList && p.classList.contains('rm-sent-break')) continue;
        return false;
      }
      return true;
    }

    function rmInsertSentBreak(block, startNode, startOffset) {
      let target = startNode;
      if (startOffset > 0) {
        if (startNode.parentElement && startNode.parentElement.closest('ruby')) return null;
        target = startNode.splitText(startOffset);
      }
      while (target.parentNode && target.parentNode !== block &&
             target.parentNode.nodeType === 1 && RM_SENT_INLINE_TAGS.has(target.parentNode.tagName) &&
             rmIsFirstMeaningfulChild(target)) {
        target = target.parentNode;
      }
      if (!target.parentNode) return null;
      if (target.parentElement && target.parentElement.closest('ruby')) return null;
      const brk = document.createElement('span');
      brk.className = 'rm-sent-break';
      brk.setAttribute('aria-hidden', 'true');
      target.parentNode.insertBefore(brk, target);
      return brk;
    }

    function rmSentenceSpanInfo(range, rootRect, vertical, pageSize, pageBlockSize) {
      const stride = Math.max(1, pageSize + RM_PAGE_GAP);
      const raw = range.getClientRects();
      const pages = new Map();
      let minPage = Infinity;
      let maxPage = -Infinity;
      for (let i = 0; i < raw.length; i++) {
        const r = raw[i];
        if (r.width < 0.5 || r.height < 0.5) continue;
        const mid = vertical ? ((r.top + r.bottom) * 0.5 - rootRect.top) : ((r.left + r.right) * 0.5 - rootRect.left);
        const pg = Math.max(0, Math.floor((mid + RM_PAGE_GAP * 0.5) / stride));
        if (pg < minPage) minPage = pg;
        if (pg > maxPage) maxPage = pg;
        const lo = vertical ? r.left : r.top;
        const hi = vertical ? r.right : r.bottom;
        const b = pages.get(pg);
        if (!b) pages.set(pg, { min: lo, max: hi });
        else {
          if (lo < b.min) b.min = lo;
          if (hi > b.max) b.max = hi;
        }
      }
      if (!pages.size) return null;
      if (minPage >= maxPage) return { straddles: false, minPage, maxPage };
      let totalBlockSpan = 0;
      pages.forEach(b => { totalBlockSpan += Math.max(0, b.max - b.min); });
      const firstB = pages.get(minPage);
      const usedBefore = vertical ? (rootRect.right - firstB.max) : (firstB.min - rootRect.top);
      return { straddles: true, minPage, maxPage, totalBlockSpan, usedBefore };
    }

    function rmApplySpacerFallback(block, brkEl, isBlockStart, sentRange, info, vertical, pageSize, pageBlockSize) {
      let sp = brkEl;
      if (isBlockStart) {
        block.classList.remove('rm-page-push');
        if (!block.parentNode) return null;
        sp = document.createElement('span');
        sp.className = 'rm-sent-break';
        sp.setAttribute('aria-hidden', 'true');
        block.parentNode.insertBefore(sp, block);
      }
      if (!sp) return null;
      const root = block.closest('#rm-epub-root');
      if (!root) return sp;
      sp.style.width = '1px';
      sp.style.height = '1px';
      const rr = root.getBoundingClientRect();
      const sr = sp.getBoundingClientRect();
      const rem = vertical ? (sr.right - rr.left) : ((rr.top + pageBlockSize) - sr.top);
      let sz = Math.max(1, Math.floor(rem) - 1);
      if (vertical) sp.style.width = sz + 'px';
      else sp.style.height = sz + 'px';
      let check = rmSentenceSpanInfo(sentRange, root.getBoundingClientRect(), vertical, pageSize, pageBlockSize);
      if (check && check.minPage <= info.minPage) {
        sz = Math.max(1, Math.ceil(rem));
        if (vertical) sp.style.width = sz + 'px';
        else sp.style.height = sz + 'px';
      }
      return sp;
    }

    // Push a sentence that straddles a column edge onto the next page so EPUB pagination never
    // cuts mid-sentence (quotes stay together; a sentence longer than one full page stays as is).
    function rmApplySentencePageBreaks(root, scroller, pageW, pageH, vertical) {
      rmClearSentenceBreaks(root);
      if (!root || !scroller || root.classList.contains('rm-image-page')) return;
      const actW = scroller.clientWidth || pageW;
      const actH = scroller.clientHeight || pageH;
      if (actW < 100 || actH < 100) return;
      const pageSize = vertical ? actH : actW;
      const pageBlockSize = vertical ? actW : actH;
      const stride = Math.max(1, pageSize + RM_PAGE_GAP);
      const linePx = Math.max(12, parseFloat(getComputedStyle(root).fontSize) || 18);
      const skipAncestor = 'pre, code, table, figure, svg, h1, h2, h3, h4, h5, h6';
      const childBlock = 'p, div, blockquote, ul, ol, li, table, pre, figure, h1, h2, h3, h4, h5, h6, section, article, hr';
      const blocks = [...root.querySelectorAll('p, li, blockquote, dd, div')].filter(el =>
        !el.classList.contains('rm-code-block') &&
        !el.closest(skipAncestor) &&
        !el.querySelector(childBlock) &&
        (el.textContent || '').trim().length > 0
      );
      if (!blocks.length) return;

      const range = document.createRange();
      let rootRect = root.getBoundingClientRect();
      let pushes = 0;
      const MAX_PUSHES = 500;

      const setSentRange = (sent) => {
        try {
          range.setStart(sent.startNode, sent.startOffset);
          range.setEnd(sent.endNode, sent.endOffset);
          return true;
        } catch (_) {
          return false;
        }
      };

      const pushSentence = (block, si, s, info) => {
        let brkEl = null;
        let ok = false;
        if (si === 0) {
          if (!block.classList.contains('rm-page-push')) {
            block.classList.add('rm-page-push');
            ok = true;
          }
        } else {
          brkEl = rmInsertSentBreak(block, s.startNode, s.startOffset);
          ok = !!brkEl;
        }
        if (!ok) return { pushed: false, brkEl: null };
        rootRect = root.getBoundingClientRect();
        const post = rmCollectBlockSentences(block);
        const cur = post[si];
        if (cur && setSentRange(cur)) {
          const after = rmSentenceSpanInfo(range, rootRect, vertical, pageSize, pageBlockSize);
          // Engines that ignore break-before: column (Gecko) leave the sentence on minPage;
          // fill the remaining block space of minPage with a sized spacer instead.
          if (after && after.minPage <= info.minPage) {
            brkEl = rmApplySpacerFallback(block, brkEl, si === 0, range, info, vertical, pageSize, pageBlockSize);
            rootRect = root.getBoundingClientRect();
          }
        }
        return { pushed: true, brkEl };
      };

      for (let bi = 0; bi < blocks.length && pushes < MAX_PUSHES; bi++) {
        const block = blocks[bi];
        const br = block.getBoundingClientRect();
        if (br.width < 0.5 || br.height < 0.5) continue;
        const first = vertical ? (br.top - rootRect.top + 1) : (br.left - rootRect.left + 1);
        const last = vertical ? (br.bottom - rootRect.top - 1) : (br.right - rootRect.left - 1);
        const bStart = Math.max(0, Math.floor((first + RM_PAGE_GAP * 0.5) / stride));
        const bEnd = Math.max(0, Math.floor((last + RM_PAGE_GAP * 0.5) / stride));
        if (bStart >= bEnd) continue;

        let sentFrom = 0;
        let innerSteps = 0;
        const tried = new Set();
        while (pushes < MAX_PUSHES && innerSteps++ < 60) {
          const sents = rmCollectBlockSentences(block);
          if (sentFrom >= sents.length) break;
          let pushed = false;
          for (let si = sentFrom; si < sents.length; si++) {
            const s = sents[si];
            if (!setSentRange(s)) continue;
            const info = rmSentenceSpanInfo(range, rootRect, vertical, pageSize, pageBlockSize);
            if (!info || !info.straddles) continue;
            const fitsOnePage = (info.maxPage - info.minPage === 1) && (info.totalBlockSpan <= pageBlockSize * 0.92);
            const hasBefore = info.usedBefore >= Math.max(10, linePx * 0.75);
            if (!fitsOnePage || !hasBefore) continue;

            const step = pushSentence(block, si, s, info);
            pushed = step.pushed;
            const brkEl = step.brkEl;
            if (pushed) {
              rootRect = root.getBoundingClientRect();
              // In vertical-rl, splitting a paragraph can pull an earlier sentence across the
              // same column edge. If so, drop this break and push that earlier sentence instead.
              let backIdx = -1;
              let backInfo = null;
              if (brkEl && si > 0 && !tried.has(si)) {
                const post = rmCollectBlockSentences(block);
                for (let pi = Math.max(0, si - 3); pi < si && pi < post.length; pi++) {
                  if (tried.has(pi)) continue;
                  const ps = post[pi];
                  if (!setSentRange(ps)) continue;
                  const pInfo = rmSentenceSpanInfo(range, rootRect, vertical, pageSize, pageBlockSize);
                  if (pInfo && pInfo.straddles && (pInfo.maxPage - pInfo.minPage === 1) &&
                      pInfo.totalBlockSpan <= pageBlockSize * 0.92 &&
                      pInfo.usedBefore >= Math.max(10, linePx * 0.75)) {
                    backIdx = pi;
                    backInfo = pInfo;
                    break;
                  }
                }
              }
              if (backIdx >= 0) {
                tried.add(si);
                const par = brkEl.parentNode;
                brkEl.remove();
                if (par) { try { par.normalize(); } catch (_) {} }
                const fresh = rmCollectBlockSentences(block);
                const bs = fresh[backIdx];
                if (bs) {
                  const backStep = pushSentence(block, backIdx, bs, backInfo);
                  if (backStep.pushed) {
                    tried.add(backIdx);
                    pushes++;
                    rootRect = root.getBoundingClientRect();
                    sentFrom = backIdx + 1;
                    break;
                  }
                }
                rootRect = root.getBoundingClientRect();
                sentFrom = si + 1;
                break;
              }
              tried.add(si);
              pushes++;
              sentFrom = si + 1;
              break;
            }
          }
          if (!pushed) break;
        }
      }
    }

    // Scale EPUB illustrations in continuous scrolling modes using image_scale (25%–100% of stage),
    // allowing images to break out of a narrow text column while leaving small inline icons untouched.
    // An image that loads late, above or beside the place being read, keeps that place: the
    // anchor is held across the resize, and images that land together are sized in one pass
    let rmEpubImageTimer = 0;
    function rmEpubImageLoaded() {
      clearTimeout(rmEpubImageTimer);
      rmEpubImageTimer = setTimeout(() => {
        if (!isReadingModeOpen() || rmState.media !== 'epub' || rmState.layout !== 'continuous') return;
        const snap = rmLayoutAnchor();
        rmResizeEpubImages();
        if (snap) rmRestoreAnchor(snap);
        rmUpdateProgressUI();
      }, 60);
    }
    function rmResizeEpubImages() {
      if (rmState.media !== 'epub' || rmState.layout !== 'continuous') return;
      const stage = document.getElementById('rm-stage');
      const root = document.getElementById('rm-epub-root');
      if (!stage || !root) return;
      const p = rmGetPrefs();
      const pct = Math.max(25, Math.min(100, Number(p.image_scale) || 80)) / 100;
      const boxW = Math.max(120, Math.round((stage.clientWidth - 24) * pct));
      const boxH = Math.max(120, Math.round((stage.clientHeight - 24) * pct));

      const vert = rmState.dir === 'vertical';
      const stRect = stage.getBoundingClientRect();
      const applyBox = (el, natW, natH) => {
        if (!(natW > 0 && natH > 0) || Math.max(natW, natH) < 120) {
          el.classList.remove('rm-scaled-img');
          el.style.removeProperty('width');
          el.style.removeProperty('height');
          el.style.removeProperty('max-width');
          el.style.removeProperty('max-height');
          el.style.removeProperty('transform');
          return;
        }
        const s = Math.min(boxW / natW, boxH / natH, 3);
        const w = Math.max(24, Math.round(natW * s));
        const h = Math.max(24, Math.round(natH * s));
        el.classList.add('rm-scaled-img');
        el.style.setProperty('width', w + 'px', 'important');
        el.style.setProperty('height', h + 'px', 'important');
        el.style.setProperty('max-width', 'none', 'important');
        el.style.setProperty('max-height', 'none', 'important');
        if (vert) {
          el.style.setProperty('transform', 'none', 'important');
          const er = el.getBoundingClientRect();
          const dy = Math.round(((stRect.top + stRect.bottom) - (er.top + er.bottom)) * 0.5);
          if (dy) el.style.setProperty('transform', `translateY(${dy}px)`, 'important');
        } else {
          el.style.removeProperty('transform');
        }
      };

      root.querySelectorAll('img:not(.gaiji):not([class*="gaiji"])').forEach(img => {
        if (img.closest('svg, td, th')) return;
        if (img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {
          applyBox(img, img.naturalWidth, img.naturalHeight);
        } else if (!img.dataset.rmScaleBound) {
          img.dataset.rmScaleBound = '1';
          img.addEventListener('load', rmEpubImageLoaded, { once: true });
        }
      });

      root.querySelectorAll('svg').forEach(svg => {
        if (svg.closest('td, th')) return;
        let vw = 0, vh = 0;
        const vb = svg.viewBox && svg.viewBox.baseVal;
        if (vb && vb.width > 0 && vb.height > 0) {
          vw = vb.width; vh = vb.height;
        } else {
          const im = svg.querySelector('image');
          vw = parseFloat((im && im.getAttribute('width')) || svg.getAttribute('width') || '0');
          vh = parseFloat((im && im.getAttribute('height')) || svg.getAttribute('height') || '0');
        }
        if (vw > 0 && vh > 0) applyBox(svg, vw, vh);
      });
    }

    function rmMeasurePagination() {
      const stage = document.getElementById('rm-stage');
      const scroller = rmScrollerEl();
      const root = document.getElementById('rm-epub-root');
      if (!stage || !scroller || !root) return;

      if (rmState.layout === 'paginated') {
        const isPhone = window.innerWidth <= 720;
        const padY = isPhone ? 18 : 36;
        const p = rmGetPrefs();
        const edgePx = Math.ceil(stage.clientWidth * RM_EDGE_ROOM);
        const padX = isPhone ? 18 : Math.max(56, edgePx * 2 + 16);
        const availW = Math.max(220, stage.clientWidth - padX);
        const availH = Math.max(200, stage.clientHeight - padY);
        const maxPx = (p.max_width || 44) * p.font_size;
        const maxHPx = (p.max_height || 36) * p.font_size;
        const pageW = Math.max(220, Math.min(availW, maxPx));
        const pageH = Math.max(200, Math.min(availH, maxHPx));
        const imgW = Math.max(220, stage.clientWidth - (isPhone ? 12 : 32));
        const imgH = Math.max(200, stage.clientHeight - (isPhone ? 12 : 24));
        stage.style.setProperty('--rm-page-w', pageW + 'px');
        stage.style.setProperty('--rm-page-h', pageH + 'px');
        stage.style.setProperty('--rm-img-page-w', imgW + 'px');
        stage.style.setProperty('--rm-img-page-h', imgH + 'px');
        const actW = scroller.clientWidth || pageW;
        const actH = scroller.clientHeight || pageH;
        rmState.pageW = actW;
        rmState.pageH = actH;
        if (root.classList.contains('rm-image-page')) {
          rmState.pageCount = 1;
          return;
        }
        const prevT = root.style.transform;
        root.style.transform = '';
        if (rmHtmlPart(rmState.part)) {
          // While a slider is dragged the pages flow without sentence breaks; letting go lays them out.
          if (rmDragAnchor) rmClearSentenceBreaks(root);
          else rmApplySentencePageBreaks(root, scroller, actW, actH, rmState.dir === 'vertical');
        }
        if (rmState.dir === 'vertical') {
          const stride = actH + RM_PAGE_GAP;
          const totalH = scroller.scrollHeight;
          rmState.pageCount = Math.max(1, Math.ceil((totalH - 4 + RM_PAGE_GAP) / Math.max(1, stride)));
        } else {
          const stride = actW + RM_PAGE_GAP;
          const totalW = scroller.scrollWidth;
          rmState.pageCount = Math.max(1, Math.ceil((totalW - 4 + RM_PAGE_GAP) / Math.max(1, stride)));
        }
        root.style.transform = prevT;
      } else {
        rmState.pageCount = 1;
        rmResizeEpubImages();
      }
    }

    function rmReadScrollRatio() {
      if (rmState.layout === 'paginated') {
        const count = Math.max(1, rmState.sections.length);
        const pCount = Math.max(1, rmState.pageCount);
        const pIdx = Math.max(0, Math.min(pCount - 1, rmState.pageIndex));
        if (count === 1) return pCount > 1 ? pIdx / (pCount - 1) : 0;
        if (rmState.secIndex === count - 1 && pIdx === pCount - 1) return 1;
        return Math.min(1, (rmState.secIndex + (pCount > 1 ? 0.999 * pIdx / (pCount - 1) : 0)) / count);
      }
      return rmReadSectionRatio();
    }

    function rmRestoreScrollRatio(ratio) {
      const sc = rmScrollerEl();
      if (!sc) return;
      const r = Math.max(0, Math.min(1, Number(ratio) || 0));
      if (rmState.layout === 'paginated') {
        const count = Math.max(1, rmState.sections.length);
        const target = rmRatioToSection(r, count);
        if (count > 1 && target.secIndex !== rmState.secIndex) {
          rmRenderPaginatedSection(target.secIndex, target);
        } else {
          const pIdx = target.atEnd ? (rmState.pageCount - 1) : Math.min(rmState.pageCount - 1, Math.round(target.inSecRatio * Math.max(0, rmState.pageCount - 1)));
          rmApplyPaginatedOffset(pIdx);
        }
        return;
      }
      if (rmState.dir === 'vertical') {
        const maxD = Math.max(0, sc.scrollWidth - sc.clientWidth);
        rmSetRtlDist(sc, r * maxD, false);
      } else {
        const maxY = Math.max(0, sc.scrollHeight - sc.clientHeight);
        sc.scrollTo({ top: r * maxY, behavior: 'instant' });
      }
    }

    function rmTurnPage(delta) {
      if (rmState.media === 'manga' && typeof rmTurnMangaPage === 'function') {
        rmTurnMangaPage(delta);
        return;
      }
      const sc = rmScrollerEl();
      if (!sc) return;
      if (rmState.layout === 'paginated') {
        if (rmBarAutoHideActive()) rmSetTopbarHidden(true);
        const nxt = rmState.pageIndex + delta;
        if (nxt < 0) {
          if (rmState.secIndex > 0) {
            rmRenderPaginatedSection(rmState.secIndex - 1, { atEnd: true });
            rmScheduleSaveProgress();
          } else if (rmState.partIndex > 0) {
            rmLoadPart(rmState.partIndex - 1, { atEnd: true });
          }
          return;
        }
        if (nxt >= rmState.pageCount) {
          if (rmState.secIndex + 1 < rmState.sections.length) {
            rmRenderPaginatedSection(rmState.secIndex + 1, { inSecRatio: 0 });
            rmScheduleSaveProgress();
          } else if (rmState.partIndex + 1 < rmState.files.length) {
            rmLoadPart(rmState.partIndex + 1, {});
          }
          return;
        }
        rmApplyPaginatedOffset(nxt);
        rmUpdateProgressUI();
        rmScheduleSaveProgress();
        return;
      }
      if (rmState.dir === 'vertical') {
        rmSetRtlDist(sc, rmGetRtlDist(sc) + delta * Math.round(sc.clientWidth * 0.8), true);
        return;
      }
      sc.scrollBy({ top: delta * Math.round(sc.clientHeight * 0.85), behavior: 'smooth' });
    }

    function rmFindAnchor(scope, frag) {
      if (!scope || !frag) return null;
      const escId = s => (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&');
      const cands = [frag];
      try {
        const dec = decodeURIComponent(frag);
        if (dec && dec !== frag) cands.push(dec);
      } catch (e) {}
      for (const f of cands) {
        try {
          const el = scope.querySelector(`[id="${escId('rm-ep-' + f)}"]`) || scope.querySelector(`[id="${escId(f)}"]`);
          if (el) return el;
        } catch (e) {}
      }
      return null;
    }

    function rmGoToAnchorInPart(member, frag, allowMemberFallback = false) {
      const part = rmState.part;
      if (!rmHtmlPart(part)) return false;
      if (rmState.layout === 'paginated') {
        let secIdx = rmState.secIndex;
        if (member) {
          secIdx = (rmState.sectionMembers || []).indexOf(member);
          if (secIdx < 0) return false;
        }
        if (frag && !allowMemberFallback && secIdx !== rmState.secIndex) {
          const doc = rmParseSafeDoc(rmState.sections[secIdx] || '');
          if (!rmFindAnchor(doc.body, frag)) return false;
        }
        const prevSec = rmState.secIndex;
        if (secIdx !== rmState.secIndex) rmRenderPaginatedSection(secIdx, { inSecRatio: 0 });
        const root = document.getElementById('rm-epub-root');
        const el = rmFindAnchor(root, frag);
        if (frag && !el && !allowMemberFallback) {
          if (secIdx !== prevSec) rmRenderPaginatedSection(prevSec, { inSecRatio: 0 });
          return false;
        }
        let page = 0;
        if (el && root) {
          const er = el.getBoundingClientRect();
          const rr = root.getBoundingClientRect();
          const off = rmState.dir === 'vertical' ? er.top - rr.top : er.left - rr.left;
          const stride = (rmState.dir === 'vertical' ? rmState.pageH : rmState.pageW) + RM_PAGE_GAP;
          page = Math.max(0, Math.floor(off / Math.max(1, stride)));
        }
        rmApplyPaginatedOffset(page);
        rmUpdateProgressUI();
        rmScheduleSaveProgress();
        return true;
      }
      const root = document.getElementById('rm-epub-root');
      if (!root) return false;
      let scope = root;
      if (member) {
        const q = (window.CSS && CSS.escape) ? CSS.escape(member) : member;
        scope = root.querySelector(`section.rm-epub-spine[data-member="${q}"]`);
        if (!scope) return false;
      }
      const el = frag ? (rmFindAnchor(scope, frag) || (allowMemberFallback && member ? scope : null)) : (member ? scope : null);
      if (!el) return false;
      el.scrollIntoView({ block: 'start', inline: 'start', behavior: 'instant' });
      rmUpdateProgressUI();
      rmScheduleSaveProgress();
      return true;
    }

    async function rmFollowLink(a) {
      const target = a.getAttribute('data-rm-href') || '';
      const cut = target.indexOf('#');
      const member = target ? (cut >= 0 ? target.slice(0, cut) : target) : '';
      const frag = target ? (cut >= 0 ? target.slice(cut + 1) : '') : (a.getAttribute('href') || '').slice(1);
      const beforePos = rmCapturePos();
      if (rmGoToAnchorInPart(member, frag, false)) {
        rmPushLinkHistory(beforePos, rmCapturePos());
        saveMediaState();
        rmSaveProgressNow(false);
        return;
      }
      if (!member || !rmState.part || rmState.media !== 'epub') return;
      let res = null;
      try {
        const excl = rmState.part.source === 'file' ? '&exclude_source=1' : '';
        const r = await fetch(`/api/reading/resolve-link?file=${encodeURIComponent(rmState.part.file)}&target=${encodeURIComponent(target)}${excl}`);
        if (r.ok) res = await r.json();
      } catch (e) {}
      const idx = res ? rmState.files.findIndex(f => f.file === res.file) : -1;
      if (idx < 0) {
        rmToast(t('rm_link_not_found'));
        return;
      }
      if (idx !== rmState.partIndex) await rmLoadPart(idx, {});
      rmGoToAnchorInPart(member, frag, true);
      rmPushLinkHistory(beforePos, rmCapturePos());
      saveMediaState();
      rmSaveProgressNow(false);
    }

    function rmStepPart(delta) {
      const nxt = rmState.partIndex + delta;
      if (nxt >= 0 && nxt < rmState.files.length) rmLoadPart(nxt, {});
    }

    let rmWheelLock = 0;
    function rmBindStageInteractions() {
      const sc = rmScrollerEl();
      const stage = document.getElementById('rm-stage');
      if (!sc || !stage) return;

      sc.onscroll = () => {
        if (rmState.layout !== 'paginated') {
          rmScheduleProgressUI();
          rmScheduleSaveProgress();
          rmOnBarScroll();
        }
      };

      stage.onwheel = e => {
        if (e.ctrlKey) return;
        if (rmState.layout === 'paginated') {
          const raw = Math.abs(e.deltaY) >= Math.abs(e.deltaX)
            ? e.deltaY
            : (rmState.dir === 'vertical' ? -e.deltaX : e.deltaX);
          if (Math.abs(raw) < 4) return;
          e.preventDefault();
          const now = Date.now();
          if (now - rmWheelLock < 120) return;
          rmWheelLock = now;
          rmTurnPage(raw > 0 ? 1 : -1);
          return;
        }
        if (rmState.dir === 'vertical') {
          const delta = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : -e.deltaX;
          if (!delta) return;
          e.preventDefault();
          rmSetRtlDist(sc, rmGetRtlDist(sc) + delta, false);
        }
      };

      stage.onmousemove = e => {
        if (!rmEdgeNavActive() || e.target.closest('a, button, input, summary')) {
          rmSetEdgeHint(null);
          return;
        }
        rmSetEdgeHint(rmEdgeHitSide(e.clientX, stage));
      };
      stage.onmouseleave = () => rmSetEdgeHint(null);

      stage.onmousedown = e => {
        if (e.button === 0 && rmEdgeNavActive() && !e.target.closest('a, button, input, summary') && rmEdgeHitSide(e.clientX, stage)) {
          e.preventDefault();
        }
      };

      stage.onclick = e => {
        const link = e.target.closest('#rm-epub-root a[data-rm-href], #rm-epub-root a[href^="#"]');
        if (link) {
          e.preventDefault();
          rmFollowLink(link);
          return;
        }
        if (e.target.closest('a, button, input, summary')) return;
        const side = rmEdgeHitSide(e.clientX, stage);
        if (rmEdgeNavActive() && side) {
          if (window.getSelection && String(window.getSelection()).trim()) return;
          const forward = rmState.dir === 'vertical' ? side === 'left' : side === 'right';
          rmTurnPage(forward ? 1 : -1);
          return;
        }
        if (window.getSelection && String(window.getSelection()).trim()) return;
        const isTouchOnly = window.matchMedia && window.matchMedia('(hover: none)').matches;
        if (isTouchOnly && rmGetPrefs().furigana === 'hover') {
          const ruby = e.target.closest('ruby');
          if (ruby) {
            const was = ruby.classList.contains('rm-ruby-open');
            stage.querySelectorAll('ruby.rm-ruby-open').forEach(r => r.classList.remove('rm-ruby-open'));
            if (!was) ruby.classList.add('rm-ruby-open');
            return;
          }
          stage.querySelectorAll('ruby.rm-ruby-open').forEach(r => r.classList.remove('rm-ruby-open'));
        }
      };

      stage.ontouchstart = e => {
        if (e.touches.length !== 1) return;
        rmState.touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
      };
      stage.ontouchend = e => {
        if (!rmState.touchStart || rmState.layout !== 'paginated' || !e.changedTouches.length) return;
        const dx = e.changedTouches[0].clientX - rmState.touchStart.x;
        const dy = e.changedTouches[0].clientY - rmState.touchStart.y;
        const dt = Date.now() - rmState.touchStart.t;
        rmState.touchStart = null;
        if (dt < 500 && Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.5) {
          const forward = rmState.dir === 'vertical' ? dx > 0 : dx < 0;
          rmTurnPage(forward ? 1 : -1);
        }
      };
    }

    // Scrolling fires every frame and the progress line reads the anchor from the whole chapter's
    // text, so it updates at most every 120 ms.
    let rmProgressTimer = null;
    function rmScheduleProgressUI() {
      if (rmProgressTimer) return;
      rmProgressTimer = setTimeout(() => {
        rmProgressTimer = null;
        if (isReadingModeOpen()) rmUpdateProgressUI();
      }, 120);
    }

    function rmUpdateProgressUI() {
      const leftEl = document.getElementById('rm-foot-left');
      const rightEl = document.getElementById('rm-foot-right');
      const fillEl = document.getElementById('rm-progress-fill');
      if (!leftEl || !rightEl || !fillEl || !rmState.part) return;
      if (rmState.media === 'manga') {
        const total = Math.max(1, (rmState.part.pages || []).length);
        const cur = Math.max(1, Math.min(total, rmState.mangaPage));
        const pct = Math.round((cur / total) * 100);
        leftEl.textContent = t('rm_page_of', { a: fmt(cur), b: fmt(total) });
        rightEl.textContent = `${t('rm_part_of', { a: fmt(rmState.partIndex + 1), b: fmt(rmState.files.length) })} · ${pct}%`;
        fillEl.style.width = pct + '%';
        return;
      }
      const anchor = rmReadAnchor();
      const totalChars = rmState.totalPlainChars || rmState.part.char_count || 0;
      const ratio = (anchor && totalChars > 0) ? anchor.scroll_ratio : rmReadScrollRatio();
      const pct = Math.round(ratio * 100);
      const readChars = (anchor && totalChars > 0) ? Math.min(totalChars, anchor.char_offset || 0) : Math.round(totalChars * ratio);
      if (rmState.layout === 'paginated') {
        const sCount = Math.max(1, rmState.sections.length);
        if (sCount > 1 && rmState.pageCount === 1) {
          leftEl.textContent = t('rm_page_of', { a: fmt(rmState.secIndex + 1), b: fmt(sCount) });
        } else if (sCount > 1) {
          leftEl.textContent = `${fmt(rmState.secIndex + 1)}/${fmt(sCount)} · ${t('rm_page_of', { a: fmt(rmState.pageIndex + 1), b: fmt(rmState.pageCount) })}`;
        } else {
          leftEl.textContent = t('rm_page_of', { a: fmt(rmState.pageIndex + 1), b: fmt(rmState.pageCount) });
        }
      } else {
        leftEl.textContent = totalChars ? `${t('rm_chars', { n: fmt(readChars) })} / ${t('rm_chars', { n: fmt(totalChars) })}` : '';
      }
      rightEl.textContent = `${t('rm_part_of', { a: fmt(rmState.partIndex + 1), b: fmt(rmState.files.length) })} · ${pct}%`;
      fillEl.style.width = pct + '%';
    }

    function rmToggleFooterMin() {
      const f = document.getElementById('rm-footer');
      if (f) f.classList.toggle('rm-footer-min');
    }

    function rmScheduleSaveProgress() {
      clearTimeout(rmState.saveTimer);
      rmState.saveTimer = setTimeout(() => rmSaveProgressNow(false), 700);
    }

    function rmSaveProgressNow(useKeepalive) {
      if (!rmState.part || !rmState.media || !rmState.folder) return;
      if (!isReadingModeOpen() && !useKeepalive) return;
      if (rmState.part.file !== (rmState.files[rmState.partIndex] || {}).file) return;
      const anchor = rmLayoutAnchor();
      const ratio = anchor
        ? anchor.scroll_ratio
        : (rmState.media === 'manga'
          ? (rmState.mangaPage - 1) / Math.max(1, (rmState.part.pages || []).length - 1)
          : rmReadScrollRatio());
      const patch = {
        file: rmState.part.file,
        part_index: rmState.partIndex,
        anchor_v: 1,
        scroll_ratio: ratio,
        char_offset: anchor ? (anchor.char_offset || 0) : Math.round((rmState.part.char_count || 0) * ratio),
        sec_index: anchor ? (anchor.sec_index || 0) : (rmState.secIndex || 0),
        quote: anchor ? (anchor.quote || '') : '',
        page: rmState.media === 'manga' ? ((anchor && anchor.page) || rmState.mangaPage) : (rmState.pageIndex + 1),
      };
      // Each save names its own page_frac and edge, null for none, so one from another layout
      // is not left behind.
      patch.page_frac = (anchor && anchor.page_frac != null) ? anchor.page_frac : null;
      patch.edge = (rmState.layout !== 'paginated' && anchor && typeof anchor.edge === 'number') ? anchor.edge : null;
      rmState.work = { ...(rmState.work || {}), ...patch };
      const payload = JSON.stringify({ media: rmState.media, folder: rmState.folder, work: patch });
      try {
        fetch('/api/reading/state', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...API_HEADERS },
          body: payload,
          keepalive: !!useKeepalive,
        }).catch(() => {});
      } catch (e) {}
    }

    function rmSetDir(mode) {
      const nextDir = (mode === 'vertical' || mode === 'horizontal') ? mode : 'auto';
      return rmUpdatePrefs({ writing_mode: nextDir });
    }

    function rmSetLayout(layout) {
      if (layout !== 'paginated' && layout !== 'continuous') return;
      return rmUpdatePrefs({ layout });
    }

    async function rmSaveWorkOverride(patch) {
      rmState.work = { ...(rmState.work || {}), ...patch };
      const needsRelayout = patch && ('writing_mode' in patch || 'layout' in patch);
      if (needsRelayout) rmApplyPrefsToDom(true);
      await apiPost('/api/reading/state', { media: rmState.media, folder: rmState.folder, work: patch }).catch(() => null);
    }

    function rmFormatBookmarkPlace(bm) {
      if (!bm) return '';
      const base = bm.label || bm.file || '';
      if (rmState.media === 'manga' && bm.page) return `${base} · ${t('page_n', { n: fmt(bm.page) })}`;
      if (bm.scroll_ratio != null) return `${base} · ${Math.round((bm.scroll_ratio || 0) * 100)}%`;
      return base;
    }

    function rmUpdateBookmarkBtn() {
      const btn = document.getElementById('rm-bm-btn');
      if (!btn) return;
      const bm = rmState.work && rmState.work.bookmark;
      btn.classList.toggle('rm-bm-active', !!bm);
      btn.title = bm ? `${t('rm_bookmark_go')} (${rmFormatBookmarkPlace(bm)})` : t('rm_bookmark_set');
    }

    async function rmSetBookmarkNow() {
      if (!rmState.part) return;
      const anchor = rmReadAnchor();
      const item = rmState.files[rmState.partIndex] || {};
      const curRatio = anchor ? anchor.scroll_ratio : (rmState.media === 'manga' ? 0 : rmReadScrollRatio());
      const nextBm = {
        file: rmState.part.file,
        anchor_v: 1,
        scroll_ratio: curRatio,
        page: rmState.media === 'manga' ? ((anchor && anchor.page) || rmState.mangaPage) : (rmState.pageIndex + 1),
        char_offset: anchor ? (anchor.char_offset || 0) : Math.round((rmState.part.char_count || 0) * curRatio),
        sec_index: anchor ? (anchor.sec_index || 0) : (rmState.secIndex || 0),
        quote: anchor ? (anchor.quote || '') : '',
        label: item.title || rmState.part.file,
      };
      if (anchor && anchor.page_frac != null) nextBm.page_frac = anchor.page_frac;
      if (anchor && typeof anchor.edge === 'number') nextBm.edge = anchor.edge;
      await rmSaveWorkOverride({ bookmark: nextBm });
      rmUpdateBookmarkBtn();
      rmRenderToc();
      const bmMenu = document.getElementById('rm-bm-menu');
      if (bmMenu) bmMenu.hidden = true;
      rmToast(`${t('rm_bookmark_saved')} ${rmFormatBookmarkPlace(nextBm)}`);
    }

    async function rmGoBookmark() {
      const bm = rmState.work && rmState.work.bookmark;
      const bmMenu = document.getElementById('rm-bm-menu');
      if (bmMenu) bmMenu.hidden = true;
      if (!bm) return;
      const idx = rmState.files.findIndex(f => f.file === bm.file);
      if (idx < 0) { rmToast(t('rm_place_gone')); return; }
      if (idx !== rmState.partIndex) {
        await rmLoadPart(idx, { targetAnchor: bm.anchor_v ? bm : null, targetRatio: bm.scroll_ratio, targetPage: bm.page || 1 });
      } else if (rmState.media === 'manga') {
        rmRestoreAnchor(bm);
      } else {
        rmRestoreAnchor(bm);
        rmUpdateProgressUI();
      }
      rmToast(t('rm_bookmark_jumped'));
    }

    async function rmClearBookmark() {
      const bmMenu = document.getElementById('rm-bm-menu');
      if (bmMenu) bmMenu.hidden = true;
      await rmSaveWorkOverride({ bookmark: null });
      rmUpdateBookmarkBtn();
      rmRenderToc();
      rmToast(t('rm_bookmark_cleared'));
    }

    function rmOnBookmarkClick() {
      rmCloseFontPopup(false);
      const notesp = document.getElementById('rm-notes-panel');
      if (notesp && !notesp.hidden && typeof rmToggleNotes === 'function') rmToggleNotes(false);
      const bm = rmState.work && rmState.work.bookmark;
      if (!bm) { rmSetBookmarkNow(); return; }
      const menu = document.getElementById('rm-bm-menu');
      if (!menu) return;
      if (!menu.hidden) { menu.hidden = true; rmResetTopbarForMode(); return; }
      menu.innerHTML = `
        <div class="rm-bm-where">${esc(rmFormatBookmarkPlace(bm))}</div>
        <div class="rm-bm-actions">
          <button type="button" class="btn primary" onclick="rmGoBookmark()">${esc(t('rm_bookmark_go'))}</button>
          <button type="button" class="btn" onclick="rmSetBookmarkNow()">${esc(t('rm_bookmark_move'))}</button>
          <button type="button" class="btn" onclick="rmClearBookmark()">${esc(t('rm_bookmark_clear'))}</button>
        </div>`;
      menu.hidden = false;
      rmSetTopbarHidden(false, 'overlay');
    }

    function rmCycleFurigana() {
      if (rmState.media === 'manga' && !rmMangaTextOnly(rmState.part)) return;
      const order = ['on', 'hover', 'off'];
      const cur = rmGetPrefs().furigana;
      const next = order[(order.indexOf(cur) + 1) % order.length];
      rmUpdatePrefs({ furigana: next });
      rmToast(`${t('rm_furi')} ${t('rm_furi_' + next)}`);
    }

    // The words every entry shares, up to a ｜ (a book's author and title), are said once in the header.
    function rmTocCommonHead(titles) {
      if (!titles.length) return '';
      let head = titles[0];
      for (const s of titles) {
        let n = 0;
        while (n < head.length && n < s.length && head[n] === s[n]) n++;
        head = head.slice(0, n);
        if (!head) return '';
      }
      const cut = head.lastIndexOf('｜');
      return cut < 0 ? '' : head.slice(0, cut + 1);
    }
    function rmRenderToc() {
      const list = document.getElementById('rm-toc-list');
      if (!list) return;
      const bmFile = rmState.work && rmState.work.bookmark && rmState.work.bookmark.file;
      const head = rmTocCommonHead(rmState.files.map(it => it.title || it.file));
      const label = s => (head && s.startsWith(head) && s.length > head.length ? s.slice(head.length) : s);
      let lastGroup = '';
      const out = [];
      rmState.files.forEach((it, i) => {
        const g = it.subtitle_group || (it.book_folder && { kind: 'book', label: it.book_folder });
        if (g && g.kind !== 'other') {
          const gName = g.kind === 'season' ? t('group_season', { n: g.order })
            : g.kind === 'movie' ? t('group_movie') : g.kind === 'ova' ? t('group_ova')
            : g.kind === 'special' ? t('group_special') : g.label;
          if (gName && gName !== lastGroup) {
            lastGroup = gName;
            out.push(`<div class="rm-toc-group">${esc(gName)}</div>`);
          }
        }
        const bmBadge = bmFile && it.file === bmFile ? '<span class="rm-toc-bm" aria-hidden="true">★</span>' : '';
        out.push(`<button type="button" class="rm-toc-item ${i === rmState.partIndex ? 'active' : ''}" data-idx="${i}" onclick="rmJumpToc(${i})"><span>${esc(label(it.title || it.file))}</span>${bmBadge}</button>`);
      });
      list.innerHTML = out.join('');
    }
    function rmHighlightToc() {
      document.querySelectorAll('#rm-toc-list .rm-toc-item').forEach((el, i) => {
        el.classList.toggle('active', i === rmState.partIndex);
      });
    }
    function rmJumpToc(idx) {
      rmToggleToc(false);
      rmLoadPart(idx, {});
    }
    function rmToggleToc(force) {
      const el = document.getElementById('rm-toc-drawer');
      if (!el) return;
      const show = force === undefined ? el.hidden : !!force;
      el.hidden = !show;
      if (show) {
        rmCloseFontPopup(false);
        const setp = document.getElementById('rm-settings-panel');
        if (setp) setp.hidden = true;
        const notesp = document.getElementById('rm-notes-panel');
        if (notesp) notesp.hidden = true;
        const bmMenu = document.getElementById('rm-bm-menu');
        if (bmMenu) bmMenu.hidden = true;
        rmSetTopbarHidden(false, 'overlay');
        const active = el.querySelector('.rm-toc-item.active');
        if (active) active.scrollIntoView({ block: 'center' });
      } else {
        rmResetTopbarForMode();
        rmFocusStage();
      }
    }

    function rmToggleSettings(force) {
      const el = document.getElementById('rm-settings-panel');
      if (!el) return;
      const show = force === undefined ? el.hidden : !!force;
      el.hidden = !show;
      if (show) {
        const toc = document.getElementById('rm-toc-drawer');
        if (toc) toc.hidden = true;
        const notesp = document.getElementById('rm-notes-panel');
        if (notesp) notesp.hidden = true;
        const bmMenu = document.getElementById('rm-bm-menu');
        if (bmMenu) bmMenu.hidden = true;
        rmSetTopbarHidden(false, 'overlay');
        rmRenderSettingsPanel();
      } else {
        rmCloseFontPopup(false);
        rmResetTopbarForMode();
        rmFocusStage();
      }
    }

    function rmRenderSettingsPanel() {
      const card = document.getElementById('rm-settings-card');
      if (!card) return;
      const prevBody = card.querySelector('.rm-settings-body');
      const prevScroll = prevBody ? prevBody.scrollTop : 0;
      const p = rmGetPrefs();
      const w = rmState.work || {};
      const dirVal = p.writing_mode || 'auto';
      const layoutVal = rmState.layout;
      const themes = [
        ['app', t('rm_theme_app')], ['haze', t('theme_haze')], ['paper', t('theme_paper')],
        ['sepia', t('rm_theme_sepia')], ['night', t('theme_night')], ['midnight', t('theme_midnight')],
      ];
      const isManga = rmState.media === 'manga';
      const mangaText = isManga && rmMangaTextOnly(rmState.part);
      const isSubs = rmState.media === 'subs';
      const bm = w.bookmark;
      card.innerHTML = `
        <div class="rm-drawer-head">
          <span>${esc(t('rm_settings'))}</span>
          <button type="button" class="sq-btn" onclick="rmToggleSettings(false)" aria-label="${esc(t('close'))}">✕</button>
        </div>
        <div class="rm-settings-body">
          ${!isManga ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_dir'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${dirVal === 'auto' ? 'active' : ''}" onclick="rmSetDir('auto')">${esc(t('rm_dir_auto'))}</button>
              <button type="button" class="seg-btn ${dirVal === 'vertical' ? 'active' : ''}" onclick="rmSetDir('vertical')">${esc(t('rm_dir_vertical'))}</button>
              <button type="button" class="seg-btn ${dirVal === 'horizontal' ? 'active' : ''}" onclick="rmSetDir('horizontal')">${esc(t('rm_dir_horizontal'))}</button>
            </div>
          </div>
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_layout'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${layoutVal === 'paginated' ? 'active' : ''}" onclick="rmSetLayout('paginated')">${esc(t('rm_layout_paginated'))}</button>
              <button type="button" class="seg-btn ${layoutVal === 'continuous' ? 'active' : ''}" onclick="rmSetLayout('continuous')">${esc(t('rm_layout_continuous'))}</button>
            </div>
          </div>` : `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_manga_layout'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.manga_layout === 'single' ? 'active' : ''}" onclick="rmUpdatePrefs({manga_layout:'single'})">${esc(t('rm_manga_single'))}</button>
              <button type="button" class="seg-btn ${p.manga_layout === 'strip' ? 'active' : ''}" onclick="rmUpdatePrefs({manga_layout:'strip'})">${esc(t('rm_manga_strip'))}</button>
            </div>
          </div>
          ${!mangaText ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_manga_boxes'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.manga_boxes === 'hover' ? 'active' : ''}" onclick="rmUpdatePrefs({manga_boxes:'hover'})">${esc(t('rm_manga_boxes_hover'))}</button>
              <button type="button" class="seg-btn ${p.manga_boxes === 'always' ? 'active' : ''}" onclick="rmUpdatePrefs({manga_boxes:'always'})">${esc(t('rm_manga_boxes_always'))}</button>
              <button type="button" class="seg-btn ${p.manga_boxes === 'off' ? 'active' : ''}" onclick="rmUpdatePrefs({manga_boxes:'off'})">${esc(t('rm_manga_boxes_off'))}</button>
            </div>
          </div>
          ${p.manga_layout === 'strip' ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_image_scale'))}</span>
            <div class="rm-range-row">
              <input type="range" min="25" max="100" step="5" value="${p.image_scale || 80}" oninput="rmLiveRangePref('image_scale', Number(this.value), this.nextElementSibling, this.value + '%')" onchange="rmUpdatePrefs({image_scale:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.image_scale || 80}%</span>
            </div>
          </div>` : ''}` : ''}`}
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_theme'))}</span>
            <div class="rm-theme-grid">${themes.map(([v, lbl]) =>
              `<button type="button" class="btn rm-theme-chip ${p.theme === v ? 'active' : ''}" onclick="rmUpdatePrefs({theme:'${v}'})">${esc(lbl)}</button>`
            ).join('')}</div>
          </div>
          ${!isManga || mangaText ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_furi'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.furigana === 'on' ? 'active' : ''}" onclick="rmUpdatePrefs({furigana:'on'})">${esc(t('rm_furi_on'))}</button>
              <button type="button" class="seg-btn ${p.furigana === 'hover' ? 'active' : ''}" onclick="rmUpdatePrefs({furigana:'hover'})">${esc(t('rm_furi_hover'))}</button>
              <button type="button" class="seg-btn ${p.furigana === 'off' ? 'active' : ''}" onclick="rmUpdatePrefs({furigana:'off'})">${esc(t('rm_furi_off'))}</button>
            </div>
          </div>
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_font'))}</span>
            ${rmFontSelectHtml(p.font_family, 'reader')}
          </div>
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_font_weight'))}</span>
            <div class="rm-range-row">
              <input type="range" min="200" max="900" step="100" value="${p.font_weight || 400}" oninput="rmLiveRangePref('font_weight', Number(this.value), this.nextElementSibling, this.value)" onchange="rmUpdatePrefs({font_weight:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.font_weight || 400}</span>
            </div>
          </div>
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_font_size'))}</span>
            <div class="rm-range-row">
              <input type="range" min="12" max="36" step="1" value="${p.font_size}" oninput="rmLiveRangePref('font_size', Number(this.value), this.nextElementSibling, this.value + 'px')" onchange="rmUpdatePrefs({font_size:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.font_size}px</span>
            </div>
          </div>
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_line_height'))}</span>
            <div class="rm-range-row">
              <input type="range" min="1" max="2.6" step="0.05" value="${p.line_height}" oninput="rmLiveRangePref('line_height', Number(this.value), this.nextElementSibling, Number(this.value).toFixed(2))" onchange="rmUpdatePrefs({line_height:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${Number(p.line_height).toFixed(2)}</span>
            </div>
          </div>
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_max_width'))}</span>
            <div class="rm-range-row">
              <input type="range" min="10" max="72" step="2" value="${p.max_width}" oninput="rmLiveRangePref('max_width', Number(this.value), this.nextElementSibling, this.value + 'em')" onchange="rmUpdatePrefs({max_width:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.max_width}em</span>
            </div>
          </div>
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_max_height'))}</span>
            <div class="rm-range-row">
              <input type="range" min="10" max="72" step="2" value="${p.max_height || 36}" oninput="rmLiveRangePref('max_height', Number(this.value), this.nextElementSibling, this.value + 'em')" onchange="rmUpdatePrefs({max_height:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.max_height || 36}em</span>
            </div>
          </div>
          ${rmState.media === 'epub' && layoutVal === 'continuous' ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_image_scale'))}</span>
            <div class="rm-range-row">
              <input type="range" min="25" max="100" step="5" value="${p.image_scale || 80}" oninput="rmLiveRangePref('image_scale', Number(this.value), this.nextElementSibling, this.value + '%')" onchange="rmUpdatePrefs({image_scale:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.image_scale || 80}%</span>
            </div>
          </div>` : ''}` : ''}
          ${isSubs ? `
          <div class="rm-set-row-inline">
            <span class="rm-set-label">${esc(t('rm_sub_timestamps'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.sub_timestamps ? 'active' : ''}" onclick="rmUpdatePrefs({sub_timestamps:true})">${esc(t('lib_cache_on'))}</button>
              <button type="button" class="seg-btn ${!p.sub_timestamps ? 'active' : ''}" onclick="rmUpdatePrefs({sub_timestamps:false})">${esc(t('lib_cache_off'))}</button>
            </div>
          </div>` : ''}
          ${(isManga || layoutVal === 'paginated') && window.innerWidth > 720 ? `
          <div class="rm-set-row-inline">
            <span class="rm-set-label">${esc(t('rm_edge_click'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.edge_click_nav !== false ? 'active' : ''}" onclick="rmUpdatePrefs({edge_click_nav:true})">${esc(t('lib_cache_on'))}</button>
              <button type="button" class="seg-btn ${p.edge_click_nav === false ? 'active' : ''}" onclick="rmUpdatePrefs({edge_click_nav:false})">${esc(t('lib_cache_off'))}</button>
            </div>
          </div>
          ${p.edge_click_nav !== false ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_edge_click_width'))}</span>
            <div class="rm-range-row">
              <input type="range" min="5" max="35" step="1" value="${p.edge_click_width || 12}" oninput="rmLiveRangePref('edge_click_width', Number(this.value), this.nextElementSibling, this.value + '%')" onchange="rmUpdatePrefs({edge_click_width:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.edge_click_width || 12}%</span>
            </div>
          </div>` : ''}` : ''}
          <div class="rm-set-row-inline">
            <span class="rm-set-label">${esc(t('rm_progress_show'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.show_progress ? 'active' : ''}" onclick="rmUpdatePrefs({show_progress:true})">${esc(t('lib_cache_on'))}</button>
              <button type="button" class="seg-btn ${!p.show_progress ? 'active' : ''}" onclick="rmUpdatePrefs({show_progress:false})">${esc(t('lib_cache_off'))}</button>
            </div>
          </div>
          ${rmCanHoverTopbar() ? `
          <div class="rm-set-row-inline">
            <span class="rm-set-label">${esc(t('rm_auto_hide_bar'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.auto_hide_bar ? 'active' : ''}" onclick="rmUpdatePrefs({auto_hide_bar:true})">${esc(t('lib_cache_on'))}</button>
              <button type="button" class="seg-btn ${!p.auto_hide_bar ? 'active' : ''}" onclick="rmUpdatePrefs({auto_hide_bar:false})">${esc(t('lib_cache_off'))}</button>
            </div>
          </div>` : ''}
          ${rmIsScrollableBarMode() ? `
          <div class="rm-set-row-inline">
            <span class="rm-set-label">${esc(t('rm_hide_bar_scroll'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.hide_bar_scroll ? 'active' : ''}" onclick="rmUpdatePrefs({hide_bar_scroll:true})">${esc(t('lib_cache_on'))}</button>
              <button type="button" class="seg-btn ${!p.hide_bar_scroll ? 'active' : ''}" onclick="rmUpdatePrefs({hide_bar_scroll:false})">${esc(t('lib_cache_off'))}</button>
            </div>
          </div>` : ''}
          ${isManga && !mangaText && p.manga_layout !== 'strip' ? `
          <div class="rm-set-row-inline">
            <button type="button" class="btn" onclick="rmMangaFit(false); rmToggleSettings(false)">${esc(t('rm_zoom_reset'))}</button>
          </div>` : ''}
          ${bm ? `<div class="rm-set-row">
            <span class="rm-set-label">${esc(rmFormatBookmarkPlace(bm))}</span>
            <div class="rm-set-row-inline">
              <button type="button" class="btn primary" onclick="rmToggleSettings(false); rmGoBookmark()">${esc(t('rm_bookmark_go'))}</button>
              <button type="button" class="btn" onclick="rmSetBookmarkNow().then(rmRenderSettingsPanel)">${esc(t('rm_bookmark_move'))}</button>
              <button type="button" class="btn" onclick="rmClearBookmark().then(rmRenderSettingsPanel)">${esc(t('rm_bookmark_clear'))}</button>
            </div>
          </div>` : ''}
        </div>
        <div class="rm-settings-foot">
          <button type="button" class="btn" onclick="rmResetPrefs()">${esc(t('rm_reset_defaults'))}</button>
          <button type="button" class="btn" onclick="rmOpenInSettings()">${esc(t('rm_open_settings'))}</button>
        </div>`;
      const nextBody = card.querySelector('.rm-settings-body');
      if (nextBody && prevScroll > 0) nextBody.scrollTop = prevScroll;
      rmFontSyncOpenPopup();
    }

    function rmFocusStage() {
      const stage = document.getElementById('rm-stage');
      if (stage) {
        try { stage.focus({ preventScroll: true }); } catch (e) {}
      }
    }

    let rmLastWide = window.innerWidth > 720;
    let rmResizeAnchor = null;
    let rmResizeTimer = null;
    // A paginated relayout of a long chapter takes about a second (the sentence page breaks), and
    // dragging a window edge fires dozens of resize events: lay out once, when the size settles.
    function rmOnResize() {
      if (!isReadingModeOpen()) {
        rmLastWide = window.innerWidth > 720;
        return;
      }
      if (rmState.part && !rmResizeAnchor) rmResizeAnchor = rmLayoutAnchor();
      clearTimeout(rmResizeTimer);
      rmResizeTimer = setTimeout(rmRelayoutAfterResize, 160);
    }

    function rmRelayoutAfterResize() {
      rmResizeTimer = null;
      const anchor = rmResizeAnchor;
      rmResizeAnchor = null;
      const wide = window.innerWidth > 720;
      const crossed = wide !== rmLastWide;
      rmLastWide = wide;
      if (!isReadingModeOpen()) return;
      if (crossed) {
        rmSetEdgeHint(null);
        rmApplyPrefsToDom(true, true, anchor);
        rmResetTopbarForMode();
        return;
      }
      if (rmState.media === 'manga') {
        const mStage = document.getElementById('rm-manga-stage');
        if (mStage && mStage.classList.contains('rm-manga-strip')) {
          rmResizeStripPages();
          if (anchor) rmRestoreAnchor(anchor);
        } else if (typeof rmMangaFit === 'function') {
          rmMangaFit(false);
        }
        return;
      }
      rmMeasurePagination();
      if (anchor) rmRestoreAnchor(anchor);
      rmUpdateProgressUI();
    }

    function rmIsVerticalScrollMode() {
      if (rmState.media === 'manga') {
        return rmGetPrefs().manga_layout === 'strip' || !!(rmState.part && (rmState.part.source === 'db' || rmMangaTextOnly(rmState.part)));
      }
      return rmState.dir === 'horizontal' && rmState.layout === 'continuous';
    }

    // In a scrolling layout a tap moves by most of a screen, smoothly; holding the key glides at a
    // steady speed until it is let go, instead of restarting a jump on every repeat.
    const RM_GLIDE_SCREENS_PER_S = 0.9;
    const rmGlide = { key: null, delta: 0, raf: 0, last: 0, pos: 0 };
    function rmGlideScroller() {
      return rmState.media === 'manga' ? document.getElementById('rm-manga-stage') : rmScrollerEl();
    }
    function rmGlideAcross() {
      return rmState.media !== 'manga' && rmState.dir === 'vertical';
    }
    function rmGlideDelta(e) {
      if (e.shiftKey) return 0;
      const k = e.key.toLowerCase();
      if (rmIsVerticalScrollMode()) {
        if (k === 'arrowdown') return 1;
        if (k === 'arrowup') return -1;
      } else if (rmState.media === 'manga' || rmState.layout === 'paginated' || rmState.dir !== 'vertical') {
        return 0;
      } else {
        if (k === 'arrowleft') return 1;
        if (k === 'arrowright') return -1;
      }
      const rtl = rmState.media === 'manga' || rmState.dir === 'vertical';
      if (k === 'd') return rtl ? -1 : 1;
      if (k === 'a') return rtl ? 1 : -1;
      return 0;
    }
    function rmGlideFrame(ts) {
      const sc = rmGlideScroller();
      if (!rmGlide.key || !sc || !isReadingModeOpen()) { rmStopGlide(); return; }
      const dt = rmGlide.last ? Math.min(50, ts - rmGlide.last) : 0;
      rmGlide.last = ts;
      const across = rmGlideAcross();
      const size = across ? sc.clientWidth : sc.clientHeight;
      const maxPos = across ? Math.max(0, sc.scrollWidth - sc.clientWidth) : Math.max(0, sc.scrollHeight - sc.clientHeight);
      rmGlide.pos = Math.max(0, Math.min(maxPos, rmGlide.pos + rmGlide.delta * size * RM_GLIDE_SCREENS_PER_S * dt / 1000));
      if (across) rmSetRtlDist(sc, rmGlide.pos);
      else sc.scrollTo({ top: rmGlide.pos, behavior: 'instant' });
      rmGlide.raf = requestAnimationFrame(rmGlideFrame);
    }
    function rmStartGlide(key, delta) {
      if (rmGlide.key === key && rmGlide.delta === delta) return;
      rmStopGlide();
      const sc = rmGlideScroller();
      if (!sc) return;
      rmGlide.key = key;
      rmGlide.delta = delta;
      rmGlide.last = 0;
      rmGlide.pos = rmGlideAcross() ? rmGetRtlDist(sc) : sc.scrollTop;
      rmGlide.raf = requestAnimationFrame(rmGlideFrame);
    }
    function rmStopGlide() {
      if (rmGlide.raf) cancelAnimationFrame(rmGlide.raf);
      const was = rmGlide.key;
      rmGlide.raf = 0;
      rmGlide.key = null;
      if (was && isReadingModeOpen()) rmScheduleSaveProgress();
    }
    function rmOnKeyUp(e) {
      if (rmGlide.key && e.key.toLowerCase() === rmGlide.key) rmStopGlide();
    }

    let rmLastNavTime = 0;
    function rmOnKeyDown(e) {
      if (!isReadingModeOpen()) return;
      if (e.isComposing || e.keyCode === 229 || isComposing || justConfirmed) return;
      if (e.ctrlKey || e.altKey || e.metaKey) return;
      const scModal = document.getElementById('shortcuts-modal');
      const isHelpKey = e.key === '?' || (e.shiftKey && (e.code === 'Slash' || e.key === '/'));
      if (scModal && scModal.classList.contains('open')) {
        if (e.key === 'Escape' || isHelpKey) { e.preventDefault(); toggleShortcutsModal(); }
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        const bmMenu = document.getElementById('rm-bm-menu');
        if (bmMenu && !bmMenu.hidden) { bmMenu.hidden = true; rmFocusStage(); return; }
        const notesp = document.getElementById('rm-notes-panel');
        if (notesp && !notesp.hidden && typeof rmToggleNotes === 'function') { rmToggleNotes(false); rmFocusStage(); return; }
        const setp = document.getElementById('rm-settings-panel');
        const toc = document.getElementById('rm-toc-drawer');
        if (setp && !setp.hidden) { rmToggleSettings(false); rmFocusStage(); return; }
        if (toc && !toc.hidden) { rmToggleToc(false); rmFocusStage(); return; }
        if (rmState.media === 'manga' && rmPz.imgW && rmPz.scale > rmPz.fitScale * 1.04) {
          rmMangaFit(false);
          return;
        }
        closeReadingMode();
        return;
      }

      const tag = document.activeElement ? document.activeElement.tagName : '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (isHelpKey) { e.preventDefault(); rmStopGlide(); toggleShortcutsModal(); return; }

      const glideDelta = rmGlideDelta(e);
      if (glideDelta) {
        e.preventDefault();
        if (e.repeat) rmStartGlide(e.key.toLowerCase(), glideDelta);
        else { rmStopGlide(); rmTurnPage(glideDelta); }
        return;
      }

      const vScroll = rmIsVerticalScrollMode();
      if (vScroll) {
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          if (rmState.media !== 'manga') {
            e.preventDefault();
            if (!e.repeat) rmStepPart(e.key === 'ArrowRight' ? 1 : -1);
          }
          return;
        }
      } else if (rmState.media !== 'manga' && rmState.dir === 'vertical' && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault();
        if (!e.repeat) rmStepPart(e.key === 'ArrowDown' ? 1 : -1);
        return;
      } else if (rmState.media === 'manga' && rmPz.imgW && rmPz.scale > rmPz.fitScale * 1.04) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          rmPz.ty += e.key === 'ArrowDown' ? -110 : 110;
          rmApplyPzTransform();
          return;
        }
      } else if (rmState.media === 'manga' && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        // One page at a time, ↑/↓ open the previous / next volume.
        e.preventDefault();
        if (!e.repeat) rmStepPart(e.key === 'ArrowDown' ? 1 : -1);
        return;
      }

      const isTurnKey = e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === 'PageUp'
        || e.key === ' ' || ((e.key === 'd' || e.key === 'D' || e.key === 'a' || e.key === 'A') && !e.shiftKey);
      if (isTurnKey) {
        const now = Date.now();
        if (e.repeat && now - rmLastNavTime < 65) { e.preventDefault(); return; }
        rmLastNavTime = now;
      }

      const rtl = rmState.media === 'manga' || rmState.dir === 'vertical';
      if (e.key === 'ArrowLeft') { e.preventDefault(); rmTurnPage(rtl ? 1 : -1); return; }
      if (e.key === 'ArrowRight') { e.preventDefault(); rmTurnPage(rtl ? -1 : 1); return; }
      if (e.key === 'PageDown' || (e.key === ' ' && !e.shiftKey)) { e.preventDefault(); rmTurnPage(1); return; }
      if (e.key === 'PageUp' || (e.key === ' ' && e.shiftKey)) { e.preventDefault(); rmTurnPage(-1); return; }
      if ((e.key === 'd' || e.key === 'D') && !e.shiftKey) { e.preventDefault(); rmTurnPage(rtl ? -1 : 1); return; }
      if ((e.key === 'a' || e.key === 'A') && !e.shiftKey) { e.preventDefault(); rmTurnPage(rtl ? 1 : -1); return; }
      if (e.key === '[') { e.preventDefault(); rmStepPart(-1); return; }
      if (e.key === ']') { e.preventDefault(); rmStepPart(1); return; }
      if ((e.key === 't' || e.key === 'T') && !e.shiftKey) { e.preventDefault(); rmToggleToc(); return; }
      if ((e.key === 'b' || e.key === 'B') && !e.shiftKey) { e.preventDefault(); rmOnBookmarkClick(); return; }
      if ((e.key === 'n' || e.key === 'N') && !e.shiftKey && typeof rmToggleNotes === 'function') { e.preventDefault(); rmCaptureNotesSelection(); rmToggleNotes(); return; }
      if ((e.key === 'f' || e.key === 'F') && !e.shiftKey) { e.preventDefault(); rmCycleFurigana(); return; }
      if ((e.key === 's' || e.key === 'S') && !e.shiftKey) { e.preventDefault(); rmToggleSettings(); return; }
      if (e.key === '0' && rmState.media === 'manga') { e.preventDefault(); rmMangaFit(false); return; }
    }

    let rmMangaStageObs = null;
    let rmMangaStripObs = null;
    let rmMangaClickTimer = null;
    const rmPz = {
      scale: 1, fitScale: 1, tx: 0, ty: 0, imgW: 0, imgH: 0,
      dragging: false, captured: false, pointerId: null, moved: false,
      startX: 0, startY: 0, origTx: 0, origTy: 0,
    };

    // No button to undo a zoom: a double click or double tap does it.
    function rmSyncZoomPill() {
      const zoomed = rmState.media === 'manga' && rmPz.imgW > 0 && rmPz.scale > rmPz.fitScale * 1.04
        && !document.querySelector('#rm-manga-stage.rm-manga-strip');
      if (zoomed) rmSetEdgeHint(null);
    }

    function rmBuildMokuroPageEl(pg) {
      if (!pg.image_url) {
        const card = document.createElement('div');
        card.className = 'rm-manga-db-page';
        card.dataset.page = String(pg.page);
        const head = `<div class="rm-manga-db-head">${esc(t('page_n', { n: fmt(pg.page) }))}</div>`;
        const body = (pg.blocks || []).map(b => `<p class="rm-db-line">${b.html || esc(b.text || '')}</p>`).join('') || `<p class="muted">${esc(t('rm_no_content'))}</p>`;
        card.innerHTML = head + body;
        return card;
      }
      const pageEl = document.createElement('div');
      pageEl.className = 'rm-mokuro-page';
      pageEl.dataset.page = String(pg.page);
      const imgW = pg.img_width || 1000;
      const imgH = pg.img_height || 1400;
      pageEl.style.width = imgW + 'px';
      pageEl.style.height = imgH + 'px';
      pageEl.style.backgroundImage = `url("${pg.image_url}")`;

      const valid = (pg.blocks || []).filter(b => b.box && b.box.length === 4);
      const indexed = valid.map((b, i) => ({ b, i, area: Math.max(1, (b.box[2] - b.box[0]) * (b.box[3] - b.box[1])) }));
      indexed.sort((a, c) => c.area - a.area);
      const zMap = new Map();
      indexed.forEach((it, rank) => zMap.set(it.i, 10 + rank));

      valid.forEach((blk, idx) => {
        const [xmin, ymin, xmax, ymax] = blk.box;
        const w = Math.max(4, xmax - xmin);
        const h = Math.max(4, ymax - ymin);
        const fs = Math.max(12, Math.min(32, blk.font_size || 16));
        const boxEl = document.createElement('div');
        boxEl.className = 'rm-text-box';
        boxEl.style.left = xmin + 'px';
        boxEl.style.top = ymin + 'px';
        boxEl.style.width = w + 'px';
        boxEl.style.height = h + 'px';
        boxEl.style.fontSize = fs + 'px';
        boxEl.style.zIndex = String(zMap.get(idx) || 10);
        if (blk.vertical) boxEl.style.writingMode = 'vertical-rl';

        const rawLines = (blk.lines && blk.lines.length) ? blk.lines : [blk.text || ''];
        for (const ln of rawLines) {
          const pEl = document.createElement('p');
          pEl.textContent = ln;
          boxEl.appendChild(pEl);
        }
        boxEl.addEventListener('click', ev => {
          ev.stopPropagation();
          if (rmGetPrefs().manga_boxes === 'hover') {
            const was = boxEl.classList.contains('rm-hovered');
            pageEl.querySelectorAll('.rm-text-box.rm-hovered').forEach(x => x.classList.remove('rm-hovered'));
            if (!was) boxEl.classList.add('rm-hovered');
          }
        });
        pageEl.appendChild(boxEl);
      });
      return pageEl;
    }

    function rmApplyPzTransform() {
      const canvas = document.getElementById('rm-mokuro-canvas');
      const mStage = document.getElementById('rm-manga-stage');
      if (!canvas || !mStage || !rmPz.imgW || !rmPz.imgH) return;
      const sw = mStage.clientWidth;
      const sh = mStage.clientHeight;
      const cw = rmPz.imgW * rmPz.scale;
      const ch = rmPz.imgH * rmPz.scale;
      if (cw <= sw) rmPz.tx = (sw - cw) / 2;
      else rmPz.tx = Math.min(0, Math.max(sw - cw, rmPz.tx));
      if (ch <= sh) rmPz.ty = (sh - ch) / 2;
      else rmPz.ty = Math.min(0, Math.max(sh - ch, rmPz.ty));
      canvas.style.transform = `translate(${rmPz.tx}px, ${rmPz.ty}px) scale(${rmPz.scale})`;
      rmSyncZoomPill();
    }

    function rmMangaFit(preserveZoom) {
      const mStage = document.getElementById('rm-manga-stage');
      if (!mStage || mStage.classList.contains('rm-manga-strip') || !rmPz.imgW || !rmPz.imgH) {
        if (mStage && mStage.classList.contains('rm-manga-strip')) rmResizeStripPages();
        rmSyncZoomPill();
        return;
      }
      const useEdgeInset = window.innerWidth > 720;
      const edgePx = useEdgeInset ? Math.ceil(mStage.clientWidth * RM_EDGE_ROOM) : 0;
      const padX = (useEdgeInset && mStage.clientWidth - edgePx * 2 >= 260) ? (edgePx * 2 + 12) : 4;
      const sw = Math.max(100, mStage.clientWidth - padX);
      const sh = Math.max(100, mStage.clientHeight - 4);
      const newFit = Math.min(sw / rmPz.imgW, sh / rmPz.imgH);
      const wasZoomed = rmPz.scale > rmPz.fitScale * 1.03;
      rmPz.fitScale = newFit;
      if (!preserveZoom || !wasZoomed) {
        rmPz.scale = newFit;
        rmPz.tx = (mStage.clientWidth - rmPz.imgW * newFit) / 2;
        rmPz.ty = (mStage.clientHeight - rmPz.imgH * newFit) / 2;
      }
      rmApplyPzTransform();
    }

    function rmZoomMangaAt(clientX, clientY, targetScale) {
      const mStage = document.getElementById('rm-manga-stage');
      if (!mStage || !rmPz.imgW) return;
      const rect = mStage.getBoundingClientRect();
      const px = clientX - rect.left;
      const py = clientY - rect.top;
      let nextScale = Math.max(rmPz.fitScale, Math.min(rmPz.fitScale * 5, targetScale));
      if (nextScale <= rmPz.fitScale * 1.03) {
        rmMangaFit(false);
        return;
      }
      const ratio = nextScale / rmPz.scale;
      rmPz.tx = px - (px - rmPz.tx) * ratio;
      rmPz.ty = py - (py - rmPz.ty) * ratio;
      rmPz.scale = nextScale;
      rmApplyPzTransform();
    }

    function rmResizeStripPages() {
      const mStage = document.getElementById('rm-manga-stage');
      if (!mStage) return;
      const p = rmGetPrefs();
      const pct = Math.max(25, Math.min(100, Number(p.image_scale) || 80)) / 100;
      const availW = Math.max(200, mStage.clientWidth - 16);
      const targetW = Math.max(120, Math.round(availW * pct));
      mStage.querySelectorAll('.rm-mokuro-strip-item').forEach(wrap => {
        const iw = parseFloat(wrap.dataset.iw || '1000');
        const ih = parseFloat(wrap.dataset.ih || '1400');
        const s = Math.min(4, targetW / Math.max(1, iw));
        wrap.style.width = Math.round(iw * s) + 'px';
        wrap.style.height = Math.round(ih * s) + 'px';
        const pgEl = wrap.firstElementChild;
        if (pgEl) pgEl.style.transform = `scale(${s})`;
      });
    }

    function rmRenderMangaPart(opts = {}) {
      const part = rmState.part;
      const stage = document.getElementById('rm-stage');
      if (!part || !stage) return;
      if (rmMangaStageObs) rmMangaStageObs.disconnect();
      if (rmMangaStripObs) rmMangaStripObs.disconnect();
      clearTimeout(rmMangaClickTimer);
      rmSetEdgeHint(null);

      const pages = part.pages || [];
      stage.classList.remove('rm-vertical', 'rm-horizontal', 'rm-paginated', 'rm-continuous');
      stage.onmousemove = null;
      stage.onmouseleave = null;
      stage.onclick = null;
      stage.onwheel = null;
      if (!pages.length) {
        stage.innerHTML = `<div class="status-line" style="padding:3em;text-align:center;">${esc(t('rm_no_content'))}</div>`;
        rmSyncZoomPill();
        rmUpdateProgressUI();
        return;
      }
      let pno = opts.atEnd ? pages.length : (opts.targetPage || 1);
      pno = Math.max(1, Math.min(pages.length, pno));
      rmState.mangaPage = pno;

      const p = rmGetPrefs();
      const isStrip = p.manga_layout === 'strip' || part.source === 'db';
      stage.innerHTML = `<div class="rm-manga-stage ${isStrip ? 'rm-manga-strip' : ''}" id="rm-manga-stage"></div>`;
      const mStage = document.getElementById('rm-manga-stage');

      if (window.ResizeObserver) {
        rmMangaStageObs = new ResizeObserver(() => rmMangaFit(true));
        rmMangaStageObs.observe(mStage);
      }

      if (isStrip) {
        rmPz.imgW = 0; rmPz.imgH = 0; rmPz.scale = 1; rmPz.fitScale = 1; rmSyncZoomPill();
        for (const pg of pages) {
          if (!pg.image_url) {
            mStage.appendChild(rmBuildMokuroPageEl(pg));
          } else {
            const wrap = document.createElement('div');
            wrap.className = 'rm-mokuro-strip-item';
            wrap.dataset.page = String(pg.page);
            wrap.dataset.iw = String(pg.img_width || 1000);
            wrap.dataset.ih = String(pg.img_height || 1400);
            wrap.appendChild(rmBuildMokuroPageEl(pg));
            mStage.appendChild(wrap);
          }
        }
        rmResizeStripPages();
        rmMangaStripObs = new IntersectionObserver(entries => {
          const vis = entries.filter(e => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio);
          if (vis.length) {
            const pNum = parseInt(vis[0].target.dataset.page || '1', 10);
            if (pNum && pNum !== rmState.mangaPage) {
              rmState.mangaPage = pNum;
              rmUpdateProgressUI();
              rmScheduleSaveProgress();
              saveMediaState();
            }
          }
        }, { root: mStage, threshold: [0.25, 0.6] });
        mStage.querySelectorAll('[data-page]').forEach(el => rmMangaStripObs.observe(el));
        const targetEl = mStage.querySelector(`[data-page="${pno}"]`);
        const frac = (opts.targetAnchor && opts.targetAnchor.page_frac) || (opts.restorePos && rmState.work && rmState.work.page_frac) || 0;
        if (pno <= 1 && !frac) mStage.scrollTop = 0;
        else if (targetEl) mStage.scrollTop = Math.max(0, targetEl.offsetTop + Math.round(frac * targetEl.offsetHeight));
        mStage.addEventListener('scroll', rmOnBarScroll, { passive: true });
      } else {
        rmDrawSingleMangaPage(pno);
      }

      mStage.addEventListener('mousemove', e => {
        if (isStrip || rmPz.dragging || !rmEdgeNavActive() || e.target.closest('.rm-text-box, a, button')) {
          rmSetEdgeHint(null);
          return;
        }
        rmSetEdgeHint(rmEdgeHitSide(e.clientX, mStage));
      });
      mStage.addEventListener('mouseleave', () => rmSetEdgeHint(null));

      mStage.addEventListener('dragstart', e => e.preventDefault());

      mStage.addEventListener('pointerdown', e => {
        if (isStrip || (e.button !== 0 && e.button !== 1)) return;
        if (e.target.closest('a, button')) return;
        if (e.button === 0 && e.target.closest('.rm-text-box') && rmGetPrefs().manga_boxes !== 'off') return;
        if (rmPz.scale <= rmPz.fitScale * 1.04) return;
        e.preventDefault();
        rmPz.dragging = true;
        rmPz.captured = false;
        rmPz.pointerId = e.pointerId;
        rmPz.moved = false;
        rmPz.startX = e.clientX;
        rmPz.startY = e.clientY;
        rmPz.origTx = rmPz.tx;
        rmPz.origTy = rmPz.ty;
      });
      mStage.addEventListener('pointermove', e => {
        if (!rmPz.dragging) return;
        const dx = e.clientX - rmPz.startX;
        const dy = e.clientY - rmPz.startY;
        if (!rmPz.moved && Math.abs(dx) <= 5 && Math.abs(dy) <= 5) return;
        if (!rmPz.moved) {
          rmPz.moved = true;
          if (!rmPz.captured && rmPz.pointerId != null) {
            try { mStage.setPointerCapture(rmPz.pointerId); rmPz.captured = true; } catch (err) {}
          }
          const canvas = document.getElementById('rm-mokuro-canvas');
          if (canvas) canvas.classList.add('rm-dragging');
        }
        rmPz.tx = rmPz.origTx + dx;
        rmPz.ty = rmPz.origTy + dy;
        rmApplyPzTransform();
      });
      const endDrag = () => {
        if (!rmPz.dragging) return;
        rmPz.dragging = false;
        if (rmPz.captured && rmPz.pointerId != null) {
          try { mStage.releasePointerCapture(rmPz.pointerId); } catch (err) {}
        }
        rmPz.captured = false;
        rmPz.pointerId = null;
        const canvas = document.getElementById('rm-mokuro-canvas');
        if (canvas) canvas.classList.remove('rm-dragging');
      };
      mStage.addEventListener('pointerup', endDrag);
      mStage.addEventListener('pointercancel', endDrag);

      mStage.addEventListener('wheel', e => {
        if (isStrip || !rmPz.imgW) return;
        if (e.ctrlKey) {
          e.preventDefault();
          const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18;
          rmZoomMangaAt(e.clientX, e.clientY, rmPz.scale * factor);
          return;
        }
        if (rmPz.scale > rmPz.fitScale * 1.04) {
          e.preventDefault();
          if (e.shiftKey) rmPz.tx -= e.deltaY;
          else { rmPz.tx -= e.deltaX; rmPz.ty -= e.deltaY; }
          rmApplyPzTransform();
        }
      }, { passive: false });

      mStage.addEventListener('mousedown', e => {
        if (!isStrip && e.button === 0 && rmEdgeNavActive() && !e.target.closest('.rm-text-box, a, button') && rmEdgeHitSide(e.clientX, mStage)) {
          e.preventDefault();
        }
      });

      mStage.addEventListener('dblclick', e => {
        if (isStrip) return;
        if (e.target.closest('.rm-text-box, a, button')) return;
        if (rmPz.scale > rmPz.fitScale * 1.04) {
          e.preventDefault();
          rmMangaFit(false);
          return;
        }
        if (rmEdgeNavActive() && rmEdgeHitSide(e.clientX, mStage)) return;
        if (!e.target.closest('.rm-mokuro-page')) return;
        e.preventDefault();
        rmZoomMangaAt(e.clientX, e.clientY, rmPz.fitScale * 2.2);
      });

      mStage.addEventListener('click', e => {
        if (isStrip) return;
        if (rmPz.moved) { rmPz.moved = false; return; }
        if (window.getSelection && String(window.getSelection()).trim()) return;
        if (e.target.closest('.rm-text-box, a, button')) return;
        mStage.querySelectorAll('.rm-text-box.rm-hovered').forEach(x => x.classList.remove('rm-hovered'));
        if (rmEdgeNavActive()) {
          const side = rmEdgeHitSide(e.clientX, mStage);
          if (side === 'left') { rmTurnMangaPage(1); return; }
          if (side === 'right') { rmTurnMangaPage(-1); return; }
        }
      });

      mStage.ontouchstart = e => {
        if (isStrip || e.touches.length !== 1 || rmPz.scale > rmPz.fitScale * 1.05) return;
        rmState.touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
      };
      mStage.ontouchend = e => {
        if (isStrip || !rmState.touchStart || !e.changedTouches.length) return;
        const dx = e.changedTouches[0].clientX - rmState.touchStart.x;
        const dy = e.changedTouches[0].clientY - rmState.touchStart.y;
        const dt = Date.now() - rmState.touchStart.t;
        rmState.touchStart = null;
        if (dt < 500 && Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.5) {
          rmTurnMangaPage(dx > 0 ? 1 : -1);
        }
      };

      rmUpdateProgressUI();
      rmResetTopbarForMode();
      saveMediaState();
      rmFocusStage();
    }

    function rmDrawSingleMangaPage(pageNo) {
      const mStage = document.getElementById('rm-manga-stage');
      const pages = (rmState.part && rmState.part.pages) || [];
      if (!mStage || !pages.length) return;
      clearTimeout(rmMangaClickTimer);
      const pno = Math.max(1, Math.min(pages.length, pageNo));
      rmState.mangaPage = pno;
      const pg = pages[pno - 1];
      mStage.innerHTML = '';
      if (!pg.image_url) {
        rmPz.imgW = 0; rmPz.imgH = 0; rmPz.scale = 1; rmPz.fitScale = 1;
        mStage.style.overflowY = 'auto';
        mStage.appendChild(rmBuildMokuroPageEl(pg));
      } else {
        mStage.style.overflowY = '';
        const canvas = document.createElement('div');
        canvas.className = 'rm-mokuro-canvas';
        canvas.id = 'rm-mokuro-canvas';
        const pageEl = rmBuildMokuroPageEl(pg);
        canvas.appendChild(pageEl);
        mStage.appendChild(canvas);
        rmPz.imgW = pg.img_width || 1000;
        rmPz.imgH = pg.img_height || 1400;
        rmMangaFit(false);
        const curPart = rmState.part;
        const probe = new Image();
        probe.onload = () => {
          if (rmState.part !== curPart || rmState.mangaPage !== pno) return;
          if ((!pg.img_width || !pg.img_height) && probe.naturalWidth && probe.naturalHeight) {
            rmPz.imgW = probe.naturalWidth;
            rmPz.imgH = probe.naturalHeight;
            pageEl.style.width = rmPz.imgW + 'px';
            pageEl.style.height = rmPz.imgH + 'px';
            rmMangaFit(false);
          }
        };
        probe.onerror = () => {
          if (rmState.part !== curPart || rmState.mangaPage !== pno) return;
          rmPz.imgW = 0; rmPz.imgH = 0;
          mStage.innerHTML = `<div class="rm-manga-missing">${esc(t('rm_manga_no_image'))}</div>`;
        };
        probe.src = pg.image_url;
      }
      const nxt = pages[pno];
      if (nxt && nxt.image_url) { const pre = new Image(); pre.src = nxt.image_url; }
      rmUpdateProgressUI();
      rmScheduleSaveProgress();
      saveMediaState();
    }

    function rmGoMangaPage(pageNo) {
      const p = rmGetPrefs();
      if (p.manga_layout === 'strip' || (rmState.part && rmState.part.source === 'db')) {
        const el = document.querySelector(`#rm-manga-stage [data-page="${pageNo}"]`);
        if (el) el.scrollIntoView({ block: 'start' });
        rmState.mangaPage = pageNo;
        rmUpdateProgressUI();
      } else {
        rmDrawSingleMangaPage(pageNo);
      }
    }

    function rmTurnMangaPage(delta) {
      const pages = (rmState.part && rmState.part.pages) || [];
      if (!pages.length) return;
      const p = rmGetPrefs();
      if (p.manga_layout === 'strip' || rmState.part.source === 'db') {
        const mStage = document.getElementById('rm-manga-stage');
        if (mStage) mStage.scrollBy({ top: delta * Math.round(mStage.clientHeight * 0.85), behavior: 'smooth' });
        return;
      }
      if (rmBarAutoHideActive(p)) rmSetTopbarHidden(true);
      const nxt = rmState.mangaPage + delta;
      if (nxt < 1) {
        if (rmState.partIndex > 0) rmLoadPart(rmState.partIndex - 1, { atEnd: true });
        return;
      }
      if (nxt > pages.length) {
        if (rmState.partIndex + 1 < rmState.files.length) rmLoadPart(rmState.partIndex + 1, { targetPage: 1 });
        return;
      }
      rmDrawSingleMangaPage(nxt);
    }


