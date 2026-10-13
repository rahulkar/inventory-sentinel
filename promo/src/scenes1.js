/* Scenes A-D: vanishing stock, the cost, meet Sentinel, plug and play over MCP. Times are global seconds (see CUE). */
'use strict';

const CUE = {
  s1: 1.5, vanish: 3.4, theft: 6.96, till: 7.83, miscount: 8.84, shortdel: 9.68, typo: 10.91,
  s2: 12.5, pct: 13.05, weeks: 15.43, later: 16.8, ifatall: 17.78,
  s3: 19.4, meet: 19.7, name: 20.33, item: 22.09, store: 22.8, day: 23.78, points: 24.95, places: 26.2, wrong: 27.8,
  s4: 30.2, plug: 30.24, speaks: 31.79, connects: 34.07, url: 37.29, sync: 38.49, flow: 39.3, nomig: 41.43, noreb: 42.56, server: 43.87, agents: 45.0,
  s5: 49.9, learns: 49.92, nolabels: 52.02, sixteen: 54.23, voids: 55.36, afterhours: 57.44, compete: 59.21, history: 60.94, winner: 62.63, onepoint7: 64.42, rule: 66.74,
  s6: 69.2, lead: 69.24, three: 72.74, varisk: 74.05, visit: 75.48, beats: 77.84, where: 80.75, first: 81.95, nostats: 83.5,
  s7: 86.5, question: 86.53, ask: 88.02, team: 89.07, splits: 90.39, digs: 92.33, plans: 94.19, live: 96.98, never: 98.84, change: 101.71, yes: 102.72,
  s8: 104.9, close: 104.93, smarter: 107.19,
  s9: 109.6, logo: 109.64, plugin: 111.42, learn: 112.45, find: 113.72, before: 114.9, END: 120.0,
};
const POS = { A: [0, 0], B: [2400, 0], C: [2400, 1500], D: [4800, 1500], E: [6100, 3000], E2: [6100, 4150], F: [8600, 4150], G: [8600, 5400], H: [6100, 5400] };

