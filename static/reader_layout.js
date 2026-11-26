    function rmScrollerEl() {
      return document.getElementById('rm-scroller') || document.getElementById('rm-stage');
    }

    const RM_SENT_OPEN = '「『（(';
    const RM_SENT_CLOSE = '」』）)';
    const RM_SENT_END = '。！？!?';
    const RM_SPEECH_END = '。！？!?…‥―─';
    const RM_SENT_WS_RE = /[\s\u3000\u200b]/;
    const RM_SENT_INLINE_TAGS = new Set(['SPAN', 'RUBY', 'RB', 'A', 'EM', 'STRONG', 'B', 'I', 'SMALL', 'SUB', 'SUP', 'MARK', 'U', 'S', 'FONT', 'ABBR', 'CITE', 'Q']);

    function rmClearSentenceBreaks(root) {
      if (!root) return;
      const parents = new Set();
      root.querySelectorAll('.rm-sent-break').forEach(el => {
        if (el.parentNode) parents.add(el.parentNode);
        el.remove();
      });
      parents.forEach(p => { try { p.normalize(); } catch (_) {} });
      root.querySelectorAll('.rm-page-push').forEach(el => el.classList.remove('rm-page-push'));
    }

    function rmCollectBlockSentences(block) {
      const items = [];
      (function walk(node) {
        for (let c = node.firstChild; c; c = c.nextSibling) {
          if (c.nodeType === 3) {
            if (c.nodeValue) items.push({ type: 'text', node: c, text: c.nodeValue });
          } else if (c.nodeType === 1) {
            const tag = c.tagName;
            if (tag === 'RT' || tag === 'RP' || tag === 'CODE' || tag === 'PRE' || tag === 'SVG' || tag === 'SCRIPT' || tag === 'STYLE' || tag === 'BUTTON') continue;
            if (c.hasAttribute && c.hasAttribute('data-rm-ui')) continue;
            if (c.classList && c.classList.contains('rm-sent-break')) continue;
            if (tag === 'BR') {
              items.push({ type: 'br', node: c });
            } else {
              walk(c);
            }
          }
        }
      })(block);

      const nextNonWs = (itemIdx, charIdx) => {
        for (let k = itemIdx; k < items.length; k++) {
          const it = items[k];
          if (it.type === 'br') return '';
          const s = it.text;
          for (let j = (k === itemIdx ? charIdx : 0); j < s.length; j++) {
            if (!RM_SENT_WS_RE.test(s[j])) return s[j];
          }
        }
        return '';
      };

      const sentences = [];
      let quoteDepth = 0;
      let ended = false;
      let prevChar = '';
      let cur = null;

      for (let k = 0; k < items.length; k++) {
        const it = items[k];
        if (it.type === 'br') {
          if (quoteDepth === 0 && cur) ended = true;
          continue;
        }
        const s = it.text;
        for (let i = 0; i < s.length; i++) {
          const ch = s[i];
          const isWs = RM_SENT_WS_RE.test(ch);
          if (ended) {
            if (isWs) continue;
            if (RM_SENT_END.includes(ch)) {
              if (cur) { cur.endNode = it.node; cur.endOffset = i + 1; }
              prevChar = ch;
              continue;
            }
            if (quoteDepth > 0 && RM_SENT_CLOSE.includes(ch)) {
              quoteDepth--;
              if (cur) { cur.endNode = it.node; cur.endOffset = i + 1; }
              prevChar = ch;
              continue;
            }
            if (cur) sentences.push(cur);
            cur = { startNode: it.node, startOffset: i, endNode: it.node, endOffset: i + 1 };
            ended = false;
          } else if (!isWs) {
            if (!cur) cur = { startNode: it.node, startOffset: i, endNode: it.node, endOffset: i + 1 };
            else { cur.endNode = it.node; cur.endOffset = i + 1; }
          }

          if (RM_SENT_OPEN.includes(ch)) {
            quoteDepth++;
          } else if (RM_SENT_CLOSE.includes(ch)) {
            if (quoteDepth > 0) {
              quoteDepth--;
              if (quoteDepth === 0 && (ch === '」' || ch === '』') && RM_SPEECH_END.includes(prevChar)) {
                const nxt = nextNonWs(k, i + 1);
                if (nxt === '「' || nxt === '『') ended = true;
              }
            }
          } else if (quoteDepth === 0 && RM_SENT_END.includes(ch)) {
            ended = true;
          }
          if (!isWs) prevChar = ch;
        }
      }
      if (cur) sentences.push(cur);
      return sentences;
    }

    function rmIsFirstMeaningfulChild(node) {
      for (let p = node.previousSibling; p; p = p.previousSibling) {
        if (p.nodeType === 3 && !p.nodeValue.replace(/[\s\u3000\u200b]+/g, '')) continue;
        if (p.nodeType === 1 && p.classList && p.classList.contains('rm-sent-break')) continue;
        return false;
      }
      return true;
    }

    function rmInsertSentBreak(block, startNode, startOffset) {
      let target = startNode;
      if (startOffset > 0) {
        if (startNode.parentElement && startNode.parentElement.closest('ruby')) return null;
        target = startNode.splitText(startOffset);
      }
      while (target.parentNode && target.parentNode !== block &&
             target.parentNode.nodeType === 1 && RM_SENT_INLINE_TAGS.has(target.parentNode.tagName) &&
             rmIsFirstMeaningfulChild(target)) {
        target = target.parentNode;
      }
      if (!target.parentNode) return null;
      if (target.parentElement && target.parentElement.closest('ruby')) return null;
      const brk = document.createElement('span');
      brk.className = 'rm-sent-break';
      brk.setAttribute('aria-hidden', 'true');
      target.parentNode.insertBefore(brk, target);
      return brk;
    }

    function rmSentenceSpanInfo(range, rootRect, vertical, pageSize, pageBlockSize) {
      const stride = Math.max(1, pageSize + RM_PAGE_GAP);
      const raw = range.getClientRects();
      const pages = new Map();
      let minPage = Infinity;
      let maxPage = -Infinity;
      for (let i = 0; i < raw.length; i++) {
        const r = raw[i];
        if (r.width < 0.5 || r.height < 0.5) continue;
        const mid = vertical ? ((r.top + r.bottom) * 0.5 - rootRect.top) : ((r.left + r.right) * 0.5 - rootRect.left);
        const pg = Math.max(0, Math.floor((mid + RM_PAGE_GAP * 0.5) / stride));
        if (pg < minPage) minPage = pg;
        if (pg > maxPage) maxPage = pg;
        const lo = vertical ? r.left : r.top;
        const hi = vertical ? r.right : r.bottom;
        const b = pages.get(pg);
        if (!b) pages.set(pg, { min: lo, max: hi });
        else {
          if (lo < b.min) b.min = lo;
          if (hi > b.max) b.max = hi;
        }
      }
      if (!pages.size) return null;
      if (minPage >= maxPage) return { straddles: false, minPage, maxPage };
      let totalBlockSpan = 0;
      pages.forEach(b => { totalBlockSpan += Math.max(0, b.max - b.min); });
      const firstB = pages.get(minPage);
      const usedBefore = vertical ? (rootRect.right - firstB.max) : (firstB.min - rootRect.top);
      return { straddles: true, minPage, maxPage, totalBlockSpan, usedBefore };
    }

    function rmApplySpacerFallback(block, brkEl, isBlockStart, sentRange, info, vertical, pageSize, pageBlockSize) {
      let sp = brkEl;
      if (isBlockStart) {
        block.classList.remove('rm-page-push');
        if (!block.parentNode) return null;
        sp = document.createElement('span');
        sp.className = 'rm-sent-break';
        sp.setAttribute('aria-hidden', 'true');
        block.parentNode.insertBefore(sp, block);
      }
      if (!sp) return null;
      const root = block.closest('#rm-epub-root');
      if (!root) return sp;
      sp.style.width = '1px';
      sp.style.height = '1px';
      const rr = root.getBoundingClientRect();
      const sr = sp.getBoundingClientRect();
      const rem = vertical ? (sr.right - rr.left) : ((rr.top + pageBlockSize) - sr.top);
      let sz = Math.max(1, Math.floor(rem) - 1);
      if (vertical) sp.style.width = sz + 'px';
      else sp.style.height = sz + 'px';
      let check = rmSentenceSpanInfo(sentRange, root.getBoundingClientRect(), vertical, pageSize, pageBlockSize);
      if (check && check.minPage <= info.minPage) {
        sz = Math.max(1, Math.ceil(rem));
        if (vertical) sp.style.width = sz + 'px';
        else sp.style.height = sz + 'px';
      }
      return sp;
    }

    // Push a sentence that straddles a column edge onto the next page so EPUB pagination never
    // cuts mid-sentence (quotes stay together; a sentence longer than one full page stays as is).
    // When `stopNode` is set (live slider drag), stop once two pages past `stopNode` are laid out
    // so the visible page keeps exact sentence breaks without laying out the rest of a long chapter.
    // Returns true when stopped early so the caller finishes the remaining pages on release.
    let rmBreaksPartial = false;
    function rmApplySentencePageBreaks(root, scroller, pageW, pageH, vertical, stopNode = null) {
      rmClearSentenceBreaks(root);
      if (!root || !scroller || root.classList.contains('rm-image-page')) return false;
      const actW = scroller.clientWidth || pageW;
      const actH = scroller.clientHeight || pageH;
      if (actW < 100 || actH < 100) return false;
      const pageSize = vertical ? actH : actW;
      const pageBlockSize = vertical ? actW : actH;
      const stride = Math.max(1, pageSize + RM_PAGE_GAP);
      const linePx = Math.max(12, parseFloat(getComputedStyle(root).fontSize) || 18);
      const skipAncestor = 'pre, code, table, figure, svg, h1, h2, h3, h4, h5, h6, summary, button, [data-rm-ui]';
      const childBlock = 'p, div, blockquote, ul, ol, li, table, pre, figure, h1, h2, h3, h4, h5, h6, section, article, hr, details, summary';
      const blocks = [...root.querySelectorAll('p, li, blockquote, dd, div')].filter(el =>
        !el.classList.contains('rm-code-block') &&
        !el.closest(skipAncestor) &&
        !el.querySelector(childBlock) &&
        (el.textContent || '').trim().length > 0
      );
      if (!blocks.length) return false;

      const range = document.createRange();
      let rootRect = root.getBoundingClientRect();
      let pushes = 0;
      const MAX_PUSHES = 500;
      let stopPage = -1;
      const measureStopPage = () => {
        if (!stopNode || !root.contains(stopNode)) return;
        try {
          range.selectNodeContents(stopNode);
          const rects = range.getClientRects();
          const r = (rects && rects.length ? rects[0] : null) || range.getBoundingClientRect();
          if (r && (r.width >= 0.5 || r.height >= 0.5)) {
            const mid = vertical ? ((r.top + r.bottom) * 0.5 - rootRect.top) : ((r.left + r.right) * 0.5 - rootRect.left);
            stopPage = Math.max(0, Math.floor((mid + RM_PAGE_GAP * 0.5) / stride));
          }
        } catch (_) {}
      };

      const setSentRange = (sent) => {
        try {
          range.setStart(sent.startNode, sent.startOffset);
          range.setEnd(sent.endNode, sent.endOffset);
          return true;
        } catch (_) {
          return false;
        }
      };

      const pushSentence = (block, si, s, info) => {
        let brkEl = null;
        let ok = false;
        if (si === 0) {
          if (!block.classList.contains('rm-page-push')) {
            block.classList.add('rm-page-push');
            ok = true;
          }
        } else {
          brkEl = rmInsertSentBreak(block, s.startNode, s.startOffset);
          ok = !!brkEl;
        }
        if (!ok) return { pushed: false, brkEl: null };
        rootRect = root.getBoundingClientRect();
        const post = rmCollectBlockSentences(block);
        const cur = post[si];
        if (cur && setSentRange(cur)) {
          const after = rmSentenceSpanInfo(range, rootRect, vertical, pageSize, pageBlockSize);
          // Engines that ignore break-before: column (Gecko) leave the sentence on minPage;
          // fill the remaining block space of minPage with a sized spacer instead.
          if (after && after.minPage <= info.minPage) {
            brkEl = rmApplySpacerFallback(block, brkEl, si === 0, range, info, vertical, pageSize, pageBlockSize);
            rootRect = root.getBoundingClientRect();
          }
        }
        return { pushed: true, brkEl };
      };

      for (let bi = 0; bi < blocks.length && pushes < MAX_PUSHES; bi++) {
        const block = blocks[bi];
        const br = block.getBoundingClientRect();
        if (br.width < 0.5 || br.height < 0.5) continue;
        const first = vertical ? (br.top - rootRect.top + 1) : (br.left - rootRect.left + 1);
        const last = vertical ? (br.bottom - rootRect.top - 1) : (br.right - rootRect.left - 1);
        const bStart = Math.max(0, Math.floor((first + RM_PAGE_GAP * 0.5) / stride));
        const bEnd = Math.max(0, Math.floor((last + RM_PAGE_GAP * 0.5) / stride));
        if (stopNode && stopPage < 0 && (block.contains(stopNode) || (block.compareDocumentPosition(stopNode) & Node.DOCUMENT_POSITION_PRECEDING))) {
          measureStopPage();
        }
        if (stopPage >= 0 && bStart > stopPage + 1) return true;
        if (bStart >= bEnd) continue;

        let sentFrom = 0;
        let innerSteps = 0;
        const tried = new Set();
        while (pushes < MAX_PUSHES && innerSteps++ < 60) {
          const sents = rmCollectBlockSentences(block);
          if (sentFrom >= sents.length) break;
          let pushed = false;
          for (let si = sentFrom; si < sents.length; si++) {
            const s = sents[si];
            if (!setSentRange(s)) continue;
            const info = rmSentenceSpanInfo(range, rootRect, vertical, pageSize, pageBlockSize);
            if (!info || !info.straddles) continue;
            const fitsOnePage = (info.maxPage - info.minPage === 1) && (info.totalBlockSpan <= pageBlockSize * 0.92);
            const hasBefore = info.usedBefore >= Math.max(10, linePx * 0.75);
            if (!fitsOnePage || !hasBefore) continue;

            const step = pushSentence(block, si, s, info);
            pushed = step.pushed;
            const brkEl = step.brkEl;
            if (pushed) {
              rootRect = root.getBoundingClientRect();
              // In vertical-rl, splitting a paragraph can pull an earlier sentence across the
              // same column edge. If so, drop this break and push that earlier sentence instead.
              let backIdx = -1;
              let backInfo = null;
              if (brkEl && si > 0 && !tried.has(si)) {
                const post = rmCollectBlockSentences(block);
                for (let pi = Math.max(0, si - 3); pi < si && pi < post.length; pi++) {
                  if (tried.has(pi)) continue;
                  const ps = post[pi];
                  if (!setSentRange(ps)) continue;
                  const pInfo = rmSentenceSpanInfo(range, rootRect, vertical, pageSize, pageBlockSize);
                  if (pInfo && pInfo.straddles && (pInfo.maxPage - pInfo.minPage === 1) &&
                      pInfo.totalBlockSpan <= pageBlockSize * 0.92 &&
                      pInfo.usedBefore >= Math.max(10, linePx * 0.75)) {
                    backIdx = pi;
                    backInfo = pInfo;
                    break;
                  }
                }
              }
              if (backIdx >= 0) {
                tried.add(si);
                const par = brkEl.parentNode;
                brkEl.remove();
                if (par) { try { par.normalize(); } catch (_) {} }
                const fresh = rmCollectBlockSentences(block);
                const bs = fresh[backIdx];
                if (bs) {
                  const backStep = pushSentence(block, backIdx, bs, backInfo);
                  if (backStep.pushed) {
                    tried.add(backIdx);
                    pushes++;
                    rootRect = root.getBoundingClientRect();
                    sentFrom = backIdx + 1;
                    break;
                  }
                }
                rootRect = root.getBoundingClientRect();
                sentFrom = si + 1;
                break;
              }
              tried.add(si);
              pushes++;
              sentFrom = si + 1;
              break;
            }
          }
          if (!pushed) break;
        }
        if (stopNode && block.contains(stopNode)) measureStopPage();
      }
      return false;
    }

    // Scale EPUB illustrations in continuous scrolling modes using image_scale (25%–100% of stage),
    // allowing images to break out of a narrow text column while leaving small inline icons untouched.
    // An image that loads late, above or beside the place being read, keeps that place: the
    // anchor is held across the resize, and images that land together are sized in one pass
    let rmEpubImageTimer = 0;
    function rmEpubImageLoaded() {
      clearTimeout(rmEpubImageTimer);
      rmEpubImageTimer = setTimeout(() => {
        if (!isReadingModeOpen() || rmState.media !== 'epub' || rmState.layout !== 'continuous') return;
        const snap = rmLayoutAnchor();
        rmResizeEpubImages();
        if (snap) rmRestoreAnchor(snap);
        rmUpdateProgressUI();
      }, 60);
    }
    function rmResizeEpubImages() {
      if (rmState.media !== 'epub' || rmState.layout !== 'continuous') return;
      const stage = document.getElementById('rm-stage');
      const root = document.getElementById('rm-epub-root');
      if (!stage || !root) return;
      const p = rmGetPrefs();
      const pct = Math.max(25, Math.min(100, Number(p.image_scale) || 80)) / 100;
      const boxW = Math.max(120, Math.round((stage.clientWidth - 24) * pct));
      const boxH = Math.max(120, Math.round((stage.clientHeight - 24) * pct));

      const vert = rmState.dir === 'vertical';
      const stRect = stage.getBoundingClientRect();
      const applyBox = (el, natW, natH) => {
        if (!(natW > 0 && natH > 0) || Math.max(natW, natH) < 120) {
          el.classList.remove('rm-scaled-img');
          el.style.removeProperty('width');
          el.style.removeProperty('height');
          el.style.removeProperty('max-width');
          el.style.removeProperty('max-height');
          el.style.removeProperty('transform');
          return;
        }
        const s = Math.min(boxW / natW, boxH / natH, 3);
        const w = Math.max(24, Math.round(natW * s));
        const h = Math.max(24, Math.round(natH * s));
        el.classList.add('rm-scaled-img');
        el.style.setProperty('width', w + 'px', 'important');
        el.style.setProperty('height', h + 'px', 'important');
        el.style.setProperty('max-width', 'none', 'important');
        el.style.setProperty('max-height', 'none', 'important');
        if (vert) {
          el.style.setProperty('transform', 'none', 'important');
          const er = el.getBoundingClientRect();
          const dy = Math.round(((stRect.top + stRect.bottom) - (er.top + er.bottom)) * 0.5);
          if (dy) el.style.setProperty('transform', `translateY(${dy}px)`, 'important');
        } else {
          el.style.removeProperty('transform');
        }
      };

      root.querySelectorAll('img:not(.gaiji):not([class*="gaiji"])').forEach(img => {
        if (img.closest('svg, td, th')) return;
        if (img.complete && img.naturalWidth > 0 && img.naturalHeight > 0) {
          applyBox(img, img.naturalWidth, img.naturalHeight);
        } else if (!img.dataset.rmScaleBound) {
          img.dataset.rmScaleBound = '1';
          img.addEventListener('load', rmEpubImageLoaded, { once: true });
        }
      });

      root.querySelectorAll('svg').forEach(svg => {
        if (svg.closest('td, th')) return;
        let vw = 0, vh = 0;
        const vb = svg.viewBox && svg.viewBox.baseVal;
        if (vb && vb.width > 0 && vb.height > 0) {
          vw = vb.width; vh = vb.height;
        } else {
          const im = svg.querySelector('image');
          vw = parseFloat((im && im.getAttribute('width')) || svg.getAttribute('width') || '0');
          vh = parseFloat((im && im.getAttribute('height')) || svg.getAttribute('height') || '0');
        }
        if (vw > 0 && vh > 0) applyBox(svg, vw, vh);
      });
    }

    // Resolve width_pct / height_pct against the display's maximized reading area, clamped to the
    // current window so shrinking a desktop window keeps box size steady until it meets the text.
    const RM_MIN_EDGE_ZONE = 30;
    function rmBoxTargets(stage, p) {
      const isPhone = window.innerWidth <= 720;
      const padX = isPhone ? 18 : 36;
      const padY = isPhone ? 18 : 36;
      const stageW = (stage && stage.clientWidth > 0) ? stage.clientWidth : window.innerWidth;
      const stageH = (stage && stage.clientHeight > 0) ? stage.clientHeight : window.innerHeight;
      const availW = Math.max(120, stageW - padX);
      const availH = Math.max(120, stageH - padY);
      const scrW = (window.screen && window.screen.availWidth) || stageW;
      const scrH = (window.screen && window.screen.availHeight) || stageH;
      const winChromeH = (!isPhone && window.outerHeight > window.innerHeight && Math.abs(window.outerWidth - window.innerWidth) <= 24)
        ? Math.min(160, window.outerHeight - window.innerHeight) : 0;
      const uiW = Math.max(0, window.innerWidth - stageW);
      const uiH = Math.max(0, window.innerHeight - stageH);
      const refW = isPhone ? availW : Math.max(availW, Math.max(120, scrW - uiW - padX));
      const refH = isPhone ? availH : Math.max(availH, Math.max(120, scrH - winChromeH - uiH - padY));
      const wPct = Math.max(10, Math.min(100, Number(p.width_pct) || 75)) / 100;
      const hPct = Math.max(10, Math.min(100, Number(p.height_pct) || 85)) / 100;
      const sPct = Math.max(10, Math.min(100, Number(p.scroll_size_pct) || 75)) / 100;
      const targetW = Math.floor(Math.max(120, refW * wPct));
      const targetH = Math.floor(Math.max(120, refH * hPct));
      const scrollW = Math.floor(Math.max(120, refW * sPct));
      const scrollH = Math.floor(Math.max(120, refH * sPct));
      // In page view a strip of RM_MIN_EDGE_ZONE px stays free on each side, so a page edge can be
      // clicked or tapped without touching the text; a wide page gets narrower, the text is never covered
      const edgeFreeW = stageW - 2 * RM_MIN_EDGE_ZONE;
      return {
        availW,
        availH,
        targetW,
        targetH,
        scrollW,
        scrollH,
        pageW: Math.floor(Math.max(120, Math.min(availW, targetW, edgeFreeW))),
        pageH: Math.floor(Math.max(120, Math.min(availH, targetH))),
      };
    }

    function rmSyncBoxVars(stage, p) {
      if (!stage) return null;
      const box = rmBoxTargets(stage, p || rmGetPrefs());
      stage.style.setProperty('--rm-max-w', box.scrollW + 'px');
      stage.style.setProperty('--rm-max-h', box.scrollH + 'px');
      return box;
    }

    function rmMeasurePagination(anchor = null) {
      const stage = document.getElementById('rm-stage');
      const scroller = rmScrollerEl();
      const root = document.getElementById('rm-epub-root');
      if (!stage || !scroller || !root) return;
      const p = rmGetPrefs();
      const box = rmSyncBoxVars(stage, p);

      if (rmState.layout === 'paginated') {
        const isPhone = window.innerWidth <= 720;
        const pageW = box.pageW;
        const pageH = box.pageH;
        const imgW = Math.max(220, stage.clientWidth - (isPhone ? 12 : 32));
        const imgH = Math.max(200, stage.clientHeight - (isPhone ? 12 : 24));
        stage.style.setProperty('--rm-page-w', pageW + 'px');
        stage.style.setProperty('--rm-page-h', pageH + 'px');
        stage.style.setProperty('--rm-img-page-w', imgW + 'px');
        stage.style.setProperty('--rm-img-page-h', imgH + 'px');
        const actW = scroller.clientWidth || pageW;
        const actH = scroller.clientHeight || pageH;
        rmState.pageW = actW;
        rmState.pageH = actH;
        if (root.classList.contains('rm-image-page')) {
          rmState.pageCount = 1;
          rmBreaksPartial = false;
          return;
        }
        const prevT = root.style.transform;
        root.style.transform = '';
        if (rmHtmlPart(rmState.part)) {
          // Clear prior breaks before locating stopNode so p.normalize() never detaches it.
          // During a slider drag, place sentence breaks through the page holding the anchor so
          // incomplete next-sentence text never flashes in; letting go finishes the remaining pages.
          rmClearSentenceBreaks(root);
          let stopNode = null;
          if (rmDragActive && anchor && anchor.anchor_v) {
            const baseOff = rmState.secCharStarts[rmState.secIndex] || 0;
            const loc = rmLocateAnchorOffset(root, Math.max(0, (anchor.char_offset || 0) - baseOff), anchor.quote);
            if (loc) stopNode = loc.node;
          }
          rmBreaksPartial = rmApplySentencePageBreaks(root, scroller, actW, actH, rmState.dir === 'vertical', stopNode);
        } else {
          rmBreaksPartial = false;
        }
        if (rmState.dir === 'vertical') {
          const stride = actH + RM_PAGE_GAP;
          const totalH = scroller.scrollHeight;
          rmState.pageCount = Math.max(1, Math.ceil((totalH - 4 + RM_PAGE_GAP) / Math.max(1, stride)));
        } else {
          const stride = actW + RM_PAGE_GAP;
          const totalW = scroller.scrollWidth;
          rmState.pageCount = Math.max(1, Math.ceil((totalW - 4 + RM_PAGE_GAP) / Math.max(1, stride)));
        }
        root.style.transform = prevT;
      } else {
        rmState.pageCount = 1;
        rmResizeEpubImages();
      }
      if (typeof rmSyncEdgeZones === 'function') rmSyncEdgeZones();
    }

    function rmReadScrollRatio() {
      if (rmState.layout === 'paginated') {
        const count = Math.max(1, rmState.sections.length);
        const pCount = Math.max(1, rmState.pageCount);
        const pIdx = Math.max(0, Math.min(pCount - 1, rmState.pageIndex));
        if (count === 1) return pCount > 1 ? pIdx / (pCount - 1) : 0;
        if (rmState.secIndex === count - 1 && pIdx === pCount - 1) return 1;
        return Math.min(1, (rmState.secIndex + (pCount > 1 ? 0.999 * pIdx / (pCount - 1) : 0)) / count);
      }
      return rmReadSectionRatio();
    }

    function rmRestoreScrollRatio(ratio) {
      const sc = rmScrollerEl();
      if (!sc) return;
      const r = Math.max(0, Math.min(1, Number(ratio) || 0));
      if (rmState.layout === 'paginated') {
        const count = Math.max(1, rmState.sections.length);
        const target = rmRatioToSection(r, count);
        if (count > 1 && target.secIndex !== rmState.secIndex) {
          rmRenderPaginatedSection(target.secIndex, target);
        } else {
          const pIdx = target.atEnd ? (rmState.pageCount - 1) : Math.min(rmState.pageCount - 1, Math.round(target.inSecRatio * Math.max(0, rmState.pageCount - 1)));
          rmApplyPaginatedOffset(pIdx);
        }
        return;
      }
      if (rmState.dir === 'vertical') {
        const maxD = Math.max(0, sc.scrollWidth - sc.clientWidth);
        rmSetRtlDist(sc, r * maxD, false);
      } else {
        const maxY = Math.max(0, sc.scrollHeight - sc.clientHeight);
        sc.scrollTo({ top: r * maxY, behavior: 'instant' });
      }
    }

    function rmTurnPage(delta) {
      rmClearDragAnchor();
      if (rmState.media === 'manga' && typeof rmTurnMangaPage === 'function') {
        rmTurnMangaPage(delta);
        return;
      }
      const sc = rmScrollerEl();
      if (!sc) return;
      if (rmState.layout === 'paginated') {
        if (rmBarAutoHideActive()) rmSetTopbarHidden(true);
        const nxt = rmState.pageIndex + delta;
        if (nxt < 0) {
          if (rmState.secIndex > 0) {
            rmRenderPaginatedSection(rmState.secIndex - 1, { atEnd: true });
            rmAnnounce(rmPageAnnounceText());
            rmScheduleSaveProgress();
          } else if (rmState.partIndex > 0) {
            rmLoadPart(rmState.partIndex - 1, { atEnd: true });
          }
          return;
        }
        if (nxt >= rmState.pageCount) {
          if (rmState.secIndex + 1 < rmState.sections.length) {
            rmRenderPaginatedSection(rmState.secIndex + 1, { inSecRatio: 0 });
            rmAnnounce(rmPageAnnounceText());
            rmScheduleSaveProgress();
          } else if (rmState.partIndex + 1 < rmState.files.length) {
            rmLoadPart(rmState.partIndex + 1, {});
          }
          return;
        }
        rmApplyPaginatedOffset(nxt);
        rmUpdateProgressUI();
        rmAnnounce(rmPageAnnounceText());
        rmScheduleSaveProgress();
        return;
      }
      if (rmState.dir === 'vertical') {
        rmSetRtlDist(sc, rmGetRtlDist(sc) + delta * Math.round(sc.clientWidth * 0.8), true);
        return;
      }
      sc.scrollBy({ top: delta * Math.round(sc.clientHeight * 0.85), behavior: 'smooth' });
    }

    function rmFindAnchor(scope, frag) {
      if (!scope || !frag) return null;
      const escId = s => (window.CSS && CSS.escape) ? CSS.escape(s) : s.replace(/["\\]/g, '\\$&');
      const cands = [frag];
      try {
        const dec = decodeURIComponent(frag);
        if (dec && dec !== frag) cands.push(dec);
      } catch (e) {}
      for (const f of cands) {
        try {
          const el = scope.querySelector(`[id="${escId('rm-ep-' + f)}"]`) || scope.querySelector(`[id="${escId(f)}"]`);
          if (el) return el;
        } catch (e) {}
      }
      return null;
    }

    // A link's target is its first character: the element's own box can begin a page earlier
    // (a note pushed to the next page, an empty anchor before a paragraph), the character cannot.
    function rmAnchorCharRect(el, root) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      walker.currentNode = el;
      const range = document.createRange();
      for (let node = walker.nextNode(), n = 0; node && n < 200; node = walker.nextNode(), n++) {
        if (node.parentElement && node.parentElement.closest('rt, rp, .rm-sent-break')) continue;
        const i = node.nodeValue.search(/\S/);
        if (i < 0) continue;
        range.setStart(node, i);
        range.setEnd(node, i + 1);
        const r = [...range.getClientRects()].find(x => x.width >= 0.5 && x.height >= 0.5);
        if (r) return r;
      }
      return el.getBoundingClientRect();
    }

    function rmGoToAnchorInPart(member, frag, allowMemberFallback = false) {
      rmClearDragAnchor();
      const part = rmState.part;
      if (!rmHtmlPart(part)) return false;
      if (rmState.layout === 'paginated') {
        let secIdx = rmState.secIndex;
        if (member) {
          secIdx = (rmState.sectionMembers || []).indexOf(member);
          if (secIdx < 0) return false;
        }
        if (frag && !allowMemberFallback && secIdx !== rmState.secIndex) {
          const doc = rmParseSafeDoc(rmState.sections[secIdx] || '');
          if (!rmFindAnchor(doc.body, frag)) return false;
        }
        const prevSec = rmState.secIndex;
        if (secIdx !== rmState.secIndex) rmRenderPaginatedSection(secIdx, { inSecRatio: 0 });
        const root = document.getElementById('rm-epub-root');
        const el = rmFindAnchor(root, frag);
        if (frag && !el && !allowMemberFallback) {
          if (secIdx !== prevSec) rmRenderPaginatedSection(prevSec, { inSecRatio: 0 });
          return false;
        }
        const vertical = rmState.dir === 'vertical';
        const axisMid = r => vertical ? (r.top + r.bottom) * 0.5 : (r.left + r.right) * 0.5;
        let page = 0;
        if (el && root) {
          const rr = root.getBoundingClientRect();
          const off = axisMid(rmAnchorCharRect(el, root)) - (vertical ? rr.top : rr.left);
          const stride = (vertical ? rmState.pageH : rmState.pageW) + RM_PAGE_GAP;
          page = Math.max(0, Math.floor((off + RM_PAGE_GAP * 0.5) / Math.max(1, stride)));
        }
        rmApplyPaginatedOffset(page);
        // The page shown is the proof: a target still before or after it moves the page.
        const sc = rmScrollerEl();
        for (let i = 0; i < 3 && el && root && sc; i++) {
          const vr = sc.getBoundingClientRect();
          const c = axisMid(rmAnchorCharRect(el, root));
          const step = c > (vertical ? vr.bottom : vr.right) ? 1 : (c < (vertical ? vr.top : vr.left) ? -1 : 0);
          const nxt = rmState.pageIndex + step;
          if (!step || nxt < 0 || nxt >= rmState.pageCount) break;
          rmApplyPaginatedOffset(nxt);
        }
        rmUpdateProgressUI();
        rmScheduleSaveProgress();
        return true;
      }
      const root = document.getElementById('rm-epub-root');
      if (!root) return false;
      let scope = root;
      if (member) {
        const q = (window.CSS && CSS.escape) ? CSS.escape(member) : member;
        scope = root.querySelector(`section.rm-epub-spine[data-member="${q}"]`);
        if (!scope) return false;
      }
      const el = frag ? (rmFindAnchor(scope, frag) || (allowMemberFallback && member ? scope : null)) : (member ? scope : null);
      if (!el) return false;
      el.scrollIntoView({ block: 'start', inline: 'start', behavior: 'instant' });
      rmUpdateProgressUI();
      rmScheduleSaveProgress();
      return true;
    }

    const RM_LINK_SELECTOR = '#rm-epub-root a[data-rm-href], #rm-epub-root a[href^="#"], #rm-epub-root a[data-rm-custom-file], #rm-epub-root a[data-rm-url]';

    // A link in a Custom .md: a web address opens in a new tab, a page of the same work opens
    // in Reading mode, and Back returns to where the link was
    async function rmFollowCustomLink(a) {
      const url = a.getAttribute('data-rm-url');
      if (url) {
        window.open(url, '_blank', 'noopener');
        return;
      }
      const file = a.getAttribute('data-rm-custom-file') || '';
      const idx = rmState.files.findIndex(f => f.file === file);
      if (idx < 0) {
        rmToast(t('rm_link_not_found'));
        return;
      }
      const beforePos = rmCapturePos();
      if (idx !== rmState.partIndex && !(await rmLoadPart(idx, {}))) return;
      rmPushLinkHistory(beforePos, rmCapturePos());
      saveMediaState();
      rmSaveProgressNow(false);
    }

    async function rmFollowLink(a) {
      if (a.hasAttribute('data-rm-url') || a.hasAttribute('data-rm-custom-file')) return rmFollowCustomLink(a);
      const target = a.getAttribute('data-rm-href') || '';
      const cut = target.indexOf('#');
      const member = target ? (cut >= 0 ? target.slice(0, cut) : target) : '';
      const frag = target ? (cut >= 0 ? target.slice(cut + 1) : '') : (a.getAttribute('href') || '').slice(1);
      const beforePos = rmCapturePos();
      if (rmGoToAnchorInPart(member, frag, false)) {
        rmPushLinkHistory(beforePos, rmCapturePos());
        saveMediaState();
        rmSaveProgressNow(false);
        return;
      }
      if (!member || !rmState.part || rmState.media !== 'epub') return;
      let res = null;
      try {
        const excl = rmState.part.source === 'file' ? '&exclude_source=1' : '';
        const r = await fetch(`/api/reading/resolve-link?file=${encodeURIComponent(rmState.part.file)}&target=${encodeURIComponent(target)}${excl}`);
        if (r.ok) res = await r.json();
      } catch (e) {}
      const idx = res ? rmState.files.findIndex(f => f.file === res.file) : -1;
      if (idx < 0) {
        rmToast(t('rm_link_not_found'));
        return;
      }
      if (idx !== rmState.partIndex && !(await rmLoadPart(idx, {}))) return;
      rmGoToAnchorInPart(member, frag, true);
      rmPushLinkHistory(beforePos, rmCapturePos());
      saveMediaState();
      rmSaveProgressNow(false);
    }

    // Stepping between chapters with the arrow keys or top-bar buttons remembers where each
    // chapter was left for this reading session, so an accidental step and return goes back to
    // the same place. Unvisited chapters, Contents and end-of-chapter buttons open at the start.
    function rmRememberPartPlace() {
      const curItem = rmState.files[rmState.partIndex];
      if (!curItem || !rmState.part || rmState.partCtrl || rmState.part.file !== curItem.file) return;
      if (rmState.media !== 'manga' && !document.getElementById('rm-epub-root')) return;
      const anchor = rmReadAnchor();
      if (anchor) rmState.partMemory.set(curItem.file, anchor);
    }

    function rmStepPart(delta, remember = true) {
      const nxt = rmState.partIndex + delta;
      if (nxt < 0 || nxt >= rmState.files.length) return;
      if (remember) {
        rmRememberPartPlace();
        const saved = rmState.partMemory.get(rmState.files[nxt].file);
        if (saved) {
          rmLoadPart(nxt, {
            targetAnchor: saved.anchor_v ? saved : null,
            targetRatio: saved.scroll_ratio,
            targetPage: saved.page || 1,
          });
          return;
        }
      }
      rmLoadPart(nxt, {});
    }

    let rmWheelLock = 0;
    function rmBindStageInteractions() {
      const sc = rmScrollerEl();
      const stage = document.getElementById('rm-stage');
      if (!sc || !stage) return;

      sc.onscroll = () => {
        if (rmState.layout !== 'paginated') {
          if (!rmDragActive && Date.now() >= rmBarIgnoreScrollUntil) rmClearDragAnchor();
          rmScheduleProgressUI();
          rmScheduleSaveProgress();
          rmOnBarScroll();
        }
      };

      stage.onwheel = e => {
        if (e.ctrlKey) return;
        if (rmState.layout === 'paginated') {
          const raw = Math.abs(e.deltaY) >= Math.abs(e.deltaX)
            ? e.deltaY
            : (rmState.dir === 'vertical' ? -e.deltaX : e.deltaX);
          if (Math.abs(raw) < 4) return;
          e.preventDefault();
          if (rmGetPrefs().scroll_turn_page === false) return;
          const now = Date.now();
          if (now - rmWheelLock < 120) return;
          rmWheelLock = now;
          rmTurnPage(raw > 0 ? 1 : -1);
          return;
        }
        if (rmState.dir === 'vertical') {
          const delta = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : -e.deltaX;
          if (!delta) return;
          e.preventDefault();
          rmSetRtlDist(sc, rmGetRtlDist(sc) + delta, false);
        }
      };

      stage.onmousemove = e => {
        if (!rmEdgeNavActive() || e.target.closest('a, button, input, summary')) {
          rmSetEdgeHint(null);
          return;
        }
        rmSetEdgeHint(rmEdgeHitSide(e.clientX, stage));
      };
      stage.onmouseleave = () => rmSetEdgeHint(null);

      stage.onmousedown = e => {
        if (e.button === 0 && rmEdgeNavActive() && !e.target.closest('a, button, input, summary') && rmEdgeHitSide(e.clientX, stage)) {
          e.preventDefault();
        }
      };

      stage.onclick = e => {
        const link = e.target.closest(RM_LINK_SELECTOR);
        if (link) {
          e.preventDefault();
          rmFollowLink(link);
          return;
        }
        if (e.target.closest('a, button, input, summary')) return;
        const side = rmEdgeHitSide(e.clientX, stage);
        if (rmEdgeNavActive() && side) {
          if (rmEdgeTapSelection()) return;
          const forward = rmState.dir === 'vertical' ? side === 'left' : side === 'right';
          rmTurnPage(forward ? 1 : -1);
          return;
        }
        if (window.getSelection && String(window.getSelection()).trim()) return;
        const isTouchOnly = window.matchMedia && window.matchMedia('(hover: none)').matches;
        if (isTouchOnly && rmGetPrefs().furigana === 'hover') {
          const ruby = e.target.closest('ruby');
          if (ruby) {
            const was = ruby.classList.contains('rm-ruby-open');
            stage.querySelectorAll('ruby.rm-ruby-open').forEach(r => r.classList.remove('rm-ruby-open'));
            if (!was) ruby.classList.add('rm-ruby-open');
            rmSyncFuriganaAria();
            return;
          }
          stage.querySelectorAll('ruby.rm-ruby-open').forEach(r => r.classList.remove('rm-ruby-open'));
          rmSyncFuriganaAria();
        }
      };

      // A tap on a link inside the book follows it and Yomitan reads nothing. Yomitan reads the
      // word under the finger when it lifts, before the click, so the point is covered from the
      // touch on and the click that lands on the cover follows the link. A mouse is left alone.
      stage.onpointerdown = e => {
        if ((e.pointerType !== 'touch' && e.pointerType !== 'pen') || !e.isPrimary) return;
        const link = e.target.closest(RM_LINK_SELECTOR);
        if (!link) return;
        const el = makeShield(e.clientX, e.clientY, 48);
        const done = () => { clearTimeout(timer); el.remove(); stage.removeEventListener('pointercancel', done); };
        const timer = setTimeout(done, 1000);
        el.onclick = ev => { ev.preventDefault(); ev.stopPropagation(); done(); rmFollowLink(link); };
        stage.addEventListener('pointercancel', done);
        (stage.closest('.rm-dialog') || document.body).appendChild(el);
      };

      stage.ontouchstart = e => {
        if (e.touches.length !== 1) return;
        rmState.touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
      };
      stage.ontouchend = e => {
        if (!rmState.touchStart || rmState.layout !== 'paginated' || !e.changedTouches.length) return;
        const dx = e.changedTouches[0].clientX - rmState.touchStart.x;
        const dy = e.changedTouches[0].clientY - rmState.touchStart.y;
        const dt = Date.now() - rmState.touchStart.t;
        rmState.touchStart = null;
        if (rmGetPrefs().scroll_turn_page === false) return;
        if (dt < 500 && Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.5) {
          const forward = rmState.dir === 'vertical' ? dx > 0 : dx < 0;
          rmTurnPage(forward ? 1 : -1);
        }
      };
    }

    // Scrolling fires every frame and the progress line reads the anchor from the whole chapter's
    // text, so it updates at most every 120 ms.
    let rmProgressTimer = null;
    function rmScheduleProgressUI() {
      if (rmProgressTimer) return;
      rmProgressTimer = setTimeout(() => {
        rmProgressTimer = null;
        if (isReadingModeOpen()) rmUpdateProgressUI();
      }, 120);
    }

    function rmRectAfterEnd(r, vr, vertical, paginated) {
      if (paginated) return vertical ? (r.top > vr.bottom - 2) : (r.left > vr.right - 2);
      if (vertical) return r.right <= vr.left + 2;
      return r.top >= vr.bottom - 2;
    }

    // The footer counts the text read up to the end of the screen, so the last page shows 100%;
    // the saved place stays the first character on screen (rmReadAnchor).
    function rmReadEndOffset() {
      const sc = rmScrollerEl();
      const root = document.getElementById('rm-epub-root');
      if (!sc || !root) return null;
      const { nodes } = rmCollectAnchorNodes(root);
      if (!nodes.length) return null;
      const vr = sc.getBoundingClientRect();
      const vertical = rmState.dir === 'vertical';
      const paginated = rmState.layout === 'paginated';
      const baseOff = (paginated && rmState.secCharStarts[rmState.secIndex]) || 0;
      const range = document.createRange();
      const after = (entry, i) => {
        const at = i > 0 && rmIsLowSurrogate(entry.text.charCodeAt(i)) ? i - 1 : i;
        range.setStart(entry.node, at);
        range.setEnd(entry.node, Math.min(entry.text.length, at + (entry.text.codePointAt(at) > 0xffff ? 2 : 1)));
        const r = range.getBoundingClientRect();
        if (!r || (r.width < 0.2 && r.height < 0.2)) return false;
        return rmRectAfterEnd(r, vr, vertical, paginated);
      };
      const firstChar = entry => rmRawIdxFromNonWs(entry.text, 0);
      let lo = 0, hi = nodes.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (after(nodes[mid], firstChar(nodes[mid]))) hi = mid;
        else lo = mid + 1;
      }
      if (lo === 0) return baseOff;
      const entry = nodes[lo - 1];
      let a = firstChar(entry), b = entry.text.length;
      while (a < b) {
        const mid = (a + b) >> 1;
        if (RM_ANCHOR_WS_RE.test(entry.text[mid]) || !after(entry, mid)) a = mid + 1;
        else b = mid;
      }
      return baseOff + entry.cumStart + Math.min(entry.nonWsLen, rmCountNonWs(entry.text, a));
    }

    function rmUpdateProgressUI() {
      const leftEl = document.getElementById('rm-foot-left');
      const rightEl = document.getElementById('rm-foot-right');
      const fillEl = document.getElementById('rm-progress-fill');
      if (!leftEl || !rightEl || !fillEl || !rmState.part) return;
      if (rmState.media === 'manga') {
        const total = Math.max(1, (rmState.part.pages || []).length);
        const cur = Math.max(1, Math.min(total, rmState.mangaPage));
        const pct = cur >= total ? 100 : Math.floor((cur / total) * 100);
        leftEl.textContent = t('rm_page_of', { a: fmt(cur), b: fmt(total) });
        rightEl.textContent = `${t('rm_part_of', { a: fmt(rmState.partIndex + 1), b: fmt(rmState.files.length) })} · ${pct}%`;
        fillEl.style.width = pct + '%';
        return;
      }
      const totalChars = rmState.totalPlainChars || rmState.part.char_count || 0;
      const endOff = totalChars > 0 ? rmReadEndOffset() : null;
      const atEnd = endOff == null && (rmState.layout === 'paginated'
        ? (rmState.secIndex >= Math.max(1, rmState.sections.length) - 1 && rmState.pageIndex >= Math.max(1, rmState.pageCount) - 1)
        : (() => {
            const sc = rmScrollerEl();
            if (!sc) return false;
            const max = rmState.dir === 'vertical' ? (sc.scrollWidth - sc.clientWidth) : (sc.scrollHeight - sc.clientHeight);
            return max <= 2 || rmReadSectionRatio() >= 0.999;
          })());
      const readChars = endOff != null ? Math.min(totalChars, endOff) : Math.round(totalChars * (atEnd ? 1 : rmReadScrollRatio()));
      const ratio = endOff != null ? readChars / totalChars : (atEnd ? 1 : rmReadScrollRatio());
      const pct = ratio >= 1 ? 100 : Math.floor(ratio * 100);
      if (rmState.layout === 'paginated') {
        const sCount = Math.max(1, rmState.sections.length);
        if (sCount > 1 && rmState.pageCount === 1) {
          leftEl.textContent = t('rm_page_of', { a: fmt(rmState.secIndex + 1), b: fmt(sCount) });
        } else if (sCount > 1) {
          leftEl.textContent = `${fmt(rmState.secIndex + 1)}/${fmt(sCount)} · ${t('rm_page_of', { a: fmt(rmState.pageIndex + 1), b: fmt(rmState.pageCount) })}`;
        } else {
          leftEl.textContent = t('rm_page_of', { a: fmt(rmState.pageIndex + 1), b: fmt(rmState.pageCount) });
        }
      } else {
        leftEl.textContent = totalChars ? `${t('rm_chars', { n: fmt(readChars) })} / ${t('rm_chars', { n: fmt(totalChars) })}` : '';
      }
      rightEl.textContent = `${t('rm_part_of', { a: fmt(rmState.partIndex + 1), b: fmt(rmState.files.length) })} · ${pct}%`;
      fillEl.style.width = pct + '%';
    }

    function rmToggleFooterMin() {
      const f = document.getElementById('rm-footer');
      if (f) f.classList.toggle('rm-footer-min');
    }

    function rmScheduleSaveProgress() {
      clearTimeout(rmState.saveTimer);
      rmState.saveTimer = setTimeout(() => rmSaveProgressNow(false), 700);
    }

    function rmSaveProgressNow(useKeepalive) {
      if (!rmState.part || !rmState.media || !rmState.folder) return;
      if (!isReadingModeOpen() && !useKeepalive) return;
      if (rmState.part.file !== (rmState.files[rmState.partIndex] || {}).file) return;
      const anchor = rmLayoutAnchor();
      const ratio = anchor
        ? anchor.scroll_ratio
        : (rmState.media === 'manga'
          ? (rmState.mangaPage - 1) / Math.max(1, (rmState.part.pages || []).length - 1)
          : rmReadScrollRatio());
      const patch = {
        file: rmState.part.file,
        part_index: rmState.partIndex,
        anchor_v: 1,
        scroll_ratio: ratio,
        char_offset: anchor ? (anchor.char_offset || 0) : Math.round((rmState.part.char_count || 0) * ratio),
        sec_index: anchor ? (anchor.sec_index || 0) : (rmState.secIndex || 0),
        quote: anchor ? (anchor.quote || '') : '',
        page: rmState.media === 'manga' ? ((anchor && anchor.page) || rmState.mangaPage) : (rmState.pageIndex + 1),
      };
      // Each save names its own page_frac and edge, null for none, so one from another layout
      // is not left behind.
      patch.page_frac = (anchor && anchor.page_frac != null) ? anchor.page_frac : null;
      patch.edge = (rmState.layout !== 'paginated' && anchor && typeof anchor.edge === 'number') ? anchor.edge : null;
      rmState.work = { ...(rmState.work || {}), ...patch };
      const payload = JSON.stringify({ media: rmState.media, folder: rmState.folder, work: patch });
      try {
        fetch('/api/reading/state', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...API_HEADERS },
          body: payload,
          keepalive: !!useKeepalive,
        }).catch(() => {});
      } catch (e) {}
    }

    function rmSetDir(mode) {
      const nextDir = (mode === 'vertical' || mode === 'horizontal') ? mode : 'auto';
      return rmUpdatePrefs({ writing_mode: nextDir });
    }

    function rmSetLayout(layout) {
      if (layout !== 'paginated' && layout !== 'continuous') return;
      return rmUpdatePrefs({ layout });
    }

    async function rmSaveWorkOverride(patch) {
      rmState.work = { ...(rmState.work || {}), ...patch };
      const needsRelayout = patch && ('writing_mode' in patch || 'layout' in patch);
      if (needsRelayout) rmApplyPrefsToDom(true);
      await apiPost('/api/reading/state', { media: rmState.media, folder: rmState.folder, work: patch }).catch(() => null);
    }
