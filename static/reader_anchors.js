    const RM_PAGE_GAP = 40;
    const rmState = {
      open: false,
      media: '',
      prefsKey: '',
      folder: '',
      files: [],
      partIndex: 0,
      part: null,
      work: null,
      dir: 'horizontal',
      layout: 'continuous',
      sections: [],
      secCharStarts: [],
      secCharLens: [],
      totalPlainChars: 0,
      secIndex: 0,
      pageIndex: 0,
      pageCount: 1,
      pageW: 0,
      pageH: 0,
      mangaPage: 1,
      mangaZoom: false,
      saveTimer: null,
      chunkGen: 0,
      toastTimer: null,
      touchStart: null,
      fallbackNoticed: false,
      historySession: 0,
      historyDepth: 0,
    };

    let rmIgnorePopCount = 0;

    const RM_ANCHOR_WS_RE = /[\s\u3000\u200b]/;
    const RM_ANCHOR_SKIP_TAGS = new Set(['RT', 'RP', 'SCRIPT', 'STYLE', 'SVG', 'NOSCRIPT']);

    function rmIsLowSurrogate(c) { return c >= 0xdc00 && c <= 0xdfff; }
    function rmCountNonWs(str, limit = str.length) {
      let n = 0;
      for (let i = 0; i < limit && i < str.length; i++) {
        if (!RM_ANCHOR_WS_RE.test(str[i])) n++;
      }
      return n;
    }

    function rmRawIdxFromNonWs(str, targetNonWs) {
      let n = 0;
      for (let i = 0; i < str.length; i++) {
        if (!RM_ANCHOR_WS_RE.test(str[i])) {
          if (n >= targetNonWs) return i;
          n++;
        }
      }
      return Math.max(0, str.length - 1);
    }

    function rmCollectAnchorNodes(root) {
      const nodes = [];
      let total = 0;
      if (!root) return { nodes, total };
      const walk = (el) => {
        for (let c = el.firstChild; c; c = c.nextSibling) {
          if (c.nodeType === 3) {
            const txt = c.nodeValue || '';
            const n = rmCountNonWs(txt);
            if (n > 0) {
              nodes.push({ node: c, text: txt, nonWsLen: n, cumStart: total });
              total += n;
            }
          } else if (c.nodeType === 1) {
            if (RM_ANCHOR_SKIP_TAGS.has(c.tagName)) continue;
            if (c.hasAttribute && c.hasAttribute('data-rm-ui')) continue;
            if (c.classList && (c.classList.contains('rm-sent-break') || c.classList.contains('rm-sub-ts') || c.classList.contains('rm-part-nav-end'))) continue;
            walk(c);
          }
        }
      };
      walk(root);
      return { nodes, total };
    }

    function rmExtractQuoteAt(nodes, startIdx, rawIdx, maxLen = 40) {
      let out = '';
      for (let i = startIdx; i < nodes.length && out.length < maxLen; i++) {
        const chunk = (i === startIdx ? nodes[i].text.slice(rawIdx) : nodes[i].text)
          .replace(/[\r\n\t]+/g, ' ')
          .replace(/\s{2,}/g, ' ');
        out += chunk;
      }
      return out.trim().slice(0, maxLen);
    }

    // Precompute cumulative non-whitespace plain-text character counts across spine sections so
    // continuous and paginated layouts share one layout-independent 0..N coordinate space.
    function rmBuildPartCharIndex(root) {
      const part = rmState.part;
      if (!part || rmState.media === 'manga') {
        rmState.secCharStarts = [];
        rmState.secCharLens = [];
        rmState.totalPlainChars = 0;
        return;
      }
      if (rmHtmlPart(part)) {
        const starts = [];
        const lens = [];
        let acc = 0;
        if (rmState.layout === 'paginated' && rmState.sections.length) {
          for (let i = 0; i < rmState.sections.length; i++) {
            starts.push(acc);
            const doc = rmParseSafeDoc(rmState.sections[i] || '');
            const n = rmCollectAnchorNodes(doc.body).total;
            lens.push(n);
            acc += n;
          }
        } else if (root) {
          const spines = [...root.querySelectorAll(':scope > section.rm-epub-spine')]
            .filter(sec => (sec.textContent || '').trim() || sec.querySelector('img, svg, hr, table'));
          if (spines.length) {
            for (const sec of spines) {
              starts.push(acc);
              const n = rmCollectAnchorNodes(sec).total;
              lens.push(n);
              acc += n;
            }
          } else {
            starts.push(0);
            acc = rmCollectAnchorNodes(root).total;
            lens.push(acc);
          }
        }
        rmState.secCharStarts = starts;
        rmState.secCharLens = lens;
        rmState.totalPlainChars = acc;
        return;
      }
      const total = root ? rmCollectAnchorNodes(root).total : 0;
      rmState.secCharStarts = [0];
      rmState.secCharLens = [total];
      rmState.totalPlainChars = total;
    }

    function rmAnchorTopPad() {
      const dlg = document.getElementById('reading-mode');
      const bar = document.getElementById('rm-topbar');
      if (dlg && dlg.classList.contains('rm-autohide-pad') && !rmBarHidden && bar) {
        return (bar.offsetHeight || 46) + 8;
      }
      return 8;
    }

    function rmRectInViewport(r, vr, vertical, paginated, topPad) {
      if (!r || r.width < 0.2 || r.height < 0.2) return false;
      if (paginated) {
        const cx = (r.left + r.right) * 0.5;
        const cy = (r.top + r.bottom) * 0.5;
        return cx >= vr.left - 2 && cx <= vr.right + 2 && cy >= vr.top - 2 && cy <= vr.bottom + 2;
      }
      if (vertical) {
        return r.left < vr.right - 2 && r.right > vr.left + 2;
      }
      return r.bottom > vr.top + topPad && r.top < vr.bottom - 2;
    }

    function rmRectBeforeStart(r, vr, vertical, paginated, topPad) {
      if (paginated) {
        return vertical ? (r.bottom < vr.top + 2) : (r.right < vr.left + 2);
      }
      if (vertical) return r.left >= vr.right - 2;
      return r.bottom <= vr.top + topPad;
    }

    function rmReadAnchor() {
      const part = rmState.part;
      const item = rmState.files[rmState.partIndex];
      const file = (part && part.file) || (item && item.file) || '';
      if (!part) return null;
      if (rmState.media === 'manga') {
        const pages = part.pages || [];
        let page = rmState.mangaPage || 1;
        let pageFrac = 0;
        const mStage = document.getElementById('rm-manga-stage');
        if (mStage && mStage.classList.contains('rm-manga-strip')) {
          const sr = mStage.getBoundingClientRect();
          const els = mStage.querySelectorAll('[data-page]');
          for (const el of els) {
            const er = el.getBoundingClientRect();
            if (er.bottom > sr.top + 8) {
              page = parseInt(el.dataset.page || String(page), 10) || page;
              pageFrac = Math.max(0, Math.min(1, (sr.top - er.top) / Math.max(1, er.height)));
              break;
            }
          }
        }
        const ratio = pages.length > 1 ? Math.max(0, Math.min(1, (page - 1) / (pages.length - 1))) : 0;
        return {
          file,
          anchor_v: 1,
          char_offset: 0,
          sec_index: 0,
          quote: '',
          scroll_ratio: Number(ratio.toFixed(5)),
          page,
          page_frac: Number(pageFrac.toFixed(5)),
        };
      }
      const sc = rmScrollerEl();
      const root = document.getElementById('rm-epub-root');
      const fallbackRatio = rmReadScrollRatio();
      const baseOff = (rmState.layout === 'paginated' && rmState.secCharStarts[rmState.secIndex]) || 0;
      if (!sc || !root) {
        return {
          file, anchor_v: 1, char_offset: baseOff, sec_index: rmState.secIndex || 0,
          quote: '', scroll_ratio: Number(fallbackRatio.toFixed(5)), page: rmState.pageIndex + 1,
        };
      }
      const { nodes } = rmCollectAnchorNodes(root);
      if (!nodes.length) {
        return {
          file, anchor_v: 1, char_offset: baseOff, sec_index: rmState.secIndex || 0,
          quote: '', scroll_ratio: Number(fallbackRatio.toFixed(5)), page: rmState.pageIndex + 1,
        };
      }
      const vr = sc.getBoundingClientRect();
      const vertical = rmState.dir === 'vertical';
      const paginated = rmState.layout === 'paginated';
      const topPad = (!paginated && !vertical) ? rmAnchorTopPad() : 2;
      const range = document.createRange();

      let startIdx = 0;
      if (nodes.length > 200) {
        let lo = 0, hi = nodes.length - 1;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          range.selectNodeContents(nodes[mid].node);
          const mr = range.getBoundingClientRect();
          if (rmRectBeforeStart(mr, vr, vertical, paginated, topPad)) lo = mid + 1;
          else hi = mid;
        }
        startIdx = Math.max(0, lo - 4);
      }

      let hitIdx = -1;
      let hitRaw = 0;
      for (let i = startIdx; i < nodes.length; i++) {
        const entry = nodes[i];
        range.selectNodeContents(entry.node);
        const nr = range.getBoundingClientRect();
        if (rmRectBeforeStart(nr, vr, vertical, paginated, topPad)) continue;
        const rects = range.getClientRects();
        let anyVis = false;
        for (let k = 0; k < rects.length; k++) {
          if (rmRectInViewport(rects[k], vr, vertical, paginated, topPad)) { anyVis = true; break; }
        }
        if (!anyVis) {
          if (!paginated && (vertical ? nr.right < vr.left : nr.top > vr.bottom)) break;
          continue;
        }
        const txt = entry.text;
        let lo = 0, hi = txt.length - 1;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          // An Ext-B kanji or emoji is two code units: measured whole, never by one half
          const at = mid > 0 && rmIsLowSurrogate(txt.charCodeAt(mid)) ? mid - 1 : mid;
          range.setStart(entry.node, at);
          range.setEnd(entry.node, Math.min(txt.length, at + (txt.codePointAt(at) > 0xffff ? 2 : 1)));
          const cr = range.getBoundingClientRect();
          if (rmRectBeforeStart(cr, vr, vertical, paginated, topPad)) lo = mid + 1;
          else hi = mid;
        }
        let raw = lo > 0 && rmIsLowSurrogate(txt.charCodeAt(lo)) ? lo - 1 : lo;
        while (raw < txt.length && RM_ANCHOR_WS_RE.test(txt[raw])) raw++;
        if (raw >= txt.length) continue;
        hitIdx = i;
        hitRaw = raw;
        break;
      }

      if (hitIdx < 0) {
        hitIdx = Math.min(nodes.length - 1, startIdx);
        hitRaw = rmRawIdxFromNonWs(nodes[hitIdx].text, 0);
      }

      const hitEntry = nodes[hitIdx];
      const localNonWs = rmCountNonWs(hitEntry.text, hitRaw);
      const charOffset = baseOff + hitEntry.cumStart + localNonWs;
      const total = rmState.totalPlainChars || (part.char_count || 0);
      const ratio = total > 0 ? Math.max(0, Math.min(1, charOffset / total)) : fallbackRatio;
      const quote = rmExtractQuoteAt(nodes, hitIdx, hitRaw, 40);
      // In a scrolled layout the anchor also keeps how far its character sat from the leading edge,
      // so a return lands on the same pixel, not a column or line away.
      let edge = null;
      if (!paginated) {
        range.setStart(hitEntry.node, hitRaw);
        range.setEnd(hitEntry.node, Math.min(hitEntry.text.length, hitRaw + 1));
        const hr = range.getBoundingClientRect();
        if (hr.width > 0 || hr.height > 0) edge = Number((vertical ? vr.right - hr.right : hr.top - vr.top).toFixed(1));
      }
      let secIdx = rmState.secIndex || 0;
      if (!paginated && rmState.secCharStarts.length > 1) {
        for (let s = rmState.secCharStarts.length - 1; s >= 0; s--) {
          if (charOffset >= rmState.secCharStarts[s]) { secIdx = s; break; }
        }
      }
      return {
        file,
        anchor_v: 1,
        char_offset: charOffset,
        sec_index: secIdx,
        quote,
        scroll_ratio: Number(ratio.toFixed(5)),
        page: rmState.pageIndex + 1,
        ...(edge != null ? { edge } : {}),
      };
    }

    function rmLocateAnchorOffset(root, localTarget, quote) {
      const { nodes, total } = rmCollectAnchorNodes(root);
      if (!nodes.length) return null;
      const clamped = Math.max(0, Math.min(Math.max(0, total - 1), localTarget || 0));
      let lo = 0, hi = nodes.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (nodes[mid].cumStart <= clamped) lo = mid;
        else hi = mid - 1;
      }
      let entry = nodes[lo];
      let rawIdx = rmRawIdxFromNonWs(entry.text, clamped - entry.cumStart);

      const qClean = (quote || '').replace(/[\s\u3000\u200b]+/g, '');
      if (qClean.length >= 6) {
        const probe = rmExtractQuoteAt(nodes, lo, rawIdx, Math.max(24, qClean.length)).replace(/[\s\u3000\u200b]+/g, '');
        const head = qClean.slice(0, 12);
        if (!probe.startsWith(head)) {
          const allNonWs = nodes.map(e => e.text.replace(/[\s\u3000\u200b]+/g, '')).join('');
          const nearStart = Math.max(0, clamped - 400);
          let found = allNonWs.indexOf(head, nearStart);
          if (found < 0 || found > clamped + 600) found = allNonWs.indexOf(head);
          if (found >= 0) {
            let a = 0, b = nodes.length - 1;
            while (a < b) {
              const m = (a + b + 1) >> 1;
              if (nodes[m].cumStart <= found) a = m;
              else b = m - 1;
            }
            entry = nodes[a];
            rawIdx = rmRawIdxFromNonWs(entry.text, found - entry.cumStart);
          }
        }
      }
      return { node: entry.node, rawIdx };
    }

    function rmAnchorTargetSection(anchor) {
      const count = Math.max(1, rmState.sections.length);
      if (count <= 1) return 0;
      const off = Math.max(0, anchor.char_offset || 0);
      if (rmState.secCharStarts.length === count) {
        if (typeof anchor.sec_index === 'number' && anchor.sec_index >= 0 && anchor.sec_index < count) {
          const s0 = rmState.secCharStarts[anchor.sec_index];
          const l0 = rmState.secCharLens[anchor.sec_index] || 0;
          if (l0 === 0 && off === s0) return anchor.sec_index;
          if (off >= s0 && off < s0 + l0) return anchor.sec_index;
        }
        for (let s = count - 1; s >= 0; s--) {
          if (off >= rmState.secCharStarts[s] && (rmState.secCharLens[s] > 0 || s === 0)) return s;
        }
      }
      if (typeof anchor.sec_index === 'number' && anchor.sec_index >= 0 && anchor.sec_index < count) {
        return anchor.sec_index;
      }
      return rmRatioToSection(anchor.scroll_ratio || 0, count).secIndex;
    }

    // A relayout (resize, a setting, a font or image load) lands on the page or scroll position that
    // holds the anchor. Reading a new anchor from that landing would start at the page's first
    // character, earlier than the old one, so every further relayout crept back a page. The landed
    // anchor is kept until the reader moves.
    let rmLanded = null;
    function rmPositionKey() {
      if (!rmState.part) return '';
      const base = `${rmState.part.file || ''}|${rmState.media}|${rmState.dir}|${rmState.layout}`;
      if (rmState.media === 'manga') {
        const mStage = document.getElementById('rm-manga-stage');
        const strip = mStage && mStage.classList.contains('rm-manga-strip');
        return `${base}|${rmState.mangaPage || 0}|${strip ? Math.round(mStage.scrollTop) : ''}`;
      }
      if (rmState.layout === 'paginated') return `${base}|${rmState.secIndex || 0}|${rmState.pageIndex || 0}`;
      const sc = rmScrollerEl();
      if (!sc) return base;
      return `${base}|${Math.round(rmState.dir === 'vertical' ? rmGetRtlDist(sc) : sc.scrollTop)}`;
    }
    function rmLayoutAnchor() {
      if (rmLanded && rmLanded.key === rmPositionKey()) return rmLanded.anchor;
      rmLanded = null;
      return rmReadAnchor();
    }

    function rmRestoreAnchor(anchor) {
      const ok = rmRestoreAnchorAt(anchor);
      rmLanded = (ok && anchor && anchor.anchor_v) ? { anchor, key: rmPositionKey() } : null;
      return ok;
    }

    // The page of the shown section that holds the anchor's character under the current layout.
    // Strict: -1 when the character is in another section; otherwise the nearest page.
    function rmAnchorPageInSection(anchor, root, strict = false) {
      if (!anchor || !root || rmState.layout !== 'paginated') return -1;
      const baseOff = rmState.secCharStarts[rmState.secIndex] || 0;
      const secLen = rmState.secCharLens[rmState.secIndex];
      const local = (anchor.char_offset || 0) - baseOff;
      if (strict && (local < 0 || (rmState.sections.length > 1 && secLen != null && local >= Math.max(1, secLen)))) return -1;
      const local0 = Math.max(0, local);
      const loc = rmLocateAnchorOffset(root, local0, anchor.quote);
      if (!loc) return -1;
      const prevT = root.style.transform;
      root.style.transform = '';
      const range = document.createRange();
      range.setStart(loc.node, loc.rawIdx);
      range.setEnd(loc.node, Math.min(loc.node.nodeValue.length, loc.rawIdx + 1));
      const cr = range.getBoundingClientRect();
      const rr = root.getBoundingClientRect();
      root.style.transform = prevT;
      const vertical = rmState.dir === 'vertical';
      const stride = Math.max(1, (vertical ? rmState.pageH : rmState.pageW) + RM_PAGE_GAP);
      const axis = vertical ? ((cr.top + cr.bottom) * 0.5 - rr.top) : ((cr.left + cr.right) * 0.5 - rr.left);
      return Math.max(0, Math.min(rmState.pageCount - 1, Math.floor((axis + RM_PAGE_GAP * 0.5) / stride)));
    }

    function rmRestoreAnchorAt(anchor) {
      if (!anchor || !rmState.part) return false;
      if (rmState.media === 'manga') {
        const pno = Math.max(1, Math.min((rmState.part.pages || []).length || 1, anchor.page || 1));
        const mStage = document.getElementById('rm-manga-stage');
        if (mStage && mStage.classList.contains('rm-manga-strip')) {
          const el = mStage.querySelector(`[data-page="${pno}"]`);
          if (el) {
            rmBarIgnoreScrollUntil = Date.now() + 200;
            const targetTop = el.offsetTop + Math.round((anchor.page_frac || 0) * el.offsetHeight);
            mStage.scrollTop = Math.max(0, targetTop);
            rmBarLastPos = mStage.scrollTop;
          }
          rmState.mangaPage = pno;
          rmUpdateProgressUI();
          return true;
        }
        if (typeof rmGoMangaPage === 'function') rmGoMangaPage(pno);
        return true;
      }
      if (!anchor.anchor_v) {
        rmRestoreScrollRatio(anchor.scroll_ratio || 0);
        return true;
      }
      const sc = rmScrollerEl();
      const root = document.getElementById('rm-epub-root');
      if (!sc || !root) return false;
      if (rmState.totalPlainChars <= 0) {
        if (rmState.layout === 'paginated' && rmState.sections.length > 1 && typeof anchor.sec_index === 'number') {
          const sIdx = Math.max(0, Math.min(rmState.sections.length - 1, anchor.sec_index));
          if (sIdx !== rmState.secIndex) rmRenderPaginatedSection(sIdx, { inSecRatio: 0 });
          else rmApplyPaginatedOffset(0);
          return true;
        }
        rmRestoreScrollRatio(anchor.scroll_ratio || 0);
        return true;
      }

      if (rmState.layout === 'paginated') {
        const targetSec = rmAnchorTargetSection(anchor);
        if (rmState.sections.length > 1 && targetSec !== rmState.secIndex) {
          rmRenderPaginatedSection(targetSec, { skipOffset: true });
        }
        const activeRoot = document.getElementById('rm-epub-root');
        const activeSc = rmScrollerEl();
        if (!activeRoot || !activeSc) return false;
        rmApplyPaginatedOffset(Math.max(0, rmAnchorPageInSection(anchor, activeRoot)));
        return true;
      }

      const loc = rmLocateAnchorOffset(root, anchor.char_offset || 0, anchor.quote);
      if (!loc) {
        rmRestoreScrollRatio(anchor.scroll_ratio || 0);
        return true;
      }
      const range = document.createRange();
      range.setStart(loc.node, loc.rawIdx);
      range.setEnd(loc.node, Math.min(loc.node.nodeValue.length, loc.rawIdx + 1));
      const cr = range.getBoundingClientRect();
      const vr = sc.getBoundingClientRect();
      rmBarIgnoreScrollUntil = Date.now() + 200;
      if (rmState.dir === 'vertical') {
        const curDist = rmGetRtlDist(sc);
        const pad = typeof anchor.edge === 'number' ? anchor.edge : 20;
        const delta = (vr.right - pad) - cr.right;
        rmSetRtlDist(sc, curDist + delta, false);
        rmBarLastPos = rmGetRtlDist(sc);
      } else {
        const pad = typeof anchor.edge === 'number' ? anchor.edge : rmAnchorTopPad();
        const targetTop = Math.max(0, sc.scrollTop + (cr.top - vr.top) - pad);
        sc.scrollTo({ top: targetTop, behavior: 'instant' });
        rmBarLastPos = sc.scrollTop;
      }
      return true;
    }

    function rmCapturePos() {
      const sc = rmScrollerEl();
      const item = rmState.files[rmState.partIndex];
      const anchor = rmReadAnchor();
      return {
        partIndex: rmState.partIndex,
        file: (rmState.part && rmState.part.file) || (item && item.file) || '',
        secIndex: rmState.secIndex || 0,
        pageIndex: rmState.pageIndex || 0,
        mangaPage: rmState.media === 'manga' ? (rmState.mangaPage || 1) : 0,
        scrollRatio: rmState.media === 'manga' ? 0 : rmReadScrollRatio(),
        scrollTop: sc ? sc.scrollTop : 0,
        rtlDist: (sc && rmState.dir === 'vertical') ? rmGetRtlDist(sc) : 0,
        anchor,
      };
    }

    async function rmRestoreHistoryPos(pos) {
      if (!pos || !isReadingModeOpen()) return;
      let idx = typeof pos.partIndex === 'number' ? pos.partIndex : -1;
      if (pos.file && (!rmState.files[idx] || rmState.files[idx].file !== pos.file)) {
        const found = rmState.files.findIndex(f => f.file === pos.file);
        if (found >= 0) idx = found;
      }
      if (idx < 0 || idx >= rmState.files.length) return;
      if (idx !== rmState.partIndex || !rmState.part) {
        const tPage = pos.mangaPage || (pos.anchor && pos.anchor.page) || 1;
        await rmLoadPart(idx, { restoreExactPos: pos, targetAnchor: pos.anchor || null, targetPage: tPage, fromHistory: true });
        return;
      }
      if (pos.anchor && pos.anchor.anchor_v) {
        rmRestoreAnchor(pos.anchor);
      } else if (rmState.media === 'manga') {
        if (typeof rmGoMangaPage === 'function') rmGoMangaPage(pos.mangaPage || 1);
      } else if (rmState.layout === 'paginated') {
        if ((rmState.sections || []).length > 1 && pos.secIndex != null && pos.secIndex !== rmState.secIndex) {
          rmRenderPaginatedSection(pos.secIndex, { inSecRatio: 0 });
        }
        rmApplyPaginatedOffset(pos.pageIndex || 0);
      } else {
        const sc = rmScrollerEl();
        if (sc && rmState.dir === 'vertical' && pos.rtlDist != null) {
          rmSetRtlDist(sc, pos.rtlDist, false);
        } else if (sc && rmState.dir !== 'vertical' && pos.scrollTop != null) {
          sc.scrollTo({ top: pos.scrollTop, behavior: 'instant' });
        } else {
          rmRestoreScrollRatio(pos.scrollRatio || 0);
        }
      }
      rmUpdateProgressUI();
      saveMediaState();
      rmSaveProgressNow(false);
    }

    function rmPushLinkHistory(beforePos, afterPos) {
      if (!rmState.historySession) {
        rmState.historySession = Date.now() + Math.floor(Math.random() * 1000);
        rmState.historyDepth = 0;
      }
      const curDepth = rmState.historyDepth || 0;
      try {
        const base = (history.state && typeof history.state === 'object') ? history.state : {};
        history.replaceState({ ...base, rmSession: rmState.historySession, rmDepth: curDepth, rmPos: beforePos }, '');
        const nextDepth = curDepth + 1;
        history.pushState({ ...base, rmSession: rmState.historySession, rmDepth: nextDepth, rmPos: afterPos }, '');
        rmState.historyDepth = nextDepth;
      } catch (e) {}
    }

    window.addEventListener('popstate', e => {
      if (rmIgnorePopCount > 0) {
        rmIgnorePopCount--;
        return;
      }
      if (!isReadingModeOpen()) return;
      const st = e.state;
      if (st && st.rmSession && st.rmSession === rmState.historySession && st.rmPos) {
        rmState.historyDepth = typeof st.rmDepth === 'number' ? st.rmDepth : 0;
        rmRestoreHistoryPos(st.rmPos);
      }
    });

    function isReadingModeOpen() {
      const dlg = document.getElementById('reading-mode');
      return !!(rmState.open && dlg && !dlg.hidden);
    }

    function rmCurrentRecipe() {
      if (!isReadingModeOpen() || !rmState.part) return null;
      return {
        media: rmState.media,
        folder: rmState.folder,
        file: rmState.part.file,
        page: rmState.media === 'manga' ? rmState.mangaPage : 0,
      };
    }

    function rmToast(msg) {
      const dlg = document.getElementById('reading-mode');
      if (!dlg) return;
      let el = dlg.querySelector('.rm-toast');
      if (!el) {
        el = document.createElement('div');
        el.className = 'rm-toast';
        el.setAttribute('role', 'status');
        dlg.appendChild(el);
      }
      el.textContent = msg;
      el.hidden = false;
      clearTimeout(rmState.toastTimer);
      rmState.toastTimer = setTimeout(() => { el.hidden = true; }, 1800);
    }

    function rmSetSafeHtml(target, htmlStr) {
      const doc = rmParseSafeDoc(htmlStr);
      target.replaceChildren(...doc.body.childNodes);
    }
