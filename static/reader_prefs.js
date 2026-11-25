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

    // Subtitles, books and manga keep their own display settings. Optional sub-profiles register here.
    const RM_EXTRA_PROFILES = {};
    const rmPrefsCache = {};
    function rmRegisterProfile(key, opts = {}) {
      RM_EXTRA_PROFILES[key] = opts;
    }
    function rmIsValidPrefsKey(m) {
      return RM_ENABLED_MEDIA.has(m) || Object.prototype.hasOwnProperty.call(RM_EXTRA_PROFILES, m);
    }
    function rmPrefsMedia(media) {
      if (media && rmIsValidPrefsKey(media)) return media;
      if (rmState.prefsKey && rmIsValidPrefsKey(rmState.prefsKey)) return rmState.prefsKey;
      return RM_ENABLED_MEDIA.has(rmState.media) ? rmState.media : 'epub';
    }
    // Subtitles scroll by default; optional sub-profiles may set their own defaults.
    function rmDefaultPrefs(m) {
      const extra = RM_EXTRA_PROFILES[m];
      const base = m === 'subs' || (extra && extra.defaultLayout === 'continuous')
        ? { ...RM_DEFAULT_PREFS, layout: 'continuous' }
        : { ...RM_DEFAULT_PREFS };
      return extra && extra.defaults ? { ...base, ...extra.defaults } : base;
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
        for (const prof of Object.values(RM_EXTRA_PROFILES)) {
          if (prof && typeof prof.onFontsLoaded === 'function') prof.onFontsLoaded();
        }
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
    // A sub-profile may fix some settings ("fixed": { key: value }); they win over anything saved,
    // and their rows leave the settings.
    function rmFixedPrefs(media) {
      const extra = RM_EXTRA_PROFILES[rmPrefsMedia(media)];
      return (extra && extra.fixed) || {};
    }
    function rmGetPrefs(media) {
      const m = rmPrefsMedia(media);
      const fixed = rmFixedPrefs(m);
      if (rmPrefsCache[m]) return { ...rmDefaultPrefs(m), ...rmPrefsCache[m], ...fixed };
      try {
        const saved = JSON.parse(store.get(`${RM_PREFS_KEY}_${m}`) || 'null');
        if (saved && typeof saved === 'object') {
          rmPrefsCache[m] = { ...rmDefaultPrefs(m), ...saved };
          return { ...rmPrefsCache[m], ...fixed };
        }
      } catch (e) {}
      return { ...rmDefaultPrefs(m), ...fixed };
    }
    async function rmFetchPrefs() {
      try {
        const r = await fetch('/api/reading/state');
        if (r.ok) {
          const data = await r.json();
          const all = (data && data.prefs_by_media) || {};
          for (const m of RM_ENABLED_MEDIA) if (all[m]) rmSetPrefsCache(m, all[m]);
          for (const m of Object.keys(RM_EXTRA_PROFILES)) if (all[m]) rmSetPrefsCache(m, all[m]);
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
      const activeKey = rmPrefsMedia();
      const needsRelayout = Object.keys(patch || {}).some(k => !RM_NO_RELAYOUT_KEYS.has(k));
      const anchor = (needsRelayout && isReadingModeOpen() && m === activeKey && rmState.part)
        ? (opts.anchor || rmDragAnchor || rmLayoutAnchor())
        : null;
      if (opts.endDrag) rmClearDragAnchor();
      const next = { ...rmGetPrefs(m), ...patch };
      rmSetPrefsCache(m, next);
      let saved = false;
      try {
        const res = await apiPost('/api/reading/state', { media: m, prefs: patch });
        if (res && !res.error) {
          saved = true;
          if (res.prefs) rmSetPrefsCache(m, res.prefs);
        }
      } catch (e) {}
      if (isReadingModeOpen() && m === activeKey) {
        rmApplyPrefsToDom(needsRelayout, opts.rebuildSettings !== false, anchor);
        if (!saved && typeof rmToast === 'function') rmToast(t('error'));
      }
      return opts.checkSaved ? saved : rmGetPrefs(m);
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
      rmSetPrefsCache(rmPrefsMedia(), { ...rmGetPrefs(), [key]: val });
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
        if (data.prefs) rmSetPrefsCache(data.prefs_key || media, data.prefs);
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
