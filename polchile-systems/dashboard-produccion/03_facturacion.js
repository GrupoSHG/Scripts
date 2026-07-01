function getFacturacionData() {
  try {
    const SS_ID = "10PvCCTw31gOhvSgcbIy15V3lBNdQZwX7Naa0R-yPO0k";
    const ss = SpreadsheetApp.openById(SS_ID);

    const hoy          = new Date();
    const anioActualNum = hoy.getFullYear();
    const mesActualNum  = hoy.getMonth() + 1;
    const txtAnioActual = String(anioActualNum);
    const txtMesActual  = String(mesActualNum).padStart(2, '0');

    const hojaVentasFull = ss.getSheetByName("Ventas_Full");
    let totalFavMes = 0;
    let totalNcvMes = 0;

    if (hojaVentasFull) {
      const dataVentas       = hojaVentasFull.getDataRange().getValues();
      const encabezadosVentas = dataVentas[0].map(h => h.toString().trim().toLowerCase());

      const colDocto      = encabezadosVentas.findIndex(h => h === "docto" || h.includes("docto") || h.includes("tipo"));
      const colFechaVentas= encabezadosVentas.findIndex(h => h === "fecha" || h.includes("fecha") || h.startsWith("fec"));
      const colTotalNeto  = encabezadosVentas.findIndex(h => h === "total_neto" || h.includes("neto"));

      const idxDocto  = colDocto      !== -1 ? colDocto      : 1;
      const idxFechaV = colFechaVentas !== -1 ? colFechaVentas : 2;
      const idxNeto   = colTotalNeto   !== -1 ? colTotalNeto   : 10;

      for (let i = 1; i < dataVentas.length; i++) {
        let fila = dataVentas[i];
        if (!fila[0] || fila[0].toString().toLowerCase().includes("total")) continue;

        let tipoDocto  = fila[idxDocto]  ? fila[idxDocto].toString().trim().toUpperCase()  : "";
        let fechaCeldaV = fila[idxFechaV];
        let valorNeto   = parseFloat(fila[idxNeto]) || 0;

        let vAnioStr = "", vMesStr = "";

        if (fechaCeldaV instanceof Date) {
          vAnioStr = String(fechaCeldaV.getFullYear());
          vMesStr  = String(fechaCeldaV.getMonth() + 1).padStart(2, '0');
        } else if (fechaCeldaV) {
          let textoLimpioV = fechaCeldaV.toString().trim().split(' ')[0];
          let partesV = textoLimpioV.split('-');
          if (partesV.length === 3) {
            vAnioStr = partesV[0].trim();
            vMesStr  = partesV[1].trim().padStart(2, '0');
          } else {
            let partesBarrasV = textoLimpioV.split('/');
            if (partesBarrasV.length === 3) {
              if (partesBarrasV[0].length === 4) { vAnioStr = partesBarrasV[0]; vMesStr = partesBarrasV[1].padStart(2, '0'); }
              else { vAnioStr = partesBarrasV[2]; vMesStr = partesBarrasV[1].padStart(2, '0'); }
            }
          }
        }

        if (vAnioStr === txtAnioActual && vMesStr === txtMesActual) {
          if (tipoDocto === "FAV") totalFavMes += valorNeto;
          else if (tipoDocto === "NCV") totalNcvMes += valorNeto;
        }
      }
    }

    let facturadoMesActual = totalFavMes - totalNcvMes;

    const hojaPorFacturar = ss.getSheetByName("Por Facturar");
    let porRecaudarAcumulado = 0;
    let fechaEntregaCercana  = "--/--/----";

    if (hojaPorFacturar) {
      const dataPend       = hojaPorFacturar.getDataRange().getValues();
      const encabezadosPend = dataPend[0].map(h => h.toString().trim().toLowerCase());

      const idxTotpend    = encabezadosPend.indexOf("totpend");
      const idxFechaMayor = encabezadosPend.indexOf("fecha_entrega_final_mayor");
      const colFecha      = idxFechaMayor !== -1 ? idxFechaMayor : 3;
      const colTotpend    = idxTotpend    !== -1 ? idxTotpend    : 13;

      let fechasValidas = [];

      for (let i = 1; i < dataPend.length; i++) {
        let fila = dataPend[i];
        if (!fila[0] || fila[0].toString().toLowerCase().includes("total")) continue;

        let fechaCelda = fila[colFecha];
        if (fechaCelda === "" || fechaCelda === null || fechaCelda === undefined) continue;

        let celdaAnioStr = "", celdaMesStr = "", tempObjDate = null;

        if (fechaCelda instanceof Date) {
          celdaAnioStr = String(fechaCelda.getFullYear());
          celdaMesStr  = String(fechaCelda.getMonth() + 1).padStart(2, '0');
          tempObjDate  = fechaCelda;
        } else {
          let textoLimpio = fechaCelda.toString().trim().split(' ')[0];
          let partes = textoLimpio.split('-');
          if (partes.length === 3) {
            celdaAnioStr = partes[0].trim();
            celdaMesStr  = partes[1].trim().padStart(2, '0');
            tempObjDate  = new Date(parseInt(partes[0],10), parseInt(partes[1],10)-1, parseInt(partes[2],10));
          } else {
            let partesBarras = textoLimpio.split('/');
            if (partesBarras.length === 3) {
              if (partesBarras[0].length === 4) {
                celdaAnioStr = partesBarras[0].trim();
                celdaMesStr  = partesBarras[1].trim().padStart(2, '0');
                tempObjDate  = new Date(parseInt(partesBarras[0],10), parseInt(partesBarras[1],10)-1, parseInt(partesBarras[2],10));
              } else {
                celdaAnioStr = partesBarras[2].trim();
                celdaMesStr  = partesBarras[1].trim().padStart(2, '0');
                tempObjDate  = new Date(parseInt(partesBarras[2],10), parseInt(partesBarras[1],10)-1, parseInt(partesBarras[0],10));
              }
            }
          }
        }

        if (celdaAnioStr === txtAnioActual && celdaMesStr === txtMesActual) {
          let totpendVal = parseFloat(fila[colTotpend]) || 0;
          porRecaudarAcumulado += totpendVal;
          if (tempObjDate && !isNaN(tempObjDate.getTime())) fechasValidas.push(tempObjDate);
        }
      }

      if (fechasValidas.length > 0) {
        const masProxima = new Date(Math.min.apply(null, fechasValidas));
        fechaEntregaCercana = String(masProxima.getDate()).padStart(2,'0') + '/' +
                              String(masProxima.getMonth()+1).padStart(2,'0') + '/' +
                              masProxima.getFullYear();
      }
    }

    return { facturado: facturadoMesActual, porFacturar: porRecaudarAcumulado, fechaEntrega: fechaEntregaCercana };
  } catch(e) {
    Logger.log("Error general en getFacturacionData: " + e.toString());
    return { error: e.toString() };
  }
}