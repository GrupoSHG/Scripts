// ============================================================
// PARAMETROS DETALLADOS v3 — Gastos Fijos Mensuales Polchile
// Datos extraídos del Presupuesto 2026 P&L de Polchile
// M5 y CyS quedan en amarillo pendientes de completar
// ============================================================
// INSTRUCCIONES:
// 1. Apps Script → + → Secuencia de comandos → "ActualizarParametros"
// 2. Pega este código → Ctrl+S → selecciona actualizarParametros → Ejecutar
// ============================================================

function actualizarParametros() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  var existente = ss.getSheetByName('Parametros');
  if (existente) ss.deleteSheet(existente);
  var h = ss.insertSheet('Parametros');
  h.setTabColor('#6A1B9A');

  // Anchos de columna
  h.setColumnWidth(1, 245); h.setColumnWidth(2, 225);
  h.setColumnWidth(3, 145); h.setColumnWidth(4, 145);
  h.setColumnWidth(5, 145); h.setColumnWidth(6, 155);

  var MORADO  = '#4A148C'; var MORADO2 = '#6A1B9A'; var MORADO_CL = '#EDE7F6';
  var AZUL    = '#0D47A1'; var AZUL_CL = '#E3F2FD';
  var VERDE   = '#1B5E20'; var VERDE_CL = '#E8F5E9';
  var NARANJA = '#E65100'; var NARAN_CL = '#FFF3E0';
  var GRIS    = '#546E7A'; var GRIS_CL  = '#ECEFF1';
  var AMAR    = '#FFF9C4'; var BLANCO   = '#FFFFFF'; var NEGRO = '#212121';

  // ================================================================
  // Construir toda la hoja con setValues en batch (anti-timeout)
  // ================================================================

  // Preparar datos para escribir de una vez
  // Estructura: [categoría, descripción, polchile, m5, cys, formula-consolidado]
  // Los valores de M5 y CyS van en 0 (amarillo = pendiente)

  var filas = [
    // ROW 1: Título
    ['PARÁMETROS — Gastos Fijos Mensuales por Empresa (Presupuesto 2026)','','','','',''],
    // ROW 2: vacía
    ['','','','','',''],
    // ROW 3: Nota
    ['  ⚠  Solo Gonzalo modifica · Actualizar cada Q con el forecast · Montos en $ mensuales','','','','',''],
    // ROW 4: vacía
    ['','','','','',''],
    // ROW 5: encabezados
    ['Categoría de gasto fijo','Descripción / Detalle','Polchile ($)','M5 Industrial ($)','CyS ($)','Consolidado ($)'],

    // ROW 6: SEP — PRODUCCIÓN REMUNERACIONES
    ['REMUNERACIONES DE PRODUCCIÓN','','','','',''],
    // ROW 7
    ['Personal Directo Producción','Operarios planta — sueldo base fijo',20651932,0,0,'=C7+D7+E7'],
    // ROW 8
    ['Bonos Producción','Bonos fijos asegurados de producción',7150000,0,0,'=C8+D8+E8'],
    // ROW 9
    ['Finiquitos Producción','Provisión mensual de finiquitos producción',934930,0,0,'=C9+D9+E9'],

    // ROW 10: SEP — MOI
    ['MANO DE OBRA INDIRECTA (MOI)','','','','',''],
    // ROW 11
    ['Gerentes, Jefaturas y Supervisores','Supervisión y jefaturas de planta',12252444,0,0,'=C11+D11+E11'],
    // ROW 12
    ['Choferes','Personal de transporte y despacho',2020747,0,0,'=C12+D12+E12'],
    // ROW 13
    ['Mantenimiento — Personal','Técnicos y operarios de mantención',2717634,0,0,'=C13+D13+E13'],
    // ROW 14
    ['Personal Seguridad','Guardias y vigilancia instalaciones',1535723,0,0,'=C14+D14+E14'],

    // ROW 15: SEP — REMUNERACIONES VENTAS
    ['REMUNERACIONES VENTAS — Solo parte fija','','','','',''],
    // ROW 16
    ['Remuneraciones Ventas (fijo)','Sueldos base equipo comercial — sin comisiones ni bonos',17225667,0,0,'=C16+D16+E16'],

    // ROW 17: SEP — REMUNERACIONES ADMINISTRACIÓN
    ['REMUNERACIONES ADMINISTRACIÓN — Solo parte fija','','','','',''],
    // ROW 18
    ['Remuneraciones Adm. (fijo)','Sueldos base finanzas, RRHH, admin — sin bonos',27374039,0,0,'=C18+D18+E18'],
    // ROW 19
    ['Directorio','Dietas y pagos fijos a directores',1702500,0,0,'=C19+D19+E19'],

    // ROW 20: SEP — ARRIENDOS
    ['ARRIENDOS Y ESPACIOS','','','','',''],
    // ROW 21
    ['Arriendo Instalaciones','Planta, bodega y patio operaciones (con reajuste UF)',11381191,0,0,'=C21+D21+E21'],
    // ROW 22
    ['Arriendo Oficinas','Oficinas administrativas y comerciales',1264577,0,0,'=C22+D22+E22'],

    // ROW 23: SEP — SUMINISTROS Y MANTENCIÓN
    ['SUMINISTROS Y MANTENCIÓN','','','','',''],
    // ROW 24
    ['Electricidad y Gas','Suministros energéticos de planta e instalaciones',1755000,0,0,'=C24+D24+E24'],
    // ROW 25
    ['Mantención Equipos y Maquinaria','Preventiva + correctiva + vehículos',3827553,0,0,'=C25+D25+E25'],

    // ROW 26: SEP — ADMINISTRACIÓN GENERAL
    ['GASTOS ADMINISTRACIÓN GENERAL','','','','',''],
    // ROW 27
    ['Seguros','Resp. civil, incendio, robo, vehículos',903327,0,0,'=C27+D27+E27'],
    // ROW 28
    ['Honorarios Fijos','Contadores, abogados y consultores recurrentes',200000,0,0,'=C28+D28+E28'],
    // ROW 29
    ['Asesorías Recurrentes','Asesorías financieras, comerciales, legales y otras',1950000,0,0,'=C29+D29+E29'],
    // ROW 30
    ['Gastos Generales Oficina','Sistemas, telecom, artículos oficina, soporte TI',4370334,0,0,'=C30+D30+E30'],
    // ROW 31
    ['Transportes y Logística','Combustible, fletes y transporte de personal',700000,0,0,'=C31+D31+E31'],
    // ROW 32
    ['Otros Gastos Adm. Fijos','Eventos, efemérides, otros gastos recurrentes menores',479167,0,0,'=C32+D32+E32'],

    // ROW 33: SEP — GASTOS FINANCIEROS
    ['GASTOS FINANCIEROS FIJOS','','','','',''],
    // ROW 34
    ['Intereses Créditos Comex','Intereses y costos financieros líneas Comex',7336350,0,0,'=C34+D34+E34'],
    // ROW 35
    ['Intereses Leasings','Cuotas de interés de contratos de leasing',536258,0,0,'=C35+D35+E35'],
    // ROW 36
    ['Gastos Bancarios y Otros','Comisiones, mantención, tarjetas crédito',13035,0,0,'=C36+D36+E36'],

    // ROW 37: SEP — COMPROMISOS RECURRENTES (no son "gastos fijos" pero son predecibles)
    ['COMPROMISOS RECURRENTES PREDECIBLES','','','','',''],
    // ROW 38
    ['Imposiciones (Previred)','AFP + Salud + Seguro cesantía — estimado mensual',30000000,0,0,'=C38+D38+E38'],
    // ROW 39
    ['IVA Estimado Mensual (F29)','Promedio histórico — variable pero predecible',35000000,0,0,'=C39+D39+E39'],
    // ROW 40
    ['Anticipos de Sueldos','Anticipos quincenales al personal',6000000,0,0,'=C40+D40+E40'],

    // ROW 41: vacía
    ['','','','','',''],

    // ROW 42: TOTAL MENSUAL
    ['TOTAL GASTOS FIJOS MENSUALES','','=SUM(C7:C40)','=SUM(D7:D40)','=SUM(E7:E40)','=C42+D42+E42'],

    // ROW 43: vacía
    ['','','','','',''],

    // ROW 44: SEMANAL — ESTA ES LA FILA QUE LEE EL DASHBOARD
    ['Gastos fijos por semana (÷4)  →  Lee el dashboard','','=C42/4','=D42/4','=E42/4','=F42/4'],

    // ROW 45: vacía
    ['','','','','',''],

    // ROW 46: SEP SEMÁFORO
    ['PARÁMETROS DEL SEMÁFORO — umbrales de runway en semanas','','','','',''],
    // ROW 47
    ['Semáforo VERDE — runway mínimo (semanas)','Si runway ≥ este valor → verde',3,3,3,3],
    // ROW 48
    ['Semáforo AMARILLO — runway mínimo (semanas)','Si runway ≥ este valor → amarillo (bajo este → rojo)',2,2,2,2],

    // ROW 49: vacía
    ['','','','','',''],

    // ROW 50: SEP CAJA MÍNIMA
    ['CAJA MÍNIMA RESERVADA — no usar en operaciones normales','','','','',''],
    // ROW 51
    ['Caja mínima operativa ($)','Monto mínimo en cuenta — no tocar',50000000,20000000,5000000,'=C51+D51+E51'],
    // ROW 52
    ['Reserva Comex USD (Polchile)','USD mínimos para renovación Comex',200000,'n/a','n/a',200000],
  ];

  // Escribir todos los datos de una vez
  h.getRange(1, 1, filas.length, 6).setValues(filas);

  // ================================================================
  // Aplicar formatos en batch
  // ================================================================

  // Altura de filas
  var alturas = {1:44, 2:6, 3:26, 4:6, 5:36,
    6:26, 7:26, 8:26, 9:26,
    10:26, 11:26, 12:26, 13:26, 14:26,
    15:26, 16:26,
    17:26, 18:26, 19:26,
    20:26, 21:26, 22:26,
    23:26, 24:26, 25:26,
    26:26, 27:26, 28:26, 29:26, 30:26, 31:26, 32:26,
    33:26, 34:26, 35:26, 36:26,
    37:26, 38:26, 39:26, 40:26,
    41:8, 42:36, 43:8, 44:30,
    45:8, 46:26, 47:26, 48:26,
    49:8, 50:26, 51:26, 52:26
  };
  for (var r in alturas) h.setRowHeight(parseInt(r), alturas[r]);

  // ---- Fila 1: título ----
  h.getRange('A1:F1').merge()
    .setBackground(MORADO).setFontColor(BLANCO)
    .setFontSize(12).setFontWeight('bold')
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // ---- Fila 3: nota ----
  h.getRange('A3:F3').merge()
    .setBackground('#FFF8E1').setFontColor(NARANJA)
    .setFontSize(10).setVerticalAlignment('middle');

  // ---- Fila 5: encabezados ----
  h.getRange('A5:F5')
    .setBackground(MORADO2).setFontColor(BLANCO)
    .setFontWeight('bold').setFontSize(10)
    .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // Separadores de sección — filas 6,10,15,17,20,23,26,33,37,46,50
  var seps = [6,10,15,17,20,23,26,33,37,46,50];
  seps.forEach(function(r) {
    h.getRange(r, 1, 1, 6).merge()
      .setBackground(MORADO_CL).setFontColor(MORADO)
      .setFontWeight('bold').setFontSize(10).setVerticalAlignment('middle');
  });

  // Filas de datos — formato moneda cols C,D,E,F
  var dataRows = [7,8,9,11,12,13,14,16,18,19,21,22,24,25,27,28,29,30,31,32,34,35,36,38,39,40];
  dataRows.forEach(function(r) {
    h.getRange(r, 1).setFontSize(10).setFontColor(NEGRO).setFontWeight('bold');
    h.getRange(r, 2).setFontSize(9).setFontColor(GRIS);
    // Polchile — azul
    h.getRange(r, 3).setNumberFormat('$#,##0').setHorizontalAlignment('right').setBackground(AZUL_CL);
    // M5 — verde, amarillo si 0
    h.getRange(r, 4).setNumberFormat('$#,##0').setHorizontalAlignment('right')
      .setBackground(AMAR).setFontColor('#795548')
      .setNote('Pendiente: ingresar monto real de M5 Industrial');
    // CyS — naranja, amarillo si 0
    h.getRange(r, 5).setNumberFormat('$#,##0').setHorizontalAlignment('right')
      .setBackground(AMAR).setFontColor('#795548')
      .setNote('Pendiente: ingresar monto real de CyS');
    // Consolidado
    h.getRange(r, 6).setNumberFormat('$#,##0').setHorizontalAlignment('right')
      .setFontWeight('bold').setBackground(MORADO_CL).setFontColor(MORADO);
  });

  // ---- Fila 42: TOTAL MENSUAL ----
  h.getRange('A42:B42').merge()
    .setBackground(MORADO).setFontColor(BLANCO)
    .setFontWeight('bold').setFontSize(12).setVerticalAlignment('middle');
  h.getRange('C42').setNumberFormat('$#,##0').setFontWeight('bold').setFontSize(12)
    .setHorizontalAlignment('right').setBackground(AZUL_CL).setFontColor(AZUL);
  h.getRange('D42').setNumberFormat('$#,##0').setFontWeight('bold').setFontSize(12)
    .setHorizontalAlignment('right').setBackground(AMAR).setFontColor('#795548');
  h.getRange('E42').setNumberFormat('$#,##0').setFontWeight('bold').setFontSize(12)
    .setHorizontalAlignment('right').setBackground(AMAR).setFontColor('#795548');
  h.getRange('F42').setNumberFormat('$#,##0').setFontWeight('bold').setFontSize(13)
    .setHorizontalAlignment('right').setBackground(MORADO_CL).setFontColor(MORADO);

  // ---- Fila 44: SEMANAL (lee el dashboard) ----
  h.getRange('A44:B44').merge()
    .setBackground(GRIS_CL).setFontColor(GRIS)
    .setFontWeight('bold').setFontSize(10).setVerticalAlignment('middle');
  h.getRange('C44').setNumberFormat('$#,##0').setFontWeight('bold').setFontSize(11)
    .setHorizontalAlignment('right').setBackground(AZUL_CL).setFontColor(AZUL);
  h.getRange('D44').setNumberFormat('$#,##0').setFontWeight('bold').setFontSize(11)
    .setHorizontalAlignment('right').setBackground(AMAR).setFontColor('#795548');
  h.getRange('E44').setNumberFormat('$#,##0').setFontWeight('bold').setFontSize(11)
    .setHorizontalAlignment('right').setBackground(AMAR).setFontColor('#795548');
  h.getRange('F44').setNumberFormat('$#,##0').setFontWeight('bold').setFontSize(11)
    .setHorizontalAlignment('right').setBackground(MORADO_CL).setFontColor(MORADO);

  // Semáforos fila 47-48
  [47,48].forEach(function(r) {
    h.getRange(r,1).setFontWeight('bold').setFontSize(10).setFontColor(NEGRO);
    h.getRange(r,2).setFontSize(9).setFontColor(GRIS);
    var bg = r===47 ? '#C8E6C9' : '#FFF9C4';
    var fc = r===47 ? '#1B5E20' : '#F57F17';
    [3,4,5,6].forEach(function(c){
      h.getRange(r,c).setBackground(bg).setFontColor(fc)
        .setFontWeight('bold').setFontSize(11).setHorizontalAlignment('center');
    });
  });

  // Caja mínima fila 51-52
  h.getRange(51,1).setFontWeight('bold').setFontSize(10);
  h.getRange(51,2).setFontSize(9).setFontColor(GRIS);
  h.getRange('C51').setNumberFormat('$#,##0').setHorizontalAlignment('right').setFontWeight('bold').setBackground(AZUL_CL).setFontColor(AZUL);
  h.getRange('D51').setNumberFormat('$#,##0').setHorizontalAlignment('right').setFontWeight('bold').setBackground(VERDE_CL).setFontColor(VERDE);
  h.getRange('E51').setNumberFormat('$#,##0').setHorizontalAlignment('right').setFontWeight('bold').setBackground(NARAN_CL).setFontColor(NARANJA);
  h.getRange('F51').setNumberFormat('$#,##0').setHorizontalAlignment('right').setFontWeight('bold');

  h.getRange(52,1).setFontWeight('bold').setFontSize(10);
  h.getRange(52,2).setFontSize(9).setFontColor(GRIS);
  h.getRange('C52').setNumberFormat('"USD "0').setHorizontalAlignment('right').setFontWeight('bold').setBackground(AZUL_CL).setFontColor(AZUL);
  h.getRange('D52').setFontColor(GRIS).setHorizontalAlignment('center');
  h.getRange('E52').setFontColor(GRIS).setHorizontalAlignment('center');
  h.getRange('F52').setNumberFormat('"USD "0').setHorizontalAlignment('right').setFontWeight('bold');

  h.setFrozenRows(5);

  // Actualizar también el Dashboard para leer fila 44
  SpreadsheetApp.getUi().alert(
    '✅ Parámetros actualizados con datos del Presupuesto 2026 Polchile.\n\n' +
    'RESUMEN POLCHILE:\n' +
    '  Rem. Personal Producción:  $28.736.862/mes\n' +
    '  Mano de Obra Indirecta:    $18.526.548/mes\n' +
    '  Rem. Ventas (fijo):        $17.225.667/mes\n' +
    '  Rem. Adm. (fijo):          $27.374.039/mes\n' +
    '  Directorio:                 $1.702.500/mes\n' +
    '  Arriendos:                 $12.645.768/mes\n' +
    '  Suministros + Mantención:   $5.582.553/mes\n' +
    '  Adm. general:               $8.602.828/mes\n' +
    '  Gastos financieros:         $7.885.643/mes\n' +
    '  Imposiciones + IVA + Ant.:  $71.000.000/mes\n' +
    '  ─────────────────────────────────────────\n' +
    '  TOTAL POLCHILE:          ~$199.282.408/mes\n' +
    '  Por semana (÷4):          ~$49.820.602/sem\n\n' +
    '⚠ Celdas en AMARILLO = pendiente M5 y CyS\n' +
    '  El dashboard lee la fila 44 (semanal) automáticamente.'
  );
}