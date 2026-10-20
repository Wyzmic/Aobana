
    const LEARN_ICONS = {
      off:'<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
      first: '<path d="M6 20V5M3 8l3-3 3 3"/><path d="M12 6h8M12 12h6M12 18h4"/>',
      only: '<path d="M4 5h16l-6.2 7.4V19l-3.6-1.8v-4.8z"/>',
    };
    const learnIcon = v => `<svg class="dd-ico" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${LEARN_ICONS[v]}</svg>`;
    function renderLearnControl() {
      const el = document.getElementById('learn-select');
      const input = document.getElementById('learn-input');
      if (!el || !input) return;
      el.hidden = !KNOWN.available;
      input.value = LEARN;
      input.disabled = LEARN === 'off';
      if (!KNOWN.available) return;
      makeDropdown(el, {
        options: LEARNS.map(v => ({ value: v, label: t('learn_' + v), pre: learnIcon(v) })),
        value: LEARN, title: t('learn_title'),
        labelFor: o => `${learnIcon(o.value)}${esc(o.value === 'off' ? 'i+1' : o.label)}`,
        onChange: v => {
          store.set('learn', v);
          input.value = v;
          input.disabled = v === 'off';
          document.querySelector('form.search-bar').submit();
        },
      });
    }
    function knowledgeHtml(r) {
      const k = r.knowledge;
      if (!k) return '';
      if (store.get('known_counts', 'on') !== 'on') {
        return k.i1 ? `<span class="known-count"><span class="known-ratio is-i1" aria-label="${esc(t('known_i1_aria'))}">i+1</span></span>` : '';
      }
      const ratio = `${k.known}/${k.total}`;
      const text = esc(t('known_count', { known: k.known, total: k.total }))
        .replace(ratio, `<span class="known-ratio${k.i1 ? ' is-i1' : ''}">${ratio}</span>`);
      return `<span class="known-count" aria-label="${esc(t('known_count_aria', { known: k.known, total: k.total }))}">${text}</span>`;
    }
    function updateLearnNote(data) {
      const note = document.getElementById('learn-note');
      if (!note) return;
      const l = data && data.learn;
      let text = '';
      try {
        if (sessionStorage.getItem('aobana_learn_removed')) { text = t('learn_removed'); sessionStorage.removeItem('aobana_learn_removed'); }
      } catch (e) {}
      if (!text && l && l.unsupported) text = t('learn_unsupported');
      else if (!text && l && l.target_known) text = t('learn_target_known', { word: PARAMS.get('q') || '' });
      note.textContent = text;
      note.hidden = !text;
    }
    function learnUnavailable() {
      store.set('learn', 'off');
      try { sessionStorage.setItem('aobana_learn_removed', '1'); } catch (e) {}
      const p = new URLSearchParams(location.search);
      p.delete('learn');
      location.replace('/?' + p.toString());
    }

    function renderKnownWords(msg) {
      const el = document.getElementById('set-known-words');
      if (!el) return;
      const counts = store.get('known_counts', 'on') === 'on';
      const sources = KNOWN.sources || [];
      const rows = sources.map(s => {
        const sel = s.origin === 'anki' && s.meta && s.meta.anki;
        const rule = sel ? ' · ' + t('anki_rule_note_' + sel.rule.kind, { ivl: sel.rule.ivl }) : '';
        return `<div class="known-source" data-id="${esc(s.id)}">
          <div class="known-source-name"><strong>${esc(s.name)}</strong>
            <span class="muted">${esc(t('known_source', { words: fmt(s.words), date: String(s.imported || '').slice(0, 10) }) + rule)}</span></div>
          <div class="known-source-btns">
            ${sel ? `<button type="button" class="btn" onclick="updateAnkiList('${esc(s.id)}', this)">${esc(t('anki_update'))}</button>
            <button type="button" class="btn" onclick="openAnkiDialog(this, '${esc(s.id)}')">${esc(t('anki_change'))}</button>` : ''}
            <button type="button" class="btn" onclick="askRemoveKnown('${esc(s.id)}')">${esc(t('known_remove'))}</button>
          </div>
          <div class="known-source-ask" hidden></div>
        </div>`;
      }).join('');
      el.innerHTML = `
        <h3>${esc(t('known_title'))}</h3>
        <div class="facts"><div>${esc(t('known_lead'))}</div></div>
        ${rows ? `<div class="known-sources">${rows}</div>
          <div class="facts known-total"><div>${esc(t('known_total', { n: fmt(KNOWN.words) }))}</div></div>`
          : `<div class="facts"><div>${esc(t('known_none'))}</div></div>`}
        ${KNOWN.available ? `<div class="set-sub-tags">
          <div class="facts">${esc(t('known_counts'))}</div>
          <div class="seg seg-fit" style="margin-top:0.4em;">
            <button type="button" class="seg-btn ${counts ? '' : 'active'}" onclick="setKnownCounts(false)">${esc(t('lib_cache_off'))}</button>
            <button type="button" class="seg-btn ${counts ? 'active' : ''}" onclick="setKnownCounts(true)">${esc(t('lib_cache_on'))}</button>
          </div></div>` : ''}
        <div class="btns known-actions">
          <button type="button" class="btn primary" onclick="pickKnownList()">${esc(t('known_import'))}</button>
          <button type="button" class="btn" onclick="openAnkiDialog(this)">${esc(t('known_reibun'))}</button>
        </div>
        <div class="facts known-formats"><div>${esc(t('known_formats'))}</div></div>
        <div class="known-preview" hidden></div>
        <div class="known-msg" role="status">${msg || ''}</div>`;
      renderLearnControl();
    }
    function setKnownCounts(on) {
      store.set('known_counts', on ? 'on' : 'off');
      renderKnownWords();
    }
    function knownMessage(html) {
      const box = document.querySelector('#set-known-words .known-msg');
      if (box) box.innerHTML = html;
    }
    function knownError(res) {
      const code = res && res.error;
      const key = 'known_err_' + code;
      const text = I18N.ja[key] ? t(key, (res && res.detail) || {}) : t('error');
      return `<div class="notice err" role="alert">${esc(text)}</div>`;
    }
    let knownFile = null;
    function pickKnownList() {
      const picker = document.createElement('input');
      picker.type = 'file';
      picker.accept = '.txt,.tsv,.csv,.json';
      picker.addEventListener('change', () => {
        if (!picker.files || !picker.files[0]) return;
        knownFile = picker.files[0];
        previewKnownList({});
      });
      picker.click();
    }
    function knownForm(options) {
      const form = new FormData();
      form.append('file', knownFile, knownFile.name);
      for (const [k, v] of Object.entries(options || {})) if (v !== undefined && v !== null) form.append(k, String(v));
      return form;
    }
    async function postKnown(url, options) {
      try {
        const r = await fetch(url, { method: 'POST', headers: { 'X-Aobana': '1' }, body: knownForm(options) });
        return await r.json();
      } catch (e) { return { error: 'network' }; }
    }
    let knownOptions = {};
    async function previewKnownList(options) {
      knownOptions = options;
      knownMessage('');
      const box = document.querySelector('#set-known-words .known-preview');
      const res = await postKnown('/api/known-words/preview', options);
      if (res.error === 'migaku_confirm' && !options.migaku_known) {
        box.innerHTML = `<div class="known-file"><strong>${esc(knownFile.name)}</strong></div>
          <div class="notice">${esc(t('known_err_migaku_confirm'))}</div>
          <div class="btns">
            <button type="button" class="btn primary" onclick="previewKnownList({ ...knownOptions, migaku_known: 1 })">${esc(t('known_migaku_yes'))}</button>
            <button type="button" class="btn" onclick="cancelKnownList()">${esc(t('lib_cancel'))}</button>
          </div>`;
        box.hidden = false;
        return;
      }
      if (res.error) { box.hidden = true; knownMessage(knownError(res)); return; }
      const cols = res.columns || null;
      const select = (id, value, none) => `<select id="${id}" onchange="changeKnownColumns()">
          ${none ? `<option value="" ${value == null ? 'selected' : ''}>${esc(t('known_col_none'))}</option>` : ''}
          ${cols.map((c, i) => `<option value="${i}" ${value === i ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>`;
      const sample = (res.sample || []).map(s => `<span class="known-sample">${esc(s.expression)}${s.reading ? `<span class="muted">（${esc(s.reading)}）</span>` : ''}</span>`).join('');
      box.innerHTML = `
        <div class="known-file"><strong>${esc(knownFile.name)}</strong> <span class="muted">${esc(t('known_entries', { n: fmt(res.entries) }))}</span></div>
        ${cols ? `<div class="known-cols">
          <label>${esc(t('known_col_word'))} ${select('known-col-word', res.column, false)}</label>
          <label>${esc(t('known_col_reading'))} ${select('known-col-reading', res.reading_column, true)}</label>
        </div>` : ''}
        <div class="known-samples">${sample}</div>
        <div class="btns">
          <button type="button" class="btn primary" onclick="importKnownList(this)">${esc(t('known_do_import'))}</button>
          <button type="button" class="btn" onclick="cancelKnownList()">${esc(t('lib_cancel'))}</button>
        </div>`;
      box.hidden = false;
    }
    function changeKnownColumns() {
      const word = document.getElementById('known-col-word');
      const reading = document.getElementById('known-col-reading');
      previewKnownList({ column: word ? word.value : undefined, reading_column: reading && reading.value !== '' ? reading.value : -1,
                         migaku_known: knownOptions.migaku_known });
    }
    function cancelKnownList() {
      knownFile = null;
      const box = document.querySelector('#set-known-words .known-preview');
      if (box) { box.hidden = true; box.innerHTML = ''; }
      knownMessage('');
    }
    async function importKnownList(button) {
      if (!knownFile) return;
      button.disabled = true;
      const res = await postKnown('/api/known-words/import', { ...knownOptions, name: knownFile.name.replace(/\.[^.]+$/, '') });
      button.disabled = false;
      if (res.error) { knownMessage(knownError(res)); return; }
      KNOWN = res;
      knownFile = null;
      renderKnownWords(`<div class="notice ok" role="status">${esc(t('known_imported', { name: res.source.name, words: fmt(res.source.words) }))}</div>`);
    }
    function knownRow(id) {
      return [...document.querySelectorAll('#set-known-words .known-source')].find(r => r.dataset.id === id);
    }
    function askRemoveKnown(id) {
      const row = knownRow(id);
      const s = (KNOWN.sources || []).find(x => x.id === id);
      if (!row || !s) return;
      row.querySelector('.known-source-btns').hidden = true;
      const ask = row.querySelector('.known-source-ask');
      ask.hidden = false;
      ask.innerHTML = `<div class="notice">${esc(t('known_remove_confirm', { name: s.name, words: fmt(s.words) }))}</div>
        <div class="btns">
          <button type="button" class="btn primary" onclick="removeKnownList('${esc(id)}', this)">${esc(t('known_remove_yes'))}</button>
          <button type="button" class="btn" onclick="cancelRemoveKnown('${esc(id)}')">${esc(t('lib_cancel'))}</button>
        </div>`;
    }
    function cancelRemoveKnown(id) {
      const row = knownRow(id);
      if (!row) return;
      row.querySelector('.known-source-ask').hidden = true;
      row.querySelector('.known-source-btns').hidden = false;
    }
    async function removeKnownList(id, button) {
      button.disabled = true;
      let res;
      try {
        res = await fetch('/api/known-words/' + encodeURIComponent(id), { method: 'DELETE', headers: { 'X-Aobana': '1' } }).then(r => r.json());
      } catch (e) { res = { error: 'network' }; }
      if (res.error) { button.disabled = false; knownMessage(knownError(res)); return; }
      KNOWN = res;
      if (!KNOWN.available) store.set('learn', 'off');
      renderKnownWords();
    }

    const anki = { decks: [], ticked: new Set(), subdecks: true, rule: { kind: 'mature', ivl: 21 },
                   noteTypes: [], fields: {}, replace: null, filter: '', timer: 0, seq: 0 };
    async function ankiFetch(url, body) {
      try {
        const init = body === undefined ? { headers: { 'X-Aobana': '1' } }
          : { method: 'POST', headers: { 'X-Aobana': '1', 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
        return await (await fetch(url, init)).json();
      } catch (e) { return { error: 'network' }; }
    }
    function ankiError(res) {
      const key = 'anki_err_' + (res && res.error);
      if (I18N.ja[key]) return `<div class="notice err" role="alert">${esc(t(key, (res && res.detail) || {}))
        .replace('Aobana Reibun', '<a href="/?tab=guide#reibun">Aobana Reibun</a>')}</div>`;
      return knownError(res);
    }
    async function openAnkiDialog(button, sid) {
      button.disabled = true;
      knownMessage(`<div class="notice">${esc(t('loading'))}</div>`);
      const res = await ankiFetch('/api/anki/decks');
      const sel = !res.error && sid ? await ankiFetch('/api/anki/selection/' + encodeURIComponent(sid)) : null;
      button.disabled = false;
      if (res.error || (sel && sel.error)) { knownMessage(ankiError(res.error ? res : sel)); return; }
      knownMessage('');
      Object.assign(anki, {
        decks: res.decks || [], replace: sid || null, filter: '', noteTypes: [],
        ticked: new Set(sel ? sel.decks.map(d => d.id) : []),
        subdecks: sel ? sel.subdecks !== false : true,
        rule: sel ? { kind: sel.rule.kind, ivl: sel.rule.ivl || 21 } : { kind: 'mature', ivl: 21 },
        fields: sel ? { ...sel.fields } : {},
      });
      const title = document.getElementById('anki-title');
      title.dataset.i18n = sid ? 'anki_title_change' : 'anki_title';
      title.textContent = t(title.dataset.i18n);
      renderAnkiDialog(res.profile || '');
      document.getElementById('anki-modal').classList.add('open');
      document.documentElement.style.overflow = 'hidden';
      ankiChanged(true);
    }
    function closeAnkiDialog() {
      document.getElementById('anki-modal').classList.remove('open');
      document.documentElement.style.overflow = '';
      anki.seq++;
      clearTimeout(anki.timer);
    }
    function ankiCovered(name) {
      return anki.subdecks && anki.decks.some(d => anki.ticked.has(d.id) && name.startsWith(d.name + '::'));
    }
    function ankiSelection() {
      const decks = anki.decks.filter(d => anki.ticked.has(d.id) && !ankiCovered(d.name)).map(d => ({ id: d.id, name: d.name }));
      const fields = {};
      for (const nt of anki.noteTypes) if (anki.fields[nt.id]) fields[nt.id] = anki.fields[nt.id];
      return { decks, subdecks: anki.subdecks, rule: anki.rule, fields };
    }
    function renderAnkiDialog(profile) {
      const rule = anki.rule;
      document.getElementById('anki-body').innerHTML = `
        <div class="facts"><div>${esc(t('anki_lead'))}</div>${profile ? `<div class="muted">${esc(t('anki_profile', { name: profile }))}</div>` : ''}</div>
        <h4>${esc(t('anki_decks'))}</h4>
        <div class="anki-deck-tools">
          <input type="search" class="anki-filter" placeholder="${esc(t('anki_filter'))}" aria-label="${esc(t('anki_filter'))}" oninput="filterAnkiDecks(this.value)">
          <label class="anki-check"><input type="checkbox" ${anki.subdecks ? 'checked' : ''} onchange="setAnkiSubdecks(this.checked)"> ${esc(t('anki_subdecks'))}</label>
        </div>
        <div class="anki-decks"></div>
        <h4>${esc(t('anki_rule'))}</h4>
        <div class="anki-rules">
          <label class="anki-check"><input type="radio" name="anki-rule" value="mature" ${rule.kind === 'mature' ? 'checked' : ''} onchange="setAnkiRule('mature')">
            ${esc(t('anki_rule_mature'))} <input type="number" class="anki-ivl" min="1" max="36500" value="${esc(String(rule.ivl || 21))}" aria-label="${esc(t('anki_days'))}" oninput="setAnkiIvl(this.value)"> ${esc(t('anki_days'))}</label>
          <label class="anki-check"><input type="radio" name="anki-rule" value="reviewed" ${rule.kind === 'reviewed' ? 'checked' : ''} onchange="setAnkiRule('reviewed')"> ${esc(t('anki_rule_reviewed'))}</label>
          <label class="anki-check"><input type="radio" name="anki-rule" value="all" ${rule.kind === 'all' ? 'checked' : ''} onchange="setAnkiRule('all')"> ${esc(t('anki_rule_all'))}</label>
        </div>
        <div class="anki-fields"></div>
        <div class="anki-preview" role="status"></div>
        <div class="btns">
          <button type="button" class="btn primary" id="anki-import" onclick="importAnkiDecks(this)" disabled>${esc(t(anki.replace ? 'anki_save' : 'anki_import'))}</button>
          <button type="button" class="btn" onclick="closeAnkiDialog()">${esc(t('lib_cancel'))}</button>
        </div>`;
      renderAnkiDecks();
    }
    function renderAnkiDecks() {
      const box = document.querySelector('#anki-body .anki-decks');
      if (!box) return;
      const top = box.scrollTop;
      const f = anki.filter.toLowerCase();
      box.innerHTML = anki.decks.filter(d => !f || d.name.toLowerCase().includes(f)).map(d => {
        const parts = d.name.split('::');
        const covered = ankiCovered(d.name);
        const notes = anki.subdecks && d.subtree_notes != null ? d.subtree_notes : d.notes;
        return `<label class="anki-deck" style="--depth:${f ? 0 : parts.length - 1}">
          <input type="checkbox" ${covered || anki.ticked.has(d.id) ? 'checked' : ''} ${covered ? 'disabled' : ''} onchange="tickAnkiDeck(${d.id}, this.checked)">
          <span class="anki-deck-name">${esc(f ? d.name : parts[parts.length - 1])}</span>
          <span class="muted">${esc(t('anki_notes', { n: fmt(notes) }))}</span></label>`;
      }).join('');
      box.scrollTop = top;
    }
    function renderAnkiFields() {
      const box = document.querySelector('#anki-body .anki-fields');
      if (!box) return;
      if (!anki.noteTypes.length) { box.innerHTML = ''; return; }
      const select = (nt, key, none) => `<select onchange="setAnkiField(${nt.id}, '${key}', this.value)">
          ${none ? `<option value="">${esc(t('known_col_none'))}</option>` : ''}
          ${nt.fields.map(f => `<option value="${esc(f)}" ${(anki.fields[nt.id] || {})[key] === f ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select>`;
      box.innerHTML = `<h4>${esc(t('anki_fields'))}</h4>` + anki.noteTypes.map(nt => `<div class="anki-nt">
          <div><strong>${esc(nt.name)}</strong> <span class="muted">${esc(t('anki_notes', { n: fmt(nt.notes) }))}</span></div>
          <div class="known-cols">
            <label>${esc(t('anki_field_word'))} ${select(nt, 'expression', false)}</label>
            <label>${esc(t('anki_field_reading'))} ${select(nt, 'reading', true)}</label>
          </div></div>`).join('');
    }
    function tickAnkiDeck(id, on) {
      if (on) anki.ticked.add(id); else anki.ticked.delete(id);
      renderAnkiDecks();
      ankiChanged(true);
    }
    function setAnkiSubdecks(on) { anki.subdecks = on; renderAnkiDecks(); ankiChanged(true); }
    function filterAnkiDecks(value) { anki.filter = value || ''; renderAnkiDecks(); }
    function setAnkiRule(kind) { anki.rule = { ...anki.rule, kind }; ankiChanged(false); }
    function setAnkiIvl(value) {
      const ivl = parseInt(value, 10);
      if (ivl >= 1 && ivl <= 36500) { anki.rule = { ...anki.rule, ivl }; ankiChanged(false); }
    }
    function setAnkiField(mid, key, value) {
      anki.fields[mid] = { ...(anki.fields[mid] || {}), [key]: value };
      ankiChanged(false);
    }
    async function ankiChanged(decksChanged) {
      clearTimeout(anki.timer);
      const seq = ++anki.seq;
      if (decksChanged) anki.fieldsWanted = true;
      const preview = document.querySelector('#anki-body .anki-preview');
      const button = document.getElementById('anki-import');
      if (button) button.disabled = true;
      if (!ankiSelection().decks.length && !anki.fieldsWanted) return;
      if (!anki.ticked.size) {
        anki.noteTypes = [];
        anki.fieldsWanted = false;
        renderAnkiFields();
        if (preview) preview.innerHTML = `<div class="facts"><div>${esc(t('anki_choose'))}</div></div>`;
        return;
      }
      if (preview) preview.innerHTML = `<div class="facts"><div>${esc(t('loading'))}</div></div>`;
      if (anki.fieldsWanted) {
        const res = await ankiFetch('/api/anki/fields', { decks: ankiSelection().decks.map(d => d.id), subdecks: anki.subdecks });
        if (seq !== anki.seq) return;
        if (res.error) { if (preview) preview.innerHTML = ankiError(res); return; }
        anki.fieldsWanted = false;
        anki.noteTypes = res.note_types || [];
        for (const nt of anki.noteTypes) {
          const mine = anki.fields[nt.id];
          if (!mine || !nt.fields.includes(mine.expression)) anki.fields[nt.id] = { expression: nt.expression, reading: nt.reading };
        }
        renderAnkiFields();
      }
      anki.timer = setTimeout(async () => {
        if (seq !== anki.seq) return;
        const res = await ankiFetch('/api/anki/preview', ankiSelection());
        if (seq !== anki.seq || !preview) return;
        if (res.error) { preview.innerHTML = ankiError(res); return; }
        const sample = (res.sample || []).map(s => `<span class="known-sample">${esc(s.expression)}${s.reading ? `<span class="muted">（${esc(s.reading)}）</span>` : ''}</span>`).join('');
        preview.innerHTML = `<div class="known-file"><strong>${esc(t('anki_preview', { notes: fmt(res.notes), words: fmt(res.entries) }))}</strong>
            ${res.skipped ? `<span class="muted">${esc(t('anki_skipped', { n: fmt(res.skipped) }))}</span>` : ''}</div>
          ${res.gone && res.gone.length ? `<div class="notice">${esc(t('anki_gone', { decks: res.gone.join(', ') }))}</div>` : ''}
          <div class="known-samples">${sample}</div>`;
        if (button) button.disabled = false;
      }, 350);
    }
    async function importAnkiDecks(button) {
      button.disabled = true;
      const res = await ankiFetch('/api/anki/import', { selection: ankiSelection(), replace: anki.replace });
      if (res.error) {
        button.disabled = false;
        const preview = document.querySelector('#anki-body .anki-preview');
        if (preview) preview.innerHTML = ankiError(res);
        return;
      }
      KNOWN = res;
      const done = anki.replace ? 'anki_changed' : 'known_imported';
      closeAnkiDialog();
      renderKnownWords(`<div class="notice ok" role="status">${esc(t(done, { name: res.source.name, words: fmt(res.source.words) }))}</div>`);
    }
    async function updateAnkiList(id, button) {
      button.disabled = true;
      knownMessage(`<div class="notice">${esc(t('loading'))}</div>`);
      const res = await ankiFetch('/api/anki/update/' + encodeURIComponent(id), {});
      button.disabled = false;
      if (res.error) { knownMessage(ankiError(res)); return; }
      KNOWN = res;
      const gone = res.gone && res.gone.length ? ` ${t('anki_gone', { decks: res.gone.join(', ') })}` : '';
      renderKnownWords(`<div class="notice ok" role="status">${esc(t('anki_updated', { name: res.source.name, words: fmt(res.source.words) }) + gone)}</div>`);
    }

