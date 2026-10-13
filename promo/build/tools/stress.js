const puppeteer = require('puppeteer-core'); const path = require('path');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', protocolTimeout: 600000 });
  const p = await b.newPage(); await p.setViewport({ width: 1920, height: 1080 });
  await p.goto(require('url').pathToFileURL(path.resolve(process.argv[2])).href + '?export=1');
  await p.waitForFunction('window.__ready === true');
  const r = { bad: [], worst: 0, wt: 0 };
  for (let c = 0; c < 12; c++) {
    const q = await p.evaluate((c) => { window.__m = window.__m || 0; const bad = []; let worst = 0, wt = 0; const slow = []; for (let i = c * 600; i < (c + 1) * 600; i++) { const t = i / 60; const s = performance.now(); try { window.renderAt(t); } catch (e) { bad.push(t.toFixed(3) + ': ' + e.message); } const d = performance.now() - s; if (d > worst) { worst = d; wt = t; } if (d > 60) slow.push(t.toFixed(2) + ':' + d.toFixed(0)); } return { bad, worst, wt, slow }; }, c);
    r.bad.push(...q.bad); (r.slow = r.slow || []).push(...q.slow); if (q.worst > r.worst) { r.worst = q.worst; r.wt = q.wt; }
  }
  r.bad = r.bad.slice(0, 10);
  console.log(JSON.stringify(r)); console.log('heap', await p.evaluate(() => (performance.memory.usedJSHeapSize/1e6).toFixed(0)+'MB')); await b.close();
})();
