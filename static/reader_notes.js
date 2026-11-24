// In-reader Notes (メモ) and AI-friendly copy helpers for Reading mode.

const RM_NOTES_COPY_FURI_KEY = 'aobana_rm_copy_furi';
const RM_NOTES_BLOCK_TAGS = new Set([
  'P', 'DIV', 'LI', 'BLOCKQUOTE', 'PRE', 'TR', 'DT', 'DD',
  'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'SECTION', 'ARTICLE', 'HR',
]);

const rmNotesState = {
  workKey: '',
  notes: [],
  scope: 'part',
  editingId: '',
  draftAnchor: null,
  draftQuote: '',
  draftQuoteFuri: '',
  draftSelected: false,
  selectedPlain: '',
  selectedFuri: '',
  copyFuri: (() => {
    try { return localStorage.getItem(RM_NOTES_COPY_FURI_KEY) === '1'; } catch (e) { return false; }
  })(),
  vpBound: false,
  saving: false,
};

function rmNotesWorkKey() {
  if (!rmState.media || !rmState.folder) return '';
  return `${rmState.media}:${rmState.folder}`;
}

function rmNotesShortTitle(fileKey, fallbackTitle) {
  const item = (rmState.files || []).find(f => f.file === fileKey);
  const full = (item && item.title) || fallbackTitle || fileKey || '';
  const head = rmTocCommonHead((rmState.files || []).map(it => it.title || it.file));
  return (head && full.startsWith(head) && full.length > head.length) ? full.slice(head.length) : full;
}

function rmExtractNodeText(node, includeFurigana) {
  if (!node) return '';
  const out = [];
  const emitBreak = () => {
    if (out.length && !out[out.length - 1].endsWith('\n')) out.push('\n');
  };
  const walk = (n) => {
    if (!n) return;
    if (n.nodeType === 3) {
      out.push(n.nodeValue || '');
      return;
    }
    if (n.nodeType !== 1) return;
    const tag = n.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'SVG') return;
    if (n.classList && (n.classList.contains('rm-sent-break') || n.classList.contains('rm-part-nav-end'))) return;
    if (n.classList && n.classList.contains('rm-sub-ts')) {
      const p = rmGetPrefs();
      if (!p.sub_timestamps) return;
      const ts = labelText(n).trim();
      if (ts) out.push(`[${ts}] `);
      return;
    }
    if (tag === 'BR') {
      out.push('\n');
      return;
    }
    if (tag === 'RT' || tag === 'RP') return;
    if (tag === 'RUBY') {
      let base = '';
      let rt = '';
      for (let c = n.firstChild; c; c = c.nextSibling) {
        if (c.nodeType === 3) {
          base += c.nodeValue || '';
        } else if (c.nodeType === 1) {
          if (c.tagName === 'RT') rt += c.textContent || '';
          else if (c.tagName === 'RP') continue;
          else base += rmExtractNodeText(c, false);
        }
      }
      out.push(includeFurigana && rt.trim() ? `${base}(${rt.trim()})` : base);
      return;
    }
    const isBlock = RM_NOTES_BLOCK_TAGS.has(tag) || (n.classList && (n.classList.contains('rm-db-line') || n.classList.contains('rm-sub-line')));
    if (isBlock) emitBreak();
    for (let c = n.firstChild; c; c = c.nextSibling) walk(c);
    if (isBlock) emitBreak();
  };
  walk(node);
  return out.join('')
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function rmExtractRangeText(range, includeFurigana) {
  if (!range || range.collapsed) return '';
  try {
    const frag = range.cloneContents();
    const wrap = document.createElement('div');
    wrap.appendChild(frag);
    return rmExtractNodeText(wrap, includeFurigana);
  } catch (e) {
    return String(range).trim();
  }
}

function rmMangaPageOcrText(pageNo) {
  const pages = (rmState.part && rmState.part.pages) || [];
  const pg = pages.find(p => p.page === pageNo) || pages[(pageNo || 1) - 1];
  if (!pg) return '';
  const lines = [];
  for (const blk of (pg.blocks || [])) {
    if (Array.isArray(blk.lines) && blk.lines.length) {
      lines.push(blk.lines.join(''));
    } else if (blk.text) {
      lines.push(blk.text);
    }
  }
  return lines.join('\n').trim();
}

