/* Characters and props, drawn from SVG-ish paths with the hand-drawn engine. Origins are at the feet / base. */
'use strict';

/* ---------- Sentinel the owl ---------- */
const OWL = {
  body: 'M0,-255 C72,-255 114,-200 114,-120 C114,-44 66,0 0,0 C-66,0 -114,-44 -114,-120 C-114,-200 -72,-255 0,-255 Z',
  tuftL: 'M-58,-236 L-92,-292 L-24,-252 Z',
  tuftR: 'M58,-236 L92,-292 L24,-252 Z',
  wing: 'M0,0 C-44,26 -48,98 -10,134 C-6,92 4,44 0,0 Z',
  beak: 'M-14,-146 Q0,-154 14,-146 L0,-114 Z',
};
function owl(x, y, s, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0) return;
  const t = S.t;
  const look = o.look || [Math.sin(t * 0.7) * 0.25, 0.05];
  const breathe = o.still ? 0 : Math.sin(t * 2.4) * 0.012;
  const sq = (o.squash || 0) + breathe;
  push(x, y, s);
  S.ctx.scale(1 + sq * 0.6, 1 - sq);
  if (o.rot) S.ctx.rotate(o.rot);
  const pO = E.out(seg(prog, 0, 0.45)), pF = seg(prog, 0.3, 0.8), pD = seg(prog, 0.45, 1);
  // shadow
  if (o.shadow !== false) fillSolid(ellPts(0, 4, 95, 14), 'rgba(60,40,20,0.12)', { alpha: pF, still: true });
  // wings behind
  const wl = o.wingL || 0, wr = o.wingR || 0;
  push(-104, -150, 1, wl); fillPoly(parsePath(OWL.wing)[0], PAL.tealD, { alpha: pF, seed: 11 }); path(OWL.wing, { w: 3.2, prog: pD }); pop();
  push(104, -150, 1, -wr); S.ctx.scale(-1, 1); fillPoly(parsePath(OWL.wing)[0], PAL.tealD, { alpha: pF, seed: 12 }); path(OWL.wing, { w: 3.2, prog: pD }); pop();
  // body + tufts
  fillPoly(parsePath(OWL.tuftL)[0], PAL.teal, { alpha: pF, seed: 3 });
  fillPoly(parsePath(OWL.tuftR)[0], PAL.teal, { alpha: pF, seed: 4 });
  fillPoly(parsePath(OWL.body)[0], PAL.teal, { alpha: pF, seed: 5 });
  path(OWL.body, { w: 4, prog: pO });
  path(OWL.tuftL, { w: 3.5, prog: pO });
  path(OWL.tuftR, { w: 3.5, prog: pO });
  // belly + feathers
  fillPoly(ellPts(0, -66, 68, 58), PAL.cream, { alpha: pF, seed: 6, off: [2, 2] });
  for (let row = 0; row < 3; row++) {
    const yy = -98 + row * 24, n = row === 1 ? 4 : 3;
    for (let i = 0; i < n; i++) {
      const xx = (i - (n - 1) / 2) * 30;
      stroke(ellPts(xx, yy, 11, 8, 0.15, 0, Math.PI * 0.75), { w: 2.4, color: PAL.tealD, prog: pD, double: false, seed: row * 10 + i });
    }
  }
  // facial disc + eyes
  for (const sx of [-1, 1]) fillPoly(ellPts(sx * 44, -172, 54, 52), PAL.tealL, { alpha: pF, seed: 20 + sx, off: [1, 1] });
  const blink = o.blink !== undefined ? o.blink : owlBlink(t, o.blinkSeed || 0);
  for (const sx of [-1, 1]) {
    const ex = sx * 44, ey = -172;
    fillSolid(ellPts(ex, ey, 38, 38), PAL.white, { alpha: pF, still: true });
    let bk = blink;
    if (o.wink && sx === 1) bk = Math.max(bk, o.wink);
    if (pD > 0) {
      const px = ex + look[0] * 14, py = ey + look[1] * 12;
      if (bk < 0.95) {
        fillSolid(ellPts(px, py, 17, 17), PAL.ink, { alpha: pD, still: true });
        fillSolid(ellPts(px - 6, py - 6, 5.5, 5.5), PAL.white, { alpha: pD, still: true });
      }
      if (bk > 0) {
        const c = S.ctx; c.save(); c.beginPath(); c.arc(ex, ey, 39, 0, 6.3); c.clip();
        c.fillStyle = PAL.teal; c.fillRect(ex - 40, ey - 40, 80, 80 * bk);
        c.restore();
        stroke([[ex - 36, ey - 38 + 76 * bk], [ex + 36, ey - 38 + 76 * bk]], { w: 3, prog: pD, double: false, seed: sx + 40 });
      }
    }
    stroke(ellPts(ex, ey, 38, 38), { w: 3.5, prog: pO, seed: 50 + sx });
    // brows
    const br = o.brow || 0;
    stroke([[ex - sx * 18, ey - 50 + br * 2], [ex + sx * 24, ey - 54 - br * 8]], { w: 3.5, prog: pD, double: false, seed: 60 + sx });
  }
  // beak
  fillPoly(parsePath(OWL.beak)[0], PAL.orange, { alpha: pF, seed: 7, off: [1, 1] });
  path(OWL.beak, { w: 3, prog: pD });
  // feet
  for (const fx of [-34, 34]) for (const d of [-11, 0, 11]) stroke([[fx + d * 0.6, -6], [fx + d * 1.3, 8]], { w: 6, color: PAL.orange, prog: pD, double: false, seed: fx + d });
  // glasses
  if (o.glasses) {
    const g = o.glasses;
    push(0, -172 - (1 - g) * 120, 1); alpha(clamp(g * 2));
    for (const sx of [-1, 1]) stroke(ellPts(sx * 44, 0, 46, 44), { w: 5, color: PAL.ink, seed: 70 + sx });
    stroke([[-6, -6], [6, -6]], { w: 5, seed: 73 });
    pop();
  }
  pop();
}
function owlBlink(t, seed) {
  const period = 3.7 + (seed % 3) * 0.4, ph = (t + seed * 1.3) % period;
  return ph < 0.16 ? Math.sin((ph / 0.16) * Math.PI) : 0;
}

