/* Ampliar fotos · plantilla A de La Taza Roja (:::cards galeria y :::cards comparar).
   Cada foto pasa a ser un botón «Ampliar»; se abre en un <dialog> a pantalla completa con su pie, flechas para pasar a la
   anterior o la siguiente (también con el teclado y deslizando el dedo) y Esc o la X para cerrar. Sin JavaScript las fotos se ven
   igual, solo que no se amplían. No usa cookies ni almacenamiento ni carga nada de fuera. */
(function () {
  "use strict";
  var es = (document.documentElement.lang || "es").slice(0, 2) !== "en";
  var T = es ? { ampliar: "Ampliar foto", cerrar: "Cerrar", ant: "Foto anterior", sig: "Foto siguiente", de: "de", visor: "Foto ampliada" }
             : { ampliar: "Enlarge photo", cerrar: "Close", ant: "Previous photo", sig: "Next photo", de: "of", visor: "Enlarged photo" };
  var imgs = Array.prototype.slice.call(document.querySelectorAll(".cards-galeria .card img, .cards-comparar .card img"));
  if (!imgs.length || typeof HTMLDialogElement !== "function") return;

  var d = document.createElement("dialog");
  d.className = "visor";
  d.setAttribute("aria-label", T.visor);
  d.innerHTML = '<figure class="visor-foto"><img alt=""><figcaption></figcaption></figure>' +
    '<button type="button" class="visor-cerrar" aria-label="' + T.cerrar + '">×</button>' +
    '<button type="button" class="visor-ant" aria-label="' + T.ant + '">‹</button>' +
    '<button type="button" class="visor-sig" aria-label="' + T.sig + '">›</button>' +
    '<p class="visor-cuenta" aria-live="polite"></p>';
  document.body.appendChild(d);
  var vImg = d.querySelector("img"), vPie = d.querySelector("figcaption"), vCuenta = d.querySelector(".visor-cuenta");
  var grupo = [], i = 0;

  var pie = function (img) {
    var card = img.closest(".card"), t = [];
    var h = card && card.querySelector("h3");
    if (h) t.push(h.textContent.trim());
    Array.prototype.forEach.call(card ? card.querySelectorAll("p") : [], function (p) {
      if (!p.querySelector("img") && p.textContent.trim()) t.push(p.textContent.trim());
    });
    return t.join(" · ") || img.alt;
  };
  var mayor = function (img) {
    // La variante más ancha del srcset (en el móvil la foto de la tarjeta es la de 480 px y ampliada se vería borrosa).
    var mejor = null, ancho = 0;
    (img.getAttribute("srcset") || "").split(",").forEach(function (c) {
      var m = c.trim().match(/^(\S+)\s+(\d+)w$/);
      if (m && +m[2] > ancho) { ancho = +m[2]; mejor = m[1]; }
    });
    return mejor || img.currentSrc || img.src;
  };
  var mostrar = function (n) {
    i = (n + grupo.length) % grupo.length;
    var img = grupo[i];
    vImg.src = mayor(img);
    vImg.alt = img.alt;
    vPie.textContent = pie(img);
    vCuenta.textContent = (i + 1) + " " + T.de + " " + grupo.length;
    d.classList.toggle("visor-una", grupo.length < 2);
  };
  var abrir = function (img) {
    // Solo las fotos de la misma página (en la vista previa conviven varias páginas en un archivo).
    var raiz = img.closest(".vista") || document;
    grupo = imgs.filter(function (x) { return (x.closest(".vista") || document) === raiz; });
    mostrar(grupo.indexOf(img));
    d.showModal();
  };

  imgs.forEach(function (img) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "foto-ampliar";
    b.setAttribute("aria-label", T.ampliar + ": " + img.alt);
    img.parentNode.insertBefore(b, img);
    b.appendChild(img);
    b.addEventListener("click", function () { abrir(img); });
  });

  d.querySelector(".visor-cerrar").addEventListener("click", function () { d.close(); });
  d.querySelector(".visor-ant").addEventListener("click", function () { mostrar(i - 1); });
  d.querySelector(".visor-sig").addEventListener("click", function () { mostrar(i + 1); });
  d.addEventListener("click", function (e) { if (e.target === d) d.close(); });  // clic fuera de la foto
  d.addEventListener("keydown", function (e) {
    if (e.key === "ArrowLeft") { e.preventDefault(); mostrar(i - 1); }
    if (e.key === "ArrowRight") { e.preventDefault(); mostrar(i + 1); }
  });
  var x0 = null;
  d.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; }, { passive: true });
  d.addEventListener("touchend", function (e) {
    if (x0 === null) return;
    var dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 50) mostrar(i + (dx < 0 ? 1 : -1));
    x0 = null;
  });
})();
