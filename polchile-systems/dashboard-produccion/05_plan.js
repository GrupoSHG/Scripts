const PLAN_CONFIG = {
  cap:              { P1: 29.6, P2: 26.0, P3: 26.0, P4: 29.6, P5: 29.6, P6: 29.6, P7: 29.6 },
  purpPresses:      ['P1','P3','P4','P5'],
  allPresses:       ['P1','P2','P3','P4','P5','P6','P7'],
  purpUtilM:        10,
  purpCycleMin:     25,
  polpSetupMin:     15,
  jornadaH:         9,
  isoDoubleLoad:    true,
  workDays:         [1,2,3,4,5],
  sameGroupTolerance: 2,
  splitThresholdM2: 1000,
};

function getPlanPrensas() {
  try {
    // Supabase: tabla 'ordenes_de_produccion' (antes leía el Sheet
    // "Orden de Produccion" directo). Mismo patrón que getWipData().
    const filas = supabaseSelect_('ordenes_de_produccion');
    if (!filas.length) return { error: "Sin datos en ordenes_de_produccion" };

    // Índice de MEDIDAS REALES desde 'base_completo' (detalle línea por
    // línea de cada NV — mucho más confiable que parsear texto libre).
    // Cada línea de producto real (con código) puede tener, inmediatamente
    // después en la misma NV (linea_nv creciente), varias líneas "hijas"
    // sin código, cuya descripción es solo un largo (ej. "3.537mm") y cuyo
    // Q_solicitado es la cantidad exacta de piezas de ese largo — sin
    // necesidad de parsear texto con regex tipo "NN x N.NNNmm".
    const filasBase = supabaseSelect_('base_completo');

    // Detecta si una descripción es "solo una medida" (nada más que un
    // número + mm/m), a diferencia de descripciones con texto libre.
    function esLineaDeMedidaPura_(desc) {
      if (!desc) return null;
      const m = String(desc).trim().match(/^([\d.,]+)\s*(mm|m)$/i);
      if (!m) return null;
      const aNumeroChileno = (crudoOriginal) => {
        const crudo = crudoOriginal.trim();
        if (crudo.indexOf(',') !== -1) {
          return parseFloat(crudo.replace(/\./g, '').replace(',', '.'));
        }
        const partes = crudo.split('.');
        if (partes.length === 1) return parseFloat(crudo);
        const ultimaParte = partes[partes.length - 1];
        if (ultimaParte.length === 3) return parseFloat(partes.join(''));
        const enteroConMiles = partes.slice(0, -1).join('');
        return parseFloat(enteroConMiles + '.' + ultimaParte);
      };
      const numero = aNumeroChileno(m[1]);
      if (isNaN(numero)) return null;
      const unidad = m[2].toLowerCase();
      return unidad === 'mm' ? numero / 1000 : (numero > 15 ? numero / 1000 : numero);
    }

    // Agrupa por NV y ordena por linea_nv (la API no garantiza orden).
    const porNV = {};
    filasBase.forEach(function(f) {
      const nv = f.nota_de_venta ? f.nota_de_venta.toString() : "";
      if (!nv) return;
      if (!porNV[nv]) porNV[nv] = [];
      porNV[nv].push(f);
    });
    Object.keys(porNV).forEach(function(nv) {
      porNV[nv].sort(function(a, b) {
        return (parseFloat(a.linea_nv) || 0) - (parseFloat(b.linea_nv) || 0);
      });
    });

    // mlPorNVyCodigo[nv][codigo] = ML total sumado de las líneas de medida
    // que siguen inmediatamente a la línea "cabecera" de ese código.
    const mlPorNVyCodigo = {};
    Object.keys(porNV).forEach(function(nv) {
      const lineas = porNV[nv];
      let codigoActual = null;
      let acumulado = 0;

      function cerrarAcumulado() {
        if (codigoActual !== null && acumulado > 0) {
          if (!mlPorNVyCodigo[nv]) mlPorNVyCodigo[nv] = {};
          mlPorNVyCodigo[nv][codigoActual] = (mlPorNVyCodigo[nv][codigoActual] || 0) + acumulado;
        }
        acumulado = 0;
      }

      lineas.forEach(function(f) {
        const codigo = f.codigo_de_producto ? f.codigo_de_producto.toString().trim().toUpperCase() : "";
        const desc   = f['descripción'] || "";
        const qSol   = parseFloat(f['q_solicitado']) || 0;
        const largoM = esLineaDeMedidaPura_(desc);

        if (codigo) {
          // Nueva línea "cabecera" — cierra el acumulado anterior y empieza uno nuevo.
          cerrarAcumulado();
          codigoActual = codigo;
        } else if (largoM !== null && codigoActual !== null) {
          // Línea hija de medida pura: suma cantidad × largo.
          acumulado += qSol * largoM;
        }
      });
      cerrarAcumulado();
    });

    const OPS = [];
    filas.forEach(function(r) {
      const pend = parseFloat(r.cantidad_pendiente) || 0;
      if (pend <= 0) return;

      const codigo = r.codigo_producto ? r.codigo_producto.toString().toUpperCase() : "";
      const bodega = r.bodega_nombre_op ? r.bodega_nombre_op.toString().toUpperCase() : "";

      if (codigo.indexOf("PSA") > -1) return;
      if (codigo.indexOf("PA")  === -1) return;
      if (bodega.indexOf("TERMINADO") === -1 && bodega.indexOf("STOCK") === -1) return;

      const nombre = (r.nombre_producto || "").toString();
      if (!/^(PolP|PurP|Pur)/i.test(nombre)) return;

      const q         = /^Pur/i.test(nombre) ? 'PurP' : 'PolP';
      // 'ordenes_de_produccion' no trae una columna ESPESOR directa —
      // se parsea siempre desde el nombre del producto (igual que antes).
      const esp       = parseEspesorNombre(nombre);
      const ancho     = /a1150/.test(nombre) ? 1.15 : /a910/.test(nombre) ? 0.91 : 1.0;
      const pieles    = parsePielesNombre(nombre);
      const tipo      = parseTipoNombre(nombre, q, esp);
      const m2          = pend;
      const nvRaw       = r.nota_vta ? r.nota_vta.toString() : "";

      // ── Cálculo de ML, en orden de preferencia ──────────────────────
      // 1) Medidas parseables en las propias observaciones de la OP.
      // 2) Medidas de la primera OP PSA de la misma NV (si la propia OP
      //    no trae medidas). Si el panel es ISO con ambas pieles "Ban",
      //    se toma la MITAD del ML de esa PSA; en cualquier otro caso
      //    (PolP4, PolP1000, etc.) se toma el ML completo de la PSA.
      // 3) Cálculo de respaldo: cantidad_pendiente / ancho.
      const obsTexto     = r.observaciones || "";
      let   mlObs        = parsearMedidasObservaciones_(obsTexto);
      const mlDesdeObs    = mlObs !== null;
      let   mlDesdeBase   = false;

      // Prioridad 2: medidas reales desde 'base_completo' (misma NV +
      // mismo código de producto), en vez de parsear observaciones.
      if (mlObs === null && nvRaw && codigo) {
        const porCodigo = mlPorNVyCodigo[nvRaw];
        if (porCodigo && porCodigo[codigo] > 0) {
          mlObs = porCodigo[codigo];
          mlDesdeBase = true;
        }
      }

      // Las medidas en observaciones (propias o de la PSA) describen el
      // PEDIDO COMPLETO de esa NV, no lo que queda por producir. Hay que
      // prorratear por la fracción pendiente (cantidad_pendiente / cantidad_op)
      // antes de usarlas — si solo queda un 1% del pedido, el ML restante
      // debe ser ~1% del ML total descrito en observaciones.
      const qOpValor = parseFloat(r.cantidad_op) || pend;
      if (mlObs !== null && qOpValor > 0) {
        const fraccionPendiente = pend / qOpValor;
        mlObs = mlObs * fraccionPendiente;
      }

      const ml = mlObs !== null ? mlObs : (m2 / ancho);
      const nv        = nvRaw;
      const isStock   = !nv || nv === "0" || nv === "" || bodega.indexOf("STOCK") > -1;

      OPS.push({
        op:     r.num_op ? r.num_op.toString() : "-",
        nv:     isStock ? "STK" : nv,
        cliente: "", // 'ordenes_de_produccion' no trae cliente directo
        fent:   r.fechaent ? formatDatePlan(r.fechaent) : "",
        q, tipo, esp, pieles, m2, ml, mlDesdeObs, mlDesdeBase,
        qOp:   parseFloat(r.cantidad_op)        || pend,
        qTerm: parseFloat(r.cantidad_terminada) || 0,
        group: buildGroupKey(q, tipo, esp, pieles),
      });
    });

    if (OPS.length === 0) return { error: "No hay OPs PA pendientes" };

    const groups   = buildPlanGroups(OPS);
    const presses  = distributePlan(OPS, groups, PLAN_CONFIG);
    const maxH     = Math.max.apply(null, presses.map(p => p.totalH).concat([1]));
    const totalDays = Math.ceil(maxH / PLAN_CONFIG.jornadaH);
    const dayLabels = buildDayLabels(totalDays, PLAN_CONFIG.workDays);

    return { asOf: new Date().toISOString(), ops: OPS, groups, presses, config: PLAN_CONFIG, dayLabels };
  } catch(e) {
    return { error: "Error en getPlanPrensas: " + e.toString() };
  }
}

