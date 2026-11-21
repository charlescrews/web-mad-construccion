/* Aviso de idioma · plantilla A de La Taza Roja.
   Si el navegador prefiere otro idioma de los que tiene la web (navigator.languages) y esta página existe en él, enseña el aviso que
   build.py dejó oculto («This page is also available in English · View in English»). No redirige a nadie. «Cerrar» lo oculta en el
   resto de la visita (sessionStorage; si no está disponible, solo en esta página). Sin cookies ni nada de fuera. */
(function () {
  "use strict";
  var avisos = document.querySelectorAll(".aviso-idioma[data-idioma]");
  if (!avisos.length) return;
  var CLAVE = "aviso-idioma-cerrado";
  try { if (sessionStorage.getItem(CLAVE)) return; } catch (e) { /* sin almacenamiento: se decide en cada página */ }
  var actual = (document.documentElement.lang || "").toLowerCase().split("-")[0];
  var prefs = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || ""])
    .map(function (l) { return String(l).toLowerCase().split("-")[0]; });
  var elegido = null;
  for (var i = 0; i < prefs.length && !elegido; i++) {
    if (prefs[i] === actual) return; // prefiere el idioma de esta página antes que los otros: nada que avisar
    for (var j = 0; j < avisos.length; j++) {
      if (avisos[j].getAttribute("data-idioma") === prefs[i]) { elegido = avisos[j]; break; }
    }
  }
  if (!elegido) return;
  elegido.hidden = false;
  var cerrar = elegido.querySelector("[data-cerrar-idioma]");
  if (cerrar) cerrar.addEventListener("click", function () {
    elegido.hidden = true;
    try { sessionStorage.setItem(CLAVE, "1"); } catch (e) { /* solo en esta página */ }
  });
})();
