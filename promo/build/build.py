"""Inline fonts, audio, data and code into one self-contained HTML file."""
import base64, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, BUILD = os.path.join(ROOT, "src"), os.path.join(ROOT, "build")
b64 = lambda p: base64.b64encode(open(p, "rb").read()).decode()
fonts = [("Caveat", "500 700", "caveat.woff2"), ("Caveat Brush", "400", "caveatbrush.woff2"), ("Kalam", "400", "kalam400.woff2"), ("Kalam", "700", "kalam700.woff2")]
css = "\n".join(f"@font-face{{font-family:'{f}';font-weight:{w};font-display:block;src:url(data:font/woff2;base64,{b64(os.path.join(BUILD,'fonts',fn))}) format('woff2');}}" for f, w, fn in fonts)
audio_path = os.path.join(BUILD, "audio", "final_mix.mp3")
audio = f"data:audio/mpeg;base64,{b64(audio_path)}" if os.path.exists(audio_path) else ""
caps_path = os.path.join(BUILD, "captions.json")
caps = json.load(open(caps_path)) if os.path.exists(caps_path) else []
data = f"window.HEAT_DATA={open(os.path.join(SRC,'heat.json')).read()};\nwindow.CAPTIONS={json.dumps(caps)};"
code = "\n".join(open(os.path.join(SRC, f), encoding="utf-8").read() for f in ["engine.js", "characters.js", "scenes1.js", "scenes2.js", "main.js"])
html = open(os.path.join(SRC, "index.html"), encoding="utf-8").read()
html = html.replace("/*FONTS*/", css).replace("/*AUDIO*/", audio).replace("/*DATA*/", data).replace("/*CODE*/", code)
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "inventory-sentinel-promo.html")
open(out, "w", encoding="utf-8").write(html)
print("wrote", out, f"{len(html)/1e6:.2f} MB", "audio" if audio else "(no audio)")