/* ===================== A: stock quietly vanishing ===================== */
const SHOP_ITEMS = (() => {
  const items = [];
  const row1 = -170, row2 = 40, row3 = 250;
  const r1 = [[-430, 'shoebox', PAL.coralL], [-290, 'trainer', PAL.white], [-140, 'shoebox', PAL.tealL], [10, 'shoebox', PAL.mustL], [160, 'trainer', PAL.white], [300, 'shoebox', PAL.lavL], [440, 'shoebox', PAL.sageL]];
  const r2 = [[-450, 'bottle', PAL.pink], [-370, 'jar', PAL.mustL], [-290, 'bottle', PAL.tealL], [-200, 'jar', PAL.coralL], [-110, 'bottle', PAL.lavL], [-20, 'tube', PAL.sageL], [70, 'bottle', PAL.pink], [160, 'jar', PAL.tealL], [250, 'bottle', PAL.mustL], [340, 'tube', PAL.coralL], [430, 'jar', PAL.lavL]];
  const r3 = [[-420, 'stack', PAL.teal], [-250, 'stack', PAL.coral], [-80, 'stack', PAL.mustard], [90, 'stack', PAL.sage], [260, 'stack', PAL.lav], [420, 'stack', PAL.tealD]];
  r1.forEach(([x, k, c]) => items.push({ x, y: row1, k, c }));
  r2.forEach(([x, k, c]) => items.push({ x, y: row2, k, c }));
  r3.forEach(([x, k, c]) => items.push({ x, y: row3, k, c }));
  items.forEach((it, i) => { it.appear = 0.9 + i * 0.055; });
  // which items vanish, and when
  const gone = [2, 9, 19, 5, 14, 22, 11, 17];
  gone.forEach((idx, j) => { items[idx].vanish = CUE.vanish + j * 0.36; items[idx].word = j === 0 || j === 3; });
  return items;
})();
function shopItem(it, t) {
  const k = popIn(t, it.appear, 0.45);
  if (k <= 0) return;
  const vk = it.vanish ? seg(t, it.vanish, it.vanish + 0.18) : 0;
  const ghost = it.vanish && t > it.vanish + 0.1;
  push(it.x, it.y);
  if (ghost) {
    alpha(0.55);
    const g = itemBox(it);
    stroke(rrPts(g[0], g[1], g[2], g[3], 8, 0), { w: 2.2, color: PAL.pencil, dash: [7, 9], double: false });
    pop();
    poof(it.x, it.y - 40, 1.25, it.vanish, t);
    if (it.word) { const wk = seg(t, it.vanish, it.vanish + 0.9); if (wk < 1) text('poof!', it.x + 40, it.y - 100 - wk * 40, { size: 44, font: 'hand', weight: 700, color: PAL.inkSoft, alpha: 1 - wk * wk, align: 'center' }); }
    return;
  }
  const sc = k * (1 - vk);
  S.ctx.scale(sc, sc);
  if (it.k === 'shoebox') {
    box(-55, -64, 110, 64, { color: it.c, tape: false });
    stroke([[-55, -50], [55, -50]], { w: 2.5 });
    text('size 8', 0, -16, { size: 22, font: 'body', align: 'center', color: PAL.inkSoft, jit: 0.5 });
  } else if (it.k === 'trainer') {
    const d = 'M-60,-6 L-58,-40 C-40,-42 -20,-56 -6,-58 C4,-40 30,-30 54,-26 C66,-22 68,-6 60,-4 Z';
    fillPoly(parsePath(d)[0], it.c, { seed: hashN(it.x) });
    path(d, { w: 3 });
    stroke([[-62, -6], [62, -6]], { w: 6, color: PAL.coral, double: false });
    stroke([[-24, -48], [-10, -38]], { w: 2.5 }); stroke([[-18, -54], [-2, -44]], { w: 2.5 });
  } else if (it.k === 'bottle') {
    fillPoly(rrPts(-20, -96, 40, 96, 12, 0), it.c, { seed: hashN(it.x, 2) });
    stroke(rrPts(-20, -96, 40, 96, 12, 8), { w: 3 });
    fillPoly(rrPts(-9, -118, 18, 24, 4, 0), PAL.ink, { alpha: 0.7, edge: false, seed: hashN(it.x, 3) });
    stroke([[-12, -60], [12, -60]], { w: 2.2, alpha: 0.6, double: false });
  } else if (it.k === 'jar') {
    fillPoly(rrPts(-30, -58, 60, 58, 14, 0), it.c, { seed: hashN(it.x, 4) });
    stroke(rrPts(-30, -58, 60, 58, 14, 8), { w: 3 });
    fillPoly(rrPts(-32, -72, 64, 16, 5, 0), PAL.white, { seed: hashN(it.x, 5) });
    stroke(rrPts(-32, -72, 64, 16, 5, 6), { w: 2.5 });
  } else if (it.k === 'tube') {
    const d = 'M-14,0 L-18,-80 L18,-80 L14,0 Z';
    fillPoly(parsePath(d)[0], it.c, { seed: hashN(it.x, 6) });
    path(d, { w: 3 });
    fillPoly(rrPts(-12, -100, 24, 22, 4, 0), PAL.white, { seed: hashN(it.x, 7) });
    stroke(rrPts(-12, -100, 24, 22, 4, 4), { w: 2.5 });
  } else if (it.k === 'stack') {
    for (let j = 0; j < 3; j++) {
      const yy = -34 - j * 34, ww = 130 - j * 6;
      fillPoly(rrPts(-ww / 2, yy, ww, 32, 10, 0), it.c, { seed: hashN(it.x, j), alpha: 0.75 - j * 0.12 });
      stroke(rrPts(-ww / 2, yy, ww, 32, 10, 8), { w: 2.8, seed: j });
      stroke([[-ww / 2 + 16, yy + 16], [ww / 2 - 16, yy + 16]], { w: 1.8, alpha: 0.5, double: false });
    }
  }
  pop();
}
function itemBox(it) {
  return { shoebox: [-58, -68, 116, 68], trainer: [-64, -60, 128, 60], bottle: [-22, -120, 44, 120], jar: [-34, -74, 68, 74], tube: [-20, -102, 40, 102], stack: [-68, -136, 136, 136] }[it.k];
}
function shopFront(t) {
  const pS = ez(t, 0.05, 1.0, E.out);
  // shelving
  stroke([[-540, -300], [-540, 360]], { w: 5, prog: pS });
  stroke([[540, -300], [540, 360]], { w: 5, prog: pS });
  for (const y of [-170, 40, 250]) {
    fillPoly(rrPts(-545, y, 1090, 22, 3, 0), PAL.brownL, { alpha: ez(t, 0.4, 0.6), seed: y });
    stroke(rrPts(-545, y, 1090, 22, 3, 10), { w: 3.5, prog: ez(t, 0.25 + (y + 170) / 1200, 0.7) });
  }
  stroke([[-560, 360], [560, 360]], { w: 4, prog: pS });
  // awning
  const pA = ez(t, 0.35, 0.8);
  for (let i = 0; i < 12; i++) {
    const x0 = -600 + i * 100;
    fillPoly([[x0, -400], [x0 + 100, -400], [x0 + 100, -330], ...ellPts(x0 + 50, -330, 50, 30, 0, 0, Math.PI), [x0, -400]], i % 2 ? PAL.white : PAL.coral, { alpha: pA, seed: i, edge: false });
    stroke(ellPts(x0 + 50, -330, 50, 30, 0, 0, Math.PI), { w: 3, prog: pA, seed: i + 30 });
  }
  stroke([[-605, -400], [605, -400]], { w: 4, prog: pA });
  // sign
  const pG = ez(t, 0.55, 0.6);
  card(-330, -515, 660, 96, { prog: pG, tint: PAL.mustL, tintA: 0.5 });
  text('Store 025 · Kingston', 0, -452, { size: 58, font: 'brush', align: 'center', prog: ez(t, 0.8, 0.9, E.lin) });
  SHOP_ITEMS.forEach((it) => shopItem(it, t));
}
const VCARDS = [
  { cue: 'theft', x: -760, rot: -0.05, label: 'Theft', tint: PAL.coralL },
  { cue: 'till', x: -380, rot: 0.035, label: 'Till fraud', tint: PAL.lavL },
  { cue: 'miscount', x: 0, rot: -0.03, label: 'Miscounts', tint: PAL.mustL },
  { cue: 'shortdel', x: 380, rot: 0.045, label: 'Short deliveries', tint: PAL.tealL },
  { cue: 'typo', x: 760, rot: -0.04, label: 'The odd typo', tint: PAL.sageL },
];
function vignetteCards(t) {
  VCARDS.forEach((v, i) => {
    const t0 = CUE[v.cue] - 0.08;
    const k = popIn(t, t0, 0.5);
    if (k <= 0) return;
    push(v.x, 290, k, v.rot + (1 - clamp(k)) * 0.2);
    card(-170, -165, 340, 320, { tint: v.tint, tintA: 0.35 });
    const c = S.ctx;
    c.save(); c.beginPath(); c.rect(-166, -160, 332, 252); c.clip();
    if (i === 0) raccoon(0, 86, 0.86, { phase: (t - t0) * 1.7 });
    if (i === 1) till(0, 84, 0.66, { receipt: ez(t, t0 + 0.3, 1.1), screen: 'VOID' });
    if (i === 2) clipboard(0, -24, 0.68, { nums: ['12', '13', '21?'], strike: ez(t, t0 + 0.5, 0.8) });
    if (i === 3) {
      const vx = lerp(-330, 6, ez(t, t0, 0.7, E.out));
      van(vx, 30, 0.62, { wheel: -(t - t0) * 9 * (1 - ez(t, t0, 0.7)), label: '12 BOXES' });
      const dk = ez(t, t0 + 0.75, 0.35);
      text('only 10 arrived', 0, 78, { size: 34, font: 'hand', weight: 700, align: 'center', color: PAL.coral, prog: dk });
    }
    if (i === 4) {
      text('120', -26, -6, { size: 120, font: 'hand', weight: 700, align: 'center', prog: ez(t, t0 + 0.1, 0.35, E.lin) });
      text('0', 74, -6, { size: 120, font: 'hand', weight: 700, align: 'center', color: PAL.coral, prog: ez(t, t0 + 0.55, 0.15, E.lin) });
      text('oops!', 70, 64, { size: 40, font: 'hand', weight: 700, align: 'center', color: PAL.coral, prog: ez(t, t0 + 0.75, 0.3, E.lin) });
      arrow(30, 48, 66, 16, { w: 3, color: PAL.coral, prog: ez(t, t0 + 0.75, 0.3) });
    }
    c.restore();
    text(v.label, 0, 140, { size: 50, font: 'brush', align: 'center', prog: ez(t, t0 + 0.15, 0.35, E.lin) });
    pop();
  });
}
function sceneA(t) {
  const sh = ez(t, 6.35, 0.75, E.inOut);
  push(0, 44 - 150 * sh, 1 - 0.22 * sh);
  shopFront(t);
  pop();
  vignetteCards(t);
}