// Capture any active selection inside #rm-stage on pointerdown before clicking the Notes button clears it.
function rmCaptureNotesSelection() {
  rmNotesState.selectedPlain = '';
  rmNotesState.selectedFuri = '';
  rmNotesState.draftSelected = false;
  const stage = document.getElementById('rm-stage');
  if (!stage || !window.getSelection) return;
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;
  const rg = sel.getRangeAt(0);
  if (!stage.contains(rg.commonAncestorContainer)) return;
  const plain = rmExtractRangeText(rg, false);
  if (!plain) return;
  const furi = rmExtractRangeText(rg, true);
  rmNotesState.selectedPlain = plain;
  rmNotesState.selectedFuri = furi !== plain ? furi : '';
  rmNotesState.draftSelected = true;

  const anchor = rmReadAnchor();
  if (!anchor) return;
  if (rmState.media !== 'manga') {
    const root = document.getElementById('rm-epub-root');
    if (root && root.contains(rg.startContainer)) {
      const { nodes } = rmCollectAnchorNodes(root);
      const baseOff = (rmState.layout === 'paginated' && rmState.secCharStarts[rmState.secIndex]) || 0;
      let selOff = -1;
      for (const entry of nodes) {
        if (entry.node === rg.startContainer) {
          selOff = baseOff + entry.cumStart + rmCountNonWs(entry.text, rg.startOffset);
          break;
        }
        try {
          if (rg.comparePoint(entry.node, 0) >= 0) {
            selOff = baseOff + entry.cumStart;
            break;
          }
        } catch (e) {}
      }
      if (selOff >= 0) {
        anchor.char_offset = selOff;
        delete anchor.edge;
        const sc = rmScrollerEl();
        const sr = rg.getClientRects()[0];
        if (rmState.layout !== 'paginated' && sc && sr) {
          const vr = sc.getBoundingClientRect();
          anchor.edge = Number((rmState.dir === 'vertical' ? vr.right - sr.right : sr.top - vr.top).toFixed(1));
        }
        const total = rmState.totalPlainChars || (rmState.part && rmState.part.char_count) || 0;
        if (total > 0) anchor.scroll_ratio = Number(Math.max(0, Math.min(1, selOff / total)).toFixed(5));
      }
    }
  }
  anchor.quote = plain.replace(/\s+/g, ' ').slice(0, 400);
  rmNotesState.draftAnchor = anchor;
  rmNotesState.draftQuote = anchor.quote;
  rmNotesState.draftQuoteFuri = rmNotesState.selectedFuri.replace(/\s+/g, ' ').slice(0, 800);
}

function rmRefreshNotesDraftAnchor(clearSelection = false) {
  if (clearSelection) {
    rmNotesState.selectedPlain = '';
    rmNotesState.selectedFuri = '';
    rmNotesState.draftSelected = false;
  }
  if (rmNotesState.draftSelected && rmNotesState.draftAnchor) return;
  const anchor = rmReadAnchor();
  rmNotesState.draftAnchor = anchor;
  if (!anchor) {
    rmNotesState.draftQuote = '';
    rmNotesState.draftQuoteFuri = '';
    return;
  }
  if (rmState.media === 'manga') {
    const txt = rmMangaPageOcrText(anchor.page || rmState.mangaPage).replace(/\s+/g, ' ').slice(0, 120);
    rmNotesState.draftQuote = txt;
    rmNotesState.draftQuoteFuri = '';
    anchor.quote = txt;
    return;
  }
  const root = document.getElementById('rm-epub-root');
  const baseOff = (rmState.layout === 'paginated' && rmState.secCharStarts[rmState.secIndex]) || 0;
  const localOff = Math.max(0, (anchor.char_offset || 0) - baseOff);
  const { nodes } = rmCollectAnchorNodes(root);
  const loc = rmLocateAnchorOffset(root, localOff, anchor.quote);
  let quote = anchor.quote || '';
  if (loc && nodes.length) {
    const idx = nodes.findIndex(e => e.node === loc.node);
    if (idx >= 0) quote = rmExtractQuoteAt(nodes, idx, loc.rawIdx, 72);
  }
  anchor.quote = quote;
  rmNotesState.draftQuote = quote;
  rmNotesState.draftQuoteFuri = '';
}

// A note shows a quote only when the reader selected the text. Without a selection the stored
// quote is the few characters at the note's position, kept to find it again, not to read.
function rmNoteShownQuote(note, includeFurigana = rmNotesState.copyFuri) {
  if (!note || !note.selected) return '';
  return (includeFurigana && note.quote_furi) || note.quote || '';
}

function rmUpdateNotesBtn() {
  const btn = document.getElementById('rm-notes-btn');
  if (!btn) return;
  const n = rmNotesState.notes.length;
  btn.title = n > 0 ? `${t('rm_notes')} (${n})` : t('rm_notes');
}

