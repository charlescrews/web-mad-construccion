# Genera static/img/zona-de-trabajo.svg: mapa orientativo (Loja, Granada, Málaga y costa), proyección simple lon/lat.
import sys, math
LON0, LON1, LAT0, LAT1 = -4.78, -3.42, 36.48, 37.42
W = 640
k = math.cos(math.radians(37.0))
H = round(W * (LAT1 - LAT0) / ((LON1 - LON0) * k))
def P(lon, lat): return ((lon - LON0) / (LON1 - LON0) * W, (LAT1 - lat) / (LAT1 - LAT0) * H)
costa = [(-4.80,36.50),(-4.62,36.54),(-4.57,36.59),(-4.50,36.62),(-4.42,36.715),(-4.34,36.72),(-4.28,36.715),(-4.09,36.74),
         (-3.88,36.745),(-3.74,36.735),(-3.69,36.73),(-3.59,36.745),(-3.52,36.72),(-3.40,36.70)]
pts = [P(*c) for c in costa]
mar = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L{W+10},{H+10} L-10,{H+10} Z"
linea = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
loja, gra, mal = P(-4.152, 37.168), P(-3.598, 37.177), P(-4.421, 36.721)
# zona: contorno suave que envuelve las tres ciudades y sus alrededores
zona_pts = [P(-4.62, 37.30), P(-4.10, 37.36), P(-3.58, 37.33), P(-3.48, 37.17), P(-3.62, 37.02), P(-3.98, 36.90),
            P(-4.20, 36.78), P(-4.36, 36.68), P(-4.56, 36.66), P(-4.66, 36.86), P(-4.72, 37.08)]
def suave(p):
    n = len(p); d = ""
    for i in range(n):
        p0, p1, p2 = p[i - 1], p[i], p[(i + 1) % n]
        a = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2); b = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        d += (f"M{a[0]:.1f},{a[1]:.1f}" if i == 0 else "") + f" Q{p1[0]:.1f},{p1[1]:.1f} {b[0]:.1f},{b[1]:.1f}"
    return d + " Z"
def diamante(cx, cy, s):  # el símbolo del logo: cuatro piezas en rombo
    h = s / 2; g = s * 0.09
    def pieza(dx, dy, col):
        x, y = cx + dx, cy + dy
        return f'<path d="M{x:.1f},{y-h+g:.1f} L{x+h-g:.1f},{y:.1f} L{x:.1f},{y+h-g:.1f} L{x-h+g:.1f},{y:.1f} Z" fill="{col}"/>'
    return (pieza(0, -h, "#A99B8B") + pieza(-h, 0, "#D9D5D1") + pieza(h, 0, "#B4AEA7") + pieza(0, h, "#B4AEA7"))
F = "font-family=\"Montserrat, 'Segoe UI', system-ui, sans-serif\""
def etiqueta(x, y, t, anchor="start", size=20, peso=700, col="#1F2328"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" {F} font-size="{size}" font-weight="{peso}" fill="{col}" text-anchor="{anchor}" '
            f'stroke="#F7F5F2" stroke-width="5" stroke-linejoin="round" paint-order="stroke">{t}</text>')
def km(a, b, t, dx=0, dy=0):
    mx, my = (a[0] + b[0]) / 2 + dx, (a[1] + b[1]) / 2 + dy
    return etiqueta(mx, my, t, "middle", 15, 600, "#4A4F55")
lang = sys.argv[1] if len(sys.argv) > 1 else "es"
mar_t = "Mar Mediterráneo" if lang == "es" else "Mediterranean Sea"
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t">
<title id="t">{"Mapa orientativo: Loja, Granada, Málaga y alrededores" if lang == "es" else "Approximate map: Loja, Granada, Málaga and nearby"}</title>
<rect width="{W}" height="{H}" fill="#F7F5F2"/>
<path d="{suave(zona_pts)}" fill="#A99B8B" fill-opacity=".22" stroke="#A99B8B" stroke-width="2" stroke-dasharray="7 6"/>
<path d="{mar}" fill="#DCE1E3"/>
<path d="{linea}" fill="none" stroke="#C3CBCF" stroke-width="2"/>
<path d="M{loja[0]:.1f},{loja[1]:.1f} L{gra[0]:.1f},{gra[1]:.1f} M{loja[0]:.1f},{loja[1]:.1f} L{mal[0]:.1f},{mal[1]:.1f}" stroke="#23282E" stroke-width="2.5" stroke-dasharray="2 7" stroke-linecap="round" fill="none"/>
{km(loja, gra, "≈ 55 km", 0, -12)}
{km(loja, mal, "≈ 70 km", -38, 0)}
<circle cx="{gra[0]:.1f}" cy="{gra[1]:.1f}" r="8" fill="#23282E"/>
<circle cx="{mal[0]:.1f}" cy="{mal[1]:.1f}" r="8" fill="#23282E"/>
<circle cx="{loja[0]:.1f}" cy="{loja[1]:.1f}" r="34" fill="#23282E"/>
{diamante(loja[0], loja[1], 26)}
{etiqueta(loja[0], loja[1] - 46, "Loja", "middle", 26, 800)}
{etiqueta(gra[0], gra[1] - 18, "Granada", "middle", 22)}
{etiqueta(mal[0] + 16, mal[1] - 12, "Málaga", "start", 22)}
{etiqueta(W - 24, H - 26, mar_t, "end", 15, 500, "#5C666B")}
</svg>
'''
open(sys.argv[2], "w", encoding="utf-8").write(svg)
print(W, H)
