// ============================================================
// AGREGAR COLUMNAS USD DETALLE — Registro Diario
// Ejecutar UNA vez en el Sheet existente
// Inserta las cuentas USD de Polchile como columnas separadas
// y mantiene todos los datos existentes intactos
// ============================================================
// INSTRUCCIONES:
// 1. Ve a tu Google Sheet → Extensiones → Apps Script
// 2. Crea un nuevo archivo (+ → Secuencia de comandos) → llámalo "AgregarUSD"
// 3. Pega TODO este código
// 4. Guarda con Ctrl+S
// 5. Selecciona la función "agregarColumnasUSD" y ejecuta
// ============================================================

function agregarColumnasUSD() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var hoja = ss.getSheetByName('Registro Diario');
  if (!hoja) {
    SpreadsheetApp.getUi().alert('Error: No se encontró la hoja "Registro Diario"');
    return;
  }

  // Estructura actual (antes del cambio):
  // A: Fecha
  // B: Ingresado por
  // C: POL Santander
  // D: POL Itaú
  // E: POL Security
  // F: POL BCI
  // G: POL Bco Chile
  // H: USD TOTAL Polchile  ← aquí insertamos 4 columnas de detalle
  // I: M5 BCI 1
  // J: M5 BCI 2
  // K: M5 Bco Chile
  // L: M5 Itaú
  // M: USD M5 Itaú
  // N: CyS Bco Chile
  // O: Comp Polchile
  // P: Comp M5
  // Q: Comp CyS
  // R: Observaciones

  // Insertar 4 columnas en posición H (columna 8)
  // Esto empuja todo lo que estaba en H hacia la derecha
  hoja.insertColumnsBefore(8, 4);

  // Ahora la estructura queda:
  // H: (nueva) POL USD Santander
  // I: (nueva) POL USD Itaú
  // J: (nueva) POL USD Security
  // K: (nueva) POL USD BCI
  // L: (era H) USD TOTAL Polchile — ahora con fórmula suma de H:K
  // M: (era I) M5 BCI 1
  // N: (era J) M5 BCI 2
  // O: (era K) M5 Bco Chile
  // P: (era L) M5 Itaú
  // Q: (era M) USD M5 Itaú
  // R: (era N) CyS Bco Chile
  // S: (era O) Comp Polchile
  // T: (era P) Comp M5
  // U: (era Q) Comp CyS
  // V: (era R) Observaciones

  // ---- FILA 1: ajustar merge del título ----
  // El título en fila 1 ya estaba mergeado A1:R1, con las 4 nuevas columnas
  // necesitamos extenderlo a V1
  try {
    hoja.getRange('A1:V1').breakApart();
    hoja.getRange('A1:V1').merge();
  } catch(e) { /* si no había merge previo, continuar */ }

  // ---- FILA 2: actualizar grupo POLCHILE ----
  // El grupo Polchile era C2:H2, ahora debe ser C2:L2
  try {
    hoja.getRange('C2:H2').breakApart();
  } catch(e) {}
  hoja.getRange('C2:L2').merge()
    .setValue('POLCHILE — pesos + USD detalle')
    .setBackground('#0D47A1').setFontColor('#FFFFFF')
    .setFontSize(10).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // Ajustar grupos siguientes en fila 2
  // M5 era I2:M2, ahora es M2:Q2
  try { hoja.getRange('I2:M2').breakApart(); } catch(e) {}
  hoja.getRange('M2:Q2').merge()
    .setValue('M5 INDUSTRIAL — pesos + USD')
    .setBackground('#1B5E20').setFontColor('#FFFFFF')
    .setFontSize(10).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // CyS era N2, ahora es R2
  hoja.getRange('R2')
    .setValue('CYS')
    .setBackground('#E65100').setFontColor('#FFFFFF')
    .setFontSize(10).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // Compromisos era O2:Q2, ahora es S2:U2
  try { hoja.getRange('O2:Q2').breakApart(); } catch(e) {}
  hoja.getRange('S2:U2').merge()
    .setValue('COMPROMISOS 14 DIAS')
    .setBackground('#B71C1C').setFontColor('#FFFFFF')
    .setFontSize(10).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // Notas era R2, ahora es V2
  hoja.getRange('V2')
    .setValue('NOTAS')
    .setBackground('#37474F').setFontColor('#FFFFFF')
    .setFontSize(10).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // ---- FILA 3: encabezados de columna ----
  hoja.setRowHeight(3, 52);

  // Nuevas columnas H, I, J, K
  hoja.getRange('H3').setValue('USD Santander\n0-051-0048805-3')
    .setBackground('#263238').setFontColor('#FFFFFF')
    .setFontSize(9).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle').setWrap(true);

  hoja.getRange('I3').setValue('USD Itaú\n1201323427')
    .setBackground('#263238').setFontColor('#FFFFFF')
    .setFontSize(9).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle').setWrap(true);

  hoja.getRange('J3').setValue('USD Security\n929733817')
    .setBackground('#263238').setFontColor('#FFFFFF')
    .setFontSize(9).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle').setWrap(true);

  hoja.getRange('K3').setValue('USD BCI\n11188588')
    .setBackground('#263238').setFontColor('#FFFFFF')
    .setFontSize(9).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle').setWrap(true);

  // Columna L: actualizar encabezado de Total USD Polchile
  hoja.getRange('L3').setValue('USD TOTAL\nPolchile (suma)')
    .setBackground('#263238').setFontColor('#00d4ff')
    .setFontSize(9).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle').setWrap(true);

  // ---- ANCHOS DE COLUMNA para las nuevas ----
  hoja.setColumnWidth(8, 120);   // H: USD Santander
  hoja.setColumnWidth(9, 120);   // I: USD Itaú
  hoja.setColumnWidth(10, 120);  // J: USD Security
  hoja.setColumnWidth(11, 120);  // K: USD BCI
  hoja.setColumnWidth(12, 125);  // L: USD Total (fórmula)

  // ---- FÓRMULA en L4 en adelante: suma de H+I+J+K ----
  // Aplicar fórmula de suma para filas de datos existentes y futuras
  var lastRow = hoja.getLastRow();
  if (lastRow >= 4) {
    for (var row = 4; row <= Math.max(lastRow, 200); row++) {
      hoja.getRange(row, 12).setFormula('=H' + row + '+I' + row + '+J' + row + '+K' + row);
    }
  }

  // ---- FORMATOS numéricos para nuevas columnas ----
  hoja.getRange('H4:K200').setNumberFormat('"USD "0.00');
  hoja.getRange('L4:L200').setNumberFormat('"USD "0.00');

  // ---- DATOS INICIALES fila 4 (saldos reales del 10 mayo) ----
  // Actualizar con saldos reales conocidos
  hoja.getRange('H4').setValue(5000);      // USD Santander 0-051-0048805-3
  hoja.getRange('I4').setValue(1972.26);   // USD Itaú 1201323427
  hoja.getRange('J4').setValue(0);         // USD Security 929733817
  hoja.getRange('K4').setValue(5652.59);   // USD BCI 11188588
  // L4 se calcula automáticamente por fórmula = 12.624,85

  // ---- CONGELAR filas (mantener) ----
  hoja.setFrozenRows(3);

  SpreadsheetApp.getUi().alert(
    '✅ Columnas USD agregadas correctamente.\n\n' +
    'Se agregaron 4 columnas de detalle USD Polchile:\n' +
    '  H: USD Santander 0-051-0048805-3\n' +
    '  I: USD Itaú 1201323427\n' +
    '  J: USD Security 929733817\n' +
    '  K: USD BCI 11188588\n' +
    '  L: USD Total Polchile (suma automática)\n\n' +
    'El resto de las columnas se desplazó hacia la derecha.\n\n' +
    'IMPORTANTE: Actualiza el script Dashboard.gs para\n' +
    'leer las nuevas posiciones de columna.'
  );
}