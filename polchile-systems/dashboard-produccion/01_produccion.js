function getM2Ayer() {
  try {
    const ss   = SpreadsheetApp.openById(ID_WIP);
    const hoja = ss.getSheetByName("M2 Producidos");
    if (!hoja) return { error: "No se encontró 'M2 Producidos'" };

    const data       = hoja.getDataRange().getValues();
    const hoy        = new Date();
    const ayer       = new Date(hoy); ayer.setDate(hoy.getDate() - 1);
    const dAyer      = ayer.getDate();
    const mAyer      = ayer.getMonth();
    const aAyer      = ayer.getFullYear();
    const mesActual  = hoy.getMonth();
    const anioActual = hoy.getFullYear();

    let totalAyer = 0, totalMes = 0;

    for (let i = 1; i < data.length; i++) {
      const marca  = data[i][0];
      const prensa = (data[i][1] || '').toString().trim().toUpperCase();
      const m2     = parseFloat(data[i][2]) || 0;
      if (!marca || m2 <= 0) continue;
      // Solo PA — excluir PC4 y Bandejera
      const esPSA = prensa.includes('PC4') || prensa.includes('BANDEJERA') || prensa.includes('BAND');
      if (esPSA) continue;
      const f = parseDateCustom(marca);
      if (!f) continue;
      if (f.getMonth() === mesActual  && f.getFullYear() === anioActual) totalMes  += m2;
      if (f.getDate()  === dAyer && f.getMonth() === mAyer && f.getFullYear() === aAyer) totalAyer += m2;
    }

    const dd = String(dAyer).padStart(2,'0');
    const mm = String(mAyer+1).padStart(2,'0');
    return { total: Math.round(totalAyer), totalMes: Math.round(totalMes), fecha: `${dd}/${mm}/${aAyer}` };
  } catch(e) {
    return { error: "Error getM2Ayer: " + e.toString() };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
function getM2PSA() {
  try {
    const ss   = SpreadsheetApp.openById(ID_WIP);
    const hoja = ss.getSheetByName("M2 Producidos");
    if (!hoja) return { error: "No se encontró 'M2 Producidos'" };

    const data       = hoja.getDataRange().getValues();
    const hoy        = new Date();
    const ayer       = new Date(hoy); ayer.setDate(hoy.getDate() - 1);
    const mesActual  = hoy.getMonth();
    const anioActual = hoy.getFullYear();
    const dAyer      = ayer.getDate();
    const mAyer      = ayer.getMonth();
    const aAyer      = ayer.getFullYear();

    let totalAyer = 0, ayerPC4 = 0, ayerBandejera = 0;
    let totalMes  = 0, mesPC4  = 0, mesBandejera  = 0;

    for (let i = 1; i < data.length; i++) {
      const marca  = data[i][0];
      const prensa = (data[i][1] || '').toString().trim().toUpperCase();
      const m2     = parseFloat(data[i][2]) || 0;
      if (!marca || m2 <= 0) continue;

      const esPC4       = prensa.includes('PC4');
      const esBandejera = prensa.includes('BANDEJERA') || prensa.includes('BAND');
      if (!esPC4 && !esBandejera) continue;

      const f = parseDateCustom(marca);
      if (!f) continue;

      if (f.getMonth() === mesActual && f.getFullYear() === anioActual) {
        totalMes += m2;
        if (esPC4)       mesPC4       += m2;
        if (esBandejera) mesBandejera += m2;
      }
      if (f.getDate() === dAyer && f.getMonth() === mAyer && f.getFullYear() === aAyer) {
        totalAyer += m2;
        if (esPC4)       ayerPC4       += m2;
        if (esBandejera) ayerBandejera += m2;
      }
    }

    const dd = String(dAyer).padStart(2,'0');
    const mm = String(mAyer+1).padStart(2,'0');

    return {
      ayer: { total: Math.round(totalAyer), pc4: Math.round(ayerPC4), bandejera: Math.round(ayerBandejera), fecha: `${dd}/${mm}/${aAyer}` },
      mes:  { total: Math.round(totalMes),  pc4: Math.round(mesPC4),  bandejera: Math.round(mesBandejera) }
    };
  } catch(e) {
    return { error: "Error getM2PSA: " + e.toString() };
  }
}

function getProduccionDiariaMes() {
  try {
    const ss   = SpreadsheetApp.openById(ID_WIP);
    const hoja = ss.getSheetByName("M2 Producidos");
    if (!hoja) return { error: "No se encontró 'M2 Producidos'" };

    const data       = hoja.getDataRange().getValues();
    const hoy        = new Date();
    const mesActual  = hoy.getMonth();
    const anioActual = hoy.getFullYear();
    const produccionPorDia = {};

    for (let i = 1; i < data.length; i++) {
      const marca  = data[i][0];
      const prensa = (data[i][1] || '').toString().trim().toUpperCase();
      const m2     = parseFloat(data[i][2]) || 0;
      if (!marca || m2 <= 0) continue;
      const esPSA = prensa.includes('PC4') || prensa.includes('BANDEJERA') || prensa.includes('BAND');
      if (esPSA) continue;
      const f = parseDateCustom(marca);
      if (!f) continue;
      if (f.getMonth() === mesActual && f.getFullYear() === anioActual) {
        const dia = f.getDate();
        produccionPorDia[dia] = (produccionPorDia[dia] || 0) + m2;
      }
    }

    const datosGrafico = [];
    Object.keys(produccionPorDia).map(Number).sort((a,b) => a-b).forEach(dia => {
      datosGrafico.push({ fecha: `${dia}/${mesActual+1}`, produccion: Math.round(produccionPorDia[dia]) });
    });

    return { meta: 1000, datos: datosGrafico };
  } catch(e) {
    return { error: "Error getProduccionDiariaMes: " + e.toString() };
  }
}

function getPrensasMetrics() {
  try {
    const ss = SpreadsheetApp.openById(ID_PRENSAS);
    const hoja = ss.getSheetByName("Dashboards m2");
    if (!hoja) return [];
    const data = hoja.getDataRange().getValues();
    const métricas = [];
    for (let i = 1; i < data.length; i++) {
      if (!data[i][0]) continue;
      métricas.push({
        name: data[i][0].toString(),
        valor: parseFloat(data[i][1]) || 0,
        cumple: data[i][2] ? !data[i][2].toString().toUpperCase().includes("NO") : true
      });
    }
    return métricas;
  } catch(e) { return []; }
}

function getRendimientoPrensas() {
  try {
    const ss   = SpreadsheetApp.openById(ID_PRENSAS);
    const hoja = ss.getSheetByName("Dashboards m2");
    if (!hoja) return { error: "No se encontró 'Dashboards m2'" };
    const data = hoja.getDataRange().getValues();

    const now        = new Date();
    const shiftStart = new Date(now);
    shiftStart.setHours(SHIFT_START_HOUR, 0, 0, 0);
    let hoursElapsed = (now.getTime() - shiftStart.getTime()) / 3600000;
    if (hoursElapsed < 0.1) hoursElapsed = 0.1;
    if (hoursElapsed > 12)  hoursElapsed = 12;

    const rows = [];
    for (let i = 1; i < data.length; i++) {
      if (!data[i][0]) continue;
      const name         = data[i][0].toString().trim();
      const real_m2      = parseFloat(data[i][1]) || 0;
      const target_per_h = META_POR_HORA[name] || 0;
      const real_per_h   = real_m2 / hoursElapsed;
      const target_total = target_per_h * hoursElapsed;
      const pct          = target_total > 0 ? (real_m2 / target_total) * 100 : 0;
      rows.push({ name, real_m2, real_per_h, target_per_h, target_total,
                  diff_per_h: real_per_h - target_per_h, pct, cumple: pct >= 90 });
    }

    return {
      rows,
      hoursElapsed,
      shiftStart: Utilities.formatDate(shiftStart, "GMT-3", "HH:mm"),
      now:        Utilities.formatDate(now,        "GMT-3", "HH:mm"),
    };
  } catch(e) { return { error: "Error rendimiento: " + e.toString() }; }
}

// ═══════════════════════════════════════════════════════════════════════════
function getM2MensualesPA() {
  try {
    const ss   = SpreadsheetApp.openById(ID_WIP);
    const hoja = ss.getSheetByName("M2 Producidos");
    if (!hoja) return { error: "No se encontró 'M2 Producidos'" };

    const data       = hoja.getDataRange().getValues();
    const hoy        = new Date();
    const mesActual  = hoy.getMonth();       // 0-indexado (0=enero)
    const anioActual = hoy.getFullYear();
    const MES_INICIO = 1;                    // 1 = febrero (0-indexado), ajustable

    // Acumulador por "año-mes" (para no mezclar años distintos si la hoja
    // llegara a acumular más de un año de historial)
    const totalesPorMes = {};

    for (let i = 1; i < data.length; i++) {
      const marca  = data[i][0];
      const prensa = (data[i][1] || '').toString().trim().toUpperCase();
      const m2     = parseFloat(data[i][2]) || 0;
      if (!marca || m2 <= 0) continue;

      // Solo PA — excluir PC4 y Bandejera (mismo criterio que getM2Ayer)
      const esPSA = prensa.includes('PC4') || prensa.includes('BANDEJERA') || prensa.includes('BAND');
      if (esPSA) continue;

      const f = parseDateCustom(marca);
      if (!f) continue;

      const anio = f.getFullYear();
      const mes  = f.getMonth(); // 0-indexado
      if (anio !== anioActual) continue;   // solo el año en curso
      if (mes  < MES_INICIO)   continue;   // desde febrero en adelante

      const key = anio + '-' + String(mes).padStart(2, '0');
      totalesPorMes[key] = (totalesPorMes[key] || 0) + m2;
    }

    const NOMBRES_MES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

    const serie = Object.keys(totalesPorMes)
      .sort()
      .map(key => {
        const [anio, mesStr] = key.split('-');
        const mesIdx = parseInt(mesStr, 10);
        return { mes: NOMBRES_MES[mesIdx], anio: parseInt(anio, 10), m2: Math.round(totalesPorMes[key]) };
      });

    const keyMesActual = anioActual + '-' + String(mesActual).padStart(2, '0');
    const totalMesActual = Math.round(totalesPorMes[keyMesActual] || 0);

    return {
      totalMesActual: totalMesActual,
      mesActualNombre: NOMBRES_MES[mesActual],
      serie: serie
    };
  } catch(e) {
    return { error: "Error getM2MensualesPA: " + e.toString() };
  }
}
