/**
 * ============================================================
 * SHIM de google.script.run para el frontend estático (Netlify)
 * ============================================================
 * Usa JSONP (carga la respuesta como <script>) en vez de fetch(),
 * porque los Web Apps de Apps Script no devuelven headers CORS
 * utilizables por fetch()/XMLHttpRequest desde otro origen —
 * aunque abrir la URL a mano en el navegador sí funcione, y aunque
 * curl/Invoke-RestMethod tampoco vean el problema (CORS solo lo
 * aplica el navegador en fetch, nunca en terminal).
 *
 * Un <script src="..."> nunca está sujeto a CORS, así que este
 * shim pide al backend que envuelva la respuesta en una función
 * callback y la carga como si fuera un script normal.
 *
 * IMPORTANTE: define window.__SCRIPT_URL__ ANTES de cargar este
 * archivo (ver index.html). El doGet de Code.js debe soportar el
 * parámetro ?callback=... (ver code-doGet-actualizado.js).
 */
(function () {
  'use strict';

  var _contador = 0;
  var TIMEOUT_MS = 45000;

  function crearRunner() {
    var _success = null;
    var _failure = null;

    var proxy = new Proxy({}, {
      get: function (target, prop) {
        if (prop === 'withSuccessHandler') {
          return function (fn) { _success = fn; return proxy; };
        }
        if (prop === 'withFailureHandler') {
          return function (fn) { _failure = fn; return proxy; };
        }

        // Cualquier otro nombre de propiedad = la función de Apps Script a invocar
        return function () {
          var args = Array.prototype.slice.call(arguments);
          var base = window.__SCRIPT_URL__;

          if (!base) {
            var errUrl = new Error('window.__SCRIPT_URL__ no está definido.');
            if (_failure) _failure(errUrl); else console.error(errUrl);
            return;
          }

          _contador++;
          var callbackName = '__gsShimCallback_' + _contador;
          var script = null;
          var timeoutId = null;

          function limpiar() {
            delete window[callbackName];
            if (script && script.parentNode) script.parentNode.removeChild(script);
            if (timeoutId) clearTimeout(timeoutId);
          }

          window[callbackName] = function (data) {
            limpiar();
            if (data && data.error) {
              if (_failure) _failure({ message: data.error });
              else console.error('Error en ' + prop + ':', data.error);
            } else if (_success) {
              _success(data);
            }
          };

          var url = base
            + '?action=' + encodeURIComponent(prop)
            + '&callback=' + callbackName;
          if (args.length) {
            url += '&args=' + encodeURIComponent(JSON.stringify(args));
          }

          script = document.createElement('script');
          script.src = url;
          script.onerror = function () {
            limpiar();
            var err = new Error('Error de red/carga al llamar ' + prop);
            if (_failure) _failure(err); else console.error(err);
          };

          timeoutId = setTimeout(function () {
            limpiar();
            var err = new Error('Timeout esperando respuesta de ' + prop);
            if (_failure) _failure(err); else console.error(err);
          }, TIMEOUT_MS);

          document.head.appendChild(script);
        };
      }
    });

    return proxy;
  }

  window.google = window.google || {};
  window.google.script = window.google.script || {};

  Object.defineProperty(window.google.script, 'run', {
    configurable: true,
    get: function () { return crearRunner(); }
  });
})();
