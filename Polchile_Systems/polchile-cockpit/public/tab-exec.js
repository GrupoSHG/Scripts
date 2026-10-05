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
const fmtM        = (n, dec=1) => fmt(n, dec);
const fmtPct      = (n, dec=0) => (n>=0?'+':'') + fmt(n, dec) + '%';
const fmtPctSimple= (n, dec=0) => fmt(n, dec) + '%';

const Delta = ({ v, suffix='%' }) => {
  const cls   = v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
  const arrow = v > 0 ? '▲' : v < 0 ? '▼' : '–';
  return <span className={'delta ' + cls}>{arrow} {Math.abs(v).toFixed(1)}{suffix}</span>;
};

// ============================================================
// TOPBAR
// ============================================================
function Topbar({ tab, setTab, scenario, setScenario, userEmail, onLogout }) {
  const tabs = [
    { id:'exec',     label:'Resumen Ejecutivo' },
    { id:'daily',    label:'Operativa Diaria'  },
    { id:'team',     label:'Equipo Comercial'  },
    { id:'glosario', label:'Glosario y Fuentes'},
  ];
  const initials = (userEmail || '').split('@')[0].slice(0,2).toUpperCase();
  return (
    <div className="topbar">
      <div className="brand">
        <div className="brand-mark">P</div>
        <div className="brand-name">POLCHILE <span>Comercial Cockpit</span></div>
      </div>
      <div className="tabs">
        {tabs.map(t => (
          <button key={t.id} className={'tab '+(tab===t.id?'active':'')} onClick={() => setTab(t.id)}>
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
          <span>Manager · GHL</span>
          <span className="text-3">· En vivo</span>
        </div>
        <div className="user-chip">
          <div className="avatar">{initials}</div>
          <div>
            <div className="text-1 fw-6">{userEmail || 'Usuario'}</div>
            <div className="text-3 fs-10">Polchile SpA</div>
          </div>
        </div>
        <button className="logout-btn" onClick={onLogout}>Salir</button>
      </div>
    </div>
  );
}

// ============================================================
// RIBBON
// ============================================================
function Ribbon() {
  const fecha           = new Date();
  const diasSemana      = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
  const currentMonthIdx = fecha.getMonth();
  const txtHoy          = `${diasSemana[fecha.getDay()]} ${fecha.getDate()} ${window.PCH.MESES[currentMonthIdx]} ${fecha.getFullYear()}`;
  const totalDias       = new Date(fecha.getFullYear(), currentMonthIdx+1, 0).getDate();
  const avanceMes       = Math.round((fecha.getDate() / totalDias) * 100);
  const txtPeriodo      = `${window.PCH.MESES_LARGO[currentMonthIdx]} ${fecha.getFullYear()} · día ${fecha.getDate()} de ${totalDias}`;
  const isLoading       = window.PCH.REAL_YTD === undefined;
  const ytdFacturado    = isLoading ? 0 : window.PCH.REAL_YTD;
  const presupArray     = window.PCH.presupMensual('base');
  let   ytdPresupuesto  = 0;
  for (let i=0; i<=currentMonthIdx; i++) ytdPresupuesto += presupArray[i];
  const cumplYTD    = ytdPresupuesto > 0 ? (ytdFacturado / ytdPresupuesto) * 100 : 0;
  const badgeColor  = cumplYTD >= 100 ? 'green' : cumplYTD >= 85 ? 'amber' : 'red';
  return (
    <div className="ribbon">
      <div className="ribbon-item"><span className="label">Hoy:</span><span className="fw-6">{txtHoy}</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">Período:</span><span className="fw-6">{txtPeriodo}</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">Avance mes:</span><span className="fw-6">{avanceMes}%</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">YTD facturado:</span><span className="fw-6 mono">{isLoading ? '...' : fmtM(ytdFacturado)} M$</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">YTD presupuesto:</span><span className="fw-6 mono">{fmtM(ytdPresupuesto)} M$</span></div>
      <div className="ribbon-divider"></div>
      <div className="ribbon-item"><span className="label">Cumplimiento YTD:</span><span className={`badge ${badgeColor}`}>{fmtPctSimple(cumplYTD,1)}</span></div>
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
  const max   = Math.max(...data, 1);
  const min   = Math.min(...data, 0);
  const range = max - min || 1;
  const pts   = data.map((v,i) => [(i/(data.length-1))*width, height-((v-min)/range)*height]);
  const path  = pts.map((p,i) => (i===0?'M':'L')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const area  = path + ` L ${width} ${height} L 0 ${height} Z`;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{width:'100%',height}}>
      {fill && <path d={area} fill={color} fillOpacity={0.12}/>}
      <path d={path} fill="none" stroke={color} strokeWidth={1.5}/>
    </svg>
  );
}

// ============================================================
// KPI STRIP
// ============================================================
function KpiStrip() {
  const k        = window.PCH.KPI_MES;
  const mesIdx   = new Date().getMonth();
  const nombreMes= window.PCH.MESES_LARGO[mesIdx];
  const cumpl    = k.presupuesto > 0 ? k.facturado / k.presupuesto * 100 : 0;
  const cumplProy= k.presupuesto > 0 ? k.forecast_mes / k.presupuesto * 100 : 0;
  const diaHoy   = new Date().getDate();
  const diasHab  = Math.floor(diaHoy * (21/30));
  const diasRest = Math.max(1, 21 - diasHab);
  const runRateReq = Math.max(0, (k.presupuesto - k.facturado) / diasRest);
  return (
    <div className="kpi-strip">
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
        <div className="kpi-bar warn"><div style={{width:Math.min(cumpl,100)+'%'}}></div></div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">NV Emitidas MTD</div>
        <div className="kpi-value mono">{fmtM(k.nv)}<span className="unit">M$</span></div>
        <div className="kpi-meta"><span className="text-3">Backlog NV→Fact</span><span className="mono fw-6">{fmtM(k.backlog_nv)}M$</span></div>
        <div className="kpi-bar"><div style={{width:Math.min(k.presupuesto>0?k.nv/k.presupuesto*100:0,100)+'%'}}></div></div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">Cotizado MTD</div>
        <div className="kpi-value mono">{fmtM(k.cotizado)}<span className="unit">M$</span></div>
        <div className="kpi-meta"><span className="badge blue">Conv. {k.conv_cot_nv}%</span><span className="text-3">→ NV</span></div>
        <div className="kpi-bar"><div style={{width:'92%',background:'var(--info)'}}></div></div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">Forecast Cierre Mes</div>
        <div className="kpi-value mono">{fmtM(k.forecast_mes)}<span className="unit">M$</span></div>
        <div className="kpi-meta"><span className={`badge ${cumplProy>=100?'green':cumplProy>=85?'amber':'red'}`}>{fmtPctSimple(cumplProy)}</span><span className="text-3">proy.</span></div>
        <div className="kpi-bar bad"><div style={{width:Math.min(cumplProy,100)+'%'}}></div></div>
      </div>
      <div className="kpi-cell">
        <div className="kpi-label">Pipeline Ponderado</div>
        <div className="kpi-value mono">{fmtM(window.PCH.FORECAST_CRM_PONDERADO)}<span className="unit">M$</span></div>
        <div className="kpi-meta"><span className="text-3">Bruto</span><span className="mono fw-6">{fmtM(window.PCH.PIPELINE_CRM.reduce((a,e)=>a+e.monto,0))}M$</span></div>
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
  const totalNeto   = data.reduce((a,f) => a + f.monto, 0);
  const totalCto    = data.reduce((a,f) => a + (f.cto||0), 0);
  const margenTotal = totalNeto > 0 ? ((totalNeto-totalCto)/totalNeto*100) : 0;
  const mColorTotal = margenTotal>=40?'var(--positive)':margenTotal>=30?'var(--warn)':'var(--negative)';
  return (
    <table className="tbl" style={{fontSize:11}}>
      <thead><tr>
        <th>FAMILIA</th><th className="num">NETO M$</th><th className="num">COSTO M$</th>
        <th className="num">MARGEN M$</th><th className="num">MARGEN %</th>
        <th className="num">PRESUP. %</th><th className="num">Δ MARGEN</th><th className="num">% TOTAL</th>
      </tr></thead>
      <tbody>
        {data.map((f,i) => {
          const cto    = typeof f.cto         === 'number' ? f.cto         : 0;
          const margen = typeof f.margen       === 'number' ? f.margen       : 0;
          const presup = typeof f.margenPresup === 'number' ? f.margenPresup : 0;
          const delta  = presup > 0 ? margen - presup : null;
          const pct    = totalNeto > 0 ? (f.monto/totalNeto*100) : 0;
          const margenM= f.monto - cto;
          const mColor = margen>=40?'var(--positive)':margen>=30?'var(--warn)':'var(--negative)';
          return (
            <tr key={i}>
              <td className="fw-6" style={{maxWidth:200,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}} title={f.fam}>{f.fam}</td>
              <td className="num mono">{fmtM(f.monto)}</td>
              <td className="num mono text-3">{fmtM(cto)}</td>
              <td className="num mono fw-6" style={{color:mColor}}>{fmtM(margenM)}</td>
              <td className="num mono fw-6" style={{color:mColor}}>{margen.toFixed(1)}%</td>
              <td className="num mono text-3">{presup>0?presup.toFixed(1)+'%':'—'}</td>
              <td className="num mono">
                {delta!==null
                  ? <span style={{color:delta>=0?'var(--positive)':'var(--negative)'}}>{delta>=0?'+':''}{delta.toFixed(1)} pp</span>
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
          <td className="num mono fw-6" style={{color:mColorTotal}}>{fmtM(totalNeto-totalCto)}</td>
          <td className="num mono fw-6" style={{color:mColorTotal}}>{margenTotal.toFixed(1)}%</td>
          <td className="num mono text-3">—</td><td className="num mono text-3">—</td>
          <td className="num mono text-3">100.0%</td>
        </tr>
      </tfoot>
    </table>
  );
}

// ============================================================
// MONTHLY BARS
// ============================================================
function MonthlyBars() {
  const presup  = window.PCH.presupMensual('base');
  const real    = window.PCH.REAL_2026.facturado;
  const real25  = window.PCH.REAL_2025_FACTURADO;
  const mesActual = new Date().getMonth();
  return (
    <div>
      <svg viewBox="0 0 1200 220" style={{width:'100%',height:220,overflow:'visible'}}>
        {[0,0.25,0.5,0.75,1].map(g => (
          <g key={g}>
            <line x1={40} x2={1200} y1={20+(180*(1-g))} y2={20+(180*(1-g))} stroke="#1f2734" strokeDasharray="2,3"/>
            <text x={2} y={24+(180*(1-g))} fontSize="9" fill="#6c7689">{Math.round(700*g)}</text>
          </g>
        ))}
        {presup.map((p,i) => {
          const x   = 50 + i*96;
          const r26 = real[i]   || 0;
          const r25 = real25[i] || 0;
          const max = 700;
          const hP  = p/max*180; const hR = r26/max*180; const hY = r25/max*180;
          const isPast    = i < mesActual;
          const isCurrent = i === mesActual;
          return (
            <g key={i}>
              <rect x={x}    y={20+180-hY} width={20} height={hY} fill="#64748b" rx={2}/>
              <rect x={x+22} y={20+180-hP} width={20} height={hP} fill="#1e40af" rx={2}/>
              {(isPast||isCurrent) && <rect x={x+44} y={20+180-hR} width={20} height={hR} fill={isCurrent?'#f59e0b':'#3b82f6'} rx={2}/>}
              <text x={x+32} y={215} fontSize="10" fill="#aab3c2" textAnchor="middle">{window.PCH.MESES[i]}</text>
              {(isPast||isCurrent)&&r26>0&&<text x={x+32} y={20+180-Math.max(hR,hP)-4} fontSize="9" fill="#e6ebf2" textAnchor="middle" fontWeight="600">{Math.round(r26/p*100)}%</text>}
            </g>
          );
        })}
      </svg>
      <div className="flex gap-3 fs-11 mt-2" style={{justifyContent:'center'}}>
        <span><span style={{display:'inline-block',width:10,height:10,background:'#64748b',borderRadius:2,marginRight:4}}></span>Real 2025</span>
        <span><span style={{display:'inline-block',width:10,height:10,background:'#1e40af',borderRadius:2,marginRight:4}}></span>Presup. 2026</span>
        <span><span style={{display:'inline-block',width:10,height:10,background:'#3b82f6',borderRadius:2,marginRight:4}}></span>Real 2026</span>
        <span><span style={{display:'inline-block',width:10,height:10,background:'#f59e0b',borderRadius:2,marginRight:4}}></span>Mes actual</span>
      </div>
    </div>
  );
}

// ============================================================
// MIX PRODUCTOS
// ============================================================
function MixProductos() {
  const data = window.PCH.MIX_FAMILIA || [];
  if (!data.length) return <div className="card"><div className="text-center text-3 mt-4">Esperando datos...</div></div>;
  return (
    <div className="card">
      <div className="card-head"><div className="card-title uppercase">Mix de Productos · Margen Real vs Presupuestado</div></div>
      <table className="tbl" style={{fontSize:11}}>
        <thead><tr>
          <th>FAMILIA</th><th className="num">PRESUP. %</th><th className="num">REAL %</th>
          <th className="num">Δ PP</th><th>DISTRIB.</th>
          <th className="num">MRG REAL</th><th className="num">MRG PRESUP.</th><th className="num">Δ MRG</th>
        </tr></thead>
        <tbody>
          {data.map((r,i) => {
            const p_pct=typeof r.p_pct==='number'?r.p_pct:0;
            const r_pct=typeof r.r_pct==='number'?r.r_pct:0;
            const d_pp =typeof r.d_pp ==='number'?r.d_pp :0;
            const m_real=typeof r.m_real==='number'?r.m_real:0;
            const m_pre =typeof r.m_pre ==='number'?r.m_pre :0;
            const m_d   =typeof r.m_d   ==='number'?r.m_d   :0;
            return (
              <tr key={i}>
                <td className="fw-6" style={{maxWidth:120,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}} title={r.fam||'—'}>{r.fam||'—'}</td>
                <td className="num mono">{p_pct.toFixed(1)}%</td>
                <td className="num mono">{r_pct.toFixed(1)}%</td>
                <td className={'num mono '+(d_pp>0?'t-up':d_pp<0?'t-down':'')}>{d_pp>0?'+':''}{d_pp.toFixed(1)}</td>
                <td><div style={{width:60,height:4,background:'#1f2734',borderRadius:2,position:'relative'}}>
                  <div style={{position:'absolute',width:Math.min(100,p_pct*2)+'%',height:'100%',background:'#475569',borderRadius:2}}></div>
                  <div style={{position:'absolute',width:Math.min(100,r_pct*2)+'%',height:'100%',background:'#3b82f6',borderRadius:2,opacity:0.8}}></div>
                </div></td>
                <td className="num mono">{m_real.toFixed(1)}%</td>
                <td className="num mono">{m_pre.toFixed(1)}%</td>
                <td className={'num mono '+(m_d>0?'t-up':m_d<0?'t-down':'')}>{m_d>0?'+':''}{m_d.toFixed(1)} pp</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================
// TOP 10 CLIENTES
// ============================================================
function Top10Clientes() {
  const data = window.PCH.TOP_CLIENTES || [];
  if (!data.length) return <div className="card"><div className="text-center text-3 mt-4">Esperando datos...</div></div>;
  const concentracion = data.reduce((a,c) => a+(c.pct||0), 0);
  return (
    <div className="card">
      <div className="flex between mb-3"><div className="card-title uppercase">Top 10 Clientes YTD</div><div className="text-3 fs-10">Concentración Pareto</div></div>
      {data.map((c,i) => {
        const valor = typeof c.val==='number'?c.val:0;
        const pct   = typeof c.pct==='number'?c.pct:0;
        const nom   = c.n || 'Sin Razón Social';
        return (
          <div key={i} className="flex between center-y mb-2" style={{fontSize:11}}>
            <div className="flex center-y gap-2" style={{width:'60%'}}>
              <span className="text-3">#{i+1}</span>
              <span style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',maxWidth:180}} title={nom}>{nom}</span>
            </div>
            <div className="flex center-y gap-2" style={{width:'40%',justifyContent:'flex-end'}}>
              <span className="badge gray" style={{fontSize:9}}>{c.type||'REC'}</span>
              <div style={{width:40,height:4,background:'#1f2734',borderRadius:2}}>
                <div style={{width:(pct*2)+'%',height:'100%',background:'#3b82f6',borderRadius:2}}></div>
              </div>
              <span className="fw-6 mono" style={{width:35,textAlign:'right'}}>{valor.toFixed(1)}</span>
              <span className="text-3 mono" style={{width:30,textAlign:'right'}}>{pct.toFixed(1)}%</span>
            </div>
          </div>
        );
      })}
      <div className="mt-3 pt-2 flex between fw-6" style={{borderTop:'1px solid var(--border-soft)',fontSize:11}}>
        <span className="uppercase text-3">Top 10 % del total</span>
        <span>{concentracion.toFixed(1)}%</span>
      </div>
    </div>
  );
}

// ============================================================
// ALERTAS + COBRANZAS
// ============================================================
function Alertas() {
  return (
    <div>
      {window.PCH.ALERTAS.map((a,i) => (
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
  const backlog = window.PCH.BACKLOG_NV;
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
          <div className="mono fw-7 fs-16">{backlog!=null?fmtM(backlog):'...'} M$</div>
          <div className="text-3 fs-10">Vinculado a Manager</div>
        </div>
      </div>
      <div style={{paddingTop:8,borderTop:'1px solid var(--border-soft)'}}>
        <div className="text-3 fs-10 uppercase mb-2">Aging cobranzas</div>
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

// ============================================================
// TAB EJECUTIVO
// ============================================================
function ExecTab() {
  const isLoading = window.PCH.REAL_YTD === undefined;
  return (
    <>
      <KpiStrip/>
      <div className="section-title" style={{color:'var(--accent)'}}>Estado Operativo · Ventas Full Manager</div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:10,marginBottom:10}}>
        <div className="card" style={{borderLeft:'4px solid #22c55e'}}>
          <div className="card-head"><div className="card-title">Venta Facturada YTD (FAV−NCV)</div><span className="badge green">YTD Real</span></div>
          <div className="mono fw-7 fs-16 text-1">{isLoading?'Cargando...':fmtM(window.PCH.REAL_YTD)+' M$'}</div>
        </div>
        <div className="card" style={{borderLeft:'4px solid #6366f1'}}>
          <div className="card-head"><div className="card-title">Notas de Venta YTD</div><span className="badge blue">NV Emitidas</span></div>
          <div className="mono fw-7 fs-16 text-1">{isLoading?'Cargando...':fmtM(window.PCH.KPI_MES.nvYTD||0)+' M$'}</div>
        </div>
        <div className="card" style={{borderLeft:'4px solid #22c55e'}}>
          <div className="card-head"><div className="card-title">Margen Bruto Real YTD</div><span className="badge green">Costo Promedio</span></div>
          <div className="mono fw-7 fs-16 text-1">{isLoading?'Cargando...':fmtM(window.PCH.MARGEN_REAL||0)+' M$'}</div>
        </div>
      </div>

      <div className="card" style={{borderLeft:'4px solid #f59e0b',marginBottom:20}}>
        <div className="card-head">
          <div className="card-title uppercase">Venta por Familia · YTD (CLASE1 desde Manager)</div>
          <span className="badge amber">M$ CLP</span>
        </div>
        <FamiliasYTD/>
      </div>

      <div className="section-title">Cumplimiento mensual 2026 vs Presupuesto vs 2025</div>
      <div style={{marginBottom:20}}>
        <div className="card">
          <div className="card-head">
            <div><div className="card-title">Facturación mensual</div><div className="card-sub">Presupuesto vs Real 2026 vs Real 2025 — M$ CLP</div></div>
            <div className="seg"><button className="on">2026</button><button>YoY</button><button>YTD acum.</button></div>
          </div>
          <MonthlyBars/>
        </div>
      </div>

      <div style={{display:'grid',gridTemplateColumns:'2.5fr 1.5fr',gap:10,marginBottom:20}}>
        <MixProductos/>
        <Top10Clientes/>
      </div>

      <div className="section-title">Alertas · Cobranzas</div>
      <div style={{display:'grid',gridTemplateColumns:'1.5fr 1fr',gap:10}}>
        <div className="card">
          <div className="card-head"><div className="card-title">Alertas activas</div><span className="badge red">2 críticas</span></div>
          <Alertas/>
        </div>
        <div className="card">
          <div className="card-head"><div className="card-title">Cobranzas y Backlog</div></div>
          <Cobranzas/>
        </div>
      </div>
    </>
  );
}

// ── Exponer globales ───────────────────────────────────────
window.Topbar    = Topbar;
window.Ribbon    = Ribbon;
window.KpiStrip  = KpiStrip;
window.ExecTab   = ExecTab;
window.Sparkline = Sparkline;
window.Delta     = Delta;
window.fmtM      = fmtM;
window.fmt       = fmt;
window.fmtPct    = fmtPct;
window.fmtPctSimple = fmtPctSimple;
