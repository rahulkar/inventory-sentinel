const puppeteer = require('puppeteer-core'); const path = require('path');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', args: ['--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage(); const errs = [];
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.setViewport({ width: 1280, height: 720 });
  await p.goto(require('url').pathToFileURL(path.resolve(process.argv[2])).href);
  await new Promise(r => setTimeout(r, 1500));
  await p.screenshot({ path: '../qa/play_start.jpg', type: 'jpeg' });
  await p.click('#start');
  const t0 = Date.now(); await new Promise(r => setTimeout(r, 4000));
  const st = await p.evaluate(() => ({ t: document.getElementById('track').currentTime, dur: document.getElementById('track').duration, paused: document.getElementById('track').paused }));
  console.log('after', (Date.now()-t0)/1000, 's wall:', JSON.stringify(st));
  await p.evaluate(() => { document.getElementById('track').currentTime = 76; document.getElementById('cc').click(); });
  await new Promise(r => setTimeout(r, 1200));
  // frame-rate probe
  const fps = await p.evaluate(() => new Promise(res => { let n = 0; const s = performance.now(); const f = () => { n++; if (performance.now() - s < 2000) requestAnimationFrame(f); else res(n / 2); }; requestAnimationFrame(f); }));
  console.log('rAF fps ~', fps);
  await p.screenshot({ path: '../qa/play_cc.jpg', type: 'jpeg' });
  console.log('errors:', errs.length ? errs : 'none');
  await b.close();
})();