/* ===================== B: what it costs ===================== */
function moneyBag(x, y, s, t) {
  push(x, y, s);
  const d = 'M-120,0 C-160,-50 -140,-160 -54,-200 L-78,-246 C-30,-266 30,-266 78,-246 L54,-200 C140,-160 160,-50 120,0 C86,30 -86,30 -120,0 Z';
  fillPoly(parsePath(d)[0], PAL.mustL, { seed: 1 });
  path(d, { w: 4 });
  stroke([[-58, -204], [58, -204]], { w: 5, color: PAL.brown });
  text('\u00a3', 0, -66, { size: 130, font: 'body', weight: 700, align: 'center', color: PAL.brown });
  text('sales', 0, -12, { size: 40, font: 'hand', weight: 700, align: 'center', color: PAL.brown });
  // the hole + patch lines
  fillSolid(ellPts(98, -24, 15, 9), PAL.ink, { alpha: 0.85 });
  pop();
}
function sceneB(t) {
  const L = -480;
  // "up to 2% of sales"
  text('up to', L - 330, -400, { size: 64, font: 'hand', weight: 700, prog: ez(t, CUE.s2, 0.4, E.lin), color: PAL.inkSoft });
  const k2 = popIn(t, CUE.pct, 0.55);
  if (k2 > 0) {
    push(L, -300, k2, -0.04);
    text('2%', 0, 88, { size: 280, font: 'brush', align: 'center', color: PAL.coral });
    pop();
    circleIt(L, -310, 230, 150, { prog: ez(t, CUE.pct + 0.35, 0.6), color: PAL.ink, w: 4 });
  }
  text('of sales', L, -95, { size: 66, font: 'hand', weight: 700, align: 'center', prog: ez(t, CUE.pct + 0.9, 0.5, E.lin) });
  // bag + dripping coins
  const kb = popIn(t, CUE.s2 - 0.3, 0.6);
  if (kb > 0) { push(L - 40, 360, kb); moneyBag(0, 0, 1.12, t); pop(); }
  for (let i = 0; i < 14; i++) {
    const t0 = CUE.s2 + 0.3 + i * 0.42;
    const dt = t - t0;
    if (dt < 0) continue;
    const hx = L - 40 + 112, hy = 336;
    let x, y, a = 1;
    if (dt < 0.35) { x = hx + dt * 60; y = hy + 0.5 * 2400 * dt * dt; }
    else { const r = dt - 0.35; x = hx + 21 + r * (150 + (i % 3) * 45); y = hy + 147 - Math.abs(Math.sin(r * 9)) * 18 * Math.exp(-r * 3); a = 1 - seg(r, 1.4, 2.2); }
    if (a > 0) coin(x, Math.min(y, 484), 22, { alpha: a });
  }
  // calendar flipping through the weeks
  const kc = popIn(t, CUE.weeks - 0.15, 0.5);
  if (kc > 0) {
    push(300, -270, kc * 1.2, 0.03);
    card(-150, -130, 300, 260, { tint: PAL.white });
    fillPoly(rrPts(-150, -130, 300, 64, 14, 0), PAL.coral, { seed: 5, alpha: 0.9 });
    for (const rx of [-80, 0, 80]) { stroke([[rx, -150], [rx, -112]], { w: 6, double: false }); }
    const wk = Math.min(6, 1 + Math.floor(Math.max(0, t - CUE.weeks) / 0.24));
    text('WEEK', 0, -82, { size: 34, font: 'body', weight: 700, align: 'center', color: PAL.white });
    text(String(wk), 0, 80, { size: 150, font: 'brush', align: 'center' });
    const ph = ((t - CUE.weeks) / 0.24) % 1;
    if (t > CUE.weeks && wk < 6 && ph < 0.6) {
      const k = ph / 0.6;
      fillSolid([[-146, -66], [146, -66], [146, -66 + 190 * (1 - k)], [-146, -66 + 190 * (1 - k)]], PAL.white, { alpha: 0.9 });
      stroke([[-146, -66 + 190 * (1 - k)], [146, -66 + 190 * (1 - k)]], { w: 2.5, alpha: 0.7 });
    }
    pop();
  }
  text('found weeks later…', 300, -50, { size: 58, font: 'hand', weight: 700, align: 'center', prog: ez(t, CUE.later - 0.2, 0.6, E.lin) });
  // the warehouse and the lost auditor
  const kw = ez(t, CUE.weeks + 0.1, 0.8);
  const stacks = [[110, 3], [210, 4], [310, 2], [600, 3], [700, 5], [800, 3], [900, 4]];
  stacks.forEach(([sx, n], j) => {
    for (let b = 0; b < n; b++) {
      const kk = clamp(kw * 3 - j * 0.25 - b * 0.12);
      if (kk > 0) box(sx - 48, 470 - (b + 1) * 74, 96, 72, { prog: kk, seed: j * 10 + b, color: b % 2 ? PAL.brownL : '#e6c39c' });
    }
  });
  if (t > CUE.weeks + 0.2) {
    const walkT = clamp((t - CUE.weeks - 0.2) / 2.1);
    const ax = lerp(370, 480, E.sine(walkT));
    const shrug = ez(t, CUE.ifatall, 0.35, E.back);
    person(ax, 470, 0.95, { shirt: PAL.tealL, skin: 3, hair: PAL.brown, walk: walkT < 1 ? (t * 2.2) % 1 : undefined, armL: lerp(0.3, 2.5, shrug), armR: lerp(2.0, 2.5, shrug), look: Math.sin(t * 3) * 0.6, mouth: shrug > 0.5 ? 'o' : undefined });
    if (shrug < 0.5) magnifier(ax + 52, 470 - 182, 0.65, { rot: -0.3 });
    const kq = popIn(t, CUE.ifatall + 0.05, 0.5);
    if (kq > 0) { push(ax + 20, 200, kq, 0.1); text('?', 0, 0, { size: 160, font: 'brush', align: 'center', color: PAL.coral }); pop(); }
    if (kq > 0) { push(ax - 80, 240, kq * 0.6, -0.2); text('?', 0, 0, { size: 90, font: 'brush', align: 'center', color: PAL.inkSoft }); pop(); }
  }
  text('…if at all', 700, -50, { size: 58, font: 'hand', weight: 700, align: 'center', color: PAL.coral, prog: ez(t, CUE.ifatall, 0.5, E.lin) });
}

