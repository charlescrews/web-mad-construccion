#!/usr/bin/env python3
"""Accesibilidad en un navegador real: axe-core sobre todas las páginas de public/ (o sobre una web publicada).

    npm ci                                   # una vez: instala axe-core (solo herramienta; la web no usa Node)
    python build.py && python tools/axe.py   # todas las páginas de public/, con y sin el aviso de cookies
    python tools/axe.py --url https://www.cliente.es/ --url https://www.cliente.es/contacto/   # una web publicada

Reglas: WCAG 2.0, 2.1 y 2.2, niveles A y AA (la EN 301 549 v4.1.1 de 2026 ya remite a WCAG 2.2). Cualquier incumplimiento
sale con error. axe encuentra solo una parte de los problemas (lo automatizable): la revisión con teclado y lector de pantalla
de la skill accesibilidad-cliente sigue haciendo falta. Necesita Playwright (pip install playwright) y Chromium.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AXE = ROOT / "node_modules" / "axe-core" / "axe.min.js"
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def serve(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D102
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def pages(public: Path) -> list[str]:
    out = []
    for f in sorted(public.rglob("*.html")):
        if 'http-equiv="refresh"' in f.read_text(encoding="utf-8", errors="replace")[:1500]:
            continue  # páginas de redirección (site.json > redirecciones): el navegador se va antes de que axe termine
        rel = "/" + str(f.relative_to(public)).replace("\\", "/")
        out.append(rel[: -len("index.html")] if rel.endswith("/index.html") else rel)
    return out


def run(urls: list[str], *, consent: str = "ninguno", viewport=(1280, 900), local: bool = True, browser=None) -> list[dict]:
    """Devuelve [{url, id, impact, help, nodes: [selector…]}]. consent: ninguno (el aviso de cookies queda abierto) | rechazado."""
    from playwright.sync_api import sync_playwright

    if not AXE.exists():
        raise SystemExit("Falta axe-core: ejecuta npm ci en la raíz del proyecto")
    src = AXE.read_text(encoding="utf-8")
    found: list[dict] = []
    pw = None if browser else sync_playwright().start()
    b = browser or pw.chromium.launch()
    try:
        ctx = b.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        if consent == "rechazado":
            ctx.add_init_script("try{localStorage.setItem('ltr_consent',JSON.stringify({v:1,analitica:false,publicidad:false,at:new Date().toISOString()}))}catch(e){}")
        if local:  # en local, nada sale a Internet (la API del cliente o el asistente no están: sus peticiones fallan sin más)
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("http://127.0.0.1", "data:")) else r.abort())
        page = ctx.new_page()
        for u in urls:
            page.goto(u, wait_until="load")
            page.add_script_tag(content=src)
            res = page.evaluate("tags => axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations']})", TAGS)
            for v in res["violations"]:
                found.append({"url": u, "id": v["id"], "impact": v.get("impact"), "help": v["help"],
                              "nodes": [", ".join(n["target"]) if isinstance(n["target"], list) else str(n["target"]) for n in v["nodes"]][:5]})
        ctx.close()
    finally:
        if pw:
            b.close()
            pw.stop()
    return found


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", action="append", default=[], help="página publicada (se puede repetir)")
    ap.add_argument("--json", action="store_true", help="salida en JSON")
    a = ap.parse_args(argv)
    if a.url:
        found = run(a.url, local=False)
    else:
        public = ROOT / "public"
        if not public.exists():
            raise SystemExit("No existe public/. Ejecuta antes: python build.py")
        srv, base = serve(public)
        try:
            urls = [base + p for p in pages(public)]
            found = run(urls) + run(urls[:3], consent="rechazado", viewport=(390, 844))
        finally:
            srv.shutdown()
    if a.json:
        print(json.dumps(found, ensure_ascii=False, indent=1))
    for f in found:
        print(f"ERROR: {f['url']}: [{f['impact']}] {f['id']}: {f['help']} → {' | '.join(f['nodes'])}")
    print(f"axe-core: {len(found)} incumplimiento(s) WCAG 2.2 A/AA")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
