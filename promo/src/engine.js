/* Inventory Sentinel promo: hand-drawn canvas engine.
 * Everything is a pure function of time t, so the same code plays live and renders frame-exact video. */
'use strict';

const W = 1920, H = 1080, BOIL_FPS = 12;
const PAL = {
  paper: '#f8f1e1', ink: '#2b2935', inkSoft: '#6b6575', pencil: '#8d8796',
  teal: '#3c8cb0', tealD: '#2a6886', tealL: '#a9d6e8', sky: '#cfe8f2',
  coral: '#e65f4a', coralL: '#f5ab9b', orange: '#f08c46',
  mustard: '#f1b43a', mustL: '#f9dc94', sage: '#76ab66', sageL: '#bfdcae',
  lav: '#9b88c6', lavL: '#d6cdea', cream: '#fdf2da', white: '#fffbf2',
  grey: '#9a95a0', greyL: '#d9d5dc', brown: '#a8754f', brownL: '#d9b48f', pink: '#f3a9b9'
};
const FONT = { hand: '"Caveat", cursive', brush: '"Caveat Brush", "Caveat", cursive', body: '"Kalam", cursive' };

const S = { ctx: null, t: 0, boil: 0, ls: 1 };

/* ---------- math ---------- */
const clamp = (v, a = 0, b = 1) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, k) => a + (b - a) * k;
const seg = (t, a, b) => clamp((t - a) / (b - a));
const E = {
  lin: (k) => k,
  in: (k) => k * k * k,
  out: (k) => 1 - Math.pow(1 - k, 3),
  out2: (k) => 1 - (1 - k) * (1 - k),
  inOut: (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
  sine: (k) => -(Math.cos(Math.PI * k) - 1) / 2,
  back: (k) => { const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); },
  elastic: (k) => (k <= 0 ? 0 : k >= 1 ? 1 : Math.pow(2, -10 * k) * Math.sin((k * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1),
};
/** 0 before a, eased 0..1 between a and a+d */
const ez = (t, a, d, f = E.out) => f(seg(t, a, a + d));
/** pop-in scale with overshoot */
const popIn = (t, a, d = 0.5) => (t < a ? 0 : E.back(seg(t, a, a + d)));
/** fade window: in over [a,a+fi], out over [b-fo,b] */
const win = (t, a, b, fi = 0.3, fo = 0.3) => Math.min(seg(t, a, a + fi), 1 - seg(t, b - fo, b));

function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hashN(...ns) {
  let h = 2166136261 >>> 0;
  for (const v of ns) { h ^= Math.round(v * 8) | 0; h = Math.imul(h, 16777619) >>> 0; }
  return h;
}
function hashStr(s) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
  return h;
}
const hashPts = (p) => hashN(p[0][0], p[0][1], p[p.length - 1][0], p[p.length - 1][1], p.length, p[p.length >> 1][0]);

/* ---------- geometry ---------- */
function resample(pts, step) {
  const n = pts.length;
  if (n < 2) return pts.slice();
  const cum = [0];
  for (let i = 1; i < n; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const L = cum[n - 1];
  if (L < 1e-6) return [pts[0], pts[0]];
  const m = Math.max(2, Math.ceil(L / step) + 1);
  const out = new Array(m);
  let j = 1;
  for (let k = 0; k < m; k++) {
    const d = (L * k) / (m - 1);
    while (j < n - 1 && cum[j] < d) j++;
    const s0 = cum[j - 1], s1 = cum[j], f = s1 > s0 ? (d - s0) / (s1 - s0) : 0;
    out[k] = [pts[j - 1][0] + (pts[j][0] - pts[j - 1][0]) * f, pts[j - 1][1] + (pts[j][1] - pts[j - 1][1]) * f];
  }
  return out;
}
function wobble(pts, amp, seed) {
  const r = rng(seed);
  const f1 = 0.09 + r() * 0.12, f2 = 0.35 + r() * 0.3, p1 = r() * 6.283, p2 = r() * 6.283;
  const sx = (r() - 0.5) * amp * 0.9, sy = (r() - 0.5) * amp * 0.9;
  const n = pts.length, out = new Array(n);
  for (let i = 0; i < n; i++) {
    const a = pts[i > 0 ? i - 1 : 0], b = pts[i < n - 1 ? i + 1 : n - 1];
    let nx = a[1] - b[1], ny = b[0] - a[0];
    const l = Math.hypot(nx, ny) || 1;
    nx /= l; ny /= l;
    const o = amp * (Math.sin(i * f1 + p1) * 0.75 + Math.sin(i * f2 + p2) * 0.35);
    out[i] = [pts[i][0] + nx * o + sx, pts[i][1] + ny * o + sy];
  }
  return out;
}
function cut(p, prog) {
  if (prog >= 1) return p;
  const f = prog * (p.length - 1), i = Math.floor(f), k = f - i;
  const out = p.slice(0, i + 1);
  if (i + 1 < p.length) out.push([lerp(p[i][0], p[i + 1][0], k), lerp(p[i][1], p[i + 1][1], k)]);
  return out;
}
function trace(c, p) {
  c.moveTo(p[0][0], p[0][1]);
  if (p.length < 3) { for (let i = 1; i < p.length; i++) c.lineTo(p[i][0], p[i][1]); return; }
  for (let i = 1; i < p.length - 1; i++) {
    const mx = (p[i][0] + p[i + 1][0]) / 2, my = (p[i][1] + p[i + 1][1]) / 2;
    c.quadraticCurveTo(p[i][0], p[i][1], mx, my);
  }
  c.lineTo(p[p.length - 1][0], p[p.length - 1][1]);
}

/* shapes as point lists */
function ellPts(cx, cy, rx, ry, a0 = -Math.PI / 2, over = 0.22, sweep = Math.PI * 2) {
  const n = Math.max(16, Math.ceil(((rx + ry) * (sweep + over)) / 9));
  const out = [];
  for (let i = 0; i <= n; i++) { const a = a0 + ((sweep + over) * i) / n; out.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]); }
  return out;
}
function rrPts(x, y, w, h, r = 12, over = 18) {
  r = Math.min(r, w / 2, h / 2);
  const out = [];
  const arc = (cx, cy, a0) => { for (let i = 0; i <= 5; i++) { const a = a0 + (Math.PI / 2) * (i / 5); out.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } };
  out.push([x + r, y]);
  arc(x + w - r, y + r, -Math.PI / 2);
  arc(x + w - r, y + h - r, 0);
  arc(x + r, y + h - r, Math.PI / 2);
  arc(x + r, y + r, Math.PI);
  out.push([x + r + over, y]);
  return out;
}
function polyClosed(p) { return [...p, p[0]]; }
function bez(p0, p1, p2, p3, n = 16) {
  const out = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, u = 1 - t;
    out.push([u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0], u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]]);
  }
  return out;
}
function curvePts(x1, y1, x2, y2, bend = 0.15) {
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, dx = x2 - x1, dy = y2 - y1;
  const cx = mx - dy * bend, cy = my + dx * bend;
  const out = [];
  for (let i = 0; i <= 20; i++) { const t = i / 20, u = 1 - t; out.push([u * u * x1 + 2 * u * t * cx + t * t * x2, u * u * y1 + 2 * u * t * cy + t * t * y2]); }
  return out;
}

