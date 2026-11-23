    // The 保存 tab: お気に入り (the starred sentences), 続きから読む (where each work in Reading mode
    // was left, and its bookmark) and 読書メモ (every work's notes). The pane last open opens again.
    const SAVED_PANES = [['favorites', 'saved_tab_favorites'], ['reading', 'saved_tab_reading'], ['notes', 'saved_tab_notes']];
    let savedPaneOpen = '';
    let savedFavoritesReady = false;
    let savedWorks = null;
    let savedNotes = null;
    let savedNoteEditing = null;
    let savedNoteAsking = null;
    let savedReadingMedia = store.get('aobana_saved_reading_media') || 'all';

    const savedPaneKnown = key => SAVED_PANES.some(([k]) => k === key);

    function initSavedTab() {
      setTitle(t('tab_saved'));
      // The cards reuse the search tab's containers (expandContext, the keyboard navigation), moved here
      document.querySelector('[data-saved-pane="favorites"]').append(document.getElementById('empty-state'), document.getElementById('results'));
      const hash = decodeURIComponent(location.hash.slice(1)).replace(/^saved-/, '');
      const kept = store.get('aobana_saved_tab');
      openSavedPane(savedPaneKnown(hash) ? hash : savedPaneKnown(kept) ? kept : 'favorites', false);
    }

    window.addEventListener('hashchange', () => {
      if (TAB !== 'saved') return;
      const hash = decodeURIComponent(location.hash.slice(1)).replace(/^saved-/, '');
      if (savedPaneKnown(hash) && hash !== savedPaneOpen) openSavedPane(hash, false);
    });

    function openSavedPane(pane, setHash = true) {
      if (!savedPaneKnown(pane)) pane = 'favorites';
      // Undo lives only while 続きから読む stays open
      if (pane !== 'reading') savedUndoDrop();
      savedPaneOpen = pane;
      store.set('aobana_saved_tab', pane);
      document.getElementById('saved-tabs').innerHTML = SAVED_PANES.map(([key, label]) =>
        `<button type="button" role="tab" class="nav-tab set-tab ${key === pane ? 'active' : ''}" aria-selected="${key === pane}" onclick="openSavedPane('${key}')">${esc(t(label))}</button>`).join('');
      document.querySelectorAll('[data-saved-pane]').forEach(p => { p.hidden = p.dataset.savedPane !== pane; });
      if (setHash) history.replaceState(history.state, '', location.pathname + location.search + '#saved-' + pane);
      updateSavedMeta();
      if (pane === 'favorites') {
        showSavedSentences();
        if (!savedFavoritesReady) {
          savedFavoritesReady = true;
          // After the relocation, which draws the list again
          relocateSaved().catch(() => {}).finally(() => { if (savedPaneOpen === 'favorites') restoreSearchReturn(); });
        }
      } else if (pane === 'reading') renderSavedReading();
      else renderSavedNotes();
    }

    function updateSavedMeta() {
      const meta = document.getElementById('saved-meta');
      if (!meta) return;
      if (savedPaneOpen === 'reading') meta.textContent = savedWorks ? t('saved_reading_count', { n: fmt(savedReadingShown().length) }) : '';
      else if (savedPaneOpen === 'notes') meta.textContent = savedNotes ? t('saved_notes_count', { n: fmt(Object.values(savedNotes).reduce((a, l) => a + l.length, 0)) }) : '';
      else meta.textContent = t('saved_count', { n: fmt(savedSentences.length) });
    }

    function savedSplitKey(wkey) {
      const cut = wkey.indexOf(':');
      return { media: wkey.slice(0, cut), folder: wkey.slice(cut + 1) };
    }

    // A part's name without the author and work before it, as Reading mode's contents show it
    function savedShortPart(title, folder) {
      const s = String(title || '');
      const cut = folder ? s.indexOf(folder + '｜') : -1;
      return cut >= 0 && cut + folder.length + 1 < s.length ? s.slice(cut + folder.length + 1) : s;
    }

    function savedPlace(media, part, ratio, page) {
      const out = [];
      if (part) out.push(part);
      if (media === 'manga' && page) out.push(t('page_n', { n: fmt(page) }));
      else if (typeof ratio === 'number') out.push(`${Math.round(ratio * 100)}%`);
      return out.join(' · ');
    }

    const savedOffTag = () => `<span class="muted">${esc(LANG === 'ja' ? `（${t('saved_media_off')}）` : `(${t('saved_media_off')})`)}</span>`;

    function savedReadingRows() {
      return Object.entries(savedWorks || {})
        .map(([wkey, w]) => ({ wkey, ...savedSplitKey(wkey), ...w }))
        .filter(w => w.file || w.bookmark)
        .sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
    }

    // The works the media bar shows: all, or one media's
    function savedReadingShown() {
      const all = savedReadingRows();
      return savedReadingMedia === 'all' ? all : all.filter(w => w.media === savedReadingMedia);
    }

    async function renderSavedReading() {
      const pane = document.querySelector('[data-saved-pane="reading"]');
      if (!savedWorks) {
        pane.innerHTML = `<div class="status-line" style="padding:2em;">${esc(t('loading'))}</div>`;
        try {
          const data = await fetch('/api/reading/state?titles=1').then(r => r.json());
          savedWorks = (data && data.works) || {};
        } catch (e) {
          pane.innerHTML = `<div class="error-text" style="padding:2em;">${esc(t('load_failed'))}</div>`;
          return;
        }
      }
      const all = savedReadingRows();
      // By media, as the Media tab's own bar: 全て, then each media that is on
      const kinds = MEDIAS.length > 1 ? MEDIAS : [];
      if (!kinds.includes(savedReadingMedia)) savedReadingMedia = 'all';
      const rows = savedReadingShown();
      pane._rows = rows;
      updateSavedMeta();
      const seg = kinds.length && all.length
        ? `<div class="seg saved-media-seg">${kinds.map(m => `<button type="button" class="seg-btn ${m === savedReadingMedia ? 'active' : ''}" onclick="savedSetReadingMedia('${m}')">${esc(mediaLabel(m))}</button>`).join('')}</div>`
        : '';
      if (!rows.length) {
        const none = all.length ? t('saved_no_reading_kind', { media: mediaLabel(savedReadingMedia) }) : t('saved_no_reading');
        pane.innerHTML = seg + `<div class="saved-empty">${esc(none)}</div>`;
        return;
      }
      pane.innerHTML = seg + `<div class="media-list">${rows.map((w, i) => {
        const on = !!MEDIA_ON[w.media];
        const where = w.file ? savedPlace(w.media, savedShortPart(w.part_title || w.file, w.folder), w.scroll_ratio, w.page) : '';
        const bm = w.bookmark;
        const bmWhere = bm ? savedPlace(w.media, savedShortPart(bm.part_title || bm.label || bm.file, w.folder), bm.scroll_ratio, bm.page) : '';
        return `<div class="media-row saved-work-row">
          <span class="media-kind ${esc(w.media)}">${esc(t('kind_' + w.media))}</span>
          <span class="media-names">
            <div class="media-name">${esc(w.folder)}${on ? '' : ' ' + savedOffTag()}</div>
            ${where ? `<div class="media-author">${esc(where)}</div>` : ''}
            ${bmWhere ? `<div class="media-author saved-bm-line">${esc(t('saved_bookmark_at', { where: bmWhere }))}</div>` : ''}
          </span>
          <span class="saved-row-actions">
            ${bm ? `<button type="button" class="btn" ${on ? '' : 'disabled'} onclick="savedOpenWork(${i}, true)">${esc(t('rm_bookmark_go'))}</button>` : ''}
            ${w.file ? `<button type="button" class="btn primary" ${on ? '' : 'disabled'} onclick="savedOpenWork(${i}, false)">${esc(t('rm_continue'))}</button>` : ''}
            <button type="button" class="icon-btn saved-remove" title="${esc(t('saved_reading_remove', { name: w.folder }))}" aria-label="${esc(t('saved_reading_remove', { name: w.folder }))}" onclick="savedRemoveRow(${i})"><span>×</span></button>
          </span>
        </div>`;
      }).join('')}</div>`;
    }

    function savedSetReadingMedia(m) {
      savedReadingMedia = m;
      store.set('aobana_saved_reading_media', m);
      renderSavedReading();
    }

    // Removed works wait here while the Undo popup shows; each removal adds to the same Undo
    let savedUndoBatch = {};

    function savedRemoveRow(i) {
      const w = (document.querySelector('[data-saved-pane="reading"]')._rows || [])[i];
      if (w) savedRemoveWorks([w.wkey]);
    }

    async function savedRemoveWorks(keys) {
      const res = await apiPost('/api/reading/state', { remove: keys }).catch(() => null);
      if (!res || !res.removed) return;
      keys.forEach(k => { if (savedWorks) delete savedWorks[k]; });
      // Left 続きから読む while it was on its way: no Undo there, as leaving ends it
      if (savedPaneOpen !== 'reading') return;
      for (const [wkey, entry] of Object.entries(res.removed)) {
        if (!(wkey in savedUndoBatch)) savedUndoBatch[wkey] = entry;
      }
      renderSavedReading();
      savedUndoShow();
    }

    function savedUndoShow() {
      const n = Object.keys(savedUndoBatch).length;
      if (!n) return savedUndoDrop();
      let box = document.getElementById('saved-undo');
      if (!box) {
        box = document.createElement('div');
        box.id = 'saved-undo';
        box.className = 'saved-undo';
        box.setAttribute('role', 'status');
        box.innerHTML = `<span class="saved-undo-text"></span><button type="button" class="btn primary" onclick="savedUndo()">${esc(t('saved_undo'))}</button>`;
        document.body.append(box);
      }
      box.querySelector('.saved-undo-text').textContent = t('saved_reading_removed', { n: fmt(n) });
    }

    function savedUndoDrop() {
      savedUndoBatch = {};
      document.getElementById('saved-undo')?.remove();
    }

    // Puts back every work removed since the popup appeared, each at its own place in the list
    async function savedUndo() {
      const batch = savedUndoBatch;
      savedUndoDrop();
      if (!Object.keys(batch).length) return;
      await apiPost('/api/reading/state', { restore: batch }).catch(() => null);
      savedWorks = null;
      if (savedPaneOpen === 'reading') renderSavedReading();
    }

    function savedOpenWork(i, toBookmark) {
      const w = (document.querySelector('[data-saved-pane="reading"]')._rows || [])[i];
      if (!w) return;
      if (toBookmark && w.bookmark) {
        jumpToReadingMode({ media: w.media, folder: w.folder, file: w.bookmark.file, target: w.bookmark, explicitStart: true, toast: t('rm_bookmark_jumped') });
      } else {
        // Where it was left: Reading mode's own place for the work
        jumpToReadingMode({ media: w.media, folder: w.folder });
      }
    }

    function savedNoteGroups() {
      return Object.entries(savedNotes || {})
        .filter(([, list]) => Array.isArray(list) && list.length)
        .map(([wkey, notes]) => ({ wkey, ...savedSplitKey(wkey), notes, newest: Math.max(...notes.map(n => n.updated_at || n.created_at || 0)) }))
        .sort((a, b) => b.newest - a.newest);
    }

    const savedNotePlace = (n, g) => savedPlace(g.media, savedShortPart(n.part_title || n.file, g.folder), n.scroll_ratio, n.page);

    async function renderSavedNotes() {
      const pane = document.querySelector('[data-saved-pane="notes"]');
      if (!savedNotes) {
        pane.innerHTML = `<div class="status-line" style="padding:2em;">${esc(t('loading'))}</div>`;
        try {
          const data = await fetch('/api/reading/notes').then(r => r.json());
          savedNotes = (data && data.works) || {};
        } catch (e) {
          pane.innerHTML = `<div class="error-text" style="padding:2em;">${esc(t('load_failed'))}</div>`;
          return;
        }
      }
      const groups = savedNoteGroups();
      pane._groups = groups;
      updateSavedMeta();
      if (!groups.length) {
        pane.innerHTML = `<div class="saved-empty">${esc(t('saved_no_notes'))}</div>`;
        return;
      }
      const furi = !!rmNotesState.copyFuri;
      const bar = `<div class="saved-notes-toolbar">
        <span class="rm-set-label">${esc(t('rm_notes_copy_furi'))}</span>
        <div class="seg seg-fit">
          <button type="button" class="seg-btn ${furi ? 'active' : ''}" onclick="savedSetCopyFuri(true)">${esc(t('lib_cache_on'))}</button>
          <button type="button" class="seg-btn ${furi ? '' : 'active'}" onclick="savedSetCopyFuri(false)">${esc(t('lib_cache_off'))}</button>
        </div>
      </div>`;
      pane.innerHTML = bar + groups.map((g, gi) => {
        const on = !!MEDIA_ON[g.media];
        const quotes = g.notes.some(n => rmNoteShownQuote(n, furi));
        const items = g.notes.map((n, ni) => {
          const q = rmNoteShownQuote(n, furi);
          const editing = savedNoteEditing && savedNoteEditing.wkey === g.wkey && savedNoteEditing.id === n.id;
          const asking = savedNoteAsking && savedNoteAsking.wkey === g.wkey && savedNoteAsking.id === n.id;
          return `<div class="rm-note-item">
            <div class="rm-note-item-head">
              <button type="button" class="rm-note-place" ${on ? '' : 'disabled'} onclick="savedJumpNote(${gi}, ${ni})">${esc(savedNotePlace(n, g))}</button>
              <div class="rm-note-item-actions">
                <button type="button" class="btn" ${on ? '' : 'disabled'} onclick="savedJumpNote(${gi}, ${ni})">${esc(t('rm_notes_jump'))}</button>
                <button type="button" class="btn" onclick="savedCopyNotes(${gi}, ${ni}, true, this)">${esc(t('rm_notes_copy'))}</button>
                <button type="button" class="btn" onclick="savedEditNote(${gi}, ${ni})">${esc(t('rm_notes_edit'))}</button>
                ${asking
                  ? `<button type="button" class="btn primary" onclick="savedDeleteNote(${gi}, ${ni})">${esc(t('rm_notes_delete'))}</button><button type="button" class="btn" onclick="savedAskDelete(null)">${esc(t('rm_notes_cancel'))}</button>`
                  : `<button type="button" class="btn" onclick="savedAskDelete(${gi}, ${ni})">${esc(t('rm_notes_delete'))}</button>`}
              </div>
            </div>
            ${q ? `<div class="rm-note-item-quote">${esc(q)}</div>` : ''}
            ${editing
              ? `<textarea class="rm-notes-textarea" id="saved-note-edit" oninput="rmAutoGrowTextarea(this)" onkeydown="if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();savedSaveNote(${gi}, ${ni});}">${esc(n.text || '')}</textarea>
                <div class="rm-notes-comp-actions">
                  <button type="button" class="btn" onclick="savedEditNote(null)">${esc(t('rm_notes_cancel'))}</button>
                  <button type="button" class="btn primary" onclick="savedSaveNote(${gi}, ${ni})">${esc(t('rm_notes_update'))}</button>
                </div>`
              : `<div class="rm-note-item-body">${esc(n.text || '')}</div>`}
          </div>`;
        }).join('');
        return `<div class="panel saved-notes-group">
          <div class="saved-notes-group-head">
            <span class="media-kind ${esc(g.media)}">${esc(t('kind_' + g.media))}</span>
            <strong class="saved-notes-work">${esc(g.folder)}</strong>
            ${on ? '' : savedOffTag()}
            <span class="muted">${esc(t('saved_notes_count', { n: fmt(g.notes.length) }))}</span>
            <div class="saved-notes-group-actions">
              <button type="button" class="btn" onclick="savedCopyNotes(${gi}, -1, false, this)">${esc(t('rm_notes_copy_notes'))}</button>
              ${quotes ? `<button type="button" class="btn" onclick="savedCopyNotes(${gi}, -1, true, this)">${esc(t('rm_notes_copy_notes_quotes'))}</button>` : ''}
            </div>
          </div>
          <div class="saved-notes-items">${items}</div>
        </div>`;
      }).join('');
      const ta = document.getElementById('saved-note-edit');
      if (ta) { rmAutoGrowTextarea(ta, false); try { ta.focus({ preventScroll: true }); } catch (e) {} }
    }

    function savedNoteAt(gi, ni) {
      const g = (document.querySelector('[data-saved-pane="notes"]')._groups || [])[gi];
      return { g, n: g && ni != null && ni >= 0 ? g.notes[ni] : null };
    }

    // A save answers with the work's notes as stored; the part names the 保存 tab was given stay
    function savedKeepPartTitles(notes, before) {
      const byFile = new Map(before.filter(n => n.part_title).map(n => [n.file, n.part_title]));
      return notes.map(n => n.part_title || !byFile.has(n.file) ? n : { ...n, part_title: byFile.get(n.file) });
    }

    function savedSetCopyFuri(on) {
      rmNotesState.copyFuri = !!on;
      try { localStorage.setItem(RM_NOTES_COPY_FURI_KEY, on ? '1' : '0'); } catch (e) {}
      renderSavedNotes();
    }

    function savedJumpNote(gi, ni) {
      const { g, n } = savedNoteAt(gi, ni);
      if (!n) return;
      jumpToReadingMode({ media: g.media, folder: g.folder, file: n.file, target: n, explicitStart: true, toast: t('rm_notes_jumped') });
    }

    // One note (ni ≥ 0, with its quote) or the work's notes, as Markdown, as the Notes drawer copies them
    async function savedCopyNotes(gi, ni, withQuotes, btn) {
      const { g, n } = savedNoteAt(gi, ni);
      if (!g) return;
      const md = rmFormatNotesMarkdown(n ? [n] : g.notes, !!rmNotesState.copyFuri, true, withQuotes, { work: g.folder, place: x => savedNotePlace(x, g) });
      if (!(await copyToClipboard(md))) return;
      // A control's words are its .lbl's data-label, not DOM text (core.js); read once, so a second press keeps them
      if (btn._label == null) btn._label = labelText(btn);
      clearTimeout(btn._copied);
      btn.textContent = t('copied');
      btn._copied = setTimeout(() => { btn.textContent = btn._label; }, 1500);
    }

    function savedEditNote(gi, ni) {
      const { g, n } = gi == null ? {} : savedNoteAt(gi, ni);
      savedNoteAsking = null;
      savedNoteEditing = n ? { wkey: g.wkey, id: n.id } : null;
      renderSavedNotes();
    }

    async function savedSaveNote(gi, ni) {
      const { g, n } = savedNoteAt(gi, ni);
      const ta = document.getElementById('saved-note-edit');
      const text = ta ? ta.value.trim() : '';
      if (!n || !text) return;
      const res = await apiPost('/api/reading/notes', { media: g.media, folder: g.folder, note: { id: n.id, file: n.file, text } }).catch(() => null);
      if (!res || !Array.isArray(res.notes)) return;
      savedNotes[g.wkey] = savedKeepPartTitles(res.notes, g.notes);
      savedNoteEditing = null;
      renderSavedNotes();
    }

    // Delete asks once, on the note itself (Delete, then Delete or Cancel), as Settings does
    function savedAskDelete(gi, ni) {
      const { g, n } = gi == null ? {} : savedNoteAt(gi, ni);
      savedNoteEditing = null;
      savedNoteAsking = n ? { wkey: g.wkey, id: n.id } : null;
      renderSavedNotes();
    }

    async function savedDeleteNote(gi, ni) {
      const { g, n } = savedNoteAt(gi, ni);
      if (!n) return;
      const r = await fetch('/api/reading/notes', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', ...API_HEADERS },
        body: JSON.stringify({ media: g.media, folder: g.folder, id: n.id }),
      }).catch(() => null);
      if (!r || !r.ok) return;
      const data = await r.json();
      savedNoteAsking = null;
      if (Array.isArray(data.notes) && data.notes.length) savedNotes[g.wkey] = savedKeepPartTitles(data.notes, g.notes);
      else delete savedNotes[g.wkey];
      renderSavedNotes();
    }
