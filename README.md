# Plantilla A · Web informativa (La Taza Roja)

Generador de webs estáticas para clientes: rápidas, sin servidor ni base de datos, sin cookies, bilingües si hace falta, con aviso legal y SEO técnico incluidos. Cubre los proyectos de **tipo A** (informativa) y la mayoría de los de **tipo B** (con blog o noticias).

La demo que trae es un cliente ficticio ("Panadería La Espiga"): sustitúyela.

## Crear un proyecto nuevo

1. Sube esta plantilla una vez a la organización de GitHub de La Taza Roja y márcala como **Template repository** (Settings > General).
2. Para cada cliente: **Use this template > Create a new repository** (público si se publica con GitHub Pages gratis).
3. Rellena `CLAUDE.md` (cabecera del proyecto) y `docs/brief.md`.
4. Edita `site.json`:
   - `site_url`, `site_name`, `languages` (el primero va en la raíz `/`).
   - `company`: datos legales del cliente (salen en aviso legal, privacidad, pie y datos estructurados).
   - `brand`: colores, radio de esquinas, tipografías y logo.
   - `contact_form.endpoint`: vacío (solo email y teléfono) o la URL del backend de la plantilla C.
5. Sustituye `content/` por las páginas del cliente y `static/img/` por sus imágenes y logo (SVG en trazos), `static/favicon.svg`,
   `static/fonts/` (con `python tools/marca.py fuente …`) y `marca/`. Genera `static/og.png` (1200×630) con `python tools/marca.py og`.
6. En local:
   ```
   pip install markdown
   python build.py
   python tools/check.py
   cd public && python -m http.server 8000
   ```
7. Publicación:
   - **GitHub Pages** (por defecto): Settings > Pages > Source: GitHub Actions. Dominio: skill `web-estatica-github-pages-ionos`.
   - **Hosting del cliente por SFTP**: variable de repositorio `DEPLOY_SFTP = true` y secretos `SFTP_HOST`, `SFTP_USER`, `SFTP_PASSWORD`, `SFTP_PATH`.

   GitHub Actions genera la web, ejecuta las comprobaciones y solo publica si pasan.
8. Antes de entregar: `python tools/check.py --release` debe terminar sin errores.

## Qué incluye

- Páginas en Markdown con bloques `:::hero`, `:::cards`, `:::cta`, `:::contact` (ver `CLAUDE.md`).
- Blog opcional con listado y entradas.
- Varios idiomas con enlaces entre traducciones, `hreflang` y sitemap con alternativas.
- Aviso legal (LSSI) y privacidad (RGPD) generados desde los datos del cliente.
- Formulario de contacto con casilla de consentimiento y campo trampa antispam; página de "gracias".
- SEO: título y descripción por página, canonical, Open Graph, datos estructurados (negocio local y artículos), `sitemap.xml`, `robots.txt`, 404.
- Menú adaptable a móvil sin JavaScript, foco de teclado visible, enlace "saltar al contenido".
- `tools/brand.py`: contraste accesible de los colores de marca (con `--fix`).
- `tools/marca.py`: fuentes autoalojadas con su licencia (`fuente`), logotipo en trazos (`logotipo`), `og.png` (`og`), revisión de logo,
  favicon y fuentes (`revisar`, también en `check.py`) y kit de entrega con manual de marca (`kit`). Skill `identidad-marca-cliente`.
- `tools/images.py`: fotos a WebP optimizado, giradas y sin metadatos.
- WhatsApp (`site.json > company.whatsapp` y `whatsapp.avisos`): enlace para escribir al negocio y casilla de avisos del pedido por WhatsApp,
  con su texto de privacidad (los envía la plantilla C con la plataforma oficial de Meta).
- Fotos y vídeo: `tools/images.py` (WebP sin metadatos, variantes para `srcset`, recortes), `tools/video.py` (MP4 sin metadatos con
  portada) y el bloque `:::video` (vídeo propio con subtítulos o imagen que enlaza a YouTube).
- Asistente al teléfono (`site.json > asistente_voz`, plantilla-bot > voz): aviso junto al teléfono del contacto y párrafo de privacidad
  (sin grabación, cuánto se guardan las transcripciones y para qué se usa el número).
- Migraciones (`docs/migracion.md`): `site.json > redirecciones` (páginas de redirección en GitHub Pages y 301 en `.htaccess` con alojamiento
  Apache) y `tools/importar_wordpress.py` (contenido publicado de WordPress o Squarespace a Markdown, para revisar en `migracion/`).
- Web instalable (`site.json > app`): manifiesto, iconos (`tools/iconos.py`), página «Sin conexión» y service worker que solo se registra
  si la web se instala o si alguien pide avisos; casilla de avisos del pedido en el dispositivo (los envía la plantilla C), baja en la
  privacidad, enlaces a las fichas de App Store y Google Play y `/.well-known` para abrir los enlaces de la web en la app.
- `tools/check.py`: contraste de marca, enlaces rotos, anclas, un `<h1>` por página, imágenes sin `alt`, textos de relleno y datos legales.
- Catálogo opcional (`site.json > catalog`): listado con buscador y filtros, fichas de producto con datos estructurados y botón de compra,
  desde un JSON o desde la API de la plantilla C, que vuelve a publicar la web cuando cambia el catálogo. Ver `CLAUDE.md`.
- Edición del contenido por el cliente con Pages CMS (`.pages.yml`, `docs/cms.md`).
- Medición opcional (`site.json > medicion`): aviso de cookies propio con Consent Mode, política de cookies generada y origen de las visitas
  (UTM) hacia el backend. Nada de Google ni Meta se carga sin aceptar. El remarketing, solo si se activa (`medicion.remarketing`) y se acepta aparte.

## Limitaciones conocidas

- El formulario necesita un backend (plantilla C) o un servicio de formularios con contrato de encargado del tratamiento.
- Para que el cliente edite contenido sin tocar Markdown: Pages CMS (`docs/cms.md`). Para maquetar a su gusto, WordPress.
- Los textos de los productos del catálogo están en un solo idioma.
