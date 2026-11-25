    const CARET = '<svg class="dd-caret" viewBox="0 0 20 20"><path d="M5.516 7.548a.625.625 0 0 1 .884-.884l3.6 3.6 3.6-3.6a.625.625 0 1 1 .884.884l-4.042 4.042a.625.625 0 0 1-.884 0z"/></svg>';
    function makeDropdown(el, { options, value, icon = '', title = '', onChange, left = false, labelFor }) {
      const cur = options.find(o => o.value === value) || options[0];
      el.classList.add('dd');
      if (left) el.classList.add('left');
      el.innerHTML = `
        <button type="button" class="dd-btn" title="${esc(title)}" aria-haspopup="listbox" aria-expanded="false">
          ${icon ? `<span class="dd-icon">${icon}</span>` : ''}
          <span class="dd-label">${labelFor ? labelFor(cur) : `${cur.pre || ''}${esc(cur.label)}`}</span>${CARET}
        </button>
        <div class="dd-menu" role="listbox">
          ${options.map(o => `<div class="dd-item ${o.value === cur.value ? 'selected' : ''}" role="option" tabindex="-1" aria-selected="${o.value === cur.value}" data-value="${esc(o.value)}">${o.pre || ''}<span>${esc(o.label)}</span></div>`).join('')}
        </div>`;
      const btn = el.querySelector('.dd-btn');
      const items = [...el.querySelectorAll('.dd-item')];
      const setOpen = open => {
        document.querySelectorAll('.dd.open').forEach(d => {
          d.classList.remove('open');
          d.querySelector('.dd-btn')?.setAttribute('aria-expanded', 'false');
        });
        el.classList.toggle('open', open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) {
          el.classList.remove('flip');
          if (el.querySelector('.dd-menu').getBoundingClientRect().left < 0) el.classList.add('flip');
        }
      };
      btn.addEventListener('click', e => {
        e.stopPropagation();
        setOpen(!el.classList.contains('open'));
      });
      btn.addEventListener('keydown', e => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          if (!el.classList.contains('open')) setOpen(true);
          const idx = Math.max(0, items.findIndex(i => i.classList.contains('selected')));
          items[idx]?.focus();
        }
      });
      items.forEach((item, idx) => {
        const pick = () => {
          setOpen(false);
          if (item.dataset.value !== cur.value) onChange(item.dataset.value);
          else btn.focus();
        };
        item.addEventListener('click', e => { e.stopPropagation(); pick(); });
        item.addEventListener('keydown', e => {
          if (e.key === 'ArrowDown') { e.preventDefault(); items[(idx + 1) % items.length]?.focus(); }
          else if (e.key === 'ArrowUp') { e.preventDefault(); items[(idx - 1 + items.length) % items.length]?.focus(); }
          else if (e.key === 'Home') { e.preventDefault(); items[0]?.focus(); }
          else if (e.key === 'End') { e.preventDefault(); items[items.length - 1]?.focus(); }
          else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); }
          else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setOpen(false); btn.focus(); }
        });
      });
    }
    document.addEventListener('click', e => {
      document.querySelectorAll('.dd.open').forEach(d => {
        d.classList.remove('open');
        d.querySelector('.dd-btn')?.setAttribute('aria-expanded', 'false');
      });
      if (!e.target.closest('.topbar')) setMenu(false);
    });

    const LABEL_STAGES = ['c-guide', 'c-settings', 'c-library', 'c-saved', 'c-media', 'c-search'];
    const TAB_ORDER = ['search', 'media', 'saved', 'library', 'settings', 'guide'];
    const SETTINGS = ['shortcuts-btn'];
    const DRAWER_STAGE = LABEL_STAGES.length + 1;
    const TABS_STAGE = DRAWER_STAGE;
    const LAST_STAGE = TABS_STAGE + TAB_ORDER.length;
    let topbarThresholds = [];
    let currentTopbarStage = -1;
    // A touch screen has no keyboard to press ? on: the shortcuts button goes, the Guide keeps one
    const topbarTouch = matchMedia('(hover: none) and (pointer: coarse)');
    const topbarNoShortcuts = () => ON_PHONE || topbarTouch.matches;

    function applyTopbarStage(stage) {
      const bar = document.querySelector('.topbar');
      const tabs = bar.querySelector('.nav-tabs');
      const menu = document.getElementById('topbar-menu');
      const menuTabs = menu.querySelector('.menu-tabs');
      const menuRight = menu.querySelector('.menu-right');
      const right = bar.querySelector(':scope > .topbar-right');
      const noShortcuts = topbarNoShortcuts();
      const settingsIn = noShortcuts || stage < DRAWER_STAGE ? 0 : SETTINGS.length;
      const tabsIn = Math.max(0, stage - TABS_STAGE);
      const inDrawer = [...SETTINGS.slice(0, settingsIn), ...TAB_ORDER.slice(TAB_ORDER.length - tabsIn)];
      // Without the shortcuts button the ☰ comes only once a tab goes into it
      bar.classList.toggle('compact', noShortcuts ? tabsIn > 0 : stage >= DRAWER_STAGE);
      LABEL_STAGES.forEach((c, idx) => {
        let on = idx < stage;
        if (inDrawer.includes(c.slice(2))) on = false;
        bar.classList.toggle(c, on);
      });
      TAB_ORDER.forEach(name => {
        const a = document.querySelector(`.nav-tab[data-tab="${name}"]`);
        if (a) (inDrawer.includes(name) ? menuTabs : tabs).appendChild(a);
      });
      SETTINGS.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.hidden = noShortcuts;
        (inDrawer.includes(id) ? menuRight : right).appendChild(el);
      });
      right.classList.toggle('is-empty', noShortcuts || settingsIn === SETTINGS.length);
      menuRight.classList.toggle('is-empty', noShortcuts || !settingsIn);
    }

    function topbarGap() {
      const bar = document.querySelector('.topbar');
      const last = bar.querySelector('.nav-tabs').lastElementChild;
      if (!last) return Infinity;
      const right = bar.querySelector(':scope > .topbar-right');
      if (!right.classList.contains('is-empty')) return right.getBoundingClientRect().left - last.getBoundingClientRect().right;
      if (bar.classList.contains('compact')) return document.getElementById('menu-btn').getBoundingClientRect().left - last.getBoundingClientRect().right;
      // Nothing after the tabs (a touch screen, no ☰ yet): the bar's own inner edge
      const edge = bar.getBoundingClientRect().right - (parseFloat(getComputedStyle(bar).paddingRight) || 0);
      return edge - last.getBoundingClientRect().right;
    }

    const topbarPhone = matchMedia('(max-width: 720px)');
    let topbarMeasuredPhone = null;
    let topbarMeasuredTouch = null;
    function updateTopbarThresholds() {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      if (bar.getBoundingClientRect().width <= 0) return;
      const hadNoAnim = bar.classList.contains('no-anim');
      bar.classList.add('no-anim');
      const wasSticky = bar.classList.contains('is-sticky');
      bar.classList.remove('is-sticky');
      const thresholds = [];
      for (let s = 0; s < LAST_STAGE; s++) {
        applyTopbarStage(s);
        thresholds.push(Math.ceil(bar.getBoundingClientRect().width - topbarGap() + 8));
      }
      topbarThresholds = thresholds;
      topbarMeasuredPhone = topbarPhone.matches;
      topbarMeasuredTouch = topbarNoShortcuts();
      bar.classList.toggle('is-sticky', wasSticky);
      applyTopbarStage(Math.max(0, currentTopbarStage));
      if (!hadNoAnim) {
        void bar.offsetHeight;
        requestAnimationFrame(() => requestAnimationFrame(() => bar.classList.remove('no-anim')));
      }
    }

    function fitTopbar(measuredWidth) {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      if (!topbarThresholds.length || topbarMeasuredPhone !== topbarPhone.matches || topbarMeasuredTouch !== topbarNoShortcuts()) updateTopbarThresholds();
      const cs = getComputedStyle(bar);
      const stickyOffset = -(parseFloat(cs.marginLeft) + parseFloat(cs.marginRight)) || 0;
      const rawW = measuredWidth !== undefined ? measuredWidth : Math.round(bar.offsetWidth);
      const w = rawW - stickyOffset;

      let stage = 0;
      while (stage < topbarThresholds.length && w < topbarThresholds[stage]) stage++;
      applyTopbarStage(stage);
      while (stage < LAST_STAGE && topbarGap() < 8) applyTopbarStage(++stage);
      if (!bar.classList.contains('compact')) setMenu(false);
      const changed = stage !== currentTopbarStage;
      currentTopbarStage = stage;
      if (changed) fitSidebar();
    }

    document.addEventListener('DOMContentLoaded', () => {
      let lastWidth = -1;
      new ResizeObserver(entries => {
        const bar = entries[0].target;
        const w = entries[0].borderBoxSize ? Math.round(entries[0].borderBoxSize[0].inlineSize) : Math.round(bar.offsetWidth);
        if (w !== lastWidth) {
          lastWidth = w;
          fitTopbar(w);
        }
      }).observe(document.querySelector('.topbar'));
      window.addEventListener('resize', () => fitTopbar());
    });
    if (document.fonts) document.fonts.ready.then(() => { updateTopbarThresholds(); fitTopbar(); });
    window.matchMedia('(max-width: 720px)').addEventListener('change', () => { updateTopbarThresholds(); fitTopbar(); });
    topbarTouch.addEventListener('change', () => { updateTopbarThresholds(); fitTopbar(); });

    document.addEventListener('DOMContentLoaded', () => {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      const sentinel = document.createElement('div');
      sentinel.id = 'topbar-sentinel';
      sentinel.style.cssText = 'height:0;pointer-events:none;';
      bar.parentElement.insertBefore(sentinel, bar);
      new IntersectionObserver(([e]) => {
        const stuck = !e.isIntersecting;
        if (bar.classList.contains('is-sticky') !== stuck) {
          topbarChange(bar, () => bar.classList.toggle('is-sticky', stuck));
          fitTopbar();
          queueDock();
        }
      }, { threshold: 0 }).observe(sentinel);
    });

    function setMenu(open) {
      const bar = document.querySelector('.topbar');
      if (!bar) return;
      bar.classList.toggle('open', open);
      document.getElementById('menu-btn').setAttribute('aria-expanded', open ? 'true' : 'false');
      fitSidebar();
    }
    function toggleMenu(e) {
      e.stopPropagation();
      setMenu(!document.querySelector('.topbar').classList.contains('open'));
    }

    const ICON_ROWS = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>';

    const SORT_ICONS = {
      recommended: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 16v4M17 18h4"/>',
      chrono: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3 2"/><path d="M12 3.5v.5M20.5 12H20M12 20.5V20M3.5 12H4"/>',
      desc: '<path d="M4 6h16M4 12h11M4 18h6"/>',
      asc: '<path d="M4 6h6M4 12h11M4 18h16"/>',
      random: '<path d="M3 7h3c4 0 6 10 10 10h5"/><path d="M3 17h3c1.6 0 2.9-1.6 4-3.5M13.9 9.5C15 8 16.2 7 18 7h3"/><path d="M18.5 4.5L21 7l-2.5 2.5M18.5 14.5L21 17l-2.5 2.5"/>',
    };
    const sortIcon = v => svgIcon(SORT_ICONS[v], 'class="dd-ico" width="16" height="16"');
    function renderTopbarControls() {
      updateTopbarThresholds();
      fitTopbar();
    }

    function renderSearchControls() {
      const seg = document.getElementById('media-seg-side');
      if (seg) {
        seg.innerHTML = MEDIAS.map(m => `<button type="button" class="seg-btn ${m === MEDIA ? 'active' : ''}" data-media="${m}" onclick="setMediaMode('${m}')">${esc(mediaLabel(m))}</button>`).join('');
        seg.hidden = MEDIAS.length === 1;
        seg.classList.toggle('seg-many', MEDIAS.length > 3);
        seg.classList.toggle('seg-five', MEDIAS.length > 4);
      }
      for (const id of ['media-dd-side', 'media-dd-phone']) {
        const dd = document.getElementById(id);
        if (!dd) continue;
        dd.hidden = MEDIAS.length === 1;
        makeDropdown(dd, { options: MEDIAS.map(m => ({ value: m, label: mediaLabel(m) })), value: MEDIA, onChange: setMediaMode });
      }
      updatePhoneTitles();
      const sortEl = document.getElementById('sort-select');
      if (sortEl) {
        makeDropdown(sortEl, {
          options: SORTS.map(v => ({ value: v, label: t('sort_' + v), pre: sortIcon(v) })),
          value: SORT, title: t('sort_title'),
          onChange: v => {
            store.set('sort', v);
            document.getElementById('sort-input').value = v;
            document.querySelector('form.search-bar').submit();
          },
        });
      }
      document.getElementById('sort-input').value = SORT;
      renderLearnControl();
      document.getElementById('media-input').value = MEDIA;
      syncHiddenFolders();
      const qInput = document.querySelector('input[name="q"]');
      qInput.value = PARAMS.get('q') || '';
      const exact = document.getElementById('exact-check');
      exact.checked = PARAMS.get('exact') === 'on';
      const chip = document.getElementById('exact-chip');
      chip.classList.toggle('on', exact.checked);
      exact.addEventListener('change', () => chip.classList.toggle('on', exact.checked));
      const rubyOnly = document.getElementById('ruby-only-check');
      rubyOnly.checked = PARAMS.get('ruby_only') === 'on';
      const rubyChip = document.getElementById('ruby-only-chip');
      rubyChip.classList.toggle('on', rubyOnly.checked);
      rubyOnly.addEventListener('change', () => rubyChip.classList.toggle('on', rubyOnly.checked));
      const multi = document.getElementById('multi-check');
      const multiChip = document.getElementById('multi-chip');
      multi.checked = multiPick;
      multiChip.classList.toggle('on', multiPick);
      multi.addEventListener('change', () => {
        multiPick = multi.checked;
        multiChip.classList.toggle('on', multiPick);
        store.set('multiPick', multiPick ? 'on' : 'off');
        clearPins();
        pinFolders(currentFolders);
        if (!multiPick && currentFolders.length > 1) applyFolders(currentFolders.slice(-1), true);
        if (allResults.length === 0 && PARAMS.get('q')) setEmptyStateForFolders(currentFolders);
        if (multiPick && pinnedFolders.length) sidebarShown = SIDEBAR_PAGE;
        if (sidebarData) { drawSidebar(); revealChosen(); }
        if (multiPick && pinnedFolders.length) { const side = document.querySelector('.sidebar'); if (side) side.scrollTop = 0; }
        renderFilterNote();
        refreshFolderHints();
      });
      document.querySelectorAll('.furi-btn').forEach(b => b.classList.toggle('off', document.documentElement.classList.contains('no-furigana')));
    }

    document.addEventListener("DOMContentLoaded", () => {
      applyI18n();
      renderTopbarControls();
      document.querySelectorAll('.nav-tab').forEach(a => a.classList.toggle('active', a.dataset.tab === TAB));
      document.querySelectorAll('[data-tab-panel]').forEach(p => { p.hidden = p.dataset.tabPanel !== TAB; });

      if (TAB === 'search') {
        store.set('aobana_last_search', window.location.pathname + window.location.search);
        renderSearchControls();
        initFetch();
        pinSearchBox();
        initSidebarTooltip();
        const filter = document.getElementById('folder-filter');
        filter.setAttribute('aria-label', t('filter_folders'));
        filter.addEventListener('input', filterFolders);
        document.querySelector('.sidebar').addEventListener('scroll', e => {
          const s = e.currentTarget;
          if (s.scrollTop + s.clientHeight > s.scrollHeight - 600) moreSidebar();
        }, { passive: true });
        document.getElementById('folder-list-dynamic').addEventListener('click', e => {
          if (e.detail > 1) { e.preventDefault(); return; }
          const link = e.target.closest('.folder-link[data-folder]');
          if (link) setFolder(link.dataset.folder || null, e);
        });
      } else if (TAB === 'saved') {
        initSavedTab();
      } else if (TAB === 'media') {
        const seg = document.getElementById('media-seg');
        seg.innerHTML = MEDIAS.map(m => `<button type="button" class="seg-btn ${m === MEDIA_TAB_FILTER ? 'active' : ''}" data-media="${m}" onclick="setMediaTabFilter('${m}')">${esc(mediaLabel(m))}</button>`).join('');
        seg.hidden = MEDIAS.length === 1;
        document.getElementById('media-filter').addEventListener('input', onMediaFilterInput);
        initMediaTab();
        initSidebarTooltip();
      } else if (TAB === 'library') {
        initLibraryTab();
      } else if (TAB === 'settings') {
        initSettingsTab();
      } else if (TAB === 'guide') {
        initGuideTab();
      }

      if (!MEDIAS_ON.length) showMediaOff();
      if (setupMode() || store.get('welcomed') !== '1') openWelcome();
      else if (!checkWhatsNew()) afterWhatsNew();
    });

    function initSidebarTooltip() {
      const tooltip = document.getElementById('sidebar-tooltip');
      if (!tooltip) return;

      let tooltipTimeout = null;
      let isTooltipActive = false;
      let closeGraceTimeout = null;

      function showTooltip(targetLink, text) {
        tooltip.textContent = text;
        tooltip.style.display = 'block';
        tooltip.style.visibility = 'hidden';

        const rect = targetLink.getBoundingClientRect();
        const tipRect = tooltip.getBoundingClientRect();

        let left = rect.right + 10;
        let top = rect.top + (rect.height - tipRect.height) / 2;

        if (left + tipRect.width > window.innerWidth - 12) {
          left = Math.max(12, Math.min(rect.left, window.innerWidth - tipRect.width - 12));
          top = rect.bottom + 6;
          if (top + tipRect.height > window.innerHeight - 12) {
            top = rect.top - tipRect.height - 6;
          }
        }
        if (top < 12) top = 12;
        if (top + tipRect.height > window.innerHeight - 12) {
          top = window.innerHeight - tipRect.height - 12;
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
        tooltip.style.visibility = 'visible';
        tooltip.classList.add('visible');
        isTooltipActive = true;
      }

      function hideTooltip() {
        clearTimeout(tooltipTimeout);
        tooltip.classList.remove('visible');
        tooltip.style.display = 'none';
      }

      function scheduleHide() {
        clearTimeout(tooltipTimeout);
        hideTooltip();
        clearTimeout(closeGraceTimeout);
        closeGraceTimeout = setTimeout(() => { isTooltipActive = false; }, 200);
      }

      const sidebarEl = document.querySelector('.sidebar');
      if (sidebarEl) {
        sidebarEl.addEventListener('mouseover', (e) => {
          const link = e.target.closest('.folder-link');
          if (!link) { scheduleHide(); return; }
          const span = link.querySelector('.folder-name, span:first-child');
          if (!span) { scheduleHide(); return; }

          if (span.scrollWidth - span.clientWidth > 1) {
            const text = span.textContent.trim();
            clearTimeout(tooltipTimeout);
            clearTimeout(closeGraceTimeout);
            if (isTooltipActive) {
              showTooltip(link, text);
            } else {
              tooltipTimeout = setTimeout(() => { showTooltip(link, text); }, 120);
            }
          } else {
            scheduleHide();
          }
        });

        sidebarEl.addEventListener('mouseout', (e) => {
          const link = e.target.closest('.folder-link');
          if (link) {
            if (e.relatedTarget && link.contains(e.relatedTarget)) return;
            scheduleHide();
          }
        });

        sidebarEl.addEventListener('scroll', () => { hideTooltip(); isTooltipActive = false; }, { passive: true });
      }

      document.addEventListener('mouseover', (e) => {
        const row = e.target.closest('.media-row');
        if (!row) return;
        const el = e.target.closest('.media-name, .media-author');
        if (el && el.scrollWidth - el.clientWidth > 1) {
          clearTimeout(tooltipTimeout);
          clearTimeout(closeGraceTimeout);
          if (isTooltipActive) showTooltip(el, el.textContent.trim());
          else tooltipTimeout = setTimeout(() => { showTooltip(el, el.textContent.trim()); }, 120);
        } else {
          scheduleHide();
        }
      });
      document.addEventListener('mouseout', (e) => {
        const el = e.target.closest('.media-row .media-name, .media-row .media-author');
        if (el && !(e.relatedTarget && el.contains(e.relatedTarget))) scheduleHide();
      });

      window.addEventListener('scroll', () => { hideTooltip(); isTooltipActive = false; }, { passive: true, capture: true });
      document.addEventListener('mousedown', () => { hideTooltip(); isTooltipActive = false; });
    }

    let isComposing = false;
    let justConfirmed = false;
    let activeCardIndex = -1;
    let lastNavTime = 0;

    function getVisibleCards() {
      return Array.from(document.querySelectorAll('#results .card, #results .media-subfolder > summary'))
        .filter(el => !el.closest('[hidden]') && !(el.matches('summary') ? el.parentElement.parentElement : el).closest('details:not([open])'));
    }

    function updateActiveCard(newIndex) {
      const cards = getVisibleCards();
      if (cards.length === 0) return;
      cards.forEach(c => c.classList.remove('keyboard-active'));
      if (newIndex < 0) newIndex = 0;
      if (newIndex >= cards.length) newIndex = cards.length - 1;
      activeCardIndex = newIndex;
      const activeCard = cards[activeCardIndex];
      if (activeCard) {
        activeCard.classList.add('keyboard-active');
        activeCard.scrollIntoView({ behavior: 'auto', block: 'nearest' });
      }
    }

    // Two lists: the app's keys and Reading mode's. It opens on the one in use.
    function showShortcutsTab(name) {
      document.querySelectorAll('#shortcuts-modal [data-sc-tab]').forEach(b => {
        const on = b.dataset.scTab === name;
        b.classList.toggle('active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      document.querySelectorAll('#shortcuts-modal [data-sc-pane]').forEach(p => { p.hidden = p.dataset.scPane !== name; });
    }
    function toggleShortcutsModal() {
      const modal = document.getElementById('shortcuts-modal');
      if (modal) {
        const reading = typeof isReadingModeOpen === 'function' && isReadingModeOpen();
        if (!modal.classList.contains('open')) showShortcutsTab(reading ? 'reader' : 'app');
        const isOpen = modal.classList.toggle('open');
        if (!reading) document.documentElement.style.overflow = isOpen ? 'hidden' : '';
      }
    }

    // An open window keeps the keyboard, as a native modal dialog does: focus moves to the window,
    // Tab and Shift+Tab go round its own controls, and closing it gives focus back to what opened it.
    // The window itself takes focus, not its first button, so Enter never confirms by accident.
    const DIALOG_FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';
    const dialogStack = [];
    const dialogOpeners = new WeakMap();
    const isShown = el => !!el && el.isConnected && el.getClientRects().length > 0;
    function topDialog() {
      for (let i = dialogStack.length - 1; i >= 0; i--) if (dialogStack[i].classList.contains('open')) return dialogStack[i];
      return null;
    }
    function dialogFocusables(m) {
      return [...m.querySelectorAll(DIALOG_FOCUSABLE)].filter(el => !el.closest('[hidden]') && isShown(el));
    }
    function dialogOpened(m) {
      if (dialogStack.includes(m)) return;
      const prev = document.activeElement;
      const under = prev && prev.closest ? prev.closest('.modal-overlay.open') : null;
      dialogOpeners.set(m, {
        el: prev && prev !== document.body && !m.contains(prev) ? prev : null,
        fallback: under && under !== m ? (dialogOpeners.get(under) || {}).el || null : null,
      });
      dialogStack.push(m);
      if (m.contains(document.activeElement)) return;
      const card = m.querySelector('[role="dialog"]') || m;
      if (!card.hasAttribute('tabindex')) card.tabIndex = -1;
      card.focus({ preventScroll: true });
    }
    function dialogClosed(m) {
      const i = dialogStack.indexOf(m);
      if (i < 0) return;
      dialogStack.splice(i, 1);
      const from = dialogOpeners.get(m) || {};
      dialogOpeners.delete(m);
      const active = document.activeElement;
      if (active && active !== document.body && !m.contains(active)) return;
      const back = [from.el, from.fallback].find(isShown);
      if (back) { try { back.focus({ preventScroll: true }); } catch (e) {} }
      else if (active && m.contains(active)) active.blur();
    }
    function trapDialogTab(e) {
      if (e.key !== 'Tab' || e.altKey || e.ctrlKey || e.metaKey) return;
      const m = topDialog();
      if (!m) return;
      const items = dialogFocusables(m);
      const card = m.querySelector('[role="dialog"]') || m;
      const active = document.activeElement;
      if (!items.length) { e.preventDefault(); card.focus({ preventScroll: true }); return; }
      const first = items[0], last = items[items.length - 1];
      const inside = m.contains(active) && active !== card && items.includes(active);
      if (e.shiftKey && (!inside || active === first)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (!inside || active === last)) { e.preventDefault(); first.focus(); }
    }
    document.addEventListener('DOMContentLoaded', () => {
      const watch = new MutationObserver(records => {
        for (const r of records) {
          const m = r.target;
          const open = m.classList.contains('open');
          if (open && !dialogStack.includes(m)) dialogOpened(m);
          else if (!open && dialogStack.includes(m)) dialogClosed(m);
        }
      });
      document.querySelectorAll('.modal-overlay').forEach(m => {
        watch.observe(m, { attributes: true, attributeFilter: ['class'] });
        if (m.classList.contains('open')) dialogOpened(m);
      });
      document.addEventListener('keydown', trapDialogTab, true);
    });

    function handleSearchTabClick(e) {
      if (TAB === 'search') {
        e.preventDefault();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      const last = store.get('aobana_last_search');
      if (last) {
        e.preventDefault();
        window.location.href = last;
      }
    }

    function handleSearchSubmit(e, form) {
      if (isComposing || justConfirmed) {
        if (e && e.preventDefault) e.preventDefault();
        return false;
      }
      const qInput = form.querySelector('input[name="q"]');
      const exactCheck = form.querySelector('input[name="exact"]');
      qInput.value = normalizeQuery(qInput.value);
      let val = qInput.value.trim();
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith('“') && val.endsWith('”')) || (val.startsWith('”') && val.endsWith('”'))) {
        if (val.length > 2) {
          qInput.value = val.substring(1, val.length - 1);
          exactCheck.checked = true;
        }
      }

      const qVal = qInput.value.trim();
      if (qVal) {
        const p = new URLSearchParams();
        p.set('q', qVal);
        if (exactCheck && exactCheck.checked) p.set('exact', 'on');
        const rubyOnlyCheck = form.querySelector('input[name="ruby_only"]');
        if (rubyOnlyCheck && rubyOnlyCheck.checked) p.set('ruby_only', 'on');
        if (SORT) p.set('sort', SORT);
        if (MEDIA && MEDIA !== 'all') p.set('media', MEDIA);
        const learnInput = form.querySelector('#learn-input');
        if (learnInput && !learnInput.disabled) p.set('learn', learnInput.value);
        currentFolders.forEach(f => p.append('folder', f));
        const searchUrl = '/?' + p.toString();
        store.set('aobana_last_search', searchUrl);
      } else {
        cancelServerSearch(1);
        store.del('aobana_last_search');
      }
    }

    document.addEventListener("DOMContentLoaded", () => {
      const qInput = document.querySelector('input[name="q"]');
      if (qInput) {
        qInput.addEventListener('compositionstart', () => {
          isComposing = true;
        });
        qInput.addEventListener('compositionend', () => {
          isComposing = false;
          justConfirmed = true;
          setTimeout(() => { justConfirmed = false; }, 60);
        });
        qInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            if (e.isComposing || e.keyCode === 229 || isComposing || justConfirmed) {
              e.preventDefault();
              return false;
            }
          }
        });
      }
    });

    document.addEventListener('keydown', function(e) {
      if (typeof isReadingModeOpen === 'function' && isReadingModeOpen()) return;
      const activeTag = document.activeElement ? document.activeElement.tagName : '';
      const isInputActive = activeTag === 'INPUT' || activeTag === 'TEXTAREA' || activeTag === 'SELECT';

      if ((e.key === '?' || (e.shiftKey && (e.code === 'Slash' || e.key === '/'))) && !isInputActive && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        toggleShortcutsModal();
        return;
      }

      if (e.key === 'Escape') {
        const modal = document.getElementById('shortcuts-modal');
        if (modal && modal.classList.contains('open')) { toggleShortcutsModal(); return; }
        const welcome = document.getElementById('welcome-modal');
        if (welcome && welcome.classList.contains('open')) { if (!setupMode()) closeWelcome(false); return; }
        const reset = document.getElementById('reset-modal');
        if (reset && reset.classList.contains('open')) { closeReset(false); return; }
        const changelog = document.getElementById('changelog-modal');
        if (changelog && changelog.classList.contains('open')) { closeChangelog(); return; }
        const ankiModal = document.getElementById('anki-modal');
        if (ankiModal && ankiModal.classList.contains('open')) { if (!(e.isComposing || e.keyCode === 229)) closeAnkiDialog(); return; }
        const isOpen = id => { const m = document.getElementById(id); return m && m.classList.contains('open'); };
        if (isOpen('stop-modal')) { closeStop(false); return; }
        if (isOpen('checkfirst-modal')) {
          document.getElementById('checkfirst-modal').classList.remove('open');
          document.documentElement.style.overflow = '';
          return;
        }
        if (isOpen('unsaved-modal')) { closeUnsaved(); return; }
        if (isOpen('whatsnew-modal')) { closeWhatsNew(); return; }
        if (closeGuideToc()) return;
        if (isOpen('reindex-modal')) { closeReindex(false); return; }
        if (isOpen('tables-modal')) { closeTables(false); return; }
        if (isOpen('update-modal')) {
          const later = document.querySelector('#update-modal [onclick="closeUpdate()"]');
          if (later && !later.hidden) closeUpdate();
          return;
        }
        if (document.documentElement.classList.contains('sheet-open') && typeof closeTitleSheet === 'function') { closeTitleSheet(); return; }
        document.querySelectorAll('.dd.open').forEach(d => {
          d.classList.remove('open');
          d.querySelector('.dd-btn')?.setAttribute('aria-expanded', 'false');
        });
        setMenu(false);
      }

      if (e.ctrlKey || e.altKey || e.metaKey) {
        return;
      }

      if ((e.key === 'q' || e.key === 'Q' || e.code === 'KeyQ') && !isInputActive && !e.shiftKey) {
        const qInput = [document.querySelector('input[name="q"]'), document.getElementById('media-detail-q'), document.getElementById('media-detail-filter'), document.getElementById('media-filter'), document.getElementById('media-q')].find(el => el && el.offsetParent !== null);
        if (qInput) {
          e.preventDefault();
          qInput.focus();
          qInput.select();
        }
        return;
      }

      if (!isInputActive) {
        // Behind an open window the cards take no keys
        if (topDialog()) return;

        if ((e.key === 'f' || e.key === 'F') && !e.shiftKey) {
          e.preventDefault();
          toggleFurigana();
          return;
        }

        const now = Date.now();
        const isNavKey = ((e.key === 'a' || e.key === 'A') && !e.shiftKey) || e.key === 'ArrowUp' ||
                         ((e.key === 'd' || e.key === 'D') && !e.shiftKey) || e.key === 'ArrowDown';
        if (isNavKey && e.repeat && (now - lastNavTime < 65)) {
          e.preventDefault();
          return;
        }

        if (((e.key === 'd' || e.key === 'D') && !e.shiftKey) || e.key === 'ArrowDown') {
          const cards = getVisibleCards();
          if (cards.length) {
            e.preventDefault();
            lastNavTime = now;
            updateActiveCard(activeCardIndex + 1);
          }
        } else if (((e.key === 'a' || e.key === 'A') && !e.shiftKey) || e.key === 'ArrowUp') {
          const cards = getVisibleCards();
          if (cards.length) {
            e.preventDefault();
            lastNavTime = now;
            updateActiveCard(activeCardIndex - 1);
          }
        } else if ((e.key === 'c' || e.key === 'C') && !e.shiftKey) {
          const cards = getVisibleCards();
          if (activeCardIndex >= 0 && activeCardIndex < cards.length) {
            const card = cards[activeCardIndex];
            const ctxBtn = card.querySelector('button[onclick*="toggleContext"]');
            if (ctxBtn) { e.preventDefault(); ctxBtn.click(); }
            const epHeader = card.querySelector('.episode-header');
            if (epHeader) { e.preventDefault(); epHeader.click(); }
            if (card.matches('.media-subfolder > summary')) { e.preventDefault(); card.click(); }
          }
        } else if ((e.key === 's' || e.key === 'S') && !e.shiftKey) {
          const cards = getVisibleCards();
          if (activeCardIndex >= 0 && activeCardIndex < cards.length) {
            const card = cards[activeCardIndex];
            const starBtn = card.querySelector('button[onclick*="toggleSave"]');
            if (starBtn) { e.preventDefault(); starBtn.click(); }
          }
        } else if (e.key === 'Enter' && !e.shiftKey && !e.repeat) {
          // The card D and A picked opens in Media at its line; a folder row opens or shuts.
          // A focused button or link keeps its own Enter.
          const focused = document.activeElement;
          if (focused && focused !== document.body && focused.closest('a[href], button, summary, [tabindex]')) return;
          const cards = getVisibleCards();
          const card = cards[activeCardIndex];
          if (!card || !card.classList.contains('keyboard-active')) return;
          if (card.matches('.media-subfolder > summary')) { e.preventDefault(); card.click(); return; }
          const open = card.querySelector('button[onclick^="openInMedia"]');
          if (open && !open.disabled) { e.preventDefault(); open.click(); }
        }
      }
    });
