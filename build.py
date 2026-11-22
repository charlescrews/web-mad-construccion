#!/usr/bin/env python3
"""Plantilla A de La Taza Roja: generador de webs estáticas para clientes.

Uso:
    pip install markdown
    python build.py            # genera public/
    python tools/check.py      # comprueba enlaces, textos de relleno y legales

Todo lo específico del cliente está en site.json y en content/.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
STATIC = ROOT / "static"
OUT = ROOT / "public"

CFG = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
SITE_URL = CFG["site_url"].rstrip("/")
LANGS: list[str] = CFG.get("languages", ["es"])
DEFAULT = LANGS[0]
CO = CFG["company"]
BRAND = CFG["brand"]
FORM = CFG.get("contact_form", {}).get("endpoint", "").strip()
BOT = CFG.get("chatbot", {})
CAT = CFG.get("catalog", {}) or {}
CAT_API = (CAT.get("api") or "").strip().rstrip("/")
CAT_BUY = bool(CAT.get("comprar")) and bool(CAT_API)
# Cierres (festivos, vacaciones): site.json > company.cierres = [{"desde": "AAAA-MM-DD", "hasta": "AAAA-MM-DD", "motivo": {"es": …}}].
# Salen en el contacto (los próximos 90 días) y en /asistente.json, de donde el asistente los toma (skill bots-web-cliente).
HOY = dt.date.fromisoformat(os.environ["LTR_HOY"]) if os.environ.get("LTR_HOY") else dt.date.today()  # LTR_HOY: solo para tests
CIERRES = []
for _i, _c in enumerate(CFG["company"].get("cierres") or []):
    try:
        _d = dt.date.fromisoformat(str(_c.get("desde", "")))
        _h = dt.date.fromisoformat(str(_c.get("hasta") or _c.get("desde")))
    except ValueError:
        sys.exit(f"ERROR: site.json > company.cierres[{_i}]: desde y hasta con formato AAAA-MM-DD")
    if _h < _d:
        sys.exit(f"ERROR: site.json > company.cierres[{_i}]: hasta es anterior a desde")
    CIERRES.append({"desde": _d, "hasta": _h, "motivo": _c.get("motivo") or ""})
# Cierres apuntados en el panel de la plantilla C (panel → Cierres): company.cierres_api = https://api.cliente.es/api/cierres. La C
# vuelve a publicar la web cuando cambian. Si no se pueden leer, no se publica (mejor la web anterior que una sin los festivos).
_CAPI = (CFG["company"].get("cierres_api") or "").strip()
if _CAPI:
    if not re.match(r"^(https://|http://(127\.0\.0\.1|localhost)[:/])", _CAPI):
        sys.exit("ERROR: site.json > company.cierres_api debe ser https://")
    import urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request(_CAPI, headers={"Accept": "application/json", "User-Agent": "plantilla-a"}), timeout=20) as _r:  # noqa: S310
            _api = json.loads(_r.read().decode("utf-8"))
        for _c in _api["cierres"]:
            _d, _h = dt.date.fromisoformat(_c["desde"]), dt.date.fromisoformat(_c["hasta"])
            _m = {k: str(v)[:80] for k, v in (_c.get("motivo") or {}).items() if k in LANGS and isinstance(v, str)}
            if _h >= _d and not any(c["desde"] == _d and c["hasta"] == _h for c in CIERRES):
                CIERRES.append({"desde": _d, "hasta": _h, "motivo": _m})
    except Exception as e:  # noqa: BLE001
        sys.exit(f"ERROR: no se pudieron leer los cierres de {_CAPI}: {e}")
CIERRES.sort(key=lambda c: c["desde"])
# Pedido preparado por el asistente (skill asistente-conectado-cliente): página /pedido/ que enseña la propuesta de la plantilla C
# (?propuesta=…) y la paga con el mismo formulario que la ficha. Necesita la compra activa.
ASISTENTE = CAT.get("asistente") is True
if ASISTENTE and not CAT_BUY:
    sys.exit("ERROR: site.json > catalog.asistente necesita catalog.api y catalog.comprar: true (el pedido preparado se paga con la plantilla C)")
ACCOUNT = (CFG.get("cuenta_url") or "").strip()
# Medición (opcional): etiquetas de Google y Meta, solo tras el consentimiento (static/consent.js).
MED = CFG.get("medicion", {}) or {}
MED_GA4 = (MED.get("ga4") or "").strip()
MED_ADS = (MED.get("google_ads") or "").strip()
MED_META = (MED.get("meta_pixel") or "").strip()
for _v, _re, _name in ((MED_GA4, r"G-[A-Z0-9]{4,20}", "ga4"), (MED_ADS, r"AW-\d{5,15}", "google_ads"), (MED_META, r"\d{5,20}", "meta_pixel")):
    if _v and not re.fullmatch(_re, _v):
        sys.exit(f"ERROR: site.json > medicion.{_name} no válido: {_v}")
MED_ON = bool(MED_GA4 or MED_ADS or MED_META)
# Remarketing (skill campanas-ads-cliente): mostrar anuncios a quien visitó la web es una finalidad distinta de medir; solo si se pide aquí,
# y entonces el aviso de cookies, la política de cookies y la privacidad lo dicen. Sin Google Ads ni Meta no tiene sentido.
MED_RMK = MED.get("remarketing") is True
if MED_RMK and not (MED_ADS or MED_META):
    sys.exit("ERROR: site.json > medicion.remarketing necesita google_ads o meta_pixel")
# CRM y fidelización (opcional, plantilla C con config/crm.json): boletín, casillas del pedido y programa de puntos.
CRM = CFG.get("crm", {}) or {}
NEWS = (CRM.get("boletin") or "").strip()
NEWS_IN_ORDER = bool(CRM.get("novedades_en_pedido"))
OFFERS = bool(CRM.get("ofertas_clientes"))
OFFERS_V = str(CRM.get("aviso_version") or "v1")
LOYALTY = CRM.get("programa", {}) or {}
LOYALTY_BASES = (LOYALTY.get("bases_url") or "").strip()
if NEWS and not re.fullmatch(r"https://[^\s\"<>]+/api/boletin", NEWS):
    sys.exit("ERROR: site.json > crm.boletin debe ser https://api.cliente.es/api/boletin")
if NEWS_IN_ORDER and OFFERS:
    # O se pide el consentimiento (casilla para aceptar) o se usa la excepción de clientes (casilla para oponerse): las dos juntas confunden.
    sys.exit("ERROR: site.json > crm: elige novedades_en_pedido u ofertas_clientes, no las dos")
if not re.fullmatch(r"[\w.-]{1,40}", OFFERS_V):
    sys.exit("ERROR: site.json > crm.aviso_version no válido")
if LOYALTY_BASES and not LOYALTY_BASES.startswith("https://"):
    sys.exit("ERROR: site.json > crm.programa.bases_url debe ser https://")
# WhatsApp (skill whatsapp-cliente): company.whatsapp = número del negocio (enlace wa.me en el contacto, sin cargar nada de Meta);
# whatsapp.avisos = la plantilla C envía avisos de pedidos por WhatsApp (casilla sin marcar en el pedido y texto de privacidad).
WA = CFG.get("whatsapp", {}) or {}
# Barra fija de contacto en el móvil (site.json > barra_movil.activa): Llamar (company.phone) y WhatsApp (company.whatsapp, si lo hay).
BARRA_MOVIL = bool((CFG.get("barra_movil") or {}).get("activa"))
# Formulario de presupuesto (bloque :::presupuesto, site.json > presupuesto): prepara en el navegador un mensaje de WhatsApp (o un email)
# con lo que escribe el cliente; la web no envía ni guarda nada (static/presupuesto.js). Sin servidor ni coste.
PRES = CFG.get("presupuesto") or {}
WA_AVISOS = bool(WA.get("avisos"))
WA_V = str(WA.get("aviso_version") or "v1")
WA_NUM = re.sub(r"[\s.\-()]", "", str(CO.get("whatsapp") or ""))
if WA_NUM and not re.fullmatch(r"\+?[1-9]\d{7,14}", WA_NUM):
    sys.exit(f"ERROR: site.json > company.whatsapp no válido: {CO.get('whatsapp')} (número con prefijo, p. ej. +34600000000)")
if not re.fullmatch(r"[\w.-]{1,40}", WA_V):
    sys.exit("ERROR: site.json > whatsapp.aviso_version no válido")
# App (skill apps-moviles-cliente): web instalable (PWA) con avisos en el dispositivo, y enlaces con las apps de las tiendas.
APP = CFG.get("app", {}) or {}
PWA = bool(APP.get("pwa"))
APP_NAME = str(APP.get("nombre") or CFG["site_name"]).strip()
APP_SHORT = str(APP.get("nombre_corto") or APP_NAME).strip()
APP_BG = str(APP.get("color_fondo") or BRAND["paper"]).strip()
if PWA and len(APP_SHORT) > 12:
    sys.exit(f"ERROR: site.json > app.nombre_corto: 12 caracteres como máximo (lo que cabe bajo el icono): «{APP_SHORT}»")
if not re.fullmatch(r"#[0-9a-fA-F]{6}", APP_BG):
    sys.exit("ERROR: site.json > app.color_fondo: #RRGGBB")
PUSH_CFG = APP.get("push", {}) or {}
PUSH_KEY = str(PUSH_CFG.get("clave_publica") or "").strip()
PUSH_V = str(PUSH_CFG.get("aviso_version") or "push-v1")
if not re.fullmatch(r"[\w.-]{1,40}", PUSH_V):
    sys.exit("ERROR: site.json > app.push.aviso_version no válido")
if PUSH_KEY:
    import base64
    try:
        _k = base64.urlsafe_b64decode(PUSH_KEY + "=" * (-len(PUSH_KEY) % 4)) if re.fullmatch(r"[A-Za-z0-9_-]+", PUSH_KEY) else b""
    except ValueError:
        _k = b""
    if len(_k) != 65 or _k[0] != 4:
        sys.exit("ERROR: site.json > app.push.clave_publica: la clave pública VAPID de la API (npm run push -- comprobar), 87 caracteres")
    if not PWA:
        sys.exit("ERROR: site.json > app.push necesita app.pwa = true (los avisos llegan al service worker de la web)")
PUSH_API = str(PUSH_CFG.get("api") or CAT_API).strip().rstrip("/")
if PUSH_KEY and not re.fullmatch(r"https://[a-z0-9.-]+(:\d+)?", PUSH_API):
    sys.exit("ERROR: site.json > app.push.api (o catalog.api): https://api.cliente.es, la API que envía los avisos")
STORES = APP.get("tiendas", {}) or {}
STORE_IOS = str(STORES.get("ios") or "").strip()
STORE_ANDROID = str(STORES.get("android") or "").strip()
if STORE_IOS and not re.fullmatch(r"https://apps\.apple\.com/[a-z]{2}/app/[\w%.-]+/?(id\d{6,12})?|https://apps\.apple\.com/[a-z]{2}/app/id\d{6,12}", STORE_IOS):
    sys.exit("ERROR: site.json > app.tiendas.ios: enlace de la ficha en https://apps.apple.com/es/app/…/id123456789")
if STORE_ANDROID and not re.fullmatch(r"https://play\.google\.com/store/apps/details\?id=[A-Za-z][\w.]+", STORE_ANDROID):
    sys.exit("ERROR: site.json > app.tiendas.android: enlace de la ficha en https://play.google.com/store/apps/details?id=…")
IOS = APP.get("ios", {}) or {}
IOS_APP_ID = str(IOS.get("app_id") or "").strip()            # TEAMID.bundle (enlaces universales)
IOS_STORE_ID = str(IOS.get("app_store_id") or "").strip()    # número de la ficha (banner de Safari)
IOS_PATHS = [str(x) for x in (IOS.get("rutas") or ["/*"])]
IOS_EXCLUDE = [str(x) for x in (IOS.get("excluir") or [])]
if IOS_APP_ID and not re.fullmatch(r"[A-Z0-9]{10}\.[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", IOS_APP_ID):
    sys.exit("ERROR: site.json > app.ios.app_id: identificador del equipo + bundle (ABCDE12345.es.cliente.app)")
if IOS_STORE_ID and not re.fullmatch(r"\d{6,12}", IOS_STORE_ID):
    sys.exit("ERROR: site.json > app.ios.app_store_id: el número de la ficha de App Store")
for _p in IOS_PATHS + IOS_EXCLUDE:
    if not re.fullmatch(r"/[A-Za-z0-9._~%/*?-]*", _p):
        sys.exit(f"ERROR: site.json > app.ios.rutas/excluir: rutas que empiezan por / (con * o ?): {_p!r}")
ANDROID = APP.get("android", {}) or {}
AND_PKG = str(ANDROID.get("paquete") or "").strip()
AND_FP = [str(x).strip().upper() for x in (ANDROID.get("huellas") or [])]
if AND_PKG and not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+", AND_PKG):
    sys.exit("ERROR: site.json > app.android.paquete: el applicationId de la app (es.cliente.app)")
if AND_PKG and not AND_FP:
    sys.exit("ERROR: site.json > app.android.huellas: la huella SHA-256 del certificado de firma de Play Console (Configuración > Firma de apps)")
if not all(re.fullmatch(r"([0-9A-F]{2}:){31}[0-9A-F]{2}", f) for f in AND_FP):
    sys.exit("ERROR: site.json > app.android.huellas: SHA-256 en formato AA:BB:… (32 pares)")
if AND_FP and not AND_PKG:
    sys.exit("ERROR: site.json > app.android: huellas sin paquete")
NATIVE = bool(STORE_IOS or STORE_ANDROID or IOS_APP_ID or AND_PKG)
# Iconos que genera tools/iconos.py (ruta en static/, lado en px).
APP_ICONS = [("app/icono-192.png", 192), ("app/icono-512.png", 512), ("app/icono-maskable-512.png", 512), ("app/apple-touch-icon.png", 180)]
# Privacidad (skill rgpd-tecnico-cliente): plazos y encargados, los mismos que config/rgpd.json de la plantilla C.
PRIV = CFG.get("privacidad", {}) or {}
PRIV_CONTACT_M = int(PRIV["contacto_meses"]) if PRIV.get("contacto_meses") is not None else 12
PRIV_ORDERS_Y = int(PRIV["pedidos_anios"]) if PRIV.get("pedidos_anios") is not None else 6
if not 1 <= PRIV_CONTACT_M <= 60:
    sys.exit("ERROR: site.json > privacidad.contacto_meses entre 1 y 60")
if not 6 <= PRIV_ORDERS_Y <= 10:
    sys.exit("ERROR: site.json > privacidad.pedidos_anios: 6 como mínimo (art. 30 del Código de Comercio) y 10 como máximo")
SERVICIOS = {
    "alojamiento": ("alojamiento de la web y del servidor", "website and server hosting"),
    "copias": ("copias de seguridad cifradas", "encrypted backups"),
    "email": ("envío de emails", "email delivery"),
    "pagos": ("pasarela de pago", "payment gateway"),
    "facturacion": ("programa de facturación", "invoicing software"),
    "medicion": ("medición de campañas", "campaign measurement"),
    "automatizaciones": ("automatización de avisos", "notification automation"),
    "mensajeria": ("entrega de pedidos", "order delivery"),
    "mantenimiento": ("mantenimiento técnico de la web", "website technical maintenance"),
    "whatsapp": ("mensajería por WhatsApp (Meta)", "WhatsApp messaging (Meta)"),
    "telefonia": ("telefonía del asistente telefónico (llamadas, transcripción y voz)", "phone assistant telephony (calls, transcription and voice)"),
    "notificaciones": ("avisos en la app (Firebase Cloud Messaging)", "app notifications (Firebase Cloud Messaging)"),
    "otro": ("otros servicios", "other services"),
}
ENCARGADOS = [e for e in (PRIV.get("encargados") or []) if isinstance(e, dict)]
for _e in ENCARGADOS:
    if _e.get("servicio") not in SERVICIOS or not str(_e.get("nombre") or "").strip() or not str(_e.get("pais") or "").strip():
        sys.exit(f"ERROR: site.json > privacidad.encargados: cada uno con servicio ({', '.join(SERVICIOS)}), nombre y pais: {_e}")
    if not all(re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d) for d in (_e.get("dominios") or [])):
        sys.exit(f"ERROR: site.json > privacidad.encargados[].dominios: solo nombres de dominio (cdn.ejemplo.com): {_e}")
_EEE = re.compile(r"\b(UE|EEE|Unión Europea|Espacio Económico Europeo|España|Irlanda|Alemania|Francia|Países Bajos|Holanda|Bélgica|Luxemburgo|Italia|"
                  r"Portugal|Austria|Suecia|Finlandia|Dinamarca|Polonia|Chequia|República Checa|Eslovaquia|Eslovenia|Croacia|Grecia|Chipre|Malta|Hungría|"
                  r"Rumanía|Bulgaria|Estonia|Letonia|Lituania|Noruega|Islandia|Liechtenstein)\b", re.I)


def in_eea(pais: str) -> bool:
    return bool(_EEE.search(pais or ""))


# Accesibilidad (skill accesibilidad-cliente): declaración generada desde site.json > accesibilidad.
A11Y = CFG.get("accesibilidad", {}) or {}
A11Y_STATE = (A11Y.get("estado") or "parcial").strip()
if A11Y_STATE not in ("total", "parcial", "no"):
    sys.exit("ERROR: site.json > accesibilidad.estado: total | parcial | no")
A11Y_DATE = (A11Y.get("fecha_evaluacion") or "").strip()
if A11Y_DATE:
    try:
        dt.date.fromisoformat(A11Y_DATE)
    except ValueError:
        sys.exit("ERROR: site.json > accesibilidad.fecha_evaluacion con formato AAAA-MM-DD")
A11Y_ISSUES = [x for x in (A11Y.get("problemas") or []) if isinstance(x, dict) and x.get("que")]
if A11Y_STATE == "total" and A11Y_ISSUES:
    sys.exit("ERROR: site.json > accesibilidad: estado «total» con problemas conocidos; usa «parcial»")
BOT_ON = bool(BOT.get("script", "").strip() and BOT.get("bot", "").strip())
# Proveedores de IA del asistente (chat y teléfono), en orden: principal y respaldo (plantilla-bot, docs/proveedores-ia.md).
# Opcional: sin ellos la privacidad habla de «un proveedor de inteligencia artificial» y de la transferencia de site.json.
IA_PROV = BOT.get("proveedores_ia") or []
if not isinstance(IA_PROV, list) or not all(isinstance(x, dict) and str(x.get("nombre") or "").strip() and str(x.get("pais") or "").strip() for x in IA_PROV):
    sys.exit("ERROR: site.json > chatbot.proveedores_ia: lista de {nombre, pais}, en orden (principal y respaldo)")
# Debe coincidir con LOG_CONVERSATIONS / CONVERSATION_RETENTION_DAYS del servidor del asistente.
_dias = int(BOT.get("conservacion_dias", 0) or 0)
BOT_RETENTION = {
    "es": f"se conservan de forma anonimizada durante {_dias} días para mejorar el servicio y después se borran" if _dias else "no se guardan una vez respondidas",
    "en": f"are kept in anonymised form for {_dias} days to improve the service and then deleted" if _dias else "are not stored once answered",
}
# Asistente al teléfono (plantilla-bot > voz; skill agente-voz-cliente): aviso junto al teléfono del contacto y párrafo de privacidad.
VOZ = CFG.get("asistente_voz", {}) or {}
VOZ_ON = bool(VOZ.get("activo"))
if VOZ_ON and not str(CO.get("phone") or "").strip():
    sys.exit("ERROR: site.json > asistente_voz.activo sin company.phone (el número en el que atiende el asistente)")
if BARRA_MOVIL and not CO.get("phone"):
    sys.exit("ERROR: site.json > barra_movil.activa sin company.phone (el número del botón Llamar)")
_vdias = VOZ.get("conservacion_dias", 0) or 0
if not isinstance(_vdias, int) or not 0 <= _vdias <= 90:
    sys.exit("ERROR: site.json > asistente_voz.conservacion_dias: número de días entre 0 y 90 (0 si LOG_CONVERSATIONS=none)")
VOZ_RETENTION = {
    "es": f"se conservan de forma anonimizada durante {_vdias} días para mejorar el servicio y después se borran" if _vdias else "no se guardan una vez terminada la llamada",
    "en": f"are kept in anonymised form for {_vdias} days to improve the service and then deleted" if _vdias else "are not stored once the call ends",
}

# ---------------------------------------------------------------------------
# Textos de interfaz (añade un idioma copiando un bloque)
# ---------------------------------------------------------------------------
T = {
    "es": {
        "skip": "Saltar al contenido", "menu": "Menú", "main_nav": "Principal",
        "blog": "Blog", "blog_title": "Blog", "blog_lead": "Novedades y artículos.",
        "read_more": "Leer más", "min_read": "{n} min de lectura", "published": "Publicado el {d}",
        "contact_h": "Contacto", "form_name": "Nombre", "form_email": "Email",
        "form_phone": "Teléfono (opcional)", "form_message": "Mensaje",
        "form_consent": "He leído y acepto la <a href=\"{url}\">política de privacidad</a>.",
        "form_info": "Responsable: {owner}. Finalidad: contestar tu mensaje. Base: tu consentimiento. Conservamos el mensaje {n} meses. Puedes ejercer tus derechos de acceso, rectificación, supresión y otros como se explica en la <a href=\"{url}\">política de privacidad</a>.",
        "ord_info": "Responsable: {owner}. Finalidad: gestionar tu pedido y su factura. Base: el contrato de compra y la obligación legal de facturar. El pago lo procesa la pasarela. Derechos y más información en la <a href=\"{url}\">política de privacidad</a>.",
        "form_send": "Enviar mensaje", "hours": "Horario", "address": "Dirección", "closures": "Próximos cierres",
        "phone": "Teléfono", "email": "Email",
        "thanks_title": "Mensaje enviado", "thanks_body": "Gracias por escribirnos. Te responderemos lo antes posible.",
        "back_home": "Volver al inicio",
        "notfound_title": "Página no encontrada",
        "notfound_body": "Esta dirección no existe o ha cambiado.",
        "legal_title": "Aviso legal", "privacy_title": "Política de privacidad", "a11y_title": "Accesibilidad",
        "all_rights": "Todos los derechos reservados.", "pending": "[pendiente]",
        "lang_name": "Español", "lang_short": "ES", "lang_avail": "Esta página también está en español.", "lang_view": "Ver en español", "lang_close": "Cerrar", "lang_region": "Idioma",
        "cat_search": "Buscar", "cat_category": "Categoría", "cat_all": "Todas", "cat_sort": "Ordenar",
        "cat_sort_rel": "Destacados", "cat_sort_up": "Precio: de menor a mayor", "cat_sort_down": "Precio: de mayor a menor",
        "prep_title": "Tu pedido preparado", "prep_lead": "Lo ha preparado el asistente de la web con lo que le pediste. Revísalo: no está hecho ni pagado hasta que pagues.",
        "prep_loading": "Cargando el pedido…", "prep_gone": "Este pedido preparado ha caducado o ya no existe. Puedes hacer el pedido desde el catálogo.",
        "prep_none": "No hay ningún pedido preparado en esta dirección. Puedes hacer el pedido desde el catálogo.", "prep_error": "No hemos podido cargar el pedido. Inténtalo de nuevo en un momento.",
        "prep_total": "Total (IVA incluido)", "prep_pay": "Ir al pago", "prep_prices": "Precios de hoy; si alguno ha cambiado desde que lo preparó el asistente, ves el actual.",
        "prep_nojs": "Para ver el pedido preparado hace falta JavaScript. También puedes hacer el pedido desde el catálogo.", "prep_items": "Productos",
        "cat_only_avail": "Solo disponibles", "cat_other": "Otros", "cat_out": "Agotado", "cat_buy": "Comprar",
        "cat_qty": "Cantidad", "cat_delivery": "Entrega", "cat_back": "Todos los productos", "cat_none": "No hay productos con esos filtros.",
        "cat_count": "{n} productos", "cat_gone": "Este producto ya no está a la venta.", "cat_vat": "IVA incluido",
        "cat_see": "Ver", "account": "Mis pedidos",
        "cookies_title": "Política de cookies", "cookies_config": "Configurar cookies",
        "inv_need": "Necesito factura a nombre de una empresa o autónomo", "inv_nif": "NIF", "inv_name": "Nombre o razón social",
        "inv_address": "Dirección", "inv_cp": "Código postal", "inv_city": "Ciudad",
        "news_email": "Tu email", "news_consent": "Quiero recibir el boletín de {name} con novedades y ofertas. Puedo darme de baja cuando quiera.",
        "news_send": "Suscribirme", "news_info": "Responsable: {owner}. Finalidad: enviarte el boletín. Base: tu consentimiento. Te pediremos que lo confirmes por email. Derechos y más información en la <a href=\"{url}\">política de privacidad</a>.",
        "news_thanks_title": "Revisa tu email", "news_thanks_body": "Te hemos enviado un enlace para confirmar la suscripción. Si no lo ves, mira en el correo no deseado.",
        "ord_news": "Quiero recibir novedades y ofertas por email",
        "ord_offers": "Como cliente, podremos enviarte por email ofertas de productos parecidos a los que compras. Si no quieres, marca esta casilla (también podrás darte de baja en cada email):",
        "ord_optout": "No quiero recibir ofertas",
        "ord_program": "Quiero unirme al programa de puntos y acepto sus <a href=\"{url}\" rel=\"noopener\">bases</a>",
        "ord_voucher": "Tengo un vale", "ord_voucher_code": "Código del vale", "ord_voucher_email": "Email del programa de puntos",
        "ord_wa": "Quiero recibir por WhatsApp los avisos de este pedido (preparado, enviado) en este móvil. Puedo darme de baja respondiendo BAJA.",
        "ord_wa_phone": "Móvil para los avisos por WhatsApp", "bar_call": "Llamar", "bar_label": "Contacto rápido", "pres_label": "Pide presupuesto", "pres_trabajo": "¿Qué trabajo es?", "pres_elige": "Elige uno", "pres_localidad": "Pueblo o zona de la obra", "pres_medidas": "Medidas aproximadas", "pres_medidas_ej": "p. ej. baño de 2 × 3 m", "pres_cuando": "¿Para cuándo?", "pres_sin_fecha": "Sin fecha concreta", "pres_nombre": "Tu nombre", "pres_nota": "Cuéntanos algo más", "pres_opcional": "(opcional)", "pres_wa": "Enviar por WhatsApp", "pres_email": "Prefiero enviarlo por email", "pres_info": "Este formulario no envía ni guarda nada: prepara el mensaje y lo mandas tú desde WhatsApp o desde tu correo. Las fotos puedes enviarlas en el mismo chat.", "pres_plazos": ["Lo antes posible", "En los próximos 3 meses", "Más adelante", "Solo quiero informarme"], "whatsapp": "WhatsApp", "wa_new": " (abre WhatsApp)",
        "phone_ai": "Puede atenderte un asistente automático con IA: di «persona» o pulsa 0 para hablar con el equipo.",
        "video_trans": "Texto del vídeo", "video_yt": "Ver el vídeo «{titulo}» en YouTube",
        "ord_push": "Quiero los avisos de este pedido (preparado, enviado) en este dispositivo. Puedo desactivarlos cuando quiera.",
        "push_blocked": "Los avisos están bloqueados en este navegador: actívalos en sus ajustes o compra sin ellos.",
        "push_off": "Dejar de recibir avisos en este dispositivo", "push_off_done": "Hecho: este dispositivo ya no recibirá avisos.",
        "offline_title": "Sin conexión", "offline_body": "No hay conexión a Internet. Cuando vuelva, abre de nuevo la página.",
        "offline_retry": "Volver a intentarlo", "offline_contact": "Si lo necesitas, puedes llamarnos o venir a vernos:",
        "app_ios": "App para iPhone (App Store)", "app_android": "App para Android (Google Play)",
    },
    "en": {
        "skip": "Skip to content", "menu": "Menu", "main_nav": "Main",
        "blog": "Blog", "blog_title": "Blog", "blog_lead": "News and articles.",
        "read_more": "Read more", "min_read": "{n} min read", "published": "Published {d}",
        "contact_h": "Contact", "form_name": "Name", "form_email": "Email",
        "form_phone": "Phone (optional)", "form_message": "Message",
        "form_consent": "I have read and accept the <a href=\"{url}\">privacy policy</a>.",
        "form_info": "Controller: {owner}. Purpose: replying to your message. Legal basis: your consent. We keep the message for {n} months. You can exercise your rights of access, rectification, erasure and others as explained in the <a href=\"{url}\">privacy policy</a>.",
        "ord_info": "Controller: {owner}. Purpose: handling your order and its invoice. Legal basis: the purchase contract and the legal obligation to invoice. Payment is processed by the payment provider. Rights and more information in the <a href=\"{url}\">privacy policy</a>.",
        "form_send": "Send message", "hours": "Opening hours", "address": "Address", "closures": "Upcoming closures",
        "phone": "Phone", "email": "Email",
        "thanks_title": "Message sent", "thanks_body": "Thank you for getting in touch. We will reply as soon as possible.",
        "back_home": "Back to home",
        "notfound_title": "Page not found",
        "notfound_body": "This address does not exist or has changed.",
        "legal_title": "Legal notice", "privacy_title": "Privacy policy", "a11y_title": "Accessibility",
        "all_rights": "All rights reserved.", "pending": "[pending]",
        "lang_name": "English", "lang_short": "EN", "lang_avail": "This page is also available in English.", "lang_view": "View in English", "lang_close": "Close", "lang_region": "Language",
        "cat_search": "Search", "cat_category": "Category", "cat_all": "All", "cat_sort": "Sort by",
        "cat_sort_rel": "Featured", "cat_sort_up": "Price: low to high", "cat_sort_down": "Price: high to low",
        "prep_title": "Your prepared order", "prep_lead": "The website assistant prepared it with what you asked for. Check it: it isn't placed or paid until you pay.",
        "prep_loading": "Loading the order…", "prep_gone": "This prepared order has expired or no longer exists. You can order from the catalogue.",
        "prep_none": "There is no prepared order at this address. You can order from the catalogue.", "prep_error": "We couldn't load the order. Please try again in a moment.",
        "prep_total": "Total (VAT included)", "prep_pay": "Go to payment", "prep_prices": "Today's prices; if any has changed since the assistant prepared it, you see the current one.",
        "prep_nojs": "You need JavaScript to see the prepared order. You can also order from the catalogue.", "prep_items": "Products",
        "cat_only_avail": "In stock only", "cat_other": "Other", "cat_out": "Sold out", "cat_buy": "Buy",
        "cat_qty": "Quantity", "cat_delivery": "Delivery", "cat_back": "All products", "cat_none": "No products match these filters.",
        "cat_count": "{n} products", "cat_gone": "This product is no longer available.", "cat_vat": "VAT included",
        "cat_see": "View", "account": "My orders",
        "cookies_title": "Cookie policy", "cookies_config": "Cookie settings",
        "inv_need": "I need an invoice for a company or self-employed person", "inv_nif": "Tax ID (NIF)", "inv_name": "Name or company name",
        "inv_address": "Address", "inv_cp": "Postcode", "inv_city": "City",
        "news_email": "Your email", "news_consent": "I want to receive {name}'s newsletter with news and offers. I can unsubscribe at any time.",
        "news_send": "Subscribe", "news_info": "Controller: {owner}. Purpose: sending you the newsletter. Legal basis: your consent. We will ask you to confirm by email. Rights and more information in the <a href=\"{url}\">privacy policy</a>.",
        "news_thanks_title": "Check your email", "news_thanks_body": "We have sent you a link to confirm your subscription. If you can't see it, check your spam folder.",
        "ord_news": "I want to receive news and offers by email",
        "ord_offers": "As a customer, we may email you offers for products similar to those you buy. If you don't want this, tick this box (you can also unsubscribe from any email):",
        "ord_optout": "I don't want to receive offers",
        "ord_program": "I want to join the loyalty programme and accept its <a href=\"{url}\" rel=\"noopener\">terms</a>",
        "ord_voucher": "I have a voucher", "ord_voucher_code": "Voucher code", "ord_voucher_email": "Loyalty programme email",
        "ord_wa": "Send me updates about this order (ready, shipped) by WhatsApp to this mobile number. I can opt out by replying STOP.",
        "ord_wa_phone": "Mobile number for WhatsApp updates", "bar_call": "Call", "bar_label": "Quick contact", "pres_label": "Request a quote", "pres_trabajo": "What kind of job?", "pres_elige": "Choose one", "pres_localidad": "Town or area of the job", "pres_medidas": "Approximate size", "pres_medidas_ej": "e.g. 2 × 3 m bathroom", "pres_cuando": "When?", "pres_sin_fecha": "No set date", "pres_nombre": "Your name", "pres_nota": "Anything else", "pres_opcional": "(optional)", "pres_wa": "Send on WhatsApp", "pres_email": "I prefer email", "pres_info": "This form does not send or store anything: it prepares the message and you send it yourself from WhatsApp or your email. You can send photos in the same chat.", "pres_plazos": ["As soon as possible", "In the next 3 months", "Later on", "Just looking for information"], "whatsapp": "WhatsApp", "wa_new": " (opens WhatsApp)",
        "phone_ai": "An automated AI assistant may answer: say “person” or press 0 to speak to the team.",
        "video_trans": "Video transcript", "video_yt": "Watch the video “{titulo}” on YouTube",
        "ord_push": "Send me updates about this order (ready, shipped) on this device. I can turn them off at any time.",
        "push_blocked": "Notifications are blocked in this browser: allow them in its settings or buy without them.",
        "push_off": "Stop notifications on this device", "push_off_done": "Done: this device will no longer receive notifications.",
        "offline_title": "You're offline", "offline_body": "There is no Internet connection. When it's back, open the page again.",
        "offline_retry": "Try again", "offline_contact": "If you need us, you can call or visit:",
        "app_ios": "iPhone app (App Store)", "app_android": "Android app (Google Play)",
    },
}
MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"],
}
SLUGS = {  # rutas de páginas generadas automáticamente
    "es": {"legal": "aviso-legal", "privacy": "privacidad", "thanks": "gracias", "blog": "blog", "cookies": "politica-cookies", "news_thanks": "boletin-revisa-tu-email",
           "accessibility": "accesibilidad", "offline": "sin-conexion", "order": "pedido"},
    "en": {"legal": "legal-notice", "privacy": "privacy", "thanks": "thanks", "blog": "blog", "cookies": "cookie-policy", "news_thanks": "newsletter-check-your-email",
           "accessibility": "accessibility", "offline": "offline", "order": "order"},
}


def t(lang: str) -> dict:
    return T.get(lang, T["en"])


def slugs(lang: str) -> dict:
    return SLUGS.get(lang, SLUGS["en"])


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def fmt_date(iso: str, lang: str) -> str:
    d = dt.date.fromisoformat(iso)
    if lang in MONTHS:
        return f"{d.day} de {MONTHS[lang][d.month - 1]} de {d.year}"
    return f"{d.day} {d.strftime('%B')} {d.year}"


def slugify(value: str, separator: str = "-") -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[\s_-]+", separator, value)


# ---------------------------------------------------------------------------
# Carga de contenido
# ---------------------------------------------------------------------------
def unquote(v: str) -> str:
    """Valores de la cabecera entre comillas, como los guarda un CMS: "Título: con dos puntos" → Título: con dos puntos."""
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            return str(json.loads(v))
        except ValueError:
            return v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def parse_md(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    m = FM_RE.match(raw)
    if not m:
        sys.exit(f"ERROR: falta la cabecera --- en {path}")
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = unquote(v.strip())
    meta["body"] = m.group(2)
    meta["path"] = path
    return meta


pages: dict[str, dict[str, dict]] = {l: {} for l in LANGS}
posts: dict[str, dict[str, dict]] = {l: {} for l in LANGS}
for lang in LANGS:
    for p in sorted((CONTENT / lang).glob("*.md")):
        pg = parse_md(p)
        pg.setdefault("key", p.stem)
        pg.setdefault("slug", "" if pg["key"] == "home" else p.stem)
        pg["lang"] = lang
        pages[lang][pg["key"]] = pg
    for p in sorted((CONTENT / lang / "blog").glob("*.md")) if (CONTENT / lang / "blog").exists() else []:
        po = parse_md(p)
        po.setdefault("key", p.stem)
        po.setdefault("slug", p.stem)
        po["lang"] = lang
        if po.get("draft") == "true":
            continue
        posts[lang][po["key"]] = po
    if "home" not in pages[lang]:
        sys.exit(f"ERROR: falta content/{lang}/home.md")


# ---------------------------------------------------------------------------
# Catálogo (opcional): productos desde la API de la plantilla C o un JSON local
# ---------------------------------------------------------------------------
SKU_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CAT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
IMG_RE = re.compile(r"^(https://[^\s\"'<>]+|[a-z0-9][a-z0-9/_.-]*\.(webp|jpe?g|png|avif))$", re.I)
RESERVED_SKUS = {"categoria"}


def load_catalog() -> dict | None:
    """Lee y valida el catálogo. Cualquier dato raro detiene la generación: mejor no publicar que publicar mal."""
    src = (CAT.get("source") or "").strip()
    if not src:
        return None
    if src.startswith("http://"):
        sys.exit("ERROR: catalog.source debe ser https://")
    if src.startswith("https://"):
        import urllib.request
        try:
            req = urllib.request.Request(src, headers={"Accept": "application/json", "User-Agent": "plantilla-a"})
            with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (https comprobado arriba)
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # sin catálogo no se publica: la web anterior sigue en pie
            sys.exit(f"ERROR: no se pudo descargar el catálogo de {src}: {e}")
    else:
        path = (ROOT / src).resolve()
        if ROOT not in path.parents or not path.exists():
            sys.exit(f"ERROR: no existe el catálogo {src}")
        data = json.loads(path.read_text(encoding="utf-8"))
    prods = data.get("productos")
    if not isinstance(prods, list):
        sys.exit("ERROR: el catálogo no tiene la lista «productos»")
    if not prods and not CAT.get("permitir_vacio"):
        sys.exit("ERROR: el catálogo está vacío. Si es intencionado, catalog.permitir_vacio = true")
    seen, errs = set(), []
    for i, p in enumerate(prods):
        sku = p.get("sku")
        if not isinstance(sku, str) or not SKU_RE.match(sku) or sku in RESERVED_SKUS or sku in seen:
            errs.append(f"producto {i + 1}: SKU no válido o repetido «{sku}»")
            continue
        seen.add(sku)
        if not isinstance(p.get("name"), str) or not p["name"].strip() or len(p["name"]) > 120:
            errs.append(f"{sku}: nombre no válido")
        if not isinstance(p.get("price_cents"), int) or isinstance(p.get("price_cents"), bool) or p["price_cents"] <= 0:
            errs.append(f"{sku}: precio no válido")
        img = p.get("image") or ""
        if img and (not IMG_RE.match(img) or ".." in img):
            errs.append(f"{sku}: imagen no válida «{img}»")
        if p.get("category") is not None and not (isinstance(p["category"], str) and CAT_RE.match(p["category"])):
            errs.append(f"{sku}: categoría no válida")
        if not isinstance(p.get("attrs", {}), dict):
            errs.append(f"{sku}: atributos no válidos")
        p.setdefault("description", "")
        p.setdefault("attrs", {})
        p["disponible"] = p.get("disponible", True) is not False
    if errs:
        sys.exit("ERROR: catálogo con datos no válidos:\n  " + "\n  ".join(errs))
    # Una foto que aún no está en static/ no debe bloquear la publicación de precios: se publica sin foto y se avisa.
    for p in prods:
        if p.get("image") and not p["image"].startswith("https://") and not (STATIC / p["image"]).is_file():
            print(f"AVISO: {p['sku']}: falta static/{p['image']}; se publica sin foto")
            p["image"] = ""
    cats = [c for c in data.get("categorias", []) if isinstance(c, dict) and CAT_RE.match(str(c.get("slug", "")))]
    return {"productos": prods, "categorias": cats}


CATALOG = load_catalog()
CAT_PAGE = (CAT.get("page") or "productos").strip()
# Idiomas con catálogo: los que tienen la página con el bloque :::catalogo (los textos de los productos están en un solo idioma).
CAT_LANGS = [l for l in LANGS if CAT_PAGE in pages[l] and ":::catalogo" in pages[l][CAT_PAGE]["body"]]
if CATALOG is not None and not CAT_LANGS:
    sys.exit(f"ERROR: catalog.page = «{CAT_PAGE}» pero ninguna content/<idioma>/{CAT_PAGE}.md tiene el bloque :::catalogo")


def money(cents: int, lang: str) -> str:
    v = f"{cents / 100:,.2f}"
    if lang == "en":
        return f"€{v}"
    return v.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()).strip()


def product_url(sku: str, lang: str) -> str:
    return url_for(CAT_PAGE, lang) + sku + "/"


def category_url(slug: str, lang: str) -> str:
    return url_for(CAT_PAGE, lang) + "categoria/" + slug + "/"


def img_src(img: str) -> str:
    return img if img.startswith("https://") else "/" + img.lstrip("/")


# ---------------------------------------------------------------------------
# Fotos y vídeo (skill fotografia-video-cliente)
# ---------------------------------------------------------------------------
def image_size(path: Path) -> tuple[int, int] | None:
    """Ancho y alto de un PNG, JPEG, WebP o GIF leyendo solo la cabecera (sin Pillow). None si no se reconoce."""
    try:
        with open(path, "rb") as fh:
            d = fh.read(64 * 1024)
    except OSError:
        return None
    if d[:8] == b"\x89PNG\r\n\x1a\n" and d[12:16] == b"IHDR":
        return int.from_bytes(d[16:20], "big"), int.from_bytes(d[20:24], "big")
    if d[:6] in (b"GIF87a", b"GIF89a"):
        return int.from_bytes(d[6:8], "little"), int.from_bytes(d[8:10], "little")
    if d[:4] == b"RIFF" and d[8:12] == b"WEBP":
        c = d[12:16]
        if c == b"VP8X":
            return 1 + int.from_bytes(d[24:27], "little"), 1 + int.from_bytes(d[27:30], "little")
        if c == b"VP8 " and d[23:26] == b"\x9d\x01\x2a":
            return int.from_bytes(d[26:28], "little") & 0x3FFF, int.from_bytes(d[28:30], "little") & 0x3FFF
        if c == b"VP8L" and d[20] == 0x2F:
            b = int.from_bytes(d[21:25], "little")
            return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
        return None
    if d[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(d):
            if d[i] != 0xFF:
                i += 1
                continue
            marker = d[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = int.from_bytes(d[i + 2:i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                return int.from_bytes(d[i + 7:i + 9], "big"), int.from_bytes(d[i + 5:i + 7], "big")
            i += 2 + seg
    return None


# Ancho de cada sitio de la plantilla (style.css): texto 46rem, portada media columna desde 52rem, tarjetas un tercio de 72rem.
SIZES = {"prose": "(max-width: 46rem) 100vw, 46rem", "hero": "(max-width: 52rem) 100vw, 36rem", "card": "(max-width: 52rem) 100vw, 24rem"}
_VARIANT = re.compile(r"-(\d{2,4})$")


def responsive(tag: str, where: str = "prose") -> str:
    """Añade width y height (la página no salta al cargar) y, si existen las variantes que hace tools/images.py --variantes
    (foto-480.webp, foto-960.webp…), srcset y sizes para que el móvil descargue la pequeña."""
    m = re.search(r'\ssrc="(/[^"?#]+)"', tag)
    if not m or re.search(r"\swidth=", tag):
        return tag
    src = m.group(1)
    f = STATIC / src.lstrip("/")
    if f.suffix.lower() in (".mp4", ".webm") and f.is_file():
        # Vídeo corto de obra con ![texto](/video/x.mp4): se reproduce al pulsarlo (nada se mueve solo), sin sonido y sin
        # descargar nada hasta entonces. Necesita un fotograma con el mismo nombre (x.webp o x.jpg) para medidas y portada.
        poster = next((f.with_suffix(e) for e in (".webp", ".jpg") if f.with_suffix(e).is_file()), None)
        dims = image_size(poster) if poster else None
        if not dims:
            sys.exit(f"ERROR: el vídeo {src} necesita su fotograma de portada {Path(src).with_suffix('.webp')} (o .jpg)")
        alt = re.search(r'\salt="([^"]*)"', tag)
        etiqueta = f' aria-label="{alt.group(1)}"' if alt and alt.group(1) else ""
        tipo = "video/mp4" if f.suffix.lower() == ".mp4" else "video/webm"
        psrc = "/" + poster.relative_to(STATIC).as_posix()
        # Sin pista de sonido (caja hdlr de tipo «soun» en el MP4) no hacen falta subtítulos: se marca para check.py (WCAG 1.2.2).
        sin_voz = "" if re.search(rb"hdlr.{8}soun", f.read_bytes(), re.S) else " data-sin-voz"
        return (f'<video controls muted playsinline preload="none" poster="{psrc}" width="{dims[0]}" height="{dims[1]}"{etiqueta}{sin_voz}>'
                f'<source src="{src}" type="{tipo}"></video>')
    if f.suffix.lower() == ".svg" and f.is_file():
        # SVG (mapas, esquemas): el tamaño sale del viewBox; sin variantes, se ve nítido a cualquier ancho.
        vb = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', f.read_text(encoding="utf-8", errors="ignore")[:2000])
        if vb:
            return tag[:-1].rstrip("/").rstrip() + f' width="{round(float(vb.group(1)))}" height="{round(float(vb.group(2)))}"' + (" />" if tag.endswith("/>") else ">")
        return tag
    if f.suffix.lower() not in (".webp", ".jpg", ".jpeg", ".png", ".gif") or not f.is_file():
        return tag
    wh = image_size(f)
    if not wh:
        return tag
    extra = f' width="{wh[0]}" height="{wh[1]}"'
    variants = []
    for v in f.parent.glob(f"{f.stem}-*{f.suffix}"):
        n = _VARIANT.search(v.stem)
        vw = image_size(v)
        if n and vw and v.stem == f"{f.stem}-{n.group(1)}" and vw[0] < wh[0]:
            variants.append((vw[0], "/" + v.relative_to(STATIC).as_posix()))
    if variants and "srcset=" not in tag:
        srcset = ", ".join(f"{u} {w}w" for w, u in sorted(variants)) + f", {src} {wh[0]}w"
        extra += f' srcset="{esc(srcset)}" sizes="{SIZES[where]}"'
    return tag[:-1].rstrip("/").rstrip() + extra + (" />" if tag.endswith("/>") else ">")


def responsive_all(h: str, where: str = "prose") -> str:
    return re.sub(r"<img\s[^>]*>", lambda m: responsive(m.group(0), where), h)


VIDEO_MAX_MB, VIDEO_AVISO_MB = 30, 15
LANG_LABEL = {"es": "Español", "en": "English", "fr": "Français", "de": "Deutsch", "it": "Italiano", "pt": "Português", "ca": "Català",
              "eu": "Euskara", "gl": "Galego", "nl": "Nederlands"}
VIDEO_KEYS = {"archivo", "poster", "subtitulos", "titulo", "transcripcion", "sin_voz", "youtube", "idioma"}


def video_block(inner: str, lang: str) -> str:
    """:::video con un vídeo propio (MP4/WebM servido desde la web, con subtítulos obligatorios si tiene voz) o, con «youtube:», una
    imagen propia que enlaza al vídeo de YouTube (no se carga nada de Google hasta que la persona hace clic)."""
    v = {}
    for line in inner.strip().splitlines():
        if not line.strip():
            continue
        k, sep, val = line.partition(":")
        k = k.strip().lower()
        if not sep or k not in VIDEO_KEYS:
            sys.exit(f"ERROR: :::video: línea no válida «{line.strip()}» (claves: {', '.join(sorted(VIDEO_KEYS))})")
        v[k] = val.strip()
    titulo = v.get("titulo", "")
    if not titulo:
        sys.exit("ERROR: :::video sin «titulo:» (se usa como nombre del vídeo para los lectores de pantalla)")

    def local(key: str, exts: tuple[str, ...]) -> Path:
        rel = v.get(key, "")
        if not rel or rel.startswith(("http:", "https:", "//")) or ".." in rel:
            sys.exit(f"ERROR: :::video «{titulo}»: falta «{key}:» con un archivo de static/ ({'/'.join(exts)})")
        f = STATIC / rel.lstrip("/")
        if f.suffix.lower() not in exts:
            sys.exit(f"ERROR: :::video «{titulo}»: «{key}» tiene que ser {'/'.join(exts)}: {rel}")
        if not f.is_file():
            sys.exit(f"ERROR: :::video «{titulo}»: no existe static/{rel.lstrip('/')}")
        return f

    poster = local("poster", (".webp", ".jpg", ".jpeg", ".png"))
    poster_tag = responsive(f'<img src="/{poster.relative_to(STATIC).as_posix()}" alt="">', "prose")
    cap = f"<figcaption>{esc(titulo)}</figcaption>"
    trans = v.get("transcripcion", "")
    if trans:
        href = url_for(trans[1:], lang) if trans.startswith("@") else ""
        if not href:
            sys.exit(f"ERROR: :::video «{titulo}»: «transcripcion:» es la clave de una página con el texto del vídeo (@clave)")
        cap = f'<figcaption>{esc(titulo)} · <a href="{href}">{t(lang)["video_trans"]}</a></figcaption>'
    yt = v.get("youtube", "")
    if yt:
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", yt):
            sys.exit(f"ERROR: :::video «{titulo}»: «youtube:» es el identificador de 11 caracteres del vídeo (lo que va tras v=)")
        if "archivo" in v:
            sys.exit(f"ERROR: :::video «{titulo}»: o «archivo:» (vídeo propio) o «youtube:», no los dos")
        img = poster_tag.replace(' alt=""', f' alt="{esc(t(lang)["video_yt"].format(titulo=titulo))}"', 1).replace("<img ", '<img loading="lazy" decoding="async" ', 1)
        return (f'<section class="section wrap prose"><figure class="video video-ext"><a href="https://www.youtube.com/watch?v={yt}" rel="noopener">'
                f'{img}<span class="play" aria-hidden="true"></span></a>{cap}</figure></section>')
    f = local("archivo", (".mp4", ".webm"))
    mb = f.stat().st_size / 1e6
    if mb > VIDEO_MAX_MB:
        sys.exit(f"ERROR: :::video «{titulo}»: {mb:.0f} MB; más de {VIDEO_MAX_MB} MB no se sirve desde la web "
                 "(comprimirlo con python tools/video.py o publicarlo en YouTube con «youtube:»)")
    if mb > VIDEO_AVISO_MB:
        print(f"AVISO: :::video «{titulo}»: {mb:.0f} MB; mejor por debajo de {VIDEO_AVISO_MB} MB (python tools/video.py)")
    sin_voz = v.get("sin_voz", "").lower() in ("true", "sí", "si", "1")
    track = ""
    if "subtitulos" in v:
        vtt = local("subtitulos", (".vtt",))
        if not vtt.read_text(encoding="utf-8-sig", errors="replace").startswith("WEBVTT"):
            sys.exit(f"ERROR: :::video «{titulo}»: {vtt.name} no es WebVTT (tiene que empezar por «WEBVTT»)")
        sl = v.get("idioma", lang)
        track = (f'<track kind="captions" src="/{vtt.relative_to(STATIC).as_posix()}" srclang="{esc(sl)}" '
                 f'label="{esc(LANG_LABEL.get(sl, sl))}" default>')
    elif not sin_voz:
        sys.exit(f"ERROR: :::video «{titulo}»: sin «subtitulos:» (archivo .vtt). Si el vídeo no tiene voz ni sonido que informe, "
                 "«sin_voz: true» (WCAG 1.2.2)")
    wh = image_size(poster) or (0, 0)
    dims = f' width="{wh[0]}" height="{wh[1]}"' if wh[0] else ""
    typ = "video/mp4" if f.suffix.lower() == ".mp4" else "video/webm"
    return (f'<section class="section wrap prose"><figure class="video"><video controls preload="none" playsinline'
            f' poster="/{poster.relative_to(STATIC).as_posix()}"{dims} aria-label="{esc(titulo)}"{" data-sin-voz" if sin_voz and not track else ""}>'
            f'<source src="/{f.relative_to(STATIC).as_posix()}" type="{typ}">{track}</video>{cap}</figure></section>')


def text_paragraphs(text: str) -> str:
    """La descripción es texto plano: se escapa siempre (no se interpreta HTML ni Markdown que llegue de la base de datos)."""
    return "".join(f"<p>{esc(par).replace(chr(10), '<br>')}</p>" for par in re.split(r"\n\s*\n", text.strip()) if par.strip())


def product_card(p: dict, lang: str, level: int = 3) -> str:
    """level: nivel del encabezado del producto (3 bajo el <h2> de su categoría; 2 en la página de una categoría)."""
    tt = t(lang)
    u = product_url(p["sku"], lang)
    img = (f'<a href="{u}" tabindex="-1" aria-hidden="true">{responsive(f"""<img src="{esc(img_src(p["image"]))}" alt="" loading="lazy" decoding="async">""", "card")}</a>'
           if p["image"] else "")
    short = p["description"].strip().split("\n")[0]
    short = (short[:137] + "…") if len(short) > 140 else short
    search = norm(" ".join([p["name"], p["description"], p.get("category") or ""] + [str(v) for v in p["attrs"].values()]))
    out = "" if p["disponible"] else f'<p class="out">{tt["cat_out"]}</p>'
    return (f'<article class="card product" data-sku="{esc(p["sku"])}" data-search="{esc(search)}" data-cat="{esc(p.get("category") or "")}" '
            f'data-price="{p["price_cents"]}" data-disp="{1 if p["disponible"] else 0}">{img}'
            f'<h{level}><a href="{u}">{esc(p["name"])}</a></h{level}><p class="price">{money(p["price_cents"], lang)}</p>{out}'
            f'{f"<p>{esc(short)}</p>" if short else ""}</article>')


def catalog_groups() -> list[tuple[dict | None, list[dict]]]:
    by: dict[str, list[dict]] = {}
    for p in CATALOG["productos"]:
        by.setdefault(p.get("category") or "", []).append(p)
    groups = [(c, by.pop(c["slug"])) for c in sorted(CATALOG["categorias"], key=lambda c: (c.get("sort", 0), c["name"])) if c["slug"] in by]
    rest = [p for ps in by.values() for p in ps]
    if rest:
        groups.append((None, rest))
    return groups


def catalog_block(lang: str) -> str:
    """Listado agrupado por categoría. Sin JavaScript se ve todo; con él, buscador, filtros y precios al día."""
    tt = t(lang)
    groups = catalog_groups()
    named = [c for c, _ in groups if c]
    opts = "".join(f'<option value="{esc(c["slug"])}">{esc(c["name"])}</option>' for c in named)
    tools = (f'<form class="catalog-tools" role="search" hidden>'
             f'<label>{tt["cat_search"]}<input type="search" name="q" autocomplete="off"></label>'
             + (f'<label>{tt["cat_category"]}<select name="cat"><option value="">{tt["cat_all"]}</option>{opts}</select></label>' if named else "")
             + f'<label>{tt["cat_sort"]}<select name="orden"><option value="">{tt["cat_sort_rel"]}</option>'
             f'<option value="up">{tt["cat_sort_up"]}</option><option value="down">{tt["cat_sort_down"]}</option></select></label>'
             f'<label class="check"><input type="checkbox" name="disp"> {tt["cat_only_avail"]}</label></form>'
             f'<p class="catalog-count" aria-live="polite" hidden data-template="{esc(tt["cat_count"])}" data-none="{esc(tt["cat_none"])}"></p>')
    if CAT.get("por_categoria") and named:
        cards = "".join(f'<article class="card"><h2><a href="{category_url(c["slug"], lang)}">{esc(c["name"])}</a></h2>'
                        f'<p class="meta">{tt["cat_count"].format(n=len(ps))}</p></article>' for c, ps in groups if c)
        return f'<section class="section wrap"><div class="cards">{cards}</div></section>'
    body = "".join(
        f'<div class="product-group" data-group="{esc(c["slug"] if c else "")}">'
        f'<h2 id="{esc("cat-" + (c["slug"] if c else "otros"))}">{esc(c["name"] if c else tt["cat_other"])}</h2>'
        f'<div class="cards products">{"".join(product_card(p, lang) for p in ps)}</div></div>'
        for c, ps in groups)
    return (f'<section class="section wrap catalog" data-lang="{lang}"{API_ATTR}>{tools}{body}'
            f'<div class="cards products sorted" hidden></div></section>')


def prefix(lang: str) -> str:
    return "/" if lang == DEFAULT else f"/{lang}/"


def url_for(key: str, lang: str) -> str:
    p = prefix(lang)
    if key == "home":
        return p
    if key in ("legal", "privacy", "thanks", "blog", "cookies", "news_thanks", "accessibility", "offline", "order"):
        return p + slugs(lang)[key] + "/"
    if key in pages[lang]:
        return p + pages[lang][key]["slug"] + "/"
    if key in posts[lang]:
        return p + slugs(lang)["blog"] + "/" + posts[lang][key]["slug"] + "/"
    sys.exit(f"ERROR: enlace a @{key} sin página en '{lang}'")


def exists_in(key: str, lang: str) -> bool:
    if key in ("home", "legal", "privacy", "accessibility"):
        return True
    if key == "thanks":
        return bool(FORM)
    if key == "cookies":
        return MED_ON
    if key == "news_thanks":
        return bool(NEWS)
    if key == "offline":
        return PWA
    if key == "order":
        return ASISTENTE and lang in CAT_LANGS
    if key == "blog":
        return bool(posts[lang])
    return key in pages[lang] or key in posts[lang]


def alternates(key: str) -> dict[str, str]:
    return {l: url_for(key, l) for l in LANGS if exists_in(key, l)}


# ---------------------------------------------------------------------------
# Markdown y bloques
# ---------------------------------------------------------------------------
def md(text: str, lang: str) -> str:
    text = re.sub(r"\]\(@([a-z0-9-]+)(#[a-z0-9-]+)?\)",
                  lambda m: f"]({url_for(m.group(1), lang)}{m.group(2) or ''})", text)
    conv = markdown.Markdown(extensions=["extra", "sane_lists", "smarty", "toc"],
                             extension_configs={"toc": {"slugify": slugify}})
    out = conv.convert(text)
    out = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" rel="noopener"', out)
    out = re.sub(r"<img ", '<img loading="lazy" decoding="async" ', out)
    return out


def as_buttons(h: str) -> str:
    """Párrafos que solo contienen enlaces -> fila de botones."""
    def rep(m):
        inner = m.group(1)
        if re.fullmatch(r"\s*(<a [^>]+>[^<]+</a>\s*)+", inner):
            links = re.findall(r"<a [^>]+>[^<]+</a>", inner)
            btns = []
            for i, a in enumerate(links):
                cls = "btn" if i == 0 else "btn btn-ghost"
                btns.append(a.replace("<a ", f'<a class="{cls}" ', 1))
            return '<p class="actions">' + "".join(btns) + "</p>"
        return m.group(0)
    return re.sub(r"<p>(.*?)</p>", rep, h, flags=re.S)


def upcoming_closures(days: int = 90) -> list[dict]:
    """Cierres que no han terminado y empiezan en los próximos `days` días."""
    return [c for c in CIERRES if c["hasta"] >= HOY and c["desde"] <= HOY + dt.timedelta(days=days)]


def closure_text(c: dict, lang: str) -> str:
    """«24 de diciembre – 26 de diciembre: Navidad» (o un solo día)."""
    def day(d: dt.date) -> str:
        if lang == "es":
            return f"{d.day} de {MONTHS['es'][d.month - 1]}"
        return d.strftime("%-d %B")
    span = day(c["desde"]) if c["desde"] == c["hasta"] else f"{day(c['desde'])} – {day(c['hasta'])}"
    m = c["motivo"].get(lang) or c["motivo"].get(DEFAULT) or "" if isinstance(c["motivo"], dict) else str(c["motivo"])
    return f"{span}: {m}" if m else span


def presupuesto_block(lang: str) -> str:
    """Formulario que prepara la solicitud de presupuesto como mensaje de WhatsApp (o email). Sin envío ni almacenamiento: los enlaces
    funcionan sin JavaScript (abren el chat vacío) y static/presupuesto.js les añade el texto escrito, codificado para la URL."""
    tt = t(lang)
    # trabajos y plazos: una lista, o una por idioma ({"es": [...], "en": [...]}) cuando la web tiene varios.
    por_idioma = lambda v: v.get(lang) if isinstance(v, dict) else v
    trabajos = por_idioma(PRES.get("trabajos"))
    if not isinstance(trabajos, list) or not trabajos or not all(isinstance(x, str) and x.strip() for x in trabajos):
        sys.exit(f"ERROR: :::presupuesto necesita site.json > presupuesto.trabajos para «{lang}» (lista de trabajos del cliente, "
                 "o una por idioma: {\"es\": [...], \"en\": [...]})")
    if not WA_NUM and not CO.get("email"):
        sys.exit("ERROR: :::presupuesto necesita company.whatsapp o company.email (a dónde se manda el mensaje)")
    plazos = por_idioma(PRES.get("plazos")) or tt["pres_plazos"]
    opt = lambda xs: "".join(f'<option>{esc(x)}</option>' for x in xs)
    o = tt["pres_opcional"]
    acciones = []
    if WA_NUM:
        acciones.append(f'<a class="btn pres-wa" href="https://wa.me/{WA_NUM.lstrip("+")}">{tt["pres_wa"]}<span class="sr">{tt["wa_new"]}</span></a>')
    if CO.get("email"):
        acciones.append(f'<a class="btn{" btn-ghost" if acciones else ""} pres-email" href="mailto:{esc(CO["email"])}">{tt["pres_email"] if acciones else tt["email"]}</a>')
    return f"""<form class="contact-form pres-form" aria-label="{tt['pres_label']}" data-lang="{lang}" data-wa="{esc(WA_NUM.lstrip('+'))}" data-email="{esc(CO.get('email', ''))}">
  <label>{tt['pres_trabajo']}<select name="trabajo"><option value="">{tt['pres_elige']}</option>{opt(trabajos)}</select></label>
  <label>{tt['pres_localidad']}<input type="text" name="localidad" maxlength="80" autocomplete="address-level2"></label>
  <label><span>{tt['pres_medidas']} <span class="opt">{o}</span></span><input type="text" name="medidas" maxlength="80" placeholder="{tt['pres_medidas_ej']}"></label>
  <label>{tt['pres_cuando']}<select name="cuando"><option value="">{tt['pres_sin_fecha']}</option>{opt(plazos)}</select></label>
  <label><span>{tt['pres_nombre']} <span class="opt">{o}</span></span><input type="text" name="nombre" maxlength="80" autocomplete="name"></label>
  <label><span>{tt['pres_nota']} <span class="opt">{o}</span></span><textarea name="nota" maxlength="1000" rows="4"></textarea></label>
  <p class="actions">{''.join(acciones)}</p>
  <p class="pres-info">{tt['pres_info']} <a href="{url_for('privacy', lang)}">{tt['privacy_title']}</a>.</p>