/* tiny SVG path parser -> list of polylines (M L H V C Q Z, absolute and relative) */
const _pathCache = new Map();
function parsePath(d) {
  let hit = _pathCache.get(d);
  if (hit) return hit;
  const toks = d.match(/[MLHVCQZmlhvcqz]|-?\d*\.?\d+(?:e-?\d+)?/g);
  const subs = [];
  let cur = null, x = 0, y = 0, sx = 0, sy = 0, cmd = 'M', i = 0;
  const num = () => parseFloat(toks[i++]);
  while (i < toks.length) {
    if (/[A-Za-z]/.test(toks[i])) cmd = toks[i++];
    const rel = cmd === cmd.toLowerCase(), C = cmd.toUpperCase();
    if (C === 'Z') { if (cur) { cur.push([sx, sy]); } x = sx; y = sy; continue; }
    if (C === 'M') {
      x = (rel ? x : 0) + num(); y = (rel ? y : 0) + num(); sx = x; sy = y;
      cur = [[x, y]]; subs.push(cur); cmd = rel ? 'l' : 'L';
    } else if (C === 'L') { x = (rel ? x : 0) + num(); y = (rel ? y : 0) + num(); cur.push([x, y]); }
    else if (C === 'H') { x = (rel ? x : 0) + num(); cur.push([x, y]); }
    else if (C === 'V') { y = (rel ? y : 0) + num(); cur.push([x, y]); }
    else if (C === 'C') {
      const ox = rel ? x : 0, oy = rel ? y : 0;
      const p1 = [ox + num(), oy + num()], p2 = [ox + num(), oy + num()], p3 = [ox + num(), oy + num()];
      cur.push(...bez([x, y], p1, p2, p3, 14).slice(1)); x = p3[0]; y = p3[1];
    } else if (C === 'Q') {
      const ox = rel ? x : 0, oy = rel ? y : 0;
      const q = [ox + num(), oy + num()], p3 = [ox + num(), oy + num()];
      const p1 = [x + (2 / 3) * (q[0] - x), y + (2 / 3) * (q[1] - y)], p2 = [p3[0] + (2 / 3) * (q[0] - p3[0]), p3[1] + (2 / 3) * (q[1] - p3[1])];
      cur.push(...bez([x, y], p1, p2, p3, 12).slice(1)); x = p3[0]; y = p3[1];
    } else { i++; }
  }
  _pathCache.set(d, subs);
  return subs;
}