/* ---------- raccoon (the cartoon "theft") ---------- */
function raccoon(x, y, s, o = {}) {
  const t = S.t, ph = o.phase || 0, step = Math.sin(ph * Math.PI * 2);
  push(x, y, s);
  if (o.flip) S.ctx.scale(-1, 1);
  const bob = Math.abs(step) * -6;
  // legs (tiptoe)
  stroke([[-14, -24 + bob], [-20 + step * 12, -2], [-12 + step * 12, 0]], { w: 5, seed: 1 });
  stroke([[18, -24 + bob], [22 - step * 12, -2], [30 - step * 12, 0]], { w: 5, seed: 2 });
  push(0, bob);
  // tail
  const tail = curvePts(-42, -44, -104, -112, -0.35);
  stroke(tail, { w: 26, color: PAL.grey, double: false, rough: 1, seed: 3 });
  for (let i = 3; i < tail.length - 1; i += 4) {
    const a = tail[i], b = tail[i + 1], ang = Math.atan2(b[1] - a[1], b[0] - a[0]) + Math.PI / 2;
    stroke([[a[0] - Math.cos(ang) * 11, a[1] - Math.sin(ang) * 11], [a[0] + Math.cos(ang) * 11, a[1] + Math.sin(ang) * 11]], { w: 5, double: false, seed: i });
  }
  stroke(tail, { w: 2.5, alpha: 0.5, seed: 4 });
  // sack
  fillPoly(ellPts(-46, -142, 40, 38), PAL.brownL, { seed: 5 });
  stroke(ellPts(-46, -142, 40, 38), { w: 3.2, seed: 6 });
  stroke([[-18, -112], [-4, -104]], { w: 3.5, seed: 7 });
  text('\u00a3', -48, -128, { size: 42, font: 'body', weight: 700, align: 'center', color: PAL.brown });
  // body
  const body = 'M-44,-34 C-52,-92 -10,-118 26,-108 C62,-98 62,-44 46,-24 C30,-6 -36,-6 -44,-34 Z';
  fillPoly(parsePath(body)[0], PAL.grey, { seed: 8 });
  path(body, { w: 3.5 });
  fillPoly(ellPts(14, -56, 22, 26), PAL.greyL, { seed: 9, edge: false });
  // arm holding sack
  stroke([[22, -96], [0, -118], [-16, -112]], { w: 5, seed: 10 });
  // head
  fillPoly(ellPts(42, -128, 36, 32), PAL.grey, { seed: 11 });
  fillPoly(parsePath('M18,-150 L22,-176 L40,-158 Z')[0], PAL.grey, { seed: 12 });
  fillPoly(parsePath('M52,-158 L68,-176 L72,-148 Z')[0], PAL.grey, { seed: 13 });
  path('M18,-150 L22,-176 L40,-158', { w: 3 });
  path('M52,-158 L68,-176 L72,-148', { w: 3 });
  stroke(ellPts(42, -128, 36, 32), { w: 3.5, seed: 14 });
  fillPoly(parsePath('M66,-138 L98,-124 L68,-110 Z')[0], PAL.greyL, { seed: 15 });
  path('M66,-138 L98,-124 L68,-110', { w: 3 });
  fillSolid(ellPts(98, -124, 6, 5), PAL.ink, { still: true });
  // bandit mask
  fillSolid(parsePath('M14,-136 C30,-146 70,-146 80,-134 C70,-120 30,-120 14,-136 Z')[0], PAL.ink, { alpha: 0.92 });
  fillSolid(ellPts(36, -134, 5, 5), PAL.white, { still: true });
  fillSolid(ellPts(62, -134, 5, 5), PAL.white, { still: true });
  pop();
  pop();
}