function buildPlanGroups(OPS) {
  const map = {};
  OPS.forEach(o => {
    if (!map[o.group]) {
      map[o.group] = { key: o.group, q: o.q, esp: o.esp, tipo: o.tipo.split(' ')[0],
                       pieles: o.pieles, items: [], totalMl: 0, totalM2: 0 };
    }
    map[o.group].items.push(o);
    map[o.group].totalMl += o.ml;
    map[o.group].totalM2 += o.m2;
  });
  const arr = [];
  for (const k in map) arr.push(map[k]);
  arr.sort((a, b) => b.totalMl - a.totalMl);
  return arr;
}

function distributePlan(OPS, groups, cfg) {
  const presses = cfg.allPresses.map(p => ({
    p, cap: cfg.cap[p], canPurp: cfg.purpPresses.indexOf(p) >= 0,
    groups: [], groupBuckets: {}, baseH: 0, extraH: 0, totalH: 0, days: 0, ml: 0, m2: 0, ops: 0,
  }));
  const purpEligible = presses.filter(p => p.canPurp);

  function pushToPress(p, g, op, portionMl, portionM2, isSplit) {
    const dl  = /ISO/.test(g.tipo) && cfg.isoDoubleLoad && g.esp <= 100;
    const effMl = dl ? portionMl / 2 : portionMl;
    const dur   = effMl / p.cap;
    let extraH = 0, cyc = 0;
    const needsSetup = !p.groupBuckets[g.key];
    if (op.q === 'PurP') { cyc = Math.ceil(portionMl / cfg.purpUtilM); extraH = (cyc * cfg.purpCycleMin) / 60; }
    if (needsSetup) {
      const bucket = { g: { key: g.key, q: g.q, tipo: g.tipo, esp: g.esp, pieles: g.pieles,
        items: [], assignedTo: p.p, baseH: 0,
        extraH: op.q === 'PurP' ? 0 : (cfg.polpSetupMin / 60),
        totalMl: 0, effectiveMl: 0, doubleLoad: dl, cycles: 0 } };
      p.groupBuckets[g.key] = bucket;
      p.groups.push(bucket.g);
      if (op.q !== 'PurP') p.extraH += cfg.polpSetupMin / 60;
    }
    const bk = p.groupBuckets[g.key].g;
    bk.items.push({ op: op.op, nv: op.nv, cliente: op.cliente, tipo: op.tipo, esp: op.esp,
      ml: portionMl, m2: portionM2, dur, cycles: cyc, extraH, isSplit, origMl: op.ml, origM2: op.m2 });
    bk.baseH += dur; bk.extraH += extraH; bk.totalMl += portionMl; bk.effectiveMl += effMl; bk.cycles += cyc;
    p.baseH += dur; p.extraH += extraH; p.totalH = p.baseH + p.extraH;
    p.ml += portionMl; p.m2 += portionM2;
    p.ops += isSplit ? (1 / (g._splitCount || 1)) : 1;
    p.days = p.totalH / cfg.jornadaH;
    g.baseH = (g.baseH || 0) + dur; g.extraH = (g.extraH || 0) + extraH;
  }

  function splitOp(op, g, pool) {
    const totalCap = pool.reduce((a, p) => a + p.cap, 0);
    g._splitCount = (g._splitCount || 0) + pool.length;
    let assigned = 0;
    pool.forEach((p, idx) => {
      const isLast    = idx === pool.length - 1;
      const portionMl = isLast ? (op.ml - assigned) : op.ml * (p.cap / totalCap);
      if (portionMl < 0.01) return;
      const portionM2 = op.m2 * (portionMl / op.ml);
      pushToPress(p, g, op, portionMl, portionM2, true);
      assigned += portionMl;
    });
  }

  function assignAtomic(op, g, pool) {
    const sorted   = pool.slice().sort((a, b) => a.totalH - b.totalH);
    const minH     = sorted[0].totalH;
    const sameGroup = sorted.filter(p => p.groupBuckets[g.key]);
    const chosen   = (sameGroup.length > 0 && (sameGroup[0].totalH - minH) <= cfg.sameGroupTolerance)
                     ? sameGroup[0] : sorted[0];
    pushToPress(chosen, g, op, op.ml, op.m2, false);
  }

  groups.forEach(g => {
    g.doubleLoad = /ISO/.test(g.tipo) && cfg.isoDoubleLoad && g.q === 'PolP' && g.esp <= 100;
    g.cycles = g.q === 'PurP' ? Math.ceil(g.totalMl / cfg.purpUtilM) : 0;
  });

  const bigPurp = [], smallPurp = [], bigPolp = [], smallPolp = [];
  groups.forEach(g => {
    g.items.forEach(it => {
      const entry = { it, g };
      if (it.m2 > cfg.splitThresholdM2) { (g.q === 'PurP' ? bigPurp : bigPolp).push(entry); }
      else { (g.q === 'PurP' ? smallPurp : smallPolp).push(entry); }
    });
  });

  bigPurp.sort((a,b)  => b.it.m2 - a.it.m2);
  bigPolp.sort((a,b)  => b.it.m2 - a.it.m2);
  bigPurp.forEach(o   => splitOp(o.it, o.g, purpEligible));
  bigPolp.forEach(o   => splitOp(o.it, o.g, presses));
  smallPurp.sort((a,b) => b.it.ml - a.it.ml);
  smallPolp.sort((a,b) => b.it.ml - a.it.ml);
  smallPurp.forEach(o => assignAtomic(o.it, o.g, purpEligible));
  smallPolp.forEach(o => assignAtomic(o.it, o.g, presses));

  presses.forEach(p => { p.ops = Math.round(p.ops); });

  const gp = {};
  presses.forEach(p => {
    Object.keys(p.groupBuckets).forEach(k => { if (!gp[k]) gp[k] = []; gp[k].push(p.p); });
  });
  groups.forEach(g => { g.splitAcross = gp[g.key] || []; });

  const opAssignment = {};
  presses.forEach(p => {
    Object.keys(p.groupBuckets).forEach(k => {
      p.groupBuckets[k].g.items.forEach(it => {
        if (!opAssignment[it.op]) opAssignment[it.op] = [];
        if (opAssignment[it.op].indexOf(p.p) === -1) opAssignment[it.op].push(p.p);
      });
    });
  });
  OPS.forEach(o => { o.assignedTo = opAssignment[o.op] || []; });

  return presses;
}