async function rmLoadWorkNotes() {
  const wk = rmNotesWorkKey();
  rmNotesState.workKey = wk;
  rmNotesState.notes = [];
  rmNotesState.editingId = '';
  rmUpdateNotesBtn();
  if (!wk) return;
  try {
    const r = await fetch(`/api/reading/notes?media=${encodeURIComponent(rmState.media)}&folder=${encodeURIComponent(rmState.folder)}`);
    if (!r.ok) return;
    const data = await r.json();
    if (rmNotesWorkKey() !== wk) return;
    rmNotesState.notes = Array.isArray(data.notes) ? data.notes : [];
    rmUpdateNotesBtn();
    const panel = document.getElementById('rm-notes-panel');
    if (panel && !panel.hidden) rmRenderNotesPanel();
  } catch (e) {}
}

function rmOnNotesPartChange() {
  const panel = document.getElementById('rm-notes-panel');
  if (panel && !panel.hidden) {
    rmRefreshNotesDraftAnchor(true);
    rmRenderNotesPanel();
  }
}

function rmResetNotesOnClose() {
  rmNotesState.editingId = '';
  rmNotesState.draftAnchor = null;
  rmNotesState.draftSelected = false;
  rmNotesState.selectedPlain = '';
  rmNotesState.selectedFuri = '';
  rmUnbindNotesViewport();
}

function rmSyncNotesViewport() {
  const card = document.getElementById('rm-notes-card');
  if (!card) return;
  if (window.innerWidth > 720 || !window.visualViewport) {
    card.style.removeProperty('--rm-notes-max-h');
    return;
  }
  const vh = Math.floor(window.visualViewport.height);
  const avail = Math.max(200, vh - 12);
  const cap = vh < window.innerHeight * 0.8 ? avail : Math.min(avail, Math.round(vh * 0.8));
  card.style.setProperty('--rm-notes-max-h', cap + 'px');
}

function rmBindNotesViewport() {
  if (rmNotesState.vpBound || !window.visualViewport) return;
  rmNotesState.vpBound = true;
  window.visualViewport.addEventListener('resize', rmSyncNotesViewport);
  window.visualViewport.addEventListener('scroll', rmSyncNotesViewport);
}

function rmUnbindNotesViewport() {
  if (!rmNotesState.vpBound || !window.visualViewport) return;
  rmNotesState.vpBound = false;
  window.visualViewport.removeEventListener('resize', rmSyncNotesViewport);
  window.visualViewport.removeEventListener('scroll', rmSyncNotesViewport);
  const card = document.getElementById('rm-notes-card');
  if (card) card.style.removeProperty('--rm-notes-max-h');
}

function rmToggleNotes(force) {
  const el = document.getElementById('rm-notes-panel');
  if (!el) return;
  const show = force === undefined ? el.hidden : !!force;
  el.hidden = !show;
  if (show) {
    rmCloseFontPopup(false);
    const toc = document.getElementById('rm-toc-drawer');
    if (toc) toc.hidden = true;
    const setp = document.getElementById('rm-settings-panel');
    if (setp) setp.hidden = true;
    const bmMenu = document.getElementById('rm-bm-menu');
    if (bmMenu) bmMenu.hidden = true;
    rmSetTopbarHidden(false, 'overlay');
    if (rmNotesState.workKey !== rmNotesWorkKey()) rmLoadWorkNotes();
    if (!rmNotesState.editingId) rmRefreshNotesDraftAnchor(false);
    rmBindNotesViewport();
    rmSyncNotesViewport();
    rmRenderNotesPanel();
    const ta = document.getElementById('rm-notes-input');
    if (ta && window.innerWidth > 720) {
      try { ta.focus({ preventScroll: true }); } catch (e) {}
    }
  } else {
    rmNotesState.editingId = '';
    rmNotesState.draftSelected = false;
    rmNotesState.selectedPlain = '';
    rmNotesState.selectedFuri = '';
    rmUnbindNotesViewport();
    rmResetTopbarForMode();
    rmFocusStage();
  }
}

function rmFormatNoteLocation(note, includePart) {
  const parts = [];
  if (includePart) {
    const title = rmNotesShortTitle(note.file, note.part_title);
    if (title) parts.push(title);
  }
  if (rmState.media === 'manga' && note.page) {
    parts.push(t('page_n', { n: fmt(note.page) }));
  } else {
    // The page is the one the note opens on with the current settings; a note elsewhere shows its percentage.
    const root = document.getElementById('rm-epub-root');
    const pIdx = (rmState.layout === 'paginated' && rmState.part && note.file === rmState.part.file)
      ? rmAnchorPageInSection(note, root, true) : -1;
    if (pIdx >= 0) {
      const sCount = Math.max(1, rmState.sections.length);
      const pageTxt = t('rm_page_of', { a: fmt(pIdx + 1), b: fmt(rmState.pageCount) });
      parts.push(sCount > 1 ? `${fmt(rmState.secIndex + 1)}/${fmt(sCount)} · ${pageTxt}` : pageTxt);
    }
    parts.push(`${Math.round((note.scroll_ratio || 0) * 100)}%`);
  }
  return parts.join(' · ');
}

