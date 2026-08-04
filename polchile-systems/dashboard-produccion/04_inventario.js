function getInventarioInsumos() {
  try {
    // Supabase: tablas 'consumos_acero' y 'consumos_pol'
    // (antes leía los Sheets "Consumos Acero" y "Consumos POL")
    const resultado = { acero: [], pol: [] };

    const filasAcero = supabaseSelect_('consumos_acero');
    filasAcero.forEach(function(row) {
      if (!row.codigo && !row.descripcion) return;
      resultado.acero.push({
        codigo:       row.codigo       || "",
        descripcion:  row.descripcion  || "",
        stk_fisico:   parseFloat(row.stk_fisico)   || 0,
        por_entregar: parseFloat(row.por_entregar) || 0,
        disponible:   parseFloat(row.disponible)   || 0,
        por_llegar:   parseFloat(row.por_llegar)   || 0,
        disp_futuro:  parseFloat(row.disp_futuro)  || 0,
      });
    });

    const filasPol = supabaseSelect_('consumos_pol');
    filasPol.forEach(function(row) {
      if (!row.codigo && !row.descripcion) return;
      resultado.pol.push({
        codigo:       row.codigo       || "",
        descripcion:  row.descripcion  || "",
        stk_fisico:   parseFloat(row.stk_fisico)   || 0,
        por_entregar: parseFloat(row.por_entregar) || 0,
        disponible:   parseFloat(row.disponible)   || 0,
        por_llegar:   parseFloat(row.por_llegar)   || 0,
        disp_futuro:  parseFloat(row.disp_futuro)  || 0,
      });
    });

    return { acero: resultado.acero, pol: resultado.pol,
             kpiAcero: calcKpi(resultado.acero), kpiPol: calcKpi(resultado.pol) };
  } catch(e) {
    return { error: "Error inventario: " + e.toString() };
  }
}

function calcKpi(rows) {
  return {
    totalItems: rows.length,
    conStock:   rows.filter(r => r.stk_fisico > 0).length,
    sinStock:   rows.filter(r => r.stk_fisico <= 0).length,
    dispNeg:    rows.filter(r => r.disponible < 0).length,
    totalStk:   rows.reduce((a, r) => a + r.stk_fisico,  0),
    totalDisp:  rows.reduce((a, r) => a + r.disponible,   0),
    totalFuturo:rows.reduce((a, r) => a + r.disp_futuro,  0),
  };
}