# Migrar una web existente a la plantilla A

> Skill `plataformas-existentes-cliente` (sección 7) y `seo-visibilidad-cliente` (sección 13). Donde más visitas se pierden es en
> una migración: no se publica nada sin el mapa de redirecciones revisado.

## 1. Antes de tocar nada

1. Copia completa de la web antigua (archivos y base de datos, o la exportación de la plataforma).
2. Rastreo de la web antigua desde `plantilla-mantenimiento`: `python -m seo.auditar https://www.web-antigua.es --max 2000 --json vieja.json`.
3. Search Console: exportar las páginas con clics y los enlaces externos (son las URLs que no se pueden perder).

## 2. Contenido desde WordPress (o Squarespace, que exporta en el mismo formato)

1. En la web antigua: Herramientas > Exportar > Todo el contenido (un `.xml`).
2. `python tools/importar_wordpress.py exportacion.xml --lang es` → carpeta `migracion/` (no se publica):
   - `blog/*.md` y `paginas/*.md`: Markdown limpio con la cabecera de la plantilla;
   - `redirecciones.json`, `imagenes.csv` e `informe.md` (lo que no se ha importado y lo que hay que revisar).
3. Solo entra lo **publicado**: borradores, privadas, programadas y con contraseña se quedan fuera. Nunca comentarios, autores ni
   emails. Scripts, iframes, formularios y códigos cortos no pasan: el informe dice dónde estaban. Tampoco entran el contenido de
   ejemplo de WordPress («Hello world!», «Sample Page») ni las páginas de sistema de WooCommerce (tienda, carrito, pago, mi cuenta):
   si tenían visitas, su redirección se pone a mano. La portada estática sale como página con el aviso de pasar su texto a
   `home.md` (los enlaces a ella ya van a `/`); una página que la plantilla ya genera (aviso legal, privacidad…) sale con otro
   nombre, sin redirección, para pasar a `site.json` lo que falte. Los vídeos del bloque «Insertar» pasan a enlace, y las
   descripciones de menos de 70 caracteres sacadas del texto quedan con `[CONFIRMAR` (ensayo general con una exportación real).
4. Revisar cada archivo con el cliente: textos al día, una sola idea por página, `description` de 140-160 caracteres
   (skill `contenido-web-cliente`). Moverlos a `content/es/blog/` y `content/es/`.
5. Imágenes: descargar las de `imagenes.csv` (con el cliente, de su copia o de la web antigua), pasarlas por
   `python tools/images.py carpeta/ static/img/blog/` y escribir cada texto alternativo pendiente. `check.py --release` falla
   mientras quede un `[CONFIRMAR: texto alternativo…]`.
6. Vídeos y mapas: el importador deja un enlace; mejor una imagen propia que enlace (sin cargar YouTube ni Google Maps).
7. Formularios: el bloque `:::contact`; tiendas: productos de WooCommerce o Shopify con `npm run convertir` de la plantilla C.

Con otras plataformas (Wix, PrestaShop, Joomla…), el contenido se pasa a mano o desde lo que exporten; el rastreo del punto 1
da la lista de URLs para las redirecciones.

## 3. Redirecciones (`site.json > redirecciones`)

```json
"redirecciones": {
  "htaccess": false,
  "reglas": {
    "/2024/05/como-hacemos-el-pan/": "/blog/como-hacemos-el-pan/",
    "/quienes-somos/": "@sobre",
    "/contacto.html": "/contacto/"
  }
}
```

- Cada URL antigua con valor a su equivalente nueva, **no todo a la portada**. Destino: ruta de esta web o `@clave` de una página.
- `build.py` genera en cada origen una página con redirección inmediata, `canonical` y `noindex` (Google la trata como
  redirección permanente) y un enlace visible. Vale en GitHub Pages.
- Con alojamiento Apache (publicación por SFTP), `"htaccess": true` añade `public/.htaccess` con 301 de verdad: mejor para
  Google y lo único que sirve para direcciones con parámetros (`/?p=123`) o `.php`. En GitHub Pages esas no se pueden redirigir.
- `build.py` falla si un destino no existe, apunta a otro dominio, encadena redirecciones, tapa una página de la web o lleva
  caracteres que no son de URL (lo raro, codificado con `%`).

## 4. El día del cambio y después

- `python build.py && python tools/check.py --release` y, desde `plantilla-mantenimiento`,
  `python -m seo.auditar http://127.0.0.1:8000 --como https://www.cliente.es`.
- Comprobar a mano 10 URLs antiguas importantes: cada una lleva a su página nueva.
- Enviar el sitemap en Search Console e inspeccionar la portada y 5 páginas clave.
- 8 semanas de seguimiento de errores 404 en Search Console; cada URL antigua que aparezca, a `redirecciones.reglas`.
- No dar de baja la web antigua (ni su alojamiento) hasta que la nueva esté publicada y las redirecciones comprobadas.