/* ---------- bean people ---------- */
const SKIN = ['#f1c8a3', '#d39a6f', '#a8694a', '#f5d4b8', '#7a4a33'];
function person(x, y, s, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0) return;
  push(x, y, s);
  alpha(Math.min(1, prog * 1.5));
  if (o.flip) S.ctx.scale(-1, 1);
  const walk = o.walk || 0, sw = Math.sin(walk * Math.PI * 2);
  const bob = o.walk !== undefined ? -Math.abs(sw) * 5 : 0;
  const shirt = o.shirt || PAL.sage, skin = SKIN[(o.skin || 0) % SKIN.length];
  fillSolid(ellPts(0, 3, 34, 7), 'rgba(60,40,20,0.12)', { still: true });
  // legs
  stroke([[-10, -52 + bob], [-12 + sw * 12, 0]], { w: 7, color: o.pants || PAL.ink, seed: 1 });
  stroke([[10, -52 + bob], [12 - sw * 12, 0]], { w: 7, color: o.pants || PAL.ink, seed: 2 });
  push(0, bob);
  // arms
  const aL = o.armL === undefined ? 0.25 + sw * 0.3 : o.armL, aR = o.armR === undefined ? 0.25 - sw * 0.3 : o.armR;
  const shL = [-26, -118], shR = [26, -118];
  const hL = [shL[0] - Math.sin(aL) * 56, shL[1] + Math.cos(aL) * 56], hR = [shR[0] + Math.sin(aR) * 56, shR[1] + Math.cos(aR) * 56];
  stroke([shL, hL], { w: 7, color: shirt, double: false, seed: 3 });
  stroke([shR, hR], { w: 7, color: shirt, double: false, seed: 4 });
  stroke([shL, hL], { w: 2.5, alpha: 0.7, seed: 5 });
  stroke([shR, hR], { w: 2.5, alpha: 0.7, seed: 6 });
  fillSolid(ellPts(hL[0], hL[1], 7, 7), skin, { still: true });
  fillSolid(ellPts(hR[0], hR[1], 7, 7), skin, { still: true });
  // body
  const body = rrPts(-30, -132, 60, 84, 24, 6);
  fillPoly(body, shirt, { seed: 7 });
  stroke(body, { w: 3.2, seed: 8 });
  if (o.tie) { fillPoly(parsePath('M-6,-130 L6,-130 L4,-96 L0,-88 L-4,-96 Z')[0], PAL.coral, { seed: 9, edge: false }); }
  if (o.vest) { stroke([[-22, -126], [-22, -60]], { w: 4, color: PAL.mustard, double: false }); stroke([[22, -126], [22, -60]], { w: 4, color: PAL.mustard, double: false }); }
  // head
  fillPoly(ellPts(0, -160, 27, 28), skin, { seed: 10 });
  stroke(ellPts(0, -160, 27, 28), { w: 3, seed: 11 });
  const lk = o.look || 0;
  fillSolid(ellPts(-9 + lk * 5, -163, 3.2, 4), PAL.ink, { still: true });
  fillSolid(ellPts(9 + lk * 5, -163, 3.2, 4), PAL.ink, { still: true });
  if (o.mouth === 'o') stroke(ellPts(lk * 4, -147, 5, 6), { w: 2.5, double: false });
  else stroke(ellPts(lk * 4, -152, 9, 6, 0.3, 0, Math.PI * 0.7), { w: 2.5, double: false, seed: 12 });
  // hats & hair
  if (o.hat === 'hard') {
    fillPoly(parsePath('M-28,-172 C-28,-206 28,-206 28,-172 Z')[0], PAL.mustard, { seed: 13 });
    path('M-28,-172 C-28,-206 28,-206 28,-172', { w: 3 });
    stroke([[-36, -171], [36, -171]], { w: 5, seed: 14 });
  } else if (o.hair) {
    fillSolid(parsePath('M-28,-166 C-30,-196 30,-198 28,-166 C18,-178 -8,-182 -28,-166 Z')[0], o.hair, { alpha: 0.95 });
  }
  if (o.mug) {
    push(hR[0] + 6, hR[1] - 2);
    fillPoly(rrPts(-10, -20, 22, 26, 4, 0), PAL.white, { seed: 15 });
    stroke(rrPts(-10, -20, 22, 26, 4, 4), { w: 2.5 });
    stroke(ellPts(14, -8, 6, 7, -1.4, 0, Math.PI * 1.2), { w: 2.5, double: false });
    for (let i = 0; i < 2; i++) { const k = (S.t * 0.6 + i * 0.5) % 1; stroke(curvePts(-2 + i * 8, -26 - k * 20, 2 + i * 8, -40 - k * 26, 0.6), { w: 2, alpha: (1 - k) * 0.6, double: false }); }
    pop();
  }
  pop();
  pop();
}