</form>"""


def contact_block(lang: str) -> str:
    tt = t(lang)
    info = []
    if CO.get("address"):
        info.append(f'<dt>{tt["address"]}</dt><dd>{esc(CO["address"])}</dd>')
    if CO.get("phone"):
        tel = re.sub(r"[^\d+]", "", CO["phone"])
        info.append(f'<dt>{tt["phone"]}</dt><dd><a href="tel:{tel}">{esc(CO["phone"])}</a></dd>'
                    + (f'<dd class="phone-ai">{tt["phone_ai"]}</dd>' if VOZ_ON else ""))
    if CO.get("email"):
        info.append(f'<dt>{tt["email"]}</dt><dd><a href="mailto:{esc(CO["email"])}">{esc(CO["email"])}</a></dd>')
    if WA_NUM:
        # Un enlace, no un widget: no carga nada de Meta hasta que la persona decide escribir.
        info.append(f'<dt>{tt["whatsapp"]}</dt><dd><a href="https://wa.me/{WA_NUM.lstrip("+")}">{esc(CO["whatsapp"])}'
                    f'<span class="sr">{tt["wa_new"]}</span></a></dd>')
    hours = (CO.get("opening_hours_text") or {}).get(lang)
    if hours:
        info.append(f'<dt>{tt["hours"]}</dt><dd>{esc(hours)}</dd>')
    proximos = upcoming_closures()
    if proximos:
        info.append(f'<dt>{tt["closures"]}</dt>' + "".join(f'<dd>{esc(closure_text(c, lang))}</dd>' for c in proximos))
    info_html = f'<dl class="contact-info">{"".join(info)}</dl>'
    if not FORM:
        return f'<div class="contact-grid single">{info_html}</div>'
    form = f"""
