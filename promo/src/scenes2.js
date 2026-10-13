/* Scenes E-I: unsupervised learning, the executive screen, the agent team, learning loop, finale. */
'use strict';

/* ===================== E: learns what normal looks like ===================== */
const SCATTER = (() => {
  const r = rng(7), pts = [];
  const g = () => { let u = 0; for (let i = 0; i < 6; i++) u += r(); return (u - 3) / Math.sqrt(0.5); };
  for (let i = 0; i < 170; i++) { const a = g(), b = g(); pts.push({ x: -470 + a * 120 + b * 20, y: 70 + a * -45 + b * 55, out: false, d: r() }); }
  [[-830, -230], [-150, -250], [-200, 330], [-800, 330], [-300, -180], [-700, 250], [-110, 120]].forEach(([x, y]) => pts.push({ x, y, out: true, d: r() }));
  return pts;
})();
const SIGNALS = ['shrinkage %', 'gap vs normal', '7-day loss', '7-day loss %', 'miscount reversal', 'sales velocity', 'zero-sales streak', 'receiving gap',
  'delivery size', 'adjustment size', 'returns', 'keyed-in scans', 'voided lines', 'overrides', 'after-hours scans', 'store-wide loss'];
function sceneE(t) {
  // the scatter owns the stage first, then slides left to make room for the signals
  const slide = lerp(430, 0, ez(t, CUE.sixteen - 0.8, 0.9, E.inOut));
  push(slide, 0);
  // axes
  const ak = ez(t, CUE.s5 - 0.4, 0.6);
  arrow(-880, 400, -880, -330, { w: 4, prog: ak, bend: 0.01 });
  arrow(-880, 400, -40, 400, { w: 4, prog: ak, bend: -0.01 });
  text('stock gap', -120, 450, { size: 40, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ak });
  push(-920, -160, 1, -Math.PI / 2); text('till voids', 0, 0, { size: 40, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ak }); pop();
  // the "normal" blob forms behind the dots
  const bk = ez(t, CUE.learns + 1.3, 0.9);
  if (bk > 0) {
    const blob = []; for (let i = 0; i <= 40; i++) { const a = (i / 40) * Math.PI * 2; const rr = 1 + Math.sin(a * 3 + 1) * 0.06; blob.push([-470 + Math.cos(a) * 300 * rr * Math.cos(-0.35) - Math.sin(a) * 170 * rr * Math.sin(-0.35), 70 + Math.cos(a) * 300 * rr * Math.sin(-0.35) + Math.sin(a) * 170 * rr * Math.cos(-0.35)]); }
    fillPoly(blob, PAL.sageL, { alpha: 0.8 * bk, seed: 3 });
    stroke(blob, { w: 3, color: PAL.sage, prog: bk, rough: 3 });
    text('normal', -250, -120, { size: 64, font: 'brush', color: PAL.sage, prog: ez(t, CUE.learns + 1.8, 0.5, E.lin) });
  }
  SCATTER.forEach((p, i) => {
    const t0 = CUE.learns - 0.2 + (p.out ? 1.5 + p.d * 0.3 : p.d * 1.5);
    const k = popIn(t, t0, 0.3);
    if (k <= 0) return;
    const rr = (p.out ? 11 : 7) * k;
    fillSolid(ellPts(p.x, p.y, rr, rr), p.out ? PAL.coral : PAL.ink, { alpha: p.out ? 0.95 : 0.75, seed: i });
    if (p.out) circleIt(p.x, p.y, 30, 28, { prog: ez(t, CUE.learns + 2.2 + p.d * 0.3, 0.4), w: 3 });
  });
  text('unusual!', -140, -290, { size: 46, font: 'hand', weight: 700, color: PAL.coral, prog: ez(t, CUE.learns + 2.6, 0.5, E.lin) });
  // labels fall in, then get crossed out
  const tags = [['theft?', -760, -0.2], ['error?', -540, 0.12], ['fine?', -320, -0.1]];
  tags.forEach(([s, x, r], i) => {
    const t0 = CUE.nolabels - 0.3 + i * 0.12;
    if (t < t0) return;
    const fall = ez(t, t0, 0.5, E.back);
    const gone = seg(t, CUE.nolabels + 1.05, CUE.nolabels + 1.25);
    const y = lerp(-640, -400, fall);
    if (gone < 1) {
      push(x, y, 1 - gone, r + Math.sin((t - t0) * 6) * 0.05 * (1 - fall));
      const w = textW(s, 44, 'hand', 700) + 70;
      const tag = [[-w / 2 + 26, -34], [w / 2, -34], [w / 2, 34], [-w / 2 + 26, 34], [-w / 2, 0]];
      fillPoly(tag, PAL.mustL, { seed: i + 5 });
      stroke(polyClosed(tag), { w: 3 });
      stroke(ellPts(-w / 2 + 26, 0, 7, 7), { w: 2.5, double: false });
      text(s, 14, 14, { size: 44, font: 'hand', weight: 700, align: 'center' });
      cross(0, 0, 2.2, { prog: ez(t, CUE.nolabels + 0.5 + i * 0.1, 0.3) });
      pop();
    }
    poof(x, y, 1.2, CUE.nolabels + 1.05, t);
  });
  text('no labels needed', -470, -400, { size: 74, font: 'brush', align: 'center', color: PAL.tealD, prog: ez(t, CUE.nolabels + 1.15, 0.7, E.lin) });
  pop();
  // sixteen signals
  text('16 signals', 470, -420, { size: 92, font: 'brush', align: 'center', prog: ez(t, CUE.sixteen - 0.1, 0.5, E.lin) });
  SIGNALS.forEach((name, i) => {
    const c = i % 4, rI = Math.floor(i / 4);
    const x = 60 + c * 218, y = -340 + rI * 116;
    const t0 = CUE.sixteen + 0.05 + i * 0.07;
    const k = popIn(t, t0, 0.4);
    if (k <= 0) return;
    const hl = (i === 12 && t > CUE.voids) || (i === 14 && t > CUE.afterhours);
    push(x + 100, y + 46, k, ((i * 37) % 7 - 3) * 0.006);
    card(-100, -46, 200, 92, { tint: hl ? PAL.coralL : [PAL.sky, PAL.mustL, PAL.lavL, PAL.sageL][(i + rI) % 4], tintA: hl ? 0.8 : 0.45, shadow: false, w: 2.5 });
    text(name, 0, -8, { size: Math.min(27, (27 * 176) / textW(name, 27, 'body', 700)), font: 'body', weight: 700, align: 'center', jit: 0.5 });
    const rr = rng(i + 3), sp = [];
    for (let j = 0; j < 12; j++) sp.push([-80 + j * 14.5, 26 - rr() * 12 - (hl && j === 9 ? 18 : 0)]);
    stroke(sp, { w: 2.2, color: hl ? PAL.coral : PAL.tealD, double: false, seed: i });
    pop();
  });
  // highlight: voided lines, after-hours scans
  const vk = ez(t, CUE.voids, 0.5);
  if (vk > 0) { circleIt(60 + 0 * 218 + 100, -340 + 3 * 116 + 46, 128, 66, { prog: vk }); push(70, 210, popIn(t, CUE.voids + 0.1, 0.4)); till(0, 0, 0.45, { screen: 'VOID' }); pop(); }
  const hk = ez(t, CUE.afterhours, 0.5);
  if (hk > 0) { circleIt(60 + 2 * 218 + 100, -340 + 3 * 116 + 46, 128, 66, { prog: hk }); push(600, 210, popIn(t, CUE.afterhours + 0.1, 0.4)); moon(0, -40, 1.5); text('11:48 pm', 90, -20, { size: 44, font: 'hand', weight: 700, color: PAL.lav }); pop(); }
}

