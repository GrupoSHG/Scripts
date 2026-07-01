function doGet(e) {
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