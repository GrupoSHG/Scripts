function getInventarioInsumos() {
  try {
    const ss    = SpreadsheetApp.openById(ID_WIP);
    const hojas = [
      { nombre: "Consumos Acero", tipo: "acero" },
      { nombre: "Consumos POL",   tipo: "pol"   }
    ];
    const resultado = { acero: [], pol: [] };

    hojas.forEach(({ nombre, tipo }) => {
      const hoja = ss.getSheetByName(nombre);
      if (!hoja) return;
      const data    = hoja.getDataRange().getValues();
      const headers = data[0].map(h => h.toString().trim().toLowerCase()
        .normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, "_"));

      const iCod    = headers.findIndex(h => h.includes("codigo"));
      const iDesc   = headers.findIndex(h => h.includes("desc"));
      const iStk    = headers.findIndex(h => h.includes("stk") || h.includes("fisico"));
      const iPorEnt = headers.findIndex(h => h.includes("por_ent") || h.includes("entregar"));
      const iDisp   = headers.findIndex(h => h === "disponible" || h.includes("disponib"));
      const iPorLl  = headers.findIndex(h => h.includes("llegar"));
      const iDispF  = headers.findIndex(h => h.includes("futuro"));

      for (let i = 1; i < data.length; i++) {
        const row = data[i];
        if (!row[iCod] && !row[iDesc]) continue;
        resultado[tipo].push({
          codigo:       iCod    > -1 ? row[iCod].toString()            : "",
          descripcion:  iDesc   > -1 ? row[iDesc].toString()           : "",
          stk_fisico:   iStk    > -1 ? (parseFloat(row[iStk])    || 0) : 0,
          por_entregar: iPorEnt > -1 ? (parseFloat(row[iPorEnt]) || 0) : 0,
          disponible:   iDisp   > -1 ? (parseFloat(row[iDisp])   || 0) : 0,
          por_llegar:   iPorLl  > -1 ? (parseFloat(row[iPorLl])  || 0) : 0,
          disp_futuro:  iDispF  > -1 ? (parseFloat(row[iDispF])  || 0) : 0,
        });
      }
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