/* ===================== E2: models compete ===================== */
const RACERS = [
  { name: 'Rule of thumb (today)', col: PAL.grey, end: 0.6, skin: 3 },
  { name: 'Autoencoder', col: PAL.lav, end: 0.74, skin: 1 },
  { name: 'Local Outlier Factor', col: PAL.teal, end: 0.84, skin: 2 },
  { name: 'Ensemble', col: PAL.mustard, end: 0.95, skin: 0 },
  { name: 'Isolation Forest', col: PAL.sage, end: 1.0, skin: 4 },
];
function sceneE2(t) {
  text('models compete on your own history', -330, -420, { size: 72, font: 'brush', align: 'center', prog: ez(t, CUE.compete, 1.4, E.lin) });
  const x0 = -790, x1 = 170, laneH = 132, ly0 = -318;
  const tk = ez(t, CUE.compete - 0.3, 0.8);
  for (let i = 0; i < RACERS.length; i++) fillPoly(rrPts(-890, ly0 - 40 + i * laneH + 4, 1150, laneH - 8, 8, 0), i % 2 ? PAL.mustL : PAL.sky, { alpha: 0.35 * tk, edge: false, seed: 300 + i, grainA: 0.1 });
  for (let i = 0; i <= RACERS.length; i++) stroke([[-890, ly0 - 40 + i * laneH], [260, ly0 - 40 + i * laneH]], { w: 2.5, prog: tk, color: PAL.inkSoft, double: false, seed: i });
  // finish line
  for (let j = 0; j < 20; j++) {
    const y = ly0 - 40 + j * (laneH * RACERS.length / 20);
    fillSolid(rrPts(x1 + 10 + (j % 2) * 16, y, 16, laneH * RACERS.length / 20, 0, 0), PAL.ink, { alpha: tk * 0.85, still: true });
  }
  stroke([[x0 - 10, ly0 - 40], [x0 - 10, ly0 - 40 + laneH * 5]], { w: 3, prog: tk, color: PAL.coral });
  const go = CUE.compete + 0.35, fin = CUE.winner;
  RACERS.forEach((r, i) => {
    const y = ly0 - 40 + (i + 1) * laneH - 10;
    text(r.name, -880, ly0 - 40 + i * laneH + 38, { size: 38, font: 'hand', weight: 700, color: PAL.ink, prog: ez(t, CUE.compete - 0.1 + i * 0.1, 0.4, E.lin) });
    const u = seg(t, go, fin);
    const shape = [E.sine, E.out2, E.inOut, E.sine, E.in][i];
    let p = r.end * shape(u);
    if (i === 4) p = u < 1 ? Math.min(1, 0.92 * E.sine(u) + 0.08 * Math.pow(u, 6)) : 1;
    const x = lerp(x0, x1 + 40, p);
    const moving = t > go && t < fin + 0.1 && p < r.end;
    if (t > CUE.compete - 0.2) person(x, y, 0.62, { shirt: r.col, skin: r.skin, walk: moving ? (t * 3.4 + i * 0.3) % 1 : undefined, armL: moving ? undefined : i === 4 && t > fin ? 2.8 : 0.2, armR: moving ? undefined : i === 4 && t > fin ? 2.8 : 0.2, prog: ez(t, CUE.compete - 0.2 + i * 0.08, 0.3) });
    if (moving && (Math.floor(t * 8) + i) % 2 === 0) poof(x - 34, y - 6, 0.4, t - 0.1, t);
  });
  // confetti + trophy
  if (t > fin) {
    const r = rng(99);
    for (let i = 0; i < 36; i++) {
      const dt = t - fin, a = -Math.PI / 2 + (r() - 0.5) * 2.4, v = 500 + r() * 500;
      const x = x1 + 40 + Math.cos(a) * v * dt, y = ly0 + 4 * laneH + 20 + Math.sin(a) * v * dt + 900 * dt * dt;
      if (dt < 2.2) stroke([[x, y], [x + Math.cos(a + dt * 9) * 16, y + Math.sin(a + dt * 9) * 16]], { w: 5, color: [PAL.coral, PAL.mustard, PAL.teal, PAL.sage, PAL.lav][i % 5], alpha: 1 - seg(dt, 1.5, 2.2), double: false, seed: i });
    }
  }
  const trk = popIn(t, fin + 0.15, 0.5);
  if (trk > 0) { push(300, -150, trk, 0.05); trophy(0, 0, 0.85); pop(); text('winner!', 300, -300, { size: 56, font: 'brush', align: 'center', color: PAL.sage, prog: ez(t, fin + 0.3, 0.4, E.lin) }); }
  // 1.7x bars
  const base = 330;
  const b1 = ez(t, CUE.onepoint7 - 0.3, 0.7), b2 = ez(t, CUE.onepoint7 + 0.1, 1.0, E.back);
  if (b1 > 0) {
    stroke([[440, base], [900, base]], { w: 4, prog: b1 });
    const h1 = 190 * b1, h2 = 323 * b2;
    fillPoly(rrPts(470, base - h1, 150, h1, 6, 0), PAL.greyL, { seed: 1 });
    stroke(rrPts(470, base - h1, 150, h1, 6, 8), { w: 3 });
    if (b2 > 0) { fillPoly(rrPts(700, base - h2, 150, h2, 6, 0), PAL.teal, { seed: 2 }); stroke(rrPts(700, base - h2, 150, h2, 6, 8), { w: 3 }); }
    text("today's rule", 545, base + 50, { size: 40, font: 'hand', weight: 700, align: 'center', prog: b1 });
    text('Sentinel', 775, base + 50, { size: 44, font: 'brush', align: 'center', prog: ez(t, CUE.onepoint7 + 0.4, 0.4, E.lin) });
    strike(470, 620, base + 40, { prog: 0 });
    stroke(curvePts(470, base + 64, 622, base + 62, 0.02), { w: 4, color: PAL.coral, prog: ez(t, CUE.rule + 0.1, 0.4), double: false });
  }
  const k17 = popIn(t, CUE.onepoint7 + 0.6, 0.55);
  if (k17 > 0) { push(670, -150, k17, -0.06); text('1.7×', 0, 0, { size: 170, font: 'brush', align: 'center', color: PAL.coral }); pop(); }
  arrow(560, base - 215, 760, base - 345, { w: 4, color: PAL.coral, prog: ez(t, CUE.onepoint7 + 0.9, 0.5), bend: -0.25 });
  text('better at putting real problems first', 670, 450, { size: 38, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.onepoint7 + 1.4, 1.0, E.lin) });
}

