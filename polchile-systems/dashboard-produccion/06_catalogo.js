function getCatalogoStock() {
  try {
    const ss = SpreadsheetApp.openById(ID_WIP);
    const hoja = ss.getSheetByName("Catálogo") || ss.getSheetByName("Catalogo");
    if (!hoja) return { error: "No se encontró la hoja 'Catálogo'" };

    const data = hoja.getDataRange().getValues();
    if (data.length < 2) return { items: [], totalValor: 0, totalUnidades: 0, totalItems: 0 };

    const headers = data[0].map(h => h.toString().trim().toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, "_"));

    const iCod    = headers.indexOf("codigo");
    const iProd   = headers.indexOf("producto");
    const iFam    = headers.indexOf("familia");
    const iTipo   = headers.indexOf("tipo");
    const iPrecio = headers.indexOf("precio");
    const iStock  = headers.findIndex(h => h.includes("stock"));

    if (iProd === -1 || iPrecio === -1 || iStock === -1) {
      return { error: "Faltan columnas básicas en 'Catálogo' (producto/precio/stock_total)" };
    }

    const items = [];
    let totalValor    = 0;
    let totalUnidades = 0;

    for (let i = 1; i < data.length; i++) {
      const row      = data[i];
      const producto = (row[iProd] || '').toString().trim();
      if (!producto) continue;

      const precio = parseFloat(row[iPrecio]) || 0;
      const stock  = parseFloat(row[iStock])  || 0;
      const total  = precio * stock;

      items.push({
        codigo:   iCod  > -1 ? (row[iCod]  || '').toString().trim() : '',
        producto: producto,
        familia:  iFam  > -1 ? (row[iFam]  || '').toString().trim() : '',
        tipo:     iTipo > -1 ? (row[iTipo] || '').toString().trim() : '',
        precio:   precio,
        stock:    stock,
        total:    total
      });

      totalValor    += total;
      totalUnidades += stock;
    }

    items.sort((a, b) => b.total - a.total);

    return {
      items:         items,
      totalValor:    totalValor,
      totalUnidades: totalUnidades,
      totalItems:    items.length
    };
  } catch(e) {
    return { error: "Error getCatalogoStock: " + e.toString() };
  }
}