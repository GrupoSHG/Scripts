/**
 * Script de Google Ads (Herramientas → Acciones masivas → Secuencias de comandos) de la cuenta
 * de Polchile. Deja el gasto DIARIO por campaña en la pestaña "google" de una hoja de Google;
 * el workflow ads-polchile-sync (Polchile_Systems/sync_ads_polchile.py) la lee y la carga en
 * polchile_crm.inversion_ads. Pasos de instalación en Polchile_Systems/INVERSION_ADS.md.
 *
 * No necesita token de desarrollador ni la API de Google Ads: los scripts corren dentro de la
 * cuenta con los permisos del usuario que los autoriza.
 *
 * Cada corrida reescribe la pestaña completa con los últimos DIAS días (Google ajusta el gasto
 * de los días recientes). Para la primera carga poner DIAS = 400, ejecutar una vez, y volver a 60.
 * Programarlo diario (p. ej. 06:00); el workflow corre a las 07:40 hora de Chile.
 */
var HOJA_ID = '18RH7f65V080ChSQUJYgmYeJmg-mYdG0OwI2sCj6SVv0';   // hoja "Inversión Ads Polchile" (Drive de atorres), compartida con bot-erp
var DIAS    = 60;                              // ventana que se reescribe en cada corrida
var PESTANA = 'google';

function main() {
  var cuenta = AdsApp.currentAccount();
  var zona = cuenta.getTimeZone();
  var hoy = new Date();
  var hasta = Utilities.formatDate(hoy, zona, 'yyyy-MM-dd');
  var desde = Utilities.formatDate(new Date(hoy.getTime() - DIAS * 864e5), zona, 'yyyy-MM-dd');

  var consulta =
    'SELECT segments.date, campaign.id, campaign.name, campaign.advertising_channel_type, ' +
    'metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions ' +
    'FROM campaign ' +
    "WHERE segments.date BETWEEN '" + desde + "' AND '" + hasta + "' AND metrics.cost_micros > 0 " +
    'ORDER BY segments.date, campaign.name';

  var filas = [['fecha', 'campana_id', 'campana', 'costo', 'impresiones', 'clics', 'conversiones', 'tipo']];
  var total = 0;
  var it = AdsApp.report(consulta).rows();
  while (it.hasNext()) {
    var r = it.next();
    var costo = Number(r['metrics.cost_micros']) / 1e6;   // micros -> moneda de la cuenta (CLP)
    total += costo;
    filas.push([
      String(r['segments.date']), String(r['campaign.id']), r['campaign.name'],
      costo, Number(r['metrics.impressions']), Number(r['metrics.clicks']), Number(r['metrics.conversions']),
      r['campaign.advertising_channel_type'],
    ]);
  }

  var libro = SpreadsheetApp.openById(HOJA_ID);
  var hoja = libro.getSheetByName(PESTANA) || libro.insertSheet(PESTANA);
  hoja.clearContents();
  // La columna fecha queda como texto (yyyy-mm-dd) para que la hoja no la convierta a fecha local.
  hoja.getRange(1, 1, filas.length, 1).setNumberFormat('@');
  hoja.getRange(1, 1, filas.length, filas[0].length).setValues(filas);

  // Pestaña "estado": cuándo corrió por última vez y qué cubrió (el workflow la ignora).
  var estado = libro.getSheetByName('estado') || libro.insertSheet('estado');
  estado.clearContents();
  estado.getRange(1, 1, 6, 2).setValues([
    ['actualizado', Utilities.formatDate(hoy, 'America/Santiago', 'yyyy-MM-dd HH:mm')],
    ['cuenta', cuenta.getCustomerId() + ' · ' + cuenta.getName()],
    ['moneda', cuenta.getCurrencyCode()],
    ['desde', desde], ['hasta', hasta],
    ['costo_ventana', total],
  ]);

  Logger.log('Filas escritas: ' + (filas.length - 1) + ' · ' + desde + ' a ' + hasta +
             ' · costo ' + cuenta.getCurrencyCode() + ' ' + Math.round(total));
}