<form class="contact-form" action="{esc(FORM)}" method="post">
  <input type="hidden" name="lang" value="{lang}">
  <input type="hidden" name="redirect" value="{SITE_URL}{url_for('thanks', lang)}">
  <div class="hp" aria-hidden="true"><label>Website <input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>
  <label>{tt['form_name']}<input type="text" name="name" required maxlength="120" autocomplete="name"></label>
  <label>{tt['form_email']}<input type="email" name="email" required maxlength="200" autocomplete="email"></label>
  <label>{tt['form_phone']}<input type="tel" name="phone" maxlength="40" autocomplete="tel"></label>
  <label>{tt['form_message']}<textarea name="message" required maxlength="4000" rows="6"></textarea></label>
  <label class="check"><input type="checkbox" name="consent" value="yes" required> <span>{tt['form_consent'].format(url=url_for('privacy', lang))}</span></label>
  <button class="btn" type="submit">{tt['form_send']}</button>
  <p class="meta small form-info">{tt['form_info'].format(owner=esc(CO.get('legal_name') or CFG['site_name']), n=PRIV_CONTACT_M, url=url_for('privacy', lang))}</p>
</form>"""
    return f'<div class="contact-grid">{form}{info_html}</div>'


def newsletter_block(lang: str, page_url: str) -> str:
    """Alta en el boletín (plantilla C, doble confirmación). Casilla sin marcar e información básica junto al formulario."""
    tt = t(lang)
    return (f'<form class="newsletter" action="{esc(NEWS)}" method="post">'
            f'<input type="hidden" name="lang" value="{lang}"><input type="hidden" name="origen" value="{esc(page_url)}">'
            f'<input type="hidden" name="redirect" value="{SITE_URL}{url_for("news_thanks", lang)}">'
            f'<div class="hp" aria-hidden="true"><label>Website <input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>'
            f'<label>{tt["news_email"]}<input type="email" name="email" required maxlength="200" autocomplete="email"></label>'
            f'<label class="check"><input type="checkbox" name="consent" value="yes" required> <span>{esc(tt["news_consent"].format(name=CFG["site_name"]))}</span></label>'
            f'<button class="btn" type="submit">{tt["news_send"]}</button>'
            f'<p class="meta small">{tt["news_info"].format(owner=esc(CO.get("legal_name") or CFG["site_name"]), url=url_for("privacy", lang))}</p></form>')


def order_extras(lang: str) -> str:
    """Casillas del pedido según site.json > crm: siempre sin marcar. Las lee la plantilla C."""
    tt = t(lang)
    out = []
    if NEWS_IN_ORDER:
        out.append(f'<label class="check"><input type="checkbox" name="consent_news" value="yes"> <span>{tt["ord_news"]}</span></label>')
    if OFFERS:
        out.append(f'<input type="hidden" name="aviso_ofertas" value="{esc(OFFERS_V)}"><p class="meta small offers">{tt["ord_offers"]}</p>'
                   f'<label class="check"><input type="checkbox" name="consent_optout" value="yes"> <span>{tt["ord_optout"]}</span></label>')
    if LOYALTY_BASES:
        out.append(f'<label class="check"><input type="checkbox" name="programa" value="yes"> <span>{tt["ord_program"].format(url=esc(LOYALTY_BASES))}</span></label>'
                   f'<details class="invoice voucher"><summary>{tt["ord_voucher"]}</summary>'
                   f'<label>{tt["ord_voucher_code"]}<input name="vale" maxlength="20" autocomplete="off" autocapitalize="characters" spellcheck="false"></label>'
                   f'<label>{tt["ord_voucher_email"]}<input type="email" name="email" maxlength="200" autocomplete="email"></label></details>')
    if WA_AVISOS:
        # Casilla sin marcar; el móvil solo es obligatorio si se marca (catalogo.js) y la plantilla C lo comprueba otra vez.
        out.append(f'<input type="hidden" name="aviso_whatsapp" value="{esc(WA_V)}">'
                   f'<label class="check"><input type="checkbox" name="consent_whatsapp" value="yes"> <span>{tt["ord_wa"]}</span></label>'
                   f'<label class="wa-phone">{tt["ord_wa_phone"]}<input type="tel" name="whatsapp" maxlength="40" autocomplete="tel" inputmode="tel"></label>')
    if PUSH_KEY:
        # Casilla sin marcar y oculta: app.js la enseña si el navegador puede recibir avisos y, al marcarla, pide el permiso y la
        # suscripción (que va en push_suscripcion). La plantilla C la liga a ESTE pedido.
        out.append(f'<div class="push-opt" data-push data-bloqueado="{esc(tt["push_blocked"])}" hidden>'
                   f'<input type="hidden" name="aviso_push" value="{esc(PUSH_V)}"><input type="hidden" name="push_suscripcion" value="">'
                   f'<label class="check"><input type="checkbox" name="consent_push" value="yes"> <span>{tt["ord_push"]}</span></label>'
                   f'<p class="meta small push-msg" role="status" aria-live="polite"></p></div>')
    return f'<div class="order-extras">{"".join(out)}</div>' if out else ""


BLOCK_RE = re.compile(r"^:::([a-z]+)((?:[ \t]+[a-z]+)*)[ \t]*\n(.*?)^:::[ \t]*$", re.S | re.M)
# Variantes de bloque (`:::hero banda`): portada a todo el ancho y oscura (con foto de fondo o sin ella), tarjetas sobre banda oscura e
# imagen y texto en paralelo (`inverso` pone la imagen a la derecha). Composiciones de tarjetas: `juntas` (piezas unidas por una junta
# fina, como un alicatado), `datos` (franja de datos cortos sin caja), `galeria` (fotos grandes sin marco, la primera destacada) y
# `comparar` (fotos del mismo tamaño en paralelo: antes y después) y `piezas` (datos cortos como baldosas de color: ### cifra grande
# y una línea). Una variante desconocida para la web (una errata no pasa sin avisar).
CARD_LAYOUTS = ("juntas", "datos", "galeria", "comparar", "piezas")
BLOCK_MODS = {"hero": {"banda"}, "cards": {"oscuro", *CARD_LAYOUTS}, "split": {"inverso"}, "presupuesto": set(), "indice": set()}
# :::indice (vacío o con una frase): fila de enlaces a los apartados (##) que vienen después en la página, salvo las bandas de llamada
# a la acción. Útil en páginas largas como la de trabajos: el visitante salta a «Suelos» o «Tejados» sin desplazarse.
INDICE = "<!--indice-->"


def render_body(body: str, lang: str, page_url: str = "") -> str:
    """Convierte el cuerpo con bloques :::hero, :::cards, :::cta, :::contact, :::catalogo, :::boletin y :::video."""
    parts, pos = [], 0
    for m in BLOCK_RE.finditer(body):
        before = body[pos:m.start()]
        if before.strip():
            parts.append(f'<section class="section prose wrap">{responsive_all(md(before, lang))}</section>')
        name, mods, inner = m.group(1), set(m.group(2).split()), m.group(3)
        bad = mods - BLOCK_MODS.get(name, set())
        if bad:
            sys.exit(f"ERROR: variante desconocida en :::{name}: {', '.join(sorted(bad))} (válidas: {', '.join(sorted(BLOCK_MODS.get(name, set()))) or 'ninguna'})")
        if name == "hero" and "banda" in mods:
            h = as_buttons(md(inner, lang))
            img = re.search(r"<p>\s*(<img [^>]+>)\s*</p>", h)
            fondo = ""
            if img:
                h = h.replace(img.group(0), "")
                tag = img.group(1).replace('loading="lazy" ', 'fetchpriority="high" ')
                fondo = f'<div class="hero-fondo">{responsive(tag, "hero")}</div>'
            parts.append(f'<section class="hero hero-banda{" has-media" if img else ""}">{fondo}<div class="wrap hero-text">{h}</div></section>')
        elif name == "hero":
            h = as_buttons(md(inner, lang))
            img = re.search(r"<p>\s*(<img [^>]+>)\s*</p>", h)
            if img:
                h = h.replace(img.group(0), "")
                media = responsive(img.group(1).replace('loading="lazy" ', 'fetchpriority="high" '), "hero")
                parts.append(f'<section class="hero has-media"><div class="wrap hero-grid"><div class="hero-text">{h}</div>'
                             f'<div class="hero-media">{media}</div></div></section>')
            else:
                parts.append(f'<section class="hero"><div class="wrap hero-text">{h}</div></section>')
        elif name == "cards":
            h = md(inner, lang)
            head, *cards = re.split(r"(?=<h3)", h)
            layouts = [m_ for m_ in CARD_LAYOUTS if m_ in mods]
            if "datos" in layouts or "piezas" in layouts:
                # Datos cortos, no apartados: el ### se queda en texto destacado y no rompe el orden de los encabezados.
                def dato(m_):
                    if "datos" in layouts:
                        return f'<p class="dato">{m_.group(1)}</p>'
                    # En piezas, una palabra larga («Por escrito») va en un cuerpo menor para no partirse a media palabra.
                    largo = max(len(w) for w in re.sub(r"<[^>]+>", "", m_.group(1)).split() or [""]) > 5
                    return f'<p class="pieza-cifra{" pieza-cifra-larga" if largo else ""}">{m_.group(1)}</p>'
                cards = [re.sub(r"<h3[^>]*>(.*?)</h3>", dato, c, flags=re.S) for c in cards]
            cards_html = "".join(f'<div class="card">{responsive_all(c, "card")}</div>' for c in cards)
            if len(layouts) > 1:
                sys.exit(f"ERROR: :::cards con dos composiciones a la vez: {', '.join(layouts)} (elige una)")
            cls = "cards" + "".join(f" cards-{m_}" for m_ in layouts)
            if "oscuro" in mods:
                parts.append(f'<section class="section banda-oscura"><div class="wrap"><div class="section-head">{as_buttons(head)}</div>'
                             f'<div class="{cls}">{cards_html}</div></div></section>')
            else:
                cabeza = f'<div class="section-head">{head}</div>' if head.strip() else ""
                parts.append(f'<section class="section wrap{" section-" + layouts[0] if layouts else ""}">{cabeza}'
                             f'<div class="{cls}">{cards_html}</div></section>')
        elif name == "split":
            h = as_buttons(md(inner, lang))
            img = re.search(r"<p>\s*(<img [^>]+>)\s*</p>", h)
            if not img:
                sys.exit("ERROR: :::split necesita una imagen (una línea ![texto alternativo](/img/...))")
            h = h.replace(img.group(0), "")
            media = responsive(img.group(1), "hero")
            parts.append(f'<section class="section wrap split{" split-inverso" if "inverso" in mods else ""}">'
                         f'<div class="split-media">{media}</div><div class="split-text">{h}</div></section>')
        elif name == "presupuesto":
            head = md(inner, lang) if inner.strip() else ""
            parts.append(f'<section class="section wrap presupuesto" id="presupuesto"><div class="pres-head">{head}</div>{presupuesto_block(lang)}</section>')
        elif name == "video":
            parts.append(video_block(inner, lang))
        elif name == "cta":
            parts.append(f'<section class="cta"><div class="wrap">{as_buttons(md(inner, lang))}</div></section>')
        elif name == "catalogo":
            if CATALOG is None:
                sys.exit("ERROR: bloque :::catalogo sin catálogo (site.json > catalog.source)")
            head_html = md(inner, lang) if inner.strip() else ""
            if head_html:
                parts.append(f'<section class="section prose wrap">{head_html}</section>')
            parts.append(catalog_block(lang))
        elif name == "boletin":
            if not NEWS:
                sys.exit("ERROR: bloque :::boletin sin site.json > crm.boletin (endpoint de la plantilla C)")
            head = md(inner, lang) if inner.strip() else ""
            parts.append(f'<section class="section wrap newsletter-section" id="boletin"><div class="newsletter-grid"><div>{head}</div>{newsletter_block(lang, page_url)}</div></section>')
        elif name == "indice":
            parts.append(INDICE + (md(inner, lang) if inner.strip() else ""))
        elif name == "contact":
            head = md(inner, lang) if inner.strip() else ""
            parts.append(f'<section class="section wrap" id="contacto">{head}{contact_block(lang)}</section>')
        else:
            sys.exit(f"ERROR: bloque desconocido :::{name}")
        pos = m.end()
    rest = body[pos:]
    if rest.strip():
        parts.append(f'<section class="section prose wrap">{responsive_all(md(rest, lang))}</section>')
    for i, part in enumerate(parts):
        if part.startswith(INDICE):
            enlaces = [(hid, re.sub(r"<[^>]+>", "", txt).strip()) for later in parts[i + 1:] if not later.startswith('<section class="cta')
                       for hid, txt in re.findall(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>', later, re.S)]
            frase = part[len(INDICE):]
            etiqueta = {"es": "Apartados de esta página", "en": "Sections on this page"}.get(lang, "Apartados")
            lis = "".join(f'<li><a href="#{hid}">{txt}</a></li>' for hid, txt in enlaces)
            parts[i] = f'<nav class="section wrap indice" aria-label="{etiqueta}">{frase}<ul>{lis}</ul></nav>'
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Plantilla HTML
# ---------------------------------------------------------------------------
def brand_css() -> str:
    b = BRAND
    faces = "".join(
        f"@font-face{{font-family:'{f['family']}';src:url('/fonts/{f['file']}') format('woff2');"
        f"font-weight:{f.get('weight', '100 900')};font-style:{f.get('style', 'normal')};font-display:swap}}"
        for f in b.get("font_files", [])
    )
    return (f"{faces}:root{{--primary:{b['primary']};--primary-ink:{b['primary_ink']};--ink:{b['ink']};"
            f"--link:{b.get('link') or b['primary']};--focus:{b.get('focus') or b['primary']};--field:{b['muted']};--muted:{b['muted']};--paper:{b['paper']};--surface:{b['surface']};--rule:{b['rule']};"
            f"--radius:{b['radius']};--font-heading:{b['font_heading']};--font-body:{b['font_body']}}}")


def ld_json(j: dict) -> str:
    # "<" como \u003c: dentro de <script> ningún texto (p. ej. el nombre de un producto) puede abrir o cerrar etiquetas.
    return json.dumps(j, ensure_ascii=False).replace("<", "\\u003c")


def head(*, lang: str, title: str, desc: str, url: str, alts: dict, og_type="website",
         jsonld: list | None = None, noindex=False, image: str | None = None) -> str:
    canonical = SITE_URL + url
    alt_links = ""
    if len(alts) > 1:
        alt_links = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE_URL + u}">' for l, u in alts.items())
        alt_links += f'<link rel="alternate" hreflang="x-default" href="{SITE_URL + alts.get(DEFAULT, url)}">'
    # "</" escapado: un nombre de producto con "</script>" no puede cerrar el bloque.
    ld = "".join(f'<script type="application/ld+json">{ld_json(j)}</script>' for j in (jsonld or []))
    img = SITE_URL + "/" + (image or "og.png").lstrip("/")
    robots = '<meta name="robots" content="noindex, follow">' if noindex else ""
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
{alt_links}{robots}
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{esc(CFG['site_name'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{img}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="{BRAND['primary']}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
{app_head()}<style>{brand_css()}</style>
<link rel="stylesheet" href="/style.css?v={CSS_V}">
{ld}
</head>"""


