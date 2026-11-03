    function renderBatches() {
      const resultsContainer = document.getElementById('results');
      const emptyState = document.getElementById('empty-state');
      resultsContainer.innerHTML = '';
      starRows.clear();

      if (allResults.length === 0) {
        emptyState.style.display = 'block';
        if (observer) observer.disconnect();
        return;
      } else {
        emptyState.style.display = 'none';
      }

      const numBatches = Math.ceil(allResults.length / BATCH_SIZE);
      for (let i = 0; i < numBatches; i++) {
        const wrapper = document.createElement('div');
        wrapper.className = 'batch-wrapper';
        wrapper.dataset.index = i;
        wrapper.innerHTML = buildBatchHTML(i);
        resultsContainer.appendChild(wrapper);
      }
    }

    function setupLoadMoreSentinel() {
      const resultsContainer = document.getElementById('results');
      let sentinel = document.getElementById('load-more-sentinel');
      if (!sentinel) {
          sentinel = document.createElement('div');
          sentinel.id = 'load-more-sentinel';
          resultsContainer.insertAdjacentElement('afterend', sentinel);
      }

      if (!hasMoreResults && !allResults.length) {
          sentinel.innerHTML = '';
      } else if (!hasMoreResults) {
          sentinel.innerHTML = `<div class="status-line" style="padding-top:4em;">${esc(t('no_more'))}</div>`;
      } else {
          sentinel.innerHTML = '';
      }

      if (loadMoreObserver) loadMoreObserver.disconnect();

      loadMoreObserver = new IntersectionObserver(async (entries) => {
          if (entries[0].isIntersecting && hasMoreResults && !isFetchingMore) {
              isFetchingMore = true;
              setTimeout(async () => {
                  isFetchingMore = false;
                  await fetchMoreResults();
              }, 150);
          }
      }, { rootMargin: '500px 0px 500px 0px' });

      loadMoreObserver.observe(sentinel);
    }

    async function fetchMoreResults() {
        if (!hasMoreResults || isFetchingMore) return;
        isFetchingMore = true;
        const myGen = searchGen;
        const sentinel = document.getElementById('load-more-sentinel');

        serverSearchInFlight++;
        try {
            sentinel.innerHTML = `<div class="status-line" style="padding:1.5em;">${esc(t('loading'))}</div>`;

            const response = await fetch(apiSearchUrl(`${searchParams().toString()}&limit=500&offset=${currentOffset}`));
            const data = await response.json();

            if (myGen !== searchGen) {
                return;
            }
            if (data.busy) {
                sentinel.innerHTML = busyLine('1.5em');
                return;
            }

            if (data.results.length > 0) {
                const startIndex = allResults.length;
                allResults = allResults.concat(data.results);
                updateReadingNote();
                hasMoreResults = data.has_more;
                currentOffset += 500;
                appendBatches(startIndex, data.results.length);
            } else {
                hasMoreResults = false;
            }

            if (!hasMoreResults) {
                sentinel.innerHTML = `<div class="status-line" style="padding:1.5em;">${esc(t('no_more'))}</div>`;
            } else {
                sentinel.innerHTML = '';
                const rect = sentinel.getBoundingClientRect();
                if (rect.top < window.innerHeight + 500) {
                    setTimeout(fetchMoreResults, 100);
                }
            }
        } catch (err) {
            console.error("Fetch more error:", err);
            sentinel.innerHTML = '';
        } finally {
            serverSearchInFlight = Math.max(0, serverSearchInFlight - 1);
            isFetchingMore = false;
        }
    }

    function appendBatches(startIndex, count) {
      const resultsContainer = document.getElementById('results');
      const startBatch = Math.floor(startIndex / BATCH_SIZE);
      const endBatch = Math.ceil((startIndex + count) / BATCH_SIZE);

      for (let i = startBatch; i < endBatch; i++) {
        if (!document.querySelector(`.batch-wrapper[data-index="${i}"]`)) {
            const wrapper = document.createElement('div');
            wrapper.className = 'batch-wrapper';
            wrapper.dataset.index = i;
            wrapper.innerHTML = buildBatchHTML(i);
            resultsContainer.appendChild(wrapper);
        }
      }
    }

    const starRows = new Map();
    let starSeq = 0;
    function starKey(item) { const k = String(++starSeq); starRows.set(k, item); return k; }
    function starRow(btn) {
      const item = btn && starRows.get(btn.dataset.star);
      return item ? JSON.parse(JSON.stringify(item)) : null;
    }

    const isSubs = r => (r.media_type || 'subs') === 'subs';
    function buildBatchHTML(batchIndex) {
      const start = batchIndex * BATCH_SIZE;
      const end = Math.min(start + BATCH_SIZE, allResults.length);
      const currentQ = PARAMS.get('q') || '';
      let html = '';
      for (let i = start; i < end; i++) {
        const r = allResults[i];
        const rId = lineId(r.line);
        const isSaved = savedSentences.some(s => s.id === rId);

        const savedItemData = {...r, id: rId};
        if (!savedItemData.original_q) savedItemData.original_q = currentQ;

        html += `
        <div class="card" id="card-${rId}">
          <div class="card-meta">
            <div class="src">${withCopy(srcWithReveal(r))}</div>
            <div class="chars">${knowledgeHtml(r)}${r.char_count !== undefined ? esc(t('chars', { n: r.char_count })) : ''}</div>
          </div>
          <div class="file-title">
            <span class="main-sentence">${isSubs(r) ? markSubTags(r.display_line) : r.display_line}</span>
            <div class="actions-box">
              <button class="icon-btn ${isSaved ? 'star-active' : ''}" onclick="toggleSave('${rId}', this)" data-star="${starKey(savedItemData)}" aria-label="${esc(t('sc_save'))}">
                <span>★</span>
              </button>
              <button class="icon-btn" onclick="toggleContext(this)" aria-label="${esc(t('sc_context'))}" data-rowid="${r.rowid}" data-file="${encodeURIComponent(r.file)}" data-media="${esc(r.media_type || '')}" data-saved-context="${r.context ? encodeURIComponent(r.context) : ''}">
                <span>⋯</span>
              </button>
            </div>
          </div>
          <div class="context">${r.context ? r.context : ''}</div>
        </div>
        `;
      }
      return html;
    }

    async function toggleContext(btn) {
      const card = btn.closest('.card');
      const ctx = card ? card.querySelector('.context') : btn.parentElement.parentElement.nextElementSibling;
      const isHidden = window.getComputedStyle(ctx).display === 'none';
      if (isHidden) {
        // A favorite's saved context is from an older window: fetched again, kept only for a failed fetch
        const savedCtx = btn.dataset.savedContext;
        if (!ctx.dataset.loaded) {
          ctx.innerHTML = `<div class="status-line">${esc(t('loading'))}</div>`;
          ctx.style.display = 'block';
          ctx.classList.remove('anim-close');
          ctx.classList.add('anim-open');
          try {
            const rowid = btn.dataset.rowid;
            const fileEnc = btn.dataset.file;
            let q = PARAMS.get('q') || '';
            try {
               const starBtn = card?.querySelector('[data-star]') || btn.previousElementSibling;
               const btnData = starRow(starBtn);
               if (btnData && btnData.original_q) q = btnData.original_q;
            } catch(e) {}
            const media = btn.dataset.media ? `&media=${encodeURIComponent(btn.dataset.media)}` : '';
            const res = await fetch(`/api/context?rowid=${rowid}&file=${fileEnc}&q=${encodeURIComponent(q)}${media}&before=3&after=3`);
            // Not kept as loaded: opened again after the run, it reads the context
            if (await busyAnswer(res)) { ctx.innerHTML = savedCtx ? decodeURIComponent(savedCtx) : busyLine('0.5em 0'); return; }
            const data = await res.json();
            if (data.context) {
              ctx.innerHTML = (btn.dataset.media || 'subs') === 'subs' ? markSubTags(data.context) : data.context;
            } else if (savedCtx) {
              ctx.innerHTML = decodeURIComponent(savedCtx);
            } else {
              ctx.innerHTML = `<div class="error-text">${esc(t('error'))}</div>`;
            }
            ctx.dataset.loaded = 'true';
          } catch (e) {
            ctx.innerHTML = savedCtx ? decodeURIComponent(savedCtx) : `<div class="error-text">${esc(t('load_failed'))}</div>`;
          }
        } else {
          ctx.style.display = 'block';
          ctx.classList.remove('anim-open');
          ctx.classList.add('anim-open');
        }
      } else {
        ctx.classList.remove('anim-open');
        ctx.classList.add('anim-close');
        setTimeout(() => {
          if (ctx.classList.contains('anim-close')) {
            ctx.style.display = 'none';
            ctx.classList.remove('anim-close');
          }
        }, 140);
      }
    }

    const ICON_MEDIA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5M16 4v5"/></svg>';
    function openInMediaIconHTML(r) {
      if (!['subs', 'epub', 'manga', 'custom'].includes(r.media_type || 'subs') || !r.file || !r.rowid) return '';
      const label = esc(t('open_in_media'));
      return `<button type="button" class="reveal-btn" onclick="openInMedia(this, event)" aria-label="${label}" title="${label}">${ICON_MEDIA}</button>`;
    }

    async function openInMedia(el, event) {
      if (event) event.stopPropagation();
      const card = el.closest('.card');
      const ctxBtn = card && card.querySelector('button[onclick*="toggleContext"]');
      const row = ctxBtn && starRow(ctxBtn.previousElementSibling);
      if (!row) return;
      el.disabled = true;
      let got = {};
      try { got = await readerAtUrl(row); } catch (e) {}
      el.disabled = false;
      // The card's context box says so; it reads the context again when opened next
      const ctx = got.busy && card && card.querySelector('.context');
      if (ctx) {
        ctx.innerHTML = busyLine('0.5em 0');
        ctx.style.display = 'block';
        delete ctx.dataset.loaded;
        return;
      }
      if (!got.url) return;
      saveSearchReturn(card);
      window.location.href = got.url;
    }

    const SEARCH_RETURN = 'aobana_search_return';
    function saveSearchReturn(card) {
      const cards = [...document.querySelectorAll('#results .card')];
      const state = { url: location.pathname + location.search, tab: TAB, count: allResults.length,
        index: cards.indexOf(card), dy: Math.round(card.getBoundingClientRect().top) };
      try { sessionStorage.setItem(SEARCH_RETURN, JSON.stringify(state)); } catch (e) {}
    }
    async function restoreSearchReturn() {
      let s = null;
      try { s = JSON.parse(sessionStorage.getItem(SEARCH_RETURN) || 'null'); sessionStorage.removeItem(SEARCH_RETURN); } catch (e) {}
      if (!s || s.url !== location.pathname + location.search || s.tab !== TAB || s.index < 0) return;
      for (let tries = 0; allResults.length < s.count && hasMoreResults && tries < 200; tries++) {
        if (isFetchingMore) { await new Promise(r => setTimeout(r, 100)); continue; }
        await fetchMoreResults();
      }
      const card = document.querySelectorAll('#results .card')[s.index];
      if (!card) return;
      window.scrollBy(0, card.getBoundingClientRect().top - s.dy);
      const ctxBtn = card.querySelector('button[onclick*="toggleContext"]');
      if (ctxBtn) await toggleContext(ctxBtn);
      window.scrollBy(0, card.getBoundingClientRect().top - s.dy);
    }
    // A page the browser kept whole needs nothing, and a later reload must not jump
    window.addEventListener('pageshow', e => { if (e.persisted) try { sessionStorage.removeItem(SEARCH_RETURN); } catch (_) {} });

    const unstarredAt = new Map();
    function toggleSave(id, btn) {
      const isSaved = btn.classList.contains('star-active');
      const data = starRow(btn);
      if (!data) return;

      if (isSaved) {
        const at = savedSentences.findIndex(s => s.id === id);
        if (TAB === 'saved' && at >= 0) unstarredAt.set(id, at);
        savedSentences = savedSentences.filter(s => s.id !== id);
        btn.classList.remove('star-active');
      } else if (TAB === 'saved' && unstarredAt.has(id)) {
        savedSentences.splice(Math.min(unstarredAt.get(id), savedSentences.length), 0, data);
        unstarredAt.delete(id);
        btn.classList.add('star-active');
      } else {
        savedSentences.unshift(data);
        btn.classList.add('star-active');
      }
      store.set('savedSentences', JSON.stringify(savedSentences));

      if (TAB === 'saved') document.getElementById('saved-meta').textContent = t('saved_count', { n: fmt(savedSentences.length) });
    }

    function initSavedTab() {
      setTitle(t('tab_saved'));
      document.getElementById('saved-head').after(document.getElementById('empty-state'), document.getElementById('results'));
      showSavedSentences();
      // After the relocation, which draws the list again
      relocateSaved().catch(() => {}).finally(restoreSearchReturn);
    }

    async function relocateSaved() {
      const items = savedSentences.map(s => ({ rowid: s.rowid, file: s.file, line: s.line, media_type: s.media_type }));
      if (!items.length) return;
      // The server reads 5,000 a request (RELOCATE_MAX): more go in batches (audit 10, F54)
      const answers = [];
      for (let at = 0; at < items.length; at += 5000) {
        const res = await apiPost('/api/relocate', { items: items.slice(at, at + 5000) }).catch(() => null);
        if (!res || !Array.isArray(res.items)) return;
        answers.push(...res.items);
      }
      let moved = 0;
      const gone = new Set();
      answers.forEach((u, i) => {
        if (!u || !savedSentences[i]) return;
        if (u.gone) gone.add(i);
        else { savedSentences[i].rowid = u.rowid; savedSentences[i].file = u.file; }
        moved++;
      });
      if (!moved) return;
      savedSentences = savedSentences.filter((s, i) => !gone.has(i));
      store.set('savedSentences', JSON.stringify(savedSentences));
      if (TAB === 'saved') showSavedSentences();
    }

    function showSavedSentences() {
      allResults = savedSentences;
      document.getElementById('saved-meta').textContent = t('saved_count', { n: fmt(savedSentences.length) });
      const empty = document.getElementById('empty-state');
      empty.dataset.i18n = 'no_saved';
      empty.textContent = t('no_saved');
      renderBatches();
    }

    function pageLabel(r) {
      const label = esc(t('page_n', { n: fmt(r.page) }));
      if (r.media_type !== 'manga' || !r.rowid) return label;
      return `<a class="page-link" href="/manga/view/${Number(r.rowid)}" target="aobana-manga-page" title="${esc(t('page_open'))}">${label}</a>`;
    }

    const REVEAL_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 6A1.5 1.5 0 0 1 4.5 4.5h4.6l2 2.2h8.4A1.5 1.5 0 0 1 21 8.2v9.8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18z"/></svg>';
    function revealIconHTML(media, file, folder = '') {
      if (ON_PHONE || !['subs', 'epub', 'manga', 'custom'].includes(media) || (!file && !folder)) return '';
      const target = file ? `data-file="${encodeURIComponent(file)}"` : `data-folder="${encodeURIComponent(folder)}"`;
      return `<button type="button" class="reveal-btn" data-media="${esc(media)}" ${target} onclick="revealInFolder(event, this)" aria-label="${esc(t('reveal'))}" title="${esc(t('reveal'))}">${REVEAL_SVG}</button>`;
    }

    function srcWithReveal(r) {
      const title = r.title || r.folder || '';
      const icon = openInMediaIconHTML(r);
      if (!icon) return `${esc(title)}${r.page ? ' · ' + pageLabel(r) : ''}`;
      if (r.page) return `${esc(title)} · <span class="reveal-glue">${pageLabel(r)}${icon}</span>`;
      const chars = [...title];
      const last = chars.pop() || '';
      return `${esc(chars.join(''))}<span class="reveal-glue">${esc(last)}${icon}</span>`;
    }

    const COPY_ICONS = {
      copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
      done: '<path d="M20 6 9 17l-5-5"/>'
    };
    const copyIcon = name => svgIcon(COPY_ICONS[name]);
    // Inside the source line's last glued span, so the buttons never wrap to a line of their own.
    function withCopy(src, more = '') {
      const label = esc(t('copy_sentence'));
      const buttons = `${more}<button type="button" class="reveal-btn text-copy" onclick="copySentence(this, event)" aria-label="${label}" title="${label}">${copyIcon('copy')}</button>`;
      return src.endsWith('</span>') ? src.slice(0, -7) + buttons + '</span>' : src + buttons;
    }
    // What the card shows: an element the page hides (furigana off, a speaker tag hidden) is left
    // out. The HTML keeps the ruby and the match: <b> where a Reibun card bolds it (the match, and
    // hl-tail; hl-tail-p is plain there). The text puts a reading in （）after its word.
    const copyBold = (tag, el) => tag === 'mark' || tag === 'b' || el.classList.contains('hl-tail');
    function copiedLine(node, html) {
      let out = '';
      for (const child of node.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) { out += html ? esc(child.data) : child.data; continue; }
        if (child.nodeType !== Node.ELEMENT_NODE || getComputedStyle(child).display === 'none') continue;
        const tag = child.tagName.toLowerCase();
        const inner = copiedLine(child, html);
        if (tag === 'br') out += html ? '<br>' : '\n';
        else if (html && inner && copyBold(tag, child)) out += `<b>${inner}</b>`;
        else if (html) out += tag === 'ruby' && !inner.includes('<rt>') || !['ruby', 'rt', 'rp', 'rb'].includes(tag) ? inner : `<${tag}>${inner}</${tag}>`;
        else if (tag === 'rt') out += inner ? `（${inner}）` : '';
        else if (tag !== 'rp') out += inner;
      }
      return out;
    }
    // One <b> for a match the page drew in pieces (食べ + させられた), as Reibun joins them
    const copiedHtml = line => copiedLine(line, true).trim().replace(/<\/b><b>/g, '');
    async function copySentence(button, event) {
      event?.preventDefault(); event?.stopPropagation();
      const line = button.closest('.card')?.querySelector('.file-title .main-sentence');
      if (!line) return;
      const html = copiedHtml(line), text = copiedLine(line, false).trim();
      if (!(await copyToClipboard(text, html))) return;
      copyDone(button, 'copy', 'copy_sentence');
    }
    async function copyToClipboard(text, html = '') {
      const types = {'text/plain': new Blob([text], {type: 'text/plain'})};
      if (html) types['text/html'] = new Blob([html], {type: 'text/html'});
      try { await navigator.clipboard.write([new ClipboardItem(types)]); return true; }
      catch (_) {
        // Not a secure page (the phone on the LAN): the old way, the copy event's own clipboard.
        const put = e => { e.clipboardData.setData('text/plain', text); if (html) e.clipboardData.setData('text/html', html); e.preventDefault(); };
        document.addEventListener('copy', put);
        try { return document.execCommand('copy'); } catch (_) { return false; }
        finally { document.removeEventListener('copy', put); }
      }
    }
    // Copied, or else `el` is selected, so a long press copies it (the update command, Reibun's code)
    async function copyOrSelect(text, el) {
      if (await copyToClipboard(text)) return true;
      const range = document.createRange(); range.selectNodeContents(el);
      const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range);
      return false;
    }
    function copyDone(button, icon, label) {
      clearTimeout(button._copied);
      button.innerHTML = copyIcon('done'); button.title = t('copied');
      button._copied = setTimeout(() => { button.innerHTML = copyIcon(icon); button.title = t(label); }, 1500);
    }

    async function revealInFolder(event, button) {
      if (event) event.stopPropagation();
      const body = { media: button.dataset.media };
      if (button.dataset.file) body.file = decodeURIComponent(button.dataset.file);
      if (button.dataset.folder) body.folder = decodeURIComponent(button.dataset.folder);
      if (button.dataset.check) body.check = decodeURIComponent(button.dataset.check);
      const res = await apiPost('/api/reveal', body).catch(() => ({ error: 'network' }));
      const row = button.closest('.episode-header');
      const scope = row ? row.parentElement : button.parentElement;
      const old = scope.querySelector(':scope > .reveal-msg');
      if (old) old.remove();
      if (!res.error) return;
      const msg = document.createElement('span');
      msg.className = 'reveal-msg warn';
      msg.textContent = ['not_found', 'not_indexed'].includes(res.error) ? t('reveal_err_gone') : t('reveal_err', { e: res.error });
      (row || button).after(msg);
      setTimeout(() => msg.remove(), 6000);
    }