/* ---------- drawing ---------- */
function stroke(pts, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0 || !pts || pts.length < 2) return;
  const c = S.ctx, w = (o.w || 3) * S.ls;
  const base = resample(pts, (o.step || 7) * S.ls);
  const seed = o.seed !== undefined ? o.seed : hashPts(pts);
  const rough = (o.rough !== undefined ? o.rough : 1.5) * S.ls;
  const boil = o.still ? 0 : S.boil;
  c.save();
  c.lineCap = 'round'; c.lineJoin = 'round';
  c.strokeStyle = o.color || PAL.ink;
  c.globalAlpha *= o.alpha === undefined ? 1 : o.alpha;
  c.lineWidth = w;
  if (o.dash) c.setLineDash(o.dash);
  c.beginPath(); trace(c, cut(wobble(base, rough, seed * 31 + boil * 977), prog)); c.stroke();
  if (o.double !== false && w >= 2 * S.ls && !o.dash) {
    c.globalAlpha *= 0.32; c.lineWidth = w * 0.6;
    c.beginPath(); trace(c, cut(wobble(base, rough * 1.5, seed * 17 + boil * 331 + 5), prog)); c.stroke();
  }
  c.restore();
}
/** stroke several polylines in sequence: prog spreads over their total length */
function strokeSeq(list, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0) return;
  const lens = list.map((p) => { let L = 0; for (let i = 1; i < p.length; i++) L += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]); return L; });
  const tot = lens.reduce((a, b) => a + b, 0) || 1;
  let acc = 0;
  for (let k = 0; k < list.length; k++) {
    const a = acc / tot, b = (acc + lens[k]) / tot; acc += lens[k];
    const pk = clamp((prog - a) / (b - a || 1));
    if (pk > 0) stroke(list[k], { ...o, prog: pk, seed: (o.seed || 0) + k * 7 + hashPts(list[k]) });
  }
}
function path(d, o = {}) { strokeSeq(parsePath(d), o); }

