    async function initCustomBrowser(category) {
      const at = takeOpenTarget();
      const path = PARAMS.get('custom_path') ?? category;
      const file = PARAMS.get('custom_file');
      const head = document.getElementById('media-detail');
      const results = document.getElementById('results');
      document.getElementById('media-body').hidden = true;
      head.hidden = false;
      const loading = document.getElementById('main-loading');
      head.after(loading, results);
      results.classList.add('media-reader', 'custom-reader');
      const key = 'aobana_custom:' + mediaUrl();
      let saved = {};
      try { saved = JSON.parse(sessionStorage.getItem(key) || '{}'); } catch (e) {}
      // Opened at a line: the file as it reads, no search or folds from an earlier visit
      if (at) saved = {};
      const parts = path.split('/').filter(Boolean);
      const parent = file ? (PARAMS.get('custom_return') || path) : parts.slice(0, -1).join('/');
      const up = parent ? customUrl(category, parent) : '/?tab=media&media=custom';
      const fileName = file ? file.replaceAll('\\', '/').split('/').pop().replace(/\.[^.]+$/, '').replace(/ [0-9a-f]{32}$/, '') : '';
      const crumbs = [{ label: t('media_custom'), href: '/?tab=media&media=custom' },
        ...parts.map((part, i) => ({ label: part, href: customUrl(category, parts.slice(0, i + 1).join('/')) })),
        ...(file ? [{ label: fileName }] : [])];
      const check = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7"/></svg>';
      const heading = `<h1>${esc(fileName || parts.at(-1) || category)}</h1>`;
      head.innerHTML = `${mediaPathBar(crumbs, up, revealIconHTML('custom', file, file ? '' : path))}
        <div class="media-detail-search custom-toolbar">
          <input id="custom-q" class="folder-filter" type="text" placeholder="${esc(t(file ? 'custom_filter_file' : 'custom_filter'))}" value="${esc(saved.q || '')}" autocomplete="off" spellcheck="false">
          <form id="custom-search" class="media-detail-form" autocomplete="off" hidden>
            <div class="search-input-wrap">
              <input id="custom-cq" class="search-input" type="text" placeholder="${esc(t('placeholder'))}" value="${esc(saved.q || '')}" autocomplete="off" spellcheck="false">
              <span class="search-btn-box"><button type="submit" class="search-btn" aria-label="${esc(t('tab_search'))}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></svg></button></span>
            </div>
            <label class="exact-chip" title="${esc(t('exact_title'))}"><input type="checkbox" id="custom-exact" ${saved.exact ? 'checked' : ''}>${check}<span>${esc(t('exact'))}</span></label>
            <label class="exact-chip" title="${esc(t('ruby_only_title'))}"><input type="checkbox" id="custom-ruby-only" ${saved.rubyOnly ? 'checked' : ''}>${check}<span>${esc(t('ruby_only'))}</span></label>
          </form>
          <div id="custom-sort"></div>
          <div class="seg"><button type="button" class="seg-btn" data-custom-mode="title">${esc(t('media_mode_title'))}</button><button type="button" class="seg-btn" data-custom-mode="content">${esc(t('media_mode_content'))}</button></div>
        </div>${heading}`;
      watchDockRow(head.querySelector('.path-bar'), head.querySelector('.media-detail-search'));
      let mode = saved.mode === 'content' ? 'content' : 'title';
      const titleInput = document.getElementById('custom-q');
      const contentInput = document.getElementById('custom-cq');
      const input = { get value() { return (mode === 'content' ? contentInput : titleInput)?.value || ''; } };
      let offset = 0, controller = null, generation = 0, timer, scrollTimer, openKept = false;
      let pages = null;
      const topLine = () => {
        const probe = Math.max(0, head.querySelector('.path-bar')?.getBoundingClientRect().bottom || 0) + 8;
        for (const el of results.querySelectorAll('.custom-line')) {
          const box = el.getBoundingClientRect();
          if (box.height && box.bottom > probe) return { rowid: el.dataset.rowid, dy: box.top };
        }
        return null;
      };
      const save = () => {
        if (!openKept) {
          const all = [...results.querySelectorAll('details')], here = new Set(all.map(el => el.dataset.group));
          saved.open = [...(saved.open || []).filter(g => !here.has(g)), ...all.filter(el => el.open).map(el => el.dataset.group)];
          saved.shut = [...(saved.shut || []).filter(g => !here.has(g)), ...all.filter(el => !el.open).map(el => el.dataset.group)];
        }
        const open = saved.open || [], shut = saved.shut || [];
        const top = pages && (pages.start > 0 || pages.end < pages.total) ? topLine() : null;
        const exact = !!document.getElementById('custom-exact')?.checked, rubyOnly = !!document.getElementById('custom-ruby-only')?.checked;
        try { sessionStorage.setItem(key, JSON.stringify({ q: input.value, mode, exact, rubyOnly, y: window.scrollY, top, open, shut, loaded: offset })); } catch (e) {}
        store.set(MEDIA_STATE, JSON.stringify({ url: mediaUrl(), open: [], y: window.scrollY }));
      };
      window.addEventListener('pagehide', save);
      document.addEventListener('click', e => { if (e.target.closest('a')) save(); }, true);
      window.addEventListener('scroll', () => { clearTimeout(scrollTimer); scrollTimer = setTimeout(save, 100); }, { passive: true });
      let fileTitle = '';
      const lineHtml = row => {
        const rId = lineId(row.line);
        const item = { ...row, id: rId, media_type: 'custom', title: fileTitle };
        delete item.line_html;
        const saved = savedSentences.some(s => s.id === rId);
        return `<div class="episode-line custom-line${row.gap_before ? ' custom-gap' : ''}" data-rowid="${row.rowid}"><span class="main-sentence">${row.display_line}</span><div class="actions-box"><button class="icon-btn ${saved ? 'star-active' : ''}" onclick="toggleSave('${rId}', this)" data-star="${starKey(item)}" aria-label="${esc(t('sc_save'))}"><span>★</span></button></div></div>`;
      };
      function readerHtml(data, found = false, titled = '') {
        const sections = data.kind === 'txt' ? [{ section_no: null }] : data.sections;
        const sectionHtml = (s, i, rows, withHead = true) => {
          const head = !withHead ? '' : s.heading ? `<h2 class="custom-heading">${esc(s.heading)}</h2>` : i ? '<div class="custom-divider"></div>' : '';
          return head + rows.map(lineHtml).join('');
        };
        const units = [];
        let current = null;
        sections.forEach((s, i) => {
          const rows = data.lines.filter(row => row.section_no === s.section_no);
          if (!current || s.heading) {
            current = { heading: s.heading, parts: [] };
            units.push(current);
          }
          current.parts.push({ s, i, rows });
        });
        const whole = data.kind === 'md' && data.fold_lines !== undefined;
        const fold = !found && (whole ? data.fold_lines : data.lines.length) >= 20 && (whole ? data.headed : units.filter(u => u.heading).length) >= 2;
        units.forEach((u, n) => { u.n = n; u.count = u.parts.reduce((sum, p) => sum + p.rows.length, 0); });
        const allOne = whole ? data.all_one : units.every(u => !u.heading || u.count <= 1);
        let shown = units;
        if (found) shown = units.map(u => ({ ...u, parts: u.parts.filter(p => p.rows.length) })).filter(u => u.parts.length);
        if (titled) shown = units.filter(u => u.heading && foldTitleFilter(u.heading).includes(titled));
        if (!shown.length) return '';
        return `<div class="episode-card">${shown.map(u => {
          const flat = u.parts.map(({ s, i, rows }) => sectionHtml(s, i, rows)).join('');
          if (!fold || !u.heading || (u.count === 1 && allOne)) return flat;
          if (!u.count) return `<div class="custom-fold-empty"><span class="media-subfolder-arrow" aria-hidden="true">▸</span><span>${esc(u.heading)}</span></div>`;
          const body = u.parts.map(({ s, i, rows }, k) => sectionHtml(s, i, rows, k > 0)).join('');
          return `<details class="media-subfolder custom-fold" data-group="fold:${u.parts[0].s.section_no ?? u.n}"${u.count === 1 ? ' data-open-first' : ''}><summary><span class="media-subfolder-arrow" aria-hidden="true">▸</span><span>${esc(u.heading)}</span><span class="media-subfolder-count">${esc(t('stat_lines', { n: fmt(u.count) }))}</span></summary><div class="custom-fold-body">${body}</div></details>`;
        }).join('')}</div>`;
      }
      function restoreFolds(found = false, root = results) {
        const kept = g => saved.open?.includes(g) ? true : saved.shut?.includes(g) || (saved.open && !saved.shut) ? false : null;
        root.querySelectorAll('details').forEach(el => { el.open = found || (kept(el.dataset.group) ?? el.hasAttribute('data-open-first')); el.addEventListener('toggle', save); });
      }
      const searching = gen => {
        stopSearchEta();
        results.innerHTML = '';
        loading.style.display = 'flex';
        return () => { if (gen === generation) loading.style.display = 'none'; };
      };
      async function load(reset = true) {
        if (reset) { offset = 0; generation++; if (controller) controller.abort(); }
        const gen = generation;
        controller = new AbortController();
        const p = new URLSearchParams({ path, q: input.value.trim(), mode, offset: String(offset), sort: customSort(), client: clientToken });
        if (mode === 'content' && document.getElementById('custom-exact')?.checked) p.set('exact', 'on');
        if (mode === 'content' && document.getElementById('custom-ruby-only')?.checked) p.set('ruby_only', 'on');
        const done = reset && mode === 'content' && p.get('q') ? searching(gen) : () => {};
        try {
          const r = await fetch('/api/custom/folder?' + p, { signal: controller.signal });
          if (r.status === 499) return;
          if (!r.ok) throw new Error(await busyAnswer(r) ? 'busy' : 'folder');
          const data = await r.json();
          if (gen !== generation) return;
          const html = data.items.map(item => {
            const fileParent = item.shown_in ?? (item.path.split('/').slice(0, -1).join('/') || category);
            const href = customUrl(category, item.type === 'folder' ? item.path : fileParent, item.type === 'folder' ? '' : item.file, path);
            const title = item.relative_title || (item.type === 'folder' ? item.name : item.title.split('｜').at(-1));
            const pills = item.type === 'hit' ? ''
              : (item.type === 'folder' && item.files > 1 ? `<span class="stat-pill secondary">${esc(t('custom_files', { n: fmt(item.files) }))}</span>` : '')
                + `<span class="stat-pill">${esc(t('stat_lines', { n: fmt(item.lines || 0) }))}</span>`;
            return `<a class="media-row${item.type === 'hit' ? ' custom-hit' : ''}" href="${esc(href)}" draggable="false"><span class="media-kind custom">${esc(t(item.type === 'folder' ? 'custom_folder' : 'custom_file'))}</span><span class="media-names"><div class="media-name">${esc(title)}</div>${item.type === 'hit' ? `<div class="main-sentence">${item.display_line}</div>` : ''}</span><span class="media-stats">${pills}</span></a>`;
          }).join('');
          results.querySelector('#custom-more')?.remove();
          let intro = '';
          if (data.page && reset) {
            fileTitle = data.page.title;
            intro = `<div class="custom-intro">${readerHtml(data.page)}</div>`;
          }
          results.classList.toggle('custom-prose', !!data.page);
          if (reset) {
            results.innerHTML = intro + (html ? `<div class="media-list" id="custom-list">${html}</div>` : intro ? '' : `<div class="status-line">${esc(t('media_none'))}</div>`);
            restoreFolds();
          }
          else results.querySelector('#custom-list')?.insertAdjacentHTML('beforeend', html);
          offset += data.items.length;
          if (data.has_more) {
            const button = document.createElement('button');
            button.id = 'custom-more'; button.className = 'btn'; button.textContent = t('custom_more');
            button.onclick = () => { button.disabled = true; load(false).then(save); };
            results.append(button);
          }
        } catch (e) { if (e.name !== 'AbortError' && gen === generation) results.innerHTML = e.message === 'busy' ? busyLine('2em') : `<div class="error-text">${esc(t('load_failed'))}</div>`; }
        finally { done(); }
      }
      async function loadFile(around = '') {
        generation++;
        const gen = generation;
        if (controller) controller.abort();
        controller = new AbortController();
        pages = null;
        const q = input.value.trim();
        const found = !!q && mode === 'content', titled = q && mode === 'title' ? foldTitleFilter(q) : '';
        const p = new URLSearchParams({ file, client: clientToken });
        if (found) {
          p.set('q', q);
          if (document.getElementById('custom-exact')?.checked) p.set('exact', 'on');
          if (document.getElementById('custom-ruby-only')?.checked) p.set('ruby_only', 'on');
        }
        if (titled) p.set('heading', q);
        if (around) p.set('at', around);
        const done = found || !results.querySelector('.episode-card') ? searching(gen) : () => {};
        try {
          const r = await fetch('/api/custom/file?' + p, { signal: controller.signal });
          if (r.status === 499) return;
          if (!r.ok) throw new Error(await busyAnswer(r) ? 'busy' : 'file');
          const data = await r.json();
          if (gen !== generation) return;
          p.delete('at');
          pages = { query: p, found, titled, start: data.start ?? 0, end: data.end ?? data.lines.length, total: data.total ?? data.lines.length };
          results.classList.toggle('custom-prose', data.kind === 'txt' || data.kind === 'md');
          fileTitle = data.title;
          results.innerHTML = readerHtml(data, found, titled) || `<div class="status-line">${esc(t(found ? 'no_results' : 'media_none'))}</div>`;
          if (results.querySelector('.episode-card')) {
            if (pages.start > 0) results.insertAdjacentHTML('afterbegin', '<div class="custom-sentinel-up"></div>');
            if (pages.end < pages.total) results.insertAdjacentHTML('beforeend', '<div class="custom-sentinel"></div>');
          }
          openKept = found;
          restoreFolds(found);
        } catch (e) { if (e.name !== 'AbortError' && gen === generation) results.innerHTML = e.message === 'busy' ? busyLine('2em') : `<div class="error-text">${esc(t('load_failed'))}</div>`; }
        finally { done(); }
      }
      async function loadPage(sentinel, up) {
        const gen = generation, mine = pages;
        const p = new URLSearchParams(mine.query);
        p.set(up ? 'before' : 'offset', String(up ? mine.start : mine.end));
        if (!up) sentinel.innerHTML = `<div class="status-line">${esc(t('loading'))}</div>`;
        try {
          const r = await fetch('/api/custom/file?' + p, { signal: controller.signal });
          if (gen !== generation || mine !== pages) return null;
          if (!r.ok) { sentinel.innerHTML = r.status === 499 ? '' : `<div class="error-text">${esc(t('load_failed'))}</div>`; return false; }
          const data = await r.json();
          if (gen !== generation || mine !== pages) return null;
          const card = results.querySelector('.episode-card');
          const box = document.createElement('div');
          box.innerHTML = readerHtml(data, mine.found, mine.titled);
          const added = box.querySelector('.episode-card');
          if (!card || !added) return false;
          restoreFolds(mine.found, added);
          if (up) {
            const keep = card.firstElementChild, before = keep ? keep.getBoundingClientRect().top : 0;
            card.prepend(...added.childNodes);
            if (keep) window.scrollBy(0, keep.getBoundingClientRect().top - before);
            mine.start = data.start;
            if (!mine.start) sentinel.remove();
          } else {
            card.append(...added.childNodes);
            mine.end = data.end;
            if (mine.end >= mine.total) sentinel.remove();
            else sentinel.innerHTML = '';
          }
          return true;
        } catch (e) {
          if (e.name === 'AbortError') return null;
          if (sentinel.isConnected) sentinel.innerHTML = `<div class="error-text">${esc(t('load_failed'))}</div>`;
          return false;
        }
      }
      let paging = false;
      const near = el => {
        if (!el || !el.isConnected) return false;
        const box = el.getBoundingClientRect();
        return box.top < window.innerHeight + 1500 && box.bottom > -1500;
      };
      async function pageIn() {
        if (paging) return;
        paging = true;
        try {
          while (pages) {
            const down = results.querySelector('.custom-sentinel'), up = results.querySelector('.custom-sentinel-up');
            const next = near(down) ? [down, false] : near(up) ? [up, true] : null;
            if (!next || await loadPage(...next) === false) break;
          }
        } finally { paging = false; }
        save();
      }
      const pageObserver = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting)) pageIn(); }, { rootMargin: '1500px 0px' });
      const watchPages = () => {
        pageObserver.disconnect();
        results.querySelectorAll('.custom-sentinel, .custom-sentinel-up').forEach(el => pageObserver.observe(el));
      };
      const run = () => (file ? loadFile().then(watchPages) : load()).then(save);
      {
        const buttons = head.querySelectorAll('[data-custom-mode]');
        const active = () => buttons.forEach(b => b.classList.toggle('active', b.dataset.customMode === mode));
        active();
        const form = document.getElementById('custom-search');
        const sortBox = document.getElementById('custom-sort');
        const drawSort = () => makeDropdown(sortBox, {
          options: CUSTOM_SORTS.map(v => ({ value: v, label: mediaSortLabel(v) })),
          value: customSort(), title: t('media_sort_title'), icon: ICON_ROWS,
          onChange: v => { store.set('customSort', v); drawSort(); if (!file) run(); },
        });
        drawSort();
        const show = () => { titleInput.hidden = mode !== 'title'; form.hidden = mode !== 'content'; sortBox.hidden = mode !== 'title'; fitDockedRow(); };
        show();
        buttons.forEach(b => b.onclick = () => { mode = b.dataset.customMode; active(); show(); (mode === 'title' ? titleInput : contentInput).focus(); run(); });
        [titleInput, contentInput].forEach(el => {
          el.addEventListener('compositionstart', () => { isComposing = true; });
          el.addEventListener('compositionend', () => { isComposing = false; });
          el.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.isComposing || isComposing || e.keyCode === 229)) e.preventDefault(); });
        });
        form.onsubmit = e => { e.preventDefault(); if (!isComposing) run(); };
        form.querySelectorAll('input[type=checkbox]').forEach(el => {
          el.closest('.exact-chip').classList.toggle('on', el.checked);
          el.onchange = () => { el.closest('.exact-chip').classList.toggle('on', el.checked); if (contentInput.value.trim()) run(); else save(); };
        });
        contentInput.oninput = () => { titleInput.value = contentInput.value; if (!contentInput.value.trim() && !isComposing) run(); };
        titleInput.oninput = () => { contentInput.value = titleInput.value; if (!isComposing) { clearTimeout(timer); timer = setTimeout(run, 180); } };
      }
      const aim = at && !at.note && at.rowid ? at.rowid : saved.top?.rowid || '';
      if (file) await loadFile(aim);
      else {
        await load();
        while (offset < (saved.loaded || 0) && results.querySelector('#custom-more')) await load(false);
      }
      showOpenNote(at, results);
      const target = at && !at.note && at.rowid && results.querySelector(`.custom-line[data-rowid="${CSS.escape(at.rowid)}"]`);
      const back = !at && saved.top && results.querySelector(`.custom-line[data-rowid="${CSS.escape(saved.top.rowid)}"]`);
      if (target) goToTargetLine(target);
      else if (back) window.scrollBy(0, back.getBoundingClientRect().top - saved.top.dy);
      else requestAnimationFrame(() => window.scrollTo(0, saved.y || 0));
      if (file) watchPages();
      setTitle(file ? (fileTitle || fileName) : (path || category));
    }
