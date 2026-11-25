// Injected into ptcglreplay.com by the Replay tab (StatsUI). Idempotent: a
// second run only re-applies. window.__tlm.setFocus(bool) switches layouts.
//
// Full board (focus): the side panels are hidden (the app's timeline does
// playback and shows the current action) and the two boards are staggered,
// the opponent's up and to the left, yours down and to the right, so it's
// obvious at a glance which side is which. Two staggered layouts are tried
// on every resize and the one that gives the biggest cards wins:
//   stack:  hand, field / turn bar / field, hand, one under the other,
//           shifted apart by whatever width is spare (tall windows)
//   corner: each hand sits beside its own field in the empty corner
//           (wide windows, where stacking would leave the cards tiny)
//
// If the site changes and the custom layout can't find its parts or comes
// out wrong a few checks in a row, it removes itself (T.broken) and the app
// shows the site exactly as the site draws it.
//
// Always: no page scrollbar, the credits line hidden (the app's Support tab
// thanks the site and links to it), and failed card images retried.
(() => {
  if (window.__tlm) { window.__tlm.apply(); return window.__tlm.broken ? 'broken' : 'again'; }
  const T = window.__tlm = { focus: true, broken: false, strikes: 0, layout: 'stack' };
  const style = document.createElement('style');
  style.id = 'tlm-style';
  document.head.appendChild(style);

  const BOARD = 'main div.w-fit.mx-auto';
  const board = () => document.querySelector(BOARD);
  const loaded = () => !!document.querySelector('input[type="range"]');

  T.css = () => T.broken ? '' : `
    html, body { overflow: hidden !important; }
    main { padding-bottom: 0 !important; }
    /* the site's credits line: thanked, with its links, on the app's Support tab */
    main > div.grid > .order-4 { display: none !important; }
    ${T.focus ? `
    main { max-width: none !important; }
    main > div.grid { grid-template-columns: minmax(0, 1fr) !important; }
    main > div.grid > div.order-3, main > div.grid > div[class~="lg:order-1"] { display: none !important; }
    main > div.grid > div[class~="lg:order-2"] { overflow: hidden !important; grid-column: 1 / -1 !important; }
    ${BOARD} {
      display: grid !important;
      column-gap: 0; row-gap: 12px;
      align-items: start; justify-items: stretch;
      width: max-content !important; min-height: 0 !important; height: auto !important;
      align-content: start !important; grid-auto-rows: auto;
      margin: 0 auto !important; padding: 12px 0 0 !important;
      zoom: var(--tlm-z, 0.6) !important;
    }
    ${BOARD}[data-tlm="stack"] {
      grid-template-columns: var(--tlm-off, 0px) calc(var(--tlm-fw, 840px) - var(--tlm-off, 0px)) var(--tlm-off, 0px);
      grid-template-areas: "ohand ohand ." "ofield ofield ." "mid mid mid" ". pfield pfield" ". phand phand";
    }
    ${BOARD}[data-tlm="corner"] {
      column-gap: 14px;
      grid-template-columns: var(--tlm-h, 380px) calc(var(--tlm-fw, 840px) - var(--tlm-h, 380px) - 14px) var(--tlm-h, 380px);
      grid-template-areas: "ofield ofield ohand" "mid mid mid" "phand pfield pfield";
    }
    ${BOARD}[data-tlm="corner"] > :nth-child(1) { align-self: start; }
    ${BOARD}[data-tlm="corner"] > :nth-child(5) { align-self: end; }
    ${BOARD} > :nth-child(1) { grid-area: ohand; }
    ${BOARD} > :nth-child(2) { grid-area: ofield; position: relative; box-shadow: inset 0 0 0 2px rgba(232, 120, 120, 0.28); }
    ${BOARD} > :nth-child(3) { grid-area: mid; }
    ${BOARD} > :nth-child(4) { grid-area: pfield; position: relative; box-shadow: inset 0 0 0 2px rgba(107, 182, 232, 0.55); }
    ${BOARD} > :nth-child(5) { grid-area: phand; }
    ${BOARD} > :nth-child(2)::before, ${BOARD} > :nth-child(4)::before {
      position: absolute; top: -11px; z-index: 5; pointer-events: none;
      padding: 2px 9px; border-radius: 999px; font: 600 12px/18px system-ui, sans-serif;
    }
    ${BOARD} > :nth-child(2)::before { content: attr(data-tlm-name); right: 18px; color: #f3c2c2; background: rgba(120, 40, 40, 0.55); }
    ${BOARD} > :nth-child(4)::before { content: attr(data-tlm-name); left: 18px; color: #d8ecfa; background: rgba(30, 80, 120, 0.7); }
    ` : ''}`;

  const handOwner = (el) => {
    const m = /^\s*(.+?)'s Hand\b/m.exec((el && el.innerText) || '');
    return m ? m[1].trim() : '';
  };
  T.label = (b) => {
    const opp = handOwner(b.children[0]);
    b.children[1].dataset.tlmName = opp ? 'Opponent · ' + opp : 'Opponent';
    b.children[3].dataset.tlmName = 'You';
  };

  // Natural (unzoomed) size of the board in a layout.
  const measure = (b, layout, z) => {
    b.dataset.tlm = layout;
    const r = b.getBoundingClientRect();
    return { w: r.width / z, h: r.height / z };
  };
  // Does the board look like what the layout asked for?
  const sane = (b) => {
    const k = b.children;
    if (k.length !== 5) return false;
    const r = Array.from(k, (c) => c.getBoundingClientRect());
    if (r.some((x) => x.width < 20 || x.height < 20)) return false;
    // opponent field above the turn bar above your field, no overlaps
    return r[1].bottom <= r[2].top + 2 && r[2].bottom <= r[3].top + 2;
  };
  // How far hand cards spill past their hand (0 when they fit).
  const spill = (b) => {
    let px = 0;
    for (const i of [0, 4]) {
      const inner = b.children[i] && b.children[i].firstElementChild;
      if (inner) px += Math.max(0, inner.scrollWidth - inner.clientWidth);
    }
    return px;
  };

  T.fit = () => {
    if (T.broken || !T.focus) return;
    const b = board();
    if (!b) { if (loaded()) T.strike(); return; }
    try {
      T.label(b);
      const z = parseFloat(getComputedStyle(b).zoom) || 1;
      const col = b.parentElement;
      const availW = (col ? col.clientWidth : innerWidth) - 16;
      const top = col ? col.getBoundingClientRect().top : 16;
      const availH = innerHeight - Math.max(0, top) - 10;
      // field width with nothing squeezing it
      const fws = [1, 3].map((i) => {
        const f = b.children[i];
        const prev = f.style.width;
        f.style.width = 'max-content';
        const w = f.getBoundingClientRect().width / z;
        f.style.width = prev;
        return w;
      });
      const fw = Math.max(...fws);
      if (!(fw >= 200)) { T.strike(); return; }
      b.style.setProperty('--tlm-fw', fw.toFixed(1) + 'px');
      b.style.setProperty('--tlm-off', '0px');

      const options = [];
      // stack: height decides the size, spare width becomes the stagger
      const s = measure(b, 'stack', z);
      const stackSpill = spill(b);
      const minOff = fw * 0.08, maxOff = fw * 0.32;
      let zs = Math.min(availH / s.h, availW / (fw + minOff));
      const off = Math.max(minOff, Math.min(maxOff, availW / zs - fw));
      options.push({ layout: 'stack', z: zs, off });
      // corner: each hand beside its field
      const h = Math.round(fw * 0.5);
      b.style.setProperty('--tlm-h', h + 'px');
      const c = measure(b, 'corner', z);
      if (sane(b) && spill(b) <= stackSpill + 2) options.push({ layout: 'corner', z: Math.min(availW / c.w, availH / c.h) });

      // the better one, with a little stickiness so it doesn't flip back and forth
      options.sort((a, bb) => bb.z - a.z);
      let pick = options[0];
      const cur = options.find((o) => o.layout === T.layout);
      if (cur && cur !== pick && pick.z < cur.z * 1.06) pick = cur;
      T.layout = pick.layout;
      b.dataset.tlm = pick.layout;
      b.style.setProperty('--tlm-off', (pick.off || 0).toFixed(1) + 'px');
      const want = Math.max(0.25, Math.min(2.5, pick.z));
      if (Math.abs(want - z) > 0.004) b.style.setProperty('--tlm-z', want.toFixed(4));
      if (sane(b)) T.strikes = 0; else T.strike();
    } catch (e) {
      T.strike();
    }
  };

  // Three bad checks in a row (about 4 s): give the page back to the site.
  T.strike = () => {
    if (++T.strikes < 3) return;
    T.broken = true;
    const b = board();
    if (b) { delete b.dataset.tlm; b.style.removeProperty('--tlm-z'); }
    style.textContent = '';
  };

  T.apply = () => {
    style.textContent = T.css();
    requestAnimationFrame(() => { T.fit(); requestAnimationFrame(T.fit); });
  };
  T.setFocus = (on) => { T.focus = !!on; T.apply(); return T.broken ? 'broken' : T.focus; };
  // A new game (back on the upload page): try the custom layout again.
  T.watchReset = () => {
    if (T.broken && !loaded()) { T.broken = false; T.strikes = 0; T.apply(); }
  };

  // Card images: retry ones that failed (a busy image server, a dropped
  // connection), a few times each.
  T.retryImages = () => {
    for (const img of document.images) {
      if (!img.complete || img.naturalWidth > 0 || !/^https?:/.test(img.src)) continue;
      const tries = Number(img.dataset.tlmTries || 0);
      if (tries >= 4) continue;
      img.dataset.tlmTries = String(tries + 1);
      const url = img.src.replace(/([?&])tlmr=\d+&?/, '$1').replace(/[?&]$/, '');
      img.src = url + (url.includes('?') ? '&' : '?') + 'tlmr=' + (tries + 1);
    }
  };

  window.addEventListener('resize', () => T.fit());
  setInterval(() => { T.watchReset(); T.fit(); T.retryImages(); }, 1500);
  T.apply();
  return 'installed';
})()
