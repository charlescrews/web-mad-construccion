/* Catálogo · plantilla A de La Taza Roja.
   Sin este script la web funciona igual (listado completo y fichas). Con él:
   - buscador y filtros en el listado, sobre las tarjetas que ya están en la página (no hace falta red);
   - si hay API (data-api), precios y disponibilidad al día, y los productos retirados desaparecen.
   No usa cookies ni almacenamiento. Todo el texto que llega de la API se pone con textContent, nunca como HTML. */
(function () {
  "use strict";
  var norm = function (s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  };
  var money = function (cents, lang) {
    return new Intl.NumberFormat(lang === "en" ? "en-IE" : "es-ES", { style: "currency", currency: "EUR" }).format(cents / 100);
  };
  var getJSON = function (url) {
    return fetch(url, { headers: { Accept: "application/json" }, credentials: "omit" }).then(function (r) {
      if (r.status === 404) return { notFound: true };
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  };

  // ---------- Listado ----------
  document.querySelectorAll("section.catalog").forEach(function (sec) {
    var lang = sec.getAttribute("data-lang") || "es";
    var form = sec.querySelector(".catalog-tools");
    var count = sec.querySelector(".catalog-count");
    var sorted = sec.querySelector(".products.sorted");
    var cards = Array.prototype.slice.call(sec.querySelectorAll(".card.product"));
    var home = cards.map(function (c) { return { card: c, parent: c.parentNode }; });

    function apply() {
      if (!form) return;
      var q = norm(form.q.value).split(" ").filter(Boolean);
      var cat = form.cat ? form.cat.value : "";
      var disp = form.disp.checked;
      var orden = form.orden.value;
      var visible = 0;
      cards.forEach(function (c) {
        var ok = c.getAttribute("data-gone") !== "1"
          && (!cat || c.getAttribute("data-cat") === cat)
          && (!disp || c.getAttribute("data-disp") === "1")
          && q.every(function (w) { return c.getAttribute("data-search").indexOf(w) !== -1; });
        c.hidden = !ok;
        if (ok) visible++;
      });
      if (orden) {
        // Orden por precio: todas las tarjetas en una sola lista.
        var list = cards.slice().sort(function (a, b) {
          var d = Number(a.getAttribute("data-price")) - Number(b.getAttribute("data-price"));
          return orden === "up" ? d : -d;
        });
        list.forEach(function (c) { sorted.appendChild(c); });
        sorted.hidden = false;
        sec.querySelectorAll(".product-group").forEach(function (g) { g.hidden = true; });
      } else {
        home.forEach(function (h) { h.parent.appendChild(h.card); });
        sorted.hidden = true;
        sec.querySelectorAll(".product-group").forEach(function (g) {
          g.hidden = !g.querySelector(".card.product:not([hidden])");
        });
      }
      if (count) {
        count.hidden = false;
        count.textContent = visible ? count.getAttribute("data-template").replace("{n}", visible) : count.getAttribute("data-none");
      }
    }

    if (form) {
      form.hidden = false;
      form.addEventListener("input", apply);
      form.addEventListener("change", apply);
      form.addEventListener("submit", function (e) { e.preventDefault(); apply(); });
    }

    var api = sec.getAttribute("data-api");
    if (api) {
      getJSON(api + "/api/catalogo/export.json").then(function (data) {
        if (!data || !data.productos) return;
        var by = {};
        data.productos.forEach(function (p) { by[p.sku] = p; });
        cards.forEach(function (c) {
          var p = by[c.getAttribute("data-sku")];
          if (!p) { c.setAttribute("data-gone", "1"); c.hidden = true; return; }
          c.setAttribute("data-price", p.price_cents);
          c.setAttribute("data-disp", p.disponible ? "1" : "0");
          var price = c.querySelector(".price");
          if (price) price.textContent = money(p.price_cents, lang);
          var out = c.querySelector(".out");
          if (out) out.hidden = !!p.disponible;
        });
        apply();
      }).catch(function () { /* sin conexión con la API: se queda lo publicado */ });
    }
  });

  // ---------- Ficha de producto ----------
  var page = document.querySelector(".product-page[data-api]");
  if (page) {
    var lang = page.getAttribute("data-lang") || "es";
    var btn = page.querySelector("form.buy button");
    var out = page.querySelector(".out");
    getJSON(page.getAttribute("data-api") + "/api/catalogo/" + encodeURIComponent(page.getAttribute("data-sku"))).then(function (d) {
      if (d.notFound) {
        if (out) { out.hidden = false; out.textContent = page.getAttribute("data-gone"); }
        if (btn) { btn.disabled = true; btn.textContent = page.getAttribute("data-out"); }
        return;
      }
      var p = d.producto;
      if (!p) return;
      var amount = page.querySelector(".price .amount");
      if (amount) amount.textContent = money(p.price_cents, lang);
      if (out) out.hidden = !!p.disponible;
      if (btn) {
        btn.disabled = !p.disponible;
        btn.textContent = page.getAttribute(p.disponible ? "data-buy" : "data-out");
      }
    }).catch(function () { /* sin conexión con la API: se queda lo publicado */ });
  }
})();

/* Pedido preparado por el asistente (site.json > catalog.asistente; skill asistente-conectado-cliente): /pedido/?propuesta=<id>.
   Lee la propuesta de la plantilla C (precios de hoy), la enseña con textContent y rellena el formulario de compra con sus productos y
   el id. Nada se guarda en el navegador. Una propuesta caducada o inventada lleva al catálogo; el pago lo decide siempre la plantilla C. */
(function () {
  "use strict";
  var sec = document.querySelector("section.prepared[data-api]");
  if (!sec) return;
  var lang = sec.getAttribute("data-lang") || "es";
  var status = sec.querySelector(".status"), box = sec.querySelector(".prepared-order");
  var say = function (attr) { status.textContent = sec.getAttribute(attr); };
  var id = "";
  try { id = new URLSearchParams(location.search).get("propuesta") || ""; } catch (e) { id = ""; }
  if (!/^[A-Za-z0-9_-]{22}$/.test(id)) { say("data-none"); return; }
  var money = function (cents) {
    return new Intl.NumberFormat(lang === "en" ? "en-IE" : "es-ES", { style: "currency", currency: "EUR" }).format(cents / 100);
  };
  fetch(sec.getAttribute("data-api") + "/api/asistente/propuestas/" + id, { headers: { Accept: "application/json" }, credentials: "omit" })
    .then(function (r) {
      if (r.status === 404) return null;
      if (!r.ok) throw new Error(r.status);
      return r.json();
    })
    .then(function (d) {
      if (!d || d.tipo !== "cesta" || !d.lineas || !d.lineas.length) { say("data-gone"); return; }
      var ul = sec.querySelector(".prepared-lines"), items = sec.querySelector(".prepared-items");
      d.lineas.forEach(function (l) {
        var li = document.createElement("li");
        li.textContent = l.cantidad + " × " + l.nombre + " · " + money(l.total_cents);
        ul.appendChild(li);
        var s = document.createElement("input"); s.type = "hidden"; s.name = "sku"; s.value = l.sku; items.appendChild(s);
        var q = document.createElement("input"); q.type = "hidden"; q.name = "qty"; q.value = String(l.cantidad); items.appendChild(q);
      });
      sec.querySelector(".prepared-total").textContent = money(d.total_cents);
      sec.querySelector("input[name=propuesta]").value = id;
      status.textContent = "";
      box.hidden = false;
    })
    .catch(function () { say("data-error"); });
})();

/* Avisos por WhatsApp en el pedido (site.json > whatsapp.avisos): el móvil solo es obligatorio si se marca la casilla, y el navegador
   lo dice en el propio campo antes de enviar. La plantilla C lo comprueba otra vez en el servidor. */
(function () {
  "use strict";
  document.querySelectorAll("form.buy").forEach(function (f) {
    var box = f.querySelector("input[name=consent_whatsapp]"), tel = f.querySelector("input[name=whatsapp]");
    if (!box || !tel) return;
    var sync = function () { tel.required = box.checked; };
    box.addEventListener("change", sync);
    sync();
  });
})();
