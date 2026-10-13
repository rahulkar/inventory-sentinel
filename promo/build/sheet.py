import sys, glob, os
from PIL import Image, ImageDraw
files = sorted(glob.glob(sys.argv[1] + "/f_*.jpg"), key=lambda f: float(os.path.basename(f)[2:-4]))
out = sys.argv[2]; n = 9
for s in range(0, len(files), n):
    sheet = Image.new("RGB", (1920, 1080), "black"); d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files[s:s+n]):
        im = Image.open(f).resize((636, 358)); x, y = (i % 3) * 642, (i // 3) * 362
        sheet.paste(im, (x, y)); d.rectangle([x, y, x+70, y+22], fill="black"); d.text((x+4, y+4), os.path.basename(f)[2:-4], fill="yellow")
    sheet.save(f"{out}_{s//n}.jpg", quality=88)
print("sheets", (len(files)+n-1)//n)
