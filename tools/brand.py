#!/usr/bin/env python3
"""Comprueba que los colores de site.json > brand se leen bien (contraste WCAG 2.x, nivel AA).

    python tools/brand.py            # informe y sugerencias
    python tools/brand.py --fix      # escribe en site.json los colores corregidos

Cada par (texto sobre fondo) debe llegar a 4.5:1, y el contorno del foco (focus) a 3:1 sobre los fondos. Si no llega, se propone el tono más
parecido (misma tonalidad, más claro u oscuro) que sí cumple.

El color corporativo (primary) NUNCA se modifica: si es claro (amarillo, verde lima…), los botones
llevan texto oscuro (primary_ink = ink) y los enlaces usan un tono aparte más oscuro (brand.link).
"""
import colorsys
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "site.json"

# (color de texto, color de fondo, dónde se usa). El primero es el que se ajusta si falla.
PAIRS = [
    ("ink", "paper", "texto normal sobre el fondo"),
    ("ink", "surface", "texto en tarjetas y cabecera"),
    ("muted", "paper", "textos secundarios"),
    ("muted", "surface", "textos secundarios en tarjetas"),
    ("link", "paper", "enlaces"),
    ("link", "surface", "botones secundarios y enlaces en tarjetas"),
    ("primary_ink", "primary", "texto de los botones y la banda de llamada a la acción"),
    ("paper", "ink", "texto del pie de página"),
]
MIN = 4.5
# Elementos que no son texto (WCAG 1.4.11): el contorno del foco tiene que verse a 3:1 sobre los fondos donde aparece.
# En la banda de llamada a la acción y en el pie, style.css usa primary_ink y paper (ya comprobados arriba a 4.5:1).
NONTEXT = [
    ("focus", "paper", "contorno del foco del teclado sobre el fondo"),
    ("focus", "surface", "contorno del foco en cabecera, tarjetas y formularios"),
]
MIN_NONTEXT = 3.0


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0, min(1, c)) * 255):02X}" for c in rgb)


def luminance(hex_color: str) -> float:
    def ch(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in hex_to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def nearest_passing(fg: str, bg: str, target: float = MIN) -> str | None:
    """Ajusta la luminosidad de fg (manteniendo tono y saturación) hasta cumplir."""
    h, l, s = colorsys.rgb_to_hls(*hex_to_rgb(fg))
    darker_bg = luminance(bg) > 0.18
    for step in range(1, 101):
        nl = l - step / 100 if darker_bg else l + step / 100
        if not 0 <= nl <= 1:
            break
        cand = rgb_to_hex(colorsys.hls_to_rgb(h, nl, s))
        if contrast(cand, bg) >= target:
            return cand
    return None


def main() -> int:
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    brand = cfg["brand"]
    brand.setdefault("link", brand["primary"])
    brand.setdefault("focus", brand["primary"])
    fix = "--fix" in sys.argv
    failures = 0
    for fg_key, bg_key, use, minimum in [(*p, MIN) for p in PAIRS] + [(*p, MIN_NONTEXT) for p in NONTEXT]:
        fg, bg = brand[fg_key], brand[bg_key]
        ratio = contrast(fg, bg)
        ok = ratio >= minimum
        mark = "OK   " if ok else "FALLA"
        print(f"{mark} {ratio:5.2f}:1  {fg_key} {fg} sobre {bg_key} {bg}  ({use})")
        if not ok:
            failures += 1
            sug = None
            if fg_key == "primary_ink":
                # Primero probar el texto oscuro o claro de la propia marca antes de inventar un tono.
                for cand in (brand["ink"], brand["paper"], "#FFFFFF", "#000000"):
                    if contrast(cand, bg) >= MIN:
                        sug = cand
                        break
            if fg_key == "focus":
                # El foco tiene que verse sobre los dos fondos: primero el texto de la marca, luego un tono del corporativo.
                sug = next((c for c in (brand["ink"], brand["link"]) if all(contrast(c, brand[b]) >= minimum for b in ("paper", "surface"))), None)
            if sug is None:
                sug = nearest_passing(fg, bg, minimum)
            if sug:
                print(f"        sugerencia: {fg_key} = {sug}  ({contrast(sug, bg):.2f}:1)")
                if fix:
                    brand[fg_key] = sug
            else:
                print("        sin ajuste posible: cambia el color de fondo")
    for k in ("link", "focus"):
        if brand.get(k) == brand["primary"]:
            brand.pop(k)
    if fix and failures:
        CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("site.json actualizado. Vuelve a ejecutar sin --fix para comprobar.")
    total = len(PAIRS) + len(NONTEXT)
    print(f"{total - failures}/{total} combinaciones cumplen el contraste mínimo ({MIN}:1 textos, {MIN_NONTEXT}:1 foco)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
