"""Logo apilado: símbolo a la izquierda, nombre y «CONSTRUCCIÓN» a la derecha (todo en trazos)."""
import re, sys
sym, l1, l2, out = sys.argv[1:5]
def parse(p):
    s = open(p).read()
    w, h = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', s).groups())
    inner = re.sub(r'^<svg[^>]*>|</svg>\s*$', '', s.strip())
    inner = re.sub(r'<title>.*?</title>', '', inner)
    return w, h, inner
sw, sh, si = parse(sym); w1, h1, i1 = parse(l1); w2, h2, i2 = parse(l2)
H = 150.0; s0 = H / sh; x = sw * s0 + 18; TW = 500.0
s1, s2 = TW / w1, TW / w2
th1, th2, gap = h1 * s1, h2 * s2, 12
y1 = (H - (th1 + gap + th2)) / 2; y2 = y1 + th1 + gap
W = x + TW
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.2f} {H:.2f}" width="{W:.0f}" height="{H:.0f}" role="img" '
       f'aria-label="Miguel Ángel Díaz Construcción"><title>Miguel Ángel Díaz Construcción</title>'
       f'<g transform="scale({s0:.5f})">{si}</g>'
       f'<g transform="translate({x:.2f} {y1:.2f}) scale({s1:.5f})">{i1}</g>'
       f'<g transform="translate({x:.2f} {y2:.2f}) scale({s2:.5f})">{i2}</g></svg>\n')
open(out, 'w').write(svg); print(f'{W:.0f}x{H:.0f} ratio {W/H:.2f}')
