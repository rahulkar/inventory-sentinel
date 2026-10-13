const puppeteer = require('puppeteer-core'); const path = require('path');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', protocolTimeout: 600000, args: ['--autoplay-policy=no-user-gesture-required','--enable-gpu','--use-angle=d3d11','--ignore-gpu-blocklist','--enable-gpu-rasterization'] });
  const p = await b.newPage(); await p.setViewport({ width: 1920, height: 1080 });
  await p.goto(require('url').pathToFileURL(path.resolve(process.argv[2])).href);
  await new Promise(r => setTimeout(r, 1500)); await p.click('#start');
  for (const start of [70, 84, 100, 3]) {
    await p.evaluate((s) => { document.getElementById('track').currentTime = s; }, start);
    const r = await p.evaluate(() => new Promise(res => { const gaps = []; let last = performance.now(); const s = last; const f = () => { const n = performance.now(); gaps.push(n - last); last = n; if (n - s < 6000) requestAnimationFrame(f); else { gaps.sort((a, b) => a - b); res({ fps: (gaps.length / 6).toFixed(1), p95: gaps[Math.floor(gaps.length * 0.95)].toFixed(0), max: gaps[gaps.length - 1].toFixed(0) }); } }; requestAnimationFrame(f); }));
    console.log('from', start, JSON.stringify(r));
  }
  await b.close();
})();