def app_head() -> str:
    """Web instalable: manifiesto e icono de iOS. Con app en App Store, el banner de Safari (lo pinta Safari: no carga nada de fuera)."""
    out = ""
    if PWA:
        out += (f'<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" href="/app/apple-touch-icon.png">'
                f'<meta name="apple-mobile-web-app-title" content="{esc(APP_SHORT)}">\n')
    if IOS_STORE_ID:
        out += f'<meta name="apple-itunes-app" content="app-id={IOS_STORE_ID}">\n'
    return out


def nav_items(lang: str) -> list[tuple[str, str, str]]:
    items = []
    for pg in pages[lang].values():
        if pg.get("nav") and pg["key"] != "home":
            items.append((int(pg["nav"]), pg["key"], pg.get("nav_title", pg["title"])))
    if posts[lang]:
        items.append((int(CFG.get("blog_nav", 50)), "blog", t(lang)["blog"]))
    return [(k, url_for(k, lang), label) for _, k, label in sorted(items)]


def logo_dims(logo: str) -> str:
    """width y height del logo (del viewBox si es SVG): el navegador reserva su hueco y la cabecera no salta al cargar."""
    p = STATIC / logo
    if p.suffix.lower() == ".svg" and p.is_file():
        m = re.search(r"<svg\b[^>]*?\bviewBox\s*=\s*[\"']\s*[-\d.eE]+[\s,]+[-\d.eE]+[\s,]+([\d.eE]+)[\s,]+([\d.eE]+)", p.read_text(encoding="utf-8", errors="replace"), re.S)
        if m and float(m.group(1)) > 0 and float(m.group(2)) > 0:
            return f' width="{round(float(m.group(1)))}" height="{round(float(m.group(2)))}"'
        return ""
    size = image_size(p) if p.is_file() else None
    return f' width="{size[0]}" height="{size[1]}"' if size else ""


def header(lang: str, key: str) -> str:
    tt = t(lang)
    cur = ' aria-current="page"'
    links = "".join(
        f'<li><a href="{u}"{cur if k == key else ""}>{esc(label)}</a></li>'
        for k, u, label in nav_items(lang)
    )
    # Idioma siempre a la vista (también en el móvil, fuera del menú): nombre completo en pantallas anchas y abreviado en el móvil
    # (el nombre accesible es siempre el completo). Y un aviso arriba, oculto, que static/idioma.js enseña a quien tiene el navegador
    # en ese otro idioma; sin redirigir a nadie.
    otros = [(l, u) for l, u in alternates(key).items() if l != lang]
    switch = "".join(f'<a class="lang" href="{u}" hreflang="{l}" lang="{l}"><span class="lang-largo">{t(l)["lang_name"]}</span>'
                     f'<span class="lang-corto" aria-hidden="true">{t(l)["lang_short"]}</span></a>' for l, u in otros)
    switch = f'<div class="lang-switch">{switch}</div>' if switch else ""
    avisos = "".join(f'<div class="aviso-idioma" role="region" aria-label="{t(l)["lang_region"]}" lang="{l}" data-idioma="{l}" hidden>'
                     f'<div class="wrap"><p>{t(l)["lang_avail"]} <a href="{u}" hreflang="{l}">{t(l)["lang_view"]}</a></p>'
                     f'<button type="button" class="linkish" data-cerrar-idioma>{t(l)["lang_close"]}</button></div></div>'
                     for l, u in otros)
    logo = BRAND.get("logo")
    brand_inner = (f'<img src="/{logo}" alt="{esc(CFG["site_name"])}" class="logo"{logo_dims(logo)}>' if logo
                   else esc(CFG["site_name"]))
    return f"""<body>
<a class="skip" href="#main">{tt['skip']}</a>
<header class="site-header">
  <div class="wrap header-row">
    <a class="brand" href="{prefix(lang)}">{brand_inner}</a>
    <details class="nav-toggle"><summary>{tt['menu']}</summary>
      <nav aria-label="{tt['main_nav']}"><ul>{links}</ul></nav>
    </details>
    <nav class="nav-wide" aria-label="{tt['main_nav']}"><ul>{links}</ul></nav>
    {switch}
  </div>
</header>
{avisos}{IDIOMA_JS if avisos else ""}<main id="main">"""


