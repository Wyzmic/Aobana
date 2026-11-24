    let settingsShown = false;
    function renderSettings(lib) {
      folderPicker = !!lib.folder_picker;
      renderMediaCard(lib);
      if (!document.querySelector('#set-known-words .known-preview:not([hidden])')) renderKnownWords();
      renderReaderSettings();
      renderDbCard(lib);
      renderPortCard(lib);
      renderSearchWorkersCard(lib.search_workers);
      settingsShown = true;
    }

    async function initSettingsTab() {
      setTitle(t('tab_settings'));
      renderLookCard();
      renderSettingsTabs();
      try {
        const cached = await fetch('/api/library/settings-snapshot').then(r => r.json());
        if (cached.settings) { renderSettings(cached.settings); renderSettingsTabs(); }
      } catch (e) {}
      if (typeof rmFetchPrefs === 'function') await rmFetchPrefs().catch(() => null);
      await refreshSettings();
      const target = settingsHashTarget();
      if (target && !target.matches('[data-set-pane]') && target.id !== 'set-reader') settingsScrollTo(target);
      if (window.location.hash === '#set-reader') {
        // From Reading mode's "More in Settings": the media it was showing, and for manga shown
        // as text, that part of manga's settings.
        const from = store.get('reader_settings_media');
        store.del('reader_settings_media');
        if (from) {
          store.set('set_reader_media', from === 'manga-text' ? 'manga' : from);
          renderReaderSettings();
        }
        const el = from === 'manga-text' && document.getElementById('set-reader-manga-text');
        if (el) settingsScrollTo(el);
      }
    }

    async function refreshSettings() {
      let lib;
      try { lib = await fetch('/api/library/settings').then(r => r.json()); }
      catch (e) {
        if (!settingsShown) document.getElementById('lib-data').innerHTML = `<div class="error-text">${esc(t('load_failed'))}</div>`;
        return;
      }
      renderSettings(lib);
      renderSettingsTabs();
    }

    // The theme and the language, side by side. A light theme and a dark theme, and which to
    // use: the device's light or dark, or always one (core.js themeChoice).
    function renderLookCard() {
      const card = document.getElementById('set-look');
      if (!card) return;
      const choice = themeChoice();
      const seg = (items, on, set) => `<div class="seg seg-fit">${items.map(([value, label, pre]) =>
        `<button type="button" class="seg-btn ${value === on ? 'active' : ''}" onclick="${set}('${value}')">${pre || ''}${esc(label)}</button>`).join('')}</div>`;
      const row = (label, body) => `<div class="set-look-row"><span class="set-look-label">${esc(label)}</span>${body}</div>`;
      const themes = list => list.map(v => [v, t('theme_' + v), `<span class="swatch ${v}"></span>`]);
      card.innerHTML = `
        <h3>${esc(t('set_look_title'))}</h3>
        <div class="set-look">
          ${row(t('theme_label'), seg([['device', t('set_theme_device')], ['light', t('set_theme_light')], ['dark', t('set_theme_dark')]], choice.mode, 'setLookMode'))}
          ${row(t('set_theme_light'), seg(themes(THEMES_LIGHT), choice.light, 'setLookLight'))}
          ${row(t('set_theme_dark'), seg(themes(THEMES_DARK), choice.dark, 'setLookDark'))}
          ${row(t('set_accent'), '<div id="set-accent-dd"></div>')}
          ${row(t('set_lang'), seg([['ja', '日本語'], ['en', 'English']], LANG, 'setLang'))}
        </div>`;
      makeDropdown(document.getElementById('set-accent-dd'), {
        options: ACCENTS.filter(([name]) => name !== 'device' || deviceAccentSupported()).map(([name, color]) => ({ value: name, label: t('accent_' + name), pre: `<span class="accent-dot" style="background:${color}"></span>` })),
        value: currentAccent(), left: true, title: t('set_accent'),
        onChange: v => { setAccent(v); renderLookCard(); },
      });
    }
    function setLookMode(v) { setThemeChoice('theme_mode', v); renderLookCard(); }
    function setLookLight(v) { setThemeChoice('theme_light', v); renderLookCard(); }
    function setLookDark(v) { setThemeChoice('theme_dark', v); renderLookCard(); }

    // One pane at a time, picked in a row like the bar's tabs, General first. A pane whose cards
    // are all hidden (its media off) has no tab. The open pane is kept in the address,
    // #set-reader, so a reload or a link lands on it.
    let setPaneOpen = '';
    function settingsHashTarget() {
      const id = decodeURIComponent(window.location.hash.slice(1));
      if (!id) return null;
      return document.querySelector(`[data-set-pane="${CSS.escape(id.replace(/^set-/, ''))}"]`) || document.getElementById(id);
    }
    function settingsScrollTo(el) {
      // Measured against the bar itself: --bar-h may not be set yet on a fresh load.
      const bar = document.querySelector('.topbar');
      const under = (bar ? bar.getBoundingClientRect().height : 0) + 12;
      window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - under, behavior: 'instant' });
    }
    function settingsPaneShown(pane) {
      return [...pane.children].some(card => getComputedStyle(card).display !== 'none');
    }
    function renderSettingsTabs() {
      const bar = document.getElementById('set-tabs');
      if (!bar) return;
      const panes = [...document.querySelectorAll('[data-set-pane]')];
      if (!setPaneOpen) {
        const target = settingsHashTarget();
        const pane = target && target.closest('[data-set-pane]');
        setPaneOpen = pane ? pane.dataset.setPane : 'general';
      }
      const shown = panes.filter(settingsPaneShown);
      if (!shown.some(p => p.dataset.setPane === setPaneOpen)) setPaneOpen = 'general';
      bar.innerHTML = shown.map(p => {
        const on = p.dataset.setPane === setPaneOpen;
        return `<button type="button" role="tab" class="nav-tab set-tab ${on ? 'active' : ''}" aria-selected="${on}" onclick="openSettingsPane('${p.dataset.setPane}')">${esc(t(p.dataset.setLabel))}</button>`;
      }).join('');
      bar.hidden = shown.length < 2;
      panes.forEach(p => { p.hidden = p.dataset.setPane !== setPaneOpen; });
    }
    window.addEventListener('hashchange', () => {
      if (!document.getElementById('set-tabs') || TAB !== 'settings') return;
      setPaneOpen = '';
      renderSettingsTabs();
      const target = settingsHashTarget();
      if (target && !target.matches('[data-set-pane]')) settingsScrollTo(target);
    });
    function openSettingsPane(name) {
      setPaneOpen = name;
      renderSettingsTabs();
      const url = window.location.pathname + window.location.search + (name === 'general' ? '' : `#set-${name}`);
      history.replaceState(history.state, '', url);
      window.scrollTo({ top: 0, behavior: 'instant' });
    }

    const MEDIA_DB = { subs: 'subs.db', books: 'epub.db', manga: 'manga.db', custom: 'custom.db' };
    const MEDIA_KINDS = ['subs', 'books', 'manga', 'custom'];
    function renderMediaCard(lib, msg) {
      const on = lib.media || { subs: true, books: true, manga: false, custom: false };
      if (typeof lib.subtitle_tags === 'boolean') syncSubTags(lib.subtitle_tags);
      syncMediaOn(lib.media);
      if (settingsShown) renderReaderSettings();
      settingsLib = lib;
      const rows = MEDIA_KINDS.map(which => {
        const dirs = mediaDirs(lib, which);
        const size = (lib.db_sizes || {})[MEDIA_DB[which]];
        const drop = size == null ? '' : `<button class="btn set-drop" onclick="askDrop('${which}')">${esc(t('set_drop', { size: fmtBytes(size) }))}</button>`;
        const dropControl = `<span class="set-drop-home" hidden></span><span class="set-drop-btns" ${drop ? '' : 'hidden'}>${drop}</span>`;
        const dropOwnRow = dirs.length > 1;
        const folderRow = (path, i) => `<div class="set-folder">
            <span class="path">${esc(path)}</span>
            <div class="btns lib-view-btns">
              ${ON_PHONE ? '' : `<button class="btn" onclick="openFolder('${which}', this, ${i})">${esc(t('lib_open'))}</button>`}
              <button class="btn" onclick="changeFolder('${which}', '', ${i})">${esc(t('lib_change'))}</button>
              ${dirs.length < 2 ? '' : `<button type="button" class="btn" onclick="askRemoveFolder('${which}', ${i}, this)">${esc(t('set_folder_remove'))}</button>`}
              ${i === dirs.length - 1 && !dropOwnRow ? dropControl : ''}
            </div>
            <div class="set-folder-ask" hidden></div>
          </div>`;
        const folder = !on[which] ? '' : `
          ${dirs.length ? dirs.map(folderRow).join('') + (dropOwnRow && drop ? `<div class="btns lib-view-btns set-drop-row">${dropControl}</div>` : '') : `<div class="facts"><div>${esc(t('set_not_set'))}</div></div>
          <div class="btns lib-view-btns"><button class="btn" onclick="changeFolder('${which}', '', 0)">${esc(t('lib_change'))}</button>${dropControl}</div>`}
          <div class="lib-edit" hidden>
            <input type="text" value="" placeholder="${esc(t('lib_change_hint'))}" spellcheck="false">
            <div class="btns">
              <button class="btn primary" onclick="saveFolder('${which}')">${esc(t('lib_save'))}</button>
              <button class="btn" onclick="toggleFolderEdit('${which}', false)">${esc(t('lib_cancel'))}</button>
            </div>
            <div class="lib-msg facts" style="margin:0.5em 0 0;"></div>
          </div>
`;
        const buttons = `${on[which] || !drop ? '' : `<div class="btns">${dropControl}</div>`}
          <div class="lib-open-msg facts" role="status"></div>
          <div class="set-drop-ask" hidden></div>
          ${which === 'subs' && on.subs ? `<div class="set-sub-tags">
            <div class="facts">${esc(t('set_sub_tags'))}</div>
            <div class="seg seg-fit" style="margin-top:0.4em;">
              <button type="button" class="seg-btn ${subTagsOn ? '' : 'active'}" onclick="setSubTags(false)">${esc(t('lib_cache_off'))}</button>
              <button type="button" class="seg-btn ${subTagsOn ? 'active' : ''}" onclick="setSubTags(true)">${esc(t('lib_cache_on'))}</button>
            </div>
          </div>` : ''}
          ${which === 'custom' && on.custom ? `<div class="set-sub-tags">
            <div class="facts">${esc(t('set_custom_trim'))}</div>
            <div class="seg seg-fit" style="margin-top:0.4em;">
              <button type="button" class="seg-btn ${lib.custom_trim === false ? 'active' : ''}" onclick="setCustomTrim(false)">${esc(t('lib_cache_off'))}</button>
              <button type="button" class="seg-btn ${lib.custom_trim === false ? '' : 'active'}" onclick="setCustomTrim(true)">${esc(t('lib_cache_on'))}</button>
            </div>
            ${lib.custom_trim_pending ? `<div class="notice" style="margin-top:0.6em;">${t('set_custom_trim_pending', { n: fmt(lib.custom_trim_pending) })}</div>` : ''}
          </div>
          <div class="set-sub-tags">
            <div class="facts">${esc(t('set_custom_ruby'))}</div>
            <div class="seg seg-fit" style="margin-top:0.4em;">
              <button type="button" class="seg-btn ${lib.custom_ruby === false ? 'active' : ''}" onclick="setCustomRuby(false)">${esc(t('lib_cache_off'))}</button>
              <button type="button" class="seg-btn ${lib.custom_ruby === false ? '' : 'active'}" onclick="setCustomRuby(true)">${esc(t('lib_cache_on'))}</button>
            </div>
            ${lib.custom_ruby_pending ? `<div class="notice" style="margin-top:0.6em;">${t('set_custom_trim_pending', { n: fmt(lib.custom_ruby_pending) })}</div>` : ''}
          </div>` : ''}`;
        return `<div class="set-media-row" id="set-media-${which}">
          <div class="btns set-media-head">
            <strong>${esc(t('set_media_' + which))}</strong>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${on[which] ? '' : 'active'}" onclick="setMediaOn('${which}', false)">${esc(t('lib_cache_off'))}</button>
              <button type="button" class="seg-btn ${on[which] ? 'active' : ''}" onclick="setMediaOn('${which}', true)">${esc(t('lib_cache_on'))}</button>
            </div>
            ${on[which] ? `<button type="button" class="btn set-folder-add" onclick="changeFolder('${which}', '', ${dirs.length})" aria-label="${esc(t('set_folder_add'))}">+</button>` : ''}
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

    // A subtitle's (speaker) tags in search results, on or off: the page hides them, the API keeps
    // them (Aobana Reibun has its own names toggle)
    let subTagsOn = MEDIA_BOOT.subtitle_tags !== false;
    function syncSubTags(value) {
      subTagsOn = value;
      document.documentElement.classList.toggle('sub-tags-off', !value);
    }
    syncSubTags(subTagsOn);
    async function setSubTags(value) {
      const res = await apiPost('/api/library', { subtitle_tags: value }).catch(() => ({ error: 'network' }));
      if (!res.error) syncSubTags(value);
      await refreshSettings();
      if (res.error) document.querySelector('#set-media .set-media-msg').innerHTML = `<span class="warn">${esc(t('error'))}</span>`;
    }

    // Custom's .txt lines read with or without their edge spaces: custom.db is read again by the
    // next Index library (paths.custom_trim)
    async function setCustomRuby(value) {
      const res = await apiPost('/api/library', { custom_ruby: value }).catch(() => ({ error: 'network' }));
      await refreshSettings();
      if (res.error) document.querySelector('#set-media .set-media-msg').innerHTML =
        `<span class="warn">${esc(res.error === 'busy' ? t('lib_err_busy') : t('error'))}</span>`;
    }

    async function setCustomTrim(value) {
      const res = await apiPost('/api/library', { custom_trim: value }).catch(() => ({ error: 'network' }));
      await refreshSettings();
      if (res.error) document.querySelector('#set-media .set-media-msg').innerHTML =
        `<span class="warn">${esc(res.error === 'busy' ? t('lib_err_busy') : t('error'))}</span>`;
    }

    async function setMediaOn(which, on) {
      const res = await apiPost('/api/library', { media: { [which]: on } }).catch(() => ({ error: 'network' }));
      await refreshSettings();
      if (res.error) document.querySelector('#set-media .set-media-msg').innerHTML =
        `<span class="warn">${esc(res.error === 'busy' ? t('lib_err_busy') : String(res.error).startsWith('overlap:') ? overlapText(res.error) : t('lib_err_notfound'))}</span>`;
    }

    function askDrop(which) {
      const row = document.getElementById(`set-media-${which}`);
      const size = labelText(row.querySelector('.set-drop')).match(/[（(](.*)[）)]/);
      const ask = row.querySelector('.set-drop-ask');
      row.querySelector('.set-drop-btns').hidden = true;
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
      row.querySelector('.set-drop-btns').hidden = false;
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

    let libRefreshFlight = null;
    let libRefreshTimer = null;
    let libPageGeneration = 0;
    function refreshLibrary() {
      if (TAB !== 'library') return Promise.resolve();
      if (libRefreshFlight) return libRefreshFlight;
      if (libRefreshTimer) clearTimeout(libRefreshTimer);
      libRefreshTimer = null;
      const generation = libPageGeneration;
      libRefreshFlight = fetchLibrary(generation).finally(() => { libRefreshFlight = null; });
      return libRefreshFlight;
    }
    async function fetchLibrary(generation) {
      let lib;
      try { lib = await fetch('/api/library').then(r => r.json()); }
      catch (e) {
        if (generation === libPageGeneration && TAB === 'library') document.getElementById('lib-folders').innerHTML = `<div class="error-text">${esc(t('load_failed'))}</div>`;
        return;
      }
      if (generation !== libPageGeneration || TAB !== 'library') return;
      syncMediaOn(lib.media);
      updateIndexBody(document.getElementById('lib-folders'),
        (MEDIA_ON.subs ? folderCard('subs', t('lib_subs'), mediaDirs(lib, 'subs'), lib.subs_disk, lib.subs_indexed, lib.counting) : '') +
        (MEDIA_ON.epub ? folderCard('books', t('lib_books'), mediaDirs(lib, 'books'), lib.books_disk, lib.books_indexed, lib.counting) : '') +
        (MEDIA_ON.manga ? folderCard('manga', t('lib_manga'), mediaDirs(lib, 'manga'), lib.manga_disk, lib.manga_indexed, lib.counting) : '') +
        (MEDIA_ON.custom ? folderCard('custom', t('lib_custom'), mediaDirs(lib, 'custom'), lib.custom_disk, lib.custom_indexed, lib.counting) : ''));
      libLast = lib;
      syncCheckScope();
      renderWorkersCard(lib.workers);
      document.getElementById('lib-refresh').hidden = !lib.updating;
      libUpdating = !!lib.updating; syncRunButtons();
      if (lib.updating) {
        updateIndexBody(document.getElementById('lib-refresh'), `<span class="spinner" aria-hidden="true"></span>${esc(t('lib_updating'))}`);
        if (!lib.index?.running) libRefreshTimer = setTimeout(() => { libRefreshTimer = null; refreshLibrary(); }, 1000);
      }
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
        if (disk.other) facts += `<div>${esc(t('lib_other_' + which, { n: fmt(disk.other) }))}</div>`;
        if (disk.filtered) facts += `<div>${esc(t('lib_filtered', { n: fmt(disk.filtered) }))}</div>`;
      }
      facts += indexed ? `<div>${esc(t('lib_indexed_' + which, { files: fmt(indexed.files), rows: fmt(indexed.rows) }))}</div>`
        : `<div>${esc(t('lib_updating'))}</div>`;
      // Custom's files the index left unread, read from custom.db, so the line stays after a restart
      const skipped = (indexed && indexed.skipped) || {};
      if (skipped.unsupported) facts += `<div>${esc(t('lib_json_unsupported', { n: fmt(skipped.unsupported) }))}</div>`;
      if (skipped.empty) facts += `<div>${esc(t('lib_md_empty', { n: fmt(skipped.empty) }))}</div>`;
      return facts;
    }

    const libFolderEdit = {};
    const libFolderMsg = {};
    // Several folders: each path listed; Change and Open folder are per folder in Settings only
    function folderCard(which, title, dirs, disk, indexed, counting) {
      const editing = !!libFolderEdit[which];
      const path = dirs[0] ?? null;
      return `<div class="lib-card" id="lib-card-${which}">
        <h3>${esc(title)}</h3>
        ${which === 'custom' ? `<div class="facts">${esc(t('lib_custom_note'))}</div>` : ''}
        ${dirs.map(d => `<span class="path">${esc(d)}</span>`).join('')}
        <div class="facts lib-facts">${folderFacts(which, path, disk, indexed, counting)}</div>
        <div class="lib-edit" ${editing ? '' : 'hidden'}>
          <input type="text" value="${esc(path ?? '')}" placeholder="${esc(t('lib_change_hint'))}" spellcheck="false">
          <div class="btns">
            <button class="btn primary" onclick="saveFolder('${which}', 'lib')">${esc(t('lib_save'))}</button>
            <button class="btn" onclick="toggleFolderEdit('${which}', false, 'lib')">${esc(t('lib_cancel'))}</button>
          </div>
        </div>
        <div class="btns lib-view-btns" ${editing || dirs.length > 1 ? 'hidden' : ''}>
          ${ON_PHONE ? '' : `<button class="btn" onclick="openFolder('${which}', this, 0)" ${disk ? '' : 'disabled'}>${esc(t('lib_open'))}</button>`}
          <button class="btn" onclick="changeFolder('${which}', 'lib', 0)">${esc(t('lib_change'))}</button>
        </div>
        <div class="lib-msg facts" style="margin:0.5em 0 0;">${libFolderMsg[which] || ''}</div>
        <div class="lib-open-msg facts" role="status"></div>
      </div>`;
    }

    function outdatedMedia(lib) {
      return [['subs', lib.subs_outdated], ['epub', lib.books_outdated], ['manga', lib.manga_outdated], ['custom', lib.custom_outdated]]
        .filter(([kind, count]) => MEDIA_ON[kind] && count > 0);
    }
    function tablesWhy(missing) {
      const all = new Set(missing);
      const why = [];
      if (all.has('repeats')) why.push(t('tables_why_counts'));
      if (all.has('kanji')) why.push(t('tables_why_reading'));
      else if ([...all].some(m => m !== 'repeats')) why.push(t('tables_why_search'));
      return why.join(LANG === 'ja' ? '' : ' ');
    }
    let focusOptimize = PARAMS.get('focus') === 'optimize';
    function renderOutdated(lib) {
      const box = document.getElementById('lib-outdated');
      const button = document.getElementById('lib-optimize');
      const outdated = new Set(outdatedMedia(lib).map(([kind]) => kind));
      const lacking = [['subs', lib.subs_tables], ['epub', lib.books_tables], ['manga', lib.manga_tables], ['custom', lib.custom_tables]]
        .filter(([kind, missing]) => MEDIA_ON[kind] && !outdated.has(kind) && (missing || []).length);
      const tables = lacking.map(([kind]) => kind);
      button.hidden = !(tables.length || optimizeDoneThisVisit);
      button.disabled = !!(lib.index && lib.index.running) || libBusy() || optimizeDoneThisVisit;
      button.querySelector('span').textContent = t(optimizeDoneThisVisit ? 'lib_tables_done_short' : 'lib_tables_run');
      if (focusOptimize) {
        focusOptimize = false;
        const url = new URL(window.location.href);
        url.searchParams.delete('focus');
        history.replaceState(null, '', url);
        if (!button.hidden) button.scrollIntoView({ block: 'center' });
      }
      let html = '';
      if (tables.length && !optimizeDoneThisVisit) {
        html += `<div>${esc(t('lib_tables', { which: tables.map(k => t('lib_stage_' + k)).join(LANG === 'ja' ? '・' : ' · '),
                                              why: tablesWhy(lacking.flatMap(([, missing]) => missing)) }))}</div>`;
      }
      box.innerHTML = html;
      box.hidden = !html;
    }

    let folderPicker = false;
    async function pickFolder(card, which, title, index) {
      const msg = card.querySelector('.lib-pick-msg') || card.querySelector('.lib-msg');
      const buttons = [...card.querySelectorAll('.lib-view-btns button, .set-folder-add')];
      const was = buttons.map(b => b.disabled);
      buttons.forEach(b => b.disabled = true);
      msg.textContent = t('lib_picking');
      const body = index == null ? { which, title } : { which, title, index };
      const res = await apiPost('/api/library/pick', body).catch(() => ({ status: 'unavailable' }));
      buttons.forEach((b, i) => b.disabled = was[i]);
      msg.textContent = '';
      return res;
    }
    const folderRowOf = (which, place) => document.getElementById(place === 'lib' ? `lib-card-${which}` : `set-media-${which}`);
    let settingsLib = null;
    const mediaDirs = (lib, which) => lib[which + '_dirs'] || (lib[which + '_dir'] != null ? [lib[which + '_dir']] : []);
    function overlapText(error) {
      const other = String(error).split(':')[2] || '';
      const kind = MEDIA_KINDS.find(k => other === k + '_dir') || 'subs';
      return t('lib_err_overlap', { media: t('set_media_' + kind) });
    }
    const folderEditAt = {};
    const folderEditVersion = new WeakMap();
    const folderSaveFlight = new WeakSet();
    function clearFolderMessages(card) {
      card.querySelectorAll('.lib-msg, .lib-pick-msg, .lib-open-msg').forEach(el => el.textContent = '');
    }
    const bumpFolderEdit = card => folderEditVersion.set(card, (folderEditVersion.get(card) || 0) + 1);
    async function changeFolder(which, place, index = 0) {
      const card = folderRowOf(which, place);
      clearFolderMessages(card);
      bumpFolderEdit(card);
      folderEditAt[which] = index;
      if (place === 'lib') libFolderMsg[which] = '';
      if (!folderPicker) return toggleFolderEdit(which, true, place);
      const dirs = mediaDirs((place === 'lib' ? libLast : settingsLib) || {}, which);
      const res = await pickFolder(card, which, t('lib_' + which), Math.min(index, Math.max(dirs.length - 1, 0)));
      if (res.status === 'unavailable') return toggleFolderEdit(which, true, place);
      if (res.status !== 'ok') return;
      card.querySelector('.lib-edit input').value = res.path;
      toggleFolderEdit(which, true, place);
      await saveFolder(which, place);
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

    function toggleFolderEdit(which, on, place) {
      const card = folderRowOf(which, place);
      if (place === 'lib') libFolderEdit[which] = on;
      const input = card.querySelector('.lib-edit input');
      if (on && !input.value) input.value = mediaDirs((place === 'lib' ? libLast : settingsLib) || {}, which)[folderEditAt[which] ?? 0] ?? '';
      if (!on) {
        input.value = '';
        clearFolderMessages(card);
        if (place === 'lib') libFolderMsg[which] = '';
        bumpFolderEdit(card);
      }
      card.querySelector('.lib-edit').hidden = !on;
      card.querySelectorAll('.lib-view-btns').forEach(el => el.hidden = on);
      card.querySelectorAll('.set-folder-add').forEach(el => el.style.visibility = on ? 'hidden' : '');
      if (place !== 'lib') {
        const drop = card.querySelector('.set-drop-btns'), home = card.querySelector('.set-drop-home');
        if (drop && home) {
          if (on) card.querySelector('.lib-edit .btns').appendChild(drop);
          else home.after(drop);
        }
      }
      if (on) input.focus();
    }

    function askRemoveFolder(which, index, button) {
      const row = button.closest('.set-folder');
      const ask = row.querySelector('.set-folder-ask');
      row.querySelector('.lib-view-btns').hidden = true;
      ask.hidden = false;
      ask.innerHTML = `<div class="notice">${esc(t('set_folder_remove_confirm', { media: t('set_media_' + which) }))}</div>
        <div class="btns">
          <button class="btn primary" onclick="removeFolder('${which}', ${index})">${esc(t('set_folder_remove_yes'))}</button>
          <button class="btn" onclick="this.closest('.set-folder').querySelector('.lib-view-btns').hidden = false; this.closest('.set-folder-ask').hidden = true">${esc(t('lib_cancel'))}</button>
        </div>`;
    }
    async function removeFolder(which, index) {
      const dirs = mediaDirs(settingsLib || {}, which);
      if (dirs.length < 2) return;
      await postFolders(which, '', dirs.filter((_, i) => i !== index));
    }

    async function saveFolder(which, place) {
      const card = folderRowOf(which, place);
      const dirs = [...mediaDirs((place === 'lib' ? libLast : settingsLib) || {}, which)];
      dirs[Math.min(folderEditAt[which] ?? 0, dirs.length)] = card.querySelector('.lib-edit input').value;
      return postFolders(which, place, dirs);
    }

    async function postFolders(which, place, dirs) {
      const card = folderRowOf(which, place);
      if (folderSaveFlight.has(card)) return false;
      const edit = card.querySelector('.lib-edit');
      const msg = (edit && !edit.hidden && edit.querySelector('.lib-msg')) || card.querySelector('.lib-pick-msg') || card.querySelector('.lib-msg');
      clearFolderMessages(card);
      const generation = folderEditVersion.get(card) || 0;
      const buttons = [...card.querySelectorAll('.lib-edit button')];
      const was = buttons.map(b => b.disabled);
      folderSaveFlight.add(card);
      buttons.forEach(b => b.disabled = true);
      let res;
      try { res = await apiPost('/api/library', { [which + '_dirs']: dirs }).catch(() => ({ error: 'network' })); }
      finally {
        folderSaveFlight.delete(card);
        buttons.forEach((b, i) => b.disabled = was[i]);
      }
      if (!card.isConnected || generation !== (folderEditVersion.get(card) || 0)) return false;
      if (res.error) {
        const error = String(res.error);
        msg.innerHTML = `<span class="warn">${esc(error === 'busy' ? t('lib_err_busy') : error.startsWith('overlap:') ? overlapText(error) : error.startsWith('not_full') ? t('lib_err_notfull', { path: (card.querySelector('.path') || {}).textContent || (MEDIA_BOOT.defaults || {})[which] || '' }) : t('lib_err_notfound'))}</span>`;
        if (place === 'lib') libFolderMsg[which] = msg.innerHTML;
        return false;
      }
      if (place === 'lib') {
        libFolderEdit[which] = false;
        libFolderMsg[which] = esc(t('lib_saved'));
        if (libRefreshFlight) await libRefreshFlight;
        await refreshLibrary();
        return true;
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
      const names = ['subs.db', 'epub.db', 'manga.db'].concat(MEDIA_ON.custom || sizes['custom.db'] != null ? ['custom.db'] : []);
      const facts = names.map(n => `<div>${esc(n)}: ${esc(fmtBytes(sizes[n]))}</div>`).join('');
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
      // The file's entries, cleaned and each once; then the choice: add to these, or replace them
      const fileItems = [];
      const seen = new Set();
      for (const orig of items) {
        const s = cleanFavorite(orig);
        if (!s) continue;
        const id = lineId(s.line);
        if (seen.has(id)) continue;
        seen.add(id);
        if (s.id !== id && s.legacy_id === undefined && typeof s.id === 'string') s.legacy_id = s.id;
        s.id = id;
        fileItems.push(s);
      }
      if (!fileItems.length) { favNote(t('fav_bad_file'), true); return; }
      favPending = { name: file.name, items: fileItems };
      favAskingReplace = false;
      document.getElementById('fav-note').hidden = true;
      renderFavChoice();
    }

    let favPending = null;
    let favAskingReplace = false;

    function renderFavChoice() {
      const box = document.getElementById('fav-choice');
      if (!box) return;
      if (!favPending) { box.hidden = true; box.innerHTML = ''; return; }
      const have = new Set(savedSentences.map(s => s.id));
      const n = favPending.items.length;
      const added = favPending.items.filter(s => !have.has(s.id)).length;
      const head = `<div class="reader-import-file">${esc(favPending.name)}</div>
        <div class="muted">${esc(t('fav_import_found', { n: fmt(n), added: fmt(added), same: fmt(n - added) }))}</div>`;
      box.innerHTML = favAskingReplace
        ? `${head}<div class="warn">${esc(t('fav_import_replace_ask', { cur: fmt(savedSentences.length), n: fmt(n) }))}</div>
          <div class="btns">
            <button type="button" class="btn danger" onclick="applyFavImport('replace')">${esc(t('fav_import_replace'))}</button>
            <button type="button" class="btn" onclick="favAskingReplace = false; renderFavChoice()">${esc(t('rm_notes_cancel'))}</button>
          </div>`
        : `${head}<div class="btns">
            <button type="button" class="btn primary" onclick="applyFavImport('add')">${esc(t('fav_import_add'))}</button>
            <button type="button" class="btn" onclick="favAskingReplace = true; renderFavChoice()">${esc(t('fav_import_replace'))}</button>
            <button type="button" class="btn" onclick="favPending = null; renderFavChoice()">${esc(t('rm_notes_cancel'))}</button>
          </div>`;
      box.hidden = false;
    }

    function applyFavImport(how) {
      if (!favPending) return;
      const items = favPending.items;
      favPending = null;
      favAskingReplace = false;
      renderFavChoice();
      if (store.get('savedSentences_backup_v1') === null) store.set('savedSentences_backup_v1', store.get('savedSentences', '[]'));
      if (how === 'replace') {
        // The list a replace took the place of, kept until the next replace
        store.set('savedSentences_before_replace', store.get('savedSentences', '[]'));
        savedSentences = items.slice();
        store.set('savedSentences', JSON.stringify(savedSentences));
        favNote(t('fav_replaced', { n: fmt(items.length) }));
        return;
      }
      const have = new Set(savedSentences.map(s => s.id));
      const incoming = items.filter(s => !have.has(s.id));
      if (incoming.length) {
        savedSentences = savedSentences.concat(incoming);
        store.set('savedSentences', JSON.stringify(savedSentences));
      }
      favNote(t('fav_imported', { added: fmt(incoming.length), same: fmt(items.length - incoming.length) }));
    }

    let readerBackupPending = null;
    let readerBackupMode = 'keep_newer';
    let readerBackupAskingReplace = false;

    function readerBackupNote(msg, warn = false) {
      const el = document.getElementById('reader-backup-note');
      if (!el) return;
      el.hidden = !msg;
      el.className = 'notice' + (warn ? ' warn' : ' ok');
      el.textContent = msg || '';
    }

    function readerBackupErrorText(code) {
      const key = {
        too_large: 'reader_backup_err_too_large',
        invalid_json: 'reader_backup_err_json',
        wrong_kind: 'reader_backup_err_kind',
        newer_version: 'reader_backup_err_version',
      }[code] || 'reader_backup_err_failed';
      return t(key);
    }

    async function exportReaderData() {
      readerBackupNote('');
      let doc;
      try {
        const r = await fetch('/api/reading/export');
        if (!r.ok) throw new Error('export');
        doc = await r.json();
      } catch (e) {
        readerBackupNote(t('reader_backup_err_failed'), true);
        return;
      }
      const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `aobana-reader-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      const worksN = Object.keys((doc.state && doc.state.works) || {}).length;
      const notesN = Object.values((doc.notes && doc.notes.works) || {}).reduce((s, l) => s + (Array.isArray(l) ? l.length : 0), 0);
      readerBackupNote(t('reader_backup_exported', { works: fmt(worksN), notes: fmt(notesN) }));
    }

    async function pickReaderBackupFile(input) {
      const file = input.files && input.files[0];
      input.value = '';
      if (!file) return;
      readerBackupNote('');
      readerBackupPending = null;
      readerBackupMode = 'keep_newer';
      readerBackupAskingReplace = false;
      const box = document.getElementById('reader-import-preview');
      if (box) { box.hidden = true; box.innerHTML = ''; }
      if (file.size > 20 * 1024 * 1024) {
        readerBackupNote(readerBackupErrorText('too_large'), true);
        return;
      }
      let buf;
      try { buf = await file.arrayBuffer(); } catch (e) {
        readerBackupNote(readerBackupErrorText('invalid_json'), true);
        return;
      }
      let res;
      try {
        const r = await fetch('/api/reading/import?dry_run=1', {
          method: 'POST',
          headers: { 'Content-Type': 'application/octet-stream', ...API_HEADERS },
          body: buf,
        });
        res = await r.json();
        if (!r.ok || res.error) {
          readerBackupNote(readerBackupErrorText(res && res.error), true);
          return;
        }
      } catch (e) {
        readerBackupNote(t('reader_backup_err_failed'), true);
        return;
      }
      readerBackupPending = { name: file.name, buf, counts: res.counts };
      renderReaderBackupPreview();
    }

    function setReaderBackupMode(mode) {
      readerBackupMode = mode;
      readerBackupAskingReplace = false;
      renderReaderBackupPreview();
    }

    function cancelReaderBackupImport() {
      readerBackupPending = null;
      readerBackupAskingReplace = false;
      const box = document.getElementById('reader-import-preview');
      if (box) { box.hidden = true; box.innerHTML = ''; }
    }

    function renderReaderBackupPreview() {
      const box = document.getElementById('reader-import-preview');
      if (!box || !readerBackupPending) return;
      const c = readerBackupPending.counts || {};
      const row = (label, g) => `<tr>
        <td>${esc(label)}</td>
        <td>${esc(fmt((g && g.new) || 0))}</td>
        <td>${esc(fmt((g && g.newer_here) || 0))}</td>
        <td>${esc(fmt((g && g.newer_in_file) || 0))}</td>
        <td>${esc(fmt((g && g.same) || 0))}</td>
      </tr>`;
      const modes = [
        ['keep_newer', 'reader_backup_mode_newer', 'reader_backup_mode_newer_note'],
        ['merge', 'reader_backup_mode_merge', 'reader_backup_mode_merge_note'],
        ['replace', 'reader_backup_mode_replace', 'reader_backup_mode_replace_note'],
      ];
      const activeMode = modes.find(m => m[0] === readerBackupMode) || modes[0];
      box.innerHTML = `
        <div class="reader-import-file">${esc(readerBackupPending.name)}</div>
        <div class="reader-import-table-wrap">
          <table class="summary-table reader-import-table">
            <thead><tr>
              <th></th>
              <th>${esc(t('reader_backup_col_new'))}</th>
              <th>${esc(t('reader_backup_col_here'))}</th>
              <th>${esc(t('reader_backup_col_file'))}</th>
              <th>${esc(t('reader_backup_col_same'))}</th>
            </tr></thead>
            <tbody>
              ${row(t('reader_backup_row_works'), c.works)}
              ${row(t('reader_backup_row_bookmarks'), c.bookmarks)}
              ${row(t('reader_backup_row_notes'), c.notes)}
            </tbody>
          </table>
        </div>
        <div class="seg seg-fit reader-import-modes">
          ${modes.map(([val, lbl]) => `<button type="button" class="seg-btn ${val === readerBackupMode ? 'active' : ''}" onclick="setReaderBackupMode('${val}')">${esc(t(lbl))}</button>`).join('')}
        </div>
        <div class="muted reader-import-mode-note">${esc(t(activeMode[2]))}</div>
        ${readerBackupAskingReplace ? `<div class="notice warn">${esc(t('reader_backup_replace_ask'))}</div>
          <div class="btns">
            <button type="button" class="btn danger" id="reader-import-confirm-replace" onclick="runReaderBackupImport(true)">${esc(t('reader_backup_replace_yes'))}</button>
            <button type="button" class="btn" onclick="readerBackupAskingReplace=false;renderReaderBackupPreview()">${esc(t('lib_cancel'))}</button>
          </div>` : `<div class="btns">
            <button type="button" class="btn primary" id="reader-import-apply" onclick="runReaderBackupImport(false)">${esc(t('fav_import'))}</button>
            <button type="button" class="btn" onclick="cancelReaderBackupImport()">${esc(t('lib_cancel'))}</button>
          </div>`}`;
      box.hidden = false;
    }

    let readerBackupBusy = false;
    async function runReaderBackupImport(confirmedReplace) {
      if (!readerBackupPending || readerBackupBusy) return;
      if (readerBackupMode === 'replace' && !confirmedReplace) {
        readerBackupAskingReplace = true;
        renderReaderBackupPreview();
        return;
      }
      const { buf } = readerBackupPending;
      const mode = readerBackupMode;
      readerBackupBusy = true;
      const applyBtn = document.getElementById('reader-import-apply');
      const repBtn = document.getElementById('reader-import-confirm-replace');
      if (applyBtn) applyBtn.disabled = true;
      if (repBtn) repBtn.disabled = true;
      let res;
      try {
        const r = await fetch(`/api/reading/import?mode=${encodeURIComponent(mode)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/octet-stream', ...API_HEADERS },
          body: buf,
        });
        res = await r.json();
        if (!r.ok || res.error) {
          readerBackupNote(readerBackupErrorText(res && res.error), true);
          return;
        }
      } catch (e) {
        readerBackupNote(t('reader_backup_err_failed'), true);
        return;
      } finally {
        readerBackupBusy = false;
        if (applyBtn) applyBtn.disabled = false;
        if (repBtn) repBtn.disabled = false;
      }
      cancelReaderBackupImport();
      if (typeof savedWorks !== 'undefined') savedWorks = null;
      if (typeof savedNotes !== 'undefined') savedNotes = null;
      if (mode === 'replace' && typeof rmFetchPrefs === 'function') {
        await rmFetchPrefs().catch(() => null);
        renderReaderSettings();
      }
      readerBackupNote(t('reader_backup_imported'));
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
      fetch('/api/profile-handoff', { method: 'POST', keepalive: body.length < 60000, headers: { 'Content-Type': 'application/json', ...API_HEADERS }, body }).catch(() => {});
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
      renderWorkersTable('workers-table', { cpus: w.cpus, recommended: w.recommended }, [
        ['workers_col_index', key => workersSpeed(WORKERS_SPEED.index[key])],
        ['workers_col_cpu', key => workersCpu(WORKERS_CPU.index[key])],
        ['workers_col_check', key => workersSpeed(WORKERS_SPEED.check[key])],
        ['workers_col_cpu', key => workersCpu(WORKERS_CPU.check[key])],
      ]);
      const input = document.getElementById('workers-input');
      input.max = w.max;
      const shown = String(w.saved || w.effective);
      const typing = document.activeElement === input || (input.dataset.shown != null && input.value !== input.dataset.shown);
      if (!typing) { input.value = shown; input.dataset.shown = shown; }
      const off = w.env || !w.parallel;
      document.querySelectorAll('#lib-workers input, #lib-workers button').forEach(el => { el.disabled = off; });
      const note = document.getElementById('workers-note');
      note.className = 'notice';
      if (w.env) { note.textContent = t('workers_env'); note.hidden = false; }
      else if (!w.parallel) { note.textContent = t('workers_single'); note.hidden = false; }
      else if (!w.saved) { note.textContent = t('workers_is_auto'); note.hidden = false; }
      else workersHint();
    }

    function clampWorkersInput(el, max, current, final) {
      if (!el) return;
      const value = el.value.trim();
      if (!value || !Number.isFinite(Number(value))) el.value = final ? String(current) : '';
      else el.value = String(Math.min(max, Math.max(1, Math.trunc(Number(value)))));
    }

    function workersHint(final = false) {
      const w = workersFacts;
      const input = document.getElementById('workers-input');
      if (w) clampWorkersInput(input, w.max, w.saved || w.effective, final);
      const note = document.getElementById('workers-note');
      const n = Number(input.value);
      note.className = 'notice';
      if (w && n > w.recommended) { note.textContent = t('workers_over', { rec: fmt(w.recommended) }); note.hidden = false; }
      else note.hidden = true;
    }

    async function saveWorkers(value) {
      const note = document.getElementById('workers-note');
      if (!value) workersHint(true);
      const v = value || document.getElementById('workers-input').value.trim();
      const res = await apiPost('/api/library', { index_workers: v }).catch(() => ({ error: 'network' }));
      if (res.error) {
        note.textContent = t('workers_bad', { max: workersFacts ? fmt(workersFacts.max) : '' });
        note.className = 'notice warn'; note.hidden = false; return;
      }
      await refreshSettings();
      if (value !== 'auto') { note.textContent = t('workers_saved'); note.className = 'notice ok'; note.hidden = false; }
    }

    const WORKERS_SPEED = {
      index: { one: ['slower', '4.69'], q: ['slower', '1.09'], tq: ['same'], all: ['same'] },
      check: { one: ['slower', '5.66'], q: ['slower', '1.49'], tq: ['faster', '1.11'], all: ['faster', '1.12'] },
      search: { one: ['slower', '2.66', '4.80'], q: ['slower', '1.05', '1.30'], tq: ['slower', '1.08', '1.16'], all: ['slower', '1.21', '1.38'] },
    };
    const WORKERS_CPU = {
      index: { one: [5, 8], q: [20, 31], half: [23, 54], tq: [23, 77], all: [23, 100] },
      check: { one: [6, 9], q: [18, 29], half: [28, 53], tq: [42, 78], all: [49, 100] },
      search: { one: [6, 9], q: [23, 28], half: [38, 52], tq: [52, 76], all: [58, 100] },
    };
    function workersCpu([avg, peak]) {
      return t('workers_range', { a: avg, b: peak }) + '%';
    }
    function workersCounts(cpus, rec) {
      const picks = [['half', rec], ['one', 1], ['all', cpus], ['tq', Math.round(cpus * 3 / 4)], ['q', Math.max(1, Math.round(cpus / 4))]];
      const seen = new Map();
      for (const [key, n] of picks) if (!seen.has(n)) seen.set(n, key);
      return [...seen.entries()].sort((a, b) => a[0] - b[0]);
    }
    function workersSpeed(v) {
      if (!v) return t('workers_base');
      if (v[0] === 'same') return t('workers_same');
      const x = v.length > 2 ? t('workers_range', { a: v[1], b: v[2] }) : v[1];
      return t(v[0] === 'faster' ? 'workers_faster' : 'workers_slower', { x });
    }
    function renderWorkersTable(id, w, cols) {
      const table = document.getElementById(id);
      const box = document.getElementById(id + '-box');
      if (!table || !box) return;
      if (!w || w.cpus < 2) { box.hidden = true; return; }
      const head = cols.map(([label]) => `<th>${esc(t(label))}</th>`).join('');
      const body = workersCounts(w.cpus, w.recommended).map(([n, key]) => {
        const count = key === 'half' ? t('workers_rec_row', { n: fmt(n) }) : fmt(n);
        const cells = cols.map(([, pick]) => `<td>${esc(pick(key))}</td>`).join('');
        return `<tr${key === 'half' ? ' class="rec"' : ''}><td>${esc(count)}</td>${cells}</tr>`;
      }).join('');
      table.innerHTML = `<tr><th>${esc(t('workers_col_count'))}</th>${head}</tr>${body}`;
      box.hidden = false;
    }

    let searchWorkersFacts = null;
    function renderSearchWorkersCard(w) {
      if (!w) return;
      searchWorkersFacts = w;
      document.getElementById('search-workers-lead').textContent = t('search_workers_lead', { cpus: fmt(w.cpus), rec: fmt(w.recommended) });
      renderWorkersTable('search-workers-table', w, [
        ['search_workers_col', key => workersSpeed(WORKERS_SPEED.search[key])],
        ['workers_col_cpu', key => workersCpu(WORKERS_CPU.search[key])],
      ]);
      const count = document.getElementById('search-workers-input');
      count.max = w.cpus;
      count.value = w.workers;
      searchWorkersHint();
    }
    function clampSearchWorkersInputs(final = false) {
      const w = searchWorkersFacts;
      clampWorkersInput(document.getElementById('search-workers-input'), w ? w.cpus : 1, w ? w.workers : 1, final);
    }
    function searchWorkersHint(final = false) {
      clampSearchWorkersInputs(final);
      const countEl = document.getElementById('search-workers-input');
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
      const res = await apiPost('/api/library', { search_workers: auto ? 'auto' : count })
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

    async function openFolder(which, button, index = 0) {
      const card = button.closest('.set-media-row, .lib-card');
      const msg = card.querySelector('.lib-open-msg');
      msg.textContent = '';
      const res = await apiPost('/api/library/open', { which, index }).catch(() => ({ error: 'network' }));
      if (res.error) {
        msg.classList.add('warn');
        msg.textContent = res.error === 'not_found' ? t('lib_err_notfound') : t('lib_error', { e: res.error });
      }
    }

    // Subtitles, books and manga each have their own section and settings, shared in no way.
    const READER_SETTINGS_MEDIA = [['subs', 'media_subs'], ['epub', 'media_epub'], ['manga', 'media_manga'], ['custom', 'media_custom']];
    function readerSettingsSection(media) {
      const p = rmGetPrefs(media);
      const seg = (key, opts) => `<div class="seg seg-fit">${opts.map(([val, lbl]) => {
        const arg = typeof val === 'string' ? `'${val}'` : String(val);
        return `<button type="button" class="seg-btn ${p[key] === val ? 'active' : ''}" onclick="setReaderPref('${media}', '${key}', ${arg})">${esc(lbl)}</button>`;
      }).join('')}</div>`;
      const row = (label, body) => `<div class="rm-set-row"><span class="rm-set-label">${esc(label)}</span>${body}</div>`;
      const range = (key, min, max, step, val, fmtJs, shown) => `<div class="rm-range-row">
              <input type="range" min="${min}" max="${max}" step="${step}" value="${val}" oninput="this.nextElementSibling.textContent=${fmtJs}" onchange="setReaderPref('${media}', '${key}', Number(this.value))">
              <span class="rm-range-val">${shown}</span>
            </div>`;
      const themes = [
        ['app', t('rm_theme_app')], ['haze', t('theme_haze')], ['paper', t('theme_paper')],
        ['sepia', t('rm_theme_sepia')], ['night', t('theme_night')], ['midnight', t('theme_midnight')],
      ];
      const textRows = [
        row(t('rm_furi'), seg('furigana', [['on', t('rm_furi_on')], ['hover', t('rm_furi_hover')], ['off', t('rm_furi_off')]])),
        row(t('rm_font'), rmFontSelectHtml(p.font_family, `set-${media}`, media)),
        row(t('rm_font_weight'), range('font_weight', 200, 900, 100, p.font_weight || 400, 'this.value', p.font_weight || 400)),
        row(t('rm_font_size'), range('font_size', 12, 36, 1, p.font_size, "this.value+'px'", `${p.font_size}px`)),
        row(t('rm_line_height'), range('line_height', 1, 2.6, 0.05, p.line_height, 'Number(this.value).toFixed(2)', Number(p.line_height).toFixed(2))),
        row(t('rm_max_width'), range('max_width', 10, 72, 2, p.max_width, "this.value+'em'", `${p.max_width}em`)),
        row(t('rm_max_height'), range('max_height', 10, 72, 2, p.max_height || 36, "this.value+'em'", `${p.max_height || 36}em`)),
      ].join('');
      const rows = [row(t('rm_theme'), `<div class="rm-theme-grid">${themes.map(([v, lbl]) =>
        `<button type="button" class="btn rm-theme-chip ${p.theme === v ? 'active' : ''}" onclick="setReaderPref('${media}', 'theme', '${v}')">${esc(lbl)}</button>`
      ).join('')}</div>`)];
      if (media === 'manga') {
        rows.push(row(t('rm_manga_layout'), seg('manga_layout', [['single', t('rm_manga_single')], ['strip', t('rm_manga_strip')]])));
        rows.push(row(t('rm_manga_boxes'), seg('manga_boxes', [['hover', t('rm_manga_boxes_hover')], ['always', t('rm_manga_boxes_always')], ['off', t('rm_manga_boxes_off')]])));
        rows.push(row(t('rm_image_scale'), range('image_scale', 25, 100, 5, p.image_scale || 80, "this.value+'%'", `${p.image_scale || 80}%`)));
      } else {
        rows.push(row(t('rm_dir'), seg('writing_mode', [['auto', t('rm_dir_auto')], ['vertical', t('rm_dir_vertical')], ['horizontal', t('rm_dir_horizontal')]])));
        rows.push(row(t('rm_layout'), seg('layout', [['paginated', t('rm_layout_paginated')], ['continuous', t('rm_layout_continuous')]])));
        rows.push(textRows);
        if (media === 'epub') rows.push(row(t('rm_image_scale'), range('image_scale', 25, 100, 5, p.image_scale || 80, "this.value+'%'", `${p.image_scale || 80}%`)));
      }
      if (media === 'subs') rows.push(row(t('rm_sub_timestamps'), seg('sub_timestamps', [[true, t('lib_cache_on')], [false, t('lib_cache_off')]])));
      rows.push(row(t('rm_progress_show'), seg('show_progress', [[true, t('lib_cache_on')], [false, t('lib_cache_off')]])));
      rows.push(row(t('rm_auto_hide_bar'), seg('auto_hide_bar', [[true, t('lib_cache_on')], [false, t('lib_cache_off')]])));
      rows.push(row(t('rm_hide_bar_scroll'), seg('hide_bar_scroll', [[true, t('lib_cache_on')], [false, t('lib_cache_off')]])));
      rows.push(row(t('rm_edge_click'), seg('edge_click_nav', [[true, t('lib_cache_on')], [false, t('lib_cache_off')]])));
      rows.push(row(t('rm_edge_click_width'), range('edge_click_width', 5, 35, 1, p.edge_click_width || 12, "this.value+'%'", `${p.edge_click_width || 12}%`)));
      let html = `<div class="rm-set-grid">${rows.join('')}</div>`;
      if (media === 'manga') {
        html += `<div class="set-reader-sub" id="set-reader-manga-text">
          <div class="set-reader-sub-title">${esc(t('set_reader_manga_text'))}</div>
          <p class="muted">${esc(t('set_reader_manga_text_lead'))}</p>
          <div class="rm-set-grid">${textRows}</div>
        </div>`;
      }
      return `<section class="set-reader-media" id="set-reader-${media}">${html}</section>`;
    }
    // One media's settings at a time, picked in a row of buttons; the last pick is kept.
    function readerSettingsMedia(shown) {
      const kept = store.get('set_reader_media');
      return shown.some(([m]) => m === kept) ? kept : shown[0][0];
    }
    function pickReaderSettingsMedia(media) {
      store.set('set_reader_media', media);
      renderReaderSettings();
    }
    function renderReaderSettings(msg = '', media = '') {
      const card = document.getElementById('set-reader');
      if (!card || typeof rmGetPrefs !== 'function') return;
      // Only the media that are on in Settings, in the app's order: subtitles, books, manga.
      const shown = READER_SETTINGS_MEDIA.filter(([m]) => MEDIA_ON[m]);
      card.hidden = !shown.length;
      if (!shown.length) { card.innerHTML = ''; return; }
      const open = readerSettingsMedia(shown);
      const picker = shown.length > 1 ? `<div class="seg seg-fit set-reader-pick">${shown.map(([m, label]) =>
        `<button type="button" class="seg-btn ${m === open ? 'active' : ''}" onclick="pickReaderSettingsMedia('${m}')">${esc(t(label))}</button>`).join('')}</div>` : '';
      card.innerHTML = `
        <h3>${esc(t('set_reader_title'))}</h3>
        <p class="muted" style="margin:0 0 0.7em; font-size:0.9em;">${esc(t('set_reader_lead'))}</p>
        ${picker}${readerSettingsSection(open)}`;
      if (msg && media) {
        const sec = document.getElementById(`set-reader-${media}`);
        if (sec) sec.insertAdjacentHTML('beforeend', `<div class="notice ok" style="margin:0.8em 0 0;">${esc(msg)}</div>`);
      }
      if (typeof rmFontSyncOpenPopup === 'function') rmFontSyncOpenPopup();
    }

    async function setReaderPref(media, key, val) {
      if (typeof rmUpdatePrefs !== 'function') return;
      await rmUpdatePrefs({ [key]: val }, { media });
      renderReaderSettings(t('set_reader_saved'), media);
    }

