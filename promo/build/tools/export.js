// Frame-exact MP4 export: renders every frame in headless Chrome and pipes JPEGs into ffmpeg with the soundtrack.
const puppeteer = require('puppeteer-core'); const path = require('path'); const { spawn } = require('child_process');
const [page, out, ffmpeg, audio, fpsArg] = process.argv.slice(2); const FPS = +(fpsArg || 30);
(async () => {
  const b = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' });
  const p = await b.newPage(); await p.setViewport({ width: 1920, height: 1080 });
  await p.goto(require('url').pathToFileURL(path.resolve(page)).href + '?export=1');
  await p.waitForFunction('window.__ready === true', { timeout: 60000 });
  const dur = await p.evaluate(() => window.DURATION); const N = Math.round(dur * FPS);
  const ff = spawn(ffmpeg, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-i', audio,
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-movflags', '+faststart',
    '-c:a', 'aac', '-b:a', '256k', '-shortest', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now();
  for (let i = 0; i < N; i++) {
    const data = await p.evaluate((t) => { window.renderAt(t); return document.getElementById('stage').toDataURL('image/jpeg', 0.95); }, i / FPS);
    const buf = Buffer.from(data.slice(data.indexOf(',') + 1), 'base64');
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 300 === 0) console.log(`frame ${i}/${N}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r)); await b.close();
  console.log('done', out, ((Date.now() - t0) / 1000).toFixed(0) + 's');
})();