/* ===================== F: the executive screen ===================== */
const DZ = 2.25, LAP_Y = 420, SCR = { x: -414, y: LAP_Y - 514, w: 828, h: 478 };
const HEAT = window.HEAT_DATA;
const TOP5 = [
  ['Canterbury · Printed Trainers', 'Delivery booked as 80 units but 8 were scanned in', 'Receiving error', '£898', 'critical'],
  ['Newcastle · Slim Sandals', '6 returns recorded, far more than this item normally gets', 'Till / scan fraud', '£774', 'critical'],
  ['Leeds · Essential Blouse', '5 returns recorded, far more than this item normally gets', 'Till / scan fraud', '£582', 'critical'],
  ['Croydon 2 · Relaxed Sandals', '10 scans outside opening hours', 'Internal theft', '£622', 'high'],
  ['Belfast · Printed Trainers', 'Shrinkage over the last 7 days is 127%', 'Internal theft', '£405', 'high'],
];
function dashboard(t) {
  // local screen coordinates: (0,0) top-left of the white screen, 828 x 478
  const ls0 = S.ls; S.ls = 1 / DZ;
  const sk = ez(t, CUE.lead + 0.6, 0.8);
  // top bar
  fillPoly(rrPts(0, 0, 828, 36, 0, 0), PAL.sky, { alpha: 0.7 * sk, seed: 1, edge: false });
  fillSolid(ellPts(22, 18, 10, 10), PAL.teal, { alpha: sk });
  text('Inventory Sentinel', 38, 25, { size: 19, font: 'brush', prog: sk });
  ['Overview', 'Alerts', 'Plan', 'Story'].forEach((s, i) => text(s, 230 + i * 70, 24, { size: 12.5, font: 'body', weight: i === 0 ? 700 : 400, color: i === 0 ? PAL.ink : PAL.inkSoft, prog: sk, jit: 0.4 }));
  fillPoly(rrPts(640, 8, 174, 21, 10, 0), PAL.white, { alpha: sk, seed: 2, edge: false });
  stroke(rrPts(640, 8, 174, 21, 10, 4), { w: 1.5, prog: sk, double: false });
  fillPoly(rrPts(642, 10, 86, 17, 8, 0), PAL.teal, { alpha: sk, seed: 3, edge: false });
  text('Executive', 685, 23, { size: 12, font: 'body', weight: 700, align: 'center', color: PAL.white, prog: sk, jit: 0.3 });
  text('Analyst', 772, 23, { size: 12, font: 'body', align: 'center', color: PAL.inkSoft, prog: sk, jit: 0.3 });
  // heading
  text('Where stock is going missing, and what to do first', 16, 66, { size: 21, font: 'body', weight: 700, prog: ez(t, CUE.lead + 1.0, 1.2, E.lin), jit: 0.5 });
  text('Every store, item and day (1,200,000 checked): the few places that look wrong, why, and what is at stake.', 16, 84, { size: 10.5, font: 'body', color: PAL.inkSoft, prog: ez(t, CUE.lead + 1.6, 1.0, E.lin), jit: 0.3 });
  // placeholders before the numbers arrive
  const heroes = [
    { cue: CUE.varisk, label: 'STOCK VALUE AT RISK', sub: 'flagged across 40 stores, valued at cost', tint: PAL.coralL },
    { cue: CUE.visit, label: 'WORTH A VISIT THIS WEEK', sub: '£19k expected back, 5x the cost of 120 hours', tint: PAL.mustL },
    { cue: CUE.beats, label: "MACHINE LEARNING VS TODAY'S RULE", sub: 'Isolation Forest vs a simple shrinkage threshold', tint: PAL.sageL },
  ];
  heroes.forEach((h, i) => {
    const x = 14 + i * 272, y = 96, w = 256, hh = 100;
    const ck = ez(t, CUE.three + i * 0.18, 0.45);
    stroke(rrPts(x, y, w, hh, 10, 6), { w: 2.2, color: PAL.greyL, prog: sk * (1 - ck), double: false });
    if (ck > 0) {
      fillSolid(rrPts(x, y, w, hh, 10, 0), PAL.white, { alpha: ck, still: true });
      fillPoly(rrPts(x, y, w, hh, 10, 0), h.tint, { alpha: 0.35 * ck, seed: 10 + i, edge: false });
      stroke(rrPts(x, y, w, hh, 10, 6), { w: 2.4, prog: ck });
    }
    text(h.label, x + 12, y + 20, { size: 9.5, font: 'body', weight: 700, color: PAL.inkSoft, prog: ez(t, h.cue - 0.2, 0.4, E.lin), jit: 0.3 });
    const nk = ez(t, h.cue, 0.9, E.out);
    if (nk > 0) {
      let big;
      if (i === 0) big = '£' + Math.round(144 * nk) + 'k';
      else if (i === 1) big = Math.round(99 * nk) + ' alerts';
      else big = (1 + 0.7 * nk).toFixed(1) + 'x better';
      text(big, x + 12, y + 64, { size: 40, font: 'brush', color: i === 0 ? PAL.coral : i === 1 ? PAL.ink : PAL.tealD, jit: 0.6 });
    }
    text(h.sub, x + 12, y + 86, { size: 10, font: 'body', color: PAL.inkSoft, prog: ez(t, h.cue + 0.5, 0.8, E.lin), jit: 0.3 });
  });
  // lower cards
  const lk = ez(t, CUE.where - 0.4, 0.5), rk = ez(t, CUE.first - 0.4, 0.5);
  stroke(rrPts(14, 210, 386, 248, 10, 6), { w: 2.2, color: PAL.greyL, prog: sk * (1 - lk), double: false });
  stroke(rrPts(414, 210, 400, 248, 10, 6), { w: 2.2, color: PAL.greyL, prog: sk * (1 - rk), double: false });
  if (lk > 0) {
    stroke(rrPts(14, 210, 386, 248, 10, 6), { w: 2.4, prog: lk });
    text('Where it happens', 28, 236, { size: 16, font: 'body', weight: 700, prog: lk, jit: 0.4 });
    const cats = ['womens', 'mens', 'kids', 'shoes', 'acc.', 'beauty', 'home', 'night'];
    const mx = 4806;
    cats.forEach((c, j) => text(c, 128 + j * 33.5, 258, { size: 8.5, font: 'body', align: 'center', color: PAL.inkSoft, prog: lk, jit: 0.2 }));
    HEAT.stores.forEach((s, r) => {
      text(s, 108, 280 + r * 22, { size: 10, font: 'body', align: 'right', prog: lk, jit: 0.2 });
      HEAT.grid[r].forEach((v, j) => {
        const ck = ez(t, CUE.where + (r + j) * 0.045, 0.3);
        if (ck <= 0) return;
        const q = Math.sqrt(v / mx);
        fillPoly(rrPts(113 + j * 33.5, 266 + r * 22, 30, 19, 3, 0), q > 0.55 ? PAL.coral : q > 0.3 ? PAL.coralL : PAL.mustL, { alpha: (0.25 + 0.75 * q) * ck, seed: r * 9 + j, edge: false, rough: 1, grain: false });
      });
    });
    text('value at risk, top 8 stores', 28, 448, { size: 9, font: 'body', color: PAL.inkSoft, prog: lk, jit: 0.2 });
  }
  if (rk > 0) {
    stroke(rrPts(414, 210, 400, 248, 10, 6), { w: 2.4, prog: rk });
    text('Work these first', 428, 236, { size: 16, font: 'body', weight: 700, prog: rk, jit: 0.4 });
    TOP5.forEach((a, i) => {
      const ik = ez(t, CUE.first + 0.1 + i * 0.16, 0.35);
      if (ik <= 0) return;
      const y = 248 + i * 42;
      push(0, (1 - ik) * 8); alpha(ik);
      if (i) stroke([[428, y], [800, y]], { w: 1.2, color: PAL.greyL, double: false });
      text(a[0], 428, y + 17, { size: 11.5, font: 'body', weight: 700, jit: 0.3 });
      text(a[1], 428, y + 33, { size: 8.5, font: 'body', color: PAL.inkSoft, jit: 0.2 });
      const sev = a[4] === 'critical' ? PAL.coral : PAL.mustard;
      const cw = textW(a[4], 9, 'body', 700) + 12;
      fillPoly(rrPts(800 - cw, y + 7, cw, 15, 7, 0), sev, { alpha: 0.85, edge: false, grain: false, seed: i });
      text(a[4], 800 - cw / 2, y + 18, { size: 9, font: 'body', weight: 700, align: 'center', color: PAL.white, jit: 0.2 });
      text(a[3], 800 - cw - 8, y + 19, { size: 12, font: 'body', weight: 700, align: 'right', jit: 0.2 });
      const tw = textW(a[2], 8.5, 'body', 700) + 12;
      fillPoly(rrPts(800 - tw, y + 25, tw, 13, 6, 0), PAL.lavL, { alpha: 0.9, edge: false, grain: false, seed: i + 20 });
      text(a[2], 800 - tw / 2, y + 35, { size: 8.5, font: 'body', weight: 700, align: 'center', color: PAL.ink, jit: 0.2 });
      pop();
    });
  }
  text('Model in use: Isolation Forest. Figures are estimates on demo vendor data.', 16, 472, { size: 8.5, font: 'body', color: PAL.inkSoft, prog: lk, jit: 0.2 });

  /* ---- marker annotations over the screen (the "whimsical" layer) ---- */
  const M = { w: 3.5, color: PAL.coral };
  heroes.forEach((h, i) => {
    const k = popIn(t, CUE.three + 0.15 + i * 0.3, 0.4);
    if (k <= 0) return;
    push(14 + i * 272 + 236, 100, k, 0.1);
    fillSolid(ellPts(0, 0, 17, 17), PAL.white, { still: true });
    stroke(ellPts(0, 0, 17, 17), { ...M, w: 3, seed: i });
    text(String(i + 1), 0, 8, { size: 24, font: 'brush', align: 'center', color: PAL.coral });
    pop();
  });
  // underline the money
  stroke(curvePts(24, 167, 120, 166, 0.03), { ...M, prog: ez(t, CUE.varisk + 0.9, 0.35), double: false });
  // hotspot callout on Kingston menswear
  const hx = 113 + 1 * 33.5 + 15, hy = 266 + 0 * 22 + 9;
  circleIt(hx, hy, 24, 17, { ...M, w: 3, prog: ez(t, CUE.where + 0.7, 0.4) });
  text('hotspot!', hx + 64, hy - 22, { size: 24, font: 'hand', weight: 700, color: PAL.coral, prog: ez(t, CUE.where + 0.9, 0.4, E.lin) });
  // "start here" pointing at the planner's first pick
  text('start here', 800, 234, { size: 24, font: 'hand', weight: 700, align: 'right', color: PAL.coral, prog: ez(t, CUE.first + 0.9, 0.4, E.lin) });
  arrow(690, 236, 640, 262, { ...M, w: 3, prog: ez(t, CUE.first + 1.1, 0.35), head: 10, bend: 0.3 });
  // no statistics degree required: a sticky note slapped on the screen
  const gk = popIn(t, CUE.nostats, 0.5);
  if (gk > 0) {
    push(700, 388, gk, -0.06);
    fillSolid(rrPts(-108, -60, 222, 130, 4, 0), 'rgba(60,40,20,0.2)', { still: true });
    fillSolid(rrPts(-114, -66, 222, 130, 4, 0), '#fbe39a', { still: true });
    stroke(rrPts(-114, -66, 222, 130, 4, 0), { w: 1.6, color: PAL.brown, alpha: 0.5, double: false });
    push(-56, 0, 0.55); gradCap(0, -6, 1, 0.1); pop();
    cross(-56, 0, 1.6, { prog: ez(t, CUE.nostats + 0.45, 0.35) });
    text('no stats', 42, -18, { size: 23, font: 'hand', weight: 700, align: 'center', prog: ez(t, CUE.nostats + 0.5, 0.35, E.lin) });
    text('degree', 42, 6, { size: 23, font: 'hand', weight: 700, align: 'center', prog: ez(t, CUE.nostats + 0.75, 0.3, E.lin) });
    text('needed :)', 42, 32, { size: 23, font: 'hand', weight: 700, align: 'center', color: PAL.coral, prog: ez(t, CUE.nostats + 1.0, 0.35, E.lin) });
    pop();
  }
  /* ---- the assistant chat dock ---- */
  const ck = ez(t, CUE.question - 0.15, 0.5, E.out);
  if (ck > 0) {
    push((1 - ck) * 380, 0);
    const px = 486, py = 46, pw = 330, ph = 424;
    fillSolid(rrPts(px + 5, py + 7, pw, ph, 14, 0), 'rgba(40,30,20,0.18)', { still: true });
    fillSolid(rrPts(px, py, pw, ph, 14, 0), PAL.white, { still: true });
    stroke(rrPts(px, py, pw, ph, 14, 8), { w: 2.6 });
    fillPoly(rrPts(px, py, pw, 40, 14, 0), PAL.teal, { alpha: 0.9, edge: false, seed: 70 });
    text('Assistant', px + 40, py + 27, { size: 17, font: 'body', weight: 700, color: PAL.white, jit: 0.3 });
    fillSolid(ellPts(px + 22, py + 20, 9, 9), PAL.white, { still: true });
    text('Hi! Ask me anything about your stock.', px + 18, py + 74, { size: 11.5, font: 'body', color: PAL.inkSoft, jit: 0.3 });
    const q1 = 'Which stores lose most in footwear,', q2 = 'and what would 120 investigator', q3 = 'hours buy us?';
    const full = q1 + q2 + q3;
    const n = Math.floor(ez(t, CUE.question + 0.15, CUE.ask - CUE.question - 0.3, E.lin) * full.length);
    const sent = t > CUE.ask + 0.2;
    const lines = [q1, q2, q3];
    if (!sent) {
      fillSolid(rrPts(px + 12, py + ph - 92, pw - 24, 80, 10, 0), PAL.sky, { alpha: 0.5, still: true });
      stroke(rrPts(px + 12, py + ph - 92, pw - 24, 80, 10, 6), { w: 1.8, double: false });
      let left = n;
      lines.forEach((l, i) => { const m = Math.max(0, Math.min(l.length, left)); left -= l.length; text(l.slice(0, m), px + 22, py + ph - 68 + i * 20, { size: 13, font: 'body', jit: 0.25 }); });
      const press = ez(t, CUE.ask, 0.08) * (1 - ez(t, CUE.ask + 0.12, 0.1));
      fillSolid(ellPts(px + pw - 36, py + ph - 30, 16 - press * 3, 16 - press * 3), PAL.teal, { still: true });
      arrow(px + pw - 44, py + ph - 30, px + pw - 28, py + ph - 30, { w: 2.5, color: PAL.white, head: 7, bend: 0 });
    } else {
      const fly = ez(t, CUE.ask + 0.2, 0.4, E.back);
      const by = lerp(py + ph - 92, py + 100, fly);
      fillPoly(rrPts(px + 40, by, pw - 52, 78, 14, 0), PAL.tealL, { alpha: 0.9, edge: false, seed: 71 });
      lines.forEach((l, i) => text(l, px + 52, by + 24 + i * 20, { size: 13, font: 'body', jit: 0.25 }));
      // thinking dots
      for (let i = 0; i < 3; i++) { const b = Math.sin(t * 9 - i * 0.8) * 3; fillSolid(ellPts(px + 30 + i * 16, py + 214 + b, 4.5, 4.5), PAL.inkSoft, { alpha: fly, still: true }); }
    }
    pop();
  }
  S.ls = ls0;
}
function sceneF(t) {
  text('for leadership', 0, -400, { size: 104, font: 'brush', align: 'center', prog: ez(t, CUE.lead, 0.9, E.lin) });
  text('it all lands on one screen', 0, -322, { size: 52, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.lead + 1.3, 1.0, E.lin) });
  const lk = ez(t, CUE.lead - 0.3, 0.8);
  if (lk > 0) { push(0, 0); alpha(lk); laptop(0, LAP_Y, 1); pop(); }
  push(SCR.x, SCR.y); dashboard(t); pop();
  person(-740, 470, 1.45, { shirt: '#5b5f86', tie: true, mug: true, skin: 1, hair: PAL.ink, armR: 0.9, look: 0.8, prog: ez(t, CUE.lead - 0.2, 0.5) });
  const ok = popIn(t, CUE.lead + 0.7, 0.45);
  if (ok > 0) owl(340, LAP_Y - 540 + 6, 0.5 * ok, { look: [-0.8, 0.6], blinkSeed: 1 });
}