function rmNotesForScope(scope) {
  const all = rmNotesState.notes || [];
  if (scope === 'work') return all;
  const curFile = rmState.part && rmState.part.file;
  return curFile ? all.filter(n => n.file === curFile) : all;
}

function rmSetNotesScope(scope) {
  rmNotesState.scope = scope === 'work' ? 'work' : 'part';
  rmRenderNotesPanel();
}

function rmSetCopyFuri(on) {
  rmNotesState.copyFuri = !!on;
  try { localStorage.setItem(RM_NOTES_COPY_FURI_KEY, rmNotesState.copyFuri ? '1' : '0'); } catch (e) {}
  rmRenderNotesPanel();
}

function rmRenderNotesPanel() {
  const card = document.getElementById('rm-notes-card');
  if (!card) return;
  const prevTa = document.getElementById('rm-notes-input');
  const prevDraftText = prevTa ? prevTa.value : '';
  const prevBody = card.querySelector('.rm-notes-body');
  const prevScroll = prevBody ? prevBody.scrollTop : 0;

  const isManga = rmState.media === 'manga';
  const isPaginated = isManga
    ? (rmGetPrefs().manga_layout !== 'strip' && !(rmState.part && rmState.part.source === 'db'))
    : rmState.layout === 'paginated';
  const pageOrAreaLabel = isPaginated ? t('rm_notes_copy_page') : t('rm_notes_copy_area');

  const curFile = rmState.part && rmState.part.file;
  const partNotes = curFile ? rmNotesState.notes.filter(n => n.file === curFile) : [];
  const workNotes = rmNotesState.notes;
  const shown = rmNotesForScope(rmNotesState.scope);
  const editing = rmNotesState.editingId ? workNotes.find(n => n.id === rmNotesState.editingId) : null;
  const anchor = editing || rmNotesState.draftAnchor;
  const quoteDisp = editing
    ? rmNoteShownQuote(editing)
    : (rmNotesState.draftSelected ? ((rmNotesState.copyFuri && rmNotesState.draftQuoteFuri) || rmNotesState.draftQuote || '') : '');
  const anchorMeta = anchor ? rmFormatNoteLocation(anchor, false) : '';
  const taValue = editing && !prevDraftText ? (editing.text || '') : prevDraftText;

  card.innerHTML = `
    <div class="rm-drawer-head">
      <span>${esc(t('rm_notes'))}${workNotes.length ? ` (${fmt(workNotes.length)})` : ''}</span>
      <button type="button" class="sq-btn" onclick="rmToggleNotes(false)" aria-label="${esc(t('close'))}">✕</button>
    </div>
    <div class="rm-notes-body">
    <div class="rm-notes-copybar">
      <div class="rm-notes-copy-btns">
        <button type="button" class="btn" onclick="rmCopyNotes(false)">${esc(t('rm_notes_copy_notes'))}</button>
        <button type="button" class="btn" onclick="rmCopyNotes(true)" ${shown.some(n => rmNoteShownQuote(n)) ? '' : 'disabled'}>${esc(t('rm_notes_copy_notes_quotes'))}</button>
        <button type="button" class="btn" onclick="rmCopyFullChapter()">${esc(t('rm_notes_copy_chapter'))}</button>
        <button type="button" class="btn" onclick="rmCopyCurrentPageOrArea()">${esc(pageOrAreaLabel)}</button>
      </div>
      ${!isManga || rmMangaTextOnly(rmState.part) ? `
      <div class="rm-notes-furi-row">
        <span class="rm-set-label">${esc(t('rm_notes_copy_furi'))}</span>
        <div class="seg seg-fit">
          <button type="button" class="seg-btn ${rmNotesState.copyFuri ? 'active' : ''}" onclick="rmSetCopyFuri(true)">${esc(t('lib_cache_on'))}</button>
          <button type="button" class="seg-btn ${!rmNotesState.copyFuri ? 'active' : ''}" onclick="rmSetCopyFuri(false)">${esc(t('lib_cache_off'))}</button>
        </div>
      </div>` : ''}
    </div>
    <div class="rm-notes-composer">
      <div class="rm-notes-anchor-bar">
        <div class="rm-notes-anchor-meta">
          <span>${esc(anchorMeta)}</span>
          ${!editing && rmNotesState.draftSelected ? `<span class="rm-notes-tag">${esc(t('rm_notes_selected_tag'))}</span>` : ''}
        </div>
        ${!editing ? `<button type="button" class="btn" style="height:24px;padding:0 7px;font-size:0.9em;" onclick="rmRefreshNotesDraftAnchor(true); rmRenderNotesPanel()">${esc(t('rm_notes_refresh_pos'))}</button>` : ''}
      </div>
      ${quoteDisp ? `<div class="rm-notes-quote-preview">${esc(quoteDisp)}</div>` : ''}
      <textarea id="rm-notes-input" class="rm-notes-textarea" placeholder="${esc(t('rm_notes_placeholder'))}" oninput="rmAutoGrowTextarea(this)" onkeydown="if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();rmSaveNote();}">${esc(taValue)}</textarea>
      <div class="rm-notes-comp-actions">
        ${editing ? `<button type="button" class="btn" onclick="rmCancelEditNote()">${esc(t('rm_notes_cancel'))}</button>` : ''}
        <button type="button" class="btn primary" onclick="rmSaveNote()">${esc(editing ? t('rm_notes_update') : t('rm_notes_save'))}</button>
      </div>
    </div>
    <div class="rm-notes-list-head">
      <div class="seg seg-fit">
        <button type="button" class="seg-btn ${rmNotesState.scope === 'part' ? 'active' : ''}" onclick="rmSetNotesScope('part')">${esc(t('rm_notes_scope_part'))} (${fmt(partNotes.length)})</button>
        <button type="button" class="seg-btn ${rmNotesState.scope === 'work' ? 'active' : ''}" onclick="rmSetNotesScope('work')">${esc(t('rm_notes_scope_work'))} (${fmt(workNotes.length)})</button>
      </div>
    </div>
    <div class="rm-notes-list">
      ${shown.length ? shown.map(n => {
        const q = rmNoteShownQuote(n);
        const place = rmFormatNoteLocation(n, rmNotesState.scope === 'work');
        return `<div class="rm-note-item" data-note-id="${esc(n.id)}">
          <div class="rm-note-item-head">
            <button type="button" class="rm-note-place" onclick="rmJumpToNote('${esc(n.id)}')">${esc(place)}</button>
            <div class="rm-note-item-actions">
              <button type="button" class="btn" onclick="rmJumpToNote('${esc(n.id)}')">${esc(t('rm_notes_jump'))}</button>
              <button type="button" class="btn" onclick="rmCopySingleNote('${esc(n.id)}')">${esc(t('rm_notes_copy'))}</button>
              <button type="button" class="btn" onclick="rmStartEditNote('${esc(n.id)}')">${esc(t('rm_notes_edit'))}</button>
              <button type="button" class="btn" onclick="rmDeleteNote('${esc(n.id)}')">${esc(t('rm_notes_delete'))}</button>
            </div>
          </div>
          ${q ? `<div class="rm-note-item-quote">${esc(q)}</div>` : ''}
          <div class="rm-note-item-body">${esc(n.text || '')}</div>
        </div>`;
      }).join('') : `<div class="rm-notes-empty">${esc(rmNotesState.scope === 'work' ? t('rm_notes_empty_work') : t('rm_notes_empty_part', { unit: t('rm_unit_' + rmState.media) }))}</div>`}
    </div>
    </div>`;

  rmAutoGrowTextarea(document.getElementById('rm-notes-input'), false);
  const nextBody = card.querySelector('.rm-notes-body');
  if (nextBody && prevScroll > 0) nextBody.scrollTop = prevScroll;
}

