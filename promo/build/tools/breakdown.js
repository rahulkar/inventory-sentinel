const puppeteer = require('puppeteer-core'); const path = require('path');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', protocolTimeout: 600000 });
  const p = await b.newPage(); await p.setViewport({ width: 1920, height: 1080 });
  await p.goto(require('url').pathToFileURL(path.resolve(process.argv[2])).href + '?export=1');
  await p.waitForFunction('window.__ready === true');
  const r = await p.evaluate(() => {
    const cv = document.getElementById('stage');
    const time = (t, n = 20) => { cv.getContext('2d').getImageData(0, 0, 1, 1); const s = performance.now(); for (let i = 0; i < n; i++) { window.renderAt(t + i * 0.001); cv.getContext('2d').getImageData(0, 0, 1, 1); } return ((performance.now() - s) / n).toFixed(1); };
    const out = {};
    for (const t of [3, 86, 89.4]) {
      out['full@' + t] = time(t);
      const o1 = window.drawOverlays; window.drawOverlays = () => {}; out['noOverlay@' + t] = time(t); window.drawOverlays = o1;
      const o2 = window.drawPaper; window.drawPaper = () => {}; out['noPaper@' + t] = time(t); window.drawPaper = o2;
      const o3 = window.fillPoly; window.fillPoly = () => {}; out['noFillPoly@' + t] = time(t); window.fillPoly = o3;
      const o4 = window.text; window.text = () => 0; out['noText@' + t] = time(t); window.text = o4;
    }
    return out;
  });
  console.log(JSON.stringify(r, null, 0)); await b.close();
})();