/* ===================== G: a team of AI agents ===================== */
const AGENTS = [
  { name: 'front door', x: -700, y: 300, s: 1.3, col: PAL.teal, hat: null },
  { name: 'alert investigator', x: -200, y: 300, s: 1.3, col: PAL.coral, hat: 'detective' },
  { name: 'loss-prevention planner', x: 300, y: 300, s: 1.3, col: PAL.mustard, hat: 'cap' },
  { name: '', x: 660, y: 40, s: 0.75, col: PAL.sage },
  { name: '', x: 850, y: 40, s: 0.75, col: PAL.lav },
  { name: '', x: 660, y: 290, s: 0.75, col: PAL.sky },
  { name: '', x: 850, y: 290, s: 0.75, col: PAL.pink },
];
function bubble(x, y, w, h, o = {}) {
  fillSolid(rrPts(x + 6, y + 8, w, h, 26, 0), 'rgba(40,30,20,0.13)', { still: true });
  fillSolid(rrPts(x, y, w, h, 26, 0), o.bg || PAL.white, { still: true });
  if (o.tint) fillPoly(rrPts(x, y, w, h, 26, 0), o.tint, { alpha: 0.45, edge: false, seed: o.seed || 1 });
  stroke(rrPts(x, y, w, h, 26, 12), { w: 3 });
}
function sceneG(t) {
  // the question arrives
  const qk = ez(t, CUE.team - 0.4, 0.5, E.back);
  const split = ez(t, CUE.splits, 0.8, E.inOut);
  const answer = t > CUE.never - 0.1;
  if (qk > 0 && split < 1) {
    push(0, -400 + (1 - qk) * -200, 1 - split * 0.4); alpha(1 - split);
    bubble(-560, -70, 1120, 140, { tint: PAL.tealL });
    text('Which stores lose most in footwear,', 0, -14, { size: 46, font: 'body', align: 'center', jit: 0.5 });
    text('and what would 120 investigator hours buy us?', 0, 44, { size: 46, font: 'body', align: 'center', jit: 0.5 });
    pop();
  }
  // agents pop in
  AGENTS.forEach((a, i) => {
    const t0 = CUE.team + i * 0.16;
    bot(a.x, a.y, a.s, { prog: ez(t, t0, 0.45), color: a.col, hat: a.hat, seed: i, light: a.col, look: i === 0 ? 1 : 0 });
    if (a.name) text(a.name, a.x, a.y + 76, { size: 40, font: 'hand', weight: 700, align: 'center', prog: ez(t, t0 + 0.2, 0.5, E.lin) });
  });
  text('+ 4 more specialists', 755, 380, { size: 36, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.team + 1.2, 0.6, E.lin) });
  // split pieces fly to the specialists
  if (split > 0 && !answer) {
    [['where in footwear?', -200, PAL.coralL], ['what do 120 hours buy?', 300, PAL.mustL]].forEach(([s, tx, col], i) => {
      const k = ez(t, CUE.splits + 0.1 + i * 0.15, 0.7, E.inOut);
      const x = lerp(0, tx, k), y = lerp(-400, -300, k);
      const w = textW(s, 36, 'hand', 700) + 50;
      push(x, y, 0.6 + 0.4 * k);
      bubble(-w / 2, -40, w, 80, { tint: col, seed: i + 3 });
      text(s, 0, 12, { size: 36, font: 'hand', weight: 700, align: 'center' });
      pop();
    });
    arrow(-620, 90, -290, 110, { w: 3.5, prog: ez(t, CUE.splits, 0.4), bend: -0.2 });
    arrow(-620, 60, 200, 110, { w: 3.5, prog: ez(t, CUE.splits + 0.2, 0.5), bend: -0.25 });
  }
  // tool calls
  const chips = [
    ['hotspots()', -200, -150, CUE.digs + 0.25, PAL.coralL],
    ['list_alerts()', -200, -80, CUE.digs + 0.75, PAL.coralL],
    ['investigation_plan(120 h)', 300, -150, CUE.plans + 0.3, PAL.mustL],
    ['compare_plans()', 300, -80, CUE.plans + 0.8, PAL.mustL],
  ];
  chips.forEach(([s, x, y, t0, col], i) => {
    const k = popIn(t, t0, 0.4) * (answer ? 1 - seg(t, CUE.never, CUE.never + 0.3) : 1);
    if (k <= 0) return;
    push(x, y, k);
    const w = textW(s, 30, 'body', 700) + 36;
    fillPoly(rrPts(-w / 2, -26, w, 52, 12, 0), col, { seed: i + 9 });
    stroke(rrPts(-w / 2, -26, w, 52, 12, 8), { w: 2.6 });
    text(s, 0, 10, { size: 30, font: 'body', weight: 700, align: 'center', jit: 0.4 });
    pop();
  });
  if (t > CUE.digs) magnifier(-90, 130 + Math.sin(t * 5) * 6, 0.95, { rot: -0.4 });
  if (t > CUE.plans) {
    push(415, 120, popIn(t, CUE.plans, 0.4));
    fillPoly(ellPts(0, 0, 38, 38), PAL.white, { seed: 3 });
    stroke(ellPts(0, 0, 38, 38), { w: 3.5 });
    stroke([[0, 0], [0, -26]], { w: 3.5 });
    stroke([[0, 0], [Math.cos(t * 4) * 20, Math.sin(t * 4) * 20]], { w: 3 });
    pop();
  }
  // live data
  const dk = ez(t, CUE.live - 0.2, 0.5);
  if (dk > 0) {
    push(50, 470, dk);
    cylinder(0, 0, 0.85, { label: 'live data' });
    pop();
    [[-200, -50], [300, -50]].forEach(([x, y], i) => {
      const line = curvePts(x + (i ? 140 : -150), y, 50, 352, i ? -0.25 : 0.25);
      stroke(line, { w: 3, dash: [10, 12], color: PAL.sage, prog: dk });
      for (let j = 0; j < 4; j++) {
        const u = ((((t - CUE.live) * 0.9 + j / 4) % 1) + 1) % 1;
        const p = line[Math.floor((1 - u) * (line.length - 1))];
        if (!answer) fillSolid(ellPts(p[0], p[1], 8, 8), PAL.sage, { alpha: dk, still: true });
      }
    });
  }
  // the answer
  if (answer) {
    const ak = ez(t, CUE.never - 0.1, 0.5, E.back);
    push(-90, -390 + (1 - ak) * -160, 1);
    bubble(-700, -110, 1260, 200, { tint: PAL.sageL, seed: 7 });
    text('Leeds and Birmingham 2 lose most in footwear (about £1.9k each).', -680, -40, { size: 40, font: 'body', jit: 0.5, prog: ez(t, CUE.never, 0.9, E.lin) });
    text('120 hours covers 99 alerts: about £19k back, 5x the cost.', -680, 18, { size: 40, font: 'body', jit: 0.5, prog: ez(t, CUE.never + 0.7, 0.9, E.lin) });
    text('✓ every number from a tool call', -680, 72, { size: 32, font: 'hand', weight: 700, color: PAL.sage, prog: ez(t, CUE.never + 1.5, 0.7, E.lin) });
    pop();
    const fk = popIn(t, CUE.never + 0.4, 0.4);
    if (fk > 0) {
      push(720, -400, fk, 0.08);
      card(-110, -60, 220, 120, { tint: PAL.mustL, tintA: 0.6 });
      text('£???', 0, 26, { size: 70, font: 'brush', align: 'center' });
      cross(0, 0, 3, { prog: ez(t, CUE.never + 1.0, 0.4) });
      pop();
      text('never invented', 720, -300, { size: 38, font: 'hand', weight: 700, align: 'center', color: PAL.coral, prog: ez(t, CUE.never + 1.3, 0.6, E.lin) });
    }
  }
  // proposal: nothing changes without a yes
  const pk = popIn(t, CUE.change - 0.1, 0.5);
  if (pk > 0) {
    push(-40, 120, pk * 1.12, -0.01);
    card(-430, -150, 860, 300, { tint: PAL.white, w: 3.5 });
    fillPoly(rrPts(-400, -124, 170, 40, 20, 0), PAL.lavL, { seed: 5, edge: false });
    text('PROPOSAL', -315, -95, { size: 26, font: 'body', weight: 700, align: 'center' });
    text('Raise a vendor task: recount Printed Trainers', -400, -24, { size: 38, font: 'body', weight: 700, jit: 0.5 });
    text('at Store 032 · Canterbury', -400, 24, { size: 38, font: 'body', weight: 700, jit: 0.5 });
    text('Nothing happens until you confirm.', -400, 70, { size: 28, font: 'body', color: PAL.inkSoft, jit: 0.4 });
    const yes = t > CUE.yes + 0.75;
    const press = ez(t, CUE.yes + 0.65, 0.08) * (1 - ez(t, CUE.yes + 0.8, 0.12));
    push(250, 100, 1 - press * 0.08);
    fillPoly(rrPts(-110, -32, 220, 64, 32, 0), PAL.sage, { seed: 6 });
    stroke(rrPts(-110, -32, 220, 64, 32, 10), { w: 3 });
    text('Confirm', 0, 12, { size: 34, font: 'body', weight: 700, align: 'center', color: PAL.white });
    pop();
    stroke(rrPts(-40, 70, 150, 60, 30, 10), { w: 2.5, color: PAL.inkSoft });
    text('Not now', 35, 112, { size: 28, font: 'body', align: 'center', color: PAL.inkSoft });
    const hk = ez(t, CUE.change + 0.5, CUE.yes + 0.6 - CUE.change - 0.5, E.inOut);
    if (hk > 0) hand(lerp(520, 262, hk), lerp(330, 104, hk) + press * 10, 1.1, { rot: -0.25 });
    if (yes) {
      const sk2 = ez(t, CUE.yes + 0.78, 0.2);
      push(300, -150, 1.7 - 0.7 * sk2, 0.1); alpha(sk2);
      stroke(rrPts(-150, -50, 300, 92, 12, 8), { w: 6, color: PAL.sage, rough: 2.5 });
      text('APPROVED ✓', 0, 18, { size: 54, font: 'brush', align: 'center', color: PAL.sage });
      pop();
    }
    pop();
  }
}

