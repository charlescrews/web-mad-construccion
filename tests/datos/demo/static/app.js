/* Web instalable (site.json > app · skill apps-moviles-cliente). Sin cookies ni dependencias.
 * - El service worker (copia sin conexión) se registra solo si la web está instalada o si la persona pide avisos: a quien solo
 *   visita la web no se le guarda nada en el navegador.
 * - Avisos (app.push): la casilla del pedido aparece si el navegador puede recibirlos (en iPhone, con la web en la pantalla de
 *   inicio), viene sin marcar y pide el permiso al marcarla; la suscripción viaja con el pedido y la plantilla C la liga a él.
 * - En la política de privacidad, «Dejar de recibir avisos en este dispositivo» si este navegador los tiene activos.
 */
(function () {
  "use strict";
  var me = document.currentScript;
  if (!me || !("serviceWorker" in navigator)) return;
  var KEY = me.getAttribute("data-key") || "", API = me.getAttribute("data-api") || "";
  var installed = (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
  var reg = null;

  function worker() {
    if (!reg) reg = navigator.serviceWorker.register("/sw.js").then(function () { return navigator.serviceWorker.ready; });
    return reg;
  }
  // Instalada, o con un service worker de antes (avisos activados otro día): se registra para tener la copia al día.
  navigator.serviceWorker.getRegistration("/").then(function (r) { if (r || installed) worker().catch(function () {}); });

  var canPush = KEY && "PushManager" in window && "Notification" in window;
  if (!canPush) return;

  function key(b64) {
    var s = b64.replace(/-/g, "+").replace(/_/g, "/"), raw = atob(s + "===".slice((s.length + 3) % 4)), a = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) a[i] = raw.charCodeAt(i);
    return a;
  }

  document.querySelectorAll("[data-push]").forEach(function (box) {
    var form = box.closest("form"), cb = box.querySelector("input[name=consent_push]"), field = box.querySelector("input[name=push_suscripcion]");
    var msg = box.querySelector(".push-msg"), pending = null;
    if (!form || !cb || !field) return;
    box.hidden = false;
    cb.addEventListener("change", function () {
      msg.textContent = "";
      field.value = "";
      if (!cb.checked) { pending = null; return; }
      // El permiso se pide aquí, porque la persona acaba de pedir los avisos (nunca al cargar la página).
      pending = Notification.requestPermission().then(function (p) {
        if (p !== "granted") throw new Error("denegado");
        return worker();
      }).then(function (r) {
        return r.pushManager.getSubscription().then(function (old) {
          return old || r.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key(KEY) });
        });
      }).then(function (sub) {
        field.value = JSON.stringify(sub.toJSON());
      }).catch(function () {
        cb.checked = false; field.value = ""; msg.textContent = box.getAttribute("data-bloqueado"); cb.focus();
      });
    });
    // Si se pulsa «Comprar» mientras el navegador aún prepara la suscripción, se espera y se envía después.
    form.addEventListener("submit", function (e) {
      if (!cb.checked || field.value || !pending) return;
      e.preventDefault();
      pending.then(function () { if (form.reportValidity()) form.submit(); });
    });
  });

  document.querySelectorAll("[data-push-baja]").forEach(function (box) {
    navigator.serviceWorker.getRegistration("/").then(function (r) { return r ? r.pushManager.getSubscription() : null; }).then(function (sub) {
      if (!sub) return;
      var btn = box.querySelector("button"), msg = box.querySelector("[role=status]");
      box.hidden = false;
      btn.addEventListener("click", function () {
        btn.disabled = true;
        // Primero se avisa a la API (deja de enviar); aunque no conteste, el navegador deja de recibir al anular la suscripción.
        fetch(API + "/api/push/baja", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ endpoint: sub.endpoint }) })
          .catch(function () {})
          .then(function () { return sub.unsubscribe(); })
          .then(function () { msg.textContent = box.getAttribute("data-hecho"); btn.closest("p").hidden = true; });
      });
    }).catch(function () {});
  });
})();
