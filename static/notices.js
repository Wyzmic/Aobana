    let activityTimer = null;
    let activityPolling = false;
    let activityAgain = false;
    let activityBusy = false;
    const ACTIVITY_WAKE_KEY = 'aobana_activity_wake';
    function wakeOtherTabs() {
      try { localStorage.setItem(ACTIVITY_WAKE_KEY, `${Date.now()}:${Math.random()}`); } catch (e) {}
    }
    async function pollActivity() {
      if (activityPolling) { activityAgain = true; return; }
      activityPolling = true;
      clearTimeout(activityTimer);
      let a = null;
      try { a = await fetch('/api/activity').then(r => r.json()); } catch (e) {}
      if (a) renderNotices(a.notices || []);
      if (a) {
        const wasBusy = activityBusy;
        activityBusy = !!(a.index || a.check || a.figures);
        if (activityBusy && !wasBusy) wakeOtherTabs();
      }
      activityPolling = false;
      if (activityBusy || activityAgain) activityTimer = setTimeout(pollActivity, 1000);
      activityAgain = false;
    }
    function noticeText(n) {
      const state = n.error ? '_error' : (n.stopped ? '_stopped' : '');
      return t(`notice_${n.kind}${n.kind === 'figures' ? '' : state}`, { time: fmtDuration(n.seconds) });
    }
    function renderNotices(list) {
      const box = document.getElementById('task-notices');
      const html = list.map(n => `<div class="task-notice${n.error ? ' warn' : ''}" role="status">
          <span>${esc(noticeText(n))}</span>
          <button class="btn" type="button" onclick="dismissNotice(${Number(n.id)}, this)">${esc(t('close'))}</button>
        </div>`).join('');
      if (box.dataset.html === html) return;
      box.dataset.html = html;
      box.innerHTML = html;
    }
    async function dismissNotice(id, btn) {
      btn.closest('.task-notice').remove();
      delete document.getElementById('task-notices').dataset.html;
      const result = await apiPost('/api/activity/dismiss', { id }).catch(() => null);
      if (result) wakeOtherTabs();
    }
    document.addEventListener('DOMContentLoaded', pollActivity);
    window.addEventListener('focus', pollActivity);
    window.addEventListener('storage', e => { if (e.key === ACTIVITY_WAKE_KEY) pollActivity(); });

    function openWelcome() {
      const m = document.getElementById('welcome-modal');
      document.getElementById('welcome-btns').hidden = setupMode();
      document.getElementById('welcome-setup-btns').hidden = !setupMode();
      document.getElementById('welcome-s0').hidden = !setupMode();
      const s1 = document.getElementById('welcome-s1');
      s1.dataset.i18nHtml = setupMode() ? 'welcome_s1_setup' : 'welcome_s1';
      s1.innerHTML = t(s1.dataset.i18nHtml);
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }

    function setupMode() { return MEDIA_BOOT.setup || store.get('setup_again') === '1'; }
    const setupState = MEDIA_BOOT.setup ? { subs: true, books: true, manga: false, custom: false } : { ...MEDIA_BOOT.on };
    function openSetupStep() {
      const card = document.getElementById('welcome-card');
      card.style.minHeight = card.offsetHeight + 'px';
      document.getElementById('welcome-pane').hidden = true;
      document.getElementById('setup-step').hidden = false;
      renderSetupRows();
    }
    function backToWelcome() {
      document.getElementById('setup-step').hidden = true;
      document.getElementById('welcome-pane').hidden = false;
    }
    function renderSetupRows() {
      const defaults = MEDIA_BOOT.defaults || {};
      const box = document.getElementById('setup-rows');
      const kept = {};
      box.querySelectorAll('input[data-which]').forEach(i => kept[i.dataset.which] = i.value);
      box.innerHTML = MEDIA_KINDS.map(which => `<div class="set-media-row">
          <div class="btns set-media-head">
            <strong>${esc(t('set_media_' + which))}</strong>
            <div class="seg seg-fit">
              <button type="button" class="seg-btn ${setupState[which] ? '' : 'active'}" onclick="setSetupOn('${which}', false)">${esc(t('lib_cache_off'))}</button>
              <button type="button" class="seg-btn ${setupState[which] ? 'active' : ''}" onclick="setSetupOn('${which}', true)">${esc(t('lib_cache_on'))}</button>
            </div>
          </div>
          <div class="btns" ${setupState[which] ? '' : 'hidden'}>
            <input type="text" data-which="${which}" value="${esc(kept[which] ?? (MEDIA_BOOT.folders || {})[which] ?? defaults[which] ?? '')}" spellcheck="false" style="flex:1; min-width:0;">
            ${MEDIA_BOOT.picker ? `<button class="btn" onclick="setupBrowse('${which}')">${esc(t('setup_browse'))}</button>` : ''}
          </div>
        </div>`).join('');
    }
    function setSetupOn(which, on) {
      setupState[which] = on;
      renderSetupRows();
    }
    async function setupBrowse(which) {
      const input = document.querySelector(`#setup-rows input[data-which="${which}"]`);
      const msg = document.getElementById('setup-msg');
      msg.textContent = t('lib_picking');
      const res = await apiPost('/api/library/pick', { which, title: t('set_media_' + which) })
        .catch(() => ({ status: 'unavailable' }));
      msg.textContent = '';
      if (res.status === 'ok') input.value = res.path;
    }
    function setupError(error) {
      if (error === 'busy') return t('lib_err_busy');
      if (error === 'none_on') return t('setup_pick_one');
      if (error.startsWith('overlap:')) return overlapText(error);
      const which = MEDIA_KINDS.find(k => error.endsWith(k + '_dir')) || 'subs';
      if (error.startsWith('not_full')) return t('lib_err_notfull', { path: (MEDIA_BOOT.defaults || {})[which] || '' });
      return t('setup_err_make');
    }
    async function finishSetup(goGuide) {
      const msg = document.getElementById('setup-msg');
      if (!MEDIA_KINDS.some(k => setupState[k])) { msg.textContent = t('setup_pick_one'); return; }
      const val = which => (document.querySelector(`#setup-rows input[data-which="${which}"]`) || {}).value || '';
      const btns = document.querySelectorAll('#setup-step .setup-finish');
      btns.forEach(b => b.disabled = true);
      const res = await apiPost('/api/setup', { media: setupState, subs_dir: val('subs'), books_dir: val('books'), manga_dir: val('manga'), custom_dir: val('custom') })
        .catch(() => ({ error: 'network' }));
      btns.forEach(b => b.disabled = false);
      if (res.error) {
        msg.innerHTML = `<span class="warn">${esc(setupError(res.error))}</span>`;
        return;
      }
      store.set('welcomed', '1');
      store.set('reindex_told', APP_VERSION);
      store.set('seen_version', APP_VERSION);
      store.del('setup_again');
      window.location.href = goGuide ? '/?tab=guide' : '/?tab=library';
    }
    function closeWelcome(goGuide) {
      store.set('welcomed', '1');
      store.set('reindex_told', APP_VERSION);
      store.set('seen_version', APP_VERSION);
      document.getElementById('welcome-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (goGuide) window.location.href = '/?tab=guide';
      else checkForUpdate();
    }

    async function checkReindex() {
      let lib = null;
      try { lib = await fetch('/api/library/outdated').then(r => r.json()); } catch (e) {}
      // An index run holds a database: asked again at the next start, the version not marked told
      if (lib && lib.busy) { checkForUpdate(); return; }
      const outdated = lib ? outdatedMedia(lib) : [];
      if (store.get('reindex_told') !== APP_VERSION) {
        store.set('reindex_told', APP_VERSION);
        if (outdated.length) {
          const m = document.getElementById('reindex-modal');
          const media = MEDIA_ON.subs && (lib.subs_tables || []).includes('source_ranges');
          m.querySelector('#reindex-body').innerHTML = t('reindex_body') + (media ? ' ' + t('reindex_media') : '');
          m.classList.add('open');
          document.documentElement.style.overflow = 'hidden';
          return;
        }
      }
      const tables = lib ? [['subs', lib.subs_tables], ['epub', lib.books_tables], ['manga', lib.manga_tables], ['custom', lib.custom_tables]]
        .flatMap(([kind, missing]) => MEDIA_ON[kind] ? (missing || []).filter(m => m === 'repeats' || (m === 'kanji' && kind !== 'custom')) : []) : [];
      if (tables.length && !outdated.length && store.get('tables_told') !== APP_VERSION) {
        store.set('tables_told', APP_VERSION);
        document.getElementById('tables-body').innerHTML = t('tables_body', { why: tablesWhy(tables) });
        document.getElementById('tables-modal').classList.add('open');
        document.documentElement.style.overflow = 'hidden';
        return;
      }
      checkForUpdate();
    }
    function closeReindex(goLibrary) {
      document.getElementById('reindex-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (goLibrary) window.location.href = '/?tab=library';
      else checkForUpdate();
    }
    function closeTables(goLibrary) {
      document.getElementById('tables-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (goLibrary) window.location.href = '/?tab=library&focus=optimize';
      else checkForUpdate();
    }


    async function checkForUpdate() {
      const boot = (document.querySelector('meta[name="aobana-boot"]') || {}).content || '';
      if (store.get('update_seen') === boot) return;
      for (let i = 0; i < 10; i++) {
        let info;
        try { info = await (await fetch('/api/update')).json(); } catch (e) { return; }
        if (info.checked) {
          store.set('update_seen', boot);
          if (info.newer && store.get('update_skip') !== info.latest) openUpdate(info);
          return;
        }
        await new Promise(r => setTimeout(r, 1500));
      }
    }
    let updateInfo = null;
    function openUpdate(info) {
      updateInfo = info;
      const m = document.getElementById('update-modal');
      m.querySelector('#update-body').innerHTML = t('update_body', { current: esc(info.current), latest: esc(info.latest) });
      m.querySelector('#update-link').href = info.url;
      if (info.termux) {
        m.querySelector('#update-more').textContent = t(info.self_update ? 'update_more_self' : 'update_more_termux');
        m.querySelector('#update-cmd-text').textContent = info.install_cmd || '';
        m.querySelector('#update-cmd').hidden = !!info.self_update;
        m.querySelector('#update-link').hidden = true;
        m.querySelector('#update-now').hidden = !info.self_update;
      } else if (info.auto) {
        m.querySelector('#update-auto').hidden = false;
        m.querySelector('#update-more').textContent = t('update_more_auto');
        m.querySelector('#update-link').classList.remove('primary');
      }
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }
    function closeUpdate() {
      document.getElementById('update-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
    }
    function skipUpdate() {
      if (updateInfo) store.set('update_skip', updateInfo.latest);
      closeUpdate();
    }
    async function copyUpdateCmd(btn) {
      const text = document.getElementById('update-cmd-text').textContent;
      try { await navigator.clipboard.writeText(text); }
      catch (e) {
        const r = document.createRange(); r.selectNodeContents(document.getElementById('update-cmd-text'));
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
        let ok = false;
        try { ok = document.execCommand('copy'); } catch (e2) {}
        if (!ok) return;
      }
      btn.textContent = t('update_copied');
    }
    async function applyUpdate() {
      const m = document.getElementById('update-modal');
      const from = updateInfo && updateInfo.current;
      try {
        const r = await fetch('/api/update/apply', { method: 'POST', headers: { 'X-Aobana': '1' } });
        if (!r.ok) return;
      } catch (e) { return; }
      m.querySelector('#update-more').textContent = t('update_running');
      m.querySelectorAll('.btns .btn').forEach(b => { b.hidden = true; });
      for (;;) {
        await new Promise(r => setTimeout(r, 3000));
        try {
          const info = await (await fetch('/api/update', { cache: 'no-store' })).json();
          if (info.current !== from) { location.reload(); return; }
        } catch (e) {}
      }
    }

    async function applyAutoUpdate() {
      const m = document.getElementById('update-modal');
      const more = m.querySelector('#update-more'), bar = m.querySelector('#update-progress');
      const from = updateInfo && updateInfo.current;
      const failed = () => {
        bar.hidden = true;
        more.textContent = t('update_failed');
        m.querySelectorAll('.btns .btn').forEach(b => { b.hidden = true; });
        const link = m.querySelector('#update-link');
        link.hidden = false;
        link.classList.add('primary');
      };
      const res = await apiPost('/api/update/apply', { lang: LANG }).catch(() => ({ error: 'network' }));
      if (res.error) return failed();
      m.querySelectorAll('.btns .btn').forEach(b => { b.hidden = true; });
      bar.hidden = false; bar.value = 0;
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      for (;;) {
        await sleep(400);
        let s;
        try { s = await (await fetch('/api/update/status', { cache: 'no-store' })).json(); } catch (e) { break; }
        if (s.state === 'error') return failed();
        if (s.state === 'installing') break;
        const pct = s.total ? Math.min(100, Math.floor(s.done * 100 / s.total)) : 0;
        bar.value = pct;
        more.textContent = t('update_downloading', { pct });
      }
      bar.hidden = true;
      more.textContent = t('update_installing') + (navigator.platform.startsWith('Win') ? ' ' + t('update_installing_admin') : '');
      let wentDown = false;
      for (;;) {
        await sleep(2000);
        try {
          const info = await (await fetch('/api/update?waiting=1', { cache: 'no-store' })).json();
          if (info.current !== from) { location.reload(); return; }
          if (wentDown) return failed();
        } catch (e) { wentDown = true; }
      }
    }

    const APP_VERSION = (document.querySelector('meta[name="aobana-version"]') || {}).content || '';
    function checkWhatsNew() {
      if (!APP_VERSION || store.get('seen_version') === APP_VERSION) return false;
      store.set('seen_version', APP_VERSION);
      openWhatsNew();
      return true;
    }
    function mdInline(s) {
      return esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '$1');
    }
    async function openWhatsNew() {
      const m = document.getElementById('whatsnew-modal');
      m.querySelector('#whatsnew-title').textContent = t('whatsnew_title', { version: APP_VERSION });
      m.querySelector('#whatsnew-sub').hidden = true;
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
      let notes = null;
      try { notes = await (await fetch('/api/release-notes')).json(); } catch (e) {}
      const items = (notes && notes.notable) || [];
      m.querySelector('#whatsnew-list').innerHTML = items.map(s => `<li>${mdInline(s)}</li>`).join('');
      m.querySelector('#whatsnew-sub').hidden = !items.length;
      m.querySelector('#whatsnew-none').hidden = !!items.length;
      if (notes && notes.url) m.querySelector('#whatsnew-more').href = notes.url;
    }
    function mdChangelog(text) {
      const out = []; let item = null, para = null;
      const flush = () => {
        if (item !== null) { out.push(`<li>${mdInline(item)}</li>`); item = null; }
        if (para !== null) { out.push(`<p>${mdInline(para)}</p>`); para = null; }
      };
      let inList = false;
      for (const line of text.split(/\r?\n/)) {
        const h = line.match(/^(#{1,3})\s+(.*)$/);
        if (h) { flush(); if (inList) { out.push('</ul>'); inList = false; }
                 if (h[1].length > 1) out.push(`<h3 class="whatsnew-sub">${mdInline(h[2])}</h3>`); continue; }
        if (line.startsWith('- ')) { flush(); if (!inList) { out.push('<ul class="whatsnew-list">'); inList = true; }
                                     item = line.slice(2).trim(); continue; }
        if (!line.trim()) { flush(); continue; }
        if (item !== null) item += ' ' + line.trim();
        else { if (inList) { out.push('</ul>'); inList = false; } para = (para ? para + ' ' : '') + line.trim(); }
      }
      flush(); if (inList) out.push('</ul>');
      return out.join('');
    }
    async function openChangelog() {
      const m = document.getElementById('changelog-modal');
      m.querySelector('#changelog-body').innerHTML = '';
      m.querySelector('#changelog-lang').hidden = !t('changelog_lang');
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
      let data = null;
      try { data = await (await fetch('/api/changelog')).json(); } catch (e) {}
      m.querySelector('#changelog-body').innerHTML = data && data.text
        ? mdChangelog(data.text) : `<p>${esc(t('changelog_none'))}</p>`;
      if (data && data.url) m.querySelector('#changelog-more').href = data.url;
    }
    function closeChangelog() {
      document.getElementById('changelog-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
    }
    function closeWhatsNew() {
      document.getElementById('whatsnew-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      afterWhatsNew();
    }
    function afterWhatsNew() {
      checkReindex();
    }

