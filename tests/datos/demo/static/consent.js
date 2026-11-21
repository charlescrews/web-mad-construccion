/* Consentimiento de cookies y medición · plantilla A de La Taza Roja.
   - Nada de Google ni de Meta se carga hasta que la persona acepta (Consent Mode «básico»).
   - «Rechazar todas» está en la primera capa, al mismo nivel y con el mismo aspecto que «Aceptar todas» (guía de la AEPD).
   - La elección se guarda en el navegador (almacenamiento técnico, exento) y se vuelve a preguntar a los 12 meses.
   - Retirar el consentimiento es igual de fácil: enlace «Configurar cookies» en el pie; al retirarlo se borran las cookies de medición.
   - Con consentimiento, guarda el origen de la visita (UTM, gclid, fbclid; gbraid o wbraid en clics de Google desde iPhone) en la sesión y
     lo añade a los formularios de compra y contacto. */
(function () {
  "use strict";
  var me = document.currentScript;
  var cfg = {
    ga4: me.getAttribute("data-ga4") || "",
    ads: me.getAttribute("data-ads") || "",
    meta: me.getAttribute("data-meta") || "",
    // Remarketing (site.json > medicion.remarketing): enseñar anuncios a quien visitó la web es otra finalidad; sin ella, la
    // publicidad solo mide (ad_personalization denegado) y el texto del aviso lo dice así.
    remarketing: me.getAttribute("data-remarketing") === "1",
    policy: me.getAttribute("data-policy") || "/",
    lang: document.documentElement.lang === "en" ? "en" : "es",
  };
  var KEY = "ltr_consent", ATTR = "ltr_attr", MAX_AGE_DAYS = 365, VERSION = 1;
  var T = {
    es: { title: "Cookies", text: "Usamos cookies propias y de terceros para medir las visitas y, si lo aceptas, para medir y mejorar nuestra publicidad. Puedes aceptarlas, rechazarlas o elegir.",
      accept: "Aceptar todas", reject: "Rechazar todas", config: "Configurar", save: "Guardar mi elección", more: "Política de cookies",
      legend: "Elige qué cookies aceptas", tech: "Técnicas (necesarias, siempre activas)", analytics: "Análisis: saber cuántas visitas hay y qué páginas se ven", ads: "Publicidad: medir los resultados de nuestros anuncios",
      textRmk: "Usamos cookies propias y de terceros para medir las visitas y, si lo aceptas, para medir nuestra publicidad y mostrarte anuncios nuestros en otras webs y redes según tu visita. Puedes aceptarlas, rechazarlas o elegir.",
      adsRmk: "Publicidad: medir nuestros anuncios y mostrarte anuncios nuestros en otras webs y redes según tu visita (remarketing)" },
    en: { title: "Cookies", text: "We use our own and third-party cookies to measure visits and, if you accept, to measure and improve our advertising. You can accept, reject or choose.",
      accept: "Accept all", reject: "Reject all", config: "Settings", save: "Save my choice", more: "Cookie policy",
      legend: "Choose which cookies you accept", tech: "Technical (necessary, always on)", analytics: "Analytics: how many visits and which pages are seen", ads: "Advertising: measure the results of our ads",
      textRmk: "We use our own and third-party cookies to measure visits and, if you accept, to measure our advertising and show you our ads on other sites and social networks based on your visit. You can accept, reject or choose.",
      adsRmk: "Advertising: measure our ads and show you our ads on other sites and social networks based on your visit (remarketing)" },
  }[cfg.lang];
  var hasAnalytics = !!cfg.ga4, hasAds = !!(cfg.ads || cfg.meta);
  if (cfg.remarketing && hasAds) { T.text = T.textRmk; T.ads = T.adsRmk; }

  function read() {
    try {
      var c = JSON.parse(localStorage.getItem(KEY) || "null");
      if (!c || c.v !== VERSION || (Date.now() - new Date(c.at).getTime()) > MAX_AGE_DAYS * 864e5) return null;
      // Si la web empieza a hacer remarketing, el «sí» a publicidad que se dio antes no lo cubre: se vuelve a preguntar.
      if (cfg.remarketing && hasAds && c.publicidad && !c.rmk) return null;
      return c;
    } catch (e) { return null; }
  }
  function write(analitica, publicidad) {
    var c = { v: VERSION, analitica: !!analitica && hasAnalytics, publicidad: !!publicidad && hasAds, rmk: !!publicidad && hasAds && cfg.remarketing, at: new Date().toISOString() };
    try { localStorage.setItem(KEY, JSON.stringify(c)); } catch (e) { /* sin almacenamiento: se pregunta en cada página */ }
    return c;
  }

  // ---------- Origen de la visita (solo se guarda con consentimiento) ----------
  var pending = null;
  (function () {
    var q = new URLSearchParams(location.search), a = {}, n = 0;
    ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "gbraid", "wbraid", "fbclid"].forEach(function (k) {
      var v = q.get(k);
      if (v) { a[k] = v.slice(0, 120); n++; }
    });
    if (n) { a.landing = location.pathname.slice(0, 200); pending = a; }
  })();
  function saveAttribution(c) {
    if (!pending || !(c.analitica || c.publicidad)) return;
    try { sessionStorage.setItem(ATTR, JSON.stringify(pending)); } catch (e) { /* nada */ }
  }
  function cookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }
  /** Añade a los formularios el origen y el consentimiento: el servidor solo envía conversiones de quien aceptó. */
  function decorate(form, c) {
    var add = function (k, v) {
      if (!v) return;
      var el = form.querySelector('input[type=hidden][name="' + k + '"]');
      if (!el) { el = document.createElement("input"); el.type = "hidden"; el.name = k; form.appendChild(el); }
      el.value = v;
    };
    add("consent_analitica", c && c.analitica ? "yes" : "");
    add("consent_publicidad", c && c.publicidad ? "yes" : "");
    add("consent_remarketing", c && c.publicidad && c.rmk && cfg.remarketing ? "yes" : "");
    if (!c || !(c.analitica || c.publicidad)) return;
    var a = {};
    try { a = JSON.parse(sessionStorage.getItem(ATTR) || "{}"); } catch (e) { /* nada */ }
    Object.keys(a).forEach(function (k) { add(k, a[k]); });
    if (c.analitica) {
      var ga = cookie("_ga").split(".");
      if (ga.length >= 4) add("ga_client_id", ga[2] + "." + ga[3]);
    }
    if (c.publicidad) { add("fbp", cookie("_fbp")); add("fbc", cookie("_fbc")); }
  }
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (!f.matches || !f.matches("form.buy, form.contact-form")) return;
    var c = read();
    decorate(f, c);
    if (c && c.analitica && window.gtag && f.matches("form.contact-form")) window.gtag("event", "generate_lead");
  }, true);

  // ---------- Etiquetas: solo después de aceptar ----------
  var loaded = false;
  function load(c) {
    if (loaded || !(c.analitica || c.publicidad)) return;
    loaded = true;
    if ((c.analitica && cfg.ga4) || (c.publicidad && cfg.ads)) {
      window.dataLayer = window.dataLayer || [];
      window.gtag = function () { window.dataLayer.push(arguments); };
      window.gtag("consent", "default", { ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied", analytics_storage: "denied" });
      window.gtag("consent", "update", {
        analytics_storage: c.analitica ? "granted" : "denied",
        ad_storage: c.publicidad ? "granted" : "denied",
        ad_user_data: c.publicidad ? "granted" : "denied",
        ad_personalization: c.publicidad && cfg.remarketing ? "granted" : "denied",
      });
      window.gtag("js", new Date());
      // Cookies de análisis de 13 meses como máximo, no los 2 años por defecto.
      if (c.analitica && cfg.ga4) window.gtag("config", cfg.ga4, { cookie_expires: 34128000 });
      if (c.publicidad && cfg.ads) window.gtag("config", cfg.ads, { allow_ad_personalization_signals: !!(c.rmk && cfg.remarketing) });
      var s = document.createElement("script");
      s.async = true;
      s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent((c.analitica && cfg.ga4) || cfg.ads);
      document.head.appendChild(s);
    }
    if (c.publicidad && cfg.meta) {
      var f = window.fbq = function () { f.callMethod ? f.callMethod.apply(f, arguments) : f.queue.push(arguments); };
      if (!window._fbq) window._fbq = f;
      f.push = f; f.loaded = true; f.version = "2.0"; f.queue = [];
      var m = document.createElement("script");
      m.async = true;
      m.src = "https://connect.facebook.net/en_US/fbevents.js";
      document.head.appendChild(m);
      window.fbq("init", cfg.meta);
      window.fbq("track", "PageView");
    }
  }

  /** Al retirar el consentimiento: borrar las cookies de medición del dominio y recargar para descargar las etiquetas. */
  function clearCookies() {
    var host = location.hostname.split("."), domains = [""];
    for (var i = 0; i < host.length - 1; i++) domains.push("; domain=." + host.slice(i).join("."));
    document.cookie.split("; ").forEach(function (kv) {
      var name = kv.split("=")[0];
      if (/^(_ga|_gid|_gat|_gcl_|_fbp|_fbc)/.test(name)) {
        domains.forEach(function (d) { document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/" + d; });
      }
    });
    try { sessionStorage.removeItem(ATTR); } catch (e) { /* nada */ }
  }

  // ---------- Banner ----------
  var box;
  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text) e.textContent = text;
    return e;
  }
  function choose(analitica, publicidad) {
    var before = read();
    var c = write(analitica, publicidad);
    var revoked = before && ((before.analitica && !c.analitica) || (before.publicidad && !c.publicidad));
    close();
    if (revoked) { clearCookies(); location.reload(); return; }
    saveAttribution(c);
    load(c);
  }
  // Accesibilidad: al cerrar, el foco vuelve a donde estaba (o al contenido), y mientras el aviso está abierto
  // la página deja sitio debajo para que lo que recibe el foco no quede tapado por el aviso (WCAG 2.4.3 y 2.4.11).
  var returnTo = null;
  function close(reopening) {
    if (!box) return;
    var hadFocus = !reopening && box.contains(document.activeElement);
    box.remove(); box = null;
    document.documentElement.style.scrollPaddingBottom = "";
    document.body.style.paddingBottom = "";
    if (hadFocus) {
      var t = returnTo && document.contains(returnTo) ? returnTo : document.getElementById("main");
      if (t) {
        if (t.id === "main" && !t.hasAttribute("tabindex")) t.setAttribute("tabindex", "-1");
        t.focus({ preventScroll: true });
      }
    }
    if (!reopening) returnTo = null;
  }
  function open(detailed) {
    var prev = document.activeElement;
    var fromBox = !!(box && box.contains(prev));
    close(true);
    if (!fromBox) returnTo = prev && prev !== document.body ? prev : null;
    var c = read() || { analitica: false, publicidad: false };
    box = el("div", { class: "consent", role: "dialog", "aria-modal": "false", "aria-labelledby": "consent-title" });
    var inner = el("div", { class: "consent-inner wrap" });
    inner.appendChild(el("p", { class: "consent-title", id: "consent-title" }, T.title));
    var p = el("p", {}, T.text + " ");
    var a = el("a", { href: cfg.policy }, T.more);
    p.appendChild(a);
    inner.appendChild(p);
    var opts;
    if (detailed) {
      opts = el("fieldset", { class: "consent-options" });
      opts.appendChild(el("legend", { class: "sr" }, T.legend));
      var row = function (name, label, on, disabled) {
        var l = el("label", {});
        var i = el("input", { type: "checkbox", name: name });
        i.checked = on; i.disabled = !!disabled;
        l.appendChild(i); l.appendChild(document.createTextNode(" " + label));
        opts.appendChild(l);
      };
      row("tecnicas", T.tech, true, true);
      if (hasAnalytics) row("analitica", T.analytics, !!c.analitica);
      if (hasAds) row("publicidad", T.ads, !!c.publicidad);
      inner.appendChild(opts);
    }
    var actions = el("div", { class: "consent-actions" });
    // Mismo aspecto para aceptar y rechazar: ninguno destaca sobre el otro.
    var acc = el("button", { type: "button", class: "btn consent-btn", "data-consent": "accept" }, T.accept);
    var rej = el("button", { type: "button", class: "btn consent-btn", "data-consent": "reject" }, T.reject);
    actions.appendChild(acc); actions.appendChild(rej);
    if (detailed) {
      var save = el("button", { type: "button", class: "btn btn-ghost", "data-consent": "save" }, T.save);
      actions.appendChild(save);
    } else {
      var conf = el("button", { type: "button", class: "btn btn-ghost", "data-consent": "config" }, T.config);
      actions.appendChild(conf);
    }
    inner.appendChild(actions);
    box.appendChild(inner);
    box.addEventListener("click", function (e) {
      var b = e.target.closest("[data-consent]");
      if (!b) return;
      var what = b.getAttribute("data-consent");
      if (what === "accept") choose(true, true);
      else if (what === "reject") choose(false, false);
      else if (what === "config") { open(true); }
      else if (what === "save") {
        var an = opts.querySelector('input[name="analitica"]'), pu = opts.querySelector('input[name="publicidad"]');
        choose(!!(an && an.checked), !!(pu && pu.checked));
      }
    });
    document.body.appendChild(box);
    // Sitio debajo del aviso: el final de la página (pie, enlaces legales) se puede ver y usar con el aviso abierto.
    document.documentElement.style.scrollPaddingBottom = box.offsetHeight + 16 + "px";
    document.body.style.paddingBottom = box.offsetHeight + "px";
    acc.focus({ preventScroll: true });
  }

  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-consent-open]");
    if (t) { e.preventDefault(); open(true); }
  });

  var current = read();
  if (current) { saveAttribution(current); load(current); }
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { open(false); });
  else open(false);
})();