let _grain = null;
function fillPoly(pts, color, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0) return;
  const c = S.ctx;
  const seed = o.seed !== undefined ? o.seed : hashPts(pts);
  const boil = o.still ? 0 : S.boil;
  const off = (o.off || [4, 3]).map((v) => v * S.ls);
  const base = resample(pts, 12 * S.ls);
  const rgh = (o.rough || 2.2) * S.ls;
  c.save();
  c.globalCompositeOperation = o.op || 'multiply';
  c.fillStyle = color;
  const a0 = (o.alpha === undefined ? 0.9 : o.alpha) * prog;
  const bbA = bbox(base), small = (bbA[2] - bbA[0]) * (bbA[3] - bbA[1]) < 2500 * S.ls * S.ls;
  const p1 = wobble(base, rgh, seed * 7 + boil * 53);
  c.globalAlpha *= a0 * (small ? 0.9 : 0.75);
  c.beginPath(); trace(c, p1.map((q) => [q[0] + off[0], q[1] + off[1]])); c.closePath(); c.fill();
  const p2 = wobble(base, rgh * 1.6, seed * 11 + boil * 71 + 3);
  c.globalAlpha = c.globalAlpha / 0.75 * 0.35;
  if (small) c.globalAlpha = 0;
  c.beginPath(); trace(c, p2.map((q) => [q[0] + off[0] * 0.5, q[1] + off[1] * 0.5])); c.closePath(); c.fill();
  const bb = o.grain === false ? null : bbox(base);
  if (_grain && bb && (bb[2] - bb[0]) * (bb[3] - bb[1]) > 9000 * S.ls * S.ls) {
    c.clip();
    c.globalAlpha = (o.grainA === undefined ? 0.3 : o.grainA) * prog;
    c.fillStyle = _grain;
    c.fillRect(bb[0] - 10, bb[1] - 10, bb[2] - bb[0] + 20, bb[3] - bb[1] + 20);
  }
  c.restore();
  if (o.edge !== false) stroke(pts, { color, w: 2.5, alpha: 0.35 * prog, double: false, seed: seed + 9, rough: 2, still: o.still });
}
function bbox(p) {
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const q of p) { if (q[0] < x0) x0 = q[0]; if (q[0] > x1) x1 = q[0]; if (q[1] < y0) y0 = q[1]; if (q[1] > y1) y1 = q[1]; }
  return [x0, y0, x1, y1];
}
/** solid flat fill (for paper "cards" that must hide what is behind) */
function fillSolid(pts, color, o = {}) {
  const c = S.ctx;
  const p = wobble(resample(pts, 12 * S.ls), (o.rough || 1.2) * S.ls, (o.seed || hashPts(pts)) + (o.still ? 0 : S.boil) * 19);
  c.save(); c.globalAlpha *= o.alpha === undefined ? 1 : o.alpha; c.fillStyle = color;
  c.beginPath(); trace(c, p); c.closePath(); c.fill(); c.restore();
}
function hatch(pts, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0) return;
  const c = S.ctx, b = bbox(pts), gap = o.gap || 12, ang = o.ang === undefined ? -0.8 : o.ang;
  c.save();
  c.beginPath(); trace(c, pts); c.closePath(); c.clip();
  const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2, R = Math.hypot(b[2] - b[0], b[3] - b[1]) / 2 + 10;
  const dx = Math.cos(ang), dy = Math.sin(ang), nx = -dy, ny = dx;
  const n = Math.floor((2 * R) / gap);
  for (let i = 0; i <= n * prog; i++) {
    const o2 = -R + i * gap;
    stroke([[cx + nx * o2 - dx * R, cy + ny * o2 - dy * R], [cx + nx * o2 + dx * R, cy + ny * o2 + dy * R]], { w: o.w || 1.6, color: o.color || PAL.inkSoft, alpha: o.alpha || 0.5, double: false, rough: 1.2, seed: i * 13 + (o.seed || 0) });
  }
  c.restore();
}

