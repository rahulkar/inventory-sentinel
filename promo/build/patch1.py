import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))


def patch(fn, reps):
    s = open(fn, encoding="utf-8").read()
    for a, b in reps:
        if a not in s and b in s:
            continue
        if a not in s:
            raise SystemExit(f"MISSING in {fn}: {a[:90]}")
        s = s.replace(a, b)
    open(fn, "w", encoding="utf-8").write(s)


patch("engine.js", [
    ("paper: '#f6eedd'", "paper: '#f8f1e1'"),
    ("g.addColorStop(0, dark ? 'rgba(160,120,70,0.035)' : 'rgba(255,255,255,0.05)');",
     "g.addColorStop(0, dark ? 'rgba(160,120,70,0.018)' : 'rgba(255,255,255,0.05)');"),
    ("    c.globalAlpha = 0.5 * prog;\n    c.fillStyle = _grain;",
     "    c.globalAlpha = (o.grainA === undefined ? 0.3 : o.grainA) * prog;\n    c.fillStyle = _grain;"),
    ("vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(0.7, 'rgba(70,45,20,0.10)'); vg.addColorStop(1, 'rgba(50,30,10,0.38)');",
     "vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(0.72, 'rgba(70,45,20,0.06)'); vg.addColorStop(1, 'rgba(50,30,10,0.30)');"),
    ("    if (o.stroke) { c.lineWidth = o.stroke; c.strokeStyle = o.strokeColor || PAL.paper; c.lineJoin = 'round'; c.strokeText(ch, 0, 0); }\n    c.fillText(ch, 0, 0);",
     "    if (ch === '\\u00a3' && o.font === 'brush') c.font = `700 ${(o.size || 40) * 0.92}px ${FONT.body}`;\n"
     "    if (o.stroke) { c.lineWidth = o.stroke; c.strokeStyle = o.strokeColor || PAL.paper; c.lineJoin = 'round'; c.strokeText(ch, 0, 0); }\n"
     "    c.fillText(ch, 0, 0);\n    if (ch === '\\u00a3') c.font = font;"),
    ("  if (o.tint) fillPoly(rrPts(x, y, w, h, r, 0), o.tint, { alpha: (o.tintA || 0.5) * prog, edge: false });",
     "  if (o.tint) fillPoly(rrPts(x, y, w, h, r, 0), o.tint, { alpha: (o.tintA || 0.5) * prog, edge: false, grainA: 0.12 });"),
    ("    fillPoly(ellPts(cx, cy, r, r * 0.9), PAL.greyL, { alpha: 0.9 * (1 - k), edge: false, grain: false, seed: i * 3 });\n    stroke(ellPts(cx, cy, r, r * 0.9), { w: 2.2, color: PAL.inkSoft, alpha: 0.8 * (1 - k), double: false, seed: i * 5 });",
     "    fillSolid(ellPts(cx, cy, r, r * 0.9), PAL.white, { alpha: 0.95 * (1 - k * k), seed: i * 3 });\n    stroke(ellPts(cx, cy, r, r * 0.9), { w: 3, color: PAL.inkSoft, alpha: 1 - k * k, double: false, seed: i * 5 });"),
    ("    const d = 26 * s * g + 6, r = (16 + (i % 3) * 7) * s * (1 - k * 0.5);",
     "    const d = 34 * s * g + 8, r = (20 + (i % 3) * 8) * s * (1 - k * 0.5);"),
])

patch("characters.js", [
    ("  push(-104, -150, 1, -wl);", "  push(-104, -150, 1, wl);"),
    ("  push(104, -150, 1, wr);", "  push(104, -150, 1, -wr);"),
    ("  fillPoly(ellPts(-14, -150, 44, 40), PAL.brownL, { seed: 5 });\n  stroke(ellPts(-14, -150, 44, 40), { w: 3.2, seed: 6 });\n  stroke([[8, -116], [22, -108]], { w: 3.5, seed: 7 });\n  text('£', -16, -136, { size: 44, font: 'brush', align: 'center', color: PAL.brown });",
     "  fillPoly(ellPts(-46, -142, 40, 38), PAL.brownL, { seed: 5 });\n  stroke(ellPts(-46, -142, 40, 38), { w: 3.2, seed: 6 });\n  stroke([[-18, -112], [-4, -104]], { w: 3.5, seed: 7 });\n  text('\\u00a3', -48, -128, { size: 42, font: 'body', weight: 700, align: 'center', color: PAL.brown });"),
    ("  stroke([[24, -96], [14, -126], [2, -128]], { w: 5, seed: 10 });",
     "  stroke([[22, -96], [0, -118], [-16, -112]], { w: 5, seed: 10 });"),
])

