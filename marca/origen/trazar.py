"""Traza el símbolo MAD del logo (PNG) a SVG en trazos, una capa por color."""
import sys, cv2, numpy as np
src, out, preview = sys.argv[1], sys.argv[2], sys.argv[3]
im = cv2.imread(src)  # BGR
rgb = cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(int)
# zona del símbolo (sin el nombre de debajo)
y0, y1 = 140, 760
sub = rgb[y0:y1]
nonwhite = (sub.min(axis=2) < 200)
ys, xs = np.where(nonwhite)
bx0, bx1, by0, by1 = xs.min()-4, xs.max()+5, ys.min()-4, ys.max()+5
sub = sub[by0:by1, bx0:bx1]
H, W = sub.shape[:2]
pal = {
  'dark':  ((0x23,0x28,0x2E), '#23282E'),
  'taupe': ((0xA9,0x9B,0x8B), '#A99B8B'),
  'light': ((0x9D,0x99,0x96), '#9D9996'),
  'mid':   ((0x80,0x80,0x81), '#808081'),
  'white': ((0xFF,0xFF,0xFF), None),
}
names = list(pal)
cols = np.array([pal[n][0] for n in names])
d = ((sub[:,:,None,:]-cols[None,None,:,:])**2).sum(axis=3)
lab = d.argmin(axis=2)
paths = []
for i, n in enumerate(names):
    color = pal[n][1]
    if not color: continue
    mask = (lab == i).astype(np.uint8)*255
    mask = cv2.medianBlur(mask, 5)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3),np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3,3),np.uint8))
    # ampliar 4x para suavizar y trazar
    big = cv2.resize(mask, (W*4, H*4), interpolation=cv2.INTER_CUBIC)
    big = cv2.GaussianBlur(big, (0,0), 6)
    _, big = cv2.threshold(big, 127, 255, cv2.THRESH_BINARY)
    cs, hier = cv2.findContours(big, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    dd = []
    for c in cs:
        if cv2.contourArea(c) < 400: continue
        a = cv2.approxPolyDP(c, 1.5 if n == "taupe" else 4.0, True).reshape(-1,2) / 4.0
        dd.append('M' + ' '.join(f'{x:.1f} {y:.1f}' for x, y in a) + 'Z')
    if dd:
        paths.append(f'<path fill="{color}" fill-rule="evenodd" d="{"".join(dd)}"/>')
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
       + ''.join(paths) + '</svg>\n')
open(out, 'w').write(svg)
cv2.imwrite(preview, cv2.cvtColor(sub.astype(np.uint8), cv2.COLOR_RGB2BGR))
print(W, H, len(svg))