// A note's box grows with what is written, so no text hides behind a small inner scrollbar.
// While the end is typed it stays in view in the panel or page that scrolls around it.
function rmAutoGrowTextarea(el, follow = true) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = (el.scrollHeight + el.offsetHeight - el.clientHeight) + 'px';
  if (!follow || document.activeElement !== el || el.selectionEnd < el.value.length) return;
  const box = el.closest('.rm-notes-body');
  if (!box) return;
  const over = el.getBoundingClientRect().bottom - box.getBoundingClientRect().bottom + 8;
  if (over > 0) box.scrollTop += over;
}

// One save at a time: a second Ctrl+Enter or click while one is on its way saves nothing more.
async function rmSaveNote() {
  if (rmNotesState.saving) return;
  const ta = document.getElementById('rm-notes-input');
  if (!ta || !rmState.part) return;
  const text = ta.value.trim();
  if (!text) return;
  const wk = rmNotesWorkKey();
  const editing = rmNotesState.editingId ? rmNotesState.notes.find(n => n.id === rmNotesState.editingId) : null;
  let notePayload;
  if (editing) {
    notePayload = { id: editing.id, file: editing.file, text };
  } else {
    if (!rmNotesState.draftAnchor) rmRefreshNotesDraftAnchor(false);
    const a = rmNotesState.draftAnchor || rmReadAnchor() || {};
    const curItem = rmState.files[rmState.partIndex] || {};
    notePayload = {
      file: rmState.part.file,
      part_title: rmNotesShortTitle(rmState.part.file, curItem.title || rmState.part.file),
      text,
      anchor_v: 1,
      char_offset: a.char_offset || 0,
      char_total: rmState.totalPlainChars || rmState.part.char_count || 0,
      sec_index: a.sec_index || 0,
      scroll_ratio: a.scroll_ratio || 0,
      page: a.page || (rmState.media === 'manga' ? rmState.mangaPage : (rmState.pageIndex + 1)),
      quote: rmNotesState.draftQuote || a.quote || '',
      quote_furi: rmNotesState.draftSelected ? (rmNotesState.draftQuoteFuri || '') : '',
      selected: !!rmNotesState.draftSelected,
    };
    if (a.page_frac != null) notePayload.page_frac = a.page_frac;
    if (typeof a.edge === 'number') notePayload.edge = a.edge;
  }
  rmNotesState.saving = true;
  try {
    const res = await apiPost('/api/reading/notes', {
      media: rmState.media,
      folder: rmState.folder,
      note: notePayload,
    });
    if (rmNotesWorkKey() !== wk) return;
    if (res && Array.isArray(res.notes)) {
      rmNotesState.notes = res.notes;
      rmNotesState.editingId = '';
      ta.value = '';
      rmRefreshNotesDraftAnchor(true);
      rmUpdateNotesBtn();
      rmRenderNotesPanel();
      rmToast(t('rm_notes_saved'));
    }
  } catch (e) {
  } finally {
    rmNotesState.saving = false;
  }
}

