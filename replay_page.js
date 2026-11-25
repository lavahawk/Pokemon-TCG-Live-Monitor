// Injected into ptcglreplay.com by the Replay tab (StatsUI). Idempotent: a
// second run only re-applies. window.__tlm.setFocus(bool) switches layouts.
//
// Full board (focus): the side panels are hidden (the app's timeline does
// playback and shows the current action) and the board is laid out wide,
// the two players side by side with the turn bar under them, then sized to
// fill the space. The site's own board is tall and narrow and is scaled to
// the window height, so it only used about a third of the middle.
//
// Always: no page scrollbar (the page was ~65 px taller than the window for
// nothing), the credits line hidden (the app's Support tab thanks the site
// and links to it), and card images that failed to load are retried.
(() => {
  if (window.__tlm) { window.__tlm.apply(); return 'again'; }
  const T = window.__tlm = { focus: true };
  const style = document.createElement('style');
  style.id = 'tlm-style';
  document.head.appendChild(style);

  const BOARD = 'main div.w-fit.mx-auto';
  T.css = () => `
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
      grid-template-columns: auto auto;
      grid-template-areas: "ohand phand" "ofield pfield" "mid mid";
      column-gap: 28px; row-gap: 14px;
      align-items: start; justify-items: stretch;
      width: max-content !important; min-height: 0 !important; height: auto !important;
      align-content: start !important; grid-auto-rows: auto;
      margin: 0 auto !important; padding-bottom: 0 !important;
      zoom: var(--tlm-z, 0.6) !important;
    }
    ${BOARD} > :nth-child(1) { grid-area: ohand; }
    ${BOARD} > :nth-child(2) { grid-area: ofield; }
    ${BOARD} > :nth-child(3) { grid-area: mid; }
    ${BOARD} > :nth-child(4) { grid-area: pfield; }
    ${BOARD} > :nth-child(5) { grid-area: phand; }
    ` : ''}`;

  // Size the wide board to the space it has.
  T.fit = () => {
    if (!T.focus) return;
    const board = document.querySelector(BOARD);
    if (!board) return;
    const z = parseFloat(getComputedStyle(board).zoom) || 1;
    const r = board.getBoundingClientRect();
    const natW = r.width / z, natH = r.height / z;
    if (natW < 50 || natH < 50) return;
    const col = board.parentElement;
    const availW = (col ? col.clientWidth : innerWidth) - 16;
    const top = col ? col.getBoundingClientRect().top : 16;
    const availH = innerHeight - Math.max(0, top) - 12;
    const want = Math.max(0.25, Math.min(2.5, availW / natW, availH / natH));
    if (Math.abs(want - z) > 0.004) board.style.setProperty('--tlm-z', want.toFixed(4));
  };

  T.apply = () => {
    style.textContent = T.css();
    requestAnimationFrame(() => { T.fit(); requestAnimationFrame(T.fit); });
  };
  T.setFocus = (on) => { T.focus = !!on; T.apply(); return T.focus; };

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
  try { new ResizeObserver(() => T.fit()).observe(document.body); } catch (e) {}
  setInterval(() => { T.fit(); T.retryImages(); }, 1500);
  T.apply();
  return 'installed';
})()