def footer(lang: str, extra: str = "", barra: bool = True) -> str:
    tt = t(lang)
    account = f'<li><a href="{esc(ACCOUNT)}">{tt["account"]}</a></li>' if ACCOUNT else ""
    cookies = (f'<li><a href="{url_for("cookies", lang)}">{tt["cookies_title"]}</a></li>'
               f'<li><button type="button" class="linkish" data-consent-open>{tt["cookies_config"]}</button></li>') if MED_ON else ""
    year = dt.date.fromisoformat(CFG["updated"]).year
    social = "".join(f'<li><a href="{esc(u)}" rel="noopener">{esc(n.capitalize())}</a></li>'
                     for n, u in CO.get("social", {}).items() if u)
    # Enlaces de texto a las fichas (las insignias oficiales, si se quieren, se descargan de Apple y Google y se sirven desde la web).
    stores = "".join(f'<li><a href="{esc(u)}" rel="noopener">{tt[k]}</a></li>' for k, u in (("app_ios", STORE_IOS), ("app_android", STORE_ANDROID)) if u)
    return f"""</main>
{barra_movil(lang) if barra else ""}
<footer class="site-footer">
  <div class="wrap footer-grid">
    <div>
      <p class="footer-name">{esc(CFG['site_name'])}</p>
      <p>{esc(CO.get('address', ''))}</p>
      <p>{esc(CO.get('phone', ''))} {('· ' + esc(CO['email'])) if CO.get('email') else ''}</p>
    </div>
    <ul class="footer-links">
      <li><a href="{url_for('legal', lang)}">{tt['legal_title']}</a></li>
      <li><a href="{url_for('privacy', lang)}">{tt['privacy_title']}</a></li>
      <li><a href="{url_for('accessibility', lang)}">{tt['a11y_title']}</a></li>
      {cookies}{account}{stores}{social}
    </ul>
  </div>
  <div class="wrap footer-base"><p>© {year} {esc(CO.get('legal_name', CFG['site_name']))}. {tt['all_rights']}</p></div>
</footer>
{extra}{consent_tag(lang)}{chatbot_tag()}{app_tag()}</body>
</html>
"""


def barra_movil(lang: str) -> str:
    """Barra fija abajo en el móvil con Llamar y WhatsApp (site.json > barra_movil.activa). Solo enlaces: no carga nada de fuera.
    style.css la oculta en pantallas anchas y reserva su sitio (padding del body y scroll-padding) para que no tape el foco ni el pie."""
    if not BARRA_MOVIL:
        return ""
    tt = t(lang)
    tel = re.sub(r"[^\d+]", "", CO["phone"])
    links = [f'<a class="btn" href="tel:{tel}">{tt["bar_call"]}</a>']
    if WA_NUM:
        links.append(f'<a class="btn btn-ghost" href="https://wa.me/{WA_NUM.lstrip("+")}">{tt["whatsapp"]}</a>')
    return f'<nav class="barra-movil" aria-label="{tt["bar_label"]}">{"".join(links)}</nav>\n'


def consent_tag(lang: str) -> str:
    """Banner de cookies y etiquetas de medición: Google y Meta solo se cargan si la persona acepta."""
    if not MED_ON:
        return ""
    rmk = ' data-remarketing="1"' if MED_RMK else ""
    return (f'<script src="/consent.js" data-ga4="{esc(MED_GA4)}" data-ads="{esc(MED_ADS)}" data-meta="{esc(MED_META)}"{rmk} '
            f'data-policy="{url_for("cookies", lang)}" defer></script>\n')


def app_tag() -> str:
    """Web instalable (static/app.js): service worker y, con avisos, la casilla del pedido y la baja. Sin cookies."""
    if not PWA:
        return ""
    data = f' data-key="{esc(PUSH_KEY)}" data-api="{esc(PUSH_API)}"' if PUSH_KEY else ""
    return f'<script src="/app.js?v={APP_JS_V}"{data} defer></script>\n'


def chatbot_tag() -> str:
    """Asistente de chat (plantilla-bot de La Taza Roja). Se activa con site.json > chatbot."""
    if not BOT_ON:
        return ""
    return f'<script src="{esc(BOT["script"])}" data-bot="{esc(BOT["bot"])}" defer></script>\n'


def write(url: str, doc: str) -> None:
    p = OUT / url.lstrip("/") / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc, encoding="utf-8")


def org_jsonld(lang: str) -> dict:
    d = {"@context": "https://schema.org", "@type": CO.get("schema_type", "Organization"),
         "name": CFG["site_name"], "url": SITE_URL + prefix(lang)}
    if BRAND.get("logo"):
        d["logo"] = SITE_URL + "/" + BRAND["logo"]
    if CO.get("phone"):
        d["telephone"] = CO["phone"]
    if CO.get("email"):
        d["email"] = CO["email"]
    if CO.get("alternate_name"):
        d["alternateName"] = CO["alternate_name"]
    if (STATIC / "og.png").exists():
        d["image"] = SITE_URL + "/og.png"
    # schema_address (partes de PostalAddress) manda sobre address: permite dar localidad y código postal sin la calle
    # (negocio que va a domicilio del cliente y cuyo domicilio fiscal es su casa: la calle ya está en el aviso legal).
    if CO.get("schema_address"):
        d["address"] = {"@type": "PostalAddress", **CO["schema_address"]}
    elif CO.get("address"):
        d["address"] = CO["address"]
    if CO.get("area_served"):
        d["areaServed"] = [{"@type": "City", "name": a} for a in CO["area_served"]]
    if CO.get("opening_hours"):
        d["openingHours"] = CO["opening_hours"]
    same = [u for u in CO.get("social", {}).values() if u]
    if same:
        d["sameAs"] = same
    return d


# ---------------------------------------------------------------------------
# Constructores
# ---------------------------------------------------------------------------
def build_page(pg: dict) -> None:
    lang, key = pg["lang"], pg["key"]
    url = url_for(key, lang)
    body = render_body(pg["body"], lang, url)
    if not body.lstrip().startswith('<section class="hero'):
        body = f'<div class="page-head wrap"><h1>{esc(pg["title"])}</h1></div>' + body
    title = pg.get("seo_title") or (CFG["site_name"] if key == "home" else f'{pg["title"]} | {CFG["site_name"]}')
    jsonld = [org_jsonld(lang)] if key == "home" else []
    doc = head(lang=lang, title=title, desc=pg["description"], url=url, alts=alternates(key),
               jsonld=jsonld, noindex=pg.get("noindex") == "true", image=pg.get("image"))
    extra = (CATALOG_JS if ":::catalogo" in pg["body"] else "") + (PRES_JS if re.search(r"^:::presupuesto\b", pg["body"], re.M) else "")
    extra += GALERIA_JS if re.search(r"^:::cards\b[^\n]*\b(galeria|comparar)\b", pg["body"], re.M) else ""
    # `barra_movil: false` en la cabecera de la página: sin la barra fija en esa página (p. ej. la del formulario de presupuesto, que ya
    # tiene sus botones). Otro valor que no sea true/false es una errata y no se publica.
    barra = pg.get("barra_movil", "true")
    if barra not in ("true", "false"):
        sys.exit(f"ERROR: content/{lang}/{key}.md: barra_movil debe ser true o false, no «{barra}»")
    doc += header(lang, key) + body + footer(lang, extra, barra=barra == "true")
    write(url, doc)


def reading_min(text: str) -> int:
    return max(1, math.ceil(len(re.findall(r"\w+", text)) / 220))


def build_blog(lang: str) -> None:
    if not posts[lang]:
        return
    tt = t(lang)
    items = sorted(posts[lang].values(), key=lambda p: p["date"], reverse=True)
    cards = []
    for po in items:
        u = url_for(po["key"], lang)
        cards.append(f'<article class="card post-card"><p class="meta">{fmt_date(po["date"], lang)}</p>'
                     f'<h2><a href="{u}">{esc(po["title"])}</a></h2><p>{esc(po["description"])}</p>'
                     f'<p><a href="{u}">{tt["read_more"]}<span class="sr"> — {esc(po["title"])}</span></a></p></article>')
        jsonld = [{"@context": "https://schema.org", "@type": "BlogPosting", "headline": po["title"],
                   "description": po["description"], "datePublished": po["date"],
                   "dateModified": po.get("updated", po["date"]), "inLanguage": lang,
                   "mainEntityOfPage": SITE_URL + u,
                   "publisher": {"@type": "Organization", "name": CFG["site_name"]}}]
        doc = head(lang=lang, title=f'{po["title"]} | {CFG["site_name"]}', desc=po["description"], url=u,
                   alts=alternates(po["key"]), og_type="article", jsonld=jsonld, image=po.get("image"))
        doc += header(lang, "blog")
        doc += (f'<article class="wrap post"><header class="page-head"><p class="meta">'
                f'{tt["published"].format(d=fmt_date(po["date"], lang))} · {tt["min_read"].format(n=reading_min(po["body"]))}</p>'
                f'<h1>{esc(po["title"])}</h1></header><div class="prose">{md(po["body"], lang)}</div></article>')
        doc += footer(lang)
        write(u, doc)
    u = url_for("blog", lang)
    doc = head(lang=lang, title=f'{tt["blog_title"]} | {CFG["site_name"]}', desc=tt["blog_lead"], url=u,
               alts=alternates("blog"))
    doc += header(lang, "blog")
    doc += (f'<div class="page-head wrap"><h1>{tt["blog_title"]}</h1><p class="lead">{tt["blog_lead"]}</p></div>'
            f'<section class="section wrap"><div class="cards">{"".join(cards)}</div></section>')
    doc += footer(lang)
    write(u, doc)


CATALOG_JS = '<script src="/catalogo.js" defer></script>\n'
PRES_JS = '<script src="/presupuesto.js" defer></script>\n'
IDIOMA_JS = '<script src="/idioma.js" defer></script>\n'
GALERIA_JS = '<script src="/galeria.js" defer></script>\n'  # ampliar fotos de :::cards galeria / comparar
API_ATTR = f' data-api="{esc(CAT_API)}"' if CAT_API else ""


def buy_fields(lang: str) -> tuple[str, str]:
    """Método de entrega y factura completa: los mismos en la ficha y en el pedido preparado por el asistente."""
    tt = t(lang)
    envio = [e for e in CAT.get("envio", []) if isinstance(e, dict) and e.get("id")]
    env = ""
    if len(envio) > 1:
        env = (f'<label>{tt["cat_delivery"]}<select name="envio">'
               + "".join(f'<option value="{esc(e["id"])}">{esc(e.get("nombre", e["id"]))}</option>' for e in envio) + "</select></label>")
    elif envio:
        env = f'<input type="hidden" name="envio" value="{esc(envio[0]["id"])}">'
    inv = ""
    if CAT.get("factura_completa"):
        inv = (f'<details class="invoice"><summary>{tt["inv_need"]}</summary>'
               f'<label>{tt["inv_nif"]}<input name="fac_nif" maxlength="20" autocomplete="off"></label>'
               f'<label>{tt["inv_name"]}<input name="fac_nombre" maxlength="120" autocomplete="organization"></label>'
               f'<label>{tt["inv_address"]}<input name="fac_direccion" maxlength="200" autocomplete="street-address"></label>'
               f'<label>{tt["inv_cp"]}<input name="fac_cp" maxlength="10" autocomplete="postal-code"></label>'
               f'<label>{tt["inv_city"]}<input name="fac_ciudad" maxlength="100" autocomplete="address-level2"></label></details>')
    return env, inv


def build_prepared_order(lang: str) -> None:
    """Pedido preparado por el asistente (/pedido/?propuesta=…): catalogo.js lo lee de la plantilla C y rellena el formulario de compra
    con sus productos y la propuesta. Sin JavaScript o sin propuesta válida, lleva al catálogo. noindex y fuera del sitemap."""
    if not exists_in("order", lang):
        return
    tt = t(lang)
    u = url_for("order", lang)
    list_url = url_for(CAT_PAGE, lang)
    env, inv = buy_fields(lang)
    doc = head(lang=lang, title=f'{tt["prep_title"]} | {CFG["site_name"]}', desc=tt["prep_title"], url=u, alts={l: url_for("order", l) for l in CAT_LANGS}, noindex=True)
    doc += header(lang, "order")
    doc += (f'<div class="page-head wrap"><h1>{tt["prep_title"]}</h1><p class="lead">{tt["prep_lead"]}</p></div>'
            f'<section class="section wrap prepared" data-lang="{lang}"{API_ATTR} data-gone="{esc(tt["prep_gone"])}" data-none="{esc(tt["prep_none"])}"'
            f' data-error="{esc(tt["prep_error"])}">'
            f'<p class="status" role="status" aria-live="polite">{tt["prep_loading"]}</p>'
            f'<noscript><p>{tt["prep_nojs"]}</p></noscript>'
            f'<div class="prepared-order" hidden><h2>{tt["prep_items"]}</h2><ul class="prepared-lines"></ul>'
            f'<p class="price"><span>{tt["prep_total"]}: </span><strong class="prepared-total"></strong></p><p class="meta small">{tt["prep_prices"]}</p>'
            f'<form class="buy" action="{esc(CAT_API)}/api/checkout" method="post"><div class="prepared-items"></div>'
            f'<input type="hidden" name="propuesta" value="">{env}{inv}{order_extras(lang)}'
            f'<button class="btn" type="submit">{tt["prep_pay"]}</button>'
            f'<p class="meta small form-info">{tt["ord_info"].format(owner=esc(CO.get("legal_name") or CFG["site_name"]), url=url_for("privacy", lang))}</p></form></div>'
            f'<p><a href="{list_url}">← {tt["cat_back"]}</a></p></section>')
    doc += footer(lang, CATALOG_JS)
    write(u, doc)


def build_catalog(lang: str) -> None:
    """Una ficha por producto (y, con por_categoria, una página por categoría). Solo en los idiomas con la página del catálogo."""
    if CATALOG is None or lang not in CAT_LANGS:
        return
    tt = t(lang)
    list_url = url_for(CAT_PAGE, lang)
    list_title = pages[lang][CAT_PAGE]["title"]
    cats = {c["slug"]: c for c in CATALOG["categorias"]}
    for p in CATALOG["productos"]:
        u = product_url(p["sku"], lang)
        cat = cats.get(p.get("category") or "")
        crumbs = f'<a href="{list_url}">{esc(list_title)}</a>' + (
            f' › <a href="{category_url(cat["slug"], lang) if CAT.get("por_categoria") else list_url + "#cat-" + cat["slug"]}">{esc(cat["name"])}</a>' if cat else "")
        attrs = "".join(f'<dt>{esc(k.replace("-", " ").capitalize())}</dt><dd>{esc(", ".join(v) if isinstance(v, list) else str(v))}</dd>'
                        for k, v in p["attrs"].items() if v)
        dl_attrs = f'<dl class="attrs">{attrs}</dl>' if attrs else ""
        buy = ""
        if CAT_BUY:
            env, inv = buy_fields(lang)
            dis = "" if p["disponible"] else " disabled"
            buy = (f'<form class="buy" action="{esc(CAT_API)}/api/checkout" method="post"><input type="hidden" name="sku" value="{esc(p["sku"])}">'
                   f'<label>{tt["cat_qty"]}<input type="number" name="qty" value="1" min="1" max="20" inputmode="numeric"></label>{env}{inv}{order_extras(lang)}'
                   f'<button class="btn" type="submit"{dis}>{tt["cat_buy"] if p["disponible"] else tt["cat_out"]}</button>'
                   f'<p class="meta small form-info">{tt["ord_info"].format(owner=esc(CO.get("legal_name") or CFG["site_name"]), url=url_for("privacy", lang))}</p></form>')
        media = (f'<div class="product-media">{responsive(f"""<img src="{esc(img_src(p["image"]))}" alt="{esc(p["name"])}" fetchpriority="high">""", "hero")}</div>'
                 if p["image"] else "")
        jsonld = {"@context": "https://schema.org", "@type": "Product", "name": p["name"], "sku": p["sku"], "url": SITE_URL + u,
                  "offers": {"@type": "Offer", "price": f'{p["price_cents"] / 100:.2f}', "priceCurrency": "EUR", "url": SITE_URL + u,
                             "availability": "https://schema.org/" + ("InStock" if p["disponible"] else "OutOfStock")}}
        if p["description"]:
            jsonld["description"] = p["description"][:5000]
        if p["image"]:
            jsonld["image"] = p["image"] if p["image"].startswith("https://") else SITE_URL + img_src(p["image"])
        if cat:
            jsonld["category"] = cat["name"]
        desc = (p["description"].strip().split("\n")[0][:155] or f'{p["name"]} · {CFG["site_name"]}')
        alts = {l: product_url(p["sku"], l) for l in CAT_LANGS}
        doc = head(lang=lang, title=f'{p["name"]} | {CFG["site_name"]}', desc=desc, url=u, alts=alts, og_type="product",
                   jsonld=[jsonld], image=p["image"] if p["image"] and not p["image"].startswith("https://") else None)
        doc += header(lang, CAT_PAGE)
        doc += (f'<div class="wrap product-page" data-sku="{esc(p["sku"])}" data-lang="{lang}"{API_ATTR}'
                f' data-gone="{esc(tt["cat_gone"])}" data-out="{esc(tt["cat_out"])}" data-buy="{esc(tt["cat_buy"])}">'
                f'<nav class="crumbs meta" aria-label="Migas">{crumbs}</nav><div class="product-grid">{media}<div class="product-info">'
                f'<h1>{esc(p["name"])}</h1><p class="price"><span class="amount">{money(p["price_cents"], lang)}</span> <span class="meta">{tt["cat_vat"]}</span></p>'
                f'<p class="out"{"" if not p["disponible"] else " hidden"}>{tt["cat_out"]}</p>'
                f'<div class="prose">{text_paragraphs(p["description"])}</div>'
                f'{dl_attrs}{buy}'
                f'<p><a href="{list_url}">← {tt["cat_back"]}</a></p></div></div></div>')
        doc += footer(lang, CATALOG_JS)
        write(u, doc)
    if CAT.get("por_categoria"):
        for c, ps in catalog_groups():
            if not c:
                continue
            u = category_url(c["slug"], lang)
            doc = head(lang=lang, title=f'{c["name"]} | {CFG["site_name"]}', desc=f'{c["name"]} · {CFG["site_name"]}', url=u,
                       alts={l: category_url(c["slug"], l) for l in CAT_LANGS})
            doc += header(lang, CAT_PAGE)
            doc += (f'<div class="page-head wrap"><p class="meta"><a href="{list_url}">{esc(list_title)}</a></p><h1>{esc(c["name"])}</h1></div>'
                    f'<section class="section wrap catalog" data-lang="{lang}"{API_ATTR}>'
                    f'<div class="product-group" data-group="{esc(c["slug"])}"><div class="cards products">{"".join(product_card(p, lang, level=2) for p in ps)}</div></div></section>')
            doc += footer(lang, CATALOG_JS)
            write(u, doc)


missing_legal: set[str] = set()


def co(field: str, lang: str) -> str:
    v = CO.get(field, "")
    if not v:
        missing_legal.add(field)
        return t(lang)["pending"]
    return esc(v)


def recipients_html(lang: str, bot_rec: str) -> str:
    """Destinatarios y transferencias desde site.json > privacidad.encargados (los mismos que config/rgpd.json de la plantilla C)."""
    es = lang == "es"
    if not ENCARGADOS:
        return ("<p>No cedemos datos a terceros salvo obligación legal. El proveedor de alojamiento actúa como encargado del tratamiento." if es
                else "<p>Data is not shared with third parties unless required by law. The hosting provider acts as data processor.") + f"{bot_rec}</p>"
    items = "; ".join(f"{SERVICIOS[e['servicio']][0 if es else 1]} ({esc(e['nombre'])}, {esc(e['pais'])})" for e in ENCARGADOS)
    out = (f"<p>No cedemos datos a terceros salvo obligación legal. Nos prestan servicios con acceso a datos, como encargados del tratamiento y con contrato: {items}.{bot_rec}</p>"
           if es else f"<p>Data is not shared with third parties unless required by law. These providers have access to data as processors, under contract: {items}.{bot_rec}</p>")
    outside = [e for e in ENCARGADOS if not in_eea(e["pais"]) and "[CONFIRMAR" not in e["pais"]]
    if outside:
        pend = "[CONFIRMAR: garantía de la transferencia]" if es else "[CONFIRMAR: transfer safeguard]"
        lst = "; ".join(f"{esc(e['nombre'])} ({esc(e['pais'])}): {esc(e.get('garantia') or '') or pend}" for e in outside)
        out += (f"<p><strong>Transferencias internacionales.</strong> Algunos proveedores tratan datos fuera del Espacio Económico Europeo, con estas garantías: {lst}.</p>" if es
                else f"<p><strong>International transfers.</strong> Some providers process data outside the European Economic Area, with these safeguards: {lst}.</p>")
    return out


