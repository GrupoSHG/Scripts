function getFacturacionData() {
  try {
    const hoy           = new Date();
    const anioActualNum = hoy.getFullYear();
    const mesActualNum  = hoy.getMonth() + 1;

    // ── Ventas_Full: Supabase (antes leía el Sheet "Ventas_Full") ──
    let totalFavMes = 0;
    let totalNcvMes = 0;
    try {
      const filasVentas = supabaseSelect_('ventas_full');
      filasVentas.forEach(function(row) {
        const tipoDocto = row.docto ? row.docto.toString().trim().toUpperCase() : "";
        if (!tipoDocto) return;

        const f = parsearFechaSupabase_(row.fecha_emision);
        if (!f) return;
        if (f.getFullYear() === anioActualNum && (f.getMonth() + 1) === mesActualNum) {
          const valorNeto = parseFloat(row.total_neto) || 0;
          if (tipoDocto === "FAV") totalFavMes += valorNeto;
          else if (tipoDocto === "NCV") totalNcvMes += valorNeto;
        }
      });
    } catch (e) {
      Logger.log("Error leyendo ventas_full desde Supabase: " + e.message);
    }

    const facturadoMesActual = totalFavMes - totalNcvMes;

    // ── Por Facturar: Supabase, tabla 'calendario' ──────────────────
    // (antes leía el Sheet "Por Facturar", un reporte ya agregado con
    // columnas 'totpend'/'fecha_entrega_final_mayor' que no existen en
    // Supabase). Se recalcula el mismo resultado directo desde el detalle
    // por NV: suma de pesos_por_facturar del mes + fecha de entrega más
    // próxima entre esas mismas filas.
    let porRecaudarAcumulado = 0;
    let fechaEntregaCercana  = "--/--/----";

    try {
      const filasCal = supabaseSelect_('calendario');
      const fechasDelMes = [];

      filasCal.forEach(function(row) {
        const f = parsearFechaSupabase_(row.fecha_entrega_final);
        if (!f) return;
        if (f.getFullYear() === anioActualNum && (f.getMonth() + 1) === mesActualNum) {
          porRecaudarAcumulado += parseFloat(row.pesos_por_facturar) || 0;
          fechasDelMes.push(f);
        }
      });

      if (fechasDelMes.length > 0) {
        const masProxima = new Date(Math.min.apply(null, fechasDelMes));
        fechaEntregaCercana = String(masProxima.getDate()).padStart(2,'0') + '/' +
                              String(masProxima.getMonth()+1).padStart(2,'0') + '/' +
                              masProxima.getFullYear();
      }
    } catch (e) {
      Logger.log("Error leyendo calendario desde Supabase: " + e.message);
    }

    const presupuestoMes = (PRESUPUESTO_MENSUAL[mesActualNum - 1] || 0) * 1000000;
    const cumplimientoPct = presupuestoMes > 0 ? (facturadoMesActual / presupuestoMes) * 100 : 0;

    return {
      facturado: facturadoMesActual,
      porFacturar: porRecaudarAcumulado,
      fechaEntrega: fechaEntregaCercana,
      presupuestoMes: presupuestoMes,
      cumplimientoPct: cumplimientoPct
    };
  } catch(e) {
    Logger.log("Error general en getFacturacionData: " + e.toString());
    return { error: e.toString() };
  }
}