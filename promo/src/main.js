/* Camera, scene graph, player UI and export hooks. */
'use strict';

const CAM = [
  [0, 0, 26, 1.0], [6.3, 0, 26, 1.035], [12.05, 0, 0, 1.0], [12.85, 2400, 0, 1.0],
  [18.9, 2400, 0, 1.0], [19.6, 2400, 1500, 1.0],
  [29.6, 2400, 1500, 1.0], [30.35, 4800, 1500, 1.0],
  [43.4, 4800, 1500, 1.0], [44.15, 6100, 1500, 1.0],
  [49.2, 6100, 1500, 1.0], [49.95, 6100, 3000, 1.0],
  [58.9, 6100, 3000, 1.0], [59.65, 6100, 4150, 1.0],
  [68.55, 6100, 4150, 1.0], [69.3, 8600, 4150, 1.0],
  [71.55, 8600, 4150, 1.0], [72.7, 8600, 4150 + LAP_Y - 514 + 239, DZ],
  [88.8, 8600, 4150 + LAP_Y - 514 + 239, DZ], [89.95, 8600, 5400, 1.0],
  [104.3, 8600, 5400, 1.0], [105.05, 6100, 5400, 1.0],
  [108.9, 6100, 5400, 1.0], [110.2, 6100, 5350, 0.9], [130, 6100, 5350, 0.9],
];
function camAt(t) {
  let i = 0;
  while (i < CAM.length - 2 && CAM[i + 1][0] <= t) i++;
  const a = CAM[i], b = CAM[i + 1];
  const k = E.inOut(seg(t, a[0], b[0]));
  const z = a[3] * Math.pow(b[3] / a[3], k);
  // keep the zoom focus stable: interpolate the position in "screen units"
  const kz = a[3] === b[3] ? k : (1 / z - 1 / a[3]) / (1 / b[3] - 1 / a[3]);
  return { x: lerp(a[1], b[1], kz), y: lerp(a[2], b[2], kz), z };
}
const SCENES = [
  { pos: POS.A, t0: -1, draw: sceneA, r: [-1000, -600, 1000, 600] },
  { pos: POS.B, t0: 11.6, draw: sceneB, r: [-1000, -600, 1000, 600] },
  { pos: POS.C, t0: 18.6, draw: sceneC, r: [-1000, -900, 1100, 640] },
  { pos: POS.D, t0: 29.2, draw: sceneD, r: [-1000, -600, 2350, 600] },
  { pos: POS.E, t0: 48.9, draw: sceneE, r: [-1000, -700, 1000, 600] },
  { pos: POS.E2, t0: 58.6, draw: sceneE2, r: [-1000, -600, 1000, 600] },
  { pos: POS.F, t0: 68.3, draw: sceneF, r: [-1000, -600, 1000, 600] },
  { pos: POS.G, t0: 88.6, draw: sceneG, r: [-1000, -650, 1000, 650] },
  { pos: POS.H, t0: 103.9, draw: sceneH, r: [-1000, -600, 1000, 640] },
];

function render(t) {
  const c = S.ctx;
  S.t = t;
  S.boil = Math.floor(t * BOIL_FPS);
  S.ls = 1;
  c.setTransform(S.q, 0, 0, S.q, 0, 0);
  c.globalAlpha = 1;
  c.globalCompositeOperation = 'source-over';
  const cam = camAt(t);
  const dx = Math.sin(t * 0.43) * 5 + Math.sin(t * 0.17 + 2) * 4, dy = Math.sin(t * 0.31 + 1) * 4;
  const rot = Math.sin(t * 0.23) * 0.0025;
  c.translate(W / 2, H / 2);
  c.rotate(rot);
  c.scale(cam.z, cam.z);
  c.translate(-cam.x + dx / cam.z, -cam.y + dy / cam.z);
  const hw = W / 2 / cam.z + 80, hh = H / 2 / cam.z + 80;
  const view = [cam.x - hw, cam.y - hh, cam.x + hw, cam.y + hh];
  drawPaper(view);
  for (const s of SCENES) {
    if (t < s.t0) continue;
    const x0 = s.pos[0] + s.r[0], y0 = s.pos[1] + s.r[1], x1 = s.pos[0] + s.r[2], y1 = s.pos[1] + s.r[3];
    if (x1 < view[0] || x0 > view[2] || y1 < view[1] || y0 > view[3]) continue;
    c.save(); c.translate(s.pos[0], s.pos[1]);
    s.draw(t);
    c.restore();
  }
  c.setTransform(S.q, 0, 0, S.q, 0, 0);
  speedLines(t);
  finale(t);
  drawOverlays();
  // fade in / out
  const fin = 1 - seg(t, 0, 0.6), fout = seg(t, CUE.END - 0.9, CUE.END - 0.1);
  const f = Math.max(fin, fout);
  if (f > 0) { c.fillStyle = `rgba(16,12,10,${f})`; c.fillRect(0, 0, W, H); }
}
function speedLines(t) {
  const a = camAt(t - 0.02), b = camAt(t + 0.02);
  const vx = (b.x - a.x) / 0.04 * a.z, vy = (b.y - a.y) / 0.04 * a.z;
  const v = Math.hypot(vx, vy);
  if (v < 1200) return;
  const k = clamp((v - 1200) / 3000);
  const ux = vx / v, uy = vy / v, nx = -uy, ny = ux;
  const r = rng(S.boil * 7 + 1);
  for (let i = 0; i < 14; i++) {
    const o = (r() - 0.5) * 1300, along = (r() - 0.5) * 1500, L = 200 + r() * 500;
    const cx = W / 2 + nx * o + ux * along, cy = H / 2 + ny * o + uy * along;
    stroke([[cx - ux * L / 2, cy - uy * L / 2], [cx + ux * L / 2, cy + uy * L / 2]], { w: 3, color: PAL.inkSoft, alpha: 0.35 * k, double: false, seed: i });
  }
}