def legal_html(lang: str) -> tuple[str, str]:
    """Aviso legal y privacidad generados desde site.json (revisar con el cliente)."""
    form_es = ("<p><strong>Formulario de contacto.</strong> Si nos escribes mediante el formulario, trataremos tu nombre, "
               "email, teléfono (si lo indicas) y mensaje para responderte, con base en tu consentimiento (art. 6.1.a RGPD). "
               f"Conservamos el mensaje {PRIV_CONTACT_M} meses y después lo borramos.</p>") if FORM else ""
    form_en = ("<p><strong>Contact form.</strong> If you write to us through the form, we process your name, email, "
               "phone (if provided) and message to reply to you, based on your consent (Art. 6(1)(a) GDPR). "
               f"We keep the message for {PRIV_CONTACT_M} months and then delete it.</p>") if FORM else ""
    api_host = esc(CAT_API.split("//", 1)[-1]) if CAT_API else ""
    shop_es = ("<p><strong>Compras.</strong> Si haces un pedido, trataremos tu nombre, email, dirección y teléfono (si los indicas) y los "
               "productos comprados para preparar y entregar el pedido y emitir la factura (art. 6.1.b RGPD), y los conservamos "
               f"{PRIV_ORDERS_Y} años desde el cierre del año, como exige la normativa contable y fiscal (art. 6.1.c RGPD); después se anonimizan. "
               "Los pedidos que no llegan a pagarse se quedan sin datos personales al mes. El pago lo procesa la pasarela de pago; nunca vemos los datos de tu tarjeta.</p>") if CAT_BUY else ""
    shop_en = ("<p><strong>Purchases.</strong> If you place an order, we process your name, email, address and phone (if provided) and the "
               "products bought to prepare and deliver the order and issue the invoice (Art. 6(1)(b) GDPR), and keep them for "
               f"{PRIV_ORDERS_Y} years from the end of the year, as accounting and tax law requires (Art. 6(1)(c) GDPR); then they are anonymised. "
               "Orders that are never paid lose their personal data after a month. Payment is processed by the payment provider; we never see your card details.</p>") if CAT_BUY else ""
    api_es = (f" Para mostrar precios y disponibilidad al día, la web consulta nuestro servidor de pedidos ({api_host}), que registra los mismos datos técnicos.") if CAT_API else ""
    api_en = (f" To show up-to-date prices and availability, the site queries our order server ({api_host}), which records the same technical data.") if CAT_API else ""
    med_es = ("<p><strong>Medición y publicidad.</strong> Solo si lo aceptas en el aviso de cookies, usamos "
              + ", ".join(x for x in ("Google Analytics para contar visitas" if MED_GA4 else "", "Google Ads" if MED_ADS else "", "Meta (Facebook e Instagram)" if MED_META else "") if x)
              + " para medir las visitas y los resultados de nuestros anuncios"
              + (" y, si aceptas las cookies de publicidad, para mostrarte anuncios nuestros en otras webs y redes según tu visita (remarketing)" if MED_RMK else "")
              + " (art. 6.1.a RGPD). Si compras o nos escribes después de aceptar, "
              "enviamos a esos servicios que la conversión se produjo; a Meta, con tu email cifrado (no legible). Estos proveedores pueden tratar "
              "datos en EE. UU., con las garantías del Marco de Privacidad de Datos UE-EE. UU. Puedes retirar el consentimiento cuando quieras "
              f"desde «Configurar cookies», en el pie de cada página. Detalle en la <a href=\"{url_for('cookies', 'es')}\">política de cookies</a>.</p>") if MED_ON and "es" in LANGS else ""
    med_en = ("<p><strong>Measurement and advertising.</strong> Only if you accept it in the cookie notice, we use "
              + ", ".join(x for x in ("Google Analytics to count visits" if MED_GA4 else "", "Google Ads" if MED_ADS else "", "Meta (Facebook and Instagram)" if MED_META else "") if x)
              + " to measure visits and the results of our ads"
              + (" and, if you accept advertising cookies, to show you our ads on other sites and social networks based on your visit (remarketing)" if MED_RMK else "")
              + " (Art. 6(1)(a) GDPR). If you buy or write to us after accepting, we tell those "
              "services that the conversion happened; Meta receives your email in hashed (unreadable) form. These providers may process data "
              "in the USA under the EU-US Data Privacy Framework. You can withdraw consent at any time from “Cookie settings” at the foot of "
              f"every page. Details in the <a href=\"{url_for('cookies', 'en')}\">cookie policy</a>.</p>") if MED_ON and "en" in LANGS else ""
    cookies_es = ("Esta web no usa cookies ni herramientas de analítica de terceros. El área de cliente («Mis pedidos») usa solo una cookie técnica "
                  "de sesión, necesaria para entrar, que se borra al salir o a los 7 días.") if ACCOUNT else "Este sitio <strong>no usa cookies</strong> ni herramientas de analítica de terceros."
    cookies_en = ("This site uses no cookies and no third-party analytics. The customer area (“My orders”) only uses a technical session "
                  "cookie, needed to sign in, which is deleted when you sign out or after 7 days.") if ACCOUNT else "This site <strong>uses no cookies</strong> and no third-party analytics."
    if MED_ON:
        cookies_es = ("Usamos cookies técnicas y, solo si las aceptas, de análisis y publicidad: ver la <a href=\"" + url_for("cookies", "es") + "\">política de cookies</a>."
                      if "es" in LANGS else "")
        cookies_en = ("We use technical cookies and, only if you accept them, analytics and advertising cookies: see the <a href=\"" + url_for("cookies", "en") + "\">cookie policy</a>."
                      if "en" in LANGS else "")
    # CRM y fidelización (site.json > crm). Revisar con el cliente, como el resto de textos legales.
    crm_es, crm_en = [], []
    if NEWS or NEWS_IN_ORDER:
        crm_es.append("<p><strong>Boletín y novedades.</strong> Si lo pides (en el formulario del boletín, al comprar o en tu área de cliente), te enviaremos por email "
                      "novedades y ofertas, con base en tu consentimiento (art. 6.1.a RGPD). " + ("En el boletín te pedimos que lo confirmes desde un enlace que te enviamos. " if NEWS else "")
                      + "Guardamos tu email, idioma, la fecha y el texto que aceptaste, como prueba. Puedes darte de baja en cada email con un clic; después solo "
                      "conservamos tu email en una lista de exclusión para no volver a escribirte.</p>")
        crm_en.append("<p><strong>Newsletter and news.</strong> If you ask for it (in the newsletter form, when buying or in your customer area), we will email you "
                      "news and offers, based on your consent (Art. 6(1)(a) GDPR). " + ("For the newsletter we ask you to confirm through a link we send you. " if NEWS else "")
                      + "We keep your email, language, the date and the text you accepted, as proof. You can unsubscribe from any email with one click; afterwards we "
                      "only keep your email on a suppression list so we don't write to you again.</p>")
    if OFFERS:
        crm_es.append("<p><strong>Ofertas a clientes.</strong> Si nos compras, podremos enviarte por email ofertas de productos o servicios nuestros parecidos a los que compraste "
                      "(art. 21.2 de la LSSI y art. 6.1.f RGPD, interés legítimo). Te lo indicamos al comprar, puedes oponerte marcando la casilla y también en cada email.</p>")
        crm_en.append("<p><strong>Offers to customers.</strong> If you buy from us, we may email you offers for our own products or services similar to those you bought "
                      "(Art. 21(2) of the Spanish LSSI and Art. 6(1)(f) GDPR, legitimate interest). We tell you when you buy; you can object by ticking the box and in every email.</p>")
    if NEWS or NEWS_IN_ORDER or OFFERS:
        crm_es.append("<p><strong>Historial de cliente.</strong> Con tus compras y reservas agrupamos a los clientes (nuevos, habituales, sin compras recientes…) para elegir "
                      "qué comunicaciones enviar a quien las aceptó y atenderte mejor (art. 6.1.f RGPD). No tomamos decisiones automatizadas con efectos sobre ti. "
                      "No usamos píxeles ni seguimiento de aperturas en los emails.</p>")
        crm_en.append("<p><strong>Customer history.</strong> We use your purchases and bookings to group customers (new, regular, not recently active…) to choose which "
                      "communications to send to those who accepted them and to serve you better (Art. 6(1)(f) GDPR). We make no automated decisions affecting you. "
                      "We use no tracking pixels or open tracking in emails.</p>")
    if LOYALTY_BASES:
        crm_es.append(f"<p><strong>Programa de puntos.</strong> Si te apuntas, trataremos tu email, tus compras y tus puntos para gestionar el programa según sus "
                      f"<a href=\"{esc(LOYALTY_BASES)}\" rel=\"noopener\">bases</a> (art. 6.1.b RGPD). Si sales del programa, borramos tus puntos y movimientos.</p>")
        crm_en.append(f"<p><strong>Loyalty programme.</strong> If you join, we process your email, purchases and points to run the programme under its "
                      f"<a href=\"{esc(LOYALTY_BASES)}\" rel=\"noopener\">terms</a> (Art. 6(1)(b) GDPR). If you leave, we delete your points and history.</p>")
    if WA_AVISOS:
        crm_es.append("<p><strong>Avisos por WhatsApp.</strong> Si lo pides al comprar o reservar, te enviaremos por WhatsApp avisos de ese pedido o esa reserva "
                      "(preparado, enviado, recordatorio, cambios), con base en tu consentimiento (art. 6.1.a RGPD). Guardamos tu móvil, cuándo lo aceptaste y el "
                      "estado de entrega de cada aviso (90 días). Puedes darte de baja cuando quieras respondiendo BAJA; después solo conservamos tu número en una "
                      "lista de exclusión para no volver a escribirte. Nunca te enviaremos publicidad por WhatsApp sin pedirte antes permiso para ello. "
                      "Los mensajes se envían con la plataforma de WhatsApp Business de Meta.</p>")
        crm_en.append("<p><strong>WhatsApp updates.</strong> If you ask for them when buying or booking, we will send you WhatsApp updates about that order or "
                      "booking (ready, shipped, reminder, changes), based on your consent (Art. 6(1)(a) GDPR). We keep your mobile number, when you accepted and the "
                      "delivery status of each update (90 days). You can opt out at any time by replying STOP; afterwards we only keep your number on a suppression "
                      "list so we don't write to you again. We will never send you advertising by WhatsApp without asking your permission first. "
                      "Messages are sent with Meta's WhatsApp Business platform.</p>")
    if WA_NUM:
        crm_es.append("<p><strong>Si nos escribes por WhatsApp.</strong> Trataremos tu número, tu nombre de perfil y lo que nos escribas para contestarte "
                      "(art. 6.1.b RGPD, o tu consentimiento si es una consulta general). WhatsApp es un servicio de Meta con sus propias condiciones. "
                      "No nos envíes por ese medio datos bancarios, de salud ni otros datos sensibles.</p>")
        crm_en.append("<p><strong>If you write to us on WhatsApp.</strong> We process your number, profile name and what you write in order to reply "
                      "(Art. 6(1)(b) GDPR, or your consent for general enquiries). WhatsApp is a Meta service with its own terms. "
                      "Do not send bank, health or other sensitive data through it.</p>")
    if PRES.get("trabajos"):
        crm_es.append("<p><strong>Formulario de presupuesto.</strong> No envía ni guarda nada en esta web: prepara en tu navegador un mensaje con lo que "
                      "escribes y eres tú quien lo manda por WhatsApp o por email. Si nos lo mandas, trataremos esos datos (nombre, pueblo, el trabajo y lo que "
                      "nos cuentes, y las fotos si las envías) para preparar el presupuesto y contestarte (art. 6.1.b RGPD) y los borraremos cuando ya no "
                      "hagan falta para eso, salvo que nos encargues el trabajo.</p>")
        crm_en.append("<p><strong>Quote form.</strong> It does not send or store anything on this website: it prepares a message in your browser with what "
                      "you write, and you send it yourself by WhatsApp or email. If you send it, we process that data (name, town, the job and what you tell "
                      "us, and photos if you send them) to prepare the quote and reply (Art. 6(1)(b) GDPR), and we delete it when it is no longer needed for "
                      "that, unless you hire us for the job.</p>")
    if PUSH_KEY:
        crm_es.append("<p><strong>Avisos en este dispositivo.</strong> Si lo pides al comprar o reservar (y das permiso en el navegador), te avisaremos en este "
                      "dispositivo del estado de ese pedido o esa reserva, con base en tu consentimiento (art. 6.1.a RGPD). Guardamos la dirección técnica que "
                      "da tu navegador para enviarte los avisos, ligada a ese pedido o esa reserva, durante 90 días como máximo. Cada aviso viaja cifrado por el "
                      "servicio de notificaciones de tu navegador (Google, Apple, Mozilla o Microsoft, según el que uses), que no puede leerlo. Puedes "
                      "desactivarlos en esta página («Dejar de recibir avisos en este dispositivo») o en los ajustes del navegador. Nunca te enviaremos "
                      "publicidad por este medio.</p>")
        crm_en.append("<p><strong>Notifications on this device.</strong> If you ask for them when buying or booking (and allow them in your browser), we will "
                      "notify you on this device about that order or booking, based on your consent (Art. 6(1)(a) GDPR). We keep the technical address your "
                      "browser gives us to send the notifications, linked to that order or booking, for 90 days at most. Each notification travels encrypted "
                      "through your browser's notification service (Google, Apple, Mozilla or Microsoft, depending on the browser), which cannot read it. You "
                      "can turn them off on this page (“Stop notifications on this device”) or in your browser settings. We will never send you advertising this way.</p>")
    if PWA:
        crm_es.append("<p><strong>Web instalable.</strong> Si instalas esta web en tu móvil u ordenador (o activas los avisos), tu navegador guarda una copia "
                      "de las páginas que visitas para que se vean sin conexión. Se queda en tu dispositivo, no nos envía nada y se borra al quitar la web "
                      "o borrar los datos del navegador.</p>")
        crm_en.append("<p><strong>Installable website.</strong> If you install this website on your phone or computer (or turn on notifications), your "
                      "browser keeps a copy of the pages you visit so they work offline. It stays on your device, sends us nothing and is deleted when you "
                      "remove the website or clear the browser data.</p>")
    if NATIVE:
        crm_es.append("<p><strong>App para móvil.</strong> La app trata los mismos datos que la web y con las mismas finalidades: los de tus pedidos y "
                      "reservas, y los que nos escribas. Si activas sus avisos, se entregan con Firebase Cloud Messaging (Google) mediante un identificador "
                      "del dispositivo, durante 90 días como máximo. Puedes pedir que borremos tus datos "
                      + ("desde la app («Mis pedidos» → «Borrar mis datos») o escribiéndonos. " if ACCOUNT else "escribiéndonos. ")
                      + "La tienda de aplicaciones (Apple o Google) trata además tus datos como responsable, con su propia política.</p>")
        crm_en.append("<p><strong>Mobile app.</strong> The app processes the same data as the website, for the same purposes: your orders and bookings "
                      "and what you write to us. If you turn on its notifications, they are delivered with Firebase Cloud Messaging (Google) using a device "
                      "identifier, for 90 days at most. You can ask us to delete your data "
                      + ("from the app (“My orders” → “Delete my data”) or by writing to us. " if ACCOUNT else "by writing to us. ")
                      + "The app store (Apple or Google) also processes your data as controller, under its own policy.</p>")
    transfer = esc(BOT.get("transferencia", "")) or "[CONFIRMAR: garantía de la transferencia internacional según el contrato del proveedor de IA]"
    bot_es = (f"<p><strong>Asistente de chat.</strong> Si usas el asistente automático de la web, tus mensajes se procesan con un "
              f"sistema de inteligencia artificial para responderte, por interés legítimo en atender tus consultas (art. 6.1.f RGPD). "
              f"No escribas datos bancarios, de salud ni otros datos sensibles. Las conversaciones {BOT_RETENTION['es']}. "
              f"La conversación se guarda en el almacenamiento de sesión de tu navegador y se borra al cerrar la pestaña; no usa cookies. "
              f"Si pides que te contactemos, trataremos los datos que nos des para responderte, con tu consentimiento (art. 6.1.a RGPD).</p>"
              + ("<p>El asistente puede consultar precios, existencias y horas libres y dejarte preparado un pedido o una reserva: el enlace "
                 "lleva un código aleatorio, sin datos personales, que caduca en unos días. Nada se compra ni se reserva hasta que tú lo "
                 "confirmas en la web. Si compras o reservas con ese enlace, el pedido guarda el código para saber cuántas ventas trae el "
                 "asistente. Para consultar un pedido, la referencia y el email que escribas en su formulario van directamente a nuestro "
                 "sistema de pedidos sin pasar por la inteligencia artificial y no se guardan.</p>" if ASISTENTE else "")) if BOT_ON else ""
    bot_en = (f"<p><strong>Chat assistant.</strong> If you use the website's automated assistant, your messages are processed by an "
              f"artificial intelligence system to answer you, based on our legitimate interest in handling your enquiries (Art. 6(1)(f) GDPR). "
              f"Do not share bank, health or other sensitive data. Conversations {BOT_RETENTION['en']}. "
              f"The conversation is kept in your browser's session storage and deleted when you close the tab; no cookies are used. "
              f"If you ask us to contact you, we process the details you give us to reply, with your consent (Art. 6(1)(a) GDPR).</p>"
              + ("<p>The assistant can check prices, stock and free slots and leave an order or a booking ready for you: the link carries "
                 "a random code, with no personal data, that expires within a few days. Nothing is bought or booked until you confirm it "
                 "on the website. If you buy or book with that link, the order keeps the code so we know how many sales the assistant "
                 "brings. To check an order, the reference and email you type in its form go straight to our order system without "
                 "passing through the artificial intelligence and are not stored.</p>" if ASISTENTE else "")) if BOT_ON else ""
    vtransfer = esc(VOZ.get("transferencia", "") or BOT.get("transferencia", "")) or "[CONFIRMAR: garantía de la transferencia internacional según los contratos de la plataforma de telefonía y del proveedor de IA]"
    vmail = co("email", lang)
    voz_es = (f"<p><strong>Asistente telefónico.</strong> Si nos llamas, puede atenderte un asistente automático con inteligencia artificial, "
              f"que te lo dice al empezar. Lo que dices se transcribe en el momento para responderte, por interés legítimo en atender tus "
              f"consultas (art. 6.1.f RGPD). La llamada no se graba y las transcripciones {VOZ_RETENTION['es']}. Puedes pedir hablar con una "
              f"persona en cualquier momento diciendo «persona» o pulsando 0. Solo usamos tu número para devolverte la llamada si nos lo pides y "
              f"lo confirmas, o si pediste hablar con alguien y no pudimos atenderte (art. 6.1.b y 6.1.f RGPD). No digas por teléfono datos "
              f"bancarios, de salud ni otros datos sensibles. Si prefieres no hablar con el asistente, escríbenos a {vmail}.</p>") if VOZ_ON else ""
    voz_en = (f"<p><strong>Phone assistant.</strong> When you call us, an automated artificial intelligence assistant may answer; it tells you "
              f"so at the start. What you say is transcribed in real time to answer you, based on our legitimate interest in handling your "
              f"enquiries (Art. 6(1)(f) GDPR). Calls are not recorded and transcripts {VOZ_RETENTION['en']}. You can ask to speak to a person "
              f"at any time by saying “person” or pressing 0. We only use your number to call you back if you ask us to and confirm it, or if "
              f"you asked to speak to someone and we could not take the call (Art. 6(1)(b) and 6(1)(f) GDPR). Do not share bank, health or other "
              f"sensitive data over the phone. If you prefer not to talk to the assistant, email us at {vmail}.</p>") if VOZ_ON else ""
    # Con los proveedores nombrados: quiénes son (el respaldo solo responde si el principal no está disponible) y transferencia solo
    # si alguno está fuera del EEE. Sin nombrarlos, como siempre.
    _ia_n = [f"{esc(x['nombre'])} ({esc(x['pais'])})" for x in IA_PROV]
    _ia_fuera = not IA_PROV or any(not in_eea(x["pais"]) for x in IA_PROV)
    _y = lambda xs, y: xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + f" {y} " + xs[-1]  # noqa: E731
    ia_es = (_y(_ia_n, "y") + " como proveedores de inteligencia artificial y subencargados (el segundo solo responde si el primero no está disponible)"
             if len(_ia_n) > 1 else f"{_ia_n[0]} como proveedor de inteligencia artificial y subencargado" if _ia_n else "")
    ia_en = (_y(_ia_n, "and") + " as artificial intelligence providers and sub-processors (the second one only answers if the first is unavailable)"
             if len(_ia_n) > 1 else f"{_ia_n[0]} as artificial intelligence provider and sub-processor" if _ia_n else "")
    def _transf(t: str, es: bool, telefonia: bool = False) -> str:
        # Con teléfono, la plataforma de telefonía (Twilio) está fuera del EEE: la transferencia se dice siempre.
        if not _ia_fuera and not telefonia:
            return "; los datos se tratan dentro del Espacio Económico Europeo." if es else "; the data is processed within the European Economic Area."
        return (f"; esto puede implicar una transferencia internacional de datos: {t}." if es
                else f"; this may involve an international data transfer: {t}.")
    voz_rec_es = ((" El asistente telefónico lo presta La Taza Roja como encargado del tratamiento, con "
                   + (f"la plataforma de telefonía como subencargado y {ia_es}" if ia_es
                      else "la plataforma de telefonía y un proveedor de inteligencia artificial como subencargados") + _transf(vtransfer, True, telefonia=True)) if VOZ_ON else "")
    voz_rec_en = ((" The phone assistant is provided by La Taza Roja as data processor, using "
                   + (f"the telephony platform as sub-processor and {ia_en}" if ia_en
                      else "the telephony platform and an artificial intelligence provider as sub-processors") + _transf(vtransfer, False, telefonia=True)) if VOZ_ON else "")
    bot_rec_es = ((" El asistente de chat lo presta La Taza Roja como encargado del tratamiento, con "
                   + (ia_es or "un proveedor de inteligencia artificial como subencargado") + _transf(transfer, True)) if BOT_ON else "")
    bot_rec_en = ((" The chat assistant is provided by La Taza Roja as data processor, using "
                   + (ia_en or "an artificial intelligence provider as sub-processor") + _transf(transfer, False)) if BOT_ON else "")
    if lang == "es":
        legal = f"""
<h2>Titular del sitio web</h2>
<p>En cumplimiento del artículo 10 de la Ley 34/2002 de servicios de la sociedad de la información y de comercio electrónico (LSSI-CE):</p>
<ul>
<li><strong>Titular:</strong> {co('legal_name', lang)}</li>
<li><strong>CIF/NIF:</strong> {co('cif', lang)}</li>
<li><strong>Domicilio:</strong> {co('address', lang)}</li>
<li><strong>Email:</strong> {co('email', lang)}</li>
<li><strong>Teléfono:</strong> {co('phone', lang)}</li>
{f"<li><strong>Datos registrales:</strong> {esc(CO['registry'])}</li>" if CO.get('registry') else ''}
</ul>
<h2>Propiedad intelectual</h2>
<p>Los contenidos de este sitio (textos, imágenes, logotipos y diseño) pertenecen a su titular o se usan con autorización. No se permite su reproducción sin permiso.</p>
<h2>Responsabilidad</h2>
<p>El titular procura que la información sea exacta y esté actualizada, pero no se responsabiliza de errores puntuales ni del contenido de sitios enlazados.</p>
<h2>Legislación aplicable</h2>
<p>Este aviso legal se rige por la legislación española.</p>"""
        privacy = f"""
<h2>Responsable del tratamiento</h2>
<p>{co('legal_name', lang)}, CIF {co('cif', lang)}, {co('address', lang)}. Contacto: {co('email', lang)}.</p>
<h2>Qué datos tratamos</h2>
<p><strong>Navegación.</strong> El servidor que aloja la web registra datos técnicos (dirección IP, fecha, página y navegador) por interés legítimo en la seguridad del sitio (art. 6.1.f RGPD).{api_es}</p>
{form_es}
{shop_es}
{med_es}
{"".join(crm_es)}
{bot_es}
{voz_es}
<p>{cookies_es}</p>
<h2>Destinatarios</h2>
{recipients_html("es", bot_rec_es + voz_rec_es)}
<h2>Tus derechos</h2>
<p>Puedes ejercer los derechos de acceso, rectificación, supresión, oposición, limitación y portabilidad escribiendo a {co('email', lang)}. Te contestaremos en el plazo de un mes. Si nos diste tu consentimiento, puedes retirarlo cuando quieras, sin que afecte a lo hecho antes. Los datos marcados como obligatorios en cada formulario son necesarios para atenderte. Si crees que no hemos tratado bien tus datos, puedes reclamar ante la Agencia Española de Protección de Datos (<a href="https://www.aepd.es" rel="noopener">www.aepd.es</a>).</p>"""
    else:
        legal = f"""
<h2>Website owner</h2>
<p>In accordance with Spanish Law 34/2002 on information society services (LSSI-CE):</p>
<ul>
<li><strong>Owner:</strong> {co('legal_name', lang)}</li>
<li><strong>Tax ID:</strong> {co('cif', lang)}</li>
<li><strong>Address:</strong> {co('address', lang)}</li>
<li><strong>Email:</strong> {co('email', lang)}</li>
<li><strong>Phone:</strong> {co('phone', lang)}</li>
{f"<li><strong>Registry details:</strong> {esc(CO['registry'])}</li>" if CO.get('registry') else ''}
</ul>
<h2>Intellectual property</h2>
<p>The content of this site (text, images, logos and design) belongs to its owner or is used with permission. It may not be reproduced without permission.</p>
<h2>Liability</h2>
<p>The owner aims to keep the information accurate and up to date but is not liable for occasional errors or for the content of linked sites.</p>
<h2>Applicable law</h2>
<p>This notice is governed by Spanish law. The Spanish version prevails.</p>"""
        privacy = f"""
<h2>Data controller</h2>
<p>{co('legal_name', lang)}, tax ID {co('cif', lang)}, {co('address', lang)}. Contact: {co('email', lang)}.</p>
<h2>What data we process</h2>
<p><strong>Browsing.</strong> The hosting server records technical data (IP address, date, page and browser) based on legitimate interest in site security (Art. 6(1)(f) GDPR).{api_en}</p>
{form_en}
{shop_en}
{med_en}
{"".join(crm_en)}
{bot_en}
{voz_en}
<p>{cookies_en}</p>
<h2>Recipients</h2>
{recipients_html("en", bot_rec_en + voz_rec_en)}
<h2>Your rights</h2>
<p>You can exercise your rights of access, rectification, erasure, objection, restriction and portability by writing to {co('email', lang)}. We will reply within one month. If you gave us your consent, you can withdraw it at any time without affecting what was done before. Fields marked as required in each form are needed to deal with your request. If you think we have not handled your data properly, you can complain to the Spanish Data Protection Agency (<a href="https://www.aepd.es" rel="noopener">www.aepd.es</a>).</p>"""
    return legal, privacy


