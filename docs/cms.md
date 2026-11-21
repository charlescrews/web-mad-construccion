# Contenido que edita el cliente

Tres caminos, de más simple a más complejo. Elegir el más simple que cubra lo que el cliente va a cambiar de verdad
(skill `web-dinamica-cliente`).

| Qué cambia | Cómo | Coste para el cliente |
|---|---|---|
| Casi nada (2-3 cambios al año) | Nos lo pide y lo cambiamos (plan de mantenimiento) | Nada extra |
| Textos, horarios, entradas del blog | **Pages CMS** sobre este repositorio (`.pages.yml`) | Nada: usa su cuenta de GitHub |
| Productos, precios, stock | Catálogo en la plantilla C (`CATALOG_SOURCE=db`) y panel | Lo del backend |

## Pages CMS

[Pages CMS](https://pagescms.org) edita los archivos del repositorio desde el navegador. Cada cambio es un commit y
GitHub Actions vuelve a generar y publicar la web. Si un cambio rompe la generación (un bloque `:::` sin cerrar, por ejemplo),
la Action falla, **la web publicada no cambia** y GitHub avisa a quien administra el repositorio.

Montarlo (por proyecto):

1. El cliente necesita una cuenta de GitHub (gratis) con acceso de escritura **solo** a este repositorio.
2. Entrar en Pages CMS con GitHub, instalar su aplicación en el repositorio del cliente y abrirlo.
3. `.pages.yml` ya trae las páginas y el blog en español. Para otro idioma, copiar los bloques cambiando `es` y la ruta.
4. Proteger lo delicado: no dar acceso a `site.json` (datos legales, marca) ni a `.github/`. Esos cambios los hacemos nosotros.
5. Sesión de 30 minutos con el cliente: cambiar un horario, publicar una entrada, ver que la web se actualiza en 1-2 minutos.

Comprobar en el ensayo general (con una cuenta real) que el guardado respeta las cabeceras: `build.py` ya acepta valores
entre comillas, que es como los escriben los CMS.

Reglas:

- Las páginas usan un campo de texto (no el editor visual) para no romper los bloques `:::hero`, `:::cards`, `:::catalogo`…
  El blog sí usa el editor visual.
- Las imágenes que suba van a `static/img`: pedirle fotos de menos de 300 KB o pasarlas por `tools/images.py` en la revisión mensual.
- Las direcciones (`slug`) no se cambian sin crear la redirección (skill `seo-visibilidad-cliente`).

## Cuándo no

- Si el cliente quiere maquetar páginas a su gusto (columnas, bloques nuevos): WordPress u otro constructor (skill `plataformas-existentes-cliente`).
- Si cambia contenido varias veces al día o lo editan varias personas con permisos distintos: un CMS con base de datos.
