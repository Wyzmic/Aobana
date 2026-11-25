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
            <span class="rm-extra-actions" id="rm-extra-actions"></span>
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
              <div class="rm-drawer-tabs" role="tablist">
                <button type="button" role="tab" class="rm-drawer-tab" data-toc-tab="toc" onclick="rmSetTocTab('toc')">${esc(t('rm_toc'))}</button>
                <button type="button" role="tab" class="rm-drawer-tab" data-toc-tab="bm" onclick="rmSetTocTab('bm')">${esc(t('rm_bookmarks'))}<span class="rm-drawer-tab-n" id="rm-toc-bm-n"></span></button>
              </div>
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
        <div class="sr-only" id="rm-live" aria-live="polite" aria-atomic="true"></div>
        <style id="rm-epub-style"></style>`;

      dlg.addEventListener('click', e => {
        const bmMenu = document.getElementById('rm-bm-menu');
        const path = e.composedPath ? e.composedPath() : [];
        const insideBm = path.includes(bmMenu) || (e.target && e.target.closest && e.target.closest('#rm-bm-menu, #rm-bm-btn'));
        if (bmMenu && !bmMenu.hidden && !insideBm) {
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
      rmState.prefsKey = '';
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
        rmState.prefsKey = data.prefs_key || media;
        if (data.prefs) rmSetPrefsCache(rmState.prefsKey, data.prefs);
        rmApplyPrefsToDom(false);
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
      rmState.prefsKey = '';
      rmState.chunkGen++;
      const extraAct = document.getElementById('rm-extra-actions');
      if (extraAct) extraAct.innerHTML = '';
      if (typeof rmOnCloseHook === 'function') rmOnCloseHook();
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
      const prof = RM_EXTRA_PROFILES[rmPrefsMedia()];
      if (prof && typeof prof.openInSettings === 'function') return prof.openInSettings();
      store.set('reader_settings_media', rmState.media === 'manga' && rmMangaTextOnly(rmState.part) ? 'manga-text' : rmState.media);
      window.location.href = '/?tab=settings#set-reader';
    }

    async function rmLoadPart(index, opts = {}) {
      if (index < 0 || index >= rmState.files.length) return false;
      rmLanded = null;
      rmState.partIndex = index;
      const item = rmState.files[index];
      if (typeof rmOnPartWillChange === 'function') rmOnPartWillChange(item);
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
        if (gen !== rmState.loadGen || !isReadingModeOpen()) return false;
      }
      let r = null;
      let part = null;
      try {
        r = await fetch(`/api/reading/part?media=${encodeURIComponent(rmState.media)}&folder=${encodeURIComponent(rmState.folder)}&file=${encodeURIComponent(item.file)}&client=${RM_PART_CLIENT}&seq=${gen}`, { signal: ctrl.signal });
        if (r.ok) part = await r.json();
      } catch (e) {}
      if (rmState.partCtrl === ctrl) rmState.partCtrl = null;
      if (gen !== rmState.loadGen || !isReadingModeOpen()) return false;
      if (!part) {
        stage.innerHTML = `<div class="error-text" style="padding:2em;text-align:center;">${esc(t('load_failed'))}</div>`;
        return false;
      }
      rmState.part = part;
      if (part.prefs_key) rmState.prefsKey = part.prefs_key;
      if (typeof rmPreparePart === 'function') rmPreparePart(part);
      rmResolveDirAndLayout();
      if (typeof rmUpdateExtraActions === 'function') rmUpdateExtraActions(part);
      rmRenderToc();

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
      rmAnnounce(shortTitle);
      rmUpdateBookmarkBtn();
      if (typeof rmOnNotesPartChange === 'function') rmOnNotesPartChange();
      saveMediaState();
      if (opts.fromHistory) rmSaveProgressNow(false);
      else rmScheduleSaveProgress();
      return true;
    }

    function rmSyncPartNavButtons() {
      const prevBtn = document.getElementById('rm-prev-btn');
      const nextBtn = document.getElementById('rm-next-btn');
      if (!prevBtn || !nextBtn || prevBtn.parentElement !== nextBtn.parentElement) return;
      const verticalNav = rmState.media === 'manga' || rmState.dir === 'vertical';
      const parent = prevBtn.parentElement;
      if (verticalNav) {
        if (prevBtn.nextElementSibling === nextBtn) parent.insertBefore(nextBtn, prevBtn);
      } else if (nextBtn.nextElementSibling === prevBtn) {
        parent.insertBefore(prevBtn, nextBtn);
      }
      const prevPath = prevBtn.querySelector('svg path');
      const nextPath = nextBtn.querySelector('svg path');
      if (prevPath) prevPath.setAttribute('d', verticalNav ? 'M9 6l6 6-6 6' : 'M15 18l-6-6 6-6');
      if (nextPath) nextPath.setAttribute('d', verticalNav ? 'M15 18l-6-6 6-6' : 'M9 6l6 6-6 6');
    }

    function rmSyncFuriganaAria() {
      const stage = document.getElementById('rm-stage');
      if (!stage) return;
      const hoverMode = rmGetPrefs().furigana === 'hover';
      stage.querySelectorAll('ruby rt').forEach(rt => {
        const ruby = rt.closest('ruby');
        const hide = hoverMode && !(ruby && ruby.classList.contains('rm-ruby-open'));
        if (hide) rt.setAttribute('aria-hidden', 'true');
        else rt.removeAttribute('aria-hidden');
      });
    }

    function rmAnnounce(text) {
      const el = document.getElementById('rm-live');
      if (!el || !text) return;
      el.textContent = String(text);
    }

    function rmPageAnnounceText() {
      if (!rmState.part) return '';
      if (rmState.media === 'manga') {
        const total = Math.max(1, (rmState.part.pages || []).length);
        const cur = Math.max(1, Math.min(total, rmState.mangaPage));
        return t('rm_page_of', { a: fmt(cur), b: fmt(total) });
      }
      if (rmState.layout !== 'paginated') return '';
      const sCount = Math.max(1, rmState.sections.length);
      if (sCount > 1 && rmState.pageCount === 1) {
        return t('rm_page_of', { a: fmt(rmState.secIndex + 1), b: fmt(sCount) });
      }
      if (sCount > 1) {
        return `${fmt(rmState.secIndex + 1)}/${fmt(sCount)} · ${t('rm_page_of', { a: fmt(rmState.pageIndex + 1), b: fmt(rmState.pageCount) })}`;
      }
      return t('rm_page_of', { a: fmt(rmState.pageIndex + 1), b: fmt(rmState.pageCount) });
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
          if (typeof rmPreparePart === 'function') rmPreparePart(rmState.part);
          if (typeof rmUpdateExtraActions === 'function') rmUpdateExtraActions(rmState.part);
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
      rmSyncPartNavButtons();
      rmSyncFuriganaAria();
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

    function rmBindFoldEvents(root) {
      if (!root || root.dataset.rmFoldsBound) return;
      root.dataset.rmFoldsBound = '1';
      root.addEventListener('toggle', e => {
        if (!e.target || e.target.tagName !== 'DETAILS') return;
        if (typeof rmOnFoldToggle === 'function') rmOnFoldToggle(e.target);
        if (rmState.layout === 'paginated') {
          rmMeasurePagination();
          rmApplyPaginatedOffset(Math.min(rmState.pageCount - 1, rmState.pageIndex));
          rmUpdateProgressUI();
        } else {
          rmScheduleProgressUI();
          rmScheduleSaveProgress();
        }
      }, true);
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
      if (typeof rmAfterPartRender === 'function') rmAfterPartRender(root, rmState.part);
      rmBindFoldEvents(root);
      rmSyncFuriganaAria();
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
          rmSyncFuriganaAria();
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
        rmSyncFuriganaAria();
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
        if (typeof rmAfterPartRender === 'function') rmAfterPartRender(root, part);
        rmBindFoldEvents(root);
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