function buildDayLabels(nDays, workDays) {
  const labels   = [];
  const cursor   = new Date();
  cursor.setHours(0, 0, 0, 0);
  while (workDays.indexOf(cursor.getDay()) === -1) cursor.setDate(cursor.getDate() + 1);
  const weekdays = ['DOM','LUN','MAR','MIE','JUE','VIE','SAB'];
  for (let i = 0; i < nDays; i++) {
    const dd = cursor.getDate();
    const mm = cursor.getMonth() + 1;
    labels.push({
      label:   weekdays[cursor.getDay()] + ' ' + (dd < 10 ? '0'+dd : dd) + '/' + (mm < 10 ? '0'+mm : mm),
      iso:     Utilities.formatDate(cursor, "GMT-3", "yyyy-MM-dd"),
      weekday: cursor.getDay(),
    });
    do { cursor.setDate(cursor.getDate() + 1); } while (workDays.indexOf(cursor.getDay()) === -1);
  }
  return labels;
}

function buildGroupKey(q, tipo, esp, pieles) {
  const fam   = pieles.split(' | ').map(p => p.split(' ')[0]).join('-');
  const base  = q === 'PurP' ? 'PUR' : 'POLP';
  const isISO = /ISO/.test(tipo);
  const subM  = tipo.match(/(\d+)\s*e/);
  const sub   = isISO ? 'ISO' : (subM ? subM[1] : '4');
  return base + '-' + sub + '-' + fam + '-e' + esp;
}

