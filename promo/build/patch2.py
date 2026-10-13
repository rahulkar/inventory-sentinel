import os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
POUND_ESC = "\\u00a3"  # the JS source spells the pound sign as an escape


def patch(fn, reps):
    s = open(fn, encoding="utf-8").read()
    for a, b in reps:
        if a not in s:
            raise SystemExit(f"MISSING in {fn}: {a[:90]}")
        s = s.replace(a, b, 1)
    open(fn, "w", encoding="utf-8").write(s)


patch("engine.js", [
    ('''function charPos(c, font, str) {
  const key = font + '|' + str;
  let hit = _measure.get(key);
  if (hit) return hit;
  const chars = [...str], xs = [];
  let s = '';
  for (const ch of chars) { xs.push(c.measureText(s).width); s += ch; }
  hit = { chars, xs, w: c.measureText(str).width };
  _measure.set(key, hit);
  return hit;
}''', '''function charPos(c, font, str, subFont) {
  const key = font + '|' + (subFont || '') + '|' + str;
  let hit = _measure.get(key);
  if (hit) return hit;
  const chars = [...str], xs = [];
  let s = '', x = 0;
  for (const ch of chars) {
    xs.push(x);
    let adv;
    if (subFont && ch === 'POUND') { c.font = subFont; adv = c.measureText(ch).width + 2; c.font = font; }
    else adv = c.measureText(s + ch).width - c.measureText(s).width;
    x += adv; s += ch;
  }
  hit = { chars, xs, w: x };
  _measure.set(key, hit);
  return hit;
}'''.replace("POUND", POUND_ESC)),
    ('''  const m = charPos(c, font, str);
  const ax =''', '''  const sub = o.font === 'brush' && str.includes('POUND') ? `700 ${(o.size || 40) * 0.92}px ${FONT.body}` : null;
  const m = charPos(c, font, str, sub);
  const ax ='''.replace("POUND", POUND_ESC)),
    ("    if (ch === 'POUND' && o.font === 'brush') c.font = `700 ${(o.size || 40) * 0.92}px ${FONT.body}`;".replace("POUND", POUND_ESC),
     "    if (sub && ch === 'POUND') c.font = sub;".replace("POUND", POUND_ESC)),
])

patch("scenes1.js", [
    ("  fillSolid(parsePath('M80,-34 L90,-18 L98,-32 L106,-16 L114,-28 L112,-8 L84,-10 Z')[0], PAL.ink, { alpha: 0.85 });\n  stroke([[74, -48], [84, -40]], { w: 2.5 }); stroke([[110, -46], [104, -38]], { w: 2.5 });",
     "  fillSolid(ellPts(98, -24, 15, 9), PAL.ink, { alpha: 0.85 });"),
    ("  if (kb > 0) { push(L - 40, 400, kb); moneyBag(0, 0, 1.12, t); pop(); }", "  if (kb > 0) { push(L - 40, 360, kb); moneyBag(0, 0, 1.12, t); pop(); }"),
    ("    const hx = L - 40 + 112, hy = 380;", "    const hx = L - 40 + 112, hy = 336;"),
    ("    if (a > 0) coin(x, Math.min(y, 512), 22, { alpha: a });", "    if (a > 0) coin(x, Math.min(y, 484), 22, { alpha: a });"),
    ("if at all', 770, -50,", "if at all', 700, -50,"),
    ("    const bx = 1500 + i * 275, by = 410;", "    const bx = 1480 + i * 275, by = 380;"),
])

patch("scenes2.js", [
    ("  const tk = ez(t, CUE.compete - 0.3, 0.8);\n",
     "  const tk = ez(t, CUE.compete - 0.3, 0.8);\n"
     "  for (let i = 0; i < RACERS.length; i++) fillPoly(rrPts(-890, ly0 - 40 + i * laneH + 4, 1150, laneH - 8, 8, 0), i % 2 ? PAL.mustL : PAL.sky, { alpha: 0.35 * tk, edge: false, seed: 300 + i, grainA: 0.1 });\n"),
])
print("patch2 ok")
