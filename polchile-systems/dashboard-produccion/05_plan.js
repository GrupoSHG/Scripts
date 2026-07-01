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
    const ss   = SpreadsheetApp.openById(ID_WIP);
    const hoja = ss.getSheetByName("Orden de Produccion");
    if (!hoja) return { error: "No se encontró 'Orden de Produccion'" };

    const data    = hoja.getDataRange().getValues();
    const headers = data[0].map(h => h.toString().replace(/[\r\n\s_]+/g, '').toUpperCase());
    const find = function() {
      for (var i = 0; i < arguments.length; i++) {
        var idx = headers.indexOf(arguments[i]);
        if (idx > -1) return idx;
      }
      return -1;
    };

    const cNV   = find("NOTAVTA");
    const cOP   = find("NUMOP");
    const cProd = find("NOMBREPRODUCTO");
    const cCod  = find("CODIGOPRODUCTO");
    const cBod  = find("BODEGANOMBREOP");
    const cPed  = find("CANTIDADOP","CANTIDADPEDIDA");
    const cTerm = find("CANTIDADTERMINADA");
    const cPend = find("CANTIDADPENDIENTE");
    const cEsp  = find("ESPESOR");
    const cCli  = find("CLIENTE");
    const cFent = find("FECHAENT");

    if (cPend === -1 || cCod === -1 || cBod === -1)
      return { error: "Faltan columnas básicas (CODIGO/BODEGA/PENDIENTE)" };

    const OPS = [];
    for (let i = 1; i < data.length; i++) {
      const pend = parseFloat(data[i][cPend]) || 0;
      if (pend <= 0) continue;

      const codigo = data[i][cCod] ? data[i][cCod].toString().toUpperCase() : "";
      const bodega = data[i][cBod] ? data[i][cBod].toString().toUpperCase() : "";

      if (codigo.indexOf("PSA") > -1) continue;
      if (codigo.indexOf("PA")  === -1) continue;
      if (bodega.indexOf("TERMINADO") === -1 && bodega.indexOf("STOCK") === -1) continue;

      const nombre = (data[i][cProd] || "").toString();
      if (!/^(PolP|PurP|Pur)/i.test(nombre)) continue;

      const q         = /^Pur/i.test(nombre) ? 'PurP' : 'PolP';
      const espCol    = cEsp > -1 ? parseInt(data[i][cEsp], 10) : 0;
      const espParsed = parseEspesorNombre(nombre);
      const esp       = espCol || espParsed;
      const ancho     = /a1150/.test(nombre) ? 1.15 : /a910/.test(nombre) ? 0.91 : 1.0;
      const pieles    = parsePielesNombre(nombre);
      const tipo      = parseTipoNombre(nombre, q, esp);
      const m2        = pend;
      const ml        = m2 / ancho;
      const nv        = data[i][cNV] ? data[i][cNV].toString() : "";
      const isStock   = !nv || nv === "0" || nv === "" || bodega.indexOf("STOCK") > -1;

      OPS.push({
        op:     data[i][cOP] ? data[i][cOP].toString() : "-",
        nv:     isStock ? "STK" : nv,
        cliente: cCli > -1 ? (data[i][cCli] || "") : "",
        fent:   cFent > -1 ? formatDatePlan(data[i][cFent]) : "",
        q, tipo, esp, pieles, m2, ml,
        qOp:   cPed  > -1 ? (parseFloat(data[i][cPed])  || pend) : pend,
        qTerm: cTerm > -1 ? (parseFloat(data[i][cTerm]) || 0)    : 0,
        group: buildGroupKey(q, tipo, esp, pieles),
      });
    }

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
    const dl  = /ISO/.test(g.tipo) && cfg.isoDoubleLoad;
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
    g.doubleLoad = /ISO/.test(g.tipo) && cfg.isoDoubleLoad && g.q === 'PolP';
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