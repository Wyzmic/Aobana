    let libPoll = null;
    let libLast = null;
    let tableRunStartedHere = false;
    let optimizeDoneThisVisit = false;
    let indexRunning = false;
    let anActing = false;
    let libLoading = false, libUpdating = false;
    let libStarting = false;
    function libBusy() { return indexRunning || anRunning || anActing || libLoading || libUpdating || libStarting; }
    function setLibStarting(on) { libStarting = on; syncRunButtons(); }
    async function anAct(work) {
      if (anActing) return;
      const pressed = (window.event?.target || document.activeElement)?.closest?.('#lib-analyse button');
      const spin = pressed && Object.assign(document.createElement('span'), { className: 'spinner an-busy' });
      if (spin) { spin.setAttribute('aria-hidden', 'true'); pressed.after(spin); }
      anActing = true; syncRunButtons();
      try { return await work(); } finally { spin?.remove(); anActing = false; syncRunButtons(); }
    }
    function syncRunButtons() {
      const run = document.getElementById('lib-run');
      const optimize = document.getElementById('lib-optimize');
      const check = document.getElementById('an-run');
      if (run) run.disabled = libBusy() || !MEDIAS_ON.length;
      if (optimize) optimize.disabled = libBusy() || optimizeDoneThisVisit;
      if (check) check.disabled = libBusy() || nothingToCheck();
      document.querySelectorAll('#an-report [data-run-lock]').forEach(b => { b.disabled = libBusy(); });
      anSaveButton();
    }
    let figPoll = null;

    function pollFigures() {
      if (figPoll) return;
      const poll = async () => {
        let f;
        try { f = await fetch('/api/library/figures').then(r => r.json()); } catch (e) { figPoll = setTimeout(poll, 1000); return; }
        if (!libLast || TAB !== 'library') { figPoll = null; return; }
        Object.assign(libLast, f);
        for (const [which, disk, indexed, path] of [['subs', f.subs_disk, libLast.subs_indexed, libLast.subs_dir],
                                                    ['books', f.books_disk, libLast.books_indexed, libLast.books_dir],
                                                    ['manga', f.manga_disk, libLast.manga_indexed, libLast.manga_dir],
                                                    ['custom', f.custom_disk, libLast.custom_indexed, libLast.custom_dir]]) {
          const box = document.querySelector(`#lib-card-${which} .lib-facts`);
          if (box) box.innerHTML = folderFacts(which, path, disk, indexed, f.counting);
        }
        if (!f.counting) { figPoll = null; pollActivity(); }
        else figPoll = setTimeout(poll, 1000);
      };
      figPoll = setTimeout(poll, 1000);
    }

    function anLoading(key) {
      const el = document.getElementById('an-loading');
      if (!el) return;
      el.hidden = !key;
      if (key) updateIndexBody(el, `<span class="spinner" aria-hidden="true"></span>${esc(t(key))}`);
      libLoading = !!key; syncRunButtons();
    }
    async function initLibraryTab() {
      setTitle(t('tab_library'));
      anLoading('lib_updating');
      await refreshLibrary();
      if (location.hash === '#lib-workers') document.getElementById('lib-workers').scrollIntoView({ block: 'start' });
      loadAnalysis();
    }

    async function runIndex() {
      if (!MEDIAS_ON.length) return;
      const only = libScope();
      if (only === 'manga') {
        document.getElementById('lib-note').hidden = true;
        document.getElementById('lib-estimate').innerHTML = '';
        return startIndex(only);
      }
      if (!MEDIA_BOOT.check_asked && only !== 'custom') {
        MEDIA_BOOT.check_asked = true;
        let d = null;
        try { d = await fetch('/api/library/analysis?status=1').then(r => r.json()); } catch (e) {}
        apiPost('/api/library/check-asked', {}).catch(() => {});
        if (d && !d.check_asked && !(d.status && d.status.running)) {
          document.getElementById('checkfirst-modal').classList.add('open');
          document.documentElement.style.overflow = 'hidden';
          return;
        }
      }
      document.getElementById('lib-note').hidden = true;
      const box = document.getElementById('lib-estimate');
      setLibStarting(true);
      box.innerHTML = `<div class="notice">${esc(t('lib_estimating'))}</div>`;
      const est = await fetch('/api/library/estimate' + (only ? `?only=${only}` : '')).then(r => r.json()).catch(() => null);
      const media = (est && est.media) || {};
      const newFiles = Object.entries(media).reduce((a, [k, m]) => a + (MEDIA_ON[k] ? m.new_files || 0 : 0), 0);
      if (!est || est.error || !newFiles) { box.innerHTML = ''; return startIndex(only); }
      box.innerHTML = renderEstimate(est, only);
    }

    let stopKind = null;
    function askStop(kind, outdated) {
      stopKind = kind;
      const m = document.getElementById('stop-modal');
      m.querySelector('h2').textContent = t(kind === 'index' ? 'stop_index_title' : 'stop_check_title');
      m.querySelector('p').textContent = t(kind === 'check' ? 'stop_check_body' : outdated ? 'stop_index_outdated' : 'stop_index_body');
      m.classList.add('open');
      document.documentElement.style.overflow = 'hidden';
    }
    async function closeStop(stop) {
      document.getElementById('stop-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (!stop || !stopKind) return;
      const res = await apiPost(stopKind === 'index' ? '/api/index/stop' : '/api/library/analyse/stop').catch(() => null);
      if (res && stopKind === 'index') renderIndexStatus(res);
      else if (res) renderAnalysisStatus(res);
    }

    function closeCheckFirst(check) {
      document.getElementById('checkfirst-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      if (!check) return runIndex();
      document.getElementById('lib-analyse').scrollIntoView({ behavior: 'smooth', block: 'start' });
      runAnalysis();
    }

    function fmtDuration(s) {
      if (s < 60) return t('est_sec');
      const m = Math.round(s / 60);
      return m < 60 ? t('est_min', { n: m }) : t('est_hour', { h: Math.floor(m / 60), m: m % 60 });
    }

    function libScope() {
      return MEDIAS_ON.length === 1 ? MEDIAS_ON[0] : '';
    }

    function syncMediaOn(state) {
      if (!state) return;
      MEDIA_ON.subs = !!state.subs; MEDIA_ON.epub = !!state.books; MEDIA_ON.manga = !!state.manga; MEDIA_ON.custom = !!state.custom;
      MEDIAS_ON.splice(0, MEDIAS_ON.length, ...MEDIAS_ALL.slice(1).filter(m => MEDIA_ON[m]));
      const off = list => list.filter(m => !MEDIA_ON[m]).map(m => t('lib_stage_' + m)).join(LANG === 'ja' ? '・' : ', ');
      const list = off(['subs', 'epub', 'manga', 'custom']);
      for (const id of ['lib-media-off', 'an-media-off']) {
        const el = document.getElementById(id);
        if (!el) continue;
        el.textContent = list ? t('lib_media_off', { list }) : '';
        el.hidden = !list;
      }
    }

    function renderEstimate(est, only) {
      let rows = '';
      let short = null;
      const EST_MEDIA = { subs: ['subs.db', 'subs_outdated'], epub: ['epub.db', 'books_outdated'], manga: ['manga.db', 'manga_outdated'], custom: ['custom.db', 'custom_outdated'] };
      for (const [k, [name, outdatedKey]] of Object.entries(EST_MEDIA)) {
        const m = est.media[k];
        if (!m || !MEDIA_ON[k] || (only && k !== only)) continue;
        const reread = libLast ? libLast[outdatedKey] : 0;
        if (!m.new_files && !m.pending_removals && !reread && !m.tables?.length) continue;
        rows += `<div>${esc(t('lib_stage_' + k))}</div><div class="num">${esc(t('est_new', { n: fmt(m.new_files) }))}</div>`;
        if (m.pending_removals) rows += `<div></div><div>${esc(t('est_removals', { n: fmt(m.pending_removals) }))}</div>`;
        if (reread) rows += `<div></div><div>${esc(t('est_reread', { n: fmt(reread) }))}</div>`;
        if (m.tables?.length) rows += `<div></div><div>${esc(t('est_tables'))}</div>`;
        rows += `<div></div><div class="num">${esc(t('est_db', { name, now: fmtBytes(m.db_now), after: fmtBytes(m.db_now + m.db_add) }))}</div>`;
        if (m.disk_free != null && m.db_add > m.disk_free) short = m.disk_free;
      }
      rows += `<div></div><div class="num"><b>${esc(t('est_total', { n: fmtBytes(est.total_bytes) }))}</b></div>`;
      rows += `<div></div><div class="num"><b>${esc(t(est.duration_unknown ? 'est_time_new' : 'est_time', { t: fmtDuration(Math.max(60, est.seconds)), w: est.workers }))}</b></div>`;
      if (est.duration_unknown) rows += `<div></div><div class="an-note">${esc(t('est_extra_work'))}</div>`;
      const warn = est.warn ? `<div class="notice warn">${esc(t('est_warn'))}</div>` : '';
      const disk = short != null ? `<div class="notice warn">${esc(t('est_disk', { free: fmtBytes(short) }))}</div>` : '';
      return `<div class="notice ${est.warn ? 'warn' : ''}">
        <b>${esc(t('est_title'))}</b>
        <div class="estimate-grid">${rows}</div>
        ${warn}${disk}
        <div style="color:var(--text-muted); font-size:0.9em;">${esc(t('est_note'))}</div>
        <div class="btns" style="display:flex; gap:0.5em; margin-top:0.6em;">
          <button class="btn primary" onclick="startIndex('${only}')">${esc(t('est_start'))}</button>
          <button class="btn" onclick="cancelEstimate()">${esc(t('est_cancel'))}</button>
        </div></div>`;
    }

    function cancelEstimate() {
      document.getElementById('lib-estimate').innerHTML = '';
      setLibStarting(false);
    }

    async function startIndex(only, outdated, tables, allowRemoval) {
      document.getElementById('lib-estimate').innerHTML = '';
      setLibStarting(true);
      if (tables) {
        tableRunStartedHere = true;
        document.getElementById('lib-optimize').disabled = true;
      } else document.getElementById('lib-outdated').hidden = true;
      const body = only ? { only } : {};
      if (outdated) body.outdated = true;
      if (tables) body.tables = true;
      if (allowRemoval) body.allow_removal = true;
      const res = await apiPost('/api/index', body).catch(() => null);
      if (!res || !res.started) setLibStarting(false);
      if (res && res.nothing) {
        tableRunStartedHere = false;
        const note = document.getElementById('lib-note');
        note.textContent = t('lib_nothing'); note.className = 'notice warn'; note.hidden = false;
        refreshLibrary();
        return;
      }
      if (!res || !res.started) { tableRunStartedHere = false; refreshLibrary(); return; }
      if (res) renderIndexStatus(res);
      startPolling();
      pollActivity();
    }

    let anPoll = null;
    const AN_ORDER = ['encoding', 'duplicate','garbled', 'language_review', 'bilingual', 'other_language', 'no_japanese', 'empty_or_wall', 'image_only', 'drm', 'unreadable', 'unsupported', 'html_error', 'duplicate_path'];

    function nothingToCheck() {
      return !MEDIA_ON.subs && !MEDIA_ON.epub && !MEDIA_ON.custom && !(MEDIA_ON.manga && mediaDirs(libLast || {}, 'manga').length > 1);
    }
    let anRunning = false;
    function syncCheckScope() {
      const btn = document.getElementById('an-run');
      if (btn) btn.disabled = nothingToCheck() || libBusy();
    }

    async function runAnalysis() {
      if (nothingToCheck()) return;
      const only = libScope() === 'manga' ? '' : libScope();
      await anAct(async () => {
        const res = await apiPost('/api/library/analyse', only ? { only } : {}).catch(() => null);
        if (res) renderAnalysisStatus(res);
      });
      pollAnalysis();
      pollActivity();
    }

    function pollAnalysis() {
      if (anPoll) return;
      const poll = async () => {
        let d;
        try { d = await fetch('/api/library/analysis?status=1').then(r => r.json()); } catch (e) { anPoll = setTimeout(poll, 1000); return; }
        if (TAB !== 'library') { anPoll = null; return; }
        renderAnalysisStatus(d.status);
        if (!d.status.running) { anPoll = null; await loadAnalysis(); pollActivity(); }
        else anPoll = setTimeout(poll, 1000);
      };
      anPoll = setTimeout(poll, 1000);
    }

    async function loadAnalysis() {
      let d;
      anLoading('an_loading_results');
      const media = ['subs', 'epub', 'manga', 'custom'].filter(m => MEDIA_ON[m]).join(',');
      try { d = await fetch('/api/library/analysis?' + new URLSearchParams({ media })).then(r => r.json()); } catch (e) { return; } finally { anLoading(null); }
      renderAnalysisStatus(d.status);
      if (d.status.running) pollAnalysis(); else { anViewMedia = media; renderAnalysis(d); }
    }

    function renderAnalysisStatus(s) {
      const btn = document.getElementById('an-run');
      const box = document.getElementById('an-status');
      s = s || {};
      anRunning = !!s.running;
      syncRunButtons();
      btn.querySelector('span').textContent = s.running ? t('an_running') : t('an_run');
      if (s.running) {
        const numeric = Number.isFinite(s.total) && s.total > 0;
        const pct = numeric ? Math.min(100, Math.round(100 * s.done / s.total)) : 0;
        const phase = s.phase || 'traversal';
        const count = numeric ? `${fmt(s.done || 0)} / ${fmt(s.total)}`
          : phase === 'reading' && s.total === 0 ? t('an_cached', { n: fmt(s.cached || 0) }) : '';
        updateIndexBody(box, `<div class="progress${numeric ? '' : ' indeterminate'}"><div style="width:${numeric ? pct : 35}%"></div></div>
          <div class="progress-text">${esc(t('an_stage_' + s.stage))} · ${esc(t('an_phase_' + phase))}${count ? ' — ' + esc(count) : ''} ${s.current ? '· ' + esc(s.current) : ''}</div>
          <div class="progress-text">${esc(t('an_elapsed', { e: fmtDuration(s.phase_elapsed ?? Math.max(0, Date.now() / 1000 - (s.started_at || Date.now() / 1000))) }))}${s.remaining == null ? '' : ' · ' + esc(fmtEta(s.remaining))}${s.workers ? ' · ' + esc(t('an_workers', { n: fmt(s.workers) })) : ''}</div>
          <div class="btns"><button class="btn" onclick="askStop('check')" ${s.stopping ? 'disabled' : ''}>${esc(t(s.stopping ? 'stopping' : 'stop_btn'))}</button></div>`);
      } else {
        box.innerHTML = s.error ? `<div class="notice err">${esc(t('lib_error', { e: s.error }))}</div>`
          : s.stopped ? `<div class="notice warn">${esc(t('an_stopped'))}</div>` : '';
      }
    }

    const AN_REASON_KEYS = {
      no_japanese: 'an_reason_no_japanese',
      image_only: 'an_why_image_only', drm: 'an_reason_drm', empty_or_wall: 'an_reason_empty_or_wall'
    };
    function anUnreadableWhy(it) {
      const error = String(it.error || ''), d = it.details || {};
      if (error.includes('Invalid UTF-16')) return t('an_why_bad_utf16');
      if (error.includes('Cannot decode as')) return t('an_why_undecodable');
      if (d.binary) return t('an_why_binary');
      if (d.damaged) return t('an_why_damaged');
      if (d.mojibake) return t('an_why_mojibake', { n: fmt(d.mojibake) });
      return '';
    }

    function anReason(reason, media) {
      return t(reason === 'bilingual' && media === 'custom' ? 'an_reason_custom_bilingual' : 'an_reason_' + reason);
    }

    function anWhy(it) {
      if (it.reason === 'duplicate_kept') return t('an_kept');
      if (it.reason === 'duplicate') {
        const keep = it.keep.split(/[\\/]/).pop();
        if (it.how === 'subplz') return t('an_why_subplz', { keep });
        return it.how === 'same_bytes' ? t('an_why_bytes', { keep }) : t('an_why_dup', { keep, pct: Math.round(100 * it.share) });
      }
      if (it.reason === 'html_error' || it.reason === 'unsupported') return '';
      if (it.reason === 'unreadable') return anUnreadableWhy(it);
      if (AN_REASON_KEYS[it.reason]) return t(AN_REASON_KEYS[it.reason]);
      if (it.reason === 'garbled' && it.media === 'epub') return t('an_why_garbled', { lines: fmt(it.lines), n: fmt(it.details?.replacement_lines || 0) });
      const counts = t('an_why_lang', { lines: fmt(it.lines), ja: fmt(it.ja), zh: fmt(it.zh), en: fmt(it.en) });
      return it.read_only ? `${counts} · ${t('an_encoding_read_only')}` : counts;
    }

    const AN_PAGE = 200;
    const AN_FILTERABLE = ['bilingual', 'other_language', 'language_review', 'image_only', 'drm', 'garbled', 'unreadable', 'unsupported', 'html_error', 'no_japanese', 'empty_or_wall'];
    let anSections = [], anReport = null, anView = '', anViewMedia = '';
    let anPicked = new Set(), anUnpicked = new Set(), anRecheck = new Set(), anRecheckKeys = { dups: [], other: [] };
    let anGroups = new Map(), anIdMedia = new Map(), anGroupMedia = new Map();
    const anChoice = new Map();
    let anDraftGeneration = null, anCanSelect = true;
    const anSavedKey = f => `${f.media}\t${f.name}`;
    const anKeyEntry = key => { const at = key.indexOf('\t'); return { media: key.slice(0, at), name: key.slice(at + 1) }; };
    const anSectionsOf = prefix => Object.entries(anReport?.sections || {}).filter(([k]) => k.startsWith(prefix));
    function anDefaultTicked(i) {
      return AN_FILTERABLE.includes(i.reason) && i.reason !== 'language_review'
        && !(i.reason === 'bilingual' && i.media === 'custom') && !(i.reason === 'garbled' && i.media === 'epub');
    }
    function anStored(key) { try { return JSON.parse(store.get(key, 'null')); } catch (_) { return null; } }
    function anSaveDraft() {
      store.set('aobana_library_draft', JSON.stringify({ generation: anDraftGeneration,
        picked: [...anPicked], unpicked: [...anUnpicked],
        choices: [...anChoice] }));
    }
    function anRestoreDraft(generation) {
      const draft = anStored('aobana_library_draft');
      anChoice.clear();
      anPicked = new Set(anSectionsOf('find:').flatMap(([k, s]) => anDefaultTicked({ media: k.split(':')[1], reason: k.split(':')[2] }) ? s.ids || [] : []));
      anUnpicked = new Set();
      if (!anCanSelect) { anPicked.clear(); anDraftGeneration = generation; return; }
      if (draft && draft.generation === generation) {
        if (Array.isArray(draft.picked)) anPicked = new Set(draft.picked);
        if (Array.isArray(draft.unpicked)) anUnpicked = new Set(draft.unpicked);
        for (const [id, choice] of Array.isArray(draft.choices) ? draft.choices : []) {
          if (choice && typeof choice === 'object' && (choice.all === true || typeof choice.keeper === 'string')) anChoice.set(id, choice);
        }
      }
      anDraftGeneration = generation;
    }
    function anNotice(key) {
      const notice = anStored('aobana_library_notice');
      return notice && notice.key === key ? `<div class="notice ok">${esc(t(notice.key, { n: fmt(notice.n) }))}</div>` : '';
    }
    const AN_REPAIR_REASONS = { 'Native ruby markup in stored text': 'an_repair_native', 'Stored text garbled': 'an_repair_garbled',
      'Stored text differs': 'an_repair_text',
      'No Japanese dialogue': 'an_reason_no_japanese',
      'ASS content named .srt': 'an_repair_ass_srt', 'Dot-millisecond timecodes': 'an_repair_dot_time', 'UTF-16': 'an_repair_encoding', 'CP932': 'an_repair_encoding' };
    function anEncodingError(code) {
      const key = code === 'read_only' ? 'an_encoding_read_only' : 'an_encoding_err_' + code;
      return I18N.ja[key] ? t(key) : '';
    }
    function anRepairReason(reason) {
      return String(reason || '').split('; ').map(part => {
        const key = AN_REPAIR_REASONS[part];
        if (key) return t(key, { e: part });
        if (part.startsWith('Ignored malformed ASS override: ')) return t('an_repair_override', { tag: part.slice(32) });
        const lines = part.match(/^Line count (\d+) -> (\d+)$/);
        if (lines) return t('an_repair_lines', { now: fmt(Number(lines[1])), n: fmt(Number(lines[2])) });
        return part;
      }).join(' · ');
    }
    function anDecisionNotice(key, n, media) {
      const previous = anStored('aobana_library_notice');
      store.set('aobana_library_notice', JSON.stringify({ key, n, at: Date.now() / 1000,
        media: [...new Set([...(previous?.media || []), ...media])] }));
    }
    function anReveal(media, path) {
      if (ON_PHONE || !path || !['subs', 'epub', 'custom'].includes(media)) return '';
      return `<button type="button" class="reveal-btn" data-media="${esc(media)}" data-check="${encodeURIComponent(path)}" onclick="revealInFolder(event, this)" aria-label="${esc(t('reveal'))}" title="${esc(t('reveal'))}">${REVEAL_SVG}</button>`;
    }
    const anInRoot = (root, path) => root ? root.replace(/[\\/]+$/, '') + (root.includes('\\') ? '\\' : '/') + path.replace(/[\\/]/g, root.includes('\\') ? '\\' : '/') : path;
    function anRow(it) {
      if (it.reason === 'duplicate_path') return `<label class="an-row"><span></span><span class="name">${esc(anInRoot(it.root, it.path))}</span><span class="why">${esc(anInRoot(it.first_root, it.path))}</span></label>`;
      const label = it.media === 'epub' && it.title ? `${it.title}${it.author ? ' / ' + it.author : ''} — ${it.path}` : it.path;
      const box = AN_FILTERABLE.includes(it.reason)
        ? `<input type="checkbox" class="an-pick" value="${it.id}" ${anPicked.has(Number(it.id)) ? 'checked' : ''} ${anCanSelect ? '' : 'disabled'}>` : '<span></span>';
      return `<label class="an-row">${box}<span class="name">${esc(label)}${anReveal(it.media, it.path)}</span><span class="why">${esc(anWhy(it))}</span></label>`;
    }
    function anFilteredRow(f) {
      const evidence = f.language_evidence;
      const language = ['bilingual', 'other_language', 'language_review'].includes(f.reason);
      const detail = language ? `<span class="an-evidence">${evidence ? esc(t('an_why_lang', Object.fromEntries(['lines','ja','zh','en'].map(k => [k, fmt(evidence[k])]))))
        + ' · ' + esc(t('an_evidence_' + f.evidence_state)) + (evidence.check_at ? ' · ' + esc(evidence.check_at) : '') : esc(t('an_evidence_unavailable'))}</span>` : '';
      return `<label class="an-row"><input type="checkbox" class="an-unpick" value="${esc(anSavedKey(f))}" ${anUnpicked.has(anSavedKey(f)) ? 'checked' : ''}>
        <span class="name">${esc(t('an_stage_' + f.media))} · ${esc(f.name)}${f.exists === false ? ' ' + esc(t('an_missing')) : anReveal(f.media, f.path || f.name)}</span>
        <span class="why">${esc(anReason(f.reason, f.media))}${f.keep ? ' · ' + esc(t('an_kept_is', { keep: f.keep.split(/[\\/]/).pop() })) : ''}${detail}</span></label>`;
    }
    function anNote(reason, media) {
      for (const key of [`an_note_${media}_${reason}`, 'an_note_' + reason]) {
        const text = t(key);
        if (text !== key) return `<div class="an-note">${esc(text)}</div>`;
      }
      return '';
    }
    function anRecheckRow(it) {
      const key = anSavedKey(it);
      const counts = it.lines ? ' · ' + t('an_why_lang', { lines: fmt(it.lines), ja: fmt(it.ja), zh: fmt(it.zh), en: fmt(it.en) }) : it.error ? ' · ' + it.error : '';
      return `<label class="an-row"><input type="checkbox" class="an-recheck" value="${esc(key)}" ${anRecheck.has(key) ? 'checked' : ''}>
        <span class="name">${esc(t('an_stage_' + it.media))} · ${esc(it.path)}${anReveal(it.media, it.path)}</span>
        <span class="why">${esc(t('an_recheck_why', { was: anReason(it.saved, it.media), now: it.now ? anReason(it.now, it.media) : t('an_recheck_clear') }) + counts)}</span></label>`;
    }
    function anSection(units, draw, size, summary, bar = '', after = '', key = '') {
      const sec = Array.isArray(units) ? { units, count: units.length, left: units.reduce((n, u) => n + size(u), 0) }
        : { name: units.name, units: [], count: units.count, left: units.left ?? units.count, ids: units.ids, keys: units.keys };
      const idx = anSections.push(Object.assign(sec, { draw, size, shown: 0 })) - 1;
      return `<details class="an-section" data-an="${idx}" data-an-key="${esc(key)}"><summary>${summary}</summary>${bar}<div class="an-list"></div>${after}</details>`;
    }
    function anQuery(extra) {
      return new URLSearchParams({ view: anView, media: anViewMedia, ...extra });
    }
    async function anDrawMore(details) {
      const idx = Number(details.dataset.an), sec = anSections[idx], list = details.querySelector('.an-list');
      if (!sec || !list || sec.busy) return;
      if (sec.name && sec.shown >= sec.units.length && sec.units.length < sec.count) {
        sec.busy = true;
        const res = await fetch('/api/library/analysis/page?' + anQuery({ section: sec.name, offset: sec.units.length })).then(r => r.json()).catch(() => null);
        sec.busy = false;
        if (anSections[idx] !== sec || !res) return;
        if (res.stale) { loadAnalysis(); return; }
        if (sec.name.startsWith('dup:')) res.rows.forEach(g => {
          anGroups.set(g.id, g);
          const c = anChoice.get(g.id);
          if (c && !c.all && !(g.members.some(m => m.name === c.keeper) && anCanKeep(g, c.keeper))) anChoice.delete(g.id);
        });
        sec.units.push(...res.rows);
        if (!res.rows.length) sec.count = sec.units.length;
      }
      if (sec.shown >= sec.units.length) return;
      let html = '', rows = 0;
      while (sec.shown < sec.units.length && rows++ < AN_PAGE) {
        const u = sec.units[sec.shown++]; html += sec.draw(u); sec.left -= sec.size(u);
      }
      list.querySelector('.an-more')?.remove();
      list.insertAdjacentHTML('beforeend', html + (sec.shown < sec.count
        ? `<button type="button" class="an-more sidebar-more">${esc(t('sidebar_more', { n: fmt(sec.left) }))}</button>` : ''));
    }
    function wireAnalysis(box) {
      if (box.dataset.wired) return;
      box.dataset.wired = '1';
      box.addEventListener('toggle', e => {
        const d = e.target;
        if (d.matches('details.an-section[data-an]') && d.open && !d.querySelector('.an-list').children.length) anDrawMore(d);
      }, true);
      box.addEventListener('scroll', e => {
        const s = e.target;
        if (s.classList?.contains('an-list') && s.scrollTop + s.clientHeight > s.scrollHeight - 400) anDrawMore(s.closest('details'));
      }, { capture: true, passive: true });
      box.addEventListener('click', e => {
        const more = e.target.closest('.an-more'); if (more) anDrawMore(more.closest('details'));
        const apply = e.target.closest('[data-an-apply]'); if (apply) anApplyGroup(apply.dataset.anApply);
        const all = e.target.closest('[data-an-apply-all]'); if (all) anApplyAll(all.dataset.anApplyAll);
      });
      box.addEventListener('change', e => {
        const cb = e.target;
        if (cb.classList.contains('an-pick')) (cb.checked ? anPicked.add(Number(cb.value)) : anPicked.delete(Number(cb.value)));
        else if (cb.classList.contains('an-unpick')) (cb.checked ? anUnpicked.add(cb.value) : anUnpicked.delete(cb.value));
        else if (cb.classList.contains('an-recheck')) (cb.checked ? anRecheck.add(cb.value) : anRecheck.delete(cb.value));
        else if (cb.classList.contains('an-keeper')) {
          const id = cb.dataset.group;
          if (!cb.value) anChoice.delete(id);
          else anChoice.set(id, cb.value === 'all' ? { all: true, by: 'hand' } : { keeper: cb.value.slice(2), by: 'hand' });
          anSaveDraft(); anRedrawGroups([id]); anSaveButton(); return;
        } else return;
        anSaveDraft(); anSelectLabel(cb.closest('details.an-section')); anSaveButton();
      });
    }
    function renderFiltered(saved) {
      const bar = `<div class="btns"><button type="button" class="btn an-all" data-filtered="1" onclick="selectAllSection(this)">${esc(t('an_select_all'))}</button></div>`;
      let html = `<section class="an-part" id="an-saved"><h3>${esc(t('an_filtered_title'))} (${fmt(saved.count)})</h3><div class="facts">${esc(t('an_saved_lead'))}</div>`;
      const blocks = [];
      for (const media of ['subs', 'epub', 'custom']) {
        if (!MEDIA_ON[media]) continue;
        const sections = saved.sections.filter(s => s.media === media);
        const reasons = [...AN_ORDER, ...new Set(sections.filter(s => !AN_ORDER.includes(s.reason)).map(s => s.reason))];
        let block = '';
        for (const reason of reasons) {
          const s = sections.find(x => x.reason === reason);
          if (s) block += anSection({ name: s.key, count: s.count, keys: null }, anFilteredRow, () => 1,
            `${esc(t('an_stage_' + media))} · ${esc(anReason(reason, media))} (${fmt(s.count)})`, anNote(reason, media) + bar, '', 'saved:' + media + ':' + reason);
        }
        if (block) blocks.push(block);
      }
      html += blocks.join('<hr class="an-divider">');
      return html + `<div class="btns an-after"><button class="btn primary" id="an-restore" onclick="unfilterPicked()" ${anUnpicked.size ? '' : 'disabled'}>${esc(t('an_unfilter'))}</button></div><div id="an-restore-msg">${anNotice('an_unfiltered')}</div></section>`;
    }
    const AN_EQUIVALENT = { subs: 0.9, epub: 0.5, custom: 0.8 };
    function anCanKeep(g, name) {
      return name === g.keeper || g.members.every(m => (g.comparisons?.[name]?.[m.name] ?? 0) >= (AN_EQUIVALENT[g.media] || 1));
    }
    function anNeedsExclusion(g, m, keeper = g.keeper) {
      return m.name !== keeper && (!m.saved || m.saved.reason === 'duplicate' && m.saved.keep !== keeper);
    }
    function anDuplicateChoices() {
      return [...anChoice].flatMap(([id, c]) => {
        const g = anGroups.get(id);
        if (!g) return [c.all ? { group: id, keep_all: true } : { group: id, keeper: c.keeper }];
        if (c.all) return g.members.some(m => m.saved?.reason === 'duplicate') ? [{ group: g.id, keep_all: true }] : [];
        const exclude = g.members.filter(m => anNeedsExclusion(g, m, c.keeper)).map(m => m.name);
        const restore = g.members.some(m => m.name === c.keeper && m.saved?.reason === 'duplicate');
        return exclude.length || restore ? [{ group: g.id, keeper: c.keeper, exclude }] : [];
      });
    }
    function anSaveButton() {
      const save = document.getElementById('an-save');
      const busy = libBusy();
      if (save) save.disabled = busy || !anCanSelect || !anPicked.size && !anDuplicateChoices().length;
      const restore = document.getElementById('an-restore'); if (restore) restore.disabled = busy || !anUnpicked.size;
      for (const [id, dups] of [['an-recheck-include', false], ['an-recheck-keep', false], ['an-recheck-dups-include', true]]) {
        const b = document.getElementById(id);
        if (b) b.disabled = busy || !anRecheckKeys[dups ? 'dups' : 'other'].some(key => anRecheck.has(key));
      }
    }
    function renderAnalysis(d) {
      const box = document.getElementById('an-report'); wireAnalysis(box);
      if (d?.error) { box.innerHTML = `<div class="notice err">${esc(t('lib_error', { e: d.error }))}</div>`; return; }
      const r = d?.report, S = r?.sections || {};
      const generation = JSON.stringify([r?.selection_generation || r?.generation || 'no-report', r?.roots || {}, d?.current_roots || {}, d?.data_dir || '']);
      const open = new Set(generation === anDraftGeneration ? [...box.querySelectorAll('details.an-section[open]')].map(n => n.dataset.anKey) : []);
      anReport = r; anView = d?.view || ''; anCanSelect = d?.selection_valid !== false; anSections = []; anGroups = new Map();
      anRecheckKeys = { dups: S['recheck-dups']?.keys || [], other: S.recheck?.keys || [] };
      const rechecked = new Set([...anRecheckKeys.dups, ...anRecheckKeys.other]);
      anRecheck = new Set([...anRecheck].filter(key => rechecked.has(key)));
      anIdMedia = new Map(anSectionsOf('find:').flatMap(([k, s]) => (s.ids || []).map(id => [id, k.split(':')[1]])));
      anGroupMedia = new Map(anSectionsOf('dup:').flatMap(([k, s]) => s.groups.map(([id]) => [id, k.split(':')[1]])));
      if (generation !== anDraftGeneration) {
        anRestoreDraft(generation);
        anRecheckKeys.dups.forEach(key => anRecheck.add(key));
      }
      anPicked = new Set([...anPicked].filter(id => anIdMedia.has(id)));
      for (const [id, c] of anChoice) if (!anGroupMedia.has(id)) anChoice.delete(id);
      let html = `<section class="an-part" id="an-completed"><h3>${esc(t('an_completed_title'))}</h3>`;
      if (!r) html += `<div class="facts">${esc(t('an_no_completed'))}</div>`;
      else {
        const files = Object.entries(r.summary || {}).reduce((n, [m, s]) => n + (MEDIA_ON[m] ? s.files || 0 : 0), 0);
        html += `<div class="facts">${esc(t('an_summary', { files: fmt(files), when: r.generated_at }))}</div>`;
        const queued = S.pending?.count || 0, repair = S.reindex?.count || 0, rechecks = rechecked.size;
        if (repair || rechecks) html += `<div class="facts">${esc(t('an_act_lead'))}</div>`;
        const attempt = r.last_attempt;
        if (attempt && !attempt.running && (attempt.stopped || attempt.error || !attempt.finished_at)) html += `<div class="notice warn">${esc(t('an_interrupted_snapshot', {
          when: new Date((attempt.finished_at || attempt.started_at) * 1000).toLocaleString(), done: fmt(attempt.done || 0), total: fmt(attempt.total || 0), stage: t('an_stage_' + attempt.stage) }))}</div>`;
        const conversions = attempt?.encoding_results || [];
        if (conversions.length) {
          const converted = conversions.filter(i => i.status === 'converted').length, failed = conversions.filter(i => i.status === 'failed');
          if (converted) html += `<div class="notice ok">${esc(t('an_encoding_result', { n: fmt(converted), dir: d.backups_dir || '' }))}</div>`;
          if (failed.length) html += `<div class="notice warn">${esc(t('an_encoding_failed_count', { f: fmt(failed.length) }))}</div>`
            + anSection(failed, i => `<div class="an-row"><span></span><span class="name">${esc(i.name)}${anReveal('subs', i.name)}</span><span class="why">${esc(anEncodingError(i.error))}</span></div>`, () => 1, esc(t('an_encoding_failures')), '', '', 'encoding-failures');
        }
        if (queued) html += anSection({ name: 'pending', count: queued }, i => `<div class="an-row an-queued"><span></span><span class="name">${esc(i.name)}${anReveal('subs', i.name)}</span><span class="why">${esc(anRepairReason(i.reason))}</span></div>`, () => 1,
          esc(t('an_pending_title', { n: fmt(queued) })), `<div class="an-note">${esc(t('an_pending_lead'))}</div>`, '', 'pending');
        if (r.pending_refresh_error) html += `<div class="notice warn">${esc(t('an_apply_failed'))}</div>`;
        if (repair) html += anSection({ name: 'reindex', count: repair }, i => `<div class="an-row"><span></span><span class="name">${esc(i.path)}${anReveal('subs', i.path)}</span><span class="why">${esc(anRepairReason(i.reason))}</span></div>`, () => 1,
          esc(t('an_repair_summary', { n: fmt(repair) })), '', `<div class="btns an-after"><button class="btn primary" data-run-lock onclick="repairSubtitles()" ${libBusy() ? 'disabled' : ''}>${esc(t('an_repair'))}</button></div><div class="an-note">${esc(t('an_reindex_notice'))}</div>`, 'reindex');
        const recheckDups = anRecheckKeys.dups.length, recheckOther = anRecheckKeys.other.length;
        if (recheckDups) html += anSection({ name: 'recheck-dups', count: recheckDups, keys: anRecheckKeys.dups }, anRecheckRow, () => 1,
          esc(t('an_recheck_dups_title', { n: fmt(recheckDups) })),
          `<div class="an-note">${esc(t('an_recheck_dups_lead'))}</div><div class="btns"><button type="button" class="btn an-all" data-recheck="1" onclick="selectAllSection(this)">${esc(t('an_select_all'))}</button></div>`,
          `<div class="btns an-after"><button class="btn primary" id="an-recheck-dups-include" onclick="recheckDecide(false, true)">${esc(t('an_unfilter'))}</button></div><div id="an-recheck-dups-msg">${anNotice('an_recheck_dups_included')}</div>`, 'recheck-dups');
        else html += anNotice('an_recheck_dups_included');
        if (recheckOther) html += anSection({ name: 'recheck', count: recheckOther, keys: anRecheckKeys.other }, anRecheckRow, () => 1,
          esc(t('an_recheck_title', { n: fmt(recheckOther) })),
          `<div class="an-note">${esc(t('an_recheck_lead'))}</div><div class="btns"><button type="button" class="btn an-all" data-recheck="1" onclick="selectAllSection(this)">${esc(t('an_select_all'))}</button></div>`,
          `<div class="btns an-after"><button class="btn primary" id="an-recheck-include" onclick="recheckDecide(false)">${esc(t('an_unfilter'))}</button><button class="btn primary" id="an-recheck-keep" onclick="recheckDecide(true)">${esc(t('an_recheck_keep'))}</button></div><div id="an-recheck-msg">${anNotice('an_recheck_kept')}${anNotice('an_recheck_included')}</div>`, 'recheck');
        const blocks = [];
        for (const media of ['subs', 'epub', 'manga', 'custom']) {
          if (!MEDIA_ON[media]) continue;
          let findings = '';
          for (const reason of AN_ORDER) {
            const dups = reason === 'duplicate' && S['dup:' + media], list = S[`find:${media}:${reason}`];
            if (dups) {
              const size = g => g.members.filter(m => anNeedsExclusion(g, m)).length;
              findings += anSection({ name: 'dup:' + media, count: dups.count, left: dups.size }, duplicateGroupHtml, size,
                `${esc(t('an_stage_' + media))} · ${esc(t('an_reason_duplicate'))} (${fmt(dups.size)})`,
                anNote('duplicate', media) + `<div class="btns"><button type="button" class="btn" data-an-apply-all="${media}" ${anCanSelect ? '' : 'disabled'}>${esc(t(anAppliedAll(media) ? 'an_unapply_all' : 'an_apply_all'))}</button></div>`, '', 'find:' + media + ':' + reason);
            } else if (list) {
              const bar = AN_FILTERABLE.includes(reason) ? `<div class="btns"><button type="button" class="btn an-all" onclick="selectAllSection(this)" ${anCanSelect ? '' : 'disabled'}>${esc(t('an_select_all'))}</button></div>` : '';
              const action = reason === 'encoding' && media === 'subs' ? `<div class="btns an-after"><button class="btn primary" data-run-lock onclick="repairEncoding()" ${libBusy() ? 'disabled' : ''}>${esc(t('an_encoding_repair'))}</button></div><div class="an-note">${esc(t('an_encoding_notice', { dir: d.backups_dir || '' }))}</div>` : '';
              findings += anSection({ name: `find:${media}:${reason}`, count: list.count, ids: list.ids || [] }, anRow, () => 1, `${esc(t('an_stage_' + media))} · ${esc(anReason(reason, media))} (${fmt(list.count)})`, anNote(reason, media) + bar, action, 'find:' + media + ':' + reason);
              if (reason === 'duplicate') findings += `<div class="notice warn">${esc(t('an_apply_failed'))}</div>`;
            }
          }
          if (findings) blocks.push(findings);
        }
        html += `<div class="an-findings${repair || queued || rechecks ? ' an-after-reindex' : ''}">`
          + (blocks.length ? `<div class="facts">${esc(t('an_completed_lead'))}</div>` : '');
        if (!anCanSelect) html += `<div class="notice warn">${esc(t('an_apply_failed'))}</div>`;
        html += blocks.join('<hr class="an-divider">') || `<div class="an-note">${esc(t('an_none'))}</div>`;
        html += `<div class="btns an-after"><button class="btn primary" id="an-save" onclick="filterFlagged()">${esc(t('an_filter'))}</button></div><div id="an-move-msg">${anNotice('an_filtered_done')}</div></div>`;
      }
      box.innerHTML = html + '</section>' + renderFiltered(d?.filtered || { count: 0, sections: [] });
      box.querySelectorAll('details.an-section').forEach(el => { if (open.has(el.dataset.anKey)) { el.open = true; anDrawMore(el); } });
      anSelectLabels(box); anSaveButton(); anSaveDraft();
    }
    function anSectionPicks(details) {
      const sec = details && anSections[Number(details.dataset.an)]; if (!sec) return null;
      if (details.querySelector('.an-all[data-filtered]')) return { ids: sec.keys, set: anUnpicked };
      if (details.querySelector('.an-all[data-recheck]')) return { ids: sec.keys, set: anRecheck };
      return { ids: sec.ids, set: anPicked };
    }
    function anAllTicked(p) { return !!p.ids?.length && p.ids.every(id => p.set.has(id)); }
    function anSelectLabel(details) {
      const btn = details?.querySelector('.an-all'), p = btn && anSectionPicks(details);
      if (p) btn.textContent = t(anAllTicked(p) ? 'an_deselect_all' : 'an_select_all');
    }
    function anSelectLabels(box) { box.querySelectorAll('details.an-section').forEach(anSelectLabel); }
    function anSyncBoxes(details) {
      details.querySelectorAll('.an-pick').forEach(cb => { cb.checked = anPicked.has(Number(cb.value)); });
      details.querySelectorAll('.an-unpick').forEach(cb => { cb.checked = anUnpicked.has(cb.value); });
      details.querySelectorAll('.an-recheck').forEach(cb => { cb.checked = anRecheck.has(cb.value); });
    }
    async function selectAllSection(btn) {
      const details = btn.closest('.an-section'), sec = details && anSections[Number(details.dataset.an)];
      if (sec && sec.keys === null) {
        btn.disabled = true;
        const res = await fetch('/api/library/analysis/keys?' + anQuery({ section: sec.name })).then(r => r.json()).catch(() => null);
        btn.disabled = false;
        if (res?.stale) { loadAnalysis(); return; }
        if (!res?.keys || anSections[Number(details.dataset.an)] !== sec) return;
        sec.keys = res.keys;
      }
      const p = anSectionPicks(details); if (!p?.ids) return;
      const untick = anAllTicked(p); p.ids.forEach(id => (untick ? p.set.delete(id) : p.set.add(id)));
      anSyncBoxes(details); anSelectLabel(details); anSaveButton(); anSaveDraft();
    }
    function anOptionLabel(g, m) {
      if (g.media === 'epub' && m.title) return `${m.title}${m.author ? ' / ' + m.author : ''} — ${m.path}`;
      return m.hints?.services?.length ? `${m.path} · ${m.hints.services.join(', ')}` : m.path;
    }
    function duplicateGroupHtml(group) {
      const c = anChoice.get(group.id), keeper = c?.keeper || group.keeper, off = anCanSelect ? '' : 'disabled';
      const options = [`<option value="" ${c ? '' : 'selected'}>${esc(t('an_choice_none'))}</option>`,
        ...group.members.map(m => {
          const ok = anCanKeep(group, m.name);
          const tag = m.name === group.keeper ? t('an_recommended_tag') : ok ? '' : t('an_not_same_tag');
          return `<option value="${esc('m:' + m.name)}" ${c?.keeper === m.name ? 'selected' : ''} ${ok ? '' : 'disabled'}>${esc(anOptionLabel(group, m) + (tag ? ' ' + tag : ''))}</option>`;
        }),
        ...(c?.all || group.members.some(m => m.saved?.reason === 'duplicate') ? [`<option value="all" ${c?.all ? 'selected' : ''}>${esc(t('an_choice_all'))}</option>`] : [])];
      const restore = c?.keeper && group.members.some(m => m.name === c.keeper && m.saved?.reason === 'duplicate');
      const rule = t(group.reason === 'subplz' ? 'an_subplz_rule' : group.reason === 'same_bytes' ? 'an_bytes_rule' : group.reason === 'similar_text' ? 'an_custom_near_rule' : group.media === 'custom' ? 'an_custom_rule' : group.media === 'epub' ? 'an_book_rule' : 'an_match_rule');
      let html = `<div class="an-dup-group" data-group="${esc(group.id)}"><div class="an-group-head">`
        + `<label class="an-keeper-label">${esc(t('an_keeper'))}<select class="an-keeper" data-group="${esc(group.id)}" ${off}>${options.join('')}</select></label>`
        + `<div class="btns"><button type="button" class="btn" data-an-apply="${esc(group.id)}" ${off}>${esc(t(c?.by === 'apply' ? 'an_unapply' : 'an_apply'))}</button><span class="facts">${esc(rule)}</span></div>`
        + (restore ? `<div class="facts">${esc(t('an_keeper_restore', { name: c.keeper }))}</div>` : '') + '</div>';
      for (const m of group.members) {
        const share = m.name === keeper ? (c ? t('an_kept') : t('an_recommended'))
          : keeper === group.keeper ? t(group.media === 'epub' ? 'an_reciprocal_book' : 'an_reciprocal', { a: Math.round(100 * m.overlap[0]), b: Math.round(100 * m.overlap[1]) })
          : t('an_match_keeper', { pct: Math.round(100 * (group.comparisons?.[keeper]?.[m.name] ?? 0)) });
        const why = [share, c && !c.all && anNeedsExclusion(group, m, keeper) ? t('an_left_out_on_save') : '',
          m.saved ? t('an_saved_exclusion') : '', m.hints?.services?.length ? m.hints.services.join(', ') : ''].filter(Boolean).join(' · ');
        html += `<div class="an-row ${c?.all || m.name === keeper ? 'kept' : ''}"><span></span><span class="name">${esc(m.path)}${anReveal(group.media, m.path)}</span><span class="why">${esc(why)}</span></div>`;
      }
      return html + '</div>';
    }
    function anListedGroups(media) { return anReport?.sections?.['dup:' + media]?.groups || []; }
    function anAppliedAll(media) {
      return anListedGroups(media).some(([id]) => anChoice.get(id)?.by === 'all');
    }
    function anRedrawGroups(ids) {
      const want = new Set(ids);
      const focused = document.activeElement?.classList?.contains('an-keeper') ? document.activeElement.dataset.group : null;
      document.querySelectorAll('#an-report .an-dup-group').forEach(el => {
        const g = want.has(el.dataset.group) && anGroups.get(el.dataset.group);
        if (g) el.outerHTML = duplicateGroupHtml(g);
      });
      if (focused && want.has(focused)) document.querySelector(`#an-report select.an-keeper[data-group="${CSS.escape(focused)}"]`)?.focus();
      document.querySelectorAll('#an-report [data-an-apply-all]').forEach(b => { b.textContent = t(anAppliedAll(b.dataset.anApplyAll) ? 'an_unapply_all' : 'an_apply_all'); });
    }
    function anApplyGroup(id) {
      const g = anGroups.get(id);
      if (!g || !anCanSelect) return;
      if (anChoice.get(id)?.by === 'apply') anChoice.delete(id); else anChoice.set(id, { keeper: g.keeper, by: 'apply' });
      anSaveDraft(); anRedrawGroups([id]); anSaveButton();
    }
    function anApplyAll(media) {
      if (!anCanSelect) return;
      const groups = anListedGroups(media);
      if (anAppliedAll(media)) groups.forEach(([id]) => { if (anChoice.get(id)?.by === 'all') anChoice.delete(id); });
      else groups.forEach(([id, keeper]) => { if (!anChoice.has(id)) anChoice.set(id, { keeper, by: 'all' }); });
      anSaveDraft(); anRedrawGroups(groups.map(([id]) => id)); anSaveButton();
    }
    function anFailed(res) { return `<div class="notice warn">${esc(res.error === 'busy' ? t('an_err_busy') : t('an_apply_failed'))}</div>`; }
    function repairSubtitles() {
      return anAct(async () => {
        const res = await apiPost('/api/library/repair', { generation: anReport.generation }).catch(() => ({ error: 'network' }));
        if (res.error) { anMessage(anFailed(res)); return; }
        await loadAnalysis();
      });
    }
    function repairEncoding() {
      return anAct(async () => {
        const res = await apiPost('/api/library/encoding-repair', { generation: anReport.generation }).catch(() => ({ error: 'network' }));
        if (res.error) { anMessage(anFailed(res)); return; }
        renderAnalysisStatus(res.status); if (res.started) pollAnalysis();
      });
    }
    function anMessage(html, id = 'an-move-msg') {
      for (const slot of html ? [id] : ['an-move-msg', 'an-restore-msg']) { const el = document.getElementById(slot); if (el) el.innerHTML = html; }
    }
    async function anWithProgress(large, request) {
      if (!large) return request;
      const spin = document.querySelector('#lib-analyse .an-busy');
      const note = document.createElement('span'); note.className = 'an-note an-progress';
      let timer = null, done = false;
      const poll = async () => {
        const p = await fetch('/api/library/filter/progress').then(r => r.json()).catch(() => null);
        if (done) return;
        if (p?.running && p.total) {
          const left = p.done ? p.elapsed / p.done * (p.total - p.done) : null;
          note.textContent = [`${fmt(p.done)} / ${fmt(p.total)}`, fmtEta(left)].filter(Boolean).join(' · ');
          if (spin?.isConnected && !note.isConnected) spin.after(note);
        }
        timer = setTimeout(poll, 1000);
      };
      timer = setTimeout(poll, 500);
      try { return await request; } finally { done = true; clearTimeout(timer); note.remove(); }
    }
    function filterFlagged() { return anAct(saveFlagged); }
    function unfilterPicked() { return anAct(includePicked); }
    function recheckDecide(keep, dups = false) { return anAct(() => saveRecheck(keep, dups)); }
    async function saveFlagged() {
      const ids = [...anPicked].filter(id => anIdMedia.has(id)), choices = anDuplicateChoices();
      if (!ids.length && !choices.length) return;
      const btn = document.getElementById('an-save'); if (btn) btn.disabled = true;
      const files = ids.length + choices.reduce((n, c) => n + (c.exclude?.length ?? 1), 0);
      const res = await anWithProgress(files > 500, apiPost('/api/library/filter', { ids, choices, generation: anReport.selection_generation || anReport.generation }).catch(() => ({ error: 'network' })));
      if (res.error) { anMessage(`<div class="notice warn">${esc(res.error === 'busy' ? t('an_err_busy') : t('an_apply_failed'))}</div>`); anSaveButton(); return; }
      anChoice.clear(); anPicked.clear(); anSaveDraft();
      anDecisionNotice('an_filtered_done', res.saved + res.included,
        [...ids.map(id => anIdMedia.get(id)), ...choices.map(c => anGroupMedia.get(c.group))].filter(Boolean));
      await loadAnalysis(); await refreshLibrary();
    }
    async function includePicked() {
      const entries = [...anUnpicked].map(anKeyEntry);
      if (!entries.length) return;
      const btn = document.getElementById('an-restore'); if (btn) btn.disabled = true;
      const res = await apiPost('/api/library/unfilter', { entries }).catch(() => ({ error: 'network' }));
      if (res.error) { anMessage(`<div class="notice warn">${esc(res.error === 'busy' ? t('an_err_busy') : t('lib_error', { e: res.error }))}</div>`, 'an-restore-msg'); anSaveButton(); return; }
      anUnpicked.clear(); anSaveDraft(); anDecisionNotice('an_unfiltered', res.unfiltered, entries.map(e => e.media));
      await loadAnalysis(); await refreshLibrary();
    }
    async function saveRecheck(keep, dups) {
      const picked = anRecheckKeys[dups ? 'dups' : 'other'].filter(key => anRecheck.has(key));
      const entries = picked.map(anKeyEntry);
      if (!entries.length) return;
      for (const id of ['an-recheck-include', 'an-recheck-keep', 'an-recheck-dups-include']) { const b = document.getElementById(id); if (b) b.disabled = true; }
      const res = await apiPost(keep ? '/api/library/keep-left-out' : '/api/library/unfilter', { entries }).catch(() => ({ error: 'network' }));
      if (res.error) { anMessage(`<div class="notice warn">${esc(res.error === 'busy' ? t('an_err_busy') : t('lib_error', { e: res.error }))}</div>`, dups ? 'an-recheck-dups-msg' : 'an-recheck-msg'); anSaveButton(); return; }
      picked.forEach(key => anRecheck.delete(key));
      anDecisionNotice(keep ? 'an_recheck_kept' : dups ? 'an_recheck_dups_included' : 'an_recheck_included', keep ? res.kept : res.unfiltered, entries.map(e => e.media));
      await loadAnalysis(); if (!keep) await refreshLibrary();
    }


    let libPollGeneration = 0;
    let libPollRun = null;
    function startPolling() {
      if (libPoll || TAB !== 'library') return;
      const generation = ++libPollGeneration;
      const poll = async () => {
        if (generation !== libPollGeneration || TAB !== 'library') return;
        let s;
        try { s = await fetch('/api/index/status').then(r => r.json()); } catch (e) {}
        if (generation !== libPollGeneration || TAB !== 'library') return;
        if (s) {
          if (libPollRun && s.run_id && libPollRun !== s.run_id) {
            libPollRun = s.run_id;
          }
          renderIndexStatus(s);
        }
        if (s && !s.running) {
          libPoll = null;
          libPollRun = null;
          pollActivity(); refreshLibrary(); loadAnalysis();
        } else {
          libPoll = setTimeout(poll, 1000);
        }
      };
      libPoll = setTimeout(poll, 1000);
    }
    window.addEventListener('pagehide', () => {
      ++libPollGeneration;
      ++libPageGeneration;
      if (libPoll) clearTimeout(libPoll);
      if (libRefreshTimer) clearTimeout(libRefreshTimer);
      if (figPoll) clearTimeout(figPoll);
      if (anPoll) clearTimeout(anPoll);
      libPoll = null;
      libRefreshTimer = figPoll = anPoll = null;
    });

    function updateIndexBody(target, html) {
      const template = document.createElement('template');
      template.innerHTML = html;
      function patch(parent, fresh) {
        [...fresh.childNodes].forEach((next, i) => {
          let old = parent.childNodes[i];
          if (!old || old.nodeType !== next.nodeType || old.nodeName !== next.nodeName) {
            if (old) parent.replaceChild(next.cloneNode(true), old);
            else parent.appendChild(next.cloneNode(true));
            return;
          }
          if (old.nodeType === Node.TEXT_NODE) {
            if (old.nodeValue !== next.nodeValue) old.nodeValue = next.nodeValue;
          } else if (old.nodeType === Node.ELEMENT_NODE) {
            [...old.attributes].forEach(a => { if (!next.hasAttribute(a.name)) old.removeAttribute(a.name); });
            [...next.attributes].forEach(a => { if (old.getAttribute(a.name) !== a.value) old.setAttribute(a.name, a.value); });
            patch(old, next);
          }
        });
        while (parent.childNodes.length > fresh.childNodes.length) parent.lastChild.remove();
      }
      patch(target, template.content);
    }

    let libLogRows = [];
    let libLogRun = null;
    let libLogFollow = true;
    function updateIndexLog(box, s) {
      let log = box.querySelector('details.log');
      if (!log) {
        log = document.createElement('details'); log.className = 'log';
        const summary = document.createElement('summary'); summary.textContent = t('lib_log');
        const controls = document.createElement('div'); controls.className = 'btns';
        const copy = document.createElement('button'); copy.className = 'btn'; copy.textContent = t('lib_log_copy');
        const follow = document.createElement('button'); follow.className = 'btn'; follow.textContent = t('lib_log_pause');
        const pre = document.createElement('pre');
        copy.onclick = () => navigator.clipboard.writeText(pre.textContent);
        follow.onclick = () => {
          libLogFollow = !libLogFollow;
          follow.textContent = t(libLogFollow ? 'lib_log_pause' : 'lib_log_follow');
        };
        controls.append(copy, follow); log.append(summary, controls, pre); box.append(log);
      }
      const pre = log.querySelector('pre');
      const atEnd = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 24;
      const rows = s.log || [];
      if (s.run_id && s.run_id !== libLogRun) {
        pre.replaceChildren(); libLogRows = []; libLogRun = s.run_id;
      }
      let overlap = Math.min(rows.length, libLogRows.length);
      while (overlap && !rows.slice(0, overlap).every((v,i) => v === libLogRows[libLogRows.length-overlap+i])) --overlap;
      for (let i = overlap; i < rows.length; ++i) pre.appendChild(document.createTextNode(rows[i] + '\n'));
      libLogRows = [...rows];
      while (pre.childNodes.length > 2000 && !window.getSelection()?.toString()) pre.firstChild.remove();
      log.hidden = !rows.length;
      if (libLogFollow && atEnd && !window.getSelection()?.toString()) pre.scrollTop = pre.scrollHeight;
    }

    const LINE_COUNTED_PHASES = ['preparation', 'writing'];
    function libErrorText(s) {
      if (s.error === 'companion_conflict') {
        const files = (s.folder_errors || []).filter(e => e.error === 'companion_conflict').map(e => e.file);
        return t('lib_err_companion_conflict', { file: files.join(LANG === 'ja' ? '、' : ', ') });
      }
      if (s.error === 'companion_migration_failed') return t('lib_err_companion_failed');
      return t('lib_error', { e: s.error });
    }
    function renderIndexStatus(s) {
      const btn = document.getElementById('lib-run');
      const box = document.getElementById('lib-status');
      s = s || {};
      const decision = anStored('aobana_library_notice');
      if (decision && !s.running && !s.error && !s.stopped && !s.tables && !s.repair
          && s.started_at > decision.at && s.finished_at && !s.failed?.length
          && !s.root_missing?.length && !s.root_not_set?.length && !Object.keys(s.removal_held || {}).length
          && decision.media?.every(media => s.stages?.includes(media))) {
        store.del('aobana_library_notice'); anMessage('');
      }
      let body = box.querySelector('.index-main');
      if (!body) { body = document.createElement('div'); body.className = 'index-main'; box.replaceChildren(body); }
      if (tableRunStartedHere && s.started_at && !s.running) {
        optimizeDoneThisVisit = !!(s.tables && !s.error && !s.stopped);
        tableRunStartedHere = false;
        if (libLast) renderOutdated(libLast);
      }
      indexRunning = !!s.running;
      if (s.running || s.finished_at || s.error || s.stopped) libStarting = false;
      syncRunButtons();
      btn.querySelector('span').textContent = s.running ? t('lib_running') : t('lib_run');
      if (!s.started_at) {
        const u = s.unfinished;
        updateIndexBody(body, u ? `<div class="notice warn">${esc(t(u.outdated ? 'lib_unfinished_outdated' : 'lib_unfinished'))}</div>` : '');
        return;
      }
      let html = '';
      if (s.running) {
        const pct = s.total ? Math.round(100 * s.done / s.total) : 0;
        html += `<div class="progress"><div style="width:${pct}%"></div></div>
          <div class="progress-text">${esc(t('lib_stage_' + s.stage))} — ${s.phase
            ? esc(t('lib_phase_' + s.phase)) + (s.phase_total && !LINE_COUNTED_PHASES.includes(s.phase) ? ` ${fmt(s.phase_done)} / ${fmt(s.phase_total)}` : '')
            : (s.current ? esc(s.current) : '')}</div>
          <div class="progress-text">${esc(t(s.total ? 'lib_phase_counts_of' : 'lib_phase_counts', { p: fmt(s.prepared_done || 0), n: fmt(s.total || 0), c: fmt(s.committed_done || 0) }))}${s.remaining == null ? '' : ' · ' + esc(fmtEta(s.remaining))}</div>
          <div class="btns"><button class="btn" onclick="askStop('index', ${s.outdated ? 'true' : 'false'})" ${s.stopping ? 'disabled' : ''}>${esc(t(s.stopping ? 'stopping' : 'stop_btn'))}</button></div>`;
      } else {
        const results = s.results || {};
        if (s.error) html += `<div class="notice err">${esc(libErrorText(s))}</div>`;
        else if (s.stopped) html += `<div class="notice warn">${esc(t('lib_stopped'))}</div>`;
        else if (s.tables) html += `<div class="notice ok">${esc(t('lib_tables_ready'))}</div>`;
        else html += `<div class="notice ok">${esc(t('lib_done'))} <a href="/">${esc(t('lib_done_search'))} →</a></div>`;
        const stages = ['subs', 'epub', 'manga', 'custom'].filter(k => results[k]);
        if (stages.length) {
          html += `<table class="summary-table"><tr><th></th><th>${esc(t('lib_col_new'))}</th><th>${esc(t('lib_col_same'))}</th><th>${esc(t('lib_col_removed'))}</th></tr>`;
          stages.forEach(k => {
            const r = results[k];
            html += `<tr><td>${esc(t('lib_stage_' + k))}</td><td>${fmt(r.indexed)}</td><td>${fmt(r.unchanged)}</td><td>${fmt(r.removed)}</td></tr>`;
          });
          html += '</table>';
        }
        if (s.json_unsupported) html += `<div class="notice">${esc(t('lib_json_unsupported', { n: fmt(s.json_unsupported) }))}</div>`;
      }
      (s.root_not_set || []).forEach(st => {
        html += `<div class="notice">${esc(t('lib_root_not_set', { s: t('lib_stage_' + st) }))}</div>`;
      });
      (s.root_missing || []).forEach(st => {
        html += `<div class="notice warn">${esc(t('lib_root_missing', { s: t('lib_stage_' + st) }))}</div>`;
      });
      const held = Object.keys(s.removal_held || {}).filter(st => ['subs', 'epub', 'manga', 'custom'].includes(st));
      if (!s.running && held.length) {
        held.forEach(st => {
          const h = s.removal_held[st];
          html += `<div class="notice warn">${esc(t('lib_removal_held', { s: t('lib_stage_' + st), gone: fmt(h.gone), indexed: fmt(h.indexed) }))}</div>`;
        });
        const only = '[' + held.map(st => `'${st}'`).join(',') + ']';
        html += `<div class="btns"><button class="btn" onclick="startIndex(${only}, false, false, true)">${esc(t('lib_remove_anyway'))}</button></div>`;
      }
      if ((s.skipped_clash || []).length) {
        html += `<div class="notice warn">${esc(t('lib_skipped_clash'))}<ul>${capList(s.skipped_clash)}</ul></div>`;
      }
      if ((s.failed || []).length) {
        html += `<div class="notice err">${esc(t('lib_failed'))}<ul>${capList(s.failed)}</ul></div>`;
      }
      updateIndexBody(body, html);
      updateIndexLog(box, s);
    }