function rmStartEditNote(id) {
  const hit = rmNotesState.notes.find(n => n.id === id);
  if (!hit) return;
  rmNotesState.editingId = id;
  rmRenderNotesPanel();
  const ta = document.getElementById('rm-notes-input');
  if (ta) {
    ta.value = hit.text || '';
    rmAutoGrowTextarea(ta, false);
    // The panel scrolls as a whole: an edit started far down the list brings the box into view
    const box = ta.closest('.rm-notes-body');
    const comp = ta.closest('.rm-notes-composer');
    if (box && comp) box.scrollTop = Math.max(0, comp.offsetTop - box.offsetTop);
    try { ta.focus({ preventScroll: true }); } catch (e) {}
  }
}

function rmCancelEditNote() {
  rmNotesState.editingId = '';
  const ta = document.getElementById('rm-notes-input');
  if (ta) ta.value = '';
  rmRenderNotesPanel();
}

async function rmDeleteNote(id) {
  if (!id || !rmState.media || !rmState.folder) return;
  const wk = rmNotesWorkKey();
  try {
    const r = await fetch('/api/reading/notes', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', ...API_HEADERS },
      body: JSON.stringify({ media: rmState.media, folder: rmState.folder, id }),
    });
    if (!r.ok) return;
    const data = await r.json();
    if (rmNotesWorkKey() !== wk) return;
    if (Array.isArray(data.notes)) {
      rmNotesState.notes = data.notes;
      if (rmNotesState.editingId === id) rmNotesState.editingId = '';
      rmUpdateNotesBtn();
      rmRenderNotesPanel();
      rmToast(t('rm_notes_deleted'));
    }
  } catch (e) {}
}

async function rmJumpToNote(id) {
  const note = rmNotesState.notes.find(n => n.id === id);
  if (!note) return;
  rmToggleNotes(false);
  const idx = rmState.files.findIndex(f => f.file === note.file);
  if (idx < 0) { rmToast(t('rm_place_gone')); return; }
  const beforePos = rmCapturePos();
  if (idx !== rmState.partIndex) {
    if (!(await rmLoadPart(idx, { targetAnchor: note.anchor_v ? note : null, targetRatio: note.scroll_ratio, targetPage: note.page || 1 }))) return;
  } else {
    rmRestoreAnchor(note);
    rmUpdateProgressUI();
  }
  rmPushLinkHistory(beforePos, rmCapturePos());
  saveMediaState();
  rmSaveProgressNow(false);
  rmToast(t('rm_notes_jumped'));
}

async function rmCopyTextToClipboard(text) {
  if (!text) {
    rmToast(t('rm_notes_copy_empty'));
    return false;
  }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      rmToast(t('rm_notes_copied'));
      return true;
    }
  } catch (e) {}
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    ta.remove();
    rmToast(ok ? t('rm_notes_copied') : t('rm_notes_copy_empty'));
    return ok;
  } catch (e) {
    rmToast(t('rm_notes_copy_empty'));
    return false;
  }
}