def cookies_html(lang: str) -> str:
    """Política de cookies generada con las herramientas activas en site.json > medicion. Revisar con el cliente."""
    es = lang == "es"
    rows = [("ltr_consent", "Este sitio" if es else "This site", "Técnica: guarda tu elección sobre cookies" if es else "Technical: stores your cookie choice",
             "12 meses (almacenamiento local)" if es else "12 months (local storage)")]
    rows.append(("ltr_attr", "Este sitio" if es else "This site", "Origen de la visita (campaña) para atribuir una compra; solo con tu consentimiento"
                 if es else "Visit source (campaign) to attribute a purchase; only with your consent", "Sesión" if es else "Session"))
    if MED_GA4:
        rows.append(("_ga, _ga_*", "Google Analytics", "Análisis: distinguir visitantes y sesiones" if es else "Analytics: tell visitors and sessions apart", "13 meses" if es else "13 months"))
    if MED_ADS:
        rows.append(("_gcl_au", "Google Ads", ("Publicidad: medir conversiones de anuncios" + (" y mostrarte anuncios nuestros según tu visita (remarketing)" if MED_RMK else "")) if es
                     else ("Advertising: measure ad conversions" + (" and show you our ads based on your visit (remarketing)" if MED_RMK else "")), "90 días" if es else "90 days"))
    if MED_META:
        rows.append(("_fbp, _fbc", "Meta", ("Publicidad: medir conversiones de anuncios" + (" y mostrarte anuncios nuestros según tu visita (remarketing)" if MED_RMK else "")) if es
                     else ("Advertising: measure ad conversions" + (" and show you our ads based on your visit (remarketing)" if MED_RMK else "")), "90 días" if es else "90 days"))
    head = ("<tr><th>Nombre</th><th>Titular</th><th>Finalidad</th><th>Duración</th></tr>" if es
            else "<tr><th>Name</th><th>Owner</th><th>Purpose</th><th>Duration</th></tr>")
    table = f'<div class="table-scroll"><table>{head}' + "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td><td>{esc(d)}</td></tr>" for a, b, c, d in rows) + "</table></div>"
    updated = esc(MED.get("politica_actualizada") or CFG["updated"])
    if es:
        return (f"<p>Una cookie es un pequeño archivo que la web guarda en tu navegador. Aquí explicamos cuáles usamos, para qué y cómo cambiar tu elección.</p>"
                f"<h2>Cookies que usamos</h2>{table}"
                "<p>Las de análisis y publicidad <strong>solo se activan si las aceptas</strong> en el aviso que aparece al entrar. Rechazarlas no te impide usar la web ni comprar.</p>"
                "<h2>Cambiar o retirar tu consentimiento</h2><p>En cualquier momento desde «Configurar cookies», en el pie de cada página. Al retirarlo, "
                "borramos las cookies de análisis y publicidad de este sitio. También puedes borrarlas desde la configuración de tu navegador. "
                "Volveremos a preguntarte a los 12 meses.</p>"
                "<h2>Proveedores y transferencias</h2><p>Google y Meta pueden tratar estos datos en EE. UU., con las garantías del Marco de Privacidad de Datos UE-EE. UU. "
                f"Más información en la <a href=\"{url_for('privacy', lang)}\">política de privacidad</a>.</p><p class=\"meta\">Actualizada el {updated}.</p>")
    return (f"<p>A cookie is a small file the site stores in your browser. Here we explain which ones we use, why, and how to change your choice.</p>"
            f"<h2>Cookies we use</h2>{table}"
            "<p>Analytics and advertising cookies <strong>are only switched on if you accept them</strong> in the notice shown when you arrive. Rejecting them does not stop you using the site or buying.</p>"
            "<h2>Change or withdraw consent</h2><p>At any time from “Cookie settings” at the foot of every page. When you withdraw it, we delete this site's "
            "analytics and advertising cookies. You can also delete them in your browser settings. We will ask again after 12 months.</p>"
            "<h2>Providers and transfers</h2><p>Google and Meta may process this data in the USA under the EU-US Data Privacy Framework. "
            f"More in the <a href=\"{url_for('privacy', lang)}\">privacy policy</a>.</p><p class=\"meta\">Updated {updated}.</p>")


def accessibility_html(lang: str) -> str:
    """Declaración de accesibilidad (site.json > accesibilidad). Para tiendas online obligadas por la Ley 11/2023, incluye la
    información del anexo V de la Directiva 2019/882: cómo funciona el servicio y cómo cumple los requisitos. Revisar con el cliente."""
    es = lang == "es"
    owner = co("legal_name", lang)
    contact = esc(A11Y.get("contacto") or CO.get("email", "")) or t(lang)["pending"]
    phone = esc(CO.get("phone", ""))
    days = int(A11Y.get("plazo_respuesta_dias") or 10)
    when = fmt_date(A11Y_DATE, lang) if A11Y_DATE else ("[CONFIRMAR: fecha de la evaluación]" if es else "[CONFIRMAR: evaluation date]")
    reviewed = fmt_date(A11Y_DATE or CFG["updated"], lang)
    state = {"total": ("plenamente conforme", "fully compliant"), "parcial": ("parcialmente conforme", "partially compliant"),
             "no": ("no conforme", "not compliant")}[A11Y_STATE][0 if es else 1]
    method = esc(A11Y.get("metodo" if es else "metodo_en") or (
        "Autoevaluación: revisión automática de todas las páginas con axe-core y revisión manual con teclado, lector de pantalla y ampliación al 400 %."
        if es else "Self-assessment: automated review of every page with axe-core and manual review with keyboard, screen reader and 400% zoom."))
    issues = "".join(f"<li><strong>{esc(i['que'])}</strong>{(' — ' + esc(i['alternativa'])) if i.get('alternativa') else ''}"
                     f"{(' (' + ('previsto: ' if es else 'planned: ') + esc(i['solucion_prevista']) + ')') if i.get('solucion_prevista') else ''}</li>"
                     for i in A11Y_ISSUES)
    if es:
        no_issues = "<p>No conocemos contenido que no sea accesible. Si encuentras alguno, cuéntanoslo.</p>"
        service = ""
        if CAT_BUY or A11Y.get("descripcion_servicio"):
            desc = esc(A11Y.get("descripcion_servicio") or "") or "[CONFIRMAR: qué se vende y cómo se compra, en dos o tres frases]"
            service = (f"<h2>Cómo funciona el servicio</h2><p>{desc}</p><h2>Cómo cumple los requisitos de accesibilidad</h2><ul>"
                       "<li>Todas las páginas, el catálogo y el pedido se pueden usar solo con el teclado, con el foco siempre visible.</li>"
                       "<li>Imágenes con texto alternativo, campos con su etiqueta y mensajes de estado que leen los lectores de pantalla.</li>"
                       "<li>Colores con el contraste mínimo y la página se puede ampliar al 400 % sin perder contenido ni desplazarse en horizontal.</li>"
                       "<li>Sin límites de tiempo en la web; el pago se hace en la página de la pasarela de pago, que publica su propia información de accesibilidad.</li>"
                       "<li>Precios, gastos de envío y condiciones se muestran antes de pagar, en texto.</li></ul>"
                       f"<p>Esta información está disponible también por teléfono{(' (' + phone + ')') if phone else ''} o en otro formato si lo pides.</p>")
        return (f"<p>{owner} se compromete a que esta web sea accesible, de acuerdo con las Pautas de Accesibilidad para el Contenido Web "
                "(WCAG) 2.2, nivel AA, a las que remite la norma europea EN 301 549.</p>"
                f"<h2>Situación de cumplimiento</h2><p>Esta web es <strong>{state}</strong> con las WCAG 2.2 AA"
                f"{', por lo que se indica a continuación' if A11Y_ISSUES else ''}.</p>"
                f"<h2>Contenido no accesible</h2>{('<ul>' + issues + '</ul>') if issues else no_issues}"
                f"{service}"
                f"<h2>Cómo se ha evaluado</h2><p>{method} Fecha de la última evaluación: {esc(when)}.</p>"
                "<h2>Comunicar un problema o pedir el contenido en otro formato</h2>"
                f"<p>Escríbenos a {contact}{(' o llámanos al ' + phone) if phone else ''}. Te contestaremos en un máximo de {days} días laborables "
                "y, si no podemos corregirlo enseguida, te daremos la información de otra forma.</p>"
                "<h2>Si no quedas satisfecho</h2><p>Puedes dirigirte a la autoridad de vigilancia de la accesibilidad de tu comunidad autónoma "
                "(Ley 11/2023) o a la Oficina de Atención a la Discapacidad (OADIS).</p>"
                f"<p class=\"meta\">Declaración revisada el {reviewed}.</p>")
    no_issues = "<p>We are not aware of any inaccessible content. If you find any, please tell us.</p>"
    service = ""
    if CAT_BUY or A11Y.get("descripcion_servicio_en") or A11Y.get("descripcion_servicio"):
        desc = esc(A11Y.get("descripcion_servicio_en") or "") or "[CONFIRMAR: what is sold and how to buy it, in two or three sentences]"
        service = (f"<h2>How the service works</h2><p>{desc}</p><h2>How it meets the accessibility requirements</h2><ul>"
                   "<li>Every page, the catalogue and the order can be used with the keyboard alone, with focus always visible.</li>"
                   "<li>Images have text alternatives, fields have labels and status messages are read by screen readers.</li>"
                   "<li>Colours meet minimum contrast and pages can be zoomed to 400% without losing content or scrolling sideways.</li>"
                   "<li>No time limits on the site; payment takes place on the payment provider's page, which publishes its own accessibility information.</li>"
                   "<li>Prices, delivery costs and terms are shown as text before paying.</li></ul>"
                   f"<p>This information is also available by phone{(' (' + phone + ')') if phone else ''} or in another format on request.</p>")
    return (f"<p>{owner} is committed to making this website accessible in line with the Web Content Accessibility Guidelines (WCAG) 2.2, "
            "level AA, referenced by the European standard EN 301 549.</p>"
            f"<h2>Compliance status</h2><p>This website is <strong>{state}</strong> with WCAG 2.2 AA"
            f"{', for the reasons below' if A11Y_ISSUES else ''}.</p>"
            f"<h2>Non-accessible content</h2>{('<ul>' + issues + '</ul>') if issues else no_issues}"
            f"{service}"
            f"<h2>How it was evaluated</h2><p>{method} Last evaluation: {esc(when)}.</p>"
            "<h2>Report a problem or ask for another format</h2>"
            f"<p>Write to {contact}{(' or call ' + phone) if phone else ''}. We will reply within {days} working days and, "
            "if we cannot fix it straight away, we will give you the information another way.</p>"
            "<h2>If you are not satisfied</h2><p>You can contact the accessibility market surveillance authority of your Spanish region "
            "(Law 11/2023) or the Spanish Disability Office (OADIS).</p>"
            f"<p class=\"meta\">Statement reviewed on {reviewed}. The Spanish version prevails.</p>")


def build_system_pages(lang: str) -> None:
    tt = t(lang)
    u = url_for("accessibility", lang)
    doc = head(lang=lang, title=f"{tt['a11y_title']} | {CFG['site_name']}", desc=tt["a11y_title"], url=u, alts=alternates("accessibility"), noindex=True)
    doc += header(lang, "accessibility") + f'<div class="page-head wrap"><h1>{tt["a11y_title"]}</h1></div><section class="section prose wrap">{accessibility_html(lang)}</section>' + footer(lang)
    write(u, doc)
    if MED_ON:
        u = url_for("cookies", lang)
        doc = head(lang=lang, title=f"{tt['cookies_title']} | {CFG['site_name']}", desc=tt["cookies_title"], url=u, alts=alternates("cookies"), noindex=True)
        doc += header(lang, "cookies") + f'<div class="page-head wrap"><h1>{tt["cookies_title"]}</h1></div><section class="section prose wrap">{cookies_html(lang)}</section>' + footer(lang)
        write(u, doc)
    legal, privacy = legal_html(lang)
    if PUSH_KEY:
        # Retirar el consentimiento tan fácil como darlo: app.js lo enseña solo si este navegador tiene avisos activos.
        privacy += (f'<div class="push-off" data-push-baja data-hecho="{esc(tt["push_off_done"])}" hidden>'
                    f'<p><button type="button" class="btn btn-ghost">{tt["push_off"]}</button></p><p class="meta" role="status" aria-live="polite"></p></div>')
    if PWA:
        u = url_for("offline", lang)
        info = []
        if CO.get("phone"):
            info.append(f'<dt>{tt["phone"]}</dt><dd><a href="tel:{re.sub(r"[^0-9+]", "", CO["phone"])}">{esc(CO["phone"])}</a></dd>')
        if CO.get("address"):
            info.append(f'<dt>{tt["address"]}</dt><dd>{esc(CO["address"])}</dd>')
        hours = (CO.get("opening_hours_text") or {}).get(lang)
        if hours:
            info.append(f'<dt>{tt["hours"]}</dt><dd>{esc(hours)}</dd>')
        contact = f'<p>{tt["offline_contact"]}</p><dl class="contact-info">{"".join(info)}</dl>' if info else ""
        doc = head(lang=lang, title=f"{tt['offline_title']} | {CFG['site_name']}", desc=tt["offline_title"], url=u, alts=alternates("offline"), noindex=True)
        doc += header(lang, "offline") + (f'<div class="page-head wrap"><h1>{tt["offline_title"]}</h1><p class="lead">{tt["offline_body"]}</p>'
                                          f'<p class="actions"><a class="btn" href="{prefix(lang)}">{tt["offline_retry"]}</a></p></div>'
                                          f'<section class="section prose wrap">{contact}</section>') + footer(lang)
        write(u, doc)
    for key, title, body in (("legal", tt["legal_title"], legal), ("privacy", tt["privacy_title"], privacy)):
        u = url_for(key, lang)
        doc = head(lang=lang, title=f"{title} | {CFG['site_name']}", desc=title, url=u, alts=alternates(key), noindex=True)
        doc += header(lang, key) + f'<div class="page-head wrap"><h1>{title}</h1></div><section class="section prose wrap">{body}</section>' + footer(lang)
        write(u, doc)
    if NEWS:
        u = url_for("news_thanks", lang)
        doc = head(lang=lang, title=f"{tt['news_thanks_title']} | {CFG['site_name']}", desc=tt["news_thanks_title"], url=u, alts=alternates("news_thanks"), noindex=True)
        doc += header(lang, "news_thanks") + (f'<div class="page-head wrap"><h1>{tt["news_thanks_title"]}</h1><p class="lead">{tt["news_thanks_body"]}</p>'
                                              f'<p class="actions"><a class="btn" href="{prefix(lang)}">{tt["back_home"]}</a></p></div>') + footer(lang)
        write(u, doc)
    if FORM:
        u = url_for("thanks", lang)
        doc = head(lang=lang, title=f"{tt['thanks_title']} | {CFG['site_name']}", desc=tt["thanks_title"], url=u,
                   alts=alternates("thanks"), noindex=True)
        doc += header(lang, "thanks") + (f'<div class="page-head wrap"><h1>{tt["thanks_title"]}</h1><p class="lead">{tt["thanks_body"]}</p>'
                                         f'<p class="actions"><a class="btn" href="{prefix(lang)}">{tt["back_home"]}</a></p></div>') + footer(lang)
        write(u, doc)


