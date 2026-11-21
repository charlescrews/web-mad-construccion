# Proyecto: Miguel Ángel Díaz Construcción (MAD Construcción)

- Tipo: A (informativa, escaparate de trabajos y contacto por teléfono, WhatsApp y email; sin formulario ni reservas)
- Cliente: Miguel Ángel Díaz, especialista en alicatados y solados. Proyecto propio de Carlos, fuera de La Taza Roja.
- Dominio: madconstruccion.es (web en www) — registrador: IONOS, cuenta a nombre de Miguel Ángel — **NO tocar registros MX/SPF/DKIM/DMARC**
- Publicación: GitHub Pages
- Entornos: pruebas (vista previa privada) / producción (https://www.madconstruccion.es)
- Contacto que aprueba: Miguel Ángel Díaz (por WhatsApp)
- Fechas: contenido del cliente recibido (nov 2026); publicación 21/11/2026
- Formulario de contacto: sin endpoint (solo teléfono, WhatsApp y email)
- Notas internas (brief, decisiones, competencia): fuera del repositorio público

## Cómo está hecha esta web (plantilla A de La Taza Roja)

- Todo lo del cliente está en `site.json` (empresa, marca, idiomas) y en `content/`.
- `content/<idioma>/<clave>.md`: una página por archivo. Cabecera obligatoria: `title`, `description`.
  Opcional: `key` (por defecto el nombre del archivo), `slug`, `nav` (número de orden en el menú), `nav_title`,
  `seo_title`, `image`, `noindex: true`. La portada es `home.md`.
- La misma `key` en cada idioma enlaza las traducciones entre sí.
- `content/<idioma>/blog/*.md`: entradas del blog (`title`, `description`, `date`; `draft: true` para ocultar).
- Bloques dentro del cuerpo de una página:
  - `:::hero` título `#`, texto, una línea de enlaces (se convierten en botones) y opcionalmente una imagen.
  - `:::cards` un `##` de sección y cada tarjeta empieza con `###`.
  - `:::cta` llamada a la acción en banda de color.
  - `:::contact` formulario (si hay endpoint) + datos de contacto.
  - `:::boletin` alta en el boletín (necesita `site.json > crm.boletin`).
  - `:::video` (skill `fotografia-video-cliente`): `titulo`, `poster` (imagen de static/) y `archivo` (MP4/WebM de static/, hasta 30 MB) con
    `subtitulos` (.vtt) o `sin_voz: true`; opcional `transcripcion: @clave` e `idioma`. Con `youtube: <id>` en vez de `archivo`, una imagen
    propia que enlaza a YouTube (nada de Google se carga). Siempre con controles, sin reproducción automática y `preload="none"`.
  - Cada bloque se cierra con `:::` en su propia línea.
  - `:::presupuesto` (texto de cabecera dentro, opcional): formulario de solicitud de presupuesto que prepara en el navegador un mensaje de
    WhatsApp (`company.whatsapp`) o un email (`company.email`) con el trabajo, el pueblo, las medidas, el plazo, el nombre y una nota. La web
    no envía ni guarda nada (sin servidor ni coste); los enlaces funcionan sin JavaScript y `static/presupuesto.js` les añade el texto
    codificado. Necesita `site.json > presupuesto.trabajos` (y `plazos`, opcional): una lista, o una por idioma
    (`{"es": [...], "en": [...]}`) si la web tiene varios. Añade su párrafo a la privacidad.
  - Variantes (se escriben tras el nombre del bloque; una desconocida para `build.py`):
    - `:::hero banda`: portada a todo el ancho sobre el color corporativo; la imagen, si la hay, va de fondo con una capa del color
      corporativo para que el texto se lea; botones claros.
    - `:::cards oscuro`: las tarjetas sobre una banda del color corporativo a todo el ancho (para alternar con secciones claras).
    - `:::split` (y `:::split inverso`, imagen a la derecha): imagen y texto en paralelo; obligatorio una imagen `![alt](/img/…)`.
- Enlaces internos: `[texto](@clave)`; el generador pone la URL correcta en cada idioma.
- Aviso legal y privacidad se generan solos desde `site.json > company` y `site.json > privacidad` (skill `rgpd-tecnico-cliente`):
  - `contacto_meses` y `pedidos_anios` (6 como mínimo): los mismos plazos que `config/rgpd.json` de la plantilla C;
  - `encargados`: quién trata datos por cuenta del cliente (`servicio`, `nombre`, `pais`; fuera del EEE, `garantia`). Salen en
    «Destinatarios» y «Transferencias internacionales». `check.py --release` falla si faltan o si falta el de un servicio activo
    (alojamiento y email con formulario o tienda; pagos con tienda);
  - el formulario de contacto y el de compra llevan debajo la información básica (responsable, finalidad, base, plazo y enlace).
- Colores y tipografías: `site.json > brand` (skills `diseno-web-cliente` e `identidad-marca-cliente`). `primary` es el color corporativo y no se toca;
  `link` (opcional) es el tono de los enlaces si el corporativo es claro. Comprobar con `python tools/brand.py`.
- Marca (`tools/marca.py`, skill `identidad-marca-cliente`; `check.py` lo comprueba todo en cada publicación):
  - tipografías propias autoalojadas: `python tools/marca.py fuente <id de Fontsource> [--version …] [--estatica --pesos 400,700]` copia
    del registro de npm solo los woff2 y la licencia a `static/fonts/` e imprime la entrada de `brand.font_files` (`family`, `file`,
    `weight`, `style`, `licencia`, `origen`). Sin licencia publicada al lado, con una licencia que no es OFL/Apache/UFL/MIT (sin
    `licencia_revisada`), con la primera familia de una pila sin autoalojar ni del sistema, o con letras de la web que la fuente no tiene
    (necesita fontTools y brotli), `check.py` falla;
  - logo en SVG en trazos (sin `<text>`), sin scripts, imágenes incrustadas, nada de fuera ni rutas del equipo, con viewBox;
    `python tools/marca.py logotipo "Nombre" --fuente static/fonts/x.woff2 --peso 650 [--simbolo marca/simbolo.svg]` lo hace con
    kerning. La cabecera lo pone con `width`/`height` y lo encoge sin deformarlo en el móvil. `static/favicon.svg` cuadrado;
  - `python tools/marca.py og [--foto …] [--texto …]`: `static/og.png` 1200×630 con el logo (Playwright, sin red). `check.py --release`
    falla sin ella o con otra medida;
  - `marca/`: `marca.json` (lema, tamaño mínimo, área de respeto, nombres y CMYK de colores, tono), `simbolo.svg` y `logo-negativo.svg`
    (opcionales). `python tools/marca.py kit` → `marca/entrega/` y su zip (no se guardan en el repositorio): logos en SVG, PDF vectorial
    y PNG transparente, avatar de 1080, favicon, og, fuentes de escritorio (Regular y Bold, con su licencia; ninguna si la licencia
    reserva el nombre), manual en HTML y PDF y `LEEME.txt`. Se para si algo de la marca falla o queda un `[CONFIRMAR`.
- Fotos: `python tools/images.py carpeta-original/ static/img/` (WebP, < 300 KB, sin metadatos: se guarda una imagen nueva, sin EXIF ni XMP).
  `--variantes 480,960` crea `foto-480.webp`…: `build.py` pone `srcset` y `sizes` según el sitio (texto, portada, tarjetas) y a toda foto
  propia le pone `width` y `height` (leídos de la cabecera) para que la página no salte. `--recorte 1200x630 --nombre og --png` para `og.png`.
- Vídeo: `python tools/video.py original.mov static/video/` (necesita ffmpeg): MP4 H.264 a 720 px, sin metadatos (ubicación, móvil, fecha),
  con faststart y portada `-poster.webp`; imprime el bloque `:::video`. Los subtítulos, revisados a mano en WebVTT.
- Accesibilidad (skill `accesibilidad-cliente`, objetivo WCAG 2.2 AA):
  - `tools/check.py` (con `tools/a11y.py`) falla con lo que se rompe al editar contenido: idioma, campos sin etiqueta, enlaces y botones
    sin texto, iframes sin `title`, zoom bloqueado, `tabindex` positivo, vídeo que suena solo o sin subtítulos, `alt` que es un nombre de archivo,
    saltos de encabezado e ids duplicados; avisa de enlaces «leer más», PDF, tablas sin encabezados e imágenes con `alt` vacío;
  - `tools/brand.py`: además del texto, el contorno del foco (`brand.focus`) a 3:1; en la banda de llamada a la acción y en el pie el
    foco usa el color del texto; los bordes de los campos usan `muted`;
  - lo que recibe el foco nunca queda tapado: `scroll-padding-top` por la cabecera fija y, con el aviso de cookies abierto, sitio debajo
    (`consent.js`);
  - `npm ci` y `python tools/axe.py`: axe-core en Chromium sobre todas las páginas (también lo hace GitHub Actions);
    `tests/test_accesibilidad_navegador.py`: teclado, foco visible y no tapado, reflujo a 320 px, aviso de cookies y movimiento reducido;
  - declaración en `/accesibilidad/` desde `site.json > accesibilidad` (estado, fecha de evaluación, problemas, descripción del
    servicio para tiendas); `check.py --release` falla si no se ha evaluado o el estado no cuadra con los problemas.
- Pedido preparado por el asistente (opcional, skill `asistente-conectado-cliente`): `site.json > catalog.asistente: true` (necesita
  `api` y `comprar`) crea `/pedido/` (noindex, fuera del sitemap). `catalogo.js` lee `?propuesta=` de la plantilla C, pinta los productos
  con `textContent` y paga con el formulario de la ficha, más `propuesta`. Si no hay propuesta o ha caducado, lleva al catálogo. La
  privacidad añade el párrafo del asistente conectado. En plantilla-bot, `tienda.pagina_pedido` = `https://DOMINIO/pedido/`.
- Cierres (festivos y vacaciones): `site.json > company.cierres` = `[{"desde", "hasta", "motivo": {"es": …}}]`. El contacto enseña los de
  los próximos 90 días. `check.py` avisa de los que ya pasaron y `build.py` para con fechas mal escritas. Para tests, `LTR_HOY=AAAA-MM-DD`.
  Con `company.cierres_api` (https://api.cliente.es/api/cierres) se suman los que el negocio apunta en el panel de la plantilla C; si no se
  pueden leer, no se publica.
- Con el asistente de chat activo, `build.py` publica `/asistente.json` con lo público de la web (contacto, horario, cierres vigentes,
  páginas indexables y productos). Lo lee `npm run conocimiento` de plantilla-bot (skill `conocimiento-asistente-cliente`). Nada privado:
  ni CIF, ni registro mercantil, ni páginas `noindex`.
- Asistente de chat (opcional): `site.json > chatbot` con `script` y `bot` del servidor `plantilla-bot` (skill `bots-web-cliente`).
  Añade el script y el párrafo de privacidad; `transferencia` debe quedar rellena (si no, `check.py --release` falla).
- `static/og.png` (1200×630): imagen al compartir en redes; `python tools/marca.py og` (o `tools/images.py --recorte 1200x630 --nombre og --png` desde una foto).
- Catálogo (opcional, `site.json > catalog`): listado con buscador y filtros (bloque `:::catalogo` en la página `catalog.page`),
  una ficha por producto en `/<página>/<sku>/` con datos estructurados `Product`, y sitemap.
  - `source`: un JSON del repositorio (`data/catalogo.json`) o `https://api.cliente.es/api/catalogo/export.json` (plantilla C con
    `CATALOG_SOURCE=db`, que avisa a la Action para volver a publicar cuando cambia algo).
  - `api` (https://api.cliente.es): precios y disponibilidad al día en el navegador y, con `comprar: true`, botón de compra.
    `envio`: lista de métodos si hay más de uno. `factura_completa: true`: campos opcionales para factura a nombre de empresa
    (la plantilla C comprueba el NIF y se los pasa al programa de facturación).
  - `por_categoria: true`: una página por categoría (catálogos de cientos de productos).
  - Si el catálogo no se puede descargar, está vacío o trae datos raros, `build.py` falla y la web publicada no cambia.
  - Los textos de los productos están en un solo idioma: solo hay fichas en los idiomas cuya página lleva `:::catalogo`.
  - Imágenes: `static/img/productos/<sku>.webp` (con `tools/images.py`) o URL https. En el panel se escribe `img/productos/<sku>.webp`.
- Área de cliente (plantilla C, `CUSTOMER_ACCOUNT=on`): `site.json > cuenta_url` añade «Mis pedidos» al pie y actualiza la privacidad.
- Edición por el cliente: Pages CMS con `.pages.yml` (ver `docs/cms.md`).
- Migraciones (skill `plataformas-existentes-cliente`, `docs/migracion.md`):
  - `site.json > redirecciones.reglas` (`"/url-vieja/": "/url-nueva/"` o `"@clave"`): página con redirección inmediata y canonical por
    cada origen; con `htaccess: true` (Apache, SFTP), además `.htaccess` con 301 (también para `?p=123` y `.php`). `build.py` falla con
    destinos de otro dominio, inexistentes o encadenados, con orígenes que tapan una página y con caracteres que no son de URL;
  - `python tools/importar_wordpress.py exportacion.xml`: WordPress (o Squarespace) a Markdown en `migracion/` para revisar: solo lo
    publicado, sin comentarios ni autores, sin HTML; propone redirecciones e imágenes.
- Medición de campañas (opcional, `site.json > medicion`: `ga4`, `google_ads`, `meta_pixel`, `politica_actualizada`, `remarketing`; skill `medicion-campanas-cliente`):
  - activa el aviso de cookies (`static/consent.js`), la política de cookies y «Configurar cookies» en el pie, y actualiza la privacidad;
  - nada de Google ni Meta se carga sin aceptar; «Rechazar todas» al mismo nivel que «Aceptar todas»; se pregunta de nuevo a los 12 meses;
  - con consentimiento, el origen de la visita (UTM, gclid, fbclid; gbraid o wbraid en clics de Google desde iPhone) viaja en los
    formularios de compra y contacto a la plantilla C, que envía las compras a GA4 y Meta desde el servidor;
  - los UTM son solo para enlaces que llegan de fuera (anuncios, redes, emails, QR): `tools/check.py` falla con un enlace interno que
    lleve `utm_*` o un identificador de clic, porque pisaría el origen real de la visita (skill `campanas-ads-cliente`).
  - `remarketing: true` (solo con `google_ads` o `meta_pixel`): mostrar anuncios a quien visitó la web es otra finalidad; el aviso, la
    política de cookies y la privacidad lo dicen, se vuelve a preguntar a quien había aceptado la publicidad sin él, y los formularios
    envían `consent_remarketing`. Sin él, la publicidad solo mide (`ad_personalization` denegado y `allow_ad_personalization_signals: false`).
- CRM y fidelización (opcional, `site.json > crm`, plantilla C con `config/crm.json`; skill `crm-fidelizacion-cliente`):
  - `boletin`: endpoint `https://api.cliente.es/api/boletin`; bloque `:::boletin` (título y texto dentro) con casilla sin marcar,
    información básica de protección de datos y página «Revisa tu email». El alta no cuenta hasta confirmar desde el email.
  - En el pedido, UNA de las dos: `novedades_en_pedido` (casilla para aceptar novedades) u `ofertas_clientes` (aviso y casilla para
    oponerse a ofertas de productos similares, LSSI 21.2; `aviso_version` igual que en el servidor). Con las dos, `build.py` falla.
  - `programa.bases_url`: casilla para unirse al programa de puntos y campo «Tengo un vale». Las bases tienen que estar publicadas
    (`tools/check.py` falla si apuntan a una página de la web que no existe).
  - Todo actualiza la política de privacidad. Ninguna casilla viene marcada.
- WhatsApp (opcional, skill `whatsapp-cliente`):
  - `company.whatsapp` (+34600000000): enlace `wa.me` en el contacto (un enlace: no se carga nada de Meta) y párrafo de privacidad;
  - `whatsapp.avisos: true` (la plantilla C envía avisos con la plataforma oficial): casilla sin marcar «avisos de este pedido por
    WhatsApp» con el móvil (obligatorio solo si se marca; `catalogo.js`), `aviso_version` y párrafo de privacidad. `check.py --release`
    exige el encargado `whatsapp` (Meta). El widget de reservas de la plantilla C pone su propia casilla.
- Varios idiomas: el selector va siempre a la vista en la cabecera, fuera del menú (en el móvil, abreviado: «EN», con «English» como
  nombre accesible). Arriba, un aviso oculto («This page is also available in English · View in English») que `static/idioma.js`
  enseña solo si el navegador prefiere otro idioma de la web antes que el de la página; no redirige. «Cerrar» lo oculta el resto
  de la visita (sessionStorage). Lo prueba `tests/test_idioma.py`.
- Barra fija de contacto en el móvil (opcional, `site.json > barra_movil.activa`): «Llamar» (`company.phone`, obligatorio) y «WhatsApp»
  (`company.whatsapp`, si lo hay) abajo en móviles: pantalla de menos de 48rem y táctil (en un ordenador con ratón no sale
  aunque la ventana sea estrecha). Solo enlaces, nada de fuera. `style.css` reserva su sitio
  (padding del body y `scroll-padding-bottom`) para que no tape el foco ni el final del pie; lo prueba `tests/test_variantes.py`.
  `barra_movil: false` en la cabecera de una página la quita solo ahí (p. ej. la del formulario de presupuesto, que ya tiene sus botones).
- Asistente al teléfono (opcional, `site.json > asistente_voz`; plantilla-bot > voz, skill `agente-voz-cliente`): `activo` añade junto al
  teléfono del contacto «Puede atenderte un asistente automático con IA: di «persona» o pulsa 0…» y el párrafo «Asistente telefónico» de
  la privacidad (no se graba, transcripciones según `conservacion_dias`, el número solo para devolver la llamada). `transferencia` (o la de
  `chatbot`) y el encargado `telefonia` (Twilio) obligatorios en `check.py --release`. Sin `company.phone`, la web no se genera.
- Web instalable y apps (opcional, `site.json > app`; skill `apps-moviles-cliente`):
  - `pwa: true`: manifiesto, iconos (`python tools/iconos.py simbolo.png` → `static/app/`; sin los cuatro de la medida justa la web
    no se publica), página «Sin conexión» con teléfono y dirección, y `sw.js` (copia de lo visitado; no toca formularios ni otros
    dominios; versión nueva con cada publicación). `static/app.js` registra el service worker **solo** si la web está instalada o si
    alguien pide avisos: a quien solo visita no se le guarda nada. `nombre_corto`: 12 caracteres como máximo;
  - `push.clave_publica` (la pública VAPID de la plantilla C, `npm run push -- comprobar`): casilla sin marcar «avisos de este pedido en
    este dispositivo» (oculta si el navegador no puede; en iPhone, solo con la web en la pantalla de inicio), permiso pedido al marcarla,
    «Dejar de recibir avisos en este dispositivo» en la privacidad y su párrafo. Un aviso solo abre páginas de la web o de su API.
    El widget de reservas de la plantilla C pone su casilla con `data-sw="/sw.js"` en su `<script>`;
  - `tiendas.ios` / `tiendas.android`: enlaces de texto a las fichas en el pie (solo apps.apple.com y play.google.com), banner de Safari con
    `ios.app_store_id` y párrafo «App para móvil»; `check.py --release` exige el encargado `notificaciones` (Firebase);
  - `ios.app_id` (TEAMID.bundle, `rutas`, `excluir`) y `android.paquete` + `huellas` (SHA-256 de Play Console > Firma de apps):
    `/.well-known/apple-app-site-association` y `/.well-known/assetlinks.json` para abrir los enlaces de la web en la app. GitHub Pages
    los publica gracias a `include-hidden-files: true` en el flujo; build.py no copia ningún archivo oculto de `static/`.

## Comandos

```
pip install markdown
python build.py                 # genera public/
python tools/check.py           # comprobaciones (lo mismo que hace GitHub Actions)
python tools/check.py --release # antes de entregar: falla si hay textos de relleno o faltan datos legales
python -m unittest discover -s tests -t .   # tests del generador (catálogo, escapado, cabeceras, aviso de cookies, boletín y casillas, privacidad, terceros, migraciones, asistente telefónico, fotos y vídeo, marca)
# Los tests usan la demo de la plantilla (tests/datos/demo: site.json, content, static, marca) con el build.py y tools/ del proyecto:
# no dependen del contenido del cliente. No borrar tests/datos/demo al sustituir la demo por el cliente.
python tools/importar_wordpress.py exportacion.xml   # contenido de WordPress a migracion/ (docs/migracion.md)
python tools/iconos.py simbolo.png   # iconos de la web instalable (site.json > app.pwa) en static/app/
python tools/video.py original.mov static/video/   # vídeo para :::video (ffmpeg)
python tools/marca.py revisar | fuente <id> | logotipo "Nombre" --fuente … | og | kit   # marca (pip install fonttools==4.66.1 brotli==1.2.0)
# con Playwright y axe-core, también prueba en un navegador (aviso de cookies y accesibilidad):
#   npm ci && pip install playwright && python -m playwright install chromium
python tools/axe.py             # axe-core (WCAG 2.2 A/AA) sobre todas las páginas de public/; --url https://… para una web publicada
python tools/vista_previa.py public vista-previa/index.html   # un solo HTML con todas las páginas (#vistas) para enseñar al cliente como página privada
cd public && python -m http.server 8000
```

## Reglas

- Acciones de GitHub fijadas por commit (SHA, con la versión en un comentario), nunca por etiqueta, y `permissions:` mínimos en cada flujo; Dependabot las actualiza. Lo comprueba un test (skill `servidor-seguridad-cliente`).
- No editar `public/` a mano: se regenera (también `.htaccess`, desde `site.json > redirecciones`).
- Nada importado de otra web se publica sin revisar: `migracion/` no se despliega y `check.py --release` falla con un `[CONFIRMAR` pendiente.
- Secretos nunca en el repositorio.
- No añadir scripts ni recursos de terceros (Google Fonts, mapas, vídeos incrustados, analítica) sin consentimiento de cookies y sin actualizar la política de privacidad.
  `tools/check.py` falla con cualquier script, hoja de estilos, fuente, imagen o iframe de otro dominio que no sea la propia web, la API
  del cliente, el asistente o un dominio declarado en `privacidad.encargados[].dominios`; Google Fonts desde su CDN, siempre.
  Vídeos y mapas: una imagen propia que enlaza a YouTube o a Google Maps.
  Las etiquetas de medición van SOLO por `site.json > medicion` (`tools/check.py` falla si aparecen puestas a mano). El asistente de chat propio (`chatbot`) ya actualiza la privacidad y no usa cookies.
- Cada imagen con `alt` descriptivo (vacío solo si es decorativa); imágenes optimizadas (WebP o JPG, < 300 KB).
- Nada de `outline: none` sin sustituto, `tabindex` positivo, `user-scalable=no`, ni contenido que se mueva o suene solo.
  Un componente nuevo (pestañas, carrusel, desplegable) se prueba con teclado y con `tools/axe.py` antes de publicarlo.