/* ===================== C: meet Sentinel ===================== */
const GRID = { x0: -40, rows: [-150, 50, 250] };
function sceneC(t) {
  // owl flies in and lands
  const land = CUE.s3 + 0.8;
  const fk = clamp((t - (CUE.s3 - 0.1)) / (land - (CUE.s3 - 0.1)));
  const P0 = [980, -760], P1 = [500, -700], P2 = [-560, -260], P3 = [-560, 330];
  const fp = bez(P0, P1, P2, P3, 1);
  let ox, oy;
  { const u = E.out2(fk), v = 1 - u; ox = v * v * v * P0[0] + 3 * v * v * u * P1[0] + 3 * v * u * u * P2[0] + u * u * u * P3[0]; oy = v * v * v * P0[1] + 3 * v * v * u * P1[1] + 3 * v * u * u * P2[1] + u * u * u * P3[1]; }
  const flying = t < land;
  const after = t - land;
  const squash = flying ? -0.05 : 0.16 * Math.exp(-after * 7) * Math.cos(after * 22);
  const pointing = ez(t, CUE.points - 0.1, 0.4, E.back);
  const flap = flying ? Math.sin(t * 28) * 0.9 + 0.3 : 0;
  if (t > CUE.s3 - 0.1) {
    owl(ox, oy, 1.3, {
      wingL: flap + (flying ? 0 : Math.sin(after * 2) * 0.04),
      wingR: flap + pointing * 1.35,
      squash, rot: flying ? -0.18 * (1 - fk) : 0,
      look: pointing > 0.1 ? [0.9, -0.3] : flying ? [-0.6, 0.4] : [0.5, -0.2], brow: pointing,
    });
    sparkle(-560, -60, 1.6, land, t);
  }
  // wordmark
  const nk = ez(t, CUE.name, 1.4, E.lin);
  text('Inventory Sentinel', 250, -310, { size: 132, font: 'brush', align: 'center', prog: nk, color: PAL.ink });
  stroke(curvePts(-210, -278, 720, -286, -0.02), { w: 7, color: PAL.coral, prog: ez(t, CUE.name + 1.3, 0.5), double: false });
  text('250 items × 40 stores × 120 days = 1.2 million checks', 290, -222, { size: 36, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.day + 0.5, 1.0, E.lin) });
  // the three rows
  const rows = [
    { label: 'every item', cue: CUE.item, n: 12, gap: 66 },
    { label: 'every store', cue: CUE.store, n: 9, gap: 88 },
    { label: 'every day', cue: CUE.day, n: 14, gap: 57 },
  ];
  const hot = [7, 3, 10];
  rows.forEach((r, ri) => {
    const y = GRID.rows[ri];
    text(r.label, GRID.x0 - 34, y + 14, { size: 54, font: 'hand', weight: 700, align: 'right', prog: ez(t, r.cue - 0.1, 0.35, E.lin) });
    for (let i = 0; i < r.n; i++) {
      const ti = r.cue + i * 0.035;
      const k = popIn(t, ti, 0.35);
      if (k <= 0) continue;
      const x = GRID.x0 + 30 + i * r.gap;
      const isHot = i === hot[ri] && t > CUE.points + 0.25 + ri * 0.25;
      push(x, y, k);
      if (ri === 0) {
        fillPoly(rrPts(-24, -24, 48, 48, 8, 0), isHot ? PAL.coral : [PAL.tealL, PAL.mustL, PAL.lavL, PAL.coralL, PAL.sageL][i % 5], { seed: i });
        stroke(rrPts(-24, -24, 48, 48, 8, 6), { w: 2.5, seed: i + 3 });
      } else if (ri === 1) {
        storeIcon(0, 30, 0.62, { color: isHot ? PAL.coral : PAL.teal });
      } else {
        fillPoly(rrPts(-22, -22, 44, 44, 5, 0), isHot ? PAL.coral : PAL.white, { seed: i + 40 });
        stroke(rrPts(-22, -22, 44, 44, 5, 6), { w: 2.5, seed: i + 50 });
        text(String(i + 1), 0, 12, { size: 26, font: 'body', weight: 700, align: 'center', jit: 0.5 });
      }
      pop();
      // tick sweep, replaced by a red flag on the hot ones
      const tk = ez(t, ti + 0.25, 0.2);
      if (tk > 0 && !isHot) check(x + 18, y - 22, 0.8, { prog: tk });
      if (isHot) {
        circleIt(x, y, 46, 44, { prog: ez(t, CUE.points + 0.25 + ri * 0.25, 0.45) });
        text('!', x + 34, y - 30, { size: 64, font: 'brush', color: PAL.coral, prog: 1 });
      }
    }
  });
  // teams walk to the flagged spots
  const team = [[-60, 0, PAL.sage], [220, 2, PAL.teal]];
  team.forEach(([tx, skin, col], j) => {
    const t0 = CUE.places + j * 0.35;
    if (t < t0) return;
    const wk = clamp((t - t0) / 1.6);
    const x = lerp(1050, 420 + tx, E.out2(wk));
    person(x, 492, 0.78, { hat: 'hard', vest: true, shirt: col, skin, walk: wk < 1 ? (t * 2.4) % 1 : undefined, armR: wk >= 1 && j === 0 ? 2.6 : undefined, flip: true, look: -0.6 });
  });
}