/* ---------------- player ---------------- */
const params = new URLSearchParams(location.search);
const EXPORT = params.has('export');
const canvas = document.getElementById('stage');
S.q = 1;
canvas.width = W; canvas.height = H;
S.ctx = canvas.getContext('2d');
/** live playback only: lower the internal resolution if this device cannot keep up */
function setQuality(q) { S.q = q; canvas.width = Math.round(W * q); canvas.height = Math.round(H * q); }
const audio = document.getElementById('track');
let captionsOn = params.has('cc');

async function boot() {
  await Promise.all([
    document.fonts.load('400 40px "Caveat Brush"'), document.fonts.load('700 40px "Caveat"'), document.fonts.load('500 40px "Caveat"'),
    document.fonts.load('400 40px "Kalam"'), document.fonts.load('700 40px "Kalam"'),
  ]);
  await document.fonts.ready;
  makeTextures();
  window.renderAt = (t) => { render(t); return true; };
  window.DURATION = CUE.END;
  window.__ready = true;
  if (EXPORT) { document.body.classList.add('export'); render(0); return; }
  setupUI();
}

function fit() {
  const s = Math.min(innerWidth / W, innerHeight / H);
  canvas.style.width = W * s + 'px'; canvas.style.height = H * s + 'px';
}
function setupUI() {
  addEventListener('resize', fit); fit();
  const ui = document.getElementById('ui'), bar = document.getElementById('bar'), start = document.getElementById('start');
  const playBtn = document.getElementById('play'), scrub = document.getElementById('scrub'), time = document.getElementById('time');
  const ccBtn = document.getElementById('cc'), fsBtn = document.getElementById('fs'), cap = document.getElementById('caption');
  scrub.max = CUE.END;
  let scrubbing = false, hideT = 0;
  render(CUE.s9 + 6.5);
  const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const begin = () => { start.classList.add('gone'); audio.play(); };
  start.addEventListener('click', begin);
  playBtn.addEventListener('click', () => (audio.paused ? audio.play() : audio.pause()));
  audio.addEventListener('play', () => (playBtn.textContent = '❚❚'));
  audio.addEventListener('pause', () => (playBtn.textContent = '▶'));
  audio.addEventListener('ended', () => { playBtn.textContent = '↻'; ui.classList.add('show'); });
  scrub.addEventListener('input', () => { scrubbing = true; audio.currentTime = +scrub.value; render(+scrub.value); });
  scrub.addEventListener('change', () => (scrubbing = false));
  ccBtn.addEventListener('click', () => { captionsOn = !captionsOn; ccBtn.classList.toggle('on', captionsOn); });
  ccBtn.classList.toggle('on', captionsOn);
  fsBtn.addEventListener('click', () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()));
  addEventListener('keydown', (e) => {
    if (e.code === 'Space') { e.preventDefault(); if (!start.classList.contains('gone')) begin(); else audio.paused ? audio.play() : audio.pause(); }
    if (e.key === 'f') fsBtn.click();
    if (e.key === 'c') ccBtn.click();
    if (e.key === 'ArrowRight') audio.currentTime = Math.min(CUE.END, audio.currentTime + 5);
    if (e.key === 'ArrowLeft') audio.currentTime = Math.max(0, audio.currentTime - 5);
  });
  addEventListener('mousemove', () => { ui.classList.add('show'); clearTimeout(hideT); hideT = setTimeout(() => !audio.paused && ui.classList.remove('show'), 2200); });
  let last = performance.now(), ema = 16, slowFor = 0;
  const loop = () => {
    const now = performance.now(), dt = now - last; last = now;
    if (!audio.paused && dt < 500) {
      ema = ema * 0.9 + dt * 0.1;
      slowFor = ema > 36 ? slowFor + dt : 0;
      if (slowFor > 1500 && S.q > 0.67) { setQuality(S.q > 0.8 ? 0.75 : 0.6667); slowFor = 0; ema = 16; }
    }
    if (start.classList.contains('gone')) {
      const t = Math.min(audio.currentTime, CUE.END);
      render(t);
      if (!scrubbing) scrub.value = t;
      time.textContent = `${fmt(t)} / ${fmt(CUE.END)}`;
      const c = captionsOn ? (window.CAPTIONS || []).find((x) => t >= x[0] && t <= x[1]) : null;
      cap.textContent = c ? c[2] : '';
      cap.style.opacity = c ? 1 : 0;
    }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
}
boot();
