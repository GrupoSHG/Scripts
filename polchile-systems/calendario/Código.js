/**
 * Dashboard Web App - NV Polchile
 * Lee 'calendario' desde Supabase y cruza con 'ordenes_de_produccion'
 * Incluye Facturado Neto mes actual desde 'ventas_full'
 *
 * v3: las 3 fuentes de datos (Por Facturar, Orden de Produccion, Ventas_Full)
 * ahora se leen desde Supabase en vez de Sheets — mismo patrón que
 * cockpit-comercial y dashboard-produccion.
 */

function doGet(e) {
  var action   = e && e.parameter && e.parameter.action;
  var callback = e && e.parameter && e.parameter.callback;

  if (action) {
    var result;
    try {
      switch (action) {
        case 'getDashboardData': result = getDashboardData(); break;
        default: result = { error: 'Acción desconocida: ' + action };
      }
    } catch (err) {
      result = { error: err.message };
    }

    if (callback) {
      return ContentService
        .createTextOutput(callback + '(' + JSON.stringify(result) + ');')
        .setMimeType(ContentService.MimeType.JAVASCRIPT);
    }
    return ContentService
      .createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // Modo HTML normal (Apps Script Web App original, sin cambios)
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Dashboard NV — Polchile')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

// ======================================================================
// SUPABASE — helpers (mismo patrón que cockpit-comercial y dashboard-produccion)
// ======================================================================
// Requiere 2 Propiedades de secuencia de comandos en ESTE proyecto:
//   SUPABASE_URL       → https://hauricnpsamnwyhondse.supabase.co
//   SUPABASE_ANON_KEY  → tu Publishable key de Supabase
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
  var PAGE_SIZE = 1000;
  var todasLasFilas = [];
  var desde = 0;

  while (true) {
    var url = cfg.url + '/rest/v1/' + tabla + '?' + qs;
    var res = UrlFetchApp.fetch(url, {
      method: 'get',
      headers: {
        'apikey': cfg.key,
        'Authorization': 'Bearer ' + cfg.key,
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

// ======================================================================
// getDashboardData — Supabase: tabla 'calendario'
// (antes leía el Sheet "Por Facturar")
// ======================================================================
function getDashboardData() {
  const filasCal = supabaseSelect_('calendario');
  if (!filasCal.length) return { error: 'Sin datos en la tabla calendario' };

  const resumenOP = cargarResumenOP();
  const facturadoNetoMes = getFacturadoNetoMesActual();

  const hoy = new Date(); hoy.setHours(0,0,0,0);

  const datos = filasCal
    .filter(r => r.nota_de_venta !== null && r.nota_de_venta !== undefined && r.nota_de_venta !== '')
    .map(r => {
      const fechaFinal = parsearFecha(r.fecha_entrega_final);
      const fechaOrig  = parsearFecha(r.fecha_entrega_original_lineas);
      const diasAtrasoReal = fechaFinal ? Math.floor((hoy - fechaFinal)/(86400000)) : null;

      let diffDias = null;
      if (fechaOrig && fechaFinal) {
        diffDias = Math.round((fechaFinal - fechaOrig) / 86400000);
      }

      const qSol  = num(r.q_solicitado);
      const qPend = num(r.q_por_despachar);
      const qDesp = qSol - qPend;
      const nvKey = String(r.nota_de_venta).trim();

      return {
        nv: r.nota_de_venta,
        fechaOriginal: formatFecha(r.fecha_entrega_original_lineas),
        fechaFinal: formatFecha(r.fecha_entrega_final),
        diffDias: diffDias,
        qSolicitado: qSol,
        qPorDespachar: qPend,
        qDespachado: qDesp,
        pctAvance: qSol > 0 ? qDesp / qSol : 0,
        cliente: String(r.cliente || '').trim(),
        estado: String(r.estado || ''),
        totalNv: num(r.total_nv),
        totalNeto: num(r.total_neto_nv),
        facturado: num(r.pesos_facturados),
        porFacturar: num(r.pesos_por_facturar),
        pagado: num(r.pagado_nv),
        pendCobro: num(r.total_pendiente_de_cobro),
        entregadoPesos: num(r.total_entregado_pesos),
        porEntregarPesos: num(r.total_por_entregar_pesos),
        tieneModif: num(r.cantidad_cambios_fecha_entrega) > 0,
        diasAtrasoReal: diasAtrasoReal,
        estaAtrasada: diasAtrasoReal !== null && diasAtrasoReal > 0,
        opPorClase: resumenOP[nvKey] || 'Compra externa / Faltan medidas'
      };
    });

  return {
    fecha: Utilities.formatDate(new Date(), 'America/Santiago', 'dd-MM-yyyy HH:mm'),
    datos: datos,
    facturadoNetoMes: facturadoNetoMes
  };
}

// ======================================================================
// getFacturadoNetoMesActual — Supabase: tabla 'ventas_full'
// (antes leía el Sheet "Ventas_Full")
// ======================================================================
function getFacturadoNetoMesActual() {
  try {
    const hoy = new Date();
    const anioActualNum = hoy.getFullYear();
    const mesActualNum = hoy.getMonth() + 1;
    const txtAnioActual = String(anioActualNum);
    const txtMesActual = String(mesActualNum).padStart(2, '0');

    const filas = supabaseSelect_('ventas_full');

    let totalFav = 0, totalNcv = 0;

    filas.forEach(function(fila) {
      const tipoDocto = fila.docto ? fila.docto.toString().trim().toUpperCase() : '';
      if (!tipoDocto) return;

      const valorNeto = num(fila.total_neto);
      const fechaCelda = fila.fecha_emision;

      let anioStr = '', mesStr = '';
      if (fechaCelda) {
        const txt = fechaCelda.toString().trim();
        const partesGuion = txt.split('-');
        if (partesGuion.length >= 3) {
          anioStr = partesGuion[0].trim();
          mesStr  = partesGuion[1].trim().padStart(2, '0');
        }
      }

      if (anioStr === txtAnioActual && mesStr === txtMesActual) {
        if (tipoDocto === 'FAV')      totalFav += valorNeto;
        else if (tipoDocto === 'NCV') totalNcv += valorNeto;
      }
    });

    const neto = totalFav - totalNcv;
    Logger.log('Facturado neto mes actual: FAV=%s NCV=%s Neto=%s', totalFav, totalNcv, neto);

    return { totalFav: totalFav, totalNcv: totalNcv, neto: neto };
  } catch (e) {
    Logger.log('Error en getFacturadoNetoMesActual: ' + e.toString());
    return { totalFav: 0, totalNcv: 0, neto: 0, error: e.toString() };
  }
}

// ======================================================================
// cargarResumenOP — Supabase: tabla 'ordenes_de_produccion'
// (antes leía el Sheet "Orden de Produccion")
// ======================================================================
function cargarResumenOP() {
  try {
    const filas = supabaseSelect_('ordenes_de_produccion');
    if (!filas.length) return {};

    const acum = {};
    filas.forEach(function(r) {
      const bodegaRaw = String(r.bodega_nombre_op || '').toUpperCase().trim();
      if (!bodegaRaw.includes('TERMINAD')) return;

      const nvRaw = r.nota_vta;
      if (nvRaw === null || nvRaw === undefined || nvRaw === '') return;
      const nv = String(nvRaw).trim();

      const clase1 = String(r.clase1 || '').trim();
      const cant = num(r.cantidad_op);
      const unidad = r.unidmed ? String(r.unidmed).trim() : '';

      if (!nv || !clase1 || cant <= 0) return;

      if (!acum[nv]) acum[nv] = {};
      if (!acum[nv][clase1]) acum[nv][clase1] = { cant: 0, unidad: unidad };
      acum[nv][clase1].cant += cant;
      if (!acum[nv][clase1].unidad && unidad) acum[nv][clase1].unidad = unidad;
    });

    const resultado = {};
    Object.entries(acum).forEach(([nv, clases]) => {
      const partes = Object.entries(clases)
        .sort((a, b) => b[1].cant - a[1].cant)
        .map(([clase, info]) => {
          const cantFmt = new Intl.NumberFormat('es-CL', {maximumFractionDigits: 2}).format(info.cant);
          return clase + ': ' + cantFmt + (info.unidad ? ' ' + info.unidad : '');
        });
      resultado[nv] = partes.join(' | ');
    });

    return resultado;
  } catch (e) {
    Logger.log('Error en cargarResumenOP: ' + e.toString());
    return {};
  }
}

function num(val) {
  if (val === null || val === undefined || val === '') return 0;
  if (typeof val === 'number') return val;
  const s = String(val).trim()
    .replace(/\s/g,'')
    .replace(/\.(?=\d{3}(\D|$))/g, '')
    .replace(',', '.');
  const n = parseFloat(s);
  return isNaN(n) ? 0 : n;
}

function parsearFecha(val) {
  if (!val) return null;
  if (val instanceof Date) return val;
  const m = String(val).trim().match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return new Date(+m[1], +m[2]-1, +m[3]);
  const d = new Date(val);
  return isNaN(d.getTime()) ? null : d;
}

function formatFecha(val) {
  const d = parsearFecha(val);
  if (!d) return '';
  return Utilities.formatDate(d, 'America/Santiago', 'dd-MM-yyyy');
}

function testConexion() {
  Logger.log('=== Prueba de conexión a Supabase ===');
  try {
    const cal = supabaseSelect_('calendario');
    Logger.log('✅ calendario: ' + cal.length + ' filas');
  } catch(e) { Logger.log('❌ calendario: ' + e.message); }

  try {
    const op = supabaseSelect_('ordenes_de_produccion');
    Logger.log('✅ ordenes_de_produccion: ' + op.length + ' filas');
  } catch(e) { Logger.log('❌ ordenes_de_produccion: ' + e.message); }

  try {
    const vf = supabaseSelect_('ventas_full');
    Logger.log('✅ ventas_full: ' + vf.length + ' filas');
  } catch(e) { Logger.log('❌ ventas_full: ' + e.message); }

  Logger.log('\n=== Facturado Neto Mes Actual ===');
  const fact = getFacturadoNetoMesActual();
  Logger.log('FAV: %s', fact.totalFav);
  Logger.log('NCV: %s', fact.totalNcv);
  Logger.log('Neto: %s', fact.neto);
}