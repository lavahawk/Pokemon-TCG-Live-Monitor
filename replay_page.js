// Injected into ptcglreplay.com by the Replay tab (StatsUI). Idempotent: a
// second run only re-applies. window.__tlm.setFocus(bool) switches layouts.
//
// Full board (focus): the side panels are hidden (the app's timeline does
// playback and shows the current action) and the board is rebuilt for
// reading the cards:
//   - the opponent on top, you underneath, lined up like the game itself,
//     with a red or blue outline and a name tag on each side
//   - each side's Active and Bench in one row, so a side is about half as
//     tall and the whole board can be drawn bigger
//   - Pokémon in play and hand cards drawn larger; face-down prizes and the
//     deck smaller (only their count matters)
//   - hovering any card shows it full size at the edge of the window
// Two arrangements are measured on every resize and the one that gives the
// biggest cards wins: hands beside their side of the board (wide windows) or
// hands above and below it (tall windows). Hand width follows the hand size.
//
// If the site changes and the custom layout can't find its parts or comes
// out wrong a few checks in a row, it removes itself (T.broken) and the app
// shows the site exactly as the site draws it.
//
// Always: no page scrollbar, the credits line hidden (the app's Support tab
// thanks the site and links to it), and failed card images retried.
(() => {
  if (window.__tlm) { window.__tlm.apply(); return window.__tlm.broken ? 'broken' : 'again'; }
  const T = window.__tlm = { focus: true, broken: false, strikes: 0, layout: 'side' };
  const style = document.createElement('style');
  style.id = 'tlm-style';
  document.head.appendChild(style);

  const BOARD = 'main div.w-fit.mx-auto';
  const FIELDS = `:is(${BOARD} > :nth-child(2), ${BOARD} > :nth-child(4))`;
  const CENTER = `${FIELDS} > div:nth-child(2)`;
  const HANDS = `:is(${BOARD} > :nth-child(1), ${BOARD} > :nth-child(5))`;
  const board = () => document.querySelector(BOARD);
  const loaded = () => !!document.querySelector('input[type="range"]');
  // card sizes in the board's own pixels (the site's: 64x89, Active 128x179)
  const CARD = { active: [172, 240], bench: [100, 140], hand: [74, 103], prize: [38, 53], pile: [52, 73] };
  const size = (k) => `width: ${CARD[k][0]}px !important; height: ${CARD[k][1]}px !important;`;

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
      column-gap: 14px; row-gap: 12px;
      align-items: stretch; justify-items: stretch;
      width: max-content !important; min-height: 0 !important; height: auto !important;
      align-content: start !important; grid-auto-rows: auto;
      margin: 0 auto !important; padding: 12px 0 0 !important;
      zoom: var(--tlm-z, 0.6) !important;
    }
    ${BOARD}[data-tlm="side"] {
      grid-template-columns: var(--tlm-fw, 900px) var(--tlm-h, 420px);
      grid-template-areas: "ofield ohand" "mid mid" "pfield phand";
    }
    ${BOARD}[data-tlm="stack"] {
      grid-template-columns: var(--tlm-fw, 900px);
      grid-template-areas: "ohand" "ofield" "mid" "pfield" "phand";
    }
    ${BOARD} > :nth-child(1) { grid-area: ohand; }
    ${BOARD} > :nth-child(2) { grid-area: ofield; box-shadow: inset 0 0 0 2px rgba(232, 120, 120, 0.32); }
    ${BOARD} > :nth-child(3) { grid-area: mid; }
    ${BOARD} > :nth-child(4) { grid-area: pfield; box-shadow: inset 0 0 0 2px rgba(107, 182, 232, 0.6); }
    ${BOARD} > :nth-child(5) { grid-area: phand; }
    ${HANDS} > div { height: 100%; }

    /* each side: prizes | Active + Bench in one row | deck and discard */
    ${FIELDS} { position: relative; gap: 22px !important; justify-content: center; padding: 18px 14px 12px !important; }
    ${FIELDS} > div[class~="w-36"] { width: auto !important; }
    ${FIELDS} > div[class~="w-36"] > div { width: auto !important; }
    ${CENTER} { flex-direction: row !important; align-items: center !important; gap: 30px !important; }
    ${CENTER} > span { display: none !important; }
    ${CENTER} > div.relative { order: 0; }
    ${CENTER} > div.flex { order: 1; gap: 10px !important; }
    ${CENTER} [class~="w-32"] { ${size('active')} }
    ${CENTER} > div.flex [class~="w-16"] { ${size('bench')} }
    ${HANDS} [class~="w-16"] { ${size('hand')} }
    ${FIELDS} > div[class~="w-36"] [class~="w-16"] { ${size('pile')} }
    ${BOARD} [class~="grid-cols-2"] [class~="w-16"] { ${size('prize')} }

    ${FIELDS}::before {
      position: absolute; top: -11px; z-index: 5; pointer-events: none;
      padding: 2px 10px; border-radius: 999px; font: 600 13px/19px system-ui, sans-serif;
      content: attr(data-tlm-name); left: 18px;
    }
    ${BOARD} > :nth-child(2)::before { color: #f6caca; background: rgba(120, 40, 40, 0.85); }
    ${BOARD} > :nth-child(4)::before { color: #d8ecfa; background: rgba(30, 80, 120, 0.9); }

    #tlm-peek {
      position: fixed; top: 50%; transform: translateY(-50%); z-index: 2147483647;
      height: min(82vh, 640px); aspect-ratio: 63 / 88; pointer-events: none; display: none;
      border-radius: 14px; overflow: hidden; background: #111;
      box-shadow: 0 14px 44px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.12);
    }
    #tlm-peek img { width: 100%; height: 100%; object-fit: contain; display: block; }
    ` : ''}`;

  const handOwner = (el) => {
    const m = /^\s*(.+?)'s Hand\b/m.exec((el && el.innerText) || '');
    return m ? m[1].trim() : '';
  };
  T.label = (b) => {
    const opp = handOwner(b.children[0]);
    const me = handOwner(b.children[4]);
    b.children[1].dataset.tlmName = opp ? 'Opponent · ' + opp : 'Opponent';
    b.children[3].dataset.tlmName = me ? 'You · ' + me : 'You';
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
    // opponent's side above the turn bar above yours, no overlaps
    return r[1].bottom <= r[2].top + 2 && r[2].bottom <= r[3].top + 2;
  };
  const handCount = (el) => (el ? el.querySelectorAll('[class~="w-16"]').length : 0);

  T.fit = () => {
    if (T.broken || !T.focus) return;
    const b = board();
    if (!b) { if (loaded()) T.strike('no board'); return; }
    try {
      T.label(b);
      const z = parseFloat(getComputedStyle(b).zoom) || 1;
      const col = b.parentElement;
      const availW = (col ? col.clientWidth : innerWidth) - 16;
      const top = col ? col.getBoundingClientRect().top : 16;
      const availH = innerHeight - Math.max(0, top) - 10;
      // the width a side needs with nothing squeezing it
      const fw = Math.max(...[1, 3].map((i) => {
        const f = b.children[i];
        const prev = f.style.width;
        f.style.width = 'max-content';
        const w = f.getBoundingClientRect().width / z;
        f.style.width = prev;
        return w;
      }));
      if (!(fw >= 200)) { T.strike('side width ' + fw); return; }
      b.style.setProperty('--tlm-fw', fw.toFixed(1) + 'px');
      // beside the board, a hand wraps onto two rows: as wide as half the bigger hand
      const n = Math.max(handCount(b.children[0]), handCount(b.children[4]));
      const perRow = Math.max(3, Math.min(8, Math.ceil(n / 2)));
      b.style.setProperty('--tlm-h', (perRow * (CARD.hand[0] + 8) + 40) + 'px');

      const options = [];
      for (const layout of ['side', 'stack']) {
        const m = measure(b, layout, z);
        if (sane(b)) options.push({ layout, z: Math.min(availW / m.w, availH / m.h) });
      }
      if (!options.length) { b.dataset.tlm = T.layout; T.strike('layout check'); return; }
      // the better one, with a little stickiness so it doesn't flip back and forth
      options.sort((a, bb) => bb.z - a.z);
      let pick = options[0];
      const cur = options.find((o) => o.layout === T.layout);
      if (cur && cur !== pick && pick.z < cur.z * 1.06) pick = cur;
      T.layout = pick.layout;
      b.dataset.tlm = pick.layout;
      const want = Math.max(0.25, Math.min(2, pick.z));
      if (Math.abs(want - z) > 0.004) b.style.setProperty('--tlm-z', want.toFixed(4));
      T.strikes = 0;
    } catch (e) {
      T.strike(String(e));
    }
  };

  // Three bad checks in a row (about 4 s): give the page back to the site.
  T.strike = (why) => {
    T.why = why;
    if (++T.strikes < 3) return;
    T.broken = true;
    const b = board();
    if (b) { delete b.dataset.tlm; b.style.removeProperty('--tlm-z'); }
    style.textContent = '';
    T.hidePeek();
  };

  // Hover a card: show it full size at the far edge of the window.
  const peek = document.createElement('div');
  peek.id = 'tlm-peek';
  const peekImg = document.createElement('img');
  peek.appendChild(peekImg);
  document.body.appendChild(peek);
  T.hidePeek = () => { peek.style.display = 'none'; };
  const cardImg = (el) => {
    const img = el && el.closest ? el.closest('img') : null;
    if (!img || !img.closest(BOARD)) return null;
    if (!/^https?:/.test(img.src) || /ptcglreplay\.com\/assets\//.test(img.src)) return null;   // card backs, energy icons
    return img.getBoundingClientRect().height >= 24 ? img : null;
  };
  document.addEventListener('mouseover', (e) => {
    if (T.broken || !T.focus) return T.hidePeek();
    const img = cardImg(e.target);
    if (!img) return T.hidePeek();
    const big = img.src.replace(/\/low\.(png|webp|jpg)/, '/high.$1');
    if (peekImg.dataset.src !== big) {
      peekImg.dataset.src = big;
      peekImg.onerror = () => { if (peekImg.src !== img.src) peekImg.src = img.src; };
      peekImg.src = big;
    }
    const left = e.clientX > innerWidth / 2;
    peek.style.left = left ? '14px' : 'auto';
    peek.style.right = left ? 'auto' : '14px';
    peek.style.display = 'block';
  });
  document.addEventListener('mouseleave', T.hidePeek);

  T.apply = () => {
    style.textContent = T.css();
    if (!T.focus) T.hidePeek();
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