patch("scenes1.js", [
    ("  push(0, -118 * sh, 1 - 0.22 * sh);\n  shopFront(t);", "  push(0, 44 - 150 * sh, 1 - 0.22 * sh);\n  shopFront(t);"),
    ("    poof(it.x, it.y - 40, 1, it.vanish, t);\n    return;",
     "    poof(it.x, it.y - 40, 1.25, it.vanish, t);\n"
     "    if (it.word) { const wk = seg(t, it.vanish, it.vanish + 0.9); if (wk < 1) text('poof!', it.x + 40, it.y - 100 - wk * 40, { size: 44, font: 'hand', weight: 700, color: PAL.inkSoft, alpha: 1 - wk * wk, align: 'center' }); }\n"
     "    return;"),
    ("  gone.forEach((idx, j) => { items[idx].vanish = CUE.vanish + j * 0.36; });",
     "  gone.forEach((idx, j) => { items[idx].vanish = CUE.vanish + j * 0.36; items[idx].word = j === 0 || j === 3; });"),
    ("    if (i === 0) raccoon(-20, 78, 0.72, { phase: (t - t0) * 1.7 });",
     "    if (i === 0) raccoon(0, 86, 0.86, { phase: (t - t0) * 1.7 });"),
    ("    person(x, 520, 0.72, { hat: 'hard',", "    person(x, 492, 0.78, { hat: 'hard',"),
    ("    push(-330, -170, uk, -0.015);", "    push(-330, -205, uk, -0.015);"),
    ("    const bx = 1520 + i * 250, by = 420;\n    bot(bx, by, 0.95,", "    const bx = 1500 + i * 275, by = 410;\n    bot(bx, by, 1.2,"),
    ("    text(name, bx, by + 58,", "    text(name, bx, by + 72,"),
    ("  fillSolid(ellPts(96, -26, 16, 10), PAL.ink, { alpha: 0.85 });",
     "  fillSolid(parsePath('M80,-34 L90,-18 L98,-32 L106,-16 L114,-28 L112,-8 L84,-10 Z')[0], PAL.ink, { alpha: 0.85 });"),
    ("  text('£', 0, -60, { size: 150, font: 'brush', align: 'center', color: PAL.brown });",
     "  text('\\u00a3', 0, -66, { size: 130, font: 'body', weight: 700, align: 'center', color: PAL.brown });"),
])

# ---- Scene B: bigger, clearer layout ----
s = open("scenes1.js", encoding="utf-8").read()
a = s.index("function sceneB(t) {")
b = s.index("/* ===================== C: meet Sentinel")
newB = r'''function sceneB(t) {
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
  if (kb > 0) { push(L - 40, 400, kb); moneyBag(0, 0, 1.12, t); pop(); }
  for (let i = 0; i < 14; i++) {
    const t0 = CUE.s2 + 0.3 + i * 0.42;
    const dt = t - t0;
    if (dt < 0) continue;
    const hx = L - 40 + 112, hy = 380;
    let x, y, a = 1;
    if (dt < 0.35) { x = hx + dt * 60; y = hy + 0.5 * 2400 * dt * dt; }
    else { const r = dt - 0.35; x = hx + 21 + r * (150 + (i % 3) * 45); y = hy + 147 - Math.abs(Math.sin(r * 9)) * 18 * Math.exp(-r * 3); a = 1 - seg(r, 1.4, 2.2); }
    if (a > 0) coin(x, Math.min(y, 512), 22, { alpha: a });
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
  text('…if at all', 770, -50, { size: 58, font: 'hand', weight: 700, align: 'center', color: PAL.coral, prog: ez(t, CUE.ifatall, 0.5, E.lin) });
}

'''
s = s[:a] + newB + s[b:]
open("scenes1.js", "w", encoding="utf-8").write(s)
print("patch1 ok")