/* ---------- AI agent bot ---------- */
function bot(x, y, s, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0) return;
  const t = S.t;
  const hover = Math.sin(t * 3 + (o.seed || 0)) * 5;
  push(x, y + hover, s * E.back(clamp(prog)));
  const col = o.color || PAL.lav;
  fillSolid(ellPts(0, 18 - hover, 40, 7), 'rgba(60,40,20,0.12)', { still: true });
  // body
  fillPoly(rrPts(-30, -56, 60, 52, 14, 0), col, { seed: 1 });
  stroke(rrPts(-30, -56, 60, 52, 14, 8), { w: 3 });
  stroke([[-30, -36], [-48, -18 + Math.sin(t * 4 + (o.seed || 0)) * 6]], { w: 4, seed: 2 });
  stroke([[30, -36], [48, -22 - Math.sin(t * 4 + 1 + (o.seed || 0)) * 6]], { w: 4, seed: 3 });
  stroke([[-14, -4], [-14, 8]], { w: 4 }); stroke([[14, -4], [14, 8]], { w: 4 });
  // head
  fillPoly(rrPts(-46, -134, 92, 72, 20, 0), col, { seed: 4 });
  stroke(rrPts(-46, -134, 92, 72, 20, 10), { w: 3.5 });
  fillSolid(rrPts(-34, -122, 68, 48, 12, 0), '#3b3846', { alpha: 0.92 });
  const bl = owlBlink(t, (o.seed || 0) + 2);
  const ex = o.look ? o.look * 5 : 0;
  fillSolid(rrPts(-20 + ex, -110 + bl * 8, 10, 16 - bl * 14, 5, 0), '#9ff0d9', { still: true });
  fillSolid(rrPts(10 + ex, -110 + bl * 8, 10, 16 - bl * 14, 5, 0), '#9ff0d9', { still: true });
  stroke(ellPts(ex, -90, 9, 4, 0.3, 0, Math.PI * 0.7), { w: 2.5, color: '#9ff0d9', double: false });
  // antenna
  stroke([[0, -134], [0, -156]], { w: 3 });
  fillSolid(ellPts(0, -160, 7, 7), o.light || PAL.coral, { still: true });
  stroke(ellPts(0, -160, 7, 7), { w: 2.5, double: false });
  if (o.hat === 'detective') {
    fillPoly(parsePath('M-40,-136 C-36,-170 36,-170 40,-136 Z')[0], PAL.brown, { seed: 5 });
    path('M-40,-136 C-36,-170 36,-170 40,-136', { w: 3 });
    stroke([[-54, -134], [54, -134]], { w: 5 });
  }
  if (o.hat === 'cap') {
    fillPoly(parsePath('M-38,-136 C-34,-168 34,-168 38,-136 Z')[0], PAL.mustard, { seed: 6 });
    path('M-38,-136 C-34,-168 34,-168 38,-136', { w: 3 });
    stroke([[30, -138], [66, -134]], { w: 6 });
  }
  pop();
}

