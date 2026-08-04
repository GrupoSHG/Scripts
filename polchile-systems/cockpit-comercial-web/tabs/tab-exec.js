/* global React, ReactDOM */
const { useState, useMemo } = React;
const D = window.PCH;

// ============================================================
// HELPERS
// ============================================================
const fmt = (n, dec=0) => {
  if (n == null || isNaN(n)) return '—';
  return n.toLocaleString('es-CL', { minimumFractionDigits: dec, maximumFractionDigits: dec });
};
const fmtM = (n, dec=1) => fmt(n, dec);
const fmtPct = (n, dec=0) => (n>=0?'+':'') + fmt(n, dec) + '%';
const fmtPctSimple = (n, dec=0) => fmt(n, dec) + '%';

const Delta = ({ v, suffix='%' }) => {
  const cls = v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  const arrow = v > 0 ? '▲' : v < 0 ? '▼' : '–';
  return <span className={'delta ' + cls}>{arrow} {Math.abs(v).toFixed(1)}{suffix}</span>;
};

// ============================================================
// TOPBAR  — ahora acepta extraTabs para tabs adicionales
// ============================================================
function Topbar({ tab, setTab, scenario, setScenario, extraTabs = [] }) {
  const baseTabs = [
    { id: 'exec',     label: 'Resumen Ejecutivo'  },
    { id: 'daily',    label: 'Operativa Diaria'   },
    { id: 'team',     label: 'Equipo Comercial'   },
    { id: 'glosario', label: 'Glosario y Fuentes' },
  ];

  // Combinar: extras (Resumen, Chipax) PRIMERO, luego tabs base
  const allTabs = [
    ...extraTabs,
    ...baseTabs.filter(b => !extraTabs.some(e => e.id === b.id)),
  ];

  return (
    <div className="topbar">
      <div className="brand">
        <div className="brand-mark">P</div>
        <div className="brand-name">POLCHILE <span>Comercial Cockpit</span></div>
      </div>
      <div className="tabs">
        {allTabs.map(t => (
          <button
            key={t.id}
            className={'tab ' + (tab === t.id ? 'active' : '')}
            onClick={() => setTab(t.id)}
          >
            <span className="dot"></span>{t.label}
          </button>
        ))}
      </div>
      <div className="topbar-right">
        <div className="scenario-pill">
          {['pesimista','base','optimista'].map(s => (
            <button key={s} className={scenario===s?'active':''} onClick={() => setScenario(s)}>
              {s==='pesimista'?'PES -20%':s==='base'?'BASE':'OPT +20%'}
            </button>
          ))}
        </div>
        <div className="live-status">
          <span className="live-dot"></span>
          <span>Manager · GHL sincronizado</span>
          <span className="text-3">· En vivo</span>
        </div>
        <div className="user-chip">
          <div className="avatar">HP</div>
          <div>
            <div className="text-1 fw-6">Hugo P.</div>
            <div className="text-3 fs-10">CEO</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// RIBBON
// ============================================================
function Ribbon() {
  const fecha = new Date();
  const diasSemana = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
  const mesesCortos = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  const currentMonthIndex = fecha.getMonth();
  const txtHoy = `${diasSemana[fecha.getDay()]} ${fecha.getDate()} ${mesesCortos[currentMonthIndex]} ${fecha.getFullYear()}`;
  const totalDias = new Date(fecha.getFullYear(), currentMonthIndex + 1, 0).getDate();
  const diaActual = fecha.getDate();
  const avanceMes = Math.round((diaActual / totalDias) * 100);
  const txtPeriodo = `${D.MESES_LARGO[currentMonthIndex]} ${fecha.getFullYear()} · día ${diaActual} de ${totalDias}`;
  const isLoading = D.REAL_YTD === undefined;
  const ytdFacturado = isLoading ? 0 : D.REAL_YTD;
  const presupArray = D.presupMensual('base');
  let ytdPresupuesto = 0;
  for (let i = 0; i <= currentMonthIndex; i++) ytdPresupuesto += presupArray[i];
  const cumplYTD = ytdPresupuesto > 0 ? (ytdFacturado / ytdPresupuesto) * 100 : 0;
  const badgeColor = cumplYTD >= 100 ? 'green' : cumplYTD >= 85 ? 'amber' : 'red';
  return (
    <div className="ribbon">
      <div className="ribbon-item"><span className="label">Hoy:</span><span className="fw-6">{txtHoy}</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">Período:</span><span className="fw-6">{txtPeriodo}</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">Avance del mes:</span><span className="fw-6">{avanceMes}%</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">YTD facturado:</span><span className="fw-6 mono">${isLoading ? '...' : fmtM(ytdFacturado)} M$</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">YTD presupuesto:</span><span className="fw-6 mono">${fmtM(ytdPresupuesto)} M$</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">Cumplimiento YTD:</span><span className={`badge ${badgeColor}`}>{fmtPctSimple(cumplYTD, 1)}</span></div>
      <div style={{marginLeft:'auto'}} className="ribbon-item">
        <span className="status-dot sd-warn"></span>
        <span className="text-2">6 alertas activas</span>
      </div>
    </div>
  );
}

// ============================================================
// MINI SVG CHARTS
// ============================================================
function Sparkline({ data, color='#5b8cff', height=40, width=140, fill=true }) {
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const pts = data.map((v,i) => {
    const x = (i/(data.length-1)) * width;
    const y = height - ((v-min)/range) * height;
    return [x,y];
  });
  const path = pts.map((p,i)=> (i===0?'M':'L')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area = path + ` L ${width} ${height} L 0 ${height} Z`;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{width:'100%',height}}>
      {fill && <path d={area} fill={color} fillOpacity={0.12} />}
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

function DonutChart({ data, size=110, thickness=18 }) {
  const total = data.reduce((a,d)=>a+d.value,0);
  const r = size/2 - thickness/2;
  const cx = size/2, cy = size/2;
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1d2532" strokeWidth={thickness} />
      {data.map((d,i) => {
        const frac = d.value/total;
        const dash = 2*Math.PI*r;
        const offset = dash * (1 - acc);
        acc += frac;
        return (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={d.color}
            strokeWidth={thickness} strokeDasharray={`${dash*frac} ${dash}`}
            strokeDashoffset={offset} transform={`rotate(-90 ${cx} ${cy})`} strokeLinecap="butt"/>
        );
      })}
    </svg>
  );
}

// ============================================================
// KPI STRIP
// ============================================================
function KpiStrip() {
  const k = D.KPI_MES;
  const mesesLabels = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
  const mesActual = new Date().getMonth();
  const nombreMes = mesesLabels[mesActual];
  const cumpl = k.facturado / k.presupuesto * 100;
  const cumplNV   = k.presupuesto > 0 ? (k.nv / k.presupuesto) * 100 : 0;
  const cumplProy = (k.forecast_fact || k.forecast_mes || 0) / k.presupuesto * 100;
  const diaHoy = new Date().getDate();
  const diasHabilesPasados = Math.floor(diaHoy * (21/30));
  const diasRestantes = Math.max(1, 21 - diasHabilesPasados);
  const runRateReq = Math.max(0, (k.presupuesto - k.facturado) / diasRestantes);
  return (
    <div className="kpi-strip" style={{gridTemplateColumns:'repeat(8, 1fr)'}}>
      <div className="kpi-cell">
        <div className="kpi-label uppercase">Presupuesto {nombreMes}</div>
        <div className="kpi-value mono">{fmtM(k.presupuesto)}<span className="unit">M$</span></div>
        <div className="kpi-meta"><span className="text-3">Diario req.</span><span className="mono fw-6">{fmtM(runRateReq)}M$</span></div>
        <div className="kpi-bar"><div style={{width:'100%'}}></div></div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">Facturado MTD</div>
        <div className="kpi-value mono">{fmtM(k.facturado)}<span className="unit">M$</span></div>
        <div className="kpi-meta"><span className="badge amber">{fmtPctSimple(cumpl)}</span><span className="text-3">vs presup.</span></div>
        <div className="kpi-bar warn"><div style={{width: cumpl+'%'}}></div></div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">NV Emitidas MTD</div>
        <div className="kpi-value mono">{fmtM(k.nv)}<span className="unit">M$</span></div>
        <div className="kpi-meta">
          <span className={`badge ${cumplNV>=100?'green':cumplNV>=80?'amber':'red'}`}>{fmtPctSimple(cumplNV)}</span>
          <span className="text-3">vs presup.</span>
        </div>
        <div className={`kpi-bar ${cumplNV>=100?'good':cumplNV>=80?'warn':'bad'}`}>
          <div style={{width: Math.min(cumplNV,100)+'%'}}></div>
        </div>
        <div className="kpi-meta mt-1" style={{fontSize:9, color:'var(--text-3)'}}>
          <span>Backlog NV→Fact: {fmtM(k.backlog_nv)}M$</span>
        </div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">Cotizado MTD</div>
        <div className="kpi-value mono">{fmtM(k.cotizado)}<span className="unit">M$</span></div>
        <div className="kpi-meta"><span className="badge blue">Conv. {k.conv_cot_nv}%</span><span className="text-3">→ NV</span></div>
        <div className="kpi-bar"><div style={{width:'92%', background:'var(--info)'}}></div></div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">Forecast Facturación</div>
        <div className="kpi-value mono">{fmtM(k.forecast_fact || k.forecast_mes)}<span className="unit">M$</span></div>
        <div className="kpi-meta">
          <span className={`badge ${cumplProy>=100?'green':cumplProy>=80?'amber':'red'}`}>{fmtPctSimple(cumplProy)}</span>
          <span className="text-3">vs presup.</span>
        </div>
        <div className="kpi-bar bad"><div style={{width: Math.min(cumplProy,100)+'%'}}></div></div>
        <div className="kpi-meta mt-1" style={{fontSize:9, color:'var(--text-3)'}}>
          <span>FAV + NV×70% + Cot×24%</span>
        </div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">Forecast NV Cierre</div>
        <div className="kpi-value mono">{fmtM(k.forecast_nv || 0)}<span className="unit">M$</span></div>
        <div className="kpi-meta">
          <span className="badge blue">{fmtPctSimple((k.forecast_nv||0) / k.presupuesto * 100)}</span>
          <span className="text-3">vs presup.</span>
        </div>
        <div className="kpi-bar"><div style={{width: Math.min(((k.forecast_nv||0)/k.presupuesto*100),100)+'%', background:'var(--info)'}}></div></div>
        <div className="kpi-meta mt-1" style={{fontSize:9, color:'var(--text-3)'}}>
          <span>NV MTD + Cot×35%</span>
        </div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">Pipeline Ponderado</div>
        <div className="kpi-value mono">{fmtM(D.FORECAST_CRM_PONDERADO)}<span className="unit">M$</span></div>
        <div className="kpi-meta"><span className="text-3">Total bruto</span><span className="mono fw-6">{fmtM(D.PIPELINE_CRM.reduce((a,e)=>a+e.monto,0))}M$</span></div>
        <div className="kpi-bar good"><div style={{width:'78%'}}></div></div>
      </div>
    </div>
  );
}

// ============================================================
// FAMILIAS YTD
// ============================================================
function FamiliasYTD() {
  const data = window.PCH.FAMILIAS_MONTO_YTD || [];
  if (!data.length) return <div className="text-3 fs-11 mt-2">Sin datos de familias disponibles.</div>;
  const totalNeto  = data.reduce((a,f) => a + f.monto, 0);
  const totalCto   = data.reduce((a,f) => a + (f.cto || 0), 0);
  const margenTotal = totalNeto > 0 ? ((totalNeto - totalCto) / totalNeto * 100) : 0;
  const mColorTotal = margenTotal >= 40 ? 'var(--positive)' : margenTotal >= 30 ? 'var(--warn)' : 'var(--negative)';
  return (
    <table className="tbl" style={{fontSize:11}}>
      <thead>
        <tr>
          <th className="text-3">FAMILIA</th>
          <th className="num text-3">NETO M$</th>
          <th className="num text-3">COSTO M$</th>
          <th className="num text-3">MARGEN M$</th>
          <th className="num text-3">MARGEN %</th>
          <th className="num text-3">PRESUP. %</th>
          <th className="num text-3">Δ MARGEN</th>
          <th className="num text-3">% TOTAL</th>
        </tr>
      </thead>
      <tbody>
        {data.map((f,i) => {
          const cto    = typeof f.cto         === 'number' ? f.cto         : 0;
          const margen = typeof f.margen       === 'number' ? f.margen       : 0;
          const presup = typeof f.margenPresup === 'number' ? f.margenPresup : 0;
          const delta  = presup > 0 ? margen - presup : null;
          const pct    = totalNeto > 0 ? (f.monto / totalNeto * 100) : 0;
          const margenM = f.monto - cto;
          const mColor  = margen >= 40 ? 'var(--positive)' : margen >= 30 ? 'var(--warn)' : 'var(--negative)';
          return (
            <tr key={i}>
              <td className="fw-6" style={{maxWidth:200, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}} title={f.fam}>{f.fam}</td>
              <td className="num mono">{fmtM(f.monto)}</td>
              <td className="num mono text-3">{fmtM(cto)}</td>
              <td className="num mono fw-6" style={{color: mColor}}>{fmtM(margenM)}</td>
              <td className="num mono fw-6" style={{color: mColor}}>{margen.toFixed(1)}%</td>
              <td className="num mono text-3">{presup > 0 ? presup.toFixed(1)+'%' : '—'}</td>
              <td className="num mono">
                {delta !== null
                  ? <span style={{color: delta >= 0 ? 'var(--positive)' : 'var(--negative)'}}>{delta >= 0 ? '+' : ''}{delta.toFixed(1)} pp</span>
                  : <span className="text-3">—</span>}
              </td>
              <td className="num mono text-3">{pct.toFixed(1)}%</td>
            </tr>
          );
        })}
      </tbody>
      <tfoot>
        <tr className="total">
          <td>TOTAL</td>
          <td className="num mono">{fmtM(totalNeto)}</td>
          <td className="num mono">{fmtM(totalCto)}</td>
          <td className="num mono fw-6" style={{color: mColorTotal}}>{fmtM(totalNeto - totalCto)}</td>
          <td className="num mono fw-6" style={{color: mColorTotal}}>{margenTotal.toFixed(1)}%</td>
          <td className="num mono text-3">—</td>
          <td className="num mono text-3">—</td>
          <td className="num mono text-3">100.0%</td>
        </tr>
      </tfoot>
    </table>
  );
}

// ============================================================
// TAB 1: RESUMEN EJECUTIVO
// ============================================================
function ExecTab() {
  const isLoading = D.REAL_YTD === undefined;
  return (
    <>
      <KpiStrip />
      <div className="section-title" style={{color: 'var(--accent)'}}>Estado Operativo · Ventas Full Manager</div>
      <div style={{display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:10, marginBottom:10}}>
        <div className="card" style={{borderLeft: '4px solid #22c55e'}}>
          <div className="card-head"><div className="card-title">Venta Facturada YTD (FAV−NCV)</div><span className="badge green">YTD Real</span></div>
          <div className="mono fw-7 fs-16 text-1">{isLoading ? "Cargando..." : `${fmtM(D.REAL_YTD)} M$`}</div>
        </div>
        <div className="card" style={{borderLeft: '4px solid #6366f1'}}>
          <div className="card-head"><div className="card-title">Notas de Venta YTD</div><span className="badge blue">NV Emitidas</span></div>
          <div className="mono fw-7 fs-16 text-1">{isLoading ? "Cargando..." : `${fmtM(D.KPI_MES.nvYTD || 0)} M$`}</div>
        </div>
        <div className="card" style={{borderLeft: '4px solid #22c55e'}}>
          <div className="card-head"><div className="card-title">Margen Bruto Real YTD</div><span className="badge green">Costo Promedio</span></div>
          <div className="mono fw-7 fs-16 text-1">{isLoading ? "Cargando..." : `${fmtM(D.MARGEN_REAL)} M$`}</div>
        </div>
      </div>
      <CardFamiliasYTD />
      <div className="section-title">Cumplimiento mensual 2026 vs Presupuesto vs 2025</div>
      <div style={{ display: 'block', marginBottom: '20px' }}>
        <div className="card">
          <div className="card-head">
            <div>
              <div className="card-title">Facturación mensual</div>
              <div className="card-sub">Presupuesto vs Real 2026 vs Real 2025 — M$ CLP</div>
            </div>
            <div className="seg">
              <button className="on">2026</button><button>YoY</button><button>YTD acum.</button>
            </div>
          </div>
          <MonthlyBars />
        </div>
      </div>
      <div style={{display:'grid', gridTemplateColumns:'2.5fr 1.5fr', gap:10, marginBottom:20}}>
        <MixProductos />
        <Top10Clientes />
      </div>
      <div className="section-title">Alertas · Cobranzas</div>
      <div style={{display:'grid', gridTemplateColumns:'1.5fr 1fr', gap:10}}>
        <div className="card">
          <div className="card-head"><div className="card-title">Alertas activas (6)</div><span className="badge red">2 críticas</span></div>
          <Alertas />
        </div>
        <div className="card">
          <div className="card-head"><div className="card-title">Cobranzas y Backlog</div></div>
          <Cobranzas />
        </div>
      </div>
    </>
  );
}

function MonthlyBars() {
  const presup = D.presupMensual('base');
  const real   = D.REAL_2026.facturado;
  const real25 = D.REAL_2025_FACTURADO;

  // Mostrar 6 meses visibles; el contenedor ocupa el 100% del card padre
  const VISIBLE      = 6;
  const ALTO_GRAFICO = 360;     // más alto para TV
  const PAD_TOP      = 40;
  const PAD_BOT      = 50;
  const PAD_IZQ      = 60;
  const ALTO_BARRAS  = ALTO_GRAFICO - PAD_TOP - PAD_BOT;

  // Medir ancho real del contenedor para calcular ANCHO_MES dinámicamente
  const wrapRef   = React.useRef(null);
  const scrollRef = React.useRef(null);
  const [contWidth, setContWidth] = useState(1600);

  React.useEffect(() => {
    function medir() {
      if (wrapRef.current) {
        const w = wrapRef.current.clientWidth;
        if (w > 200) setContWidth(w);
      }
    }
    medir();
    window.addEventListener('resize', medir);
    return () => window.removeEventListener('resize', medir);
  }, []);

  // ANCHO_MES = (contenedor - padding izq) / 6 → cada mes ocupa 1/6 del ancho visible
  const ANCHO_MES = Math.max(120, Math.floor((contWidth - PAD_IZQ) / VISIBLE));
  const ANCHO_SVG = PAD_IZQ + 12 * ANCHO_MES;

  // Eje Y dinámico
  const maxData = Math.max(
    Math.max.apply(null, presup),
    Math.max.apply(null, real),
    Math.max.apply(null, real25),
    1
  );
  const maxY = Math.ceil(maxData / 100) * 100;

  // Posicionar scroll para que el mes actual quede al borde derecho de los 6 visibles
  React.useEffect(() => {
    if (scrollRef.current) {
      const mesActual = D.MES_ACTUAL || 5;
      const targetMes = Math.max(0, mesActual - VISIBLE + 1);
      scrollRef.current.scrollLeft = targetMes * ANCHO_MES;
    }
  }, [ANCHO_MES]);

  // Tamaño de barras y separación proporcional
  const W_BARRA = Math.floor(ANCHO_MES * 0.22);   // 22% del mes por barra
  const GAP     = Math.floor(ANCHO_MES * 0.025);  // 2.5% gap entre barras
  const OFFSET  = Math.floor((ANCHO_MES - (W_BARRA * 3 + GAP * 2)) / 2); // centrar grupo

  return (
    <div ref={wrapRef} style={{width:'100%'}}>
      <div
        ref={scrollRef}
        style={{
          width:'100%',
          overflowX:'scroll',
          overflowY:'hidden',
          paddingBottom:8,
        }}
      >
        <svg
          width={ANCHO_SVG}
          height={ALTO_GRAFICO}
          style={{display:'block'}}
        >
          {/* Líneas guía + labels eje Y */}
          {[0, 0.25, 0.5, 0.75, 1].map(g => (
            <g key={g}>
              <line
                x1={PAD_IZQ}
                x2={ANCHO_SVG}
                y1={PAD_TOP + ALTO_BARRAS * (1 - g)}
                y2={PAD_TOP + ALTO_BARRAS * (1 - g)}
                stroke="#1f2734"
                strokeDasharray="2,3"
              />
              <text
                x={PAD_IZQ - 8}
                y={PAD_TOP + 5 + ALTO_BARRAS * (1 - g)}
                fontSize="13"
                fill="#6c7689"
                textAnchor="end"
              >
                {Math.round(maxY * g)}
              </text>
            </g>
          ))}

          {presup.map((p, i) => {
            const xBase = PAD_IZQ + i * ANCHO_MES + OFFSET;
            const r26   = real[i]   || 0;
            const r25   = real25[i] || 0;

            const hP = (p   / maxY) * ALTO_BARRAS;
            const hR = (r26 / maxY) * ALTO_BARRAS;
            const hY = (r25 / maxY) * ALTO_BARRAS;

            const isPast    = i < D.MES_ACTUAL;
            const isCurrent = i === D.MES_ACTUAL;
            const mostrarReal26 = isPast || isCurrent;

            const yBase = PAD_TOP + ALTO_BARRAS;

            const x25 = xBase;
            const xP  = xBase + W_BARRA + GAP;
            const x26 = xBase + (W_BARRA + GAP) * 2;

            return (
              <g key={i}>
                {/* Real 2025 */}
                <rect
                  x={x25}
                  y={yBase - hY}
                  width={W_BARRA}
                  height={hY}
                  fill="#64748b"
                  rx={3}
                />
                {r25 > 0 && (
                  <text
                    x={x25 + W_BARRA/2}
                    y={yBase - hY - 6}
                    fontSize="14"
                    fill="#cbd5e1"
                    textAnchor="middle"
                    fontWeight="600"
                  >
                    {Math.round(r25)}
                  </text>
                )}

                {/* Presupuesto 2026 */}
                <rect
                  x={xP}
                  y={yBase - hP}
                  width={W_BARRA}
                  height={hP}
                  fill="#1e40af"
                  rx={3}
                />
                {p > 0 && (
                  <text
                    x={xP + W_BARRA/2}
                    y={yBase - hP - 6}
                    fontSize="14"
                    fill="#93c5fd"
                    textAnchor="middle"
                    fontWeight="600"
                  >
                    {Math.round(p)}
                  </text>
                )}

                {/* Real 2026 */}
                {mostrarReal26 && (
                  <>
                    <rect
                      x={x26}
                      y={yBase - hR}
                      width={W_BARRA}
                      height={hR}
                      fill={isCurrent ? '#f59e0b' : '#3b82f6'}
                      rx={3}
                    />
                    {r26 > 0 && (
                      <text
                        x={x26 + W_BARRA/2}
                        y={yBase - hR - 6}
                        fontSize="14"
                        fill={isCurrent ? '#fbbf24' : '#e6ebf2'}
                        textAnchor="middle"
                        fontWeight="700"
                      >
                        {Math.round(r26)}
                      </text>
                    )}
                  </>
                )}

                {/* % cumplimiento sobre el grupo */}
                {mostrarReal26 && r26 > 0 && p > 0 && (
                  <text
                    x={xBase + (W_BARRA*3 + GAP*2)/2}
                    y={yBase - Math.max(hR, hP) - 28}
                    fontSize="15"
                    fill={isCurrent ? '#fbbf24' : '#22c55e'}
                    textAnchor="middle"
                    fontWeight="700"
                  >
                    {Math.round(r26/p*100)}%
                  </text>
                )}

                {/* Nombre del mes */}
                <text
                  x={xBase + (W_BARRA*3 + GAP*2)/2}
                  y={yBase + 28}
                  fontSize="16"
                  fill={isCurrent ? '#f59e0b' : '#aab3c2'}
                  textAnchor="middle"
                  fontWeight={isCurrent ? '700' : '500'}
                >
                  {D.MESES[i]}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Hint scroll */}
      <div className="text-3 fs-11 mt-1" style={{textAlign:'center'}}>
        ← Desliza para ver todos los meses →
      </div>

      <div className="flex gap-3 fs-12 mt-2" style={{justifyContent:'center', flexWrap:'wrap'}}>
        <span><span style={{display:'inline-block',width:12,height:12,background:'#64748b',borderRadius:2,marginRight:6}}></span>Real 2025</span>
        <span><span style={{display:'inline-block',width:12,height:12,background:'#1e40af',borderRadius:2,marginRight:6}}></span>Presup. 2026</span>
        <span><span style={{display:'inline-block',width:12,height:12,background:'#3b82f6',borderRadius:2,marginRight:6}}></span>Real 2026</span>
        <span><span style={{display:'inline-block',width:12,height:12,background:'#f59e0b',borderRadius:2,marginRight:6}}></span>Mes actual</span>
      </div>
    </div>
  );
}

// ============================================================
// CARD COLAPSABLE: Venta por Familia YTD
// ============================================================
function CardFamiliasYTD() {
  const [abierto, setAbierto] = useState(true);
  return (
    <div className="card" style={{borderLeft: '4px solid #f59e0b', marginBottom: 20}}>
      <div
        className="card-head"
        style={{cursor: 'pointer', userSelect: 'none'}}
        onClick={() => setAbierto(a => !a)}
      >
        <div className="card-title uppercase" style={{display:'flex', alignItems:'center', gap:8}}>
          <span style={{
            display:'inline-block',
            transform: abierto ? 'rotate(90deg)' : 'rotate(0deg)',
            transition:'transform 0.2s',
            fontSize:14,
            color:'#f59e0b',
          }}>▶</span>
          Venta por Familia · YTD (CLASE1 desde Manager)
        </div>
        <span className="badge amber">M$ CLP</span>
      </div>
      {abierto && (
        <div style={{overflowX: 'auto'}}>
          <FamiliasYTD />
        </div>
      )}
    </div>
  );
}

function MixProductos() {
  const data = window.PCH.MIX_FAMILIA || [];
  if (data.length === 0) return <div className="card"><div className="text-center text-3 mt-4">Esperando datos de productos...</div></div>;
  return (
    <div className="card">
      <div className="card-head"><div className="card-title uppercase">Mix de Productos · Margen Real vs Presupuestado</div></div>
      <table className="tbl" style={{fontSize: 11}}>
        <thead>
          <tr>
            <th className="text-3">FAMILIA / CLASE</th>
            <th className="num text-3">PRESUP. %</th>
            <th className="num text-3">REAL %</th>
            <th className="num text-3">Δ PP</th>
            <th className="text-3">DISTRIBUCIÓN</th>
            <th className="num text-3">MARGEN REAL</th>
            <th className="num text-3">MARGEN PRESUP.</th>
            <th className="num text-3">Δ MARGEN</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r,i) => {
            const p_pct  = typeof r.p_pct  === 'number' ? r.p_pct  : 0;
            const r_pct  = typeof r.r_pct  === 'number' ? r.r_pct  : 0;
            const d_pp   = typeof r.d_pp   === 'number' ? r.d_pp   : 0;
            const m_real = typeof r.m_real === 'number' ? r.m_real : 0;
            const m_pre  = typeof r.m_pre  === 'number' ? r.m_pre  : 0;
            const m_d    = typeof r.m_d    === 'number' ? r.m_d    : 0;
            return (
              <tr key={i}>
                <td className="fw-6" style={{maxWidth:'120px',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}} title={r.fam||'—'}>{r.fam||'—'}</td>
                <td className="num mono">{p_pct.toFixed(1)}%</td>
                <td className="num mono">{r_pct.toFixed(1)}%</td>
                <td className={"num mono "+(d_pp>0?'t-up':d_pp<0?'t-down':'')}>{d_pp>0?'+':''}{d_pp.toFixed(1)}</td>
                <td>
                  <div style={{width:60,height:4,background:'#1f2734',borderRadius:2,position:'relative'}}>
                    <div style={{position:'absolute',width:Math.min(100,p_pct*2)+'%',height:'100%',background:'#475569',borderRadius:2}}></div>
                    <div style={{position:'absolute',width:Math.min(100,r_pct*2)+'%',height:'100%',background:'#3b82f6',borderRadius:2,opacity:0.8}}></div>
                  </div>
                </td>
                <td className="num mono">{m_real.toFixed(1)}%</td>
                <td className="num mono">{m_pre.toFixed(1)}%</td>
                <td className={"num mono "+(m_d>0?'t-up':m_d<0?'t-down':'')}>{m_d>0?'+':''}{m_d.toFixed(1)} pp</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Top10Clientes() {
  const data = window.PCH.TOP_CLIENTES || [];
  if (data.length === 0) return <div className="card"><div className="text-center text-3 mt-4">Esperando datos de clientes...</div></div>;
  const concentracionTotal = data.reduce((acc,c) => acc+(c.pct||0), 0);
  return (
    <div className="card">
      <div className="flex between mb-3"><div className="card-title uppercase">Top 10 Clientes YTD</div><div className="text-3 fs-10">Concentración Pareto</div></div>
      {data.map((c,i) => {
        const valor = typeof c.val === 'number' ? c.val : 0;
        const porcentaje = typeof c.pct === 'number' ? c.pct : 0;
        const nombreCli = c.n || 'Sin Razón Social';
        return (
          <div key={i} className="flex between center-y mb-2" style={{fontSize:11}}>
            <div className="flex center-y gap-2" style={{width:'60%'}}>
              <span className="text-3">#{i+1}</span>
              <span className="uppercase" style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:180}} title={nombreCli}>{nombreCli}</span>
            </div>
            <div className="flex center-y gap-2 justify-end" style={{width:'40%'}}>
              <span className="badge gray" style={{fontSize:9}}>{c.type||'REC'}</span>
              <div style={{width:40,height:4,background:'#1f2734',borderRadius:2}}>
                <div style={{width:(porcentaje*2)+'%',height:'100%',background:'#3b82f6',borderRadius:2}}></div>
              </div>
              <span className="fw-6 mono" style={{width:35,textAlign:'right'}}>{valor.toFixed(1)}</span>
              <span className="text-3 mono" style={{width:30,textAlign:'right'}}>{porcentaje.toFixed(1)}%</span>
            </div>
          </div>
        );
      })}
      <div className="mt-3 pt-2 flex between fw-6" style={{borderTop:'1px solid var(--border-soft)',fontSize:11}}>
        <span className="uppercase text-3">Top 10 % Del Total</span>
        <span>{concentracionTotal.toFixed(1)}%</span>
      </div>
    </div>
  );
}

function Alertas() {
  return (
    <div>
      {D.ALERTAS.map((a,i) => (
        <div key={i} className={'alert-item '+a.tipo}>
          <div className="alert-icon">{a.icon}</div>
          <div>
            <div className="alert-text fs-12">{a.texto}</div>
            <div className="alert-action mt-1">→ {a.accion}</div>
          </div>
          <button className="icon-btn">→</button>
        </div>
      ))}
    </div>
  );
}

function Cobranzas() {
  const isLoading = D.BACKLOG_NV === undefined;
  return (
    <div>
      <div className="flex gap-3 mb-3">
        <div style={{flex:1}}>
          <div className="text-3 fs-10 uppercase">DSO actual</div>
          <div className="mono fw-7 fs-16 t-warn">47 días</div>
          <div className="text-3 fs-10">objetivo: 35</div>
        </div>
        <div style={{flex:1}}>
          <div className="text-3 fs-10 uppercase">Backlog NV→Fact</div>
          <div className="mono fw-7 fs-16">{isLoading ? '...' : fmtM(D.BACKLOG_NV)} M$</div>
          <div className="text-3 fs-10">Vinculado a Manager</div>
        </div>
      </div>
      <div style={{paddingTop:8, borderTop:'1px solid var(--border-soft)'}}>
        <div className="text-3 fs-10 uppercase mb-2">Cuentas por cobrar (aging)</div>
        <table className="tbl" style={{fontSize:11}}>
          <tbody>
            <tr><td>Por vencer</td><td className="num mono">412,3</td><td className="num"><span className="badge green">62%</span></td></tr>
            <tr><td>1–30 días</td><td className="num mono">148,7</td><td className="num"><span className="badge blue">22%</span></td></tr>
            <tr><td>31–60 días</td><td className="num mono">68,1</td><td className="num"><span className="badge amber">10%</span></td></tr>
            <tr><td>61–90 días</td><td className="num mono">28,4</td><td className="num"><span className="badge amber">4%</span></td></tr>
            <tr><td>&gt;90 días</td><td className="num mono">14,2</td><td className="num"><span className="badge red">2%</span></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TabGlosario() {
  const terminos = [
    { t:'MTD (Month-To-Date)', d:'Todo lo generado desde el día 1 del mes actual hasta hoy.' },
    { t:'YTD (Year-To-Date)', d:'Suma acumulada desde el 1 de enero del año en curso hasta hoy.' },
    { t:'Forecast Cierre Mes', d:'Proyección: Facturado MTD + NV del mes + (Cotizaciones vivas × 24%).' },
    { t:'Backlog NV', d:'NV emitidas en el CRM aún no entregadas ni facturadas en Manager.' },
    { t:'Pipeline Ponderado', d:'Monto de cotizaciones × probabilidad de cierre.' },
    { t:'FAV', d:'Factura de Venta — documento tributario en Manager ERP.' },
    { t:'NCV', d:'Nota de Crédito de Venta — reversa sobre una FAV.' },
  ];
  return (
    <div style={{padding:20, color:'#cbd5e1'}}>
      <h2 style={{fontSize:'1.4rem', color:'#fff', marginBottom:20}}>📚 Glosario de Términos Comerciales</h2>
      <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(300px, 1fr))', gap:16}}>
        {terminos.map((x,i) => (
          <div key={i} className="card" style={{padding:18}}>
            <strong style={{color:'#38bdf8', fontSize:'1rem', display:'block', marginBottom:8}}>{x.t}</strong>
            {x.d}
          </div>
        ))}
      </div>
    </div>
  );
}

window.ExecTab       = ExecTab;
window.Topbar        = Topbar;
window.Ribbon        = Ribbon;
window.KpiStrip      = KpiStrip;
window.Sparkline     = Sparkline;
window.Delta         = Delta;
window.TabGlosario   = TabGlosario;
window.FamiliasYTD   = FamiliasYTD;
window.fmtM          = fmtM;
window.fmt           = fmt;
window.fmtPct        = fmtPct;
window.fmtPctSimple  = fmtPctSimple;
