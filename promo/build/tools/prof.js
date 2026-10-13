const puppeteer = require('puppeteer-core'); const path = require('path');
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', protocolTimeout: 600000 });
  const p = await b.newPage(); await p.setViewport({ width: 1920, height: 1080 });
  await p.goto(require('url').pathToFileURL(path.resolve(process.argv[2])).href + '?export=1');
  await p.waitForFunction('window.__ready === true');
  const r = await p.evaluate(() => { const out = []; for (const pass of [1, 2]) for (let t = 88.6; t < 90.2; t += 0.1) { const s = performance.now(); window.renderAt(t); out.push(pass + '@' + t.toFixed(1) + '=' + (performance.now() - s).toFixed(0)); } return out.join(' '); });
  console.log(r); await b.close();
})();
