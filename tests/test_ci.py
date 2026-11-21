"""CI: las acciones de GitHub van fijadas por commit (una etiqueta se puede mover: ataque a trivy-action, marzo de 2026)
y cada flujo declara permisos mínimos. Skill servidor-seguridad-cliente."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CiTests(unittest.TestCase):
    def test_acciones_fijadas_por_sha_y_permisos(self):
        flujos = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertTrue(flujos)
        for f in flujos:
            txt = f.read_text(encoding="utf-8")
            for uso in re.findall(r"uses:\s*(\S+)", txt):
                self.assertRegex(uso, r"@[0-9a-f]{40}$", f"{f.name}: {uso} sin fijar por SHA")
            self.assertRegex(txt, r"(?m)^permissions:", f"{f.name}: sin permisos declarados")

    def test_ci_comprueba_fotos_y_caracteres_de_las_fuentes(self):
        """Sin Pillow, fontTools y brotli, los tests de imágenes y la comprobación de caracteres de las fuentes se saltarían en silencio."""
        for f in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            txt = f.read_text(encoding="utf-8")
            if "tools/check.py" not in txt:
                continue
            for pkg in ("Pillow", "fonttools", "brotli"):
                self.assertRegex(txt, rf"pip install [^\n]*\b{pkg}==\d", f"{f.name}: {pkg} sin instalar o sin fijar")


if __name__ == "__main__":
    unittest.main()