function parseEspesorNombre(name) {
  const m = name.match(/e(\d+)/);
  return m ? parseInt(m[1], 10) : 0;
}

function parseTipoNombre(name, q, esp) {
  const m = name.match(/^(Pol|Pur)P(-ISO|\d+)/);
  if (!m) return q + ' e' + esp;
  const suff = m[2] === '-ISO' ? '-ISO' : m[2];
  return q + suff + ' e' + esp;
}

function parsePielesNombre(name) {
  const m = name.match(/s([A-Za-z0-9]+?)i([A-Za-z0-9]+)$/);
  if (!m) return '';
  return formatPiel(m[1]) + ' | ' + formatPiel(m[2]);
}

function formatPiel(s) {
  if (/FOIL/i.test(s)) return 'FOIL';
  if (/PPP/i.test(s))  return 'PPP';
  const mPc  = s.match(/^(PC\d+)/);
  const mBan = s.match(/^(Ban)/);
  const head = mPc ? mPc[1] : (mBan ? 'Ban' : 'Ban');
  const tail = s.slice(head.length).replace(/^\d{2,3}/, '');
  return (head + ' ' + (tail || '')).trim();
}

function formatDatePlan(d) {
  if (!d) return "";
  if (d instanceof Date) return Utilities.formatDate(d, "GMT-3", "yyyy-MM-dd");
  return d.toString();
}

