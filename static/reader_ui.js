    const RM_BOOKMARKS_MAX = 100;

    function rmWorkBookmarks(work = rmState.work) {
      if (!work) return [];
      if (Array.isArray(work.bookmarks)) return work.bookmarks;
      if (work.bookmark && typeof work.bookmark === 'object') return [work.bookmark];
      return [];
    }

    function rmBookmarkPlaceKey(bm) {
      if (!bm) return '';
      const sec = Number(bm.sec_index || 0), ch = Number(bm.char_offset || 0);
      const pg = rmState.media === 'manga' ? Number(bm.page || 0) : 0;
      return `${bm.file || ''}|${sec}|${ch}|${pg}`;
    }

    function rmCurrentBookmarkCandidate() {
      if (!rmState.part) return null;
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
        created_at: Math.floor(Date.now() / 1000),
      };
      if (anchor && anchor.page_frac != null) nextBm.page_frac = anchor.page_frac;
      if (anchor && typeof anchor.edge === 'number') nextBm.edge = anchor.edge;
      return nextBm;
    }

    function rmCurrentBookmarkIndex() {
      const cand = rmCurrentBookmarkCandidate();
      if (!cand) return -1;
      const key = rmBookmarkPlaceKey(cand);
      return rmWorkBookmarks().findIndex(b => rmBookmarkPlaceKey(b) === key);
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
      const bms = rmWorkBookmarks();
      btn.title = bms.length ? `${t('rm_bookmarks')} (${fmt(bms.length)})` : t('rm_bookmark_set');
    }

    // One bookmark at a time, and the list the server answers with: another tab's bookmarks on
    // the same work stay, and a failed write leaves memory unchanged.
    async function rmSaveBookmarkDelta(delta) {
      const res = await apiPost('/api/reading/state', { media: rmState.media, folder: rmState.folder, work: delta }).catch(() => null);
      const bms = res && res.work && Array.isArray(res.work.bookmarks) ? res.work.bookmarks : null;
      if (!bms) return false;
      const work = { ...(rmState.work || {}), bookmarks: bms };
      delete work.bookmark;
      rmState.work = work;
      return true;
    }

    async function rmAddBookmarkHere() {
      const nextBm = rmCurrentBookmarkCandidate();
      if (!nextBm) return false;
      const existing = rmWorkBookmarks();
      const key = rmBookmarkPlaceKey(nextBm);
      const dupIdx = existing.findIndex(b => rmBookmarkPlaceKey(b) === key);
      if (dupIdx >= 0) {
        if (!(await rmSaveBookmarkDelta({ bookmark_remove: existing[dupIdx] }))) {
          rmToast(t('error'));
          return false;
        }
        rmUpdateBookmarkBtn();
        rmRenderToc();
        const bmMenu = document.getElementById('rm-bm-menu');
        if (bmMenu && !bmMenu.hidden) rmRenderBookmarkMenu();
        rmToast(t('rm_bookmark_deleted'));
        return false;
      }
      if (existing.length >= RM_BOOKMARKS_MAX) {
        rmToast(t('rm_bookmark_limit', { n: fmt(RM_BOOKMARKS_MAX) }));
        return false;
      }
      if (!(await rmSaveBookmarkDelta({ bookmark_add: nextBm }))) {
        rmToast(t('error'));
        return false;
      }
      rmUpdateBookmarkBtn();
      rmRenderToc();
      const bmMenu = document.getElementById('rm-bm-menu');
      if (bmMenu && !bmMenu.hidden) rmRenderBookmarkMenu();
      rmToast(`${t('rm_bookmark_saved')} ${rmFormatBookmarkPlace(nextBm)}`);
      return true;
    }

    async function rmGoBookmark(bmIdx = 0) {
      const bms = rmWorkBookmarks();
      const bm = bms[bmIdx];
      const bmMenu = document.getElementById('rm-bm-menu');
      if (bmMenu) bmMenu.hidden = true;
      if (!bm) return;
      const idx = rmState.files.findIndex(f => f.file === bm.file);
      if (idx < 0) { rmToast(t('rm_place_gone')); return; }
      const beforePos = rmCapturePos();
      if (idx !== rmState.partIndex) {
        if (!(await rmLoadPart(idx, { targetAnchor: bm.anchor_v ? bm : null, targetRatio: bm.scroll_ratio, targetPage: bm.page || 1 }))) return;
      } else if (rmState.media === 'manga') {
        rmRestoreAnchor(bm);
      } else {
        rmRestoreAnchor(bm);
        rmUpdateProgressUI();
      }
      rmPushLinkHistory(beforePos, rmCapturePos());
      saveMediaState();
      rmSaveProgressNow(false);
      rmToast(t('rm_bookmark_jumped'));
    }

    async function rmDeleteBookmark(i) {
      const bm = rmWorkBookmarks()[i];
      if (!bm) return;
      if (!(await rmSaveBookmarkDelta({ bookmark_remove: bm }))) {
        rmToast(t('error'));
        return;
      }
      rmUpdateBookmarkBtn();
      rmRenderBookmarkMenu();
      rmRenderToc();
      rmToast(t('rm_bookmark_deleted'));
    }

    function rmRenderBookmarkMenu() {
      const menu = document.getElementById('rm-bm-menu');
      if (!menu) return;
      const bms = rmWorkBookmarks();
      const here = rmCurrentBookmarkIndex() >= 0;
      const headBtn = `<div class="rm-bm-actions">
        <button type="button" class="btn ${here ? '' : 'primary'}" id="rm-bm-add-btn" onclick="rmAddBookmarkHere()">${esc(t(here ? 'rm_bookmark_remove_here' : 'rm_bookmark_add_here'))}</button>
      </div>`;
      if (!bms.length) {
        menu.innerHTML = headBtn + `<div class="rm-bm-where">${esc(t('rm_bookmark_empty'))}</div>`;
        return;
      }
      const head = rmTocCommonHead(rmState.files.map(it => it.title || it.file));
      const shortLbl = s => (head && s.startsWith(head) && s.length > head.length ? s.slice(head.length) : s);
      const rows = bms.map((bm, i) => {
        const place = rmFormatBookmarkPlace({ ...bm, label: shortLbl(bm.label || bm.file || '') });
        return `<div class="rm-bm-item" data-bm-idx="${i}">
          ${bm.name ? `<div class="rm-bm-name">${esc(bm.name)}</div>` : ''}
          <div class="rm-bm-where">${esc(place)}</div>
          <div class="rm-bm-row-actions">
            <button type="button" class="btn primary" onclick="rmGoBookmark(${i})">${esc(t('rm_bookmark_go_one'))}</button>
            <button type="button" class="btn" onclick="rmDeleteBookmark(${i})">${esc(t('rm_notes_delete'))}</button>
          </div>
        </div>`;
      }).join('');
      menu.innerHTML = headBtn + `<div class="rm-bm-list">${rows}</div>`;
    }

    function rmOnBookmarkClick() {
      rmCloseFontPopup(false);
      const notesp = document.getElementById('rm-notes-panel');
      if (notesp && !notesp.hidden && typeof rmToggleNotes === 'function') rmToggleNotes(false);
      const menu = document.getElementById('rm-bm-menu');
      if (!menu) return;
      if (!menu.hidden) {
        menu.hidden = true;
        rmResetTopbarForMode();
        return;
      }
      rmRenderBookmarkMenu();
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
    // The drawer's two tabs, 目次 and しおり; inside 目次, files (nested tree when subfolders exist) or in-file sections
    let rmTocTab = 'toc';
    let rmTocSub = 'files';
    let rmTocQuery = '';
    function rmSetTocTab(tab) {
      rmTocTab = tab === 'bm' ? 'bm' : 'toc';
      rmRenderToc();
      const list = document.getElementById('rm-toc-list');
      if (list) list.scrollTop = 0;
      if (rmTocTab === 'toc') {
        const active = list && list.querySelector('.rm-toc-item.active');
        if (active) active.scrollIntoView({ block: 'center' });
      }
    }
    function rmSetTocSub(sub) {
      rmTocSub = sub === 'sections' ? 'sections' : 'files';
      rmRenderToc();
      const list = document.getElementById('rm-toc-list');
      if (list) list.scrollTop = 0;
    }
    function rmSetTocQuery(val) {
      rmTocQuery = String(val || '');
      const list = document.getElementById('rm-toc-list');
      const itemsBox = list && list.querySelector('.rm-toc-tree-body');
      if (itemsBox) {
        itemsBox.innerHTML = rmTocFilesHtml();
      } else {
        rmRenderToc();
      }
    }
    function rmTocBuildTree(files, queryFolded) {
      const root = { name: '', folders: new Map(), items: [], count: 0, hasActive: false };
      files.forEach((it, i) => {
        const parts = Array.isArray(it.folder_parts) ? it.folder_parts : [];
        const title = it.title || it.file;
        if (queryFolded) {
          const hay = foldTitleFilter([...parts, title].join(' '));
          if (!hay.includes(queryFolded)) return;
        }
        let node = root;
        const active = i === rmState.partIndex;
        if (active) node.hasActive = true;
        node.count++;
        for (const seg of parts) {
          let next = node.folders.get(seg);
          if (!next) {
            next = { name: seg, folders: new Map(), items: [], count: 0, hasActive: false };
            node.folders.set(seg, next);
          }
          next.count++;
          if (active) next.hasActive = true;
          node = next;
        }
        node.items.push({ it, i, title, active });
      });
      return root;
    }
    function rmTocRenderTree(node, expandAll, depth = 0) {
      const out = [];
      for (const child of node.folders.values()) {
        const open = expandAll || child.hasActive;
        out.push(`<details class="rm-toc-folder" style="--rm-toc-depth:${depth}"${open ? ' open' : ''}>
          <summary><span class="rm-toc-arrow" aria-hidden="true">▸</span><span class="rm-toc-folder-name">${esc(child.name)}</span><span class="rm-toc-folder-n">${esc(fmt(child.count))}</span></summary>
          <div class="rm-toc-folder-body">${rmTocRenderTree(child, expandAll, depth + 1)}</div>
        </details>`);
      }
      for (const { i, title, active } of node.items) {
        out.push(`<button type="button" class="rm-toc-item ${active ? 'active' : ''}" data-idx="${i}" onclick="rmJumpToc(${i})"><span>${esc(title)}</span></button>`);
      }
      return out.join('');
    }
    function rmTocFilesHtml() {
      const hasTree = rmState.files.some(it => Array.isArray(it.folder_parts) && it.folder_parts.length > 0);
      const q = rmTocQuery.trim() ? foldTitleFilter(rmTocQuery.trim()) : '';
      if (hasTree) {
        const tree = rmTocBuildTree(rmState.files, q);
        return tree.count ? rmTocRenderTree(tree, !!q, 0) : `<div class="rm-toc-empty">${esc(t('rm_toc_no_match'))}</div>`;
      }
      const head = rmTocCommonHead(rmState.files.map(it => it.title || it.file));
      const label = s => (head && s.startsWith(head) && s.length > head.length ? s.slice(head.length) : s);
      let lastGroup = '';
      const out = [];
      rmState.files.forEach((it, i) => {
        const shown = label(it.title || it.file);
        if (q && !foldTitleFilter(shown + ' ' + (it.book_folder || '')).includes(q)) return;
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
        out.push(`<button type="button" class="rm-toc-item ${i === rmState.partIndex ? 'active' : ''}" data-idx="${i}" onclick="rmJumpToc(${i})"><span>${esc(shown)}</span></button>`);
      });
      return out.length ? out.join('') : `<div class="rm-toc-empty">${esc(t('rm_toc_no_match'))}</div>`;
    }
    function rmJumpHeading(member, anchorId) {
      rmToggleToc(false);
      const beforePos = rmCapturePos();
      if (rmGoToAnchorInPart(member, anchorId, true)) {
        const root = document.getElementById('rm-epub-root');
        const el = root && anchorId ? document.getElementById(anchorId) : null;
        if (el) {
          for (let p = el; p && p !== root; p = p.parentElement) {
            if (p.tagName === 'DETAILS' && !p.open) p.open = true;
          }
          if (rmState.layout === 'paginated') {
            rmMeasurePagination();
            rmGoToAnchorInPart(member, anchorId, true);
          } else {
            el.scrollIntoView({ block: 'start', behavior: 'instant' });
            rmUpdateProgressUI();
          }
        }
        rmPushLinkHistory(beforePos, rmCapturePos());
        saveMediaState();
        rmSaveProgressNow(false);
      }
    }
    function rmTocBookmarkRows(bms, label) {
      if (!bms.length) return `<div class="rm-toc-empty">${esc(t('rm_bookmark_empty'))}</div>`;
      return bms.map((bm, bi) => {
        const place = rmFormatBookmarkPlace({ ...bm, label: label(bm.label || bm.file || '') });
        const text = bm.name ? `<span class="rm-toc-bm-name">${esc(bm.name)}</span><span class="rm-toc-bm-sub">${esc(place)}</span>` : `<span>${esc(place)}</span>`;
        return `<div class="rm-toc-bm-row" data-bm-idx="${bi}">
          <button type="button" class="rm-toc-item rm-toc-bm-item" onclick="rmToggleToc(false); rmGoBookmark(${bi})">${text}</button>
          <button type="button" class="icon-btn rm-toc-bm-x" title="${esc(t('rm_bookmark_delete_one'))}" aria-label="${esc(t('rm_bookmark_delete_one'))}" onclick="rmDeleteBookmark(${bi})"><span>×</span></button>
        </div>`;
      }).join('');
    }
    function rmRenderToc() {
      const list = document.getElementById('rm-toc-list');
      if (!list) return;
      const bms = rmWorkBookmarks();
      const head = rmTocCommonHead(rmState.files.map(it => it.title || it.file));
      const label = s => (head && s.startsWith(head) && s.length > head.length ? s.slice(head.length) : s);
      document.querySelectorAll('#rm-toc-drawer .rm-drawer-tab').forEach(b => {
        const on = b.dataset.tocTab === rmTocTab;
        b.classList.toggle('active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      const n = document.getElementById('rm-toc-bm-n');
      if (n) n.textContent = bms.length ? fmt(bms.length) : '';
      if (rmTocTab === 'bm') {
        list.innerHTML = rmTocBookmarkRows(bms, label);
        return;
      }
      const headings = (rmState.part && Array.isArray(rmState.part.toc_headings)) ? rmState.part.toc_headings : [];
      if (!headings.length && rmTocSub === 'sections') rmTocSub = 'files';
      const subBar = headings.length ? `<div class="rm-toc-sub"><div class="seg seg-fit">
        <button type="button" class="seg-btn ${rmTocSub === 'files' ? 'active' : ''}" onclick="rmSetTocSub('files')">${esc(t('rm_toc_files'))}</button>
        <button type="button" class="seg-btn ${rmTocSub === 'sections' ? 'active' : ''}" onclick="rmSetTocSub('sections')">${esc(t('rm_toc_sections'))} (${esc(fmt(headings.length))})</button>
      </div></div>` : '';
      if (rmTocSub === 'sections' && headings.length) {
        list.innerHTML = subBar + headings.map(h =>
          `<button type="button" class="rm-toc-item rm-toc-heading-item${h.sub ? ' rm-toc-sub-item' : ''}" onclick="rmJumpHeading('${esc(h.member || '')}', '${esc(h.id || '')}')"><span>${esc(h.label)}</span></button>`
        ).join('');
        return;
      }
      const filterBar = rmState.files.length >= 20 ? `<div class="rm-toc-filter-wrap">
        <input type="text" id="rm-toc-filter" class="folder-filter rm-toc-filter" placeholder="${esc(t('rm_toc_filter'))}" value="${esc(rmTocQuery)}" autocomplete="off" spellcheck="false" oninput="if(!isComposing)rmSetTocQuery(this.value)">
      </div>` : '';
      list.innerHTML = subBar + filterBar + `<div class="rm-toc-tree-body">${rmTocFilesHtml()}</div>`;
      const fInput = document.getElementById('rm-toc-filter');
      if (fInput) {
        fInput.addEventListener('compositionstart', () => { isComposing = true; });
        fInput.addEventListener('compositionend', () => { isComposing = false; rmSetTocQuery(fInput.value); });
      }
    }
    function rmHighlightToc() {
      document.querySelectorAll('#rm-toc-list .rm-toc-item[data-idx]').forEach(el => {
        el.classList.toggle('active', Number(el.dataset.idx) === rmState.partIndex);
      });
    }
    async function rmJumpToc(idx) {
      rmToggleToc(false);
      if (idx < 0 || idx >= rmState.files.length) return;
      const beforePos = rmCapturePos();
      if (!(await rmLoadPart(idx, {}))) return;
      rmPushLinkHistory(beforePos, rmCapturePos());
      saveMediaState();
      rmSaveProgressNow(false);
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
        rmRenderToc();
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
      const fixed = rmFixedPrefs();
      // Page turns exist in page view and in a manga's single pages, never in its strip.
      const pageTurns = isManga
        ? !mangaText && p.manga_layout !== 'strip' && !(rmState.part && rmState.part.source === 'db')
        : layoutVal === 'paginated';
      card.innerHTML = `
        <div class="rm-drawer-head">
          <span>${esc(t('rm_settings'))}</span>
          <button type="button" class="sq-btn" onclick="rmToggleSettings(false)" aria-label="${esc(t('close'))}">✕</button>
        </div>
        <div class="rm-settings-body">
          ${!isManga ? `${fixed.writing_mode ? '' : `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_dir'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${dirVal === 'auto' ? 'active' : ''}" onclick="rmSetDir('auto')">${esc(t('rm_dir_auto'))}</button>
              <button type="button" class="seg-btn ${dirVal === 'vertical' ? 'active' : ''}" onclick="rmSetDir('vertical')">${esc(t('rm_dir_vertical'))}</button>
              <button type="button" class="seg-btn ${dirVal === 'horizontal' ? 'active' : ''}" onclick="rmSetDir('horizontal')">${esc(t('rm_dir_horizontal'))}</button>
            </div>
          </div>`}${fixed.layout ? '' : `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_layout'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${layoutVal === 'paginated' ? 'active' : ''}" onclick="rmSetLayout('paginated')">${esc(t('rm_layout_paginated'))}</button>
              <button type="button" class="seg-btn ${layoutVal === 'continuous' ? 'active' : ''}" onclick="rmSetLayout('continuous')">${esc(t('rm_layout_continuous'))}</button>
            </div>
          </div>`}` : mangaText ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_dir'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${rmMangaTextVertical(p) ? 'active' : ''}" onclick="rmUpdatePrefs({writing_mode:'vertical'})">${esc(t('rm_dir_vertical'))}</button>
              <button type="button" class="seg-btn ${rmMangaTextVertical(p) ? '' : 'active'}" onclick="rmUpdatePrefs({writing_mode:'horizontal'})">${esc(t('rm_dir_horizontal'))}</button>
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
              <input type="range" min="8" max="72" step="1" value="${p.font_size}" oninput="rmLiveRangePref('font_size', Number(this.value), this.nextElementSibling, this.value + 'px')" onchange="rmUpdatePrefs({font_size:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
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
          ${layoutVal === 'continuous' || mangaText ? `<div class="rm-set-row">
            <span class="rm-set-label">${esc(t((mangaText ? rmMangaTextVertical(p) : rmState.dir === 'vertical') ? 'rm_max_height' : 'rm_max_width'))}</span>
            <div class="rm-range-row">
              <input type="range" min="10" max="100" step="1" value="${p.scroll_size_pct || 75}" oninput="rmLiveRangePref('scroll_size_pct', Number(this.value), this.nextElementSibling, this.value + '%')" onchange="rmUpdatePrefs({scroll_size_pct:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.scroll_size_pct || 75}%</span>
            </div>
          </div>` : `<div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_max_width'))}</span>
            <div class="rm-range-row">
              <input type="range" min="10" max="100" step="1" value="${p.width_pct || 75}" oninput="rmLiveRangePref('width_pct', Number(this.value), this.nextElementSibling, this.value + '%')" onchange="rmUpdatePrefs({width_pct:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.width_pct || 75}%</span>
            </div>
          </div>
          ${fixed.writing_mode === 'horizontal' ? '' : `<div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_max_height'))}</span>
            <div class="rm-range-row">
              <input type="range" min="10" max="100" step="1" value="${p.height_pct || 85}" oninput="rmLiveRangePref('height_pct', Number(this.value), this.nextElementSibling, this.value + '%')" onchange="rmUpdatePrefs({height_pct:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.height_pct || 85}%</span>
            </div>
          </div>`}`}
          ${rmState.media === 'epub' && layoutVal === 'continuous' ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_image_scale'))}</span>
            <div class="rm-range-row">
              <input type="range" min="25" max="100" step="5" value="${p.image_scale || 80}" oninput="rmLiveRangePref('image_scale', Number(this.value), this.nextElementSibling, this.value + '%')" onchange="rmUpdatePrefs({image_scale:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.image_scale || 80}%</span>
            </div>
          </div>` : ''}` : ''}
          ${isSubs && !(rmState.part && rmState.part.source === 'db') ? `
          <div class="rm-set-row-inline">
            <span class="rm-set-label">${esc(t('rm_sub_timestamps'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.sub_timestamps ? 'active' : ''}" onclick="rmUpdatePrefs({sub_timestamps:true})">${esc(t('lib_cache_on'))}</button>
              <button type="button" class="seg-btn ${!p.sub_timestamps ? 'active' : ''}" onclick="rmUpdatePrefs({sub_timestamps:false})">${esc(t('lib_cache_off'))}</button>
            </div>
          </div>` : ''}
          ${RM_EXTRA_PROFILES[rmPrefsMedia()]?.settingsHtml ? RM_EXTRA_PROFILES[rmPrefsMedia()].settingsHtml(p) : ''}
          ${pageTurns ? `
          <div class="rm-set-row-inline">
            <span class="rm-set-label">${esc(rmPageTurnLabel('rm_scroll_turn'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.scroll_turn_page !== false ? 'active' : ''}" onclick="rmUpdatePrefs({scroll_turn_page:true})">${esc(t('lib_cache_on'))}</button>
              <button type="button" class="seg-btn ${p.scroll_turn_page === false ? 'active' : ''}" onclick="rmUpdatePrefs({scroll_turn_page:false})">${esc(t('lib_cache_off'))}</button>
            </div>
          </div>` : ''}
          ${pageTurns ? `
          <div class="rm-set-row-inline">
            <span class="rm-set-label">${esc(rmPageTurnLabel('rm_edge_click'))}</span>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${p.edge_click_nav !== false ? 'active' : ''}" onclick="rmUpdatePrefs({edge_click_nav:true})">${esc(t('lib_cache_on'))}</button>
              <button type="button" class="seg-btn ${p.edge_click_nav === false ? 'active' : ''}" onclick="rmUpdatePrefs({edge_click_nav:false})">${esc(t('lib_cache_off'))}</button>
            </div>
          </div>
          ${p.edge_click_nav !== false ? `
          <div class="rm-set-row">
            <span class="rm-set-label">${esc(rmPageTurnLabel('rm_edge_click_width'))}</span>
            <div class="rm-range-row">
              <input type="range" min="5" max="40" step="1" value="${p.edge_click_width || 25}" oninput="rmLiveRangePref('edge_click_width', Number(this.value), this.nextElementSibling, this.value + '%')" onchange="rmUpdatePrefs({edge_click_width:Number(this.value)}, {rebuildSettings:false, endDrag:true})">
              <span class="rm-range-val">${p.edge_click_width || 25}%</span>
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
          ${rmWorkBookmarks().length ? `<div class="rm-set-row">
            <span class="rm-set-label">${esc(t('rm_bookmarks'))} (${fmt(rmWorkBookmarks().length)})</span>
            <div class="rm-set-row-inline">
              <button type="button" class="btn primary" onclick="rmToggleSettings(false); rmGoBookmark(0)">${esc(t('rm_bookmark_go'))}</button>
              <button type="button" class="btn" onclick="rmToggleSettings(false); rmOnBookmarkClick()">${esc(t('rm_bookmarks'))}</button>
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
      if (typeof rmSyncEdgeZones === 'function') rmSyncEdgeZones();
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
      if (e.target && e.target.closest && e.target.closest('[data-rm-overlay-bar]')) return;
      if (isHelpKey) { e.preventDefault(); rmStopGlide(); toggleShortcutsModal(); return; }

      // A sub-profile may take keys of its own first.
      if (typeof rmExtraKey === 'function' && rmExtraKey(e)) { e.preventDefault(); return; }

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
      if ((e.key === 'b' || e.key === 'B') && !e.shiftKey) { e.preventDefault(); rmAddBookmarkHere(); return; }
      if ((e.key === 'n' || e.key === 'N') && !e.shiftKey && typeof rmToggleNotes === 'function') { e.preventDefault(); rmCaptureNotesSelection(); rmToggleNotes(); return; }
      if ((e.key === 'f' || e.key === 'F') && !e.shiftKey) { e.preventDefault(); rmCycleFurigana(); return; }
      if ((e.key === 's' || e.key === 'S') && !e.shiftKey) { e.preventDefault(); rmToggleSettings(); return; }
      if (e.key === '0' && rmState.media === 'manga') { e.preventDefault(); rmMangaFit(false); return; }
    }
