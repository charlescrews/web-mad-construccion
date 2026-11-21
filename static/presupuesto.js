/* Formulario de presupuesto · plantilla A de La Taza Roja (bloque :::presupuesto).
   No envía ni guarda nada: con lo que escribe la persona prepara el texto de los enlaces de WhatsApp (wa.me/…?text=) y de email
   (mailto:…?subject=&body=), siempre con encodeURIComponent, y es ella quien lo manda desde su móvil u ordenador.
   Sin este script los enlaces siguen funcionando (abren el chat o el correo vacíos). No usa cookies ni almacenamiento. */
(function () {
  "use strict";
  var TEXTOS = {
    es: { hola: "Hola, quiero pedir presupuesto.", trabajo: "Trabajo", localidad: "Pueblo o zona", medidas: "Medidas aproximadas",
          cuando: "Para cuándo", nombre: "Nombre", nota: "Más detalles", fotos: "(Si puedo, te mando fotos por aquí.)",
          asunto: "Presupuesto" },
    en: { hola: "Hello, I would like a quote.", trabajo: "Job", localidad: "Town or area", medidas: "Approximate size",
          cuando: "When", nombre: "Name", nota: "More details", fotos: "(I can send photos here.)", asunto: "Quote request" }
  };
  document.querySelectorAll("form.pres-form").forEach(function (f) {
    var T = TEXTOS[f.getAttribute("data-lang")] || TEXTOS.es;
    var wa = f.querySelector("a.pres-wa"), em = f.querySelector("a.pres-email");
    var num = f.getAttribute("data-wa"), email = f.getAttribute("data-email");
    var val = function (n) { var e = f.elements[n]; return e ? String(e.value).trim() : ""; };
    var lineas = function () {
      var l = [T.hola];
      ["trabajo", "localidad", "medidas", "cuando", "nombre", "nota"].forEach(function (n) {
        var v = val(n);
        if (v) l.push(T[n] + ": " + v);
      });
      return l;
    };
    var actualizar = function () {
      var l = lineas();
      if (wa && num) wa.href = "https://wa.me/" + num + "?text=" + encodeURIComponent(l.concat([T.fotos]).join("\n"));
      if (em && email) {
        var asunto = T.asunto + (val("trabajo") ? ": " + val("trabajo") : "") + (val("localidad") ? " (" + val("localidad") + ")" : "");
        em.href = "mailto:" + email + "?subject=" + encodeURIComponent(asunto) + "&body=" + encodeURIComponent(l.join("\n"));
      }
    };
    f.addEventListener("input", actualizar);
    f.addEventListener("change", actualizar);
    // Intro en un campo de una línea: como pulsar el primer botón (WhatsApp o, si no hay, email). Sin botón de envío el navegador
    // no envía el formulario solo, así que se hace aquí; en el cuadro de texto largo, Intro sigue siendo salto de línea.
    var enviar = function (e) {
      e.preventDefault();
      actualizar();
      var a = wa || em;
      if (a) a.click();
    };
    f.addEventListener("submit", enviar);
    f.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && e.target.tagName === "INPUT") enviar(e);
    });
    actualizar();
  });
})();