/* ===================== H: it learns from every closed alert ===================== */
function loopPt(u) {
  const a = Math.PI * (1 - u) + 0.15;
  return [Math.cos(a) * 620, 160 - Math.sin(a) * 440];
}
function sceneH(t) {
  const lk = ez(t, CUE.close - 0.4, 0.9);
  const loop = []; for (let i = 0; i <= 40; i++) loop.push(loopPt(i / 40 * 0.92));
  stroke(loop, { w: 4, dash: [14, 14], prog: lk, color: PAL.tealD });
  if (lk > 0.95) arrow(loop[38][0], loop[38][1], loop[40][0] + 6, loop[40][1] + 30, { w: 4, color: PAL.tealD, bend: 0 });
  text('teams close alerts', -700, -120, { size: 48, font: 'hand', weight: 700, align: 'center', prog: ez(t, CUE.close + 0.2, 0.7, E.lin) });
  text('the model learns', 700, -120, { size: 48, font: 'hand', weight: 700, align: 'center', prog: ez(t, CUE.close + 1.4, 0.7, E.lin) });
  person(-760, 478, 0.95, { hat: 'hard', vest: true, shirt: PAL.coral, skin: 2, armR: 2.2, look: 0.5, prog: ez(t, CUE.close - 0.4, 0.4) });
  person(-600, 478, 0.95, { hat: 'hard', vest: true, shirt: PAL.teal, skin: 0, armL: 2.0, look: 0.3, flip: true, prog: ez(t, CUE.close - 0.3, 0.4) });
  const sm = t > CUE.smarter;
  owl(0, 470, 1.15, { glasses: ez(t, CUE.smarter, 0.5, E.back), look: sm ? [0, 0.2] : [-0.6, -0.5], brow: sm ? 1 : 0, prog: ez(t, CUE.close - 0.6, 0.8) });
  sparkle(0, 100, 2, CUE.smarter + 0.35, t);
  const cards = [['confirmed theft', PAL.coralL], ['counting error', PAL.mustL], ['false alarm', PAL.greyL]];
  cards.forEach(([s, col], i) => {
    const t0 = CUE.close + 0.1 + i * 0.5, dur = 1.6;
    const u = seg(t, t0, t0 + dur);
    if (u <= 0 || u >= 1) return;
    let [x, y] = loopPt(u * 0.92);
    const intoOwl = seg(u, 0.85, 1);
    x = lerp(x, 0, intoOwl); y = lerp(y, 250, intoOwl);
    push(x, y, 1 - intoOwl * 0.8, Math.sin(u * 6) * 0.08);
    const w = textW(s, 34, 'hand', 700) + 60;
    card(-w / 2, -32, w, 64, { tint: col, tintA: 0.7, shadow: false });
    check(-w / 2 + 26, 0, 0.7);
    text(s, 14, 12, { size: 34, font: 'hand', weight: 700, align: 'center' });
    pop();
  });
  text('a little smarter', 430, 180, { size: 64, font: 'brush', color: PAL.tealD, prog: ez(t, CUE.smarter + 0.2, 0.7, E.lin) });
  text('P(true) recalibrated  ·  re-ranker retrained', 430, 240, { size: 30, font: 'hand', weight: 700, color: PAL.inkSoft, prog: ez(t, CUE.smarter + 0.6, 0.9, E.lin) });
}

