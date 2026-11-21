"""Imágenes provisionales (SVG) con dibujo de baldosas y el rótulo «Foto pendiente»."""
import sys, math
out = sys.argv[1]
INK, TAUPE, G1, G2, PAPER = "#23282E", "#B9AD9F", "#DCD7D1", "#CDC7C0", "#F1EDE8"

def label(w, h, txt):
    # Etiqueta discreta abajo a la izquierda: se entiende que falta la foto sin que domine la imagen.
    bw, bh, m = 330, 64, 36
    x, y = (w - bw) / 2, h - bh - m  # centrada abajo: sobrevive a los recortes 4:3 y 3:2
    return (f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="32" fill="#fff" opacity=".92"/>'
            f'<circle cx="{x + 34}" cy="{y + bh / 2}" r="9" fill="none" stroke="{INK}" stroke-width="3"/>'
            f'<text x="{x + 58}" y="{y + 42}" font-family="system-ui,sans-serif" font-size="28" font-weight="600" fill="{INK}">{txt}</text>')


def rombos(w, h, s=70):
    r, out = [], []
    for j in range(-1, int(h/(s/2))+2):
        for i in range(-1, int(w/s)+2):
            cx = i*s + (s/2 if j % 2 else 0); cy = j*s/2
            c = [G1, G2, TAUPE, G1, G2][(i*3 + j*2) % 5]
            d = s/2 - 3
            out.append(f'<path d="M{cx} {cy-d}L{cx+d} {cy}L{cx} {cy+d}L{cx-d} {cy}Z" fill="{c}"/>')
    return ''.join(out)

def cuadricula(w, h, s=80):
    out = []
    for j in range(0, int(h/s)+1):
        for i in range(0, int(w/s)+1):
            c = [G1, G2, G1, PAPER][(i + 2*j) % 4]
            out.append(f'<rect x="{i*s+3}" y="{j*s+3}" width="{s-6}" height="{s-6}" fill="{c}"/>')
    return ''.join(out)

def espiga(w, h, L=90, t=30):
    out = []
    for j in range(-4, int(h/t)+int(w/(2*t))+8):
        for i in range(-2, int(w/(2*t))+4):
            x, y = i*2*t, j*t - i*t
            c = [G1, G2, TAUPE][(i+j) % 3]
            out.append(f'<rect x="{x+2}" y="{y+2}" width="{L-4}" height="{t-4}" fill="{c}"/>')
            out.append(f'<rect x="{x+L-t+2}" y="{y+t+2}" width="{t-4}" height="{L-4}" fill="{[G2, G1, G1][(i+j) % 3]}"/>')
    return ''.join(out)

def gran_formato(w, h, sw=240, sh=120):
    out = []
    for j in range(0, int(h/sh)+1):
        off = (sw/2) if j % 2 else 0
        for i in range(-1, int(w/sw)+2):
            c = TAUPE if (i*7 + j*3) % 11 == 0 else [G1, G2][(i+j) % 2]
            out.append(f'<rect x="{i*sw+off+2}" y="{j*sh+2}" width="{sw-4}" height="{sh-4}" fill="{c}"/>')
    return ''.join(out)

def svg(name, w, h, pattern):
    s = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
         f'<rect width="{w}" height="{h}" fill="{PAPER}"/>{pattern(w, h)}{label(w, h, "Foto pendiente")}</svg>\n')
    open(f'{out}/{name}.svg', 'w').write(s)

svg('portada-provisional', 1200, 900, gran_formato)
svg('retrato-provisional', 1200, 800, cuadricula)
svg('trabajo-alicatado-provisional', 1200, 800, cuadricula)
svg('trabajo-solado-provisional', 1200, 800, espiga)
svg('trabajo-reforma-provisional', 1200, 800, gran_formato)
svg('trabajo-acabados-provisional', 1200, 800, rombos)
print('ok')

# Fondo de la portada «banda» (versión B): solo el dibujo, sin rótulo, porque va debajo del texto; el alt y el nombre siguen
# bloqueando la publicación (check.py --release).
def svg_sin_rotulo(name, w, h, pattern):
    s = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
         f'<rect width="{w}" height="{h}" fill="{PAPER}"/>{pattern(w, h)}</svg>\n')
    open(f'{out}/{name}.svg', 'w').write(s)

svg_sin_rotulo('portada-banda-provisional', 1600, 900, rombos)
