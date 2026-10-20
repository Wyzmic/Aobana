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
        if (response.status === 409 && data.error === 'known_words_unavailable') { learnUnavailable(); return; }
        if (data.busy) {
          allResults = [];
          const empty = document.getElementById('empty-state');
          empty.dataset.i18n = 'search_busy';
          empty.textContent = t('search_busy');
          empty.style.display = 'block';
          return;
        }

        outsideMedia = new Set(Array.isArray(data.outside_media) ? data.outside_media : []);
        if (!inPage && choiceOutsideMedia()) { setTimeout(() => applyFolders([], true), 0); return; }
        readingWords = Array.isArray(data.reading_words) ? data.reading_words : [];
        readingDropped = Array.isArray(data.reading_dropped) ? data.reading_dropped : [];
        setEmptyStateForFolders(currentFolders);
        if (LEARN === 'only' && data.learn && !data.learn.unsupported && !currentFolders.length) {
          const empty = document.getElementById('empty-state');
          empty.dataset.i18n = '';
          empty.textContent = t(data.learn.target_known ? 'learn_empty_known' : 'learn_empty', { word: PARAMS.get('q') || '' });
        }

        allResults = data.results;
        updateReadingNote();
        updateLearnNote(data);
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
        if (!inPage) restoreSearchReturn();

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

    let readingWords = [];
    let readingDropped = [];
    function updateReadingNote() {
      const note = document.getElementById('reading-note');
      if (readingDropped.length) {
        note.textContent = t('reading_fallback', { word: readingDropped.join('・') });
        note.hidden = false;
        return;
      }
      const show = readingWords.length > 0 && allResults.length > 0 && searchParams().get('ruby_only') !== 'on'
        && !allResults.some(r => String(r.display_line || '').includes('class="hl-guess"'));
      note.textContent = show ? t('reading_note', { word: readingWords.join('・') }) : '';
      note.hidden = !show;
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

    const HISTORY_MAX = 20;
    function normalizeQuery(q) {
      const chunks = [];
      let current = '', quoted = false;
      for (const char of q) {
        if ('"“”'.includes(char)) quoted = !quoted;
        if (/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u.test(char) && !quoted) {
          if (current) chunks.push(current);
          current = '';
        } else current += char;
      }
      if (current) chunks.push(current);
      const minusRun = (chunk, follows) => {
        let run = 0;
        while (run < chunk.length && '-－ーｰ'.includes(chunk[run])) run++;
        if (run === 0 || (run === 1 && '-－'.includes(chunk[0])) || (run === chunk.length && !follows)) return chunk;
        return ([...chunk.slice(0, run)].every(c => c === '-') ? '-' : '－') + chunk.slice(run);
      };
      for (let at = 0; at < chunks.length; at++) chunks[at] = minusRun(chunks[at], at + 1 < chunks.length);
      const out = [];
      for (let at = 0; at < chunks.length; at++) {
        if (['-', '－'].includes(chunks[at]) && at + 1 < chunks.length) {
          out.push(minusRun(chunks[at] + chunks[at + 1], at + 2 < chunks.length));
          at++;
        } else out.push(chunks[at]);
      }
      let quotedPart = false;
      return out.join(' ').split(/(["“”])/u).map(part => {
        if ('"“”'.includes(part) && part) { quotedPart = !quotedPart; return part; }
        return quotedPart ? part : part.replace(/(?<=[^\s=＝])[ \t　]*([=＝])[ \t　]*(?=[^\s=＝])/gu, '$1');
      }).join('');
    }

    function saveToHistory(q) {
      q = normalizeQuery(q);
      let history;
      try { history = JSON.parse(store.get('searchHistory', '[]')); } catch (e) { history = []; }
      if (!Array.isArray(history)) history = [];
      history = history.filter(item => item !== q);
      history.unshift(q);
      store.set('searchHistory', JSON.stringify(history.slice(0, HISTORY_MAX)));
    }

    const STACKED = window.matchMedia('(max-width: 720px)');
    function folderHintKey() {
      return (multiPick ? 'folder_hint' : 'folder_hint_one') + (STACKED.matches ? '_above' : '');
    }
    function refreshFolderHints() {
      document.querySelectorAll('.folder-hint').forEach(p => { p.textContent = t(folderHintKey()); });
    }
    STACKED.addEventListener('change', refreshFolderHints);
    function readingHint() {
      const link = q => {
        const p = new URLSearchParams();
        currentFolders.forEach(f => p.append('folder', f));
        p.set('q', q);
        return `<a href="/?${p.toString()}" draggable="false">${esc(q)}</a>`;
      };
      const line = esc(t('reading_hint')).replace('{myou}', link('明＝みょう')).replace('{iru}', link('入る＝いる'));
      return `<p class="reading-hint">${line}</p>
        <p class="reading-hint">${esc(t('ruby_only_hint'))}</p>`;
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
        const chips = history.slice(0, HISTORY_MAX).map((q, i) => {
          const p = new URLSearchParams(keep); p.set('q', q);
          return `<span class="history-chip"><button type="button" data-i="${i}" aria-label="${esc(t('remove_recent', { q }))}">✕</button><a href="/?${p.toString()}" draggable="false">${esc(q)}</a></span>`;
        }).join('');
        panel.innerHTML = `<div class="history-label">${esc(t('recent'))}</div><div class="history-chips">${chips}</div>
          <p class="folder-hint">${esc(t(folderHintKey()))}</p>${readingHint()}`;
        panel.querySelectorAll('.history-chip button').forEach(b => b.addEventListener('click', e => {
          e.preventDefault();
          const q = history[Number(b.dataset.i)];
          let now;
          try { now = JSON.parse(store.get('searchHistory', '[]')); } catch (_) { now = []; }
          now = (Array.isArray(now) ? now : []).slice(0, HISTORY_MAX);
          store.set('searchHistory', JSON.stringify(now.filter(item => item !== q)));
          showSearchHistory(true);
        }));
      } else {
        panel.innerHTML = `<p class="folder-hint">${esc(t(folderHintKey()))}</p>${readingHint()}`;
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
          if (!inPage && choiceOutsideMedia()) { applyFolders([], true); return; }
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
    let folderAuthors = {}, folderAuthorsState = 'none';
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
      const top = side.querySelector('.side-controls')?.getBoundingClientRect().bottom ?? box.top;
      if (r.top < top || r.bottom > box.bottom) side.scrollTop += r.top - top - (box.bottom - top - r.height) / 2;
    }

    let sidebarDrawn = null;
    function sidebarSignature(data) {
      return JSON.stringify([data.all_folders || [], data.folder_counts || {}, data.global_total || 0,
                             [...pinnedFolders].sort(), [...currentFolders].sort()]);
    }

    function markSelected() {
      updatePhoneTitles();
      document.querySelectorAll('#folder-list-dynamic .folder-link[data-folder]').forEach(a => {
        const f = a.dataset.folder;
        a.classList.toggle('selected', f ? currentFolders.includes(f) : !currentFolders.length);
      });
    }

    function foldTitleFilter(text) {
      return (text || '').normalize('NFKC').replace(/[ァ-ヶ]/g,
        c => String.fromCharCode(c.charCodeAt(0) - 0x60)).toLowerCase();
    }

    function drawSidebar() {
      const list = document.getElementById('folder-list-dynamic');
      if (!list || !sidebarData) return;
      sidebarDrawn = sidebarSignature(sidebarData);
      const input = document.getElementById('folder-filter');
      const needle = input ? foldTitleFilter(input.value.trim()) : '';
      const listed = sidebarData.all_folders || [];
      const unlisted = currentFolders.filter(f => !listed.includes(f) && !pinnedFolders.includes(f));
      const top = [...listed.filter(f => pinnedFolders.includes(f)),
                   ...pinnedFolders.filter(f => !listed.includes(f)),
                   ...(multiPick ? unlisted : [])];
      const rest = [...listed.filter(f => !pinnedFolders.includes(f)), ...(multiPick ? [] : unlisted)];
      const match = f => !needle || foldTitleFilter(f).includes(needle)
        || foldTitleFilter(folderAuthors[f]).includes(needle);
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
      updatePhoneTitles();
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

    async function loadFolderAuthors() {
      if (folderAuthorsState !== 'none') return;
      folderAuthorsState = 'loading';
      try {
        const data = await fetch('/api/folder-authors').then(r => r.json());
        folderAuthors = data.authors || {};
        folderAuthorsState = data.ready ? 'loaded' : 'none';
      } catch (e) {
        folderAuthorsState = 'none';
        return;
      }
      if (Object.keys(folderAuthors).length) filterFolders();
    }

    function filterFolders() {
      sidebarShown = SIDEBAR_PAGE;
      drawSidebar();
      if (document.getElementById('folder-filter')?.value.trim()) loadFolderAuthors();
    }

    function setMediaMode(next) {
      store.set('media', next);
      const url = new URL(window.location);
      url.searchParams.set('media', next);
      window.location.href = url.toString();
    }

    function setFolder(folder, event) {
      if (event && event.preventDefault) event.preventDefault();
      if (!multiPick) closeTitleSheet();
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

    if (window.visualViewport && matchMedia('(pointer: coarse)').matches) {
      const TYPED = 'input[type=text], input[type=search], input:not([type]), textarea';
      document.addEventListener('focusin', e => {
        const box = e.target;
        if (!box.matches?.(TYPED)) return;
        document.documentElement.classList.add('kb-open');
        const fit = () => {
          if (document.activeElement !== box) return;
          const above = visualViewport.offsetTop + visualViewport.height - 8;
          const over = box.getBoundingClientRect().bottom - above;
          if (over > 0) window.scrollTo({ top: window.scrollY + over, behavior: 'smooth' });
        };
        visualViewport.addEventListener('resize', fit, { once: true });
        setTimeout(fit, 400);
      });
      document.addEventListener('focusout', () => document.documentElement.classList.remove('kb-open'));
    }

    function pinSearchBox() {
      const form = document.querySelector('form.search-bar');
      const box = form && form.querySelector('.search-input-wrap');
      const column = document.querySelector('[data-tab-panel="search"] .main-content');
      if (!box || !column) return;
      const spacer = document.createElement('div');
      spacer.className = 'search-pin-spacer';
      spacer.hidden = true;
      form.before(spacer);
      const phone = matchMedia('(max-width: 720px)');
      const side = document.querySelector('[data-tab-panel="search"] .sidebar');
      const results = document.getElementById('results');
      const pieces = () => [...form.querySelectorAll(':scope > .search-input-wrap, .search-options > :not(input[type=hidden])')];
      let lastY = window.scrollY;
      const update = () => {
        const barBottom = document.querySelector('.topbar').getBoundingClientRect().bottom;
        const gap = side && getComputedStyle(side).position === 'sticky' ? parseFloat(getComputedStyle(side).top) - barBottom : 8;
        const pinned = form.classList.contains('pinned');
        const home = (pinned ? spacer : form).getBoundingClientRect();
        const hasResults = !!(results && results.firstElementChild);
        const away = form.classList.contains('pin-away');
        const down = window.scrollY - lastY > 4;
        const sticky = home.bottom - box.offsetHeight >= barBottom + Math.max(0, gap);
        const under = !phone.matches ? !sticky
          : pinned && !away && !down ? !sticky : home.bottom <= barBottom;
        const pin = hasResults && under;
        form.classList.toggle('row-stick', hasResults);
        form.classList.toggle('row-stuck', hasResults && !pin && home.top < barBottom + Math.max(0, gap) - 0.5);
        form.style.setProperty('--stick-top', barBottom + 'px');
        form.style.setProperty('--stick-gap', Math.max(0, gap) + 'px');
        if (pin && !pinned) {
          spacer.style.height = form.offsetHeight + 'px';
          spacer.hidden = false;
          if (phone.matches && window.scrollY >= lastY) {
            form.style.transition = 'none';
            form.classList.add('pin-away');
            requestAnimationFrame(() => requestAnimationFrame(() => { form.style.transition = ''; }));
          }
        } else if (!pin && pinned) {
          spacer.hidden = true;
        }
        form.classList.toggle('pinned', pin);
        if (pin) {
          const col = column.getBoundingClientRect();
          form.style.top = barBottom + 'px';
          form.style.left = col.left + 'px';
          form.style.width = col.width + 'px';
          form.style.paddingTop = Math.max(0, gap) + 'px';
          const s = side && side.getBoundingClientRect();
          const from = s && s.width && s.right <= col.left ? s.right : 0;
          form.style.setProperty('--strip-l', (col.left - from) + 'px');
          form.style.setProperty('--strip-r', (document.documentElement.clientWidth - col.right) + 'px');
          const all = pieces();
          all.forEach(el => el.classList.remove('pin-off'));
          const rowTop = box.getBoundingClientRect().top;
          const off = all.map(el => el.getBoundingClientRect().top > rowTop + 4);
          all.forEach((el, i) => el.classList.toggle('pin-off', off[i]));
        } else {
          form.style.top = form.style.left = form.style.width = form.style.paddingTop = '';
          pieces().forEach(el => el.classList.remove('pin-off'));
        }
        const y = window.scrollY;
        const typing = window.visualViewport && visualViewport.height < window.innerHeight * 0.8;
        if (!pin || !phone.matches || typing) {
          form.classList.remove('pin-away');
          lastY = y;
        } else if (Math.abs(y - lastY) > 4) {
          form.classList.toggle('pin-away', y > lastY);
          lastY = y;
        }
      };
      const arrange = () => {
        const chips = pieces().slice(1);
        chips.forEach(el => {
          el.style.order = el.style.marginBlock = '';
          el.style.removeProperty('--row1-dy');
          el.classList.remove('pin-off', 'row1');
        });
        box.classList.remove('row1');
        const stick = form.classList.contains('row-stick');
        form.classList.remove('row-stick');
        const rowTop = box.getBoundingClientRect().top;
        const beside = chips.filter(el => el.getBoundingClientRect().top <= rowTop + 4);
        if (phone.matches) beside.forEach((el, i) => { el.style.order = String(-(i + 1)); });
        [box, ...beside].forEach(el => el.classList.add('row1'));
        const b = box.getBoundingClientRect();
        beside.forEach(el => {
          const d = Math.max(0, (b.height - el.offsetHeight) / 2) + 'px';
          el.style.marginBlock = d;
          el.style.setProperty('--row1-dy', d);
        });
        const s = side && side.getBoundingClientRect();
        const from = !phone.matches && s && s.width && s.right <= b.left ? s.right : 0;
        form.style.setProperty('--strip-bl', (b.left - from) + 'px');
        form.style.setProperty('--strip-br', (document.documentElement.clientWidth - b.right) + 'px');
        form.classList.toggle('row-stick', stick);
      };
      window.addEventListener('scroll', update, { passive: true });
      window.addEventListener('resize', () => { update(); arrange(); update(); });
      let colWidth = column.clientWidth, pageWidth = document.documentElement.clientWidth;
      if (window.ResizeObserver) {
        const watch = new ResizeObserver(() => {
          const page = document.documentElement.clientWidth;
          if (column.clientWidth === colWidth && page === pageWidth) return;
          colWidth = column.clientWidth; pageWidth = page;
          update(); arrange(); update();
        });
        watch.observe(column); watch.observe(document.documentElement);
      }
      if (results) new MutationObserver(update).observe(results, { childList: true });
      arrange();
      update();
      if (document.fonts) document.fonts.ready.then(() => { arrange(); update(); });
      if (side) side.addEventListener('scroll', () => side.classList.toggle('scrolled', side.scrollTop > 0), { passive: true });
    }

    let sheetMoving = 0;
    function moveTitleSheet(open) {
      const root = document.documentElement;
      root.classList.add('sheet-moving');
      root.classList.toggle('sheet-open', open);
      clearTimeout(sheetMoving);
      sheetMoving = setTimeout(() => root.classList.remove('sheet-moving'), 260);
    }
    function openTitleSheet() {
      moveTitleSheet(true);
      setTimeout(revealChosen, 0);
    }
    function closeTitleSheet() {
      moveTitleSheet(false);
    }
    function updatePhoneTitles() {
      const el = document.getElementById('phone-titles-label');
      if (!el) return;
      const n = currentFolders.length;
      const counts = (sidebarData && sidebarData.folder_counts) || {};
      const known = currentFolders.every(f => counts[f] != null);
      const count = !n ? (sidebarData ? sidebarData.global_total : null)
        : known ? currentFolders.reduce((a, f) => a + counts[f], 0) : null;
      el.textContent = n > 1 ? t('phone_titles_n', { n: fmt(n) }) : n ? currentFolders[0] : t('all');
      const badge = el.nextElementSibling;
      badge.hidden = !PARAMS.get('q') || count == null;
      badge.textContent = count == null ? '' : fmt(count);
    }

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
    function updateTopbarH() {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      const slot = bar.classList.contains('has-path') ? document.getElementById('topbar-path') : null;
      document.documentElement.style.setProperty('--bar-h', bar.getBoundingClientRect().height + 'px');
      document.documentElement.style.setProperty('--topbar-h', bar.offsetHeight + (slot ? slot.offsetHeight : 0) + 'px');
    }
    document.addEventListener('DOMContentLoaded', () => {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      const ro = new ResizeObserver(() => { updateTopbarH(); queueFit(); });
      ro.observe(bar);
      const slot = document.getElementById('topbar-path');
      if (slot) ro.observe(slot);
    });

    let lastScrollIntent = -Infinity;
    for (const ev of ['wheel', 'touchmove', 'keydown', 'pointerdown']) {
      window.addEventListener(ev, () => { lastScrollIntent = performance.now(); }, { passive: true, capture: true });
    }
    let pointerHeld = false, autoScroll = false;
    window.addEventListener('pointerdown', e => { pointerHeld = true; autoScroll = e.button === 1; }, { passive: true, capture: true });
    for (const ev of ['pointerup', 'pointercancel']) window.addEventListener(ev, () => { pointerHeld = false; }, { passive: true, capture: true });
    for (const ev of ['wheel', 'keydown']) window.addEventListener(ev, () => { autoScroll = false; }, { passive: true, capture: true });
    window.addEventListener('scroll', () => { if (pointerHeld || autoScroll) lastScrollIntent = performance.now(); }, { passive: true, capture: true });
    function topbarChange(bar, change) {
      const instant = performance.now() - lastScrollIntent > 800;
      if (instant) bar.classList.add('no-anim');
      change();
      if (instant) {
        void bar.offsetHeight;
        requestAnimationFrame(() => requestAnimationFrame(() => bar.classList.remove('no-anim')));
      }
      return instant;
    }
    let dockWatched = [], docked = [];
    function moveKeepingFocus(node, place) {
      const active = node.contains(document.activeElement) ? document.activeElement : null;
      const sel = active && 'selectionStart' in active ? [active.selectionStart, active.selectionEnd] : null;
      place(node);
      if (active && document.activeElement !== active) {
        active.focus({ preventScroll: true });
        if (sel) try { active.setSelectionRange(sel[0], sel[1]); } catch (e) {}
      }
    }
    function undockRow(keep = 0) {
      if (docked.length <= keep) return;
      while (docked.length > keep) {
        const { row, ph } = docked.pop();
        row.querySelectorAll('.dock-off').forEach(el => el.classList.remove('dock-off'));
        if (ph && ph.isConnected) moveKeepingFocus(row, n => ph.replaceWith(n));
        else row.remove();
      }
      const bar = document.querySelector('.topbar');
      if (bar && !docked.length) bar.classList.remove('has-path', 'dock-away');
      updateTopbarH();
    }
    const dockPhone = matchMedia('(max-width: 720px)');
    function watchDockRow(...rows) {
      undockRow();
      dockWatched = rows.filter(Boolean);
      queueDock();
    }
    function fitModeRow(row) {
      row.classList.remove('chips-below');
      if (!dockPhone.matches) return;
      const seg = row.querySelector(':scope > .seg');
      const box = [...row.querySelectorAll('.folder-filter, .search-input-wrap')].find(el => el.offsetParent !== null);
      if (seg && box && seg.getBoundingClientRect().top > box.getBoundingClientRect().top + 4) row.classList.add('chips-below');
    }
    window.addEventListener('resize', () => document.querySelectorAll('.media-detail-search').forEach(fitModeRow));
    function fitDockedRow() {
      document.querySelectorAll('.media-detail-search').forEach(fitModeRow);
      const slot = document.getElementById('topbar-path');
      if (!slot) return;
      const crumbs = slot.querySelector('.path-crumbs');
      if (crumbs) crumbs.scrollLeft = crumbs.scrollWidth;
      const row = slot.querySelector('.media-detail-search');
      slot.querySelectorAll('.dock-off').forEach(el => el.classList.remove('dock-off'));
      if (!dockPhone.matches) return;
      const sort = slot.querySelector('#media-sort'), filter = slot.querySelector('#media-filter');
      if (sort && filter) sort.classList.toggle('dock-off', sort.getBoundingClientRect().top > filter.getBoundingClientRect().top + 4);
      if (!row) return;
      const pieces = [...row.querySelectorAll(':scope > :not([hidden]):not(form), :scope > form:not([hidden]) > *')];
      const first = pieces.find(el => el.matches('.folder-filter, .search-input-wrap'));
      if (!first) return;
      const top = first.getBoundingClientRect().top;
      const off = pieces.map(el => el.getBoundingClientRect().top > top + 4);
      pieces.forEach((el, i) => el.classList.toggle('dock-off', off[i]));
    }
    let dockLastY = window.scrollY;
    function dockHomesGone() {
      const bar = document.querySelector('.topbar');
      const edge = bar ? bar.getBoundingClientRect().bottom : 0;
      return docked.every(({ ph }) => !ph.isConnected || ph.getBoundingClientRect().bottom <= edge);
    }
    function dockAway() {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      const y = window.scrollY;
      const typing = window.visualViewport && visualViewport.height < window.innerHeight * 0.8;
      if (!docked.length || !dockPhone.matches || typing) bar.classList.remove('dock-away');
      else if (Math.abs(y - dockLastY) > 4) bar.classList.toggle('dock-away', y > dockLastY && dockHomesGone());
      else return;
      dockLastY = y;
    }
    window.addEventListener('scroll', dockAway, { passive: true });
    window.addEventListener('resize', fitDockedRow);
    function checkDock() {
      const bar = document.querySelector('.topbar');
      const slot = document.getElementById('topbar-path');
      if (!dockWatched.length || !bar || !slot) return;
      if (!docked.length && !dockWatched[0].isConnected) { dockWatched = []; return; }
      const sticky = bar.classList.contains('is-sticky');
      const pad = getComputedStyle(slot);
      const padT = parseFloat(pad.paddingTop) || 0, padB = parseFloat(pad.paddingBottom) || 0;
      const edge = n => n ? docked[n - 1].row.getBoundingClientRect().bottom + padB : bar.getBoundingClientRect().bottom + padT;
      if (docked.length && !(sticky && docked.at(-1).ph.getBoundingClientRect().top <= edge(docked.length - 1))) {
        undockRow(docked.length - 1);
        return queueDock();
      }
      const row = dockWatched[docked.length];
      if (!row || !row.isConnected || !sticky || row.getBoundingClientRect().top > edge(docked.length)) return;
      if (dockPhone.matches && row.getBoundingClientRect().bottom > bar.getBoundingClientRect().bottom) return;
      const cs = getComputedStyle(row);
      const ph = document.createElement('div');
      ph.className = 'dock-placeholder';
      ph.style.cssText = `height:${row.offsetHeight}px;margin:${cs.marginTop} 0 ${cs.marginBottom};`;
      topbarChange(bar, () => {
        moveKeepingFocus(row, n => { n.replaceWith(ph); slot.appendChild(n); });
        docked.push({ row, ph });
        bar.classList.add('has-path');
        fitDockedRow();
        if (dockPhone.matches && window.scrollY >= dockLastY) {
          slot.style.transition = 'none';
          bar.classList.add('dock-away');
          requestAnimationFrame(() => requestAnimationFrame(() => { slot.style.transition = ''; }));
        }
      });
      updateTopbarH();
      queueDock();
    }
    let dockQueued = false;
    function queueDock() {
      if (dockQueued) return;
      dockQueued = true;
      requestAnimationFrame(() => { dockQueued = false; checkDock(); });
    }
    window.addEventListener('scroll', queueDock, { passive: true });
    window.addEventListener('resize', queueDock);