/* ---------- text ---------- */
const _measure = new Map();
function charPos(c, font, str, subFont) {
  const key = font + '|' + (subFont || '') + '|' + str;
  let hit = _measure.get(key);
  if (hit) return hit;
  const chars = [...str], xs = [];
  let s = '', x = 0;
  for (const ch of chars) {
    xs.push(x);
    let adv;
    if (subFont && ch === '\u00a3') { c.font = subFont; adv = c.measureText(ch).width + 2; c.font = font; }
    else adv = c.measureText(s + ch).width - c.measureText(s).width;
    x += adv; s += ch;
  }
  hit = { chars, xs, w: x };
  if (_measure.size > 3000) _measure.clear();
  _measure.set(key, hit);
  return hit;
}
/** hand-lettered text: per-character boil, progressive write-on (prog 0..1) */
function text(str, x, y, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0 || !str) return 0;
  const c = S.ctx;
  const font = `${o.weight || 400} ${o.size || 40}px ${FONT[o.font || 'hand']}`;
  c.save();
  c.font = font;
  c.textBaseline = o.base || 'alphabetic';
  const sub = o.font === 'brush' && str.includes('\u00a3') ? `700 ${(o.size || 40) * 0.92}px ${FONT.body}` : null;
  const m = charPos(c, font, str, sub);
  const jit = o.jit === undefined ? 1 : o.jit;
  const ax = o.align === 'center' ? -m.w / 2 : o.align === 'right' ? -m.w : 0;
  c.translate(x + ax, y);
  c.fillStyle = o.color || PAL.ink;
  c.globalAlpha *= o.alpha === undefined ? 1 : o.alpha;
  // fast path: finished, low-jitter text (UI copy) boils as one run instead of glyph by glyph
  if (prog >= 1 && jit <= 0.5 && !sub && !o.stroke) {
    const r = rng(hashStr(str) + (o.seed || 0) + S.boil * 104729);
    c.translate((r() - 0.5) * 1.2 * jit * S.ls, (r() - 0.5) * 1.4 * jit * S.ls);
    c.rotate((r() - 0.5) * 0.01 * jit);
    c.fillText(str, 0, 0);
    c.restore();
    return m.w;
  }
  const n = m.chars.length, shown = prog * n;
  const seed0 = hashStr(str) + (o.seed || 0);
  const ga = c.globalAlpha;
  for (let i = 0; i < n; i++) {
    if (i >= shown) break;
    const ch = m.chars[i];
    if (ch === ' ') continue;
    const k = clamp(shown - i);
    const r = rng(seed0 + i * 7919 + S.boil * 104729);
    const rot = (r() - 0.5) * 0.05 * jit, dx = (r() - 0.5) * 1.2 * jit * S.ls, dy = (r() - 0.5) * 1.4 * jit * S.ls;
    c.save();
    c.translate(m.xs[i] + dx, dy + (1 - k) * 6 * S.ls);
    c.rotate(rot);
    c.globalAlpha = ga * k;
    // the brush face draws a pound sign that reads like a "t", so borrow Kalam's
    if (sub && ch === '\u00a3') c.font = sub;
    if (o.stroke) { c.lineWidth = o.stroke; c.strokeStyle = o.strokeColor || PAL.paper; c.lineJoin = 'round'; c.strokeText(ch, 0, 0); }
    c.fillText(ch, 0, 0);
    c.restore();
  }
  c.restore();
  return m.w;
}
function textW(str, size, fontKey = 'hand', weight = 400) {
  const c = S.ctx, font = `${weight} ${size}px ${FONT[fontKey]}`;
  c.save(); c.font = font; const w = charPos(c, font, str).w; c.restore();
  return w;
}

