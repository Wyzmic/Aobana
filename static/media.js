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
      if (PARAMS.get('media') === 'custom' && PARAMS.get('folder')) return;
      if (TAB !== 'media' || mediaRestoring) return;
      if (!PARAMS.get('folder')) {
        const listState = { url: mediaUrl(), q: document.getElementById('media-filter')?.value || '',
          media: mediaTabFilter(), sort: mediaSort(), loaded: mediaOffset, y: Math.round(window.scrollY),
          at: mediaListAnchor() };
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
      store.set(MEDIA_STATE, JSON.stringify({
        url: mediaUrl(), mode: mediaDetailMode, q: titleQ, open,
        groups: [...mediaGroupState], y: Math.round(window.scrollY), at: mediaAnchor()
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
    const CUSTOM_SORTS = ['default', ...MEDIA_SORTS];
    function customSort() {
      const v = store.get('customSort', 'default');
      return CUSTOM_SORTS.includes(v) ? v : 'default';
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
      // A Custom category of one file under its own name opens the file
      const href = it.file ? customUrl(it.folder, '', it.file) : '/?' + p.toString();
      return `<a class="media-row" href="${esc(href)}" draggable="false">
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
      const counts = { subs: data.shows, epub: data.books, manga: data.manga, custom: data.custom };
      const one = MEDIAS_ON.length === 1 ? MEDIAS_ON[0] : mediaTabFilter() === 'all' ? null : mediaTabFilter();
      const summary = one ? t('media_summary_' + one, { n: fmt(counts[one] || 0) })
        : [t('media_summary_total', { n: fmt(MEDIAS_ON.reduce((sum, m) => sum + (counts[m] || 0), 0)) }),
           ...MEDIAS_ON.map(m => t('media_summary_' + m, { n: fmt(counts[m] || 0) }))].join(' · ');
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
      if (mediaHasMore && !mediaRestoring) watchMediaEnd();
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

    function mediaListAnchor() {
      const bar = document.querySelector('.topbar');
      const edge = (bar ? bar.getBoundingClientRect().bottom : 0) + 8;
      const row = [...document.querySelectorAll('#media-list .media-row')].find(el => el.getBoundingClientRect().bottom > edge);
      return row ? { url: row.getAttribute('href'), dy: row.getBoundingClientRect().top } : null;
    }
    function restoreMediaListScroll(state) {
      const row = state.at && [...document.querySelectorAll('#media-list .media-row')].find(el => el.getAttribute('href') === state.at.url);
      if (row) window.scrollTo({ top: window.scrollY + row.getBoundingClientRect().top - state.at.dy, behavior: 'instant' });
      else window.scrollTo(0, state.y || 0);
    }
    document.addEventListener('click', e => {
      if (TAB === 'media' && e.target.closest('#media-list .media-row')) saveMediaState();
    }, true);

    async function initMediaTab() {
      const folder = PARAMS.get('folder');
      if (folder && PARAMS.get('media') === 'custom') return initCustomBrowser(folder);
      if (folder) return initMediaDetail(folder);
      watchDockRow(document.querySelector('#media-body .media-toolbar-wrap'));
      let prior = null;
      try { prior = JSON.parse(sessionStorage.getItem(MEDIA_LIST_STATE) || 'null'); } catch (e) {}
      mediaRestoring = true;
      try {
        if (prior) {
          document.getElementById('media-filter').value = prior.q || '';
          store.set('mediaSort', prior.sort);
          store.set('mediaTabFilter', prior.media);
          document.querySelectorAll('#media-seg .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.media === prior.media));
        }
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
      makeDropdown(document.getElementById('media-sort'), {
        options: MEDIA_SORTS.map(v => ({ value: v, label: mediaSortLabel(v) })),
        value: mediaSort(), title: t('media_sort_title'), icon: ICON_ROWS,
        onChange: v => { store.set('mediaSort', v); initMediaSort(); mediaListTop(); loadMediaPage(true).then(saveMediaState); },
      });
    }

    function setMediaTabFilter(m) {
      store.set('mediaTabFilter', m);
      document.querySelectorAll('#media-seg .seg-btn').forEach(b => b.classList.toggle('active', b.dataset.media === m));
      mediaListTop();
      loadMediaPage(true).then(saveMediaState);
    }
    function mediaListTop() { window.scrollTo({ top: 0, behavior: 'instant' }); }

    function onMediaFilterInput() {
      clearTimeout(mediaFilterTimer);
      mediaFilterTimer = setTimeout(() => loadMediaPage(true).then(saveMediaState), 150);
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
      else header.scrollIntoView({ block: 'start' });
    }

    function customUrl(category, path, file, returnPath) {
      const p = new URLSearchParams({ tab: 'media', media: 'custom', folder: category, custom_path: path });
      if (file) p.set('custom_file', file);
      if (file && returnPath) p.set('custom_return', returnPath);
      return '/?' + p.toString();
    }


    async function initMediaDetail(folder) {
      const at = takeOpenTarget();
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
          head.querySelector('.path-reveal').innerHTML = revealIconHTML(it.media, '', folder);
        }
        mediaDetailFiles = ep.files || [];
        renderEpisodesList(mediaDetailFiles);
        const state = readMediaState();
        if (at) {
          document.getElementById('main-loading').style.display = 'none';
          await openMediaTarget(at);
        } else if (state && state.url === mediaUrl()) {
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
      renderEpisodesList(matched, true);
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

    function episodeHeaderHTML(item) {
      const safeFile = encodeURIComponent(item.file);
      return `<div class="episode-header" data-file="${safeFile}" onclick="expandEpisode(this)">
                    <div class="episode-title">${esc(item.title)}</div>
                    ${item.lines === 0 ? `<span class="muted">${esc(t('media_no_dialogue'))}</span>` : ''}
                    ${mediaDetailMedia === 'epub' ? '' : revealIconHTML(mediaDetailMedia, item.file)}
                    <div class="episode-toggle-icon">▼</div>
                </div>`;
    }

    function renderEpisodesList(filesList, filtering = false) {
      const resultsContainer = document.getElementById('results');
      function episodeHTML(item) {
         const fileHash = btoa(unescape(encodeURIComponent(item.file))).substring(0, 32).replace(/=/g, '');
         return `
            <div class="card episode-card collapsed" id="ep-card-${fileHash}">
                ${episodeHeaderHTML(item)}
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
              : group.kind === 'movie' ? t('group_movie') : group.kind === 'ova' ? t('group_ova') : name;
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

