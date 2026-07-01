function getWipData() {
  try {
    const ss = SpreadsheetApp.openById(ID_WIP);
    const hoja = ss.getSheetByName("Orden de Produccion");
    if (!hoja) return { error: "No se encontró la pestaña 'Orden de Produccion'" };

    const data = hoja.getDataRange().getValues();
    const headers = data[0].map(h => h.toString().replace(/[\r\n\s_]+/g, '').toUpperCase());

    const findCol = (exactMatches, partialMatch) => {
      for (let em of exactMatches) {
        let idx = headers.indexOf(em);
        if (idx > -1) return idx;
      }
      if (partialMatch) return headers.findIndex(h => h.includes(partialMatch));
      return -1;
    };

    const colNV        = findCol(["NOTAVTA"], "NOTAVTA");
    const colOP        = findCol(["NUMOP"], "NUMOP");
    const colPedida    = findCol(["CANTIDADOP", "CANTIDADPEDIDA"], "CANTIDADOP");
    const colTerminada = findCol(["CANTIDADTERMINADA"], "TERMINADA");
    const colPendiente = findCol(["CANTIDADPENDIENTE"], "PENDIENTE");
    const colProd      = findCol(["NOMBREPRODUCTO"], "PRODUCTO");
    const colCodigo    = findCol(["CODIGOPRODUCTO"], "CODIGO");
    const colUnidad    = findCol(["UNIDMED"], "UNID");
    const colBodega    = findCol(["BODEGANOMBREOP"], "BODEGA");
    const colRevest    = findCol(["REVESTIMIENTO"], "REVEST");
    const colEspesor   = findCol(["ESPESOR"], "ESP");
    const colLargo     = findCol(["LARGO"], "LARG");
    const colCliente   = findCol(["CLIENTE"], "CLIEN");
    const colFechaIn   = findCol(["FECHAIN", "FECHAINGRESO"], "FECHAIN");

    if (colPendiente === -1) return { error: "Falta la columna CANTIDAD_PENDIENTE en el Excel" };
    if (colBodega    === -1) return { error: "Falta la columna BODEGA_NOMBRE_OP en el Excel" };
    if (colCodigo    === -1) return { error: "Falta la columna CODIGO_PRODUCTO en el Excel" };

    const hoy        = new Date();
    const mesActual  = hoy.getMonth();
    const anioActual = hoy.getFullYear();

    const conAislacion = [];
    const sinAislacion = [];

    for (let i = 1; i < data.length; i++) {
      let pend   = parseFloat(data[i][colPendiente]) || 0;
      let term   = colTerminada > -1 ? parseFloat(data[i][colTerminada]) || 0 : 0;
      let bodega = data[i][colBodega] ? data[i][colBodega].toString().toUpperCase() : "";
      let codigo = data[i][colCodigo] ? data[i][colCodigo].toString().toUpperCase() : "";

      let esMesActualProducido = false;
      if (colFechaIn > -1 && data[i][colFechaIn]) {
        let f = parseDateCustom(data[i][colFechaIn]);
        if (f && f.getMonth() === mesActual && f.getFullYear() === anioActual) esMesActualProducido = true;
      }

      let producidaMes = esMesActualProducido ? term : 0;

      if (pend > 0 || term > 0) {
        const item = {
          nv:            colNV      > -1 ? data[i][colNV]                          : "-",
          op:            colOP      > -1 ? data[i][colOP]                          : "-",
          producto:      colProd    > -1 ? data[i][colProd]                        : "-",
          cliente:       colCliente > -1 ? data[i][colCliente]                     : "-",
          revestimiento: colRevest  > -1 ? data[i][colRevest]                      : "-",
          espesor:       colEspesor > -1 ? data[i][colEspesor]                     : "-",
          largo:         colLargo   > -1 ? data[i][colLargo]                       : "-",
          pedida:        colPedida  > -1 ? parseFloat(data[i][colPedida])  || 0    : 0,
          producida:     term,
          producidaMes:  producidaMes,
          pendiente:     pend,
          bodega:        bodega,
          unidad:        colUnidad  > -1 ? data[i][colUnidad]                      : "UN",
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
    }

    // ── producidoPAMes: lee M2 Producidos excluyendo PC4 y Bandejera ──
    let producidoPAMes = 0;
    try {
      const hojaM2 = ss.getSheetByName("M2 Producidos");
      if (hojaM2) {
        const dataM2 = hojaM2.getDataRange().getValues();
        // Col A=Marca temporal, Col B=Prensa, Col C=M2
        for (let i = 1; i < dataM2.length; i++) {
          const marca  = dataM2[i][0];
          const prensa = (dataM2[i][1] || '').toString().trim().toUpperCase();
          const m2     = parseFloat(dataM2[i][2]) || 0;
          if (!marca || m2 <= 0) continue;
          // Excluir PSA (PC4 y Bandejera) — solo contar PA
          const esPSA = prensa.includes('PC4') ||
                        prensa.includes('BANDEJERA') ||
                        prensa.includes('BAND');
          if (esPSA) continue;
          const f = parseDateCustom(marca);
          if (f && f.getMonth() === mesActual && f.getFullYear() === anioActual) {
            producidoPAMes += m2;
          }
        }
      }
    } catch (err) { Logger.log("Error producidoPAMes: " + err.toString()); }

    return { conAislacion, sinAislacion, producidoPAMes };
  } catch(e) { return { error: "Error en el servidor: " + e.toString() }; }
}

function getWipAcero() {
  try {
    const ss = SpreadsheetApp.openById(ID_WIP);

    const hojaC = ss.getSheetByName("Consumos Acero");
    if (!hojaC) return { error: "No se encontró 'Consumos Acero'" };
    const dataC = hojaC.getDataRange().getValues();
    const hC    = dataC[0].map(h => h.toString().trim().toLowerCase());
    const iCod  = hC.findIndex(h => h.includes("codigo"));
    const iDesc = hC.findIndex(h => h.includes("desc"));
    const iStk  = hC.findIndex(h => h.includes("stk") || h.includes("fisico"));

    const stockMap = {};
    for (let i = 1; i < dataC.length; i++) {
      const stk = parseFloat(dataC[i][iStk]) || 0;
      if (stk <= 0) continue;
      const cod  = (dataC[i][iCod]  || '').toString().trim().toUpperCase();
      const desc = (dataC[i][iDesc] || '').toString().trim();
      if (!cod) continue;
      stockMap[cod] = { codigo: cod, descripcion: desc, stk_fisico: stk };
    }

    const hojaA = ss.getSheetByName("Aceros");
    if (!hojaA) return { error: "No se encontró hoja 'Aceros'" };
    const dataA   = hojaA.getDataRange().getValues();
    const hA_full = dataA[0].map(h => h.toString().trim().toLowerCase()
                      .normalize("NFD").replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,'_'));

    let colCodA = -1, colNombre = -1, colConsumo = -1;
    for (let c = 11; c < hA_full.length; c++) {
      const h = hA_full[c];
      if (colCodA    === -1 && h.includes('codigo'))                        colCodA    = c;
      if (colNombre  === -1 && h === 'acero')                               colNombre  = c;
      if (colConsumo === -1 && h.includes('consumo') && h.includes('mes')) colConsumo = c;
    }
    if (colCodA    === -1) colCodA    = 11;
    if (colNombre  === -1) colNombre  = 12;
    if (colConsumo === -1) colConsumo = 13;

    const consumoMap = {};
    for (let i = 1; i < dataA.length; i++) {
      const cod     = (dataA[i][colCodA]    || '').toString().trim().toUpperCase();
      const nombre  = (dataA[i][colNombre]  || '').toString().trim();
      const consumo = parseFloat(dataA[i][colConsumo]) || 0;
      if (!cod) continue;
      consumoMap[cod] = { nombre, consumo_mes_kg: consumo };
    }

    const hoy = new Date();
    const resultado = [];

    for (const cod in stockMap) {
      const s           = stockMap[cod];
      const a           = consumoMap[cod] || null;
      const consumo_mes = a ? (a.consumo_mes_kg || 0) : 0;
      const stk         = s.stk_fisico;
      let meses_restantes = null, fecha_agotamiento = null;

      if (consumo_mes > 0) {
        meses_restantes = stk / consumo_mes;
        const fechaAg = new Date(hoy);
        fechaAg.setDate(fechaAg.getDate() + Math.round(meses_restantes * 30.44));
        fecha_agotamiento = String(fechaAg.getDate()).padStart(2,'0') + '/' +
                            String(fechaAg.getMonth()+1).padStart(2,'0') + '/' +
                            fechaAg.getFullYear();
        meses_restantes = Math.round(meses_restantes * 10) / 10;
      }

      const urgencia = meses_restantes === null ? 'sin_consumo'
        : meses_restantes <= 1 ? 'critico'
        : meses_restantes <= 2 ? 'alerta'
        : 'ok';

      resultado.push({ codigo: cod, descripcion: a ? a.nombre : s.descripcion,
        stk_fisico: stk, consumo_mes_kg: consumo_mes,
        meses_restantes, fecha_agotamiento, urgencia });
    }

    const ord = { critico:0, alerta:1, ok:2, sin_consumo:3 };
    resultado.sort((a,b) => {
      if (ord[a.urgencia] !== ord[b.urgencia]) return ord[a.urgencia]-ord[b.urgencia];
      if (a.meses_restantes===null) return 1;
      if (b.meses_restantes===null) return -1;
      return a.meses_restantes - b.meses_restantes;
    });

    return { items: resultado };
  } catch(e) {
    return { error: "Error getWipAcero: " + e.toString() };
  }
}