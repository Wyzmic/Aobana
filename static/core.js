    const PAGE_BOOT = (document.querySelector('meta[name="aobana-boot"]') || {}).content || '';
    const RUN_KEYS = new Set(['aobana_last_search', 'aobana_last_media']);
    const store = {
      get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
      set(k, v) {
        if (RUN_KEYS.has(k) && PAGE_BOOT && store.get('aobana_boot') !== PAGE_BOOT) return;
        try { localStorage.setItem(k, v); } catch (e) {}
      },
      del(k) { try { localStorage.removeItem(k); } catch (e) {} },
    };
    (function () {
      const boot = PAGE_BOOT;
      if (boot && store.get('aobana_boot') !== boot) {
        store.del('aobana_last_search');
        store.del('aobana_last_media');
        store.set('aobana_boot', boot);
      }
    })();
    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    }
    function fmt(n) { return Number(n || 0).toLocaleString(LANG === 'ja' ? 'ja-JP' : 'en-US'); }
    if (document.getAnimations) {
      let animSync = 0;
      new MutationObserver(() => {
        if (animSync) return;
        animSync = requestAnimationFrame(() => {
          animSync = 0;
          for (const a of document.getAnimations()) {
            if (a.startTime !== 0 && 'animationName' in a && a.effect && a.effect.getTiming().iterations === Infinity) a.startTime = 0;
          }
        });
      }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden'] });
    }
    const ON_PHONE = (document.querySelector('meta[name="aobana-termux"]') || {}).content === '1';

    const LIST_CAP = 100;
    function capList(list, total = list.length) {
      return list.slice(0, LIST_CAP).map(f => `<li>${esc(f)}</li>`).join('')
        + (total > LIST_CAP ? `<li>${esc(t('list_more', { n: fmt(total - LIST_CAP) }))}</li>` : '');
    }
    const svgIcon = (paths, attrs = 'aria-hidden="true"') =>
      `<svg ${attrs} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

    let LANG = document.documentElement.getAttribute('lang') === 'en' ? 'en' : 'ja';
    function t(key, vars) {
      let s = (I18N[LANG] && I18N[LANG][key]) ?? I18N.ja[key] ?? key;
      if (vars) s = s.replace(/\{(\w+)\|([^|}]*)\|([^}]*)\}/g, (m, k, one, many) =>
        k in vars ? (Number(String(vars[k]).replace(/[^\d.-]/g, '')) === 1 ? one : many) : m);
      if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(v);
      return s;
    }
    function applyI18n(root = document) {
      root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
      root.querySelectorAll('[data-i18n-html]').forEach(el => { el.innerHTML = t(el.dataset.i18nHtml); });
      root.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
      root.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
      root.querySelectorAll('[data-i18n-aria]').forEach(el => { el.setAttribute('aria-label', t(el.dataset.i18nAria)); });
    }

    const LABEL_CONTROLS = '.brand, .nav-tab, .seg-btn, .dd-btn, .dd-item, .exact-chip, .sq-btn, .btn, .icon-btn, '
      + '.search-btn, .reveal-btn, .path-back, .modal-close, .menu-btn, .sidebar-more, .media-kind, summary, label[for], '
      + '.rm-topbar-title, .rm-drawer-head, .rm-set-label, .rm-range-val, .rm-footer, .rm-toc-group, .rm-toc-item, '
      + '.rm-bm-where, .rm-toast, .rm-sub-ts';
    function hideLabelText(node) {
      const parent = node.parentElement;
      if (!parent || !node.data.trim() || parent.closest('svg, style, script, textarea')) return;
      const span = document.createElement('span');
      span.className = 'lbl';
      span.dataset.label = node.data;
      node.replaceWith(span);
    }
    function hideLabels(root) {
      const controls = root.matches?.(LABEL_CONTROLS) ? [root] : [];
      controls.push(...(root.querySelectorAll?.(LABEL_CONTROLS) || []));
      for (const el of controls) {
        const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        const texts = [];
        while (walk.nextNode()) texts.push(walk.currentNode);
        texts.forEach(hideLabelText);
      }
    }
    function labelText(el) {
      return [...el.querySelectorAll('.lbl')].map(s => s.dataset.label).join('') || el.textContent;
    }
    function startHidingLabels() {
      hideLabels(document.body);
      new MutationObserver(records => {
        for (const r of records) {
          if (r.type === 'characterData') {
            if (r.target.parentElement?.closest(LABEL_CONTROLS)) hideLabelText(r.target);
            continue;
          }
          for (const n of r.addedNodes) {
            if (n.nodeType === 3) { if (n.parentElement?.closest(LABEL_CONTROLS)) hideLabelText(n); }
            else if (n.nodeType === 1) {
              if (n.parentElement?.closest(LABEL_CONTROLS)) hideLabels(n.parentElement.closest(LABEL_CONTROLS));
              else hideLabels(n);
            }
          }
        }
      }).observe(document.body, { childList: true, subtree: true, characterData: true });
    }
    if (document.body) startHidingLabels();
    else document.addEventListener('DOMContentLoaded', startHidingLabels);

    // Keep a closing fold from pulling text above it down under the finger when scrollTop clamps
    // at the bottom, and shield the tap point briefly if a control itself disappears on tap.
    const FOLD_SPACERS = new WeakMap();
    function isWindowScroller(sc) {
      return !sc || sc === document.scrollingElement || sc === document.documentElement || sc === document.body;
    }
    function findFoldScroller(el, existingOnly) {
      for (let p = el && el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
        if (FOLD_SPACERS.has(p)) return p;
        if (existingOnly) continue;
        const st = getComputedStyle(p);
        if ((st.overflowY === 'auto' || st.overflowY === 'scroll' || st.overflowY === 'overlay') && p.scrollHeight > p.clientHeight + 1) {
          return p;
        }
      }
      const root = document.scrollingElement || document.documentElement;
      if (existingOnly) return FOLD_SPACERS.has(root) ? root : null;
      return root;
    }
    function getFoldScrollPos(sc) {
      return isWindowScroller(sc) ? window.scrollY : sc.scrollTop;
    }
    function setFoldScrollPos(sc, top) {
      if (isWindowScroller(sc)) window.scrollTo({ top, behavior: 'instant' });
      else sc.scrollTop = top;
    }
    function reclaimFoldSpacer(sc) {
      if (!sc) return;
      const state = FOLD_SPACERS.get(sc);
      if (!state || state.extra <= 0) return;
      if (!state.el.isConnected) { state.extra = 0; return; }
      const curScroll = getFoldScrollPos(sc);
      if (curScroll <= 0) {
        state.el.remove();
        state.extra = 0;
        return;
      }
      const clientH = isWindowScroller(sc) ? window.innerHeight : sc.clientHeight;
      const maxNow = Math.max(0, sc.scrollHeight - clientH);
      const slack = Math.floor(maxNow - curScroll);
      if (slack > 0) {
        state.extra = Math.max(0, state.extra - slack);
        if (state.extra <= 0) { state.el.remove(); state.extra = 0; }
        else state.el.style.height = state.extra + 'px';
      }
    }
    function setFoldSpacer(sc, height) {
      let state = FOLD_SPACERS.get(sc);
      if (!state) {
        const el = document.createElement('div');
        el.className = 'fold-scroll-spacer';
        el.setAttribute('aria-hidden', 'true');
        el.setAttribute('data-rm-ui', '1');
        el.style.cssText = 'height:0;flex-shrink:0;pointer-events:none;';
        state = { el, extra: 0 };
        FOLD_SPACERS.set(sc, state);
        (isWindowScroller(sc) ? window : sc).addEventListener('scroll', () => reclaimFoldSpacer(sc), { passive: true });
      }
      const host = isWindowScroller(sc) ? document.body : sc;
      if (!host) return;
      if (!state.el.isConnected) { state.extra = 0; host.appendChild(state.el); }
      const next = Math.max(0, Math.ceil(height));
      state.extra = next;
      if (next <= 0) state.el.remove();
      else state.el.style.height = next + 'px';
    }
    function anchorFoldClose(e) {
      if (e.defaultPrevented) return;
      const summary = e.target && e.target.closest && e.target.closest('summary');
      if (!summary) return;
      const details = summary.parentElement;
      if (!details || details.tagName !== 'DETAILS' || details.querySelector(':scope > summary') !== summary) return;
      const innerBtn = e.target.closest('button, a, input, select, textarea');
      if (innerBtn && summary.contains(innerBtn)) return;
      if (!details.open) return;
      if (details.closest('.rm-paginated')) return;
      const sc = findFoldScroller(details, false);
      if (!sc || getComputedStyle(sc).writingMode.startsWith('vertical')) return;
      const beforeScroll = getFoldScrollPos(sc);
      const beforeTop = summary.getBoundingClientRect().top;
      const beforeDetH = details.getBoundingClientRect().height;
      e.preventDefault();
      details.open = false;
      const dy = summary.getBoundingClientRect().top - beforeTop;
      if (dy > 0.5) {
        const prevState = FOLD_SPACERS.get(sc);
        const curExtra = prevState && prevState.el.isConnected ? prevState.extra : 0;
        const collapsed = Math.max(dy, beforeDetH - details.getBoundingClientRect().height);
        setFoldSpacer(sc, curExtra + collapsed);
        setFoldScrollPos(sc, beforeScroll);
        reclaimFoldSpacer(sc);
      }
    }
    let tapShieldEl = null;
    let tapShieldTimer = null;
    let lastControlTap = null;
    function clearTapShield() {
      if (tapShieldTimer) { clearTimeout(tapShieldTimer); tapShieldTimer = null; }
      if (tapShieldEl) { tapShieldEl.remove(); tapShieldEl = null; }
    }
    function shieldTapPoint(x, y) {
      if (!document.body || !Number.isFinite(x) || !Number.isFinite(y) || (x === 0 && y === 0)) return;
      clearTapShield();
      const el = document.createElement('div');
      el.className = 'tap-shield';
      el.setAttribute('aria-hidden', 'true');
      el.setAttribute('data-rm-ui', '1');
      el.style.cssText = `position:fixed;left:${Math.round(x - 24)}px;top:${Math.round(y - 24)}px;width:48px;height:48px;z-index:2147483640;background:rgba(0,0,0,0.01);`;
      document.body.appendChild(el);
      tapShieldEl = el;
      tapShieldTimer = setTimeout(clearTapShield, 160);
    }
    function shieldLastControlTap() {
      if (lastControlTap && performance.now() - lastControlTap.at < 200) {
        shieldTapPoint(lastControlTap.x, lastControlTap.y);
      }
    }
    function maybeShieldDisappearedControl(hit) {
      if (!hit || hit.done) return;
      hit.done = true;
      if (hit.x < 0 || hit.y < 0 || hit.x >= window.innerWidth || hit.y >= window.innerHeight) return;
      const top = document.elementFromPoint(hit.x, hit.y);
      if (!top || (!hit.ctrl.contains(top) && !top.closest(LABEL_CONTROLS))) {
        shieldTapPoint(hit.x, hit.y);
      }
    }
    let activeControlClick = null;
    document.addEventListener('pointerdown', clearTapShield, true);
    document.addEventListener('mousedown', e => {
      if (e.detail > 1 && e.target && e.target.closest) {
        const hdr = e.target.closest('summary, .episode-header');
        if (hdr) {
          const inner = e.target.closest('button, a, input, select, textarea');
          if (!inner || !hdr.contains(inner)) e.preventDefault();
        }
      }
    });
    document.addEventListener('click', e => {
      const hdr = e.target && e.target.closest && e.target.closest('summary, .episode-header');
      if (!hdr) return;
      const sel = window.getSelection && window.getSelection();
      if (sel && !sel.isCollapsed && !(hdr.contains(sel.anchorNode) && hdr.contains(sel.focusNode))) {
        sel.removeAllRanges();
      }
    }, true);
    document.addEventListener('click', e => {
      const ctrl = e.target && e.target.closest && e.target.closest(LABEL_CONTROLS);
      if (ctrl && (e.clientX || e.clientY)) {
        const hit = { ctrl, x: e.clientX, y: e.clientY, at: performance.now(), done: false };
        activeControlClick = hit;
        lastControlTap = hit;
        queueMicrotask(() => maybeShieldDisappearedControl(hit));
      } else {
        activeControlClick = null;
      }
    }, true);
    document.addEventListener('click', e => {
      anchorFoldClose(e);
      const hit = activeControlClick;
      activeControlClick = null;
      maybeShieldDisappearedControl(hit);
    });
    document.addEventListener('toggle', e => {
      if (e.target && e.target.tagName === 'DETAILS' && e.target.open) {
        reclaimFoldSpacer(findFoldScroller(e.target, true));
      }
    }, true);
    function setLang(lang) {
      store.set('lang', lang);
      location.reload();
    }
    document.documentElement.style.setProperty('--no-more', JSON.stringify(t('no_more')));

    // Settings, General: a light theme and a dark theme, and which to use: the device's light or
    // dark, or always one. The device's choice reaches the page through the browser
    // (prefers-color-scheme), so a browser set to light or dark on its own wins over the system.
    // index.html paints the same.
    // In each pair the tinted theme comes first, as shown in Settings; Paper and Night are the defaults.
    const THEMES = ['haze', 'paper', 'night', 'midnight'];
    const THEMES_LIGHT = ['haze', 'paper'];
    const THEMES_DARK = ['night', 'midnight'];
    // Each theme's page colour, for the phone browser's bar (meta theme-color).
    const THEME_COLORS = { paper: '#f7f7f5', haze: '#e4eaf1', night: '#181a1b', midnight: '#000000' };
    function currentTheme() { return document.documentElement.getAttribute('data-theme') || 'night'; }
    function deviceScheme() {
      return (window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark';
    }
    function themeChoice() {
      const mode = store.get('theme_mode'), light = store.get('theme_light'), dark = store.get('theme_dark');
      return {
        mode: ['device', 'light', 'dark'].includes(mode) ? mode : 'device',
        light: THEMES_LIGHT.includes(light) ? light : 'paper',
        dark: THEMES_DARK.includes(dark) ? dark : 'night',
      };
    }
    function themeFor(choice) {
      const side = choice.mode === 'device' ? deviceScheme() : choice.mode;
      return side === 'light' ? choice.light : choice.dark;
    }
    function applyTheme(name) {
      document.documentElement.setAttribute('data-theme', name);
      updateThemeColorMeta();
      if (typeof isReadingModeOpen === 'function' && isReadingModeOpen()) rmApplyPrefsToDom(false, false);
    }
    function syncTheme() {
      const name = themeFor(themeChoice());
      store.set('theme', name);
      if (name !== currentTheme()) applyTheme(name);
      if (store.get('accent') === 'device') applyAccent();
    }
    // key: theme_mode (device, light or dark), theme_light or theme_dark.
    function setThemeChoice(key, value) {
      store.set(key, value);
      syncTheme();
    }
    // The accent colour, over every theme (app.css, Accent). 'default' is the themes' own blue;
    // the colour is the dot shown beside each name.
    const ACCENTS = [['default', '#2b72e7'], ['device', 'AccentColor'], ['cyan', '#217b97'], ['teal', '#0d7f79'],
      ['green', '#2b8a3e'], ['indigo', '#6863e5'], ['purple', '#6f42c1'], ['pink', '#c2255c'], ['red', '#c92a2a'],
      ['orange', '#c2540a'], ['gold', '#8b6b1a'], ['gray', '#4f5b69']];
    const ACCENT_VARS = ['--ac-h', '--ac-k', '--ac-c1', '--ac-c2', '--ac-c3', '--ac-c4', '--ac-c5', '--ac-c6'];
    // The themes' strong colours by band of lightness: [OKLCH L, hue offset from the blue]
    // (app.css, Accent), to cap the device's accent where sRGB runs out at its hue.
    const ACCENT_BANDS = {
      c1: [[0.435, 1], [0.474, 0], [0.477, 1]],
      c2: [[0.505, 0], [0.516, 0], [0.533, -10], [0.536, 0], [0.558, 0], [0.569, -2], [0.575, 0], [0.586, -8]],
      c3: [[0.647, -2]],
      c4: [[0.723, -2], [0.755, -22], [0.795, -11]],
      c5: [[0.816, 1], [0.863, -9], [0.876, -34]],
      c6: [[0.82, 0]],
    };
    // The system's accent colour reaches a page only as CSS AccentColor: Firefox and Safari give
    // it; Chrome and Edge keep it off on every system, Android too, and a Chrome that knows the
    // word answers its own fixed blue, #0075ff (Chrome 156 on a Mac), which is not the device's.
    const ACCENT_FIXED = 'rgb(0, 117, 255)';
    function deviceAccentRgb() {
      if (!(window.CSS && CSS.supports && CSS.supports('color', 'AccentColor')) || !document.body) return null;
      const probe = document.createElement('span');
      probe.style.cssText = 'display:none;color:AccentColor';
      document.body.appendChild(probe);
      const color = getComputedStyle(probe).color;
      probe.remove();
      const m = (color.match(/[\d.]+/g) || []).map(Number);
      return color === ACCENT_FIXED || m.length < 3 ? null : m;
    }
    function deviceAccentSupported() {
      return !!deviceAccentRgb();
    }
    function rgbToOklch(r, g, b) {
      const lin = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
      const [R, G, B] = [lin(r), lin(g), lin(b)];
      const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
      const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
      const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
      const a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
      const bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
      return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, Math.hypot(a, bb), (Math.atan2(bb, a) * 180 / Math.PI + 360) % 360];
    }
    function oklchInSrgb(L, C, h) {
      const a = C * Math.cos(h * Math.PI / 180), b = C * Math.sin(h * Math.PI / 180);
      const l = Math.pow(L + 0.3963377774 * a + 0.2158037573 * b, 3);
      const m = Math.pow(L - 0.1055613458 * a - 0.0638541728 * b, 3);
      const s = Math.pow(L - 0.0894841775 * a - 1.2914855480 * b, 3);
      return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s].every(x => x >= -1e-4 && x <= 1 + 1e-4);
    }
    function oklchMaxChroma(L, h) {
      let lo = 0, hi = 0.4;
      for (let i = 0; i < 24; i++) { const mid = (lo + hi) / 2; if (oklchInSrgb(L, mid, h)) lo = mid; else hi = mid; }
      return lo;
    }
    function deviceAccentVars() {
      const m = deviceAccentRgb();
      if (!m) return null;
      const [, C, h] = rgbToOklch(m[0], m[1], m[2]);
      // A grey accent tints as Gray does.
      const grey = C < 0.04;
      const vars = { '--ac-h': h.toFixed(1), '--ac-k': grey ? '0.35' : '1' };
      for (const [band, pts] of Object.entries(ACCENT_BANDS)) {
        let cap = Math.min(...pts.map(([l, off]) => oklchMaxChroma(l, h + off))) - 0.002;
        if (grey) cap = Math.min(cap, 0.033);
        vars['--ac-' + band] = cap.toFixed(3);
      }
      return vars;
    }
    function currentAccent() {
      const v = store.get('accent');
      if (v === 'device') return deviceAccentSupported() ? v : 'default';
      return ACCENTS.some(([name]) => name === v) ? v : 'default';
    }
    function applyAccent() {
      const root = document.documentElement;
      let name = currentAccent();
      ACCENT_VARS.forEach(v => root.style.removeProperty(v));
      if (name === 'device') {
        const vars = deviceAccentVars();
        if (vars) {
          Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v));
          store.set('accent_device', JSON.stringify(vars));
        } else name = 'default';
      }
      if (name === 'default') root.removeAttribute('data-accent');
      else root.setAttribute('data-accent', name);
      updateThemeColorMeta();
    }
    function setAccent(value) {
      if (value === 'default') store.del('accent');
      else store.set('accent', value);
      applyAccent();
    }
    // The phone browser's bar takes the page's background, the accent's tint included.
    function updateThemeColorMeta() {
      const bar = document.querySelector('meta[name="theme-color"]');
      if (!bar) return;
      let color = THEME_COLORS[currentTheme()] || THEME_COLORS.night;
      if (document.documentElement.hasAttribute('data-accent')) {
        try {
          const ctx = document.createElement('canvas').getContext('2d');
          ctx.fillStyle = '#010203';
          ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--bg-body').trim();
          if (ctx.fillStyle !== '#010203') {
            ctx.fillRect(0, 0, 1, 1);
            const d = ctx.getImageData(0, 0, 1, 1).data;
            color = '#' + [d[0], d[1], d[2]].map(x => x.toString(16).padStart(2, '0')).join('');
          }
        } catch (e) {}
      }
      bar.setAttribute('content', color);
      updateFavicon();
    }
    // The tab's icon is the bar's icon in the accent's colours: aobana.svg when no accent is set,
    // else the icon on the page with its colours written in, as a data: URL.
    function updateFavicon() {
      const link = document.querySelector('link[rel="icon"]');
      const icon = document.getElementById('brand-icon');
      if (!link || !icon) return;
      if (!link.dataset.plain) link.dataset.plain = link.getAttribute('href');
      if (!document.documentElement.hasAttribute('data-accent')) {
        if (link.getAttribute('href') !== link.dataset.plain) link.setAttribute('href', link.dataset.plain);
        return;
      }
      try {
        const ctx = document.createElement('canvas').getContext('2d');
        const hex = c => {
          ctx.clearRect(0, 0, 1, 1);
          ctx.fillStyle = '#000000';
          ctx.fillStyle = c;
          ctx.fillRect(0, 0, 1, 1);
          const d = ctx.getImageData(0, 0, 1, 1).data;
          return '#' + [d[0], d[1], d[2]].map(x => x.toString(16).padStart(2, '0')).join('');
        };
        const svg = icon.cloneNode(true);
        ['class', 'id', 'aria-hidden'].forEach(a => svg.removeAttribute(a));
        svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        const live = icon.querySelectorAll('[class]');
        svg.querySelectorAll('[class]').forEach((el, i) => {
          const cs = getComputedStyle(live[i]);
          if (el.classList.contains('ic-stalk')) el.setAttribute('stroke', hex(cs.stroke));
          else el.setAttribute('fill', hex(cs.fill));
          el.removeAttribute('class');
        });
        link.setAttribute('href', 'data:image/svg+xml,' + encodeURIComponent(new XMLSerializer().serializeToString(svg)));
      } catch (e) {}
    }
    // Checked again when the page comes back: a switch while it was hidden may not fire 'change'.
    if (window.matchMedia) {
      const mq = matchMedia('(prefers-color-scheme: light)');
      if (mq.addEventListener) mq.addEventListener('change', syncTheme);
      else if (mq.addListener) mq.addListener(syncTheme);
    }
    window.addEventListener('focus', syncTheme);
    window.addEventListener('pageshow', syncTheme);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) syncTheme(); });
    if (document.body) applyAccent();
    else document.addEventListener('DOMContentLoaded', applyAccent);
    // Chrome on Android can answer AccentColor with another colour for a while after the page
    // opens, until the first tap. The device's accent is asked again a few times, and at the first
    // touch or key.
    function recheckDeviceAccent() { if (store.get('accent') === 'device') applyAccent(); }
    window.addEventListener('load', () => [300, 1000, 3000].forEach(ms => setTimeout(recheckDeviceAccent, ms)));
    ['pointerdown', 'keydown', 'scroll'].forEach(type =>
      window.addEventListener(type, recheckDeviceAccent, { once: true, passive: true, capture: true }));

    const PARAMS = new URLSearchParams(window.location.search);
    const TAB = PARAMS.get('view') === 'saved' ? 'saved'
              : ['search', 'saved', 'media', 'library', 'settings', 'guide'].includes(PARAMS.get('tab')) ? PARAMS.get('tab') : 'search';
    const SORTS = ['recommended', 'chrono', 'desc', 'asc', 'random'];
    const MEDIA_BOOT = (() => {
      try { return JSON.parse(document.getElementById('aobana-media').textContent); }
      catch (e) { return { on: { subs: true, books: true }, setup: false }; }
    })();
    const MEDIA_ON = { subs: !!MEDIA_BOOT.on.subs, epub: !!MEDIA_BOOT.on.books, manga: !!MEDIA_BOOT.on.manga, custom: !!MEDIA_BOOT.on.custom };
    const MEDIAS_ALL = ['all', 'subs', 'epub', 'manga', 'custom'];
    const MEDIAS_ON = MEDIAS_ALL.slice(1).filter(m => MEDIA_ON[m]);
    const MEDIAS = MEDIAS_ON.length > 1 ? ['all', ...MEDIAS_ON] : MEDIAS_ON.length ? MEDIAS_ON : ['all'];
    function mediaLabel(m) {
      return t(m === 'all' ? (MEDIAS_ON.length === 2 ? 'media_both' : 'media_all') : 'media_' + m);
    }
    const SORT = SORTS.includes(PARAMS.get('sort')) ? PARAMS.get('sort')
               : (SORTS.includes(store.get('sort')) ? store.get('sort') : 'recommended');
    const MEDIA = MEDIAS.includes(PARAMS.get('media')) ? PARAMS.get('media')
                : (MEDIAS.includes(store.get('media')) ? store.get('media') : MEDIAS[0]);
    let KNOWN = (() => {
      try { return JSON.parse(document.getElementById('aobana-known-words').textContent); }
      catch (e) { return { available: false, sources: [] }; }
    })();
    const LEARNS = ['off', 'first', 'only'];
    const LEARN = !KNOWN.available ? 'off' : LEARNS.includes(PARAMS.get('learn')) ? PARAMS.get('learn')
                : (LEARNS.includes(store.get('learn')) ? store.get('learn') : 'off');
    let currentFolders = TAB === 'search' ? PARAMS.getAll('folder').filter(Boolean) : [];
    let pinnedFolders = [];
    try { pinnedFolders = JSON.parse(sessionStorage.getItem('pinnedFolders') || '[]'); } catch (e) {}
    if (!Array.isArray(pinnedFolders)) pinnedFolders = [];
    let multiPick = store.get('multiPick') === 'on';
    function clearPins() {
      pinnedFolders = [];
      try { sessionStorage.removeItem('pinnedFolders'); } catch (e) {}
    }
    function unpinFolder(f) {
      pinnedFolders = pinnedFolders.filter(p => p !== f);
      try { sessionStorage.setItem('pinnedFolders', JSON.stringify(pinnedFolders)); } catch (e) {}
    }
    function pinFolders(list) {
      if (!multiPick) return;
      const before = pinnedFolders.length;
      for (const f of list) if (f && !pinnedFolders.includes(f)) pinnedFolders.push(f);
      if (pinnedFolders.length !== before) {
        try { sessionStorage.setItem('pinnedFolders', JSON.stringify(pinnedFolders)); } catch (e) {}
      }
    }
    if (TAB === 'search') pinFolders(currentFolders);
    function searchParams() {
      const p = new URLSearchParams(window.location.search);
      p.delete('tab');
      p.set('sort', SORT);
      p.set('media', MEDIA);
      if (LEARN !== 'off') p.set('learn', LEARN);
      else p.delete('learn');
      p.delete('pin');
      pinnedFolders.forEach(f => p.append('pin', f));
      return p;
    }

    let allResults = [];
    let observer;
    const BATCH_SIZE = 25;
    function lineId(line) {
      return btoa(unescape(encodeURIComponent(line)));
    }

    const RUBY_HTML_TAGS = {
      ruby: ['alpha'], rt: [], rp: [], rb: [], mark: ['hl-guess'], b: ['hl-guess'], br: [],
      span: ['hl-tail', 'hl-tail-p'], div: ['spacer'],
    };
    // A subtitle's （…） with words after it in its line is a speaker tag (Aobana Reibun's rule): wrapped
    // so Settings can hide it. A line that is only tags, （笑い声）, keeps them; ruby is never a tag
    const SUB_TAG_RE = /（[^（）]*）/g;
    function markSubTags(html) {
      if (typeof html !== 'string' || !html.includes('（')) return html;
      const doc = new DOMParser().parseFromString(`<!doctype html><body>${html}`, 'text/html');
      const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      let changed = false;
      for (const node of nodes) {
        if (!node.data.includes('（') || node.parentElement.closest('ruby, rt')) continue;
        const block = node.parentElement.closest('div, p') || doc.body;
        const parts = [];
        let last = 0;
        for (const m of node.data.matchAll(SUB_TAG_RE)) {
          const range = doc.createRange();
          range.setStart(node, m.index + m[0].length);
          range.setEndAfter(block.lastChild);
          if (!range.toString().replace(SUB_TAG_RE, '').trim()) continue;
          parts.push(doc.createTextNode(node.data.slice(last, m.index)));
          const span = doc.createElement('span');
          span.className = 'sub-tag';
          span.textContent = m[0];
          parts.push(span);
          last = m.index + m[0].length;
        }
        if (!parts.length) continue;
        parts.push(doc.createTextNode(node.data.slice(last)));
        node.replaceWith(...parts);
        changed = true;
      }
      return changed ? doc.body.innerHTML : html;
    }
    const RUBY_HTML_DROP = new Set(['script', 'style', 'template', 'noscript', 'iframe', 'object', 'embed',
      'svg', 'math', 'textarea', 'title', 'xmp', 'noembed', 'noframes', 'select', 'head']);
    const RUBY_HTML_ESC = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;'};
    function sanitizeRubyHtml(html) {
      if (typeof html !== 'string' || !html) return '';
      const doc = new DOMParser().parseFromString(`<!doctype html><body>${html}`, 'text/html');
      const walk = node => {
        let out = '';
        for (const n of node.childNodes) {
          if (n.nodeType === Node.TEXT_NODE) {
            out += n.data.replace(/[&<>"']/g, c => RUBY_HTML_ESC[c]);
          } else if (n.nodeType === Node.ELEMENT_NODE) {
            const tag = n.localName;
            if (RUBY_HTML_DROP.has(tag)) continue;
            const classes = Object.prototype.hasOwnProperty.call(RUBY_HTML_TAGS, tag) ? RUBY_HTML_TAGS[tag] : null;
            const cls = n.getAttribute('class');
            const keep = classes && (tag === 'span' || tag === 'div' ? classes.includes(cls) : true);
            if (!keep) { out += walk(n); continue; }
            if (tag === 'br') { out += '<br>'; continue; }
            const attr = cls && classes.includes(cls) ? ` class="${cls}"` : '';
            out += `<${tag}${attr}>${walk(n)}</${tag}>`;
          }
        }
        return out;
      };
      return walk(doc.body);
    }

    const FAV_TEXT = new Set(['id', 'legacy_id', 'line', 'file', 'media_type', 'title', 'folder', 'original_q',
      'readings', 'base_forms', 'clean_text']);
    const FAV_INT = new Set(['rowid', 'page', 'char_count']);
    const FAV_HTML = new Set(['display_line', 'context']);
    function cleanFavorite(s) {
      if (!s || typeof s !== 'object' || typeof s.line !== 'string') return null;
      const out = {};
      for (const k of Object.keys(s)) {
        const v = s[k];
        if (FAV_TEXT.has(k)) {
          if (typeof v === 'string') out[k] = v;
        } else if (FAV_INT.has(k)) {
          const n = typeof v === 'number' ? v : parseInt(v, 10);
          if (Number.isSafeInteger(n)) out[k] = n;
        } else if (k === 'score') {
          const n = Number(v);
          if (Number.isFinite(n)) out[k] = n;
        } else if (FAV_HTML.has(k)) {
          if (typeof v === 'string') out[k] = sanitizeRubyHtml(v);
        }
      }
      return out;
    }

    function loadSavedSentences() {
      let raw, list;
      try {
        raw = localStorage.getItem('savedSentences');
        list = JSON.parse(raw || '[]');
      } catch (e) {
        console.error('savedSentences unreadable, left as is:', e);
        return [];
      }
      if (!Array.isArray(list)) return [];
      const seen = new Set();
      const out = [];
      let changed = false;
      for (const orig of list) {
        const s = cleanFavorite(orig);
        if (!s) { changed = true; continue; }
        if (JSON.stringify(s) !== JSON.stringify(orig)) changed = true;
        const id = lineId(s.line);
        if (seen.has(id)) { changed = true; continue; }
        seen.add(id);
        if (s.id !== id) {
          if (s.legacy_id === undefined && typeof orig.id === 'string') s.legacy_id = orig.id;
          s.id = id;
          changed = true;
        }
        out.push(s);
      }
      if (changed) {
        try {
          if (localStorage.getItem('savedSentences_backup_v1') === null) {
            localStorage.setItem('savedSentences_backup_v1', raw);
          }
          localStorage.setItem('savedSentences', JSON.stringify(out));
        } catch (e) {
          console.error('savedSentences re-key not saved:', e);
        }
      }
      return out;
    }

    let savedSentences = loadSavedSentences();

    const searchSeed = (() => {
      const fresh = Math.floor(Math.random() * 2147483647);
      if (TAB !== 'search') return fresh;
      const p = new URLSearchParams(window.location.search);
      const url = [p.get('q') || '', p.get('sort') || 'recommended', p.get('media') || 'all',
                   p.get('exact') || '', p.getAll('folder').join('\u0001'), p.get('ruby_only') || ''].join('\u0000');
      try {
        const last = JSON.parse(sessionStorage.getItem('aobana_seed') || 'null');
        if (last && last.url === url) return last.seed;
        sessionStorage.setItem('aobana_seed', JSON.stringify({ url, seed: fresh }));
      } catch (e) {}
      return fresh;
    })();
    const clientToken = (() => {
      try {
        let tok = sessionStorage.getItem('subsClient');
        if (!tok) {
          tok = Math.random().toString(36).slice(2) + Date.now().toString(36);
          sessionStorage.setItem('subsClient', tok);
        }
        return tok;
      } catch (e) {
        return 'tab-' + Math.random().toString(36).slice(2);
      }
    })();
    function apiSearchUrl(qs) {
      return `/api/search?${qs}&seed=${searchSeed}&client=${encodeURIComponent(clientToken)}`;
    }
    const API_HEADERS = { 'X-Aobana': '1' };
    function apiPost(url, body) {
      return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...API_HEADERS }, body: JSON.stringify(body || {}) })
        .then(r => r.json());
    }
    let serverSearchInFlight = 0;
    function cancelServerSearch(grace) {
      if (serverSearchInFlight <= 0) return;
      serverSearchInFlight = 0;
      try {
        fetch(`/api/search/cancel?client=${encodeURIComponent(clientToken)}`, {
          method: 'POST', keepalive: true,
          headers: { 'Content-Type': 'application/json', ...API_HEADERS },
          body: JSON.stringify({ grace: grace || 0 }),
        }).catch(() => {});
      } catch (e) {}
    }
    window.addEventListener('pagehide', () => {
      if (TAB !== 'search') cancelServerSearch(1);
    });

    let currentSearchController = null;
    let currentOffset = 0;
    let isFetchingMore = false;
    let hasMoreResults = true;
    let loadMoreObserver = null;
    let searchGen = 0;
    let outsideMedia = new Set();

    function choiceOutsideMedia() {
      return !multiPick && currentFolders.length > 0 && currentFolders.every(f => outsideMedia.has(f));
    }

    function setEmptyStateForFolders(folders) {
      const empty = document.getElementById('empty-state');
      if (!empty) return;
      if (onlyExcludes(PARAMS.get('q') || '')) {
        empty.dataset.i18n = 'no_results_only_excluded';
        empty.textContent = t('no_results_only_excluded');
      } else if (folders.length && folders.every(f => outsideMedia.has(f))) {
        empty.dataset.i18n = 'no_results_outside_media';
        empty.textContent = t('no_results_outside_media', { n: folders.length });
      } else if (folders.length) {
        empty.dataset.i18n = 'no_results_chosen';
        empty.textContent = t('no_results_chosen');
      } else {
        empty.dataset.i18n = 'no_results';
        empty.textContent = t('no_results');
      }
    }
    function busyLine(pad) {
      return `<div class="status-line" style="padding:${pad};">${esc(t('search_busy'))}</div>`;
    }
    async function busyAnswer(res) {
      if (!res || res.status !== 503) return false;
      try { return !!(await res.clone().json()).busy; } catch (e) { return false; }
    }

    let epSentinelObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const sentinel = entry.target;
                const fileEnc = sentinel.dataset.file;
                const offset = parseInt(sentinel.dataset.offset, 10);
                epSentinelObserver.unobserve(sentinel);
                setTimeout(() => {
                    loadMoreEpisodeSentinel(sentinel, fileEnc, offset);
                }, 100);
            }
        });
    }, { rootMargin: '500px 0px 500px 0px' });
    const epUpObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => { if (entry.isIntersecting) loadEarlierLines(entry.target); });
    }, { rootMargin: '400px 0px 400px 0px' });

    function setTitle(part) {
      document.title = part ? `${part} | ${t('app')}` : t('app');
    }

    // A Delete that asks: the confirming Delete takes the place of the one pressed. When the row
    // grows (Cancel added) and wraps, its other buttons hide while it asks.
    function askRect(btn) {
      if (!btn || !btn.getBoundingClientRect) return null;
      const r = btn.getBoundingClientRect();
      return { right: r.right, top: r.top };
    }
    function keepAskInPlace(row, from) {
      const yes = row && row.querySelector('.btn.primary');
      if (!yes || !from) return;
      const r = yes.getBoundingClientRect();
      if (Math.abs(r.right - from.right) > 2 || Math.abs(r.top - from.top) > 2) row.classList.add('asking-tight');
    }

    // Scrolls item fully into view inside strip only, never moving the page.
    function scrollStripTo(strip, item) {
      if (!strip || !item || strip.scrollWidth <= strip.clientWidth) return;
      const sr = strip.getBoundingClientRect();
      const ir = item.getBoundingClientRect();
      if (ir.width <= 0 || sr.width <= 0) return;
      const pad = 8;
      const max = Math.max(0, strip.scrollWidth - strip.clientWidth);
      if (ir.left < sr.left + pad) {
        strip.scrollLeft = Math.max(0, strip.scrollLeft + (ir.left - sr.left) - pad);
      } else if (ir.right > sr.right - pad) {
        strip.scrollLeft = Math.min(max, strip.scrollLeft + (ir.right - sr.right) + pad);
      }
    }

    function bindTabStripKeys(strip, onPick) {
      if (!strip || strip.dataset.stripKeys) return;
      strip.dataset.stripKeys = '1';
      strip.addEventListener('keydown', e => {
        const tabs = [...strip.querySelectorAll('[role="tab"]:not([disabled])')];
        const i = tabs.indexOf(document.activeElement);
        if (i < 0 || tabs.length < 2) return;
        let next = -1;
        if (e.key === 'ArrowRight') next = (i + 1) % tabs.length;
        else if (e.key === 'ArrowLeft') next = (i - 1 + tabs.length) % tabs.length;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = tabs.length - 1;
        if (next < 0) return;
        e.preventDefault();
        const key = tabs[next].dataset.tabKey;
        if (key) onPick(key, true);
      });
    }