def page_text(body: str) -> str:
    """Texto de una página para el asistente: sin marcas de bloque, imágenes, HTML ni enlaces internos (como `npm run importar`)."""
    body = re.sub(r"^:::\s*\w*\s*$", "", body, flags=re.M)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    body = re.sub(r"\[([^\]]+)\]\(@[\w-]+\)", r"\1", body)
    body = re.sub(r"\[([^\]]+)\]\((https?:[^)]+)\)", r"\1 (\2)", body)
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"^\s*(titulo|poster|archivo|subtitulos|youtube|transcripcion|idioma|sin_voz):.*$", "", body, flags=re.M)  # :::video
    return re.sub(r"\n{3,}", "\n\n", body).strip()[:6000]


def build_assistant_data() -> bool:
    """/asistente.json (solo con el asistente de chat): lo publicado en la web, para que plantilla-bot regenere su conocimiento
    (`npm run conocimiento`). Solo información pública: datos de contacto, horario, cierres, páginas indexables y productos."""
    if not BOT_ON:
        return False
    data = {
        "version": 1, "generado": HOY.isoformat(), "web": SITE_URL, "nombre": CFG["site_name"],
        "empresa": {"direccion": CO.get("address", ""), "telefono": CO.get("phone", ""), "email": CO.get("email", ""),
                    "whatsapp": CO.get("whatsapp", ""), "horario": CO.get("opening_hours_text") or {}, "horario_schema": CO.get("opening_hours", "")},
        "cierres": [{"desde": c["desde"].isoformat(), "hasta": c["hasta"].isoformat(),
                     "motivo": c["motivo"] if isinstance(c["motivo"], dict) else {DEFAULT: str(c["motivo"])}} for c in CIERRES if c["hasta"] >= HOY],
        "paginas": [{"idioma": l, "clave": k, "titulo": pg.get("title", ""), "url": SITE_URL + url_for(k, l), "texto": page_text(pg["body"])}
                    for l in LANGS for k, pg in sorted(pages[l].items()) if pg.get("noindex") != "true" and k not in ("order",)],
        "productos": [{"sku": p["sku"], "nombre": p["name"], "precio_cents": p["price_cents"], "disponible": bool(p.get("disponible", True)),
                       "categoria": p.get("category") or ""} for p in (CATALOG or {}).get("productos", [])],
    }
    (OUT / "asistente.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def build_404() -> None:
    tt = t(DEFAULT)
    doc = head(lang=DEFAULT, title=tt["notfound_title"], desc=tt["notfound_title"], url="/404.html", alts={}, noindex=True)
    doc += header(DEFAULT, "404") + (f'<div class="page-head wrap"><h1>{tt["notfound_title"]}</h1><p class="lead">{tt["notfound_body"]}</p>'
                                     f'<p class="actions"><a class="btn" href="/">{tt["back_home"]}</a></p></div>') + footer(DEFAULT)
    (OUT / "404.html").write_text(doc, encoding="utf-8")


def build_sitemap() -> None:
    keys = set()
    for lang in LANGS:
        keys |= {k for k, pg in pages[lang].items() if pg.get("noindex") != "true"}
        keys |= set(posts[lang])
        if posts[lang]:
            keys.add("blog")
    rows = []
    for key in sorted(keys):
        alts = alternates(key)
        for lang, u in alts.items():
            links = ""
            if len(alts) > 1:
                links = "".join(f'<xhtml:link rel="alternate" hreflang="{l}" href="{SITE_URL + uu}"/>' for l, uu in alts.items())
            rows.append(f"<url><loc>{SITE_URL + u}</loc><lastmod>{CFG['updated']}</lastmod>{links}</url>")
    if CATALOG is not None:
        extra = [lambda l, p=p: product_url(p["sku"], l) for p in CATALOG["productos"]]
        if CAT.get("por_categoria"):
            extra += [lambda l, c=c: category_url(c["slug"], l) for c, _ in catalog_groups() if c]
        for f in extra:
            alts = {l: f(l) for l in CAT_LANGS}
            for lang, u in alts.items():
                links = "".join(f'<xhtml:link rel="alternate" hreflang="{l}" href="{SITE_URL + uu}"/>' for l, uu in alts.items()) if len(alts) > 1 else ""
                rows.append(f"<url><loc>{SITE_URL + u}</loc>{links}</url>")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(rows) + "\n</urlset>\n", encoding="utf-8")
    # Rastreadores de IA: los de búsqueda (OAI-SearchBot, Claude-SearchBot, PerplexityBot) siempre permitidos para aparecer
    # en sus respuestas. Los de entrenamiento se bloquean solo si el cliente lo pide (no afecta a Google Search).
    training = ["GPTBot", "ClaudeBot", "Google-Extended", "CCBot", "Applebot-Extended"]
    block = "".join(f"User-agent: {b}\nDisallow: /\n\n" for b in training) if CFG.get("seo", {}).get("bloquear_entrenamiento_ia") else ""
    (OUT / "robots.txt").write_text(f"{block}User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Redirecciones (site.json > redirecciones): migraciones desde otra web sin perder visitas ni posicionamiento
# ---------------------------------------------------------------------------
# Solo caracteres de URL seguros (lo que no lo sea va codificado con %): así no se puede colar nada en el HTML ni en .htaccess.
_SEG = r"[A-Za-z0-9._~%-]+"
REDIR_SRC_RE = re.compile(rf"^/(?:{_SEG}/)*(?:{_SEG})?(?:\?[A-Za-z0-9._~%=&+-]+)?$")
REDIR_DST_RE = re.compile(rf"^/(?:{_SEG}/)*(?:{_SEG})?(?:#[A-Za-z0-9_-]+)?$")
REDIR_TXT = {"es": ("Esta página se ha movido", "Ir a la nueva dirección"), "en": ("This page has moved", "Go to the new address")}


def _redir_norm(p: str) -> str:
    return p.rstrip("/") or "/"


def redirects() -> list[tuple[str, str]]:
    """[(origen, destino)] validadas. Destino: ruta de esta web (/nueva/) o @clave de una página del idioma principal (@sobre, @sobre#equipo).
    Nunca a otro dominio, nunca encadenadas, nunca la portada como origen."""
    from urllib.parse import unquote
    cfg = CFG.get("redirecciones") or {}
    rules = cfg.get("reglas") or {}
    if not isinstance(rules, dict):
        sys.exit("ERROR: site.json > redirecciones.reglas debe ser {\"/url-vieja/\": \"/url-nueva/\"}")
    out: list[tuple[str, str]] = []
    for src, dst in rules.items():
        if src.startswith("_"):
            continue
        if not isinstance(dst, str) or not dst:
            sys.exit(f"ERROR: site.json > redirecciones: destino vacío para {src!r}")
        if dst.startswith("@"):
            key, _, frag = dst[1:].partition("#")
            dst = url_for(key, DEFAULT) + (f"#{frag}" if frag else "")
        if not REDIR_SRC_RE.fullmatch(src) or src == "/" or "//" in src:
            sys.exit(f"ERROR: site.json > redirecciones: origen no válido {src!r} (ruta que empieza por /, sin espacios ni comillas; "
                     "lo demás codificado con %; nunca la portada)")
        path = src.split("?")[0]
        if any(s in (".", "..") for s in path.split("/")) or re.search(r"[\x00-\x20\x7f]", unquote(src)):
            sys.exit(f"ERROR: site.json > redirecciones: origen no válido {src!r}")
        if not REDIR_DST_RE.fullmatch(dst) or any(s in (".", "..") for s in dst.split("#")[0].split("/")):
            sys.exit(f"ERROR: site.json > redirecciones: destino no válido {dst!r} para {src!r}: solo rutas de esta web (/nueva/) o @clave; "
                     "nunca otro dominio")
        if _redir_norm(path) == _redir_norm(dst.split("#")[0]) and "?" not in src:
            sys.exit(f"ERROR: site.json > redirecciones: {src!r} se redirige a sí misma")
        out.append((src, dst))
    sources = {_redir_norm(s) for s, _ in out if "?" not in s}
    for src, dst in out:
        if _redir_norm(dst.split("#")[0]) in sources:
            sys.exit(f"ERROR: site.json > redirecciones: {src!r} → {dst!r} y {dst!r} también se redirige. Sin cadenas: que apunte al destino final")
    return out


def redirect_page(dst: str) -> str:
    title, link = REDIR_TXT.get(DEFAULT, REDIR_TXT["en"])
    return (f'<!doctype html>\n<html lang="{DEFAULT}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{title}</title><meta name="robots" content="noindex"><link rel="canonical" href="{esc(SITE_URL + dst.split("#")[0])}">'
            f'<meta http-equiv="refresh" content="0; url={esc(dst)}"></head>'
            f'<body><main><h1>{title}</h1><p><a href="{esc(dst)}">{link}</a></p></main></body></html>\n')


def _htaccess_rule(src: str, dst: str) -> list[str]:
    from urllib.parse import unquote
    path, _, query = src.partition("?")
    p = path.lstrip("/")
    pat = re.escape(unquote(p.rstrip("/"))).replace("\\ ", "\\x20") + ("/?" if p.endswith("/") else "")
    lines = [f"RewriteCond %{{QUERY_STRING}} ^{re.escape(query)}$"] if query else []
    return lines + [f"RewriteRule ^{pat}$ {dst} [R=301,L,NE,QSD]"]


def build_redirects() -> int:
    """Una página con redirección inmediata (y canonical) por cada origen: vale en GitHub Pages y en cualquier alojamiento.
    Con redirecciones.htaccess = true (alojamiento Apache, publicación por SFTP) además .htaccess con 301 de verdad, que es lo mejor
    para Google y lo único que sirve para direcciones con parámetros (?p=123) o .php."""
    rules = redirects()
    if not rules:
        return 0
    ht = bool((CFG.get("redirecciones") or {}).get("htaccess"))
    lines: list[str] = []
    for src, dst in rules:
        path, _, query = src.partition("?")
        dpath = dst.split("#")[0]
        target = OUT / dpath.lstrip("/")
        if dpath.endswith("/") or not Path(dpath).suffix:
            target = target / "index.html"
        if not target.exists():
            sys.exit(f"ERROR: site.json > redirecciones: {src!r} lleva a {dst!r}, que no existe en la web")
        last = path.rsplit("/", 1)[-1]
        static_ok = not query and (path.endswith("/") or "." not in last or last.endswith((".html", ".htm")))
        if not static_ok and not ht:
            sys.exit(f"ERROR: site.json > redirecciones: {src!r} solo se puede redirigir con .htaccess (alojamiento Apache): "
                     "en GitHub Pages no hay redirecciones con parámetros ni de .php. Poner redirecciones.htaccess = true o dejarla fuera")
        if static_ok:
            f = OUT / path.lstrip("/")
            f = f if last.endswith((".html", ".htm")) else f / "index.html"
            if f.exists():
                sys.exit(f"ERROR: site.json > redirecciones: {src!r} es una página de esta web; la redirección la taparía")
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(redirect_page(dst), encoding="utf-8")
        if ht:
            lines += _htaccess_rule(src, dst)
    if ht:
        (OUT / ".htaccess").write_text("# Generado por build.py desde site.json > redirecciones. No editar a mano.\n"
                                       "<IfModule mod_rewrite.c>\nRewriteEngine On\n" + "\n".join(lines) + "\n</IfModule>\n", encoding="utf-8")
    return len(rules)


def png_size(path: Path) -> tuple[int, int] | None:
    """Ancho y alto de un PNG leyendo su cabecera (sin Pillow)."""
    b = path.read_bytes()[:24]
    if len(b) < 24 or b[:8] != b"\x89PNG\r\n\x1a\n" or b[12:16] != b"IHDR":
        return None
    return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


SW_TEMPLATE = r"""/* Generado por build.py (site.json > app). No editar a mano: se regenera en cada publicación. */
"use strict";
const VERSION = "%VERSION%";
const PRECACHE = %PRECACHE%;
const OFFLINE = %OFFLINE%;
// Un aviso solo puede abrir páginas de la web o de su API (nunca otra web, aunque el aviso lo pida).
const ORIGINS = [self.location.origin].concat(%ORIGINS%);
const CACHE = "ltr-" + VERSION, PAGES = "ltr-paginas-" + VERSION, MAX_PAGES = 40;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});
// Al publicar una versión nueva, se borra todo lo de la anterior.
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("ltr-") && k !== CACHE && k !== PAGES)
    .map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

// Solo se guarda lo de esta web, completo, sin redirecciones y sin «no-store».
const storable = (res) => res && res.status === 200 && res.type === "basic" && !res.redirected
  && !/no-store|private/i.test(res.headers.get("cache-control") || "");

function offlinePage(path) {
  const k = Object.keys(OFFLINE).filter((p) => p && path.startsWith(p)).sort((a, b) => b.length - a.length)[0];
  return OFFLINE[k || ""];
}

async function keep(cacheName, req, res) {
  const c = await caches.open(cacheName);
  await c.put(req, res);
  const keys = await c.keys();
  for (let i = 0; cacheName === PAGES && i < keys.length - MAX_PAGES; i++) await c.delete(keys[i]);
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return; // pedidos, contacto, reservas: siempre a la red, nunca a la caché
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // API, pasarela de pago, mapas…: ni se tocan ni se guardan
  if (req.mode === "navigate") {
    // Páginas: primero la red (precios y horarios al día); sin conexión, la copia o la página «Sin conexión».
    e.respondWith(fetch(req).then((res) => {
      if (storable(res) && !url.search) e.waitUntil(keep(PAGES, req, res.clone()));
      return res;
    }).catch(async () => (await caches.match(req, { ignoreSearch: true })) || (await caches.match(offlinePage(url.pathname))) || Response.error()));
    return;
  }
  // Estilos, scripts, imágenes y fuentes: de la copia si está; si no, de la red (y se guarda).
  e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
    if (storable(res)) e.waitUntil(keep(CACHE, req, res.clone()));
    return res;
  })));
});

function safeUrl(u) {
  try {
    const x = new URL(u, self.location.origin);
    if (ORIGINS.includes(x.origin) && (x.protocol === "https:" || x.hostname === "localhost" || x.hostname === "127.0.0.1")) return x.href;
  } catch (err) { /* enlace ilegible */ }
  return self.location.origin + "/";
}

// Avisos de la plantilla C (formato «declarativo» de Safari: {web_push: 8030, notification: {title, body, navigate}}).
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = {}; }
  const n = d.notification || {};
  e.waitUntil(self.registration.showNotification(String(n.title || "Aviso").slice(0, 80), {
    body: String(n.body || "").slice(0, 240), lang: n.lang || undefined, icon: "/app/icono-192.png", data: { url: safeUrl(n.navigate || "/") },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = safeUrl((e.notification.data || {}).url || "/");
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) if (c.url === url && "focus" in c) return c.focus();
    return self.clients.openWindow(url);
  }));
});
"""


def build_app() -> list[str]:
    """Web instalable y apps: manifiesto, service worker, «Sin conexión» y los archivos de /.well-known para los enlaces con las apps.
    Devuelve la lista de lo generado."""
    made: list[str] = []
    if PWA:
        bad = []
        for rel, side in APP_ICONS:
            f = STATIC / rel
            size = png_size(f) if f.is_file() else None
            if size != (side, side):
                bad.append(f"static/{rel} ({side}×{side} px){' — mide ' + 'x'.join(map(str, size)) if size else ''}")
        if bad:
            sys.exit("ERROR: site.json > app.pwa: faltan o no miden lo que deben los iconos: " + ", ".join(bad)
                     + ". Generarlos con: python tools/iconos.py simbolo.png")
        icons = [{"src": "/app/icono-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                 {"src": "/app/icono-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                 {"src": "/app/icono-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]
        manifest = {"id": "/", "name": APP_NAME, "short_name": APP_SHORT, "description": pages[DEFAULT]["home"]["description"],
                    "lang": DEFAULT, "dir": "ltr", "start_url": "/", "scope": "/", "display": "standalone",
                    "background_color": APP_BG, "theme_color": BRAND["primary"], "icons": icons}
        if STORE_ANDROID:
            # Sin «prefer_related_applications»: la web sigue siendo instalable; la app se ofrece, no se impone.
            manifest["related_applications"] = [{"platform": "play", "url": STORE_ANDROID, "id": AND_PKG or STORE_ANDROID.split("id=", 1)[1]}]
        (OUT / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        made.append("manifest.webmanifest")
    if IOS_APP_ID:
        comps = [{"/": p, "exclude": True} for p in IOS_EXCLUDE] + [{"/": p} for p in IOS_PATHS]
        aasa = {"applinks": {"details": [{"appIDs": [IOS_APP_ID], "components": comps}]}, "webcredentials": {"apps": [IOS_APP_ID]}}
        wk = OUT / ".well-known"
        wk.mkdir(exist_ok=True)
        # Sin extensión, sin redirecciones y por https (Apple lo descarga desde su CDN). Con Apache, que lo sirva como JSON.
        (wk / "apple-app-site-association").write_text(json.dumps(aasa, indent=2), encoding="utf-8")
        if (CFG.get("redirecciones") or {}).get("htaccess"):
            (wk / ".htaccess").write_text('<Files "apple-app-site-association">\nForceType application/json\n</Files>\n', encoding="utf-8")
        made.append(".well-known/apple-app-site-association")
    if AND_PKG:
        wk = OUT / ".well-known"
        wk.mkdir(exist_ok=True)
        links = [{"relation": ["delegate_permission/common.handle_all_urls"],
                  "target": {"namespace": "android_app", "package_name": AND_PKG, "sha256_cert_fingerprints": AND_FP}}]
        (wk / "assetlinks.json").write_text(json.dumps(links, indent=2), encoding="utf-8")
        made.append(".well-known/assetlinks.json")
    return made


def write_sw() -> None:
    """El service worker va al final: su versión es la huella de todo lo publicado (cualquier cambio renueva la copia sin conexión)."""
    if not PWA:
        return
    h = hashlib.sha1()
    for f in sorted(p for p in OUT.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(OUT)).encode())
        h.update(f.read_bytes())
    offline = {("" if l == DEFAULT else prefix(l)): url_for("offline", l) for l in LANGS}
    precache = sorted({"/", *offline.values(), f"/style.css?v={CSS_V}", "/favicon.svg", f"/app.js?v={APP_JS_V}",
                       *("/" + rel for rel, _ in APP_ICONS[:2])} | ({"/" + BRAND["logo"]} if BRAND.get("logo") else set()))
    origins = sorted({o for o in (CAT_API, PUSH_API, re.sub(r"^(https://[^/]+).*$", r"\1", ACCOUNT) if ACCOUNT else "") if o})
    sw = (SW_TEMPLATE.replace("%VERSION%", h.hexdigest()[:12]).replace("%PRECACHE%", json.dumps(precache))
          .replace("%OFFLINE%", json.dumps(offline)).replace("%ORIGINS%", json.dumps(origins)))
    (OUT / "sw.js").write_text(sw, encoding="utf-8")


CSS_V = "dev"
APP_JS_V = "dev"


def main() -> None:
    global CSS_V, APP_JS_V
    if OUT.exists():
        shutil.rmtree(OUT)
    # Sin archivos ocultos de static/ (.DS_Store, .env…): GitHub Pages publica los ocultos (hacen falta para /.well-known).
    shutil.copytree(STATIC, OUT, ignore=shutil.ignore_patterns(".*"))
    CSS_V = hashlib.sha1((STATIC / "style.css").read_bytes()).hexdigest()[:8]
    APP_JS_V = hashlib.sha1((STATIC / "app.js").read_bytes()).hexdigest()[:8] if (STATIC / "app.js").exists() else "dev"
    if not PWA:
        (OUT / "app.js").unlink(missing_ok=True)
    if CFG.get("custom_domain"):
        (OUT / "CNAME").write_text(CFG["custom_domain"] + "\n", encoding="utf-8")
    for lang in LANGS:
        for pg in pages[lang].values():
            build_page(pg)
        build_blog(lang)
        build_catalog(lang)
        build_prepared_order(lang)
        build_system_pages(lang)
    build_404()
    build_sitemap()
    n = len(list(OUT.rglob("index.html")))
    n_redir = build_redirects()
    app_files = build_app()
    datos_asistente = build_assistant_data()
    write_sw()
    print(f"OK: {n} páginas en public/ ({', '.join(LANGS)})" + (f" · catálogo: {len(CATALOG['productos'])} productos" if CATALOG is not None else "")
          + (f" · {n_redir} redirecciones" if n_redir else "") + (" · asistente.json" if datos_asistente else "") + (f" · app: {', '.join(app_files + (['sw.js'] if PWA else []))}" if app_files else ""))
    if missing_legal:
        print("AVISO: faltan datos legales en site.json > company: " + ", ".join(sorted(missing_legal)))


if __name__ == "__main__":
    main()
