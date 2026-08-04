function getWipData() {
  try {
    // Supabase: tabla 'ordenes_de_produccion' (antes leía el Sheet "Orden de Produccion")
    const filas = supabaseSelect_('ordenes_de_produccion');

    const hoy        = new Date();
    const mesActual  = hoy.getMonth();
    const anioActual = hoy.getFullYear();

    const conAislacion = [];
    const sinAislacion = [];

    filas.forEach(function(row) {
      const pend   = parseFloat(row.cantidad_pendiente)  || 0;
      const term   = parseFloat(row.cantidad_terminada)  || 0;
      const bodega = row.bodega_nombre_op ? row.bodega_nombre_op.toString().toUpperCase() : "";
      const codigo = row.codigo_producto  ? row.codigo_producto.toString().toUpperCase()  : "";

      let esMesActualProducido = false;
      if (row.fechain) {
        const f = parsearFechaSupabase_(row.fechain);
        if (f && f.getMonth() === mesActual && f.getFullYear() === anioActual) esMesActualProducido = true;
      }

      const producidaMes = esMesActualProducido ? term : 0;

      if (pend > 0 || term > 0) {
        // OJO: revestimiento, espesor, largo y cliente no existen en la tabla
        // 'ordenes_de_produccion' de Supabase (tampoco existían realmente en
        // el Sheet — la consulta SQL nunca los trajo, por eso ya mostraban
        // "-" antes también). Se mantienen como "-" por consistencia.
        const item = {
          nv:            row.nota_vta        !== undefined ? row.nota_vta        : "-",
          op:            row.num_op          !== undefined ? row.num_op          : "-",
          producto:      row.nombre_producto !== undefined ? row.nombre_producto : "-",
          cliente:       "-",
          revestimiento: "-",
          espesor:       "-",
          largo:         "-",
          pedida:        parseFloat(row.cantidad_op) || 0,
          producida:     term,
          producidaMes:  producidaMes,
          pendiente:     pend,
          bodega:        bodega,
          unidad:        row.unidmed !== undefined ? row.unidmed : "UN",
          estado:        (term > 0 && pend > 0) ? "EN PROCESO" : (pend <= 0 ? "TERMINADO" : "PENDIENTE")
        };

        if (codigo.includes("PA") && !codigo.includes("PSA")) {
          if (bodega.includes("TERMINADO") || bodega.includes("STOCK")) {
            conAislacion.push(item);
          }
        } else if (codigo.includes("PSA")) {
          if (bodega.includes("TERMINADO") || bodega.includes("INSUMO") || bodega.includes("STOCK")) {
            sinAislacion.push(item);
          }
        }
      }
    });

    // "M2 Producidos" sigue siendo entrada manual (Categoría B) — sin cambios
    let producidoPAMes = 0;
    try {
      const ss = SpreadsheetApp.openById(ID_WIP);
      const hojaM2 = ss.getSheetByName("M2 Producidos");
      if (hojaM2) {
        const dataM2 = hojaM2.getDataRange().getValues();
        for (let i = 1; i < dataM2.length; i++) {
          const marca  = dataM2[i][0];
          const prensa = (dataM2[i][1] || '').toString().trim().toUpperCase();
          const m2     = parseFloat(dataM2[i][2]) || 0;
          if (!marca || m2 <= 0) continue;
          const esPSA = prensa.includes('PC4') || prensa.includes('BANDEJERA') || prensa.includes('BAND');
          if (esPSA) continue;
          const f = parseDateCustom(marca);
          if (f && f.getMonth() === mesActual && f.getFullYear() === anioActual) producidoPAMes += m2;
        }
      }
    } catch (err) { Logger.log("Error producidoPAMes: " + err.toString()); }

    return { conAislacion, sinAislacion, producidoPAMes };
  } catch(e) { return { error: "Error en el servidor: " + e.toString() }; }
}

// Parsea fechas que llegan de Supabase (ISO: "2026-07-24T00:00:00" o similar)
function parsearFechaSupabase_(valor) {
  if (!valor) return null;
  const d = new Date(valor);
  return isNaN(d.getTime()) ? null : d;
}

function getWipAcero() {
  try {
    // Supabase: tabla 'consumos_acero' (antes leía el Sheet "Consumos Acero")
    const filasConsumo = supabaseSelect_('consumos_acero');
    const stockMap = {};
    filasConsumo.forEach(function(row) {
      const stk = parseFloat(row.stk_fisico) || 0;
      if (stk <= 0) return;
      const cod = (row.codigo || '').toString().trim().toUpperCase();
      if (!cod) return;
      const por_entregar = parseFloat(row.por_entregar) || 0;
      const por_llegar   = parseFloat(row.por_llegar)   || 0;
      stockMap[cod] = {
        codigo: cod, descripcion: row.descripcion || '',
        stk_fisico: stk, por_entregar: por_entregar,
        saldo: stk - por_entregar, por_llegar: por_llegar,
      };
    });

    // Supabase: tabla 'aceros' (antes leía el Sheet "Aceros")
    // OJO: los nombres de columna cambiaron respecto al Sheet viejo —
    // ya no es "consumo_mes" sino 'promedio_cantidad_mensual', y el nombre
    // del acero es 'producto' en vez de una columna llamada "Acero".
    const filasAceros = supabaseSelect_('aceros');
    const consumoMap = {};
    filasAceros.forEach(function(row) {
      const cod = (row.codigo || '').toString().trim().toUpperCase();
      if (!cod) return;
      consumoMap[cod] = {
        nombre: row.producto || '',
        consumo_mes_kg: parseFloat(row.promedio_cantidad_mensual) || 0,
      };
    });

    const hoy = new Date();
    const resultado = [];

    for (const cod in stockMap) {
      const s            = stockMap[cod];
      const a            = consumoMap[cod] || null;
      const consumo_mes  = a ? (a.consumo_mes_kg || 0) : 0;
      const stk          = s.stk_fisico;
      const por_entregar = s.por_entregar;
      const saldo        = s.saldo;
      const por_llegar   = s.por_llegar;

      let meses_restantes = null, fecha_agotamiento = null;

      if (consumo_mes > 0) {
        meses_restantes = saldo / consumo_mes;
        const fechaAg = new Date(hoy);
        fechaAg.setDate(fechaAg.getDate() + Math.round(meses_restantes * 30.44));
        fecha_agotamiento = String(fechaAg.getDate()).padStart(2,'0') + '/' +
                            String(fechaAg.getMonth()+1).padStart(2,'0') + '/' +
                            fechaAg.getFullYear();
        meses_restantes = Math.round(meses_restantes * 10) / 10;
      }

      const urgencia = meses_restantes === null ? 'sin_consumo'
        : meses_restantes <= 1  ? 'critico'
        : meses_restantes <= 2  ? 'alerta'
        : 'ok';

      resultado.push({
        codigo: cod, descripcion: a ? a.nombre : s.descripcion,
        consumo_mes_kg: consumo_mes,
        stk_fisico: stk, por_entregar: por_entregar,
        saldo: saldo, por_llegar: por_llegar,
        meses_restantes: meses_restantes,
        fecha_agotamiento: fecha_agotamiento,
        urgencia: urgencia,
      });
    }

    resultado.sort((a, b) => b.consumo_mes_kg - a.consumo_mes_kg);
    return { items: resultado };
  } catch(e) {
    return { error: "Error getWipAcero: " + e.toString() };
  }
}