/* ---------- props ---------- */
function magnifier(x, y, s, o = {}) {
  push(x, y, s, o.rot || 0);
  fillPoly(ellPts(0, 0, 34, 34), PAL.sky, { alpha: 0.6, seed: 1, edge: false });
  stroke(ellPts(0, 0, 34, 34), { w: 6, seed: 2 });
  stroke([[24, 24], [64, 64]], { w: 11, color: PAL.brown, double: false, seed: 3 });
  stroke([[24, 24], [64, 64]], { w: 3, seed: 4 });
  stroke(ellPts(-8, -8, 16, 16, 3.6, 0, 1.2), { w: 3, color: PAL.white, double: false, seed: 5 });
  pop();
}
function box(x, y, w, h, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  fillPoly(rrPts(x, y, w, h, 4, 0), o.color || PAL.brownL, { alpha: prog, seed: o.seed || hashN(x, y) });
  stroke(rrPts(x, y, w, h, 4, 8), { w: o.w || 3, prog, seed: (o.seed || 0) + 1 });
  if (o.tape !== false) stroke([[x + w / 2, y], [x + w / 2, y + h * 0.35]], { w: 3, prog, color: PAL.brown, double: false });
}
function coin(x, y, r, o = {}) {
  fillPoly(ellPts(x, y, r, r), PAL.mustard, { seed: hashN(x, y), alpha: o.alpha === undefined ? 1 : o.alpha, grain: false });
  stroke(ellPts(x, y, r, r), { w: 2.5, alpha: o.alpha === undefined ? 1 : o.alpha, seed: hashN(y, x) });
  text('£', x, y + r * 0.42, { size: r * 1.3, font: 'brush', align: 'center', color: PAL.brown, alpha: o.alpha === undefined ? 1 : o.alpha, jit: 0.5 });
}
function van(x, y, s, o = {}) {
  push(x, y, s);
  const body = 'M-150,-20 L-150,-150 L60,-150 L60,-20 Z';
  const cab = 'M60,-20 L60,-118 L118,-118 L150,-72 L150,-20 Z';
  fillPoly(parsePath(body)[0], PAL.white, { seed: 1 });
  fillPoly(parsePath(cab)[0], PAL.coral, { seed: 2 });
  path(body, { w: 3.5 }); path(cab, { w: 3.5 });
  fillPoly(parsePath('M76,-108 L112,-108 L134,-76 L76,-76 Z')[0], PAL.sky, { seed: 3 });
  path('M76,-108 L112,-108 L134,-76 L76,-76 Z', { w: 2.5 });
  text(o.label || 'DELIVERY', -45, -76, { size: 40, font: 'brush', align: 'center', color: PAL.tealD });
  const wr = o.wheel || 0;
  for (const wx of [-96, 104]) {
    fillSolid(ellPts(wx, -16, 26, 26), PAL.ink, { still: true });
    fillSolid(ellPts(wx, -16, 10, 10), PAL.greyL, { still: true });
    stroke([[wx + Math.cos(wr) * 18, -16 + Math.sin(wr) * 18], [wx - Math.cos(wr) * 18, -16 - Math.sin(wr) * 18]], { w: 2.5, color: PAL.greyL, double: false });
  }
  pop();
}
function till(x, y, s, o = {}) {
  push(x, y, s);
  // receipt
  const rk = o.receipt || 0;
  if (rk > 0) {
    const rh = 40 + rk * 150;
    fillSolid(rrPts(-34, -150 - rh, 68, rh + 10, 3, 0), PAL.white, { still: true });
    stroke(rrPts(-34, -150 - rh, 68, rh + 10, 3, 4), { w: 2.5 });
    const lines = ['VOID', 'VOID', 'VOID', 'VOID'];
    for (let i = 0; i < 4; i++) {
      const yy = -150 - rh + 30 + i * 34;
      if (yy < -150) text(lines[i], 0, yy, { size: 24, font: 'body', weight: 700, align: 'center', color: PAL.coral, jit: 0.6 });
    }
  }
  const body = 'M-110,0 L-90,-120 L90,-120 L110,0 Z';
  fillPoly(parsePath(body)[0], PAL.lavL, { seed: 1 });
  path(body, { w: 3.5 });
  fillPoly(rrPts(-60, -190, 120, 58, 8, 0), PAL.ink, { seed: 2, alpha: 0.85 });
  stroke(rrPts(-60, -190, 120, 58, 8, 6), { w: 3 });
  stroke([[0, -132], [0, -120]], { w: 4 });
  text(o.screen || '£0.00', 0, -150, { size: 30, font: 'body', weight: 700, align: 'center', color: '#9ff0d9', jit: 0.5 });
  for (let r = 0; r < 3; r++) for (let c = 0; c < 4; c++) stroke(rrPts(-70 + c * 36, -100 + r * 30, 26, 18, 5, 4), { w: 2.2, double: false, seed: r * 4 + c });
  pop();
}
function clipboard(x, y, s, o = {}) {
  push(x, y, s, o.rot || 0);
  fillPoly(rrPts(-80, -110, 160, 220, 12, 0), PAL.brownL, { seed: 1 });
  stroke(rrPts(-80, -110, 160, 220, 12, 10), { w: 3.5 });
  fillSolid(rrPts(-66, -92, 132, 190, 4, 0), PAL.white, { still: true });
  fillPoly(rrPts(-34, -124, 68, 30, 8, 0), PAL.grey, { seed: 2 });
  stroke(rrPts(-34, -124, 68, 30, 8, 6), { w: 3 });
  const nums = o.nums || ['12', '13', '21?'];
  nums.forEach((n, i) => {
    text(n, -46, -44 + i * 56, { size: 46, font: 'hand', weight: 700, color: i === nums.length - 1 ? PAL.coral : PAL.ink });
    if (i < nums.length - 1 && o.strike) strike(-52, 20, -58 + i * 56, { prog: clamp(o.strike * 2 - i * 0.5), w: 3.5 });
  });
  pop();
}
function laptop(x, y, s, o = {}) {
  // screen area: (-420,-520)..(420,-40) at s=1; base below
  push(x, y, s);
  const scr = rrPts(-440, -540, 880, 530, 26, 0);
  fillPoly(scr, PAL.greyL, { seed: 1 });
  stroke(rrPts(-440, -540, 880, 530, 26, 14), { w: 4 });
  fillSolid(rrPts(-414, -514, 828, 478, 10, 0), PAL.white, { still: true });
  const base = 'M-500,0 L500,0 L540,40 L-540,40 Z';
  fillPoly(parsePath(base)[0], PAL.grey, { seed: 2 });
  path(base, { w: 4 });
  stroke([[-70, 14], [70, 14]], { w: 3, alpha: 0.6 });
  pop();
}
function plug(x, y, s, o = {}) {
  push(x, y, s, o.rot || 0);
  stroke([[-32, -60], [-32, -100]], { w: 10, color: PAL.greyL, double: false }); stroke([[-32, -60], [-32, -100]], { w: 2.5 });
  stroke([[32, -60], [32, -100]], { w: 10, color: PAL.greyL, double: false }); stroke([[32, -60], [32, -100]], { w: 2.5 });
  const body = rrPts(-70, -64, 140, 110, 30, 0);
  fillPoly(body, o.color || PAL.mustard, { seed: 1 });
  stroke(rrPts(-70, -64, 140, 110, 30, 12), { w: 4 });
  if (o.label) text(o.label, 0, 6, { size: 40, font: 'brush', align: 'center' });
  pop();
}
function socket(x, y, s, o = {}) {
  push(x, y, s);
  fillPoly(rrPts(-110, -110, 220, 220, 40, 0), o.color || PAL.white, { seed: 1 });
  stroke(rrPts(-110, -110, 220, 220, 40, 14), { w: 4 });
  fillSolid(ellPts(-34, -20, 12, 18), PAL.ink, { still: true, alpha: 0.9 });
  fillSolid(ellPts(34, -20, 12, 18), PAL.ink, { still: true, alpha: 0.9 });
  if (o.label) text(o.label, 0, 72, { size: 50, font: 'brush', align: 'center', color: PAL.tealD });
  pop();
}
function cabinet(x, y, s, o = {}) {
  push(x, y, s);
  const prog = o.prog === undefined ? 1 : o.prog;
  fillPoly(rrPts(-150, -400, 300, 400, 14, 0), PAL.sky, { seed: 1, alpha: prog });
  stroke(rrPts(-150, -400, 300, 400, 14, 12), { w: 4, prog });
  const labels = o.labels || ['stock counts', 'deliveries', 'tills', 'returns'];
  labels.forEach((l, i) => {
    const yy = -380 + i * 94;
    fillSolid(rrPts(-126, yy, 252, 80, 8, 0), PAL.white, { alpha: prog, still: true });
    stroke(rrPts(-126, yy, 252, 80, 8, 6), { w: 3, prog: clamp(prog * 2 - 0.5 - i * 0.1) });
    stroke([[-30, yy + 22], [30, yy + 22]], { w: 5, prog: clamp(prog * 2 - 0.6), color: PAL.inkSoft });
    text(l, 0, yy + 62, { size: 32, font: 'body', align: 'center', prog: clamp(prog * 2 - 0.8 - i * 0.1) });
  });
  pop();
}
function cylinder(x, y, s, o = {}) {
  push(x, y, s);
  const w = 90, h = 120;
  fillPoly([[-w, -h], [w, -h], [w, 0], ...ellPts(0, 0, w, 26, 0, 0, Math.PI), [-w, -h]], o.color || PAL.sageL, { seed: 1 });
  fillPoly(ellPts(0, -h, w, 26), o.top || PAL.sage, { seed: 2 });
  stroke(ellPts(0, -h, w, 26), { w: 3.5 });
  stroke([[-w, -h], [-w, 0]], { w: 3.5 }); stroke([[w, -h], [w, 0]], { w: 3.5 });
  stroke(ellPts(0, 0, w, 26, 0, 0, Math.PI), { w: 3.5 });
  stroke(ellPts(0, -h / 2, w, 26, 0, 0, Math.PI), { w: 2.5, alpha: 0.6 });
  if (o.label) text(o.label, 0, -h / 2 + 50, { size: 34, font: 'brush', align: 'center' });
  pop();
}
function hand(x, y, s, o = {}) {
  // pointing cursor hand
  push(x, y, s, o.rot || 0);
  const d = 'M0,0 L0,-46 C0,-56 14,-56 14,-46 L14,-18 C16,-26 28,-26 28,-16 C30,-24 42,-24 42,-12 C44,-20 56,-18 56,-6 L56,20 C56,40 44,54 24,54 L10,54 C-6,54 -14,44 -20,32 L-30,10 C-34,0 -22,-6 -14,2 Z';
  fillPoly(parsePath(d)[0], PAL.white, { seed: 1, alpha: 1, op: 'source-over' });
  path(d, { w: 3.2 });
  pop();
}
function moon(x, y, s) {
  push(x, y, s);
  const d = 'M10,-30 C-22,-26 -30,16 -4,30 C-28,34 -48,10 -40,-12 C-34,-30 -14,-38 10,-30 Z';
  fillPoly(parsePath(d)[0], PAL.mustL, { seed: 1 });
  path(d, { w: 3 });
  pop();
}
function trophy(x, y, s) {
  push(x, y, s);
  const cup = 'M-50,-150 L50,-150 C50,-90 30,-66 0,-62 C-30,-66 -50,-90 -50,-150 Z';
  fillPoly(parsePath(cup)[0], PAL.mustard, { seed: 1 });
  path(cup, { w: 3.5 });
  stroke(ellPts(-56, -126, 18, 22, 1.6, 0, Math.PI), { w: 4, double: false });
  stroke(ellPts(56, -126, 18, 22, -1.6, 0, Math.PI), { w: 4, double: false });
  stroke([[0, -62], [0, -30]], { w: 6 });
  fillPoly(rrPts(-34, -32, 68, 30, 4, 0), PAL.brown, { seed: 2 });
  stroke(rrPts(-34, -32, 68, 30, 4, 4), { w: 3 });
  pop();
}
function gradCap(x, y, s, rot = 0) {
  push(x, y, s, rot);
  fillPoly([[-70, 0], [0, -30], [70, 0], [0, 30]], PAL.ink, { seed: 1, alpha: 0.85 });
  path('M-70,0 L0,-30 L70,0 L0,30 Z', { w: 3 });
  fillPoly(rrPts(-36, 10, 72, 34, 6, 0), PAL.ink, { seed: 2, alpha: 0.85 });
  stroke([[0, 0], [52, 8], [56, 40]], { w: 3, color: PAL.mustard });
  pop();
}
function storeIcon(x, y, s, o = {}) {
  push(x, y, s);
  fillPoly(rrPts(-50, -70, 100, 70, 4, 0), PAL.white, { seed: 1 });
  stroke(rrPts(-50, -70, 100, 70, 4, 4), { w: 2.5 });
  for (let i = 0; i < 5; i++) fillPoly(rrPts(-56 + i * 22.4, -96, 22.4, 26, 3, 0), i % 2 ? PAL.white : (o.color || PAL.coral), { seed: 2 + i, edge: false });
  stroke(rrPts(-56, -96, 112, 26, 3, 4), { w: 2.5 });
  stroke(rrPts(-16, -42, 32, 42, 2, 4), { w: 2.5 });
  pop();
}