// ctx: { work, place } when the notes are copied outside Reading mode (the 保存 tab)
function rmFormatNotesMarkdown(notes, includeFurigana, multiPart, withQuotes = true, ctx = null) {
  if (!notes || !notes.length) return '';
  const work = ctx ? ctx.work : (rmState.folder || '');
  const curTitle = ctx ? '' : rmState.part ? rmNotesShortTitle(rmState.part.file, (rmState.files[rmState.partIndex] || {}).title) : '';
  const header = multiPart
    ? (LANG === 'ja' ? `# 『${work}』` : `# ${work}`)
    : (LANG === 'ja' ? `# 『${work}』 — ${curTitle}` : `# ${work} — ${curTitle}`);
  const lines = [header, ''];
  notes.forEach((n, i) => {
    const loc = ctx ? ctx.place(n) : rmFormatNoteLocation(n, multiPart);
    const label = LANG === 'ja' ? `## メモ ${i + 1}（${loc}）` : `## Note ${i + 1} (${loc})`;
    lines.push(label);
    const q = withQuotes ? rmNoteShownQuote(n, includeFurigana) : '';
    if (q) lines.push(`> ${q}`);
    lines.push(n.text || '');
    lines.push('');
  });
  return lines.join('\n').trim();
}

function rmCopyNotes(withQuotes) {
  const list = rmNotesForScope(rmNotesState.scope);
  const md = rmFormatNotesMarkdown(list, rmNotesState.copyFuri, rmNotesState.scope === 'work', !!withQuotes);
  return rmCopyTextToClipboard(md);
}

function rmCopySingleNote(id) {
  const note = rmNotesState.notes.find(n => n.id === id);
  if (!note) return;
  const md = rmFormatNotesMarkdown([note], rmNotesState.copyFuri, note.file !== (rmState.part && rmState.part.file));
  return rmCopyTextToClipboard(md);
}

function rmGetFullChapterText(includeFurigana) {
  const part = rmState.part;
  if (!part) return '';
  if (rmState.media === 'manga') {
    const chunks = [];
    for (const pg of (part.pages || [])) {
      const txt = rmMangaPageOcrText(pg.page);
      if (txt) chunks.push(`[${t('page_n', { n: fmt(pg.page) })}]\n${txt}`);
    }
    return chunks.join('\n\n').trim();
  }
  if (rmHtmlPart(part) && rmState.layout === 'paginated' && rmState.sections.length) {
    const chunks = [];
    for (const secHtml of rmState.sections) {
      const doc = rmParseSafeDoc(secHtml || '');
      const txt = rmExtractNodeText(doc.body, includeFurigana);
      if (txt) chunks.push(txt);
    }
    return chunks.join('\n\n').trim();
  }
  const root = document.getElementById('rm-epub-root');
  return rmExtractNodeText(root, includeFurigana);
}

function rmCopyFullChapter() {
  return rmCopyTextToClipboard(rmGetFullChapterText(rmNotesState.copyFuri));
}