/**
 * parsearMedidasObservaciones_
 * ============================
 * Extrae metros lineales (ML) totales desde el texto de observaciones
 * de una OP. Formato esperado: "NN x N.NNNmm" (cantidad x largo en mm),
 * pudiendo repetirse separado por "/".
 *
 * OJO formato chileno: el PUNTO es separador de MILES, no decimal.
 * "2.300mm" = 2300mm = 2,3 metros (no 2,3mm).
 *
 * Si el texto no matchea el patrón (ej. "Flejar 54ml Acero..." o
 * "Según Nota de Venta N° 14061 de..."), devuelve null — en ese caso
 * getPlanPrensas() usa el cálculo de respaldo (cantidad_pendiente / ancho),
 * igual que antes de esta integración.
 *
 * @param {string} texto  Contenido crudo de la columna "observaciones"
 * @return {number|null}  Metros lineales totales, o null si no matchea
 */
function parsearMedidasObservaciones_(texto) {
  if (!texto) return null;

  const txt = String(texto).trim();
  let totalML = 0;
  let encontroAlguna = false;

  // Formato chileno: punto = separador de miles, coma = decimal — PERO
  // solo cuando el punto realmente agrupa de a 3 dígitos (ej. "3.528" =
  // 3528). Si el último punto tiene 1 o 2 dígitos después (ej. "166.8"),
  // es un decimal real, no separador de miles.
  const aNumeroChileno = (crudoOriginal) => {
    const crudo = crudoOriginal.trim();
    if (crudo.indexOf(',') !== -1) {
      // Ya viene con coma decimal explícita → los puntos son de miles.
      return parseFloat(crudo.replace(/\./g, '').replace(',', '.'));
    }
    const partes = crudo.split('.');
    if (partes.length === 1) return parseFloat(crudo); // sin puntos
    const ultimaParte = partes[partes.length - 1];
    if (ultimaParte.length === 3) {
      // Todos los puntos son de miles (ej. "3.528" → 3528, "22.860" → 22860)
      return parseFloat(partes.join(''));
    }
    // El último punto es decimal (ej. "166.8" → 166.8). Si hubiera puntos
    // antes, esos sí serían de miles (ej. "1.234.5" → 1234.5).
    const enteroConMiles = partes.slice(0, -1).join('');
    return parseFloat(enteroConMiles + '.' + ultimaParte);
  };

  // ── Patrón 1: "NN x N.NNNmm" (cantidad x largo, con o sin "mm"/"m") ──
  // La cantidad también puede traer separador de miles (ej. "3.528 x ...").
  // Exige la unidad pegada al número para no chocar con el patrón 2.
  const regex1 = /([\d.,]+)\s*x\s*([\d.,]+)\s*(mm|m)\b/gi;
  let match1;
  while ((match1 = regex1.exec(txt)) !== null) {
    const cantidad = aNumeroChileno(match1[1]);
    const numero   = aNumeroChileno(match1[2]);
    const unidad   = match1[3].toLowerCase();
    if (isNaN(cantidad) || isNaN(numero)) continue;

    let largoMetros;
    if (unidad === 'mm') {
      largoMetros = numero / 1000;
    } else {
      largoMetros = numero > 15 ? numero / 1000 : numero;
    }

    totalML += cantidad * largoMetros;
    encontroAlguna = true;
  }

  // ── Patrón 2: "... = N.Nml" (total ya calculado por quien escribió la
  // observación, ej. "24 x 6.950 = 166.8ml"). Se suma directo, sin
  // recalcular, para no depender de que el "x ..." previo matchee patrón 1.
  const regex2 = /=\s*([\d.,]+)\s*ml\b/gi;
  let match2;
  while ((match2 = regex2.exec(txt)) !== null) {
    const numero = aNumeroChileno(match2[1]);
    if (isNaN(numero)) continue;
    totalML += numero;
    encontroAlguna = true;
  }

  return encontroAlguna ? Math.round(totalML * 100) / 100 : null;
}