/* ---------- transforms ---------- */
function push(x = 0, y = 0, s = 1, rot = 0, sy) {
  const c = S.ctx; c.save(); c.translate(x, y); if (rot) c.rotate(rot); if (s !== 1 || (sy !== undefined && sy !== s)) c.scale(s, sy === undefined ? s : sy);
}
function pop() { S.ctx.restore(); }
function alpha(a) { S.ctx.globalAlpha *= a; }

/* ---------- reusable doodles ---------- */
function arrow(x1, y1, x2, y2, o = {}) {
  const pts = curvePts(x1, y1, x2, y2, o.bend === undefined ? 0.12 : o.bend);
  const prog = o.prog === undefined ? 1 : o.prog;
  stroke(pts, { ...o, prog });
  if (prog > 0.9) {
    const n = pts.length, a = pts[n - 1], b = pts[n - 4];
    const ang = Math.atan2(a[1] - b[1], a[0] - b[0]), L = o.head || 18;
    const k = seg(prog, 0.9, 1);
    stroke([[a[0] - Math.cos(ang - 0.5) * L * k, a[1] - Math.sin(ang - 0.5) * L * k], a, [a[0] - Math.cos(ang + 0.5) * L * k, a[1] - Math.sin(ang + 0.5) * L * k]], { ...o, prog: 1, seed: 77 });
  }
}
function check(x, y, s = 1, o = {}) { stroke([[x - 14 * s, y], [x - 4 * s, y + 11 * s], [x + 18 * s, y - 16 * s]], { w: 5 * s, color: PAL.sage, ...o }); }
function cross(x, y, s = 1, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  stroke([[x - 14 * s, y - 14 * s], [x + 14 * s, y + 14 * s]], { w: 5 * s, color: PAL.coral, ...o, prog: clamp(prog * 2) });
  stroke([[x + 14 * s, y - 14 * s], [x - 14 * s, y + 14 * s]], { w: 5 * s, color: PAL.coral, ...o, prog: clamp(prog * 2 - 1) });
}
/** scribbled-out strike line */
function strike(x1, x2, y, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  const pts = [];
  const n = 5;
  for (let i = 0; i <= n; i++) pts.push([lerp(x1, x2, i / n), y + (i % 2 ? -6 : 6)]);
  stroke([[x1 - 6, y + 2], [x2 + 6, y - 3]], { w: o.w || 5, color: o.color || PAL.coral, prog });
}
/** circle-it marker loop */
function circleIt(cx, cy, rx, ry, o = {}) {
  stroke(ellPts(cx, cy, rx, ry, -2.2, 0.6), { w: o.w || 4, color: o.color || PAL.coral, rough: 2.5, ...o });
}
function sparkle(x, y, s, t0, t, color = PAL.mustard) {
  const k = seg(t, t0, t0 + 0.7);
  if (k <= 0 || k >= 1) return;
  const g = E.out(k), a = 1 - k;
  for (let i = 0; i < 6; i++) {
    const ang = (i / 6) * Math.PI * 2 + 0.3;
    const r0 = 14 * s * g + 6 * s, r1 = r0 + 16 * s * (1 - k * 0.6);
    stroke([[x + Math.cos(ang) * r0, y + Math.sin(ang) * r0], [x + Math.cos(ang) * r1, y + Math.sin(ang) * r1]], { w: 4 * s, color, alpha: a, double: false, seed: i });
  }
}
/** puff of smoke when something vanishes */
function poof(x, y, s, t0, t) {
  const k = seg(t, t0, t0 + 0.75);
  if (k <= 0 || k >= 1) return;
  const g = E.out(k);
  for (let i = 0; i < 7; i++) {
    const ang = (i / 7) * Math.PI * 2 + i;
    const d = 34 * s * g + 8, r = (20 + (i % 3) * 8) * s * (1 - k * 0.5);
    const cx = x + Math.cos(ang) * d, cy = y + Math.sin(ang) * d * 0.8 - 14 * g * s;
    fillSolid(ellPts(cx, cy, r, r * 0.9), PAL.white, { alpha: 0.95 * (1 - k * k), seed: i * 3 });
    stroke(ellPts(cx, cy, r, r * 0.9), { w: 3, color: PAL.inkSoft, alpha: 1 - k * k, double: false, seed: i * 5 });
  }
}
/** a sticky-note/paper card */
function card(x, y, w, h, o = {}) {
  const prog = o.prog === undefined ? 1 : o.prog;
  if (prog <= 0) return;
  const r = o.r === undefined ? 14 : o.r;
  if (o.shadow !== false) fillSolid(rrPts(x + 7, y + 9, w, h, r, 0), 'rgba(60,40,20,0.13)', { alpha: prog, rough: 1.5, still: true });
  fillSolid(rrPts(x, y, w, h, r, 0), o.bg || PAL.white, { alpha: Math.min(1, prog * 1.5), rough: 1.2, still: true });
  if (o.tint) fillPoly(rrPts(x, y, w, h, r, 0), o.tint, { alpha: (o.tintA || 0.5) * prog, edge: false, grainA: 0.12 });
  stroke(rrPts(x, y, w, h, r, 12), { w: o.w || 3, prog: E.out(prog), color: o.color || PAL.ink });
}
function chip(str, x, y, color, o = {}) {
  const size = o.size || 26;
  const w = textW(str, size, 'body', 700) + size * 0.9, h = size * 1.45;
  const a = o.prog === undefined ? 1 : o.prog;
  if (a <= 0) return w;
  push(x + (o.align === 'right' ? -w : 0), y, 1);
  alpha(Math.min(1, a * 1.4));
  fillPoly(rrPts(0, -h / 2, w, h, h / 2, 0), color, { alpha: 0.85, edge: false, grain: false });
  stroke(rrPts(0, -h / 2, w, h, h / 2, 8), { w: 2, color: o.line || PAL.ink, alpha: 0.7, double: false });
  text(str, w / 2, size * 0.36, { size, font: 'body', weight: 700, align: 'center', color: o.ink || PAL.ink, jit: 0.4 });
  pop();
  return w;
}