function rmGetVisiblePaginatedText(root, scroller, includeFurigana) {
  if (!root || !scroller) return '';
  const vr = scroller.getBoundingClientRect();
  const vertical = rmState.dir === 'vertical';
  const range = document.createRange();
  const out = [];
  const emitBreak = () => {
    if (out.length && !out[out.length - 1].endsWith('\n')) out.push('\n');
  };
  const rectVis = (r) => {
    if (!r || r.width < 0.3 || r.height < 0.3) return false;
    const cx = (r.left + r.right) * 0.5;
    const cy = (r.top + r.bottom) * 0.5;
    return cx >= vr.left - 2 && cx <= vr.right + 2 && cy >= vr.top - 2 && cy <= vr.bottom + 2;
  };
  const walk = (n) => {
    if (!n) return;
    if (n.nodeType === 3) {
      const txt = n.nodeValue || '';
      if (!txt) return;
      range.selectNodeContents(n);
      const rects = range.getClientRects();
      let anyVis = false;
      let allVis = rects.length > 0;
      for (let i = 0; i < rects.length; i++) {
        if (rectVis(rects[i])) anyVis = true;
        else allVis = false;
      }
      if (!anyVis) return;
      if (allVis) {
        out.push(txt);
        return;
      }
      let buf = '';
      // One character at a time, an Ext-B kanji or emoji (two code units) as one
      for (let i = 0; i < txt.length;) {
        const w = txt.codePointAt(i) > 0xffff ? 2 : 1;
        range.setStart(n, i);
        range.setEnd(n, i + w);
        if (rectVis(range.getBoundingClientRect())) buf += txt.slice(i, i + w);
        i += w;
      }
      if (buf) out.push(buf);
      return;
    }
    if (n.nodeType !== 1) return;
    const tag = n.tagName;
    if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT' || tag === 'SVG' || tag === 'RT' || tag === 'RP') return;
    if (n.classList && (n.classList.contains('rm-sent-break') || n.classList.contains('rm-part-nav-end'))) return;
    if (n.classList && n.classList.contains('rm-sub-ts')) {
      if (!rmGetPrefs().sub_timestamps) return;
      if (rectVis(n.getBoundingClientRect())) {
        const ts = labelText(n).trim();
        if (ts) out.push(`[${ts}] `);
      }
      return;
    }
    if (tag === 'BR') {
      if (out.length) out.push('\n');
      return;
    }
    if (tag === 'RUBY') {
      const rr = n.getBoundingClientRect();
      if (!rectVis(rr)) return;
      out.push(rmExtractNodeText(n, includeFurigana));
      return;
    }
    const isBlock = RM_NOTES_BLOCK_TAGS.has(tag) || (n.classList && (n.classList.contains('rm-db-line') || n.classList.contains('rm-sub-line')));
    if (isBlock) emitBreak();
    for (let c = n.firstChild; c; c = c.nextSibling) walk(c);
    if (isBlock) emitBreak();
  };
  for (let k = root.firstChild; k; k = k.nextSibling) walk(k);
  return out.join('')
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function rmGetCurrentAreaText(includeFurigana) {
  if (rmNotesState.selectedPlain) {
    return (includeFurigana && rmNotesState.selectedFuri) ? rmNotesState.selectedFuri : rmNotesState.selectedPlain;
  }
  const part = rmState.part;
  if (!part) return '';
  if (rmState.media === 'manga') {
    const mStage = document.getElementById('rm-manga-stage');
    if (mStage && mStage.classList.contains('rm-manga-strip')) {
      const sr = mStage.getBoundingClientRect();
      const els = [...mStage.querySelectorAll('[data-page]')];
      let first = -1, last = -1;
      els.forEach((el, idx) => {
        const er = el.getBoundingClientRect();
        if (er.bottom > sr.top + 4 && er.top < sr.bottom - 4) {
          if (first < 0) first = idx;
          last = idx;
        }
      });
      if (first < 0) return rmMangaPageOcrText(rmState.mangaPage);
      const lo = Math.max(0, first - 1);
      const hi = Math.min(els.length - 1, last + 1);
      const out = [];
      for (let i = lo; i <= hi; i++) {
        const pno = parseInt(els[i].dataset.page || '0', 10);
        const txt = rmMangaPageOcrText(pno);
        if (txt) out.push(`[${t('page_n', { n: fmt(pno) })}]\n${txt}`);
      }
      return out.join('\n\n').trim();
    }
    return rmMangaPageOcrText(rmState.mangaPage);
  }
  const sc = rmScrollerEl();
  const root = document.getElementById('rm-epub-root');
  if (!sc || !root) return '';
  if (rmState.layout === 'paginated') {
    return rmGetVisiblePaginatedText(root, sc, includeFurigana);
  }
  const vr = sc.getBoundingClientRect();
  const vertical = rmState.dir === 'vertical';
  const childSel = 'p, li, blockquote, pre, h1, h2, h3, h4, h5, h6, .rm-db-line, .rm-sub-line';
  const blocks = [...root.querySelectorAll('p, li, blockquote, pre, h1, h2, h3, h4, h5, h6, div, .rm-db-line, .rm-sub-line')].filter(el =>
    !el.classList.contains('rm-part-nav-end') &&
    !el.closest('.rm-part-nav-end') &&
    !el.querySelector(childSel) &&
    (el.textContent || '').trim().length > 0
  );
  if (!blocks.length) return rmExtractNodeText(root, includeFurigana);
  let first = -1;
  let last = -1;
  for (let i = 0; i < blocks.length; i++) {
    const br = blocks[i].getBoundingClientRect();
    if (br.width < 0.5 || br.height < 0.5) continue;
    const vis = vertical
      ? (br.left < vr.right - 2 && br.right > vr.left + 2)
      : (br.bottom > vr.top + 2 && br.top < vr.bottom - 2);
    if (vis) {
      if (first < 0) first = i;
      last = i;
    }
  }
  if (first < 0) return rmExtractNodeText(root, includeFurigana);
  const lo = Math.max(0, first - 1);
  const hi = Math.min(blocks.length - 1, last + 1);
  const parts = [];
  for (let i = lo; i <= hi; i++) {
    const txt = rmExtractNodeText(blocks[i], includeFurigana);
    if (txt) parts.push(txt);
  }
  return parts.join('\n').trim();
}

function rmCopyCurrentPageOrArea() {
  return rmCopyTextToClipboard(rmGetCurrentAreaText(rmNotesState.copyFuri));
}
