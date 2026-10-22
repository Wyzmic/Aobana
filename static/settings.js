    let settingsShown = false;
    function renderSettings(lib) {
      folderPicker = !!lib.folder_picker;
      renderMediaCard(lib);
      if (!document.querySelector('#set-known-words .known-preview:not([hidden])')) renderKnownWords();
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

    const MEDIA_DB = { subs: 'subs.db', books: 'epub.db', manga: 'manga.db', custom: 'custom.db' };
    const MEDIA_KINDS = ['subs', 'books', 'manga', 'custom'];
    function renderMediaCard(lib, msg) {
      const on = lib.media || { subs: true, books: true, manga: false, custom: false };
      if (typeof lib.subtitle_tags === 'boolean') syncSubTags(lib.subtitle_tags);
      syncMediaOn(lib.media);
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
            ${lib.custom_trim_pending ? `<div class="notice" style="margin-top:0.6em;">${t('set_custom_trim_pending', { n: lib.custom_trim_pending.toLocaleString() })}</div>` : ''}
          </div>
          <div class="set-sub-tags">
            <div class="facts">${esc(t('set_custom_ruby'))}</div>
            <div class="seg seg-fit" style="margin-top:0.4em;">
              <button type="button" class="seg-btn ${lib.custom_ruby === false ? 'active' : ''}" onclick="setCustomRuby(false)">${esc(t('lib_cache_off'))}</button>
              <button type="button" class="seg-btn ${lib.custom_ruby === false ? '' : 'active'}" onclick="setCustomRuby(true)">${esc(t('lib_cache_on'))}</button>
            </div>
            ${lib.custom_ruby_pending ? `<div class="notice" style="margin-top:0.6em;">${t('set_custom_trim_pending', { n: lib.custom_ruby_pending.toLocaleString() })}</div>` : ''}
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
      // Custom's files the index left unread, read from custom.db, so the line stays after a restart (audit 10, F43)
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
      renderCacheCard(lib.search_cache);
    }

    function renderCacheCard(c, msg) {
      c = c || { entries: 0, bytes: 0, on: false };
      document.getElementById('lib-cache').innerHTML = `
        <h3>${esc(t('lib_cache_title'))}</h3>
        <div class="facts"><div>${esc(t('lib_cache_lead'))}</div>
          <div>${esc(t('lib_cache', { n: fmt(c.entries), size: fmtBytes(c.bytes) }))}</div></div>
        <div class="btns" style="align-items:center;">
          <div class="seg seg-fit">
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

