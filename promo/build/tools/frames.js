// usage: node frames.js page.html outdir t1 t2 ...  -> PNG per time
const puppeteer = require('puppeteer-core');
const path = require('path'), fs = require('fs');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
(async () => {
  const [page, outdir, ...ts] = process.argv.slice(2);
  fs.mkdirSync(outdir, { recursive: true });
  const b = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--disable-gpu-vsync', '--force-device-scale-factor=1'] });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(String(e)));
  p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
  await p.setViewport({ width: 1920, height: 1080 });
  await p.goto(require('url').pathToFileURL(path.resolve(page)).href + '?export=1');
  await p.waitForFunction('window.__ready === true', { timeout: 60000 }).catch(() => {});
  if (errs.length) console.log('ERRORS:', errs.join('\n'));
  for (const t of ts) {
    const t0 = Date.now();
    await p.evaluate((t) => window.renderAt(t), +t);
    const ms = Date.now() - t0;
    const data = await p.evaluate(() => document.getElementById('stage').toDataURL('image/jpeg', 0.85));
    fs.writeFileSync(path.join(outdir, `f_${String(t).padStart(6, '0')}.jpg`), Buffer.from(data.split(',')[1], 'base64'));
    console.log('t', t, 'render', ms, 'ms');
  }
  if (errs.length) console.log('ERRORS:', errs.join('\n'));
  await b.close();
})();
