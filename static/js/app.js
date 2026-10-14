// Aula Virtual CETPRO Mangomarca — JavaScript sin frameworks.
// Todo funciona también sin JavaScript; esto solo ayuda.
(function () {
  'use strict';

  // Fotos grandes del celular (JPG de 3 a 8 MB): se achican a 1600 px antes de subirlas.
  // Suben mucho más rápido con datos móviles. Si el navegador no puede, se sube la original.
  document.addEventListener('change', function (ev) {
    var input = ev.target;
    if (!input || input.type !== 'file' || input.dataset.sinComprimir !== undefined) { return; }
    if (input.dataset.comprimida === '1') { delete input.dataset.comprimida; return; }
    var f = input.files && input.files[0];
    if (!f || !/^image\/(jpeg|webp)$/.test(f.type) || f.size < 900 * 1024 || !window.DataTransfer || !window.createImageBitmap) { return; }
    ev.stopImmediatePropagation();
    var avisar = function () { input.dataset.comprimida = '1'; input.dispatchEvent(new Event('change', { bubbles: true })); };
    createImageBitmap(f).then(function (img) {
      var escala = Math.min(1, 1600 / Math.max(img.width, img.height));
      var lienzo = document.createElement('canvas');
      lienzo.width = Math.round(img.width * escala);
      lienzo.height = Math.round(img.height * escala);
      lienzo.getContext('2d').drawImage(img, 0, 0, lienzo.width, lienzo.height);
      lienzo.toBlob(function (blob) {
        if (blob && blob.size < f.size) {
          var dt = new DataTransfer();
          dt.items.add(new File([blob], f.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' }));
          input.files = dt.files;
        }
        avisar();
      }, 'image/jpeg', 0.82);
    }).catch(avisar);
  }, true);

  // Casillas que muestran u ocultan una parte del formulario (ej. «Ponerles fechas»).
  document.querySelectorAll('input[type="checkbox"][data-mostrar]').forEach(function (casilla) {
    var parte = document.getElementById(casilla.dataset.mostrar);
    var actualizar = function () { if (parte) { parte.hidden = !casilla.checked; } };
    casilla.addEventListener('change', actualizar);
    actualizar();
  });

  // Zona para soltar una foto o archivo arrastrado (en PC). Lo pone en el campo indicado.
  document.querySelectorAll('[data-soltar]').forEach(function (zona) {
    var destino = document.getElementById(zona.dataset.soltar);
    if (!destino) { return; }
    ['dragenter', 'dragover'].forEach(function (t) {
      zona.addEventListener(t, function (ev) { ev.preventDefault(); zona.classList.add('encima'); });
    });
    ['dragleave', 'drop'].forEach(function (t) {
      zona.addEventListener(t, function () { zona.classList.remove('encima'); });
    });
    zona.addEventListener('drop', function (ev) {
      ev.preventDefault();
      if (ev.dataTransfer && ev.dataTransfer.files.length) {
        destino.files = ev.dataTransfer.files;
        destino.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  });

  // El botón de enviar se activa recién cuando hay una foto o un archivo elegido.
  document.querySelectorAll('form[data-requiere-archivo]').forEach(function (form) {
    var boton = form.querySelector('button[type="submit"]');
    var aviso = form.querySelector('[data-aviso-archivo]');
    var revisar = function () {
      var hay = Array.prototype.some.call(form.querySelectorAll('input[type="file"]'), function (i) { return i.files && i.files.length; });
      boton.disabled = !hay;
      if (aviso) { aviso.hidden = hay; }
    };
    form.addEventListener('change', function () { setTimeout(revisar, 0); });
    revisar();
  });

  // Buscador y filtro de una lista (módulos, mensajes): oculta las filas que no coinciden.
  // El buscador es input[data-filtro="id-de-la-lista"]; el filtro de estado, select[data-filtro-estado="id"].
  var sinTildes = function (t) { return t.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); };
  var filtrarLista = function (id) {
    var lista = document.getElementById(id);
    if (!lista) { return; }
    var campo = document.querySelector('input[data-filtro="' + id + '"]');
    var estado = document.querySelector('select[data-filtro-estado="' + id + '"]');
    var q = campo ? sinTildes(campo.value.trim()) : '';
    var est = estado ? estado.value : '';
    var visibles = 0;
    lista.querySelectorAll('[data-buscar]').forEach(function (fila) {
      var ver = (q === '' || sinTildes(fila.dataset.buscar).indexOf(q) !== -1) && (est === '' || fila.dataset.estado === est);
      fila.hidden = !ver;
      if (ver) { visibles++; }
    });
    var nada = lista.querySelector('[data-sin-resultados]');
    if (nada) { nada.hidden = visibles > 0; }
  };
  document.querySelectorAll('input[data-filtro]').forEach(function (campo) {
    campo.addEventListener('input', function () { filtrarLista(campo.dataset.filtro); });
  });
  document.querySelectorAll('select[data-filtro-estado]').forEach(function (sel) {
    sel.addEventListener('change', function () { filtrarLista(sel.dataset.filtroEstado); });
  });

  // Listas de filas que crecen (clases de un módulo, criterios de una tarea): «+ Añadir», «Quitar» y numeración.
  document.querySelectorAll('[data-filas]').forEach(function (cont) {
    var lista = cont.querySelector('[data-lista]');
    var molde = cont.querySelector('template[data-molde]');
    var agregar = cont.querySelector('[data-agregar]');
    var max = parseInt(cont.dataset.max || '40', 10);
    var total = cont.querySelector('[data-total]');
    if (!lista || !molde) { return; }
    var sumar = function () {
      if (!total) { return; }
      var suma = 0;
      cont.querySelectorAll('[data-puntos]').forEach(function (c) { suma += parseInt(c.value || '0', 10) || 0; });
      total.textContent = suma;
      var caja = total.parentElement;
      var resto = cont.querySelector('[data-resto]');
      caja.classList.toggle('ok', suma === 20);
      caja.classList.toggle('aviso', suma > 0 && suma < 20);
      caja.classList.toggle('mal', suma > 20);
      if (resto) { resto.textContent = suma > 0 && suma < 20 ? ' · faltan ' + (20 - suma) : (suma > 20 ? ' · te pasaste por ' + (suma - 20) : (suma === 20 ? ' · ¡completo!' : '')); }
    };
    var renumerar = function () {
      var filas = lista.querySelectorAll('[data-fila]');
      filas.forEach(function (fila, i) {
        fila.querySelectorAll('[data-num]').forEach(function (el) { el.textContent = i + 1; });
        fila.querySelectorAll('[data-etiqueta]').forEach(function (el) { el.setAttribute('aria-label', el.dataset.etiqueta.replace('#', i + 1)); });
        fila.querySelectorAll('[data-quitar]').forEach(function (b) { b.hidden = filas.length <= 1; });
      });
      if (agregar) { agregar.hidden = filas.length >= max; }
      sumar();
    };
    if (agregar) {
      agregar.addEventListener('click', function () {
        lista.appendChild(molde.content.firstElementChild.cloneNode(true));
        renumerar();
        var campos = lista.querySelectorAll('[data-fila]:last-child input');
        if (campos.length) { campos[0].focus(); }
      });
    }
    lista.addEventListener('click', function (ev) {
      var quitar = ev.target.closest('[data-quitar]');
      if (!quitar) { return; }
      var fila = quitar.closest('[data-fila]');
      if (fila && lista.querySelectorAll('[data-fila]').length > 1) { fila.remove(); renumerar(); }
    });
    cont.addEventListener('input', sumar);
    renumerar();
  });

  // Elegir un filtro en una lista envía el formulario solo.
  document.querySelectorAll('select[data-autoenviar]').forEach(function (sel) {
    sel.addEventListener('change', function () { if (sel.form) { sel.form.submit(); } });
  });

  // Al calificar con criterios: los puntos de cada criterio suman la nota (se puede cambiar a mano).
  document.querySelectorAll('[data-rubrica]').forEach(function (rub) {
    var nota = document.getElementById(rub.dataset.rubrica);
    if (!nota) { return; }
    rub.addEventListener('input', function () {
      var suma = 0;
      var alguno = false;
      rub.querySelectorAll('[data-pts]').forEach(function (c) {
        if (c.value !== '') { alguno = true; }
        suma += Math.min(parseFloat(c.value || '0') || 0, parseFloat(c.max || '20'));
      });
      if (alguno) { nota.value = Math.min(suma, 20); }
      var visor = rub.querySelector('[data-suma]');
      if (visor) { visor.textContent = Math.min(suma, 20); }
    });
  });

  // Copiar al portapapeles (credenciales, contraseña generada). Si el navegador no deja, se selecciona el texto.
  var copiarTexto = function (texto, aviso) {
    var hecho = function () {
      if (!aviso) { return; }
      var original = aviso.textContent;
      aviso.textContent = '¡Copiado!';
      setTimeout(function () { aviso.textContent = original; }, 2000);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(texto).then(hecho, function () { window.prompt('Copia el texto con Ctrl+C:', texto); });
    } else {
      window.prompt('Copia el texto con Ctrl+C:', texto);
    }
  };
  document.querySelectorAll('[data-copiar]').forEach(function (btn) {
    btn.addEventListener('click', function () { copiarTexto(btn.dataset.copiar, btn.querySelector('span')); });
  });
  document.querySelectorAll('[data-copiar-campo]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var campo = document.getElementById(btn.dataset.copiarCampo);
      if (campo && campo.value !== '') { copiarTexto(campo.value, btn.querySelector('span')); }
    });
  });
  // Contraseña segura al azar (10 letras y números sin confusiones), creada en este navegador.
  document.querySelectorAll('[data-generar-clave]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var campo = document.getElementById(btn.dataset.generarClave);
      if (!campo) { return; }
      var letras = 'abcdefghjkmnpqrstuvwxyz23456789';
      var clave = '';
      var azar = new Uint8Array(40);
      window.crypto.getRandomValues(azar);
      for (var i = 0; i < azar.length && clave.length < 10; i++) {
        if (azar[i] < 248) { clave += letras.charAt(azar[i] % letras.length); } // 248 = 8 x 31: sin sesgo
      }
      campo.value = clave;
      campo.type = 'text';
      campo.dispatchEvent(new Event('input', { bubbles: true }));
    });
  });

  // «Marcar a todos» en una tabla: marca o desmarca las casillas ids[] del formulario indicado.
  document.querySelectorAll('input[data-marcar-todos]').forEach(function (todos) {
    todos.addEventListener('change', function () {
      document.querySelectorAll('input[name="ids[]"][form="' + todos.dataset.marcarTodos + '"]').forEach(function (c) { c.checked = todos.checked; });
    });
  });

  // En la conversación, se muestra lo último.
  var ultimo = document.querySelector('.mensajeria-chat #ultimo');
  if (ultimo && ultimo.parentElement) { ultimo.parentElement.scrollTop = ultimo.parentElement.scrollHeight; }

  // Imprimir (o guardar como PDF).
  document.querySelectorAll('[data-imprimir]').forEach(function (btn) {
    btn.addEventListener('click', function () { window.print(); });
  });

  // El "Paso 2" (revisar y enviar) aparece recién cuando se eligió la foto o el archivo.
  document.querySelectorAll('input[type="file"][data-paso2]').forEach(function (input) {
    var paso2 = document.getElementById(input.dataset.paso2);
    if (paso2 && !(input.files && input.files.length)) { paso2.hidden = true; }
  });

  // Vista previa de la foto o nombre del archivo elegido antes de enviar.
  document.querySelectorAll('input[type="file"][data-previa]').forEach(function (input) {
    input.addEventListener('change', function () {
      var destino = document.getElementById(input.dataset.previa);
      var nombre = document.getElementById(input.dataset.nombre);
      var archivo = input.files && input.files[0];
      // Si se usan dos campos (cámara y archivo), solo se envía el último elegido.
      if (archivo && input.dataset.otro) {
        var otro = document.getElementById(input.dataset.otro);
        if (otro) { otro.value = ''; }
      }
      if (nombre) { nombre.textContent = archivo ? 'Elegiste: ' + archivo.name : ''; }
      if (destino) {
        if (archivo && /^image\/(jpeg|png|webp)$/.test(archivo.type)) {
          destino.src = URL.createObjectURL(archivo);
          destino.classList.add('visible');
        } else {
          destino.removeAttribute('src');
          destino.classList.remove('visible');
        }
      }
      var paso2 = document.getElementById(input.dataset.paso2 || '');
      if (paso2 && archivo) { paso2.hidden = false; paso2.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    });
  });

  // Pide confirmar antes de borrar. (Una opción con data-sin-confirmar ya muestra su propia pantalla de confirmación.)
  document.querySelectorAll('form[data-confirmar]').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      var elegida = form.querySelector('option:checked');
      if (elegida && elegida.hasAttribute('data-sin-confirmar')) { return; }
      if (!window.confirm(form.dataset.confirmar)) { ev.preventDefault(); }
    });
  });

  // «Agregar otra…»: muestra la siguiente fila escondida de una lista de campos (por ejemplo, las unidades didácticas).
  document.querySelectorAll('[data-mas-filas]').forEach(function (boton) {
    boton.addEventListener('click', function () {
      var lista = document.getElementById(boton.dataset.masFilas);
      var oculta = lista ? lista.querySelector('[data-fila][hidden]') : null;
      if (oculta) {
        oculta.hidden = false;
        var campo = oculta.querySelector('input');
        if (campo) { campo.focus(); }
      }
      if (!lista || !lista.querySelector('[data-fila][hidden]')) { boton.hidden = true; }
    });
  });

  // Unidades didácticas: «Quitar» saca la unidad (las de abajo suben un lugar) y deja libre un lugar para «Agregar otra unidad».
  // Siempre quedan visibles al menos 3 filas. Lo quitado se borra de verdad al guardar el módulo.
  var listaUnidades = document.getElementById('lista-unidades');
  if (listaUnidades) {
    listaUnidades.addEventListener('click', function (ev) {
      var quitar = ev.target.closest('[data-quitar-unidad]');
      if (!quitar) { return; }
      var visibles = Array.prototype.filter.call(listaUnidades.querySelectorAll('[data-fila]'), function (f) { return !f.hidden; });
      var indice = visibles.indexOf(quitar.closest('[data-fila]'));
      for (var k = indice; k < visibles.length - 1; k++) {
        var desde = visibles[k + 1].querySelectorAll('input');
        visibles[k].querySelectorAll('input').forEach(function (campo, j) { campo.value = desde[j].value; });
      }
      var ultima = visibles[visibles.length - 1];
      ultima.querySelectorAll('input').forEach(function (campo) { campo.value = ''; });
      var quedan = visibles.length;
      if (quedan > 3) { ultima.hidden = true; quedan -= 1; }
      var masUnidades = document.querySelector('[data-mas-filas="lista-unidades"]');
      if (masUnidades) { masUnidades.hidden = false; }
      var aviso = document.querySelector('[data-aviso-unidades]');
      if (aviso) { aviso.textContent = 'Unidad quitada. Quedan ' + quedan + ' filas.'; }
      var campoNombre = visibles[Math.min(indice, quedan - 1)].querySelector('input');
      if (campoNombre) { campoNombre.focus(); }
    });
  }

  // Menús «Más» y «Opciones»: se cierran al tocar fuera o con Escape.
  document.addEventListener('click', function (ev) {
    document.querySelectorAll('details.menu-opciones[open]').forEach(function (menu) {
      if (!menu.contains(ev.target)) { menu.open = false; }
    });
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') { return; }
    document.querySelectorAll('details.menu-opciones[open]').forEach(function (menu) {
      menu.open = false;
      var boton = menu.querySelector('summary');
      if (boton) { boton.focus(); }
    });
  });

  // Evita enviar dos veces (por ejemplo, al tocar dos veces "Enviar tarea").
  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      var boton = form.querySelector('button[type="submit"]:not([name])');
      if (boton) {
        // Se revisa después de los demás avisos (confirmar, preguntas sin responder) por si cancelaron el envío.
        setTimeout(function () {
          if (ev.defaultPrevented) { return; }
          boton.disabled = true;
          boton.textContent = 'Enviando…';
        }, 0);
      }
    });
  });

  // Mostrar u ocultar contraseña.
  document.querySelectorAll('[data-ver-clave]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var campo = document.getElementById(btn.dataset.verClave);
      var ver = campo.type === 'password';
      campo.type = ver ? 'text' : 'password';
      (btn.querySelector('span') || btn).textContent = ver ? 'Ocultar' : 'Ver';
      btn.setAttribute('aria-pressed', ver ? 'true' : 'false');
    });
  });

  // «Mostrar lo que escribo»: muestra u oculta varias contraseñas a la vez (pantalla de contraseña nueva).
  document.querySelectorAll('input[data-ver-claves]').forEach(function (casilla) {
    casilla.addEventListener('change', function () {
      casilla.dataset.verClaves.split(' ').forEach(function (id) {
        var campo = document.getElementById(id);
        if (campo) { campo.type = casilla.checked ? 'text' : 'password'; }
      });
    });
  });

  // Contraseña nueva: avisa si las dos veces que la escribió son iguales.
  document.querySelectorAll('form[data-clave-nueva]').forEach(function (form) {
    var nueva = form.querySelector('#nueva');
    var repetir = form.querySelector('#repetir');
    var aviso = form.querySelector('[data-coinciden]');
    if (!nueva || !repetir || !aviso) { return; }
    var revisar = function () {
      if (repetir.value === '') { aviso.textContent = ''; return; }
      aviso.textContent = nueva.value === repetir.value ? '✓ Las dos son iguales.' : 'Todavía no son iguales.';
    };
    nueva.addEventListener('input', revisar);
    repetir.addEventListener('input', revisar);
  });

  // Campo de puntos de penalidad: solo se muestra si se eligió "restando puntos".
  document.querySelectorAll('input[name="politica_tardia"]').forEach(function (r) {
    r.addEventListener('change', function () {
      var caja = document.getElementById('caja-penalidad');
      if (caja) { caja.hidden = r.value !== 'penalidad'; }
    });
  });

  // Tipo de material: archivo o enlace.
  document.querySelectorAll('input[name="tipo"][data-material]').forEach(function (r) {
    r.addEventListener('change', function () {
      var form = r.closest('form');
      form.querySelector('[data-campo="archivo"]').hidden = r.value !== 'archivo';
      form.querySelector('[data-campo="enlace"]').hidden = r.value !== 'enlace';
    });
  });

  // ===== Armar preguntas del formulario (como Google Forms) =====
  document.querySelectorAll('[data-form-pregunta]').forEach(function (form) {
    var unaCorrecta = ['opcion', 'desplegable'];
    function tipoActual() {
      var s = form.querySelector('[data-tipo-pregunta]');
      return s ? s.value : 'opcion';
    }
    function actualizar() {
      var tipo = tipoActual();
      form.querySelectorAll('[data-para]').forEach(function (bloque) {
        bloque.hidden = bloque.dataset.para.split(' ').indexOf(tipo) === -1;
      });
      form.querySelectorAll('[data-no-para]').forEach(function (bloque) {
        bloque.hidden = bloque.dataset.noPara.split(' ').indexOf(tipo) !== -1;
      });
      var etq = form.querySelector('[data-etiqueta-enunciado]');
      if (etq) { etq.textContent = tipo === 'seccion' ? 'Título' : 'Pregunta'; }
      var etqAyuda = form.querySelector('[data-etiqueta-ayuda]');
      if (etqAyuda) { etqAyuda.textContent = tipo === 'seccion' ? 'Descripción (opcional)' : 'Descripción o ayuda (opcional)'; }
      var ayuda = form.querySelector('[data-ayuda-opcion]');
      if (ayuda) {
        ayuda.innerHTML = tipo === 'multiple'
          ? 'Escribe las opciones y marca <b>todas las correctas</b>.'
          : 'Escribe las opciones y marca <b>la correcta</b>.';
      }
      if (unaCorrecta.indexOf(tipo) !== -1) { // solo una correcta: deja marcada la primera
        var marcadas = form.querySelectorAll('input[name="correctas[]"]:checked');
        for (var i = 1; i < marcadas.length; i++) { marcadas[i].checked = false; }
      }
    }
    form.querySelectorAll('[data-tipo-pregunta]').forEach(function (s) { s.addEventListener('change', actualizar); });
    form.addEventListener('change', function (ev) {
      if (ev.target.name === 'correctas[]' && ev.target.checked && unaCorrecta.indexOf(tipoActual()) !== -1) {
        form.querySelectorAll('input[name="correctas[]"]').forEach(function (c) { if (c !== ev.target) { c.checked = false; } });
      }
    });
    var agregar = form.querySelector('[data-agregar-opcion]');
    var lista = form.querySelector('[data-lista-opciones]');
    // Vuelve a numerar las opciones (el número une cada opción con su casilla "Correcta").
    function renumerar() {
      lista.querySelectorAll('.fila-opcion').forEach(function (fila, i) {
        var check = fila.querySelector('input[type="checkbox"]');
        var texto = fila.querySelector('input.form-control');
        var etiqueta = fila.querySelector('label.visually-hidden');
        var quitar = fila.querySelector('[data-quitar-opcion]');
        if (check) { check.value = String(i); }
        texto.name = 'opcion[' + i + ']';
        texto.id = texto.id.replace(/-\d+$/, '-' + i);
        texto.placeholder = 'Opción ' + (i + 1);
        if (etiqueta) { etiqueta.htmlFor = texto.id; etiqueta.textContent = 'Opción ' + (i + 1); }
        if (quitar) { quitar.setAttribute('aria-label', 'Quitar opción ' + (i + 1)); }
      });
    }
    if (agregar && lista) {
      agregar.addEventListener('click', function () {
        var filas = lista.querySelectorAll('.fila-opcion');
        if (filas.length >= 15) { return; }
        var nueva = filas[filas.length - 1].cloneNode(true);
        var check = nueva.querySelector('input[type="checkbox"]');
        if (check) { check.checked = false; }
        nueva.querySelector('input.form-control').value = '';
        lista.appendChild(nueva);
        renumerar();
        nueva.querySelector('input.form-control').focus();
      });
      // Quitar una opción (siempre quedan al menos 2 filas; si solo hay 2, se vacía).
      lista.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-quitar-opcion]');
        if (!btn) { return; }
        var fila = btn.closest('.fila-opcion');
        var filas = lista.querySelectorAll('.fila-opcion');
        if (filas.length > 2) {
          var siguiente = fila.nextElementSibling || fila.previousElementSibling;
          fila.remove();
          renumerar();
          var foco = siguiente && siguiente.querySelector('input.form-control');
          if (foco) { foco.focus(); }
        } else {
          fila.querySelector('input.form-control').value = '';
          var c = fila.querySelector('input[type="checkbox"]');
          if (c) { c.checked = false; }
        }
      });
    }
    actualizar();
  });

  // ===== Responder un formulario =====
  var formExamen = document.querySelector('form[data-examen]');
  if (formExamen) {
    var preguntas = formExamen.querySelectorAll('[data-pregunta]');
    var resumen = formExamen.querySelector('[data-resumen]');
    var vistaPrevia = formExamen.hasAttribute('data-vista-previa');
    var enviando = false;
    function respondida(p) {
      var tipo = p.dataset.tipo;
      if (tipo === 'cuadricula' || tipo === 'cuadricula_casillas') {
        var filas = p.querySelectorAll('[data-fila]');
        for (var i = 0; i < filas.length; i++) { if (!filas[i].querySelector('input:checked')) { return false; } }
        return filas.length > 0;
      }
      if (tipo === 'archivo') {
        var f = p.querySelector('input[type="file"]');
        return !!(f && f.files && f.files.length);
      }
      var sel = p.querySelector('select');
      if (sel) { return sel.value !== ''; }
      var marcado = p.querySelector('input[type="radio"]:checked, input[type="checkbox"]:checked');
      if (marcado) { return marcado.value !== 'otra' || (p.querySelector('input[name^="otra["]') || {}).value; }
      var texto = p.querySelector('input.form-control:not([name^="otra["]), textarea, input[type="date"], input[type="time"]');
      return !!(texto && texto.value.trim() !== '');
    }
    function contar() {
      var faltan = 0;
      var obligatoriasFaltan = 0;
      preguntas.forEach(function (p) {
        if (!respondida(p)) {
          faltan++;
          if (p.hasAttribute('data-obligatoria')) { obligatoriasFaltan++; }
        } else {
          p.classList.remove('sin-responder');
        }
      });
      if (resumen) {
        resumen.textContent = faltan === 0
          ? '¡Respondiste todas las preguntas!'
          : 'Te faltan ' + faltan + (faltan === 1 ? ' pregunta' : ' preguntas') + (obligatoriasFaltan ? ' (' + obligatoriasFaltan + ' obligatoria' + (obligatoriasFaltan === 1 ? '' : 's') + ')' : '') + '.';
      }
      return obligatoriasFaltan;
    }
    // Al escribir en "Otra", se marca sola esa opción.
    formExamen.querySelectorAll('input[name^="otra["]').forEach(function (campo) {
      campo.addEventListener('input', function () {
        var opcion = formExamen.querySelector('[data-otra="' + campo.id + '"]');
        if (opcion && campo.value.trim() !== '') { opcion.checked = true; }
      });
    });
    formExamen.addEventListener('change', contar);
    formExamen.addEventListener('input', contar);
    formExamen.addEventListener('submit', function (ev) {
      if (vistaPrevia) { ev.preventDefault(); return; }
      if (enviando) { return; }
      var faltan = contar();
      if (faltan > 0 && !formExamen.dataset.tiempoAgotado) {
        ev.preventDefault();
        preguntas.forEach(function (p) { if (p.hasAttribute('data-obligatoria') && !respondida(p)) { p.classList.add('sin-responder'); } });
        var primera = formExamen.querySelector('.sin-responder');
        if (primera) { primera.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
        window.alert('Te falta responder ' + (faltan === 1 ? '1 pregunta obligatoria' : faltan + ' preguntas obligatorias') + ' (marcadas con *).');
        return;
      }
      if (formExamen.dataset.tiempoAgotado) {
        // Se acabó el tiempo: se envía igual aunque falten preguntas.
        formExamen.querySelectorAll('[required]').forEach(function (c) { c.required = false; });
      }
      enviando = true;
    });
    if (!vistaPrevia) {
      // Avisar si intenta salir de la página sin enviar.
      window.addEventListener('beforeunload', function (ev) {
        if (!enviando) { ev.preventDefault(); ev.returnValue = ''; }
      });
    }
    contar();
  }

  var reloj = document.querySelector('.reloj-examen[data-segundos]');
  if (reloj) {
    var fin = Date.now() + parseInt(reloj.dataset.segundos, 10) * 1000;
    var salida = reloj.querySelector('[data-reloj]');
    var formReloj = document.getElementById(reloj.dataset.form);
    var tic = setInterval(function () {
      var resta = Math.max(0, Math.round((fin - Date.now()) / 1000));
      var m = Math.floor(resta / 60);
      var s = resta % 60;
      salida.textContent = m + ':' + (s < 10 ? '0' : '') + s;
      reloj.classList.toggle('poco', resta <= 60);
      if (resta === 60) { reloj.setAttribute('aria-live', 'assertive'); salida.textContent += ' (¡queda 1 minuto!)'; }
      if (resta <= 0) {
        clearInterval(tic);
        if (formReloj) {
          formReloj.dataset.tiempoAgotado = '1';
          formReloj.querySelectorAll('[required]').forEach(function (c) { c.required = false; });
          formReloj.requestSubmit();
        }
      }
    }, 1000);
  }

  // ===== Mensajes: se actualiza solo cada 30 s si no estás escribiendo =====
  var formChat = document.querySelector('form[data-recargar]');
  if (formChat) {
    var cajaTexto = formChat.querySelector('textarea');
    setInterval(function () {
      if (cajaTexto && cajaTexto.value.trim() === '' && document.visibilityState === 'visible') {
        window.location.replace(window.location.pathname + '?t=' + Date.now() + '#ultimo');
      }
    }, 30000);
  }

  // El botón flotante "+ Agregar pregunta" se oculta mientras el formulario de agregar está a la vista.
  var flotante = document.querySelector('.btn-flotante');
  var zonaNueva = document.getElementById('nueva');
  if (flotante && zonaNueva) {
    var revisarFlotante = function () {
      var r = zonaNueva.getBoundingClientRect();
      flotante.hidden = r.top < window.innerHeight * 0.7 && r.bottom > 0;
    };
    window.addEventListener('scroll', revisarFlotante, { passive: true });
    window.addEventListener('resize', revisarFlotante);
    window.addEventListener('hashchange', revisarFlotante);
    revisarFlotante();
  }

  // Copiar un texto (por ejemplo, la instrucción para la IA).
  document.querySelectorAll('[data-copiar]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var campo = document.getElementById(btn.dataset.copiar);
      var listo = function () {
        var antes = btn.innerHTML;
        btn.textContent = '¡Copiado! Ahora pégalo en la IA';
        setTimeout(function () { btn.innerHTML = antes; }, 3000);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(campo.value).then(listo);
      } else {
        campo.select();
        document.execCommand('copy');
        listo();
      }
    });
  });

  // Ajustes del admin: vista previa de los colores mientras se eligen.
  document.querySelectorAll('input[data-color-tema]').forEach(function (input) {
    input.addEventListener('input', function () {
      document.querySelectorAll('[data-vt="' + input.dataset.colorTema + '"]').forEach(function (el) {
        el.style.background = input.value;
      });
    });
  });

  // Leer en voz alta (Web Speech API del navegador).
  var voz = window.speechSynthesis;
  document.querySelectorAll('[data-leer]').forEach(function (btn) {
    if (!voz) { btn.hidden = true; return; }
    btn.addEventListener('click', function () {
      if (voz.speaking) { voz.cancel(); btn.setAttribute('aria-pressed', 'false'); return; }
      var origen = document.getElementById(btn.dataset.leer);
      var texto = origen ? origen.innerText : '';
      if (!texto) { return; }
      var u = new SpeechSynthesisUtterance(texto);
      u.lang = 'es-PE';
      u.rate = 0.95;
      var voces = voz.getVoices().filter(function (v) { return v.lang && v.lang.indexOf('es') === 0; });
      if (voces.length) { u.voice = voces.find(function (v) { return v.lang === 'es-PE'; }) || voces[0]; }
      u.onend = function () { btn.setAttribute('aria-pressed', 'false'); };
      btn.setAttribute('aria-pressed', 'true');
      voz.speak(u);
    });
  });

  // Formulario de personas: lo obligatorio cambia según el tipo de cuenta (alumno: su DNI; las demás: su correo).
  document.querySelectorAll('form').forEach(function (form) {
    var campos = form.querySelectorAll('[data-requerido-para], [data-destacar-para]');
    var radios = form.querySelectorAll('input[type="radio"][name="rol"]');
    if (!campos.length || !radios.length) { return; }
    var aplicar = function () {
      var marcado = form.querySelector('input[type="radio"][name="rol"]:checked');
      var rol = marcado ? marcado.value : '';
      campos.forEach(function (campo) {
        var lista = (campo.dataset.requeridoPara || campo.dataset.destacarPara).split(' ');
        var requerido = lista.indexOf(rol) !== -1;
        if (campo.dataset.requeridoPara !== undefined) { campo.required = requerido; } // «requerido»: pide llenarlo; «destacar»: solo cambia el texto
        campo.parentElement.querySelectorAll('[data-si-requerido]').forEach(function (el) { el.hidden = !requerido; });
        campo.parentElement.querySelectorAll('[data-si-opcional]').forEach(function (el) { el.hidden = requerido; });
      });
      form.querySelectorAll('[data-solo-para]').forEach(function (el) { el.hidden = el.dataset.soloPara.split(' ').indexOf(rol) === -1; });
    };
    radios.forEach(function (r) { r.addEventListener('change', aplicar); });
    aplicar();
  });

  // Formulario de curso: las muestras ponen el color, la vista previa sigue al nombre y al color, y se avisa si el color es muy claro
  // (encima va letra blanca). Sin JavaScript queda el selector de color del navegador y el servidor revisa lo mismo.
  var campoColor = document.querySelector('[data-campo-color]');
  if (campoColor) {
    var campoNombre = document.querySelector('[data-campo-nombre]');
    var vistaCurso = document.querySelector('[data-vista-curso]');
    var avisoColor = document.querySelector('[data-aviso-color]');
    var muestras = document.querySelectorAll('[data-poner-color]');
    var luminancia = function (hex) {
      var c = [1, 3, 5].map(function (i) {
        var v = parseInt(hex.substr(i, 2), 16) / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    };
    var actualizarCurso = function () {
      var valor = campoColor.value;
      vistaCurso.style.setProperty('--color', valor);
      vistaCurso.querySelector('[data-vista-nombre]').textContent = campoNombre.value.trim() || 'Nombre del curso';
      avisoColor.hidden = 1.05 / (luminancia(valor) + 0.05) >= 4.5; // contraste con el blanco
      muestras.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.ponerColor.toLowerCase() === valor.toLowerCase() ? 'true' : 'false'); });
    };
    muestras.forEach(function (b) {
      b.addEventListener('click', function () { campoColor.value = b.dataset.ponerColor; actualizarCurso(); });
    });
    campoColor.addEventListener('input', actualizarCurso);
    campoNombre.addEventListener('input', actualizarCurso);
    actualizarCurso();
  }

  // ---------- Animaciones ----------
  // Todo se apaga con «Reducir animaciones» (Mi cuenta) o si el aparato pide menos movimiento.
  var sinMovimiento = function () {
    return document.body.classList.contains('sin-animacion') ||
      (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  };

  // Confeti suave para festejar un logro (entregar una tarea, terminar un examen…).
  var celebrar = function () {
    if (sinMovimiento() || document.querySelector('.confeti')) { return; }
    var colores = ['#1249A3', '#C8231B', '#F5B301', '#166534', '#7C3AED', '#0EA5E9'];
    var caja = document.createElement('div');
    caja.className = 'confeti';
    caja.setAttribute('aria-hidden', 'true');
    for (var i = 0; i < 36; i++) {
      var pieza = document.createElement('i');
      pieza.style.setProperty('--x', Math.round(Math.random() * 100) + '%');
      pieza.style.setProperty('--dx', Math.round(Math.random() * 120 - 60) + 'px');
      pieza.style.setProperty('--giro', Math.round(Math.random() * 720 - 360) + 'deg');
      pieza.style.setProperty('--t', (1.5 + Math.random()).toFixed(2) + 's');
      pieza.style.setProperty('--r', (Math.random() * 0.4).toFixed(2) + 's');
      pieza.style.background = colores[i % colores.length];
      caja.appendChild(pieza);
    }
    document.body.appendChild(caja);
    setTimeout(function () { caja.remove(); }, 3400);
  };
  if (document.querySelector('.mensaje[data-celebrar]')) { setTimeout(celebrar, 250); }

  // Los números del resumen del Inicio (por hacer, asistencia, módulos…) suben desde cero.
  if (!sinMovimiento()) {
    document.querySelectorAll('.hola-datos b').forEach(function (el) {
      var m = /^(\d+)(\D*)$/.exec(el.textContent.trim());
      if (!m || parseInt(m[1], 10) === 0) { return; }
      var meta = parseInt(m[1], 10);
      var sufijo = m[2];
      var inicio = null;
      var paso = function (t) {
        if (inicio === null) { inicio = t; }
        var avance = Math.min(1, (t - inicio) / 700);
        el.textContent = Math.round(meta * (1 - Math.pow(1 - avance, 3))) + sufijo; // frena al llegar
        if (avance < 1) { window.requestAnimationFrame(paso); }
      };
      el.textContent = '0' + sufijo;
      window.requestAnimationFrame(paso);
    });
  }

  // La campana suena una sola vez por visita si hay avisos nuevos.
  try {
    var campana = document.querySelector('.campana');
    if (campana && campana.querySelector('.contador') && !sinMovimiento() && !sessionStorage.getItem('campana-sonada')) {
      campana.classList.add('campanada');
      sessionStorage.setItem('campana-sonada', '1');
    }
  } catch (e) { /* sin almacenamiento del navegador: no pasa nada */ }

  // Cielo de galaxia, dibujado en un lienzo: estrellas de tres profundidades que van pasando despacio y titilan,
  // una galaxia en espiral que gira muy lento y, de vez en cuando, una estrella fugaz. Es ligero (decenas o pocos cientos de
  // estrellas, entre 24 y 38 cuadros por segundo) y, mientras está detenido, deja dibujada una sola imagen fija.
  // Lo usan la pantalla de entrada (grande, con ratón), los banners de bienvenida del Inicio y el tutorial (chicos, más calmados).
  var CIELO_ENTRADA = { area: 5000, minimo: 50, tope: 200, fps: 38, raton: true, galaxia: { x: 0.72, y: 0.82, tam: 0.58, puntos: 1100 }, fugaz: [5, 7, 8] };
  // «estrecho»: dónde queda la galaxia (y de qué tamaño) cuando la caja mide menos de 560 px de ancho (celular), para no taparle el texto.
  var CIELO_BANNER = { area: 4200, minimo: 28, tope: 110, fps: 28, raton: false, galaxia: { x: 0.84, y: 0.5, tam: 1.15, puntos: 380, estrecho: { x: 0.82, y: 0.16, tam: 0.3 } }, fugaz: [9, 20, 25] };
  // En el tutorial la galaxia va en el centro de la franja, entre «Tutorial del aula virtual» y «Paso 1 de 10», para no tapar el texto.
  var CIELO_TUTORIAL = { area: 4200, minimo: 28, tope: 110, fps: 28, raton: false, galaxia: { x: 0.6, y: 0.55, tam: 1.15, puntos: 380, estrecho: { x: 0.62, y: 0.62, tam: 0.22 } }, fugaz: [9, 20, 25] };
  var crearCielo = function (lienzo, caja, cfg) {
    var ctx = lienzo.getContext && lienzo.getContext('2d');
    if (!ctx) { return null; }
    cfg = cfg || CIELO_ENTRADA;
    var TAU = Math.PI * 2;
    var COLORES = ['255,255,255', '205,228,255', '165,203,255'];
    var PROFUNDIDAD = [8, 16, 30]; // cuánto se corre cada capa con el ratón (px)
    var VELOCIDAD = [3, 7, 13]; // cuánto avanza cada capa (px por segundo)
    var estrellas = [];
    var brazos = [];
    var fugaz = null;
    var ancho = 0;
    var alto = 0;
    var corriendo = false;
    var cuadroId = 0;
    var ultimo = 0;
    var giro = 0;
    var tiempo = 0;
    var proxima = 0;
    var mirandoX = 0;
    var mirandoY = 0;
    var ratonX = 0;
    var ratonY = 0;
    var semilla = 20260;
    var azar = function () { semilla = (semilla * 16807) % 2147483647; return (semilla - 1) / 2147483646; };

    var generar = function () {
      semilla = 20260; // la misma semilla: el cielo se ve igual en cada visita
      estrellas = [];
      var cuantas = Math.max(cfg.minimo, Math.min(cfg.tope, Math.round(ancho * alto / cfg.area)));
      for (var i = 0; i < cuantas; i++) {
        var capa = i % 10 === 0 ? 2 : (i % 3 === 0 ? 1 : 0); // pocas grandes, algunas medianas, muchas chicas
        estrellas.push({
          x: azar() * ancho, y: azar() * alto, capa: capa,
          r: [0.7, 1.1, 1.7][capa] * (0.8 + azar() * 0.5),
          alfa: [0.5, 0.7, 0.95][capa],
          fase: azar() * TAU, ritmo: 0.6 + azar() * 1.6,
          estilo: 'rgb(' + COLORES[Math.floor(azar() * COLORES.length)] + ')'
        });
      }
      // Galaxia: dos brazos en espiral hechos de puntitos, y un centro más denso y cálido.
      brazos = [];
      var puntos = cfg.galaxia ? cfg.galaxia.puntos : 0;
      for (var k = 0; k < puntos; k++) {
        var nucleo = k < puntos * 0.18;
        var t = nucleo ? azar() * 0.18 : 0.12 + azar() * 0.88;
        brazos.push({
          radio: nucleo ? t : Math.pow(t, 0.85),
          angulo: (nucleo ? azar() * TAU : (k % 2) * Math.PI + t * 9.4 + (azar() - 0.5) * (0.9 - t * 0.5)),
          r: 0.8 + azar() * (nucleo ? 1.2 : 1.3),
          alfa: nucleo ? 0.8 : 0.85 * (1 - t * 0.55),
          estilo: nucleo ? 'rgb(255,236,205)' : (azar() < 0.5 ? 'rgb(190,220,255)' : 'rgb(150,195,255)')
        });
      }
    };

    var dibujarGalaxia = function () {
      if (!cfg.galaxia) { return; }
      var g = cfg.galaxia;
      var tam = Math.min(Math.min(ancho, alto) * g.tam, ancho * 0.5);
      var gx = g.x;
      var gy = g.y;
      if (g.estrecho && ancho < 560) {
        gx = g.estrecho.x;
        gy = g.estrecho.y;
        tam = Math.min(tam, ancho * g.estrecho.tam);
      }
      var cx = ancho * gx - ratonX * 22;
      var cy = alto * gy - ratonY * 22;
      var inclina = -0.42;
      var c = Math.cos(inclina);
      var s = Math.sin(inclina);
      var brillo = ctx.createRadialGradient(cx, cy, 0, cx, cy, tam * 0.9);
      brillo.addColorStop(0, 'rgba(255,238,210,.30)');
      brillo.addColorStop(0.15, 'rgba(170,205,255,.15)');
      brillo.addColorStop(1, 'rgba(120,170,255,0)');
      ctx.globalAlpha = 1;
      ctx.fillStyle = brillo;
      ctx.fillRect(cx - tam, cy - tam, tam * 2, tam * 2);
      for (var i = 0; i < brazos.length; i++) {
        var b = brazos[i];
        var a = b.angulo + giro; // gira entera, muy despacio
        var x = Math.cos(a) * b.radio * tam;
        var y = Math.sin(a) * b.radio * tam * 0.42; // vista de lado
        ctx.globalAlpha = b.alfa;
        ctx.fillStyle = b.estilo;
        ctx.fillRect(cx + x * c - y * s, cy + x * s + y * c, b.r, b.r);
      }
    };

    var dibujar = function (dt) {
      ctx.clearRect(0, 0, ancho, alto);
      dibujarGalaxia();
      for (var i = 0; i < estrellas.length; i++) {
        var e = estrellas[i];
        if (dt) {
          e.x += 0.28 * VELOCIDAD[e.capa] * dt; // las estrellas van pasando hacia arriba y un poco a la derecha
          e.y -= 0.96 * VELOCIDAD[e.capa] * dt;
          if (e.y < -6) { e.y = alto + 6; e.x = azar() * ancho; }
          if (e.x > ancho + 6) { e.x = -6; }
        }
        var x = e.x - ratonX * PROFUNDIDAD[e.capa];
        var y = e.y - ratonY * PROFUNDIDAD[e.capa];
        var brillo = e.alfa * (0.62 + 0.38 * Math.sin(tiempo * e.ritmo + e.fase));
        ctx.globalAlpha = brillo;
        ctx.fillStyle = e.estilo;
        if (e.capa === 0) {
          ctx.fillRect(x, y, e.r * 1.5, e.r * 1.5);
        } else {
          ctx.beginPath();
          ctx.arc(x, y, e.r, 0, TAU);
          ctx.fill();
          if (e.capa === 2) { // las más grandes tienen destello en cruz
            ctx.globalAlpha = brillo * 0.55;
            ctx.fillRect(x - e.r * 4, y - 0.35, e.r * 8, 0.7);
            ctx.fillRect(x - 0.35, y - e.r * 4, 0.7, e.r * 8);
          }
        }
      }
      if (fugaz) {
        var f = fugaz;
        var avance = f.edad / f.vida;
        var hx = f.x + f.vx * f.edad;
        var hy = f.y + f.vy * f.edad;
        var cola = ctx.createLinearGradient(hx, hy, hx - f.vx * 0.22, hy - f.vy * 0.22);
        cola.addColorStop(0, 'rgba(255,255,255,.95)');
        cola.addColorStop(1, 'rgba(160,200,255,0)');
        ctx.globalAlpha = Math.sin(avance * Math.PI);
        ctx.strokeStyle = cola;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(hx, hy);
        ctx.lineTo(hx - f.vx * 0.22, hy - f.vy * 0.22);
        ctx.stroke();
        if (dt) {
          f.edad += dt;
          if (f.edad >= f.vida) { fugaz = null; }
        }
      }
      ctx.globalAlpha = 1;
    };

    var paso = function (ahora) {
      cuadroId = 0;
      if (!corriendo) { return; }
      var t = ahora / 1000;
      if (t - ultimo >= 1 / cfg.fps - 0.001) {
        var dt = Math.min(0.1, t - ultimo);
        ultimo = t;
        tiempo += dt;
        giro += dt * 0.04;
        ratonX += (mirandoX - ratonX) * Math.min(1, dt * 4);
        ratonY += (mirandoY - ratonY) * Math.min(1, dt * 4);
        if (!fugaz && tiempo >= proxima) {
          fugaz = { x: ancho * (0.45 + Math.random() * 0.5), y: alto * Math.random() * 0.35, vx: -520, vy: 290, edad: 0, vida: 0.9 };
          proxima = tiempo + cfg.fugaz[1] + Math.random() * cfg.fugaz[2];
        }
        dibujar(dt);
      }
      cuadroId = window.requestAnimationFrame(paso);
    };

    return {
      ajustar: function () {
        ancho = caja.clientWidth;
        alto = caja.clientHeight;
        if (!ancho || !alto) { return false; }
        var escala = Math.min(window.devicePixelRatio || 1, 1.5);
        lienzo.width = Math.round(ancho * escala);
        lienzo.height = Math.round(alto * escala);
        ctx.setTransform(escala, 0, 0, escala, 0, 0);
        generar();
        if (!proxima) { proxima = cfg.fugaz[0]; }
        dibujar(0);
        return true;
      },
      correr: function (si) {
        if (si) {
          if (!corriendo && ancho) {
            corriendo = true;
            ultimo = window.performance.now() / 1000;
            cuadroId = window.requestAnimationFrame(paso);
          }
          return;
        }
        corriendo = false;
        if (cuadroId) { window.cancelAnimationFrame(cuadroId); cuadroId = 0; }
        mirandoX = 0;
        mirandoY = 0;
        ratonX = 0;
        ratonY = 0;
        fugaz = null;
        if (ancho) { dibujar(0); } // queda una imagen fija del cielo
      },
      mover: function (x, y) { mirandoX = x; mirandoY = y; }
    };
  };

  // Fondo vivo de la entrada: las luces, las figuras y el cielo se mueven un poco al mover el ratón (solo con ratón y pantalla ancha).
  // «Quitar el movimiento del fondo» lo detiene y se recuerda en este aparato.
  var lado = document.querySelector('.publica-lado');
  var fondo = lado && lado.querySelector('.fondo-vivo');
  if (fondo) {
    var pausa = lado.querySelector('[data-fondo-pausa]');
    var cielo = null;
    var lienzoCielo = fondo.querySelector('canvas[data-cielo]');
    if (lienzoCielo) { cielo = crearCielo(lienzoCielo, lado); }
    var quieto = false;
    try { quieto = localStorage.getItem('fondo-quieto') === '1'; } catch (e) { /* sin almacenamiento */ }
    var centrarFondo = function () {
      fondo.style.setProperty('--px', 0);
      fondo.style.setProperty('--py', 0);
      if (cielo) { cielo.mover(0, 0); }
    };
    // Mueve el cielo solo si hay lugar donde verlo, nadie pidió menos movimiento y no se quitó el movimiento del fondo.
    var actualizarCielo = function () {
      if (!cielo) { return; }
      var visible = fondo.offsetWidth > 0 && cielo.ajustar();
      cielo.correr(visible && !quieto && !sinMovimiento());
    };
    var ponerQuieto = function (valor) {
      quieto = valor;
      lado.classList.toggle('fondo-quieto', valor);
      if (valor) { centrarFondo(); }
      if (pausa) { pausa.textContent = valor ? 'Poner el movimiento del fondo' : 'Quitar el movimiento del fondo'; }
    };
    ponerQuieto(quieto);
    actualizarCielo();
    if (window.ResizeObserver) {
      new window.ResizeObserver(actualizarCielo).observe(lado);
    } else {
      window.addEventListener('resize', actualizarCielo);
    }
    if (pausa) {
      pausa.addEventListener('click', function () {
        ponerQuieto(!quieto);
        try { localStorage.setItem('fondo-quieto', quieto ? '1' : '0'); } catch (e) { /* vale solo en esta visita */ }
        if (cielo) { cielo.correr(!quieto && !sinMovimiento()); }
      });
    }
    if (window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine) and (min-width: 992px)').matches) {
      var cuadro = 0;
      var px = 0;
      var py = 0;
      lado.addEventListener('pointermove', function (ev) {
        if (quieto || sinMovimiento() || ev.pointerType === 'touch') { return; }
        var caja = lado.getBoundingClientRect();
        px = (ev.clientX - caja.left) / caja.width - 0.5;
        py = (ev.clientY - caja.top) / caja.height - 0.5;
        if (cielo) { cielo.mover(px, py); }
        if (!cuadro) {
          cuadro = window.requestAnimationFrame(function () {
            cuadro = 0;
            fondo.style.setProperty('--px', px.toFixed(3));
            fondo.style.setProperty('--py', py.toFixed(3));
          });
        }
      });
      lado.addEventListener('pointerleave', centrarFondo);
    }
  }

  // Cielo de los banners de bienvenida (Inicio) y del encabezado del tutorial: más chico y calmado que el de la entrada.
  // Corre solo mientras se ve en pantalla (y el del tutorial, solo mientras está abierto); con «Reducir animaciones» o con el
  // aviso del aparato queda una imagen fija. Si no hay lienzo en la página, no hace nada.
  document.querySelectorAll('canvas[data-cielo-banner]').forEach(function (lienzo) {
    var caja = lienzo.parentElement;
    var cieloBanner = crearCielo(lienzo, caja, lienzo.dataset.cieloBanner === 'tutorial' ? CIELO_TUTORIAL : CIELO_BANNER);
    if (!cieloBanner) { return; }
    var enPantalla = true;
    var refrescar = function () { cieloBanner.correr(cieloBanner.ajustar() && enPantalla && !sinMovimiento()); };
    refrescar();
    if (window.ResizeObserver) {
      new window.ResizeObserver(refrescar).observe(caja);
    } else {
      window.addEventListener('resize', refrescar);
    }
    if (window.IntersectionObserver) {
      new window.IntersectionObserver(function (cambios) {
        enPantalla = cambios[cambios.length - 1].isIntersecting;
        cieloBanner.correr(enPantalla && !sinMovimiento());
      }).observe(caja);
    }
  });

  // Al enviar fotos o archivos el botón muestra «Enviando…» y un segundo toque no la manda dos veces.
  var restablecerBoton = function (form) {
    var boton = form.querySelector('.btn.ocupado');
    if (boton && boton.dataset.original !== undefined) {
      boton.innerHTML = boton.dataset.original;
      boton.classList.remove('ocupado');
      boton.removeAttribute('aria-disabled');
    }
    form.removeAttribute('aria-busy');
    delete form.dataset.ocupado;
  };
  document.querySelectorAll('form[enctype="multipart/form-data"]').forEach(function (form) {
    form.addEventListener('submit', function (ev) {
      var boton = ev.submitter || form.querySelector('button[type="submit"]');
      if (!boton || boton.name === 'despues') { return; }
      if (form.dataset.ocupado === '1') { ev.preventDefault(); return; }
      form.dataset.ocupado = '1';
      form.setAttribute('aria-busy', 'true');
      boton.dataset.original = boton.innerHTML;
      boton.classList.add('ocupado');
      boton.setAttribute('aria-disabled', 'true');
      boton.textContent = 'Enviando…';
      setTimeout(function () { restablecerBoton(form); }, 60000); // si no hubo respuesta (sin internet), se puede volver a intentar
    });
  });
  window.addEventListener('pageshow', function (ev) { // al volver atrás, el botón no se queda en «Enviando…»
    if (ev.persisted) { document.querySelectorAll('form[data-ocupado]').forEach(restablecerBoton); }
  });

  // Tutorial de primera vez («Repetir tutorial» lo vuelve a abrir): un paso a la vez. Funciona con teclado y lector de pantalla.
  var tutorial = document.getElementById('tutorial');
  if (tutorial) {
    var pasos = tutorial.querySelectorAll('[data-slide]');
    var botonAnterior = tutorial.querySelector('[data-anterior]');
    var botonSiguiente = tutorial.querySelector('[data-siguiente]');
    var botonEscuchar = tutorial.querySelector('[data-escuchar]');
    var puntosPaso = tutorial.querySelectorAll('[data-punto]');
    var numeroPaso = tutorial.querySelector('[data-paso]');
    var vozTutorial = window.speechSynthesis;
    var pasoActual = 0;
    var antesDelTutorial = document.activeElement;

    var pararVoz = function () {
      if (vozTutorial) { vozTutorial.cancel(); }
      if (botonEscuchar) { botonEscuchar.setAttribute('aria-pressed', 'false'); }
    };
    var mostrarPaso = function (n) {
      pararVoz();
      pasoActual = Math.max(0, Math.min(pasos.length - 1, n));
      pasos.forEach(function (p, i) { p.hidden = i !== pasoActual; });
      puntosPaso.forEach(function (p, i) { p.classList.toggle('activo', i === pasoActual); });
      numeroPaso.textContent = pasoActual + 1;
      botonAnterior.hidden = pasoActual === 0;
      botonSiguiente.textContent = pasoActual === pasos.length - 1 ? '¡Listo, empezar!' : 'Siguiente';
      var titulo = pasos[pasoActual].querySelector('h2');
      if (titulo) { titulo.focus(); } // el lector de pantalla lee el paso nuevo
    };
    var cerrarTutorial = function () {
      pararVoz();
      if (tutorial.close) { tutorial.close(); } else { tutorial.removeAttribute('open'); }
      if (antesDelTutorial && antesDelTutorial.focus) { antesDelTutorial.focus(); }
    };

    botonSiguiente.addEventListener('click', function () {
      if (pasoActual >= pasos.length - 1) { cerrarTutorial(); celebrar(); } else { mostrarPaso(pasoActual + 1); }
    });
    botonAnterior.addEventListener('click', function () { mostrarPaso(pasoActual - 1); });
    tutorial.querySelector('[data-saltar]').addEventListener('click', cerrarTutorial);
    tutorial.addEventListener('cancel', function (ev) { ev.preventDefault(); cerrarTutorial(); }); // tecla Esc
    tutorial.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowRight') { botonSiguiente.click(); } else if (ev.key === 'ArrowLeft' && !botonAnterior.hidden) { botonAnterior.click(); }
    });

    if (botonEscuchar) {
      if (!vozTutorial) { botonEscuchar.hidden = true; }
      botonEscuchar.addEventListener('click', function () {
        if (vozTutorial.speaking) { pararVoz(); return; }
        var paso = pasos[pasoActual];
        var texto = paso.querySelector('h2').textContent + '. ' + paso.querySelector('[data-texto]').textContent;
        var u = new SpeechSynthesisUtterance(texto);
        u.lang = 'es-PE';
        u.rate = 0.95;
        var voces = vozTutorial.getVoices().filter(function (v) { return v.lang && v.lang.indexOf('es') === 0; });
        if (voces.length) { u.voice = voces.find(function (v) { return v.lang === 'es-PE'; }) || voces[0]; }
        u.onend = function () { botonEscuchar.setAttribute('aria-pressed', 'false'); };
        botonEscuchar.setAttribute('aria-pressed', 'true');
        vozTutorial.speak(u);
      });
    }

    if (tutorial.dataset.abrir === '1') {
      mostrarPaso(0);
      if (tutorial.showModal) { tutorial.showModal(); } else { tutorial.setAttribute('open', ''); }
      mostrarPaso(0); // otra vez, ya abierto: así el foco queda en el título del primer paso
    }
  }
})();