/* ---------- paper, grain, vignette ---------- */
let _paperPat = null, _vignette = null, _grainFrames = [];
function makeTextures() {
  const mk = (w, h) => { const cv = document.createElement('canvas'); cv.width = w; cv.height = h; return cv; };
  // paper tile
  const P = mk(1024, 1024), pc = P.getContext('2d');
  pc.fillStyle = PAL.paper; pc.fillRect(0, 0, 1024, 1024);
  const r = rng(42);
  // soft mottling (tileable by wrapping blobs)
  for (let i = 0; i < 260; i++) {
    const x = r() * 1024, y = r() * 1024, rad = 40 + r() * 160, dark = r() < 0.5;
    for (const ox of [-1024, 0, 1024]) for (const oy of [-1024, 0, 1024]) {
      const g = pc.createRadialGradient(x + ox, y + oy, 0, x + ox, y + oy, rad);
      g.addColorStop(0, dark ? 'rgba(160,120,70,0.018)' : 'rgba(255,255,255,0.05)'); g.addColorStop(1, 'rgba(0,0,0,0)');
      pc.fillStyle = g; pc.fillRect(x + ox - rad, y + oy - rad, rad * 2, rad * 2);
    }
  }
  // fibres
  pc.lineCap = 'round';
  for (let i = 0; i < 2600; i++) {
    const x = r() * 1024, y = r() * 1024, a = r() * Math.PI, l = 4 + r() * 22;
    pc.strokeStyle = r() < 0.6 ? `rgba(120,95,60,${0.03 + r() * 0.06})` : `rgba(255,255,255,${0.1 + r() * 0.15})`;
    pc.lineWidth = 0.6 + r() * 0.8;
    pc.beginPath(); pc.moveTo(x, y); pc.quadraticCurveTo(x + Math.cos(a) * l * 0.5 + (r() - 0.5) * 4, y + Math.sin(a) * l * 0.5, x + Math.cos(a) * l, y + Math.sin(a) * l); pc.stroke();
  }
  // speckles
  const id = pc.getImageData(0, 0, 1024, 1024), d = id.data;
  for (let i = 0; i < d.length; i += 4) { const n = (r() - 0.5) * 10; d[i] += n; d[i + 1] += n; d[i + 2] += n * 0.9; }
  pc.putImageData(id, 0, 0);
  for (let i = 0; i < 500; i++) { pc.fillStyle = `rgba(90,70,50,${0.08 + r() * 0.15})`; pc.beginPath(); pc.arc(r() * 1024, r() * 1024, 0.4 + r() * 1.1, 0, 6.3); pc.fill(); }
  _paperPat = S.ctx.createPattern(P, 'repeat');

  // watercolour granulation tile (multiplied inside fills)
  const G = mk(512, 512), gc = G.getContext('2d');
  gc.fillStyle = '#fff'; gc.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 900; i++) {
    const x = r() * 512, y = r() * 512, rad = 3 + r() * 26;
    for (const ox of [-512, 0, 512]) for (const oy of [-512, 0, 512]) {
      const g = gc.createRadialGradient(x + ox, y + oy, 0, x + ox, y + oy, rad);
      g.addColorStop(0, `rgba(80,60,40,${0.05 + r() * 0.07})`); g.addColorStop(1, 'rgba(0,0,0,0)');
      gc.fillStyle = g; gc.fillRect(x + ox - rad, y + oy - rad, rad * 2, rad * 2);
    }
  }
  const gd = gc.getImageData(0, 0, 512, 512), g2 = gd.data;
  for (let i = 0; i < g2.length; i += 4) { const n = (r() - 0.5) * 26; g2[i] += n; g2[i + 1] += n; g2[i + 2] += n; }
  gc.putImageData(gd, 0, 0);
  _grain = S.ctx.createPattern(G, 'repeat');

  // vignette
  const V = mk(W, H), vc = V.getContext('2d');
  const vg = vc.createRadialGradient(W / 2, H * 0.48, H * 0.35, W / 2, H / 2, H * 1.05);
  vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(0.72, 'rgba(70,45,20,0.06)'); vg.addColorStop(1, 'rgba(50,30,10,0.30)');
  vc.fillStyle = vg; vc.fillRect(0, 0, W, H);
  const lg = vc.createLinearGradient(0, 0, W, H);
  lg.addColorStop(0, 'rgba(255,240,200,0.10)'); lg.addColorStop(0.5, 'rgba(255,240,200,0)'); lg.addColorStop(1, 'rgba(120,80,40,0.06)');
  vc.fillStyle = lg; vc.fillRect(0, 0, W, H);
  _vignette = V;

  // film grain frames
  for (let f = 0; f < 4; f++) {
    const F = mk(W / 2, H / 2), fc = F.getContext('2d'), im = fc.createImageData(W / 2, H / 2), dd = im.data;
    for (let i = 0; i < dd.length; i += 4) { const v = r(); const dark = v < 0.5; dd[i] = dd[i + 1] = dd[i + 2] = dark ? 40 : 255; dd[i + 3] = Math.abs(v - 0.5) * 2 * 26; }
    fc.putImageData(im, 0, 0);
    const B = mk(W, H), bc = B.getContext('2d');
    bc.drawImage(V, 0, 0); bc.imageSmoothingEnabled = true; bc.drawImage(F, 0, 0, W, H);
    _grainFrames.push(B);
  }
}
function drawPaper(view) {
  const c = S.ctx;
  c.save(); c.fillStyle = _paperPat; c.fillRect(view[0], view[1], view[2] - view[0], view[3] - view[1]); c.restore();
}
function drawOverlays() {
  const c = S.ctx;
  c.save();
  c.drawImage(_grainFrames[S.boil % 4], 0, 0);
  c.restore();
}
