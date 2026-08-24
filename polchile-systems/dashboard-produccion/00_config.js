function doGet(e) {
  var action   = e && e.parameter && e.parameter.action;
  var callback = e && e.parameter && e.parameter.callback;

  // Modo API JSON (JSONP): usado por el frontend estático (Netlify) vía el
  // shim de google.script.run. Cada función llamable desde el frontend
  // necesita su propio 'case' acá.
  if (action) {
    var result;
    try {
      switch (action) {
        case 'getPrensasMetrics':      result = getPrensasMetrics();      break;
        case 'getWipData':             result = getWipData();             break;
        case 'getFacturacionData':     result = getFacturacionData();     break;
        case 'getPlanPrensas':         result = getPlanPrensas();         break;
        case 'getRendimientoPrensas':  result = getRendimientoPrensas();  break;
        case 'getProduccionDiariaMes':result = getProduccionDiariaMes(); break;
        case 'getInventarioInsumos':  result = getInventarioInsumos();   break;
        case 'getM2Ayer':              result = getM2Ayer();              break;
        case 'getWipAcero':            result = getWipAcero();            break;
        case 'getM2PSA':               result = getM2PSA();               break;
        case 'getCatalogoStock':       result = getCatalogoStock();       break;
        default: result = { error: 'Acción desconocida: ' + action };
      }
    } catch (err) {
      result = { error: err.message };
    }

    if (callback) {
      // JSONP: la respuesta se envuelve como JS ejecutable, cargado por el
      // frontend vía <script src="...">. Esto evita el problema de CORS
      // que Apps Script tiene con fetch() desde otro origen.
      return ContentService
        .createTextOutput(callback + '(' + JSON.stringify(result) + ');')
        .setMimeType(ContentService.MimeType.JAVASCRIPT);
    }

    return ContentService
      .createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // Modo HTML normal (el Apps Script Web App original, sigue funcionando igual)
  const page = e && e.parameter && e.parameter.page;
  const tplName = (page === 'plan' || page === 'itinerario') ? 'Plan' : 'Dashboard';
  return HtmlService.createTemplateFromFile(tplName)
      .evaluate()
      .setTitle(tplName === 'Plan' ? 'Itinerario de Prensas · Polchile' : 'Sistema Operativo Polchile')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1')
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

const ID_PRENSAS = "1VsrO56oje4_XVEVbUAyuOz7eb0p8ZaQ_gOzOFNW0STc";
const ID_WIP = "10PvCCTw31gOhvSgcbIy15V3lBNdQZwX7Naa0R-yPO0k";

// Presupuesto de facturación mensual (M$ CLP), Ene→Dic.
// Debe mantenerse igual al array PRESUPUESTO_MENSUAL del Cockpit Comercial.
const PRESUPUESTO_MENSUAL = [383.4, 421.2, 437.4, 367.2, 448.2, 502.2, 459.0, 469.8, 459.0, 415.8, 534.6, 502.2];

// Constantes que usa getRendimientoPrensas() (en 01_produccion.js).
// SHIFT_START_HOUR: turno empieza a las 08:00.
const SHIFT_START_HOUR = 8;

// META_POR_HORA: 170 m²/jornada de 9h (misma jornada que PLAN_CONFIG.jornadaH
// en 05_plan.js) → 170/9 ≈ 18.89 m²/h, igual para las 7 prensas.
const META_POR_HORA = {
  P1: 18.89, P2: 18.89, P3: 18.89, P4: 18.89, P5: 18.89, P6: 18.89, P7: 18.89
};

function parseDateCustom(val) {
  if (!val) return null;
  if (val instanceof Date) {
    if (isNaN(val.getTime())) return null;
    return val;
  }
  let str = val.toString().trim();
  let datePart = str.split(/[\sT]+/)[0];
  let parts = datePart.split(/[-/]/);
  if (parts.length === 3) {
    let p0 = parseInt(parts[0], 10);
    let p1 = parseInt(parts[1], 10) - 1;
    let p2 = parseInt(parts[2], 10);
    if (p0 > 1000) {
      return new Date(p0, p1, p2);
    } else {
      let y = p2;
      if (y < 100) y += 2000;
      return new Date(y, p1, p0);
    }
  }
  let fallback = new Date(val);
  if (!isNaN(fallback.getTime())) return fallback;
  return null;
}
// ======================================================================
// SUPABASE — Fase 3: lectura de datos ya sincronizados por el pipeline
// ======================================================================
// Requiere 2 Propiedades de secuencia de comandos configuradas en ESTE
// proyecto (dashboard-produccion), igual que ya hiciste en cockpit-comercial:
//   SUPABASE_URL       → https://hauricnpsamnwyhondse.supabase.co
//   SUPABASE_ANON_KEY  → tu Publishable key de Supabase
// EJECUTAR UNA SOLA VEZ: selecciona "configurarSupabase" en el desplegable de
// funciones (arriba, junto al botón ▶ Ejecutar) y dale a Ejecutar. Deja
// SUPABASE_URL / SUPABASE_ANON_KEY apuntando al proyecto consolidado.
function configurarSupabase() {
  var props = PropertiesService.getScriptProperties();
  props.setProperty('SUPABASE_URL', 'https://ffxopvzxyeacpbtxuagu.supabase.co');
  props.setProperty('SUPABASE_ANON_KEY', 'sb_publishable_7UxU-do4iR5rP7Fnx8kQiw_XqDLMaHc');
  Logger.log('Listo: SUPABASE_URL y SUPABASE_ANON_KEY actualizados al proyecto consolidado.');
}

function getSupabaseConfig_() {
  var props = PropertiesService.getScriptProperties();
  var url = props.getProperty('SUPABASE_URL');
  var key = props.getProperty('SUPABASE_ANON_KEY');
  if (!url || !key) {
    throw new Error('Faltan SUPABASE_URL / SUPABASE_ANON_KEY en Propiedades del script');
  }
  return { url: url, key: key };
}

function supabaseSelect_(tabla, filtro) {
  var cfg = getSupabaseConfig_();
  var qs  = filtro || 'select=*';
  var PAGE_SIZE = 1000; // límite por defecto de la API REST de Supabase
  var todasLasFilas = [];
  var desde = 0;

  while (true) {
    var url = cfg.url + '/rest/v1/' + tabla + '?' + qs;
    var res = UrlFetchApp.fetch(url, {
      method: 'get',
      headers: {
        'apikey': cfg.key,
        'Authorization': 'Bearer ' + cfg.key,
        'Accept-Profile': 'shg_dashboards',
        'Range-Unit': 'items',
        'Range': desde + '-' + (desde + PAGE_SIZE - 1)
      },
      muteHttpExceptions: true
    });

    var code = res.getResponseCode();
    if (code !== 200 && code !== 206) {
      throw new Error('Supabase [' + tabla + '] respondió ' + code + ': ' + res.getContentText().substring(0, 300));
    }

    var pagina = JSON.parse(res.getContentText());
    todasLasFilas = todasLasFilas.concat(pagina);

    if (pagina.length < PAGE_SIZE) break;
    desde += PAGE_SIZE;
  }

  return todasLasFilas;
}