/* ===================== I: finale (screen space) ===================== */
function finale(t) {
  const k = ez(t, CUE.s9 - 0.55, 0.6, E.out);
  if (k <= 0) return;
  const c = S.ctx;
  const y0 = (1 - k) * (H + 80);
  // a fresh sheet slides up over the story
  c.save();
  c.translate(0, y0);
  c.fillStyle = 'rgba(60,40,20,0.25)'; c.fillRect(0, -18, W, 18);
  c.fillStyle = _paperPat; c.fillRect(0, 0, W, H + 100);
  c.restore();
  push(0, y0);
  const ok = popIn(t, CUE.logo - 0.2, 0.55);
  if (ok > 0) {
    const wink = seg(t, CUE.before + 1.4, CUE.before + 1.6) * (1 - seg(t, CUE.before + 2.0, CUE.before + 2.2));
    owl(455, 700, 1.22 * ok, { look: t > CUE.before ? [0.7, -0.2] : [0.8, -0.4], wink: wink > 0 ? 1 : 0, brow: t > CUE.before + 1.3 ? 1 : 0, wingR: t > CUE.before + 1.3 ? ez(t, CUE.before + 1.3, 0.3) * 0.7 : 0, blinkSeed: 4 });
    sparkle(560, 340, 1.5, CUE.before + 1.45, t);
  }
  text('Inventory Sentinel', 1150, 420, { size: 156, font: 'brush', align: 'center', prog: ez(t, CUE.logo, 1.3, E.lin) });
  stroke(curvePts(660, 460, 1640, 452, -0.02), { w: 8, color: PAL.coral, prog: ez(t, CUE.logo + 1.25, 0.45), double: false });
  text('finds stock going missing, and tells you what to do first', 1150, 530, { size: 44, font: 'hand', weight: 700, align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.logo + 1.4, 1.2, E.lin) });
  const icons = [
    [CUE.plugin, 'Plug it in.', 820],
    [CUE.learn, 'Let it learn.', 1150],
    [CUE.find, 'Find the loss…', 1480],
  ];
  icons.forEach(([c0, s, x], i) => {
    const kk = popIn(t, c0 - 0.1, 0.5);
    if (kk <= 0) return;
    push(x, 680, kk);
    fillPoly(ellPts(0, 0, 70, 70), [PAL.mustL, PAL.sageL, PAL.tealL][i], { seed: i + 1 });
    stroke(ellPts(0, 0, 70, 70), { w: 3.5, seed: i + 4 });
    if (i === 0) { push(0, 26, 0.55); plug(0, 0, 1, { color: PAL.mustard }); pop(); }
    if (i === 1) { const r = rng(5); for (let j = 0; j < 16; j++) { const a = r() * 6.28, d = r() * 32; fillSolid(ellPts(Math.cos(a) * d * 1.3, Math.sin(a) * d * 0.8, 5, 5), PAL.ink, { still: true, alpha: 0.8 }); } fillSolid(ellPts(42, -36, 7, 7), PAL.coral, { still: true }); }
    if (i === 2) magnifier(-10, -10, 0.75, { rot: 0 });
    pop();
    text(s, x, 800, { size: 54, font: 'hand', weight: 700, align: 'center', prog: ez(t, c0, 0.5, E.lin) });
  });
  text('…before it’s lost.', 1150, 930, { size: 96, font: 'brush', align: 'center', color: PAL.coral, prog: ez(t, CUE.before, 0.9, E.lin) });
  text('MCP connectors  ·  unsupervised detection  ·  an AI agent team', 1150, 1030, { size: 32, font: 'body', align: 'center', color: PAL.inkSoft, prog: ez(t, CUE.before + 1.6, 1.0, E.lin), jit: 0.4 });
  pop();
}