/* ===================== D: plug and play over MCP ===================== */
const D_CABLE = [[-492, 210], [-430, 330], [-300, 420], [-170, 380], [-110, 250]];
function cablePath(plugX, plugY) {
  const pts = [[-490, 160]];
  const cps = bez([-490, 160], [-380, 470], [plugX - 260, plugY + 230], [plugX - 70, plugY], 30);
  return pts.concat(cps.slice(1));
}
function sceneD(t) {
  // title
  text('plug & play', -330, -380, { size: 120, font: 'brush', align: 'center', prog: ez(t, CUE.plug, 0.9, E.lin) });
  stroke(curvePts(-600, -350, -60, -356, -0.03), { w: 6, color: PAL.mustard, prog: ez(t, CUE.plug + 0.8, 0.4), double: false });
  // vendor system
  push(-640, 330, 0.95); cabinet(0, 0, 1, { prog: ez(t, CUE.plug - 0.2, 1.2) }); pop();
  text('your inventory system', -640, -82, { size: 44, font: 'hand', weight: 700, align: 'center', prog: ez(t, CUE.plug + 0.6, 0.8, E.lin) });
  // socket block on Sentinel's console
  const sk = ez(t, CUE.plug + 0.2, 0.7);
  if (sk > 0) {
    fillPoly(rrPts(70, 40, 150, 200, 18, 0), PAL.white, { seed: 3, alpha: sk });
    stroke(rrPts(70, 40, 150, 200, 18, 12), { w: 4, prog: sk });
    fillSolid(rrPts(64, 96, 16, 30, 4, 0), PAL.ink, { alpha: sk });
    fillSolid(rrPts(64, 156, 16, 30, 4, 0), PAL.ink, { alpha: sk });
    text('MCP', 145, 26, { size: 64, font: 'brush', align: 'center', color: PAL.tealD, prog: ez(t, CUE.speaks + 0.6, 0.5, E.lin) });
    stroke(bez([220, 140], [280, 140], [300, 300], [372, 300], 16), { w: 6, color: PAL.ink, prog: sk });
  }
  text('Model Context Protocol', 145, 300, { size: 34, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.speaks + 1.0, 0.9, E.lin) });
  // Sentinel on its pedestal
  const pk = ez(t, CUE.plug + 0.3, 0.6);
  if (pk > 0) {
    fillPoly(rrPts(360, 250, 260, 120, 14, 0), PAL.tealL, { seed: 9, alpha: pk });
    stroke(rrPts(360, 250, 260, 120, 14, 10), { w: 4, prog: pk });
    text('Sentinel', 490, 328, { size: 50, font: 'brush', align: 'center', prog: pk });
  }
  const hop = popIn(t, CUE.plug + 0.5, 0.5);
  if (hop > 0) owl(490, 252, 0.95 * hop, { look: t < CUE.server ? [-0.7, 0.2] : [0.8, -0.1], wingL: t > CUE.speaks && t < CUE.speaks + 1.2 ? 0.6 + Math.sin(t * 10) * 0.2 : 0, blinkSeed: 2, still: false });
  // speech bubble
  const bk = popIn(t, CUE.speaks, 0.45) * (1 - seg(t, CUE.url - 0.4, CUE.url));
  if (bk > 0) {
    push(600, -160, bk);
    card(-160, -70, 320, 120, { r: 50 });
    fillSolid([[-40, 46], [20, 46], [-70, 110]], PAL.white, { still: true });
    stroke([[-40, 50], [-70, 110], [20, 50]], { w: 3 });
    text('I speak MCP!', 0, 10, { size: 50, font: 'hand', weight: 700, align: 'center' });
    pop();
  }
  // the plug travels and clicks in
  const plugIn = CUE.connects + 2.4;
  const mk = ez(t, CUE.connects + 0.3, 2.1, E.inOut);
  const plugX = lerp(-150, 32, mk), plugY = lerp(330, 140, E.out(mk));
  const ck = ez(t, CUE.plug + 0.6, 0.8);
  if (ck > 0) {
    const cp = cablePath(plugX, plugY);
    stroke(cp, { w: 7, color: PAL.ink, prog: ck, rough: 1 });
    // plug body (prongs point right)
    push(plugX, plugY, 1, (1 - mk) * 0.4);
    alpha(clamp(ck * 2 - 1));
    stroke([[30, -30], [70, -30]], { w: 9, color: PAL.greyL, double: false }); stroke([[30, -30], [70, -30]], { w: 2.5 });
    stroke([[30, 30], [70, 30]], { w: 9, color: PAL.greyL, double: false }); stroke([[30, 30], [70, 30]], { w: 2.5 });
    fillPoly(rrPts(-80, -56, 112, 112, 26, 0), PAL.mustard, { seed: 4 });
    stroke(rrPts(-80, -56, 112, 112, 26, 10), { w: 4 });
    pop();
    sparkle(80, 140, 1.4, plugIn, t, PAL.mustard);
    // data flowing along the cable into Sentinel
    if (t > CUE.flow) {
      const full = cp.concat(bez([plugX + 70, plugY], [280, 140], [300, 300], [372, 300], 12));
      const res = resample(full, 10);
      const nP = 22;
      const fa = Math.min(seg(t, CUE.flow, CUE.flow + 0.4), 1 - seg(t, CUE.server + 0.6, CUE.server + 1.2));
      for (let i = 0; i < nP; i++) {
        const u = ((t - CUE.flow) * 0.55 + i / nP) % 1;
        const p = res[Math.floor(u * (res.length - 1))];
        const col = [PAL.coral, PAL.teal, PAL.mustard, PAL.sage, PAL.lav][i % 5];
        fillSolid(rrPts(p[0] - 9, p[1] - 9, 18, 18, 4, 0), col, { alpha: fa, still: true });
      }
    }
  }
  // URL + sync button
  const uk = popIn(t, CUE.url - 0.25, 0.45);
  if (uk > 0) {
    push(-330, -205, uk, -0.015);
    card(-300, -100, 600, 190, { tint: PAL.sky, tintA: 0.4 });
    text('Connect a data source', -270, -52, { size: 34, font: 'body', weight: 700 });
    fillSolid(rrPts(-270, -30, 360, 56, 10, 0), PAL.white, { still: true });
    stroke(rrPts(-270, -30, 360, 56, 10, 6), { w: 2.5 });
    const url = 'https://stock.yourco.com/mcp';
    const n = Math.floor(ez(t, CUE.url, 1.0, E.lin) * url.length);
    text(url.slice(0, n), -256, 8, { size: 24, font: 'body', color: PAL.tealD, jit: 0.4 });
    if (n < url.length && Math.floor(t * 3) % 2 === 0) stroke([[-256 + textW(url.slice(0, n), 24, 'body') + 4, -16], [-256 + textW(url.slice(0, n), 24, 'body') + 4, 14]], { w: 2.5, double: false });
    const press = ez(t, CUE.sync + 0.08, 0.08) * (1 - ez(t, CUE.sync + 0.25, 0.15));
    push(190, -2, 1 - press * 0.08);
    fillPoly(rrPts(-74, -28, 148, 56, 28, 0), t > CUE.sync ? PAL.sage : PAL.teal, { seed: 8 });
    stroke(rrPts(-74, -28, 148, 56, 28, 8), { w: 3 });
    text(t > CUE.sync + 0.3 ? 'syncing…' : 'Sync now', 0, 10, { size: 28, font: 'body', weight: 700, align: 'center', color: PAL.white });
    pop();
    // cursor
    const hk = ez(t, CUE.url + 0.6, 0.6, E.inOut);
    if (hk > 0 && t < CUE.nomig) hand(lerp(320, 205, hk), lerp(200, 14, hk) + press * 8, 0.9, { rot: -0.3 });
    pop();
  }
  // counter
  const rows = Math.round(clamp((t - CUE.flow) / 2.0) * 1200000);
  if (t > CUE.flow) {
    text(rows.toLocaleString('en-GB') + ' rows', 490, 440, { size: 54, font: 'brush', align: 'center', prog: ez(t, CUE.flow, 0.3, E.lin) });
    text('120 days of history in ~30 seconds', 490, 488, { size: 32, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.flow + 1.6, 0.6, E.lin) });
  }
  // stamps
  [['NO MIGRATION', CUE.nomig, -560, -0.08], ['NO REBUILD', CUE.noreb, -150, 0.06]].forEach(([s, c, x, r]) => {
    const k = ez(t, c - 0.05, 0.22, E.out);
    if (k <= 0) return;
    push(x, 470, 1.6 - 0.6 * k, r);
    alpha(k);
    const w = textW(s, 60, 'brush') + 50;
    stroke(rrPts(-w / 2, -48, w, 84, 10, 6), { w: 6, color: PAL.coral, rough: 2.5 });
    text(s, 0, 16, { size: 60, font: 'brush', align: 'center', color: PAL.coral });
    pop();
  });
  /* ---- D2: Sentinel is an MCP server too ---- */
  const X2 = 1300;
  text('…and an MCP server too', X2 + 30, -400, { size: 96, font: 'brush', align: 'center', prog: ez(t, CUE.server + 0.2, 1.0, E.lin) });
  text('32 tools your own AI agents can call', X2 + 30, -320, { size: 44, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.server + 1.1, 0.9, E.lin) });
  const stK = ez(t, CUE.server + 0.3, 0.6);
  if (stK > 0) {
    stroke(bez([620, 300], [700, 300], [740, 120], [880, 120], 16), { w: 6, prog: stK });
    fillPoly(rrPts(880, 60, 420, 120, 20, 0), PAL.white, { seed: 31, alpha: stK });
    stroke(rrPts(880, 60, 420, 120, 20, 12), { w: 4, prog: stK });
    text('MCP server', 1090, 50, { size: 40, font: 'brush', align: 'center', color: PAL.tealD, prog: stK });
    for (let i = 0; i < 3; i++) {
      fillSolid(rrPts(940 + i * 130, 92, 60, 56, 12, 0), PAL.greyL, { alpha: stK, still: true });
      stroke(rrPts(940 + i * 130, 92, 60, 56, 12, 6), { w: 2.5, prog: stK });
      fillSolid(rrPts(956 + i * 130, 108, 8, 24, 3, 0), PAL.ink, { alpha: stK });
      fillSolid(rrPts(976 + i * 130, 108, 8, 24, 3, 0), PAL.ink, { alpha: stK });
    }
  }
  const AG = [['Claude Desktop', PAL.coral, 0], ['IDE agents', PAL.lav, 1], ['your own apps', PAL.mustard, 2]];
  AG.forEach(([name, col, i]) => {
    const t0 = CUE.agents - 0.6 + i * 0.3, tp = CUE.agents + 0.55 + i * 0.72;
    const bx = 1480 + i * 275, by = 380;
    bot(bx, by, 1.2, { prog: ez(t, t0, 0.5), color: col, seed: i * 2, light: col });
    text(name, bx, by + 72, { size: 40, font: 'hand', weight: 700, align: 'center', prog: ez(t, t0 + 0.3, 0.5, E.lin) });
    if (t > t0 + 0.2) {
      const sx = 970 + i * 130, sy = 120;
      const k = ez(t, t0 + 0.4, tp - t0 - 0.4, E.inOut);
      const px = lerp(bx - 40, sx, k), py = lerp(by - 120, sy - 22, k);
      stroke(bez([bx - 40, by - 70], [bx - 60, by + 40], [px, py + 160], [px, py + 40], 18), { w: 5, color: col, double: false });
      stroke(bez([bx - 40, by - 70], [bx - 60, by + 40], [px, py + 160], [px, py + 40], 18), { w: 2 });
      push(px, py + (t > tp ? -6 : 0));
      fillPoly(rrPts(-26, 0, 52, 46, 10, 0), col, { seed: i + 60 });
      stroke(rrPts(-26, 0, 52, 46, 10, 6), { w: 3 });
      if (t < tp) { stroke([[-10, 0], [-10, -20]], { w: 4 }); stroke([[10, 0], [10, -20]], { w: 4 }); }
      pop();
      sparkle(sx, sy - 10, 1, tp, t, col);
    }
  });
}
