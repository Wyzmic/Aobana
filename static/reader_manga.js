    let rmMangaStageObs = null;
    let rmMangaStripObs = null;
    let rmMangaClickTimer = null;
    const rmPz = {
      scale: 1, fitScale: 1, tx: 0, ty: 0, imgW: 0, imgH: 0,
      dragging: false, captured: false, pointerId: null, moved: false,
      startX: 0, startY: 0, origTx: 0, origTy: 0,
    };

    // No button to undo a zoom: a double click or double tap does it.
    function rmSyncZoomPill() {
      const zoomed = rmState.media === 'manga' && rmPz.imgW > 0 && rmPz.scale > rmPz.fitScale * 1.04
        && !document.querySelector('#rm-manga-stage.rm-manga-strip');
      if (zoomed) rmSetEdgeHint(null);
    }

    function rmBuildMokuroPageEl(pg) {
      if (!pg.image_url) {
        const card = document.createElement('div');
        card.className = 'rm-manga-db-page';
        card.dataset.page = String(pg.page);
        const head = `<div class="rm-manga-db-head">${esc(t('page_n', { n: fmt(pg.page) }))}</div>`;
        const body = (pg.blocks || []).map(b => `<p class="rm-db-line">${b.html || esc(b.text || '')}</p>`).join('') || `<p class="muted">${esc(t('rm_no_content'))}</p>`;
        card.innerHTML = head + body;
        return card;
      }
      const pageEl = document.createElement('div');
      pageEl.className = 'rm-mokuro-page';
      pageEl.dataset.page = String(pg.page);
      const imgW = pg.img_width || 1000;
      const imgH = pg.img_height || 1400;
      pageEl.style.width = imgW + 'px';
      pageEl.style.height = imgH + 'px';
      pageEl.style.backgroundImage = `url("${pg.image_url}")`;

      const valid = (pg.blocks || []).filter(b => b.box && b.box.length === 4);
      const indexed = valid.map((b, i) => ({ b, i, area: Math.max(1, (b.box[2] - b.box[0]) * (b.box[3] - b.box[1])) }));
      indexed.sort((a, c) => c.area - a.area);
      const zMap = new Map();
      indexed.forEach((it, rank) => zMap.set(it.i, 10 + rank));

      valid.forEach((blk, idx) => {
        const [xmin, ymin, xmax, ymax] = blk.box;
        const w = Math.max(4, xmax - xmin);
        const h = Math.max(4, ymax - ymin);
        const fs = Math.max(12, Math.min(32, blk.font_size || 16));
        const boxEl = document.createElement('div');
        boxEl.className = 'rm-text-box';
        boxEl.style.left = xmin + 'px';
        boxEl.style.top = ymin + 'px';
        boxEl.style.width = w + 'px';
        boxEl.style.height = h + 'px';
        boxEl.style.fontSize = fs + 'px';
        boxEl.style.zIndex = String(zMap.get(idx) || 10);
        if (blk.vertical) boxEl.style.writingMode = 'vertical-rl';

        // One <p> per box, one inline span per OCR line: the line breaks come from CSS, so Yomitan reads a box as one sentence.
        const rawLines = (blk.lines && blk.lines.length) ? blk.lines : [blk.text || ''];
        const pEl = document.createElement('p');
        for (const ln of rawLines) {
          const lineEl = document.createElement('span');
          lineEl.className = 'rm-ocr-line';
          lineEl.textContent = ln;
          pEl.appendChild(lineEl);
        }
        boxEl.appendChild(pEl);
        boxEl.addEventListener('click', ev => {
          ev.stopPropagation();
          if (rmGetPrefs().manga_boxes === 'hover') {
            const was = boxEl.classList.contains('rm-hovered');
            pageEl.querySelectorAll('.rm-text-box.rm-hovered').forEach(x => x.classList.remove('rm-hovered'));
            if (!was) boxEl.classList.add('rm-hovered');
          }
        });
        pageEl.appendChild(boxEl);
      });
      return pageEl;
    }

    function rmApplyPzTransform() {
      const canvas = document.getElementById('rm-mokuro-canvas');
      const mStage = document.getElementById('rm-manga-stage');
      if (!canvas || !mStage || !rmPz.imgW || !rmPz.imgH) return;
      const sw = mStage.clientWidth;
      const sh = mStage.clientHeight;
      const cw = rmPz.imgW * rmPz.scale;
      const ch = rmPz.imgH * rmPz.scale;
      if (cw <= sw) rmPz.tx = (sw - cw) / 2;
      else rmPz.tx = Math.min(0, Math.max(sw - cw, rmPz.tx));
      if (ch <= sh) rmPz.ty = (sh - ch) / 2;
      else rmPz.ty = Math.min(0, Math.max(sh - ch, rmPz.ty));
      canvas.style.transform = `translate(${rmPz.tx}px, ${rmPz.ty}px) scale(${rmPz.scale})`;
      rmSyncZoomPill();
    }

    function rmMangaFit(preserveZoom) {
      const mStage = document.getElementById('rm-manga-stage');
      if (!mStage || mStage.classList.contains('rm-manga-strip') || !rmPz.imgW || !rmPz.imgH) {
        if (mStage && mStage.classList.contains('rm-manga-strip')) rmResizeStripPages();
        rmSyncZoomPill();
        return;
      }
      const useEdgeInset = window.innerWidth > 720;
      const edgePx = useEdgeInset ? Math.ceil(mStage.clientWidth * RM_EDGE_ROOM) : 0;
      const padX = (useEdgeInset && mStage.clientWidth - edgePx * 2 >= 260) ? (edgePx * 2 + 12) : 4;
      const sw = Math.max(100, mStage.clientWidth - padX);
      const sh = Math.max(100, mStage.clientHeight - 4);
      const newFit = Math.min(sw / rmPz.imgW, sh / rmPz.imgH);
      const wasZoomed = rmPz.scale > rmPz.fitScale * 1.03;
      rmPz.fitScale = newFit;
      if (!preserveZoom || !wasZoomed) {
        rmPz.scale = newFit;
        rmPz.tx = (mStage.clientWidth - rmPz.imgW * newFit) / 2;
        rmPz.ty = (mStage.clientHeight - rmPz.imgH * newFit) / 2;
      }
      rmApplyPzTransform();
    }

    function rmZoomMangaAt(clientX, clientY, targetScale) {
      const mStage = document.getElementById('rm-manga-stage');
      if (!mStage || !rmPz.imgW) return;
      const rect = mStage.getBoundingClientRect();
      const px = clientX - rect.left;
      const py = clientY - rect.top;
      let nextScale = Math.max(rmPz.fitScale, Math.min(rmPz.fitScale * 5, targetScale));
      if (nextScale <= rmPz.fitScale * 1.03) {
        rmMangaFit(false);
        return;
      }
      const ratio = nextScale / rmPz.scale;
      rmPz.tx = px - (px - rmPz.tx) * ratio;
      rmPz.ty = py - (py - rmPz.ty) * ratio;
      rmPz.scale = nextScale;
      rmApplyPzTransform();
    }

    function rmResizeStripPages() {
      const mStage = document.getElementById('rm-manga-stage');
      if (!mStage) return;
      const p = rmGetPrefs();
      const pct = Math.max(25, Math.min(100, Number(p.image_scale) || 80)) / 100;
      const availW = Math.max(200, mStage.clientWidth - 16);
      const targetW = Math.max(120, Math.round(availW * pct));
      mStage.querySelectorAll('.rm-mokuro-strip-item').forEach(wrap => {
        const iw = parseFloat(wrap.dataset.iw || '1000');
        const ih = parseFloat(wrap.dataset.ih || '1400');
        const s = Math.min(4, targetW / Math.max(1, iw));
        wrap.style.width = Math.round(iw * s) + 'px';
        wrap.style.height = Math.round(ih * s) + 'px';
        const pgEl = wrap.firstElementChild;
        if (pgEl) pgEl.style.transform = `scale(${s})`;
      });
    }

    function rmRenderMangaPart(opts = {}) {
      const part = rmState.part;
      const stage = document.getElementById('rm-stage');
      if (!part || !stage) return;
      if (rmMangaStageObs) rmMangaStageObs.disconnect();
      if (rmMangaStripObs) rmMangaStripObs.disconnect();
      clearTimeout(rmMangaClickTimer);
      rmSetEdgeHint(null);

      const pages = part.pages || [];
      stage.classList.remove('rm-vertical', 'rm-horizontal', 'rm-paginated', 'rm-continuous');
      stage.onmousemove = null;
      stage.onmouseleave = null;
      stage.onclick = null;
      stage.onwheel = null;
      if (!pages.length) {
        stage.innerHTML = `<div class="status-line" style="padding:3em;text-align:center;">${esc(t('rm_no_content'))}</div>`;
        rmSyncZoomPill();
        rmUpdateProgressUI();
        return;
      }
      let pno = opts.atEnd ? pages.length : (opts.targetPage || 1);
      pno = Math.max(1, Math.min(pages.length, pno));
      rmState.mangaPage = pno;

      const p = rmGetPrefs();
      const isStrip = p.manga_layout === 'strip' || part.source === 'db';
      stage.innerHTML = `<div class="rm-manga-stage ${isStrip ? 'rm-manga-strip' : ''}" id="rm-manga-stage"></div>`;
      const mStage = document.getElementById('rm-manga-stage');

      if (window.ResizeObserver) {
        rmMangaStageObs = new ResizeObserver(() => rmMangaFit(true));
        rmMangaStageObs.observe(mStage);
      }

      if (isStrip) {
        rmPz.imgW = 0; rmPz.imgH = 0; rmPz.scale = 1; rmPz.fitScale = 1; rmSyncZoomPill();
        for (const pg of pages) {
          if (!pg.image_url) {
            mStage.appendChild(rmBuildMokuroPageEl(pg));
          } else {
            const wrap = document.createElement('div');
            wrap.className = 'rm-mokuro-strip-item';
            wrap.dataset.page = String(pg.page);
            wrap.dataset.iw = String(pg.img_width || 1000);
            wrap.dataset.ih = String(pg.img_height || 1400);
            wrap.appendChild(rmBuildMokuroPageEl(pg));
            mStage.appendChild(wrap);
          }
        }
        rmSyncFuriganaAria();
        rmResizeStripPages();
        rmMangaStripObs = new IntersectionObserver(entries => {
          const vis = entries.filter(e => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio);
          if (vis.length) {
            const pNum = parseInt(vis[0].target.dataset.page || '1', 10);
            if (pNum && pNum !== rmState.mangaPage) {
              rmState.mangaPage = pNum;
              rmUpdateProgressUI();
              rmScheduleSaveProgress();
              saveMediaState();
            }
          }
        }, { root: mStage, threshold: [0.25, 0.6] });
        mStage.querySelectorAll('[data-page]').forEach(el => rmMangaStripObs.observe(el));
        const targetEl = mStage.querySelector(`[data-page="${pno}"]`);
        const frac = (opts.targetAnchor && opts.targetAnchor.page_frac) || (opts.restorePos && rmState.work && rmState.work.page_frac) || 0;
        if (pno <= 1 && !frac) mStage.scrollTop = 0;
        else if (targetEl) mStage.scrollTop = Math.max(0, targetEl.offsetTop + Math.round(frac * targetEl.offsetHeight));
        mStage.addEventListener('scroll', rmOnBarScroll, { passive: true });
      } else {
        rmDrawSingleMangaPage(pno);
      }

      mStage.addEventListener('mousemove', e => {
        if (isStrip || rmPz.dragging || !rmEdgeNavActive() || e.target.closest('.rm-text-box, a, button')) {
          rmSetEdgeHint(null);
          return;
        }
        rmSetEdgeHint(rmEdgeHitSide(e.clientX, mStage));
      });
      mStage.addEventListener('mouseleave', () => rmSetEdgeHint(null));

      mStage.addEventListener('dragstart', e => e.preventDefault());

      mStage.addEventListener('copy', e => {
        const sel = window.getSelection && window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount || !e.clipboardData) return;
        const range = sel.getRangeAt(0);
        if (!mStage.contains(range.commonAncestorContainer)) return;
        const startEl = range.startContainer.nodeType === 3 ? range.startContainer.parentElement : range.startContainer;
        const endEl = range.endContainer.nodeType === 3 ? range.endContainer.parentElement : range.endContainer;
        const startBox = startEl && startEl.closest('.rm-text-box');
        const endBox = endEl && endEl.closest('.rm-text-box');
        let out = '';
        if (startBox && startBox === endBox) {
          out = range.toString().replace(/[\r\n]+/g, '');
        } else {
          const boxes = [...mStage.querySelectorAll('.rm-text-box')].filter(b => range.intersectsNode(b));
          if (!boxes.length) return;
          const parts = [];
          for (const box of boxes) {
            const sub = document.createRange();
            sub.selectNodeContents(box);
            if (range.compareBoundaryPoints(Range.START_TO_START, sub) > 0) {
              sub.setStart(range.startContainer, range.startOffset);
            }
            if (range.compareBoundaryPoints(Range.END_TO_END, sub) < 0) {
              sub.setEnd(range.endContainer, range.endOffset);
            }
            const txt = sub.toString().replace(/[\r\n]+/g, '');
            if (txt) parts.push(txt);
          }
          if (!parts.length) return;
          out = parts.join('\n');
        }
        if (!out) return;
        e.clipboardData.setData('text/plain', out);
        e.preventDefault();
      });

      mStage.addEventListener('pointerdown', e => {
        if (isStrip || (e.button !== 0 && e.button !== 1)) return;
        if (e.target.closest('a, button')) return;
        if (e.button === 0 && e.target.closest('.rm-text-box') && rmGetPrefs().manga_boxes !== 'off') return;
        if (rmPz.scale <= rmPz.fitScale * 1.04) return;
        e.preventDefault();
        rmPz.dragging = true;
        rmPz.captured = false;
        rmPz.pointerId = e.pointerId;
        rmPz.moved = false;
        rmPz.startX = e.clientX;
        rmPz.startY = e.clientY;
        rmPz.origTx = rmPz.tx;
        rmPz.origTy = rmPz.ty;
      });
      mStage.addEventListener('pointermove', e => {
        if (!rmPz.dragging) return;
        const dx = e.clientX - rmPz.startX;
        const dy = e.clientY - rmPz.startY;
        if (!rmPz.moved && Math.abs(dx) <= 5 && Math.abs(dy) <= 5) return;
        if (!rmPz.moved) {
          rmPz.moved = true;
          if (!rmPz.captured && rmPz.pointerId != null) {
            try { mStage.setPointerCapture(rmPz.pointerId); rmPz.captured = true; } catch (err) {}
          }
          const canvas = document.getElementById('rm-mokuro-canvas');
          if (canvas) canvas.classList.add('rm-dragging');
        }
        rmPz.tx = rmPz.origTx + dx;
        rmPz.ty = rmPz.origTy + dy;
        rmApplyPzTransform();
      });
      const endDrag = () => {
        if (!rmPz.dragging) return;
        rmPz.dragging = false;
        if (rmPz.captured && rmPz.pointerId != null) {
          try { mStage.releasePointerCapture(rmPz.pointerId); } catch (err) {}
        }
        rmPz.captured = false;
        rmPz.pointerId = null;
        const canvas = document.getElementById('rm-mokuro-canvas');
        if (canvas) canvas.classList.remove('rm-dragging');
      };
      mStage.addEventListener('pointerup', endDrag);
      mStage.addEventListener('pointercancel', endDrag);

      mStage.addEventListener('wheel', e => {
        if (isStrip || !rmPz.imgW) return;
        if (e.ctrlKey) {
          e.preventDefault();
          const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18;
          rmZoomMangaAt(e.clientX, e.clientY, rmPz.scale * factor);
          return;
        }
        if (rmPz.scale > rmPz.fitScale * 1.04) {
          e.preventDefault();
          if (e.shiftKey) rmPz.tx -= e.deltaY;
          else { rmPz.tx -= e.deltaX; rmPz.ty -= e.deltaY; }
          rmApplyPzTransform();
        }
      }, { passive: false });

      mStage.addEventListener('mousedown', e => {
        if (!isStrip && e.button === 0 && rmEdgeNavActive() && !e.target.closest('.rm-text-box, a, button') && rmEdgeHitSide(e.clientX, mStage)) {
          e.preventDefault();
        }
      });

      mStage.addEventListener('dblclick', e => {
        if (isStrip) return;
        if (e.target.closest('.rm-text-box, a, button')) return;
        if (rmPz.scale > rmPz.fitScale * 1.04) {
          e.preventDefault();
          rmMangaFit(false);
          return;
        }
        if (rmEdgeNavActive() && rmEdgeHitSide(e.clientX, mStage)) return;
        if (!e.target.closest('.rm-mokuro-page')) return;
        e.preventDefault();
        rmZoomMangaAt(e.clientX, e.clientY, rmPz.fitScale * 2.2);
      });

      mStage.addEventListener('click', e => {
        if (isStrip) return;
        if (rmPz.moved) { rmPz.moved = false; return; }
        if (window.getSelection && String(window.getSelection()).trim()) return;
        if (e.target.closest('.rm-text-box, a, button')) return;
        mStage.querySelectorAll('.rm-text-box.rm-hovered').forEach(x => x.classList.remove('rm-hovered'));
        if (rmEdgeNavActive()) {
          const side = rmEdgeHitSide(e.clientX, mStage);
          if (side === 'left') { rmTurnMangaPage(1); return; }
          if (side === 'right') { rmTurnMangaPage(-1); return; }
        }
      });

      mStage.ontouchstart = e => {
        if (isStrip || e.touches.length !== 1 || rmPz.scale > rmPz.fitScale * 1.05) return;
        rmState.touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
      };
      mStage.ontouchend = e => {
        if (isStrip || !rmState.touchStart || !e.changedTouches.length) return;
        const dx = e.changedTouches[0].clientX - rmState.touchStart.x;
        const dy = e.changedTouches[0].clientY - rmState.touchStart.y;
        const dt = Date.now() - rmState.touchStart.t;
        rmState.touchStart = null;
        if (dt < 500 && Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.5) {
          rmTurnMangaPage(dx > 0 ? 1 : -1);
        }
      };

      rmUpdateProgressUI();
      rmResetTopbarForMode();
      saveMediaState();
      rmFocusStage();
    }

    function rmDrawSingleMangaPage(pageNo) {
      const mStage = document.getElementById('rm-manga-stage');
      const pages = (rmState.part && rmState.part.pages) || [];
      if (!mStage || !pages.length) return;
      clearTimeout(rmMangaClickTimer);
      const pno = Math.max(1, Math.min(pages.length, pageNo));
      rmState.mangaPage = pno;
      const pg = pages[pno - 1];
      mStage.innerHTML = '';
      if (!pg.image_url) {
        rmPz.imgW = 0; rmPz.imgH = 0; rmPz.scale = 1; rmPz.fitScale = 1;
        mStage.style.overflowY = 'auto';
        mStage.appendChild(rmBuildMokuroPageEl(pg));
        rmSyncFuriganaAria();
      } else {
        mStage.style.overflowY = '';
        const canvas = document.createElement('div');
        canvas.className = 'rm-mokuro-canvas';
        canvas.id = 'rm-mokuro-canvas';
        const pageEl = rmBuildMokuroPageEl(pg);
        canvas.appendChild(pageEl);
        mStage.appendChild(canvas);
        rmPz.imgW = pg.img_width || 1000;
        rmPz.imgH = pg.img_height || 1400;
        rmMangaFit(false);
        const curPart = rmState.part;
        const probe = new Image();
        probe.onload = () => {
          if (rmState.part !== curPart || rmState.mangaPage !== pno) return;
          if ((!pg.img_width || !pg.img_height) && probe.naturalWidth && probe.naturalHeight) {
            rmPz.imgW = probe.naturalWidth;
            rmPz.imgH = probe.naturalHeight;
            pageEl.style.width = rmPz.imgW + 'px';
            pageEl.style.height = rmPz.imgH + 'px';
            rmMangaFit(false);
          }
        };
        probe.onerror = () => {
          if (rmState.part !== curPart || rmState.mangaPage !== pno) return;
          rmPz.imgW = 0; rmPz.imgH = 0;
          mStage.innerHTML = `<div class="rm-manga-missing">${esc(t('rm_manga_no_image'))}</div>`;
        };
        probe.src = pg.image_url;
      }
      const nxt = pages[pno];
      if (nxt && nxt.image_url) { const pre = new Image(); pre.src = nxt.image_url; }
      rmUpdateProgressUI();
      rmScheduleSaveProgress();
      saveMediaState();
    }

    function rmGoMangaPage(pageNo) {
      const p = rmGetPrefs();
      if (p.manga_layout === 'strip' || (rmState.part && rmState.part.source === 'db')) {
        const el = document.querySelector(`#rm-manga-stage [data-page="${pageNo}"]`);
        if (el) el.scrollIntoView({ block: 'start' });
        rmState.mangaPage = pageNo;
        rmUpdateProgressUI();
      } else {
        rmDrawSingleMangaPage(pageNo);
      }
    }

    function rmTurnMangaPage(delta) {
      const pages = (rmState.part && rmState.part.pages) || [];
      if (!pages.length) return;
      const p = rmGetPrefs();
      if (p.manga_layout === 'strip' || rmState.part.source === 'db') {
        const mStage = document.getElementById('rm-manga-stage');
        if (mStage) mStage.scrollBy({ top: delta * Math.round(mStage.clientHeight * 0.85), behavior: 'smooth' });
        return;
      }
      if (rmBarAutoHideActive(p)) rmSetTopbarHidden(true);
      const nxt = rmState.mangaPage + delta;
      if (nxt < 1) {
        if (rmState.partIndex > 0) rmLoadPart(rmState.partIndex - 1, { atEnd: true });
        return;
      }
      if (nxt > pages.length) {
        if (rmState.partIndex + 1 < rmState.files.length) rmLoadPart(rmState.partIndex + 1, { targetPage: 1 });
        return;
      }
      rmDrawSingleMangaPage(nxt);
      rmAnnounce(rmPageAnnounceText());
    }


