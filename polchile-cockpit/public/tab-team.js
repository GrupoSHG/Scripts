/* global React */
const D3 = window.PCH;

// ============================================================
// TAB 3: EQUIPO COMERCIAL
// ============================================================
function TeamTab() {
  const mesActual = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'][new Date().getMonth()];
  return (
    <>
      <window.KpiStrip/>

      <div className="section-title">Ranking del equipo · Cumplimiento individual {mesActual} MTD</div>
      <div className="card tight"><RankingTable/></div>

      <div className="section-title">Detalle por vendedor</div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:10}}>
        {D3.VENDEDORES.map(v => <VendedorCard key={v.id} v={v}/>)}
      </div>

      <div className="section-title">Estructura de costos del equipo · {mesActual} 2026</div>
      <div style={{display:'grid',gridTemplateColumns:'1.4fr 1fr 1fr',gap:10}}>
        <div className="card"><div className="card-head"><div className="card-title">Costos del depto. comercial</div><div className="card-sub">Mensual</div></div><CostosTable/></div>
        <div className="card"><div className="card-head"><div className="card-title">Ahorro Gerencia Comercial</div><span className="badge green">Activo</span></div><AhorroGerencia/></div>
        <div className="card"><div className="card-head"><div className="card-title">Bono Jefe de Ventas</div><span className="badge blue">3 meses</span></div><BonoCB/></div>
      </div>

      <div className="section-title">Productividad y conversión · Por vendedor</div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
        <div className="card"><div className="card-head"><div className="card-title">Win rate, ciclo y ticket promedio</div></div><ProductividadTable/></div>
        <div className="card"><div className="card-head"><div className="card-title">Mix de cartera por vendedor</div></div><MixVendedor/></div>
      </div>
    </>
  );
}

// ============================================================
// RANKING TABLE
// ============================================================
function RankingTable() {
  const activos = D3.VENDEDORES.filter(v => v.activo);
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>#</th><th>Vendedor</th><th>Cargo</th>
          <th className="num">Meta M$</th><th className="num">Cotizado MTD</th>
          <th className="num">NV MTD</th><th className="num">Facturado MTD</th>
          <th>Cumpl. MTD</th><th className="num">Comisión proy.</th>
        </tr>
      </thead>
      <tbody>
        {activos.map((v,i) => {
          const facturado = v.real?(v.real.facturado||0):0;
          const nv        = v.real?(v.real.nv       ||0):0;
          const cotizado  = v.real?(v.real.cotizado ||0):0;
          const meta      = v.metaMensual||0;
          const cumpl     = meta>0?(facturado/meta*100):null;
          const comision  = facturado*((v.comision||0)/100);
          return (
            <tr key={v.id}>
              <td className="text-3 mono">{i+1}</td>
              <td className="strong">
                <span className="flex center-y gap-2">
                  <span style={{display:'inline-flex',alignItems:'center',justifyContent:'center',
                    width:22,height:22,fontSize:9,borderRadius:'50%',fontWeight:700,color:'white',
                    background:v.color||'#475569'}}>{v.avatar}</span>
                  {v.nombre}
                </span>
              </td>
              <td className="text-2 fs-11">{v.cargo}</td>
              <td className="num mono">{meta||'—'}</td>
              <td className="num mono">{cotizado>0?cotizado.toFixed(1):'—'}</td>
              <td className="num mono">{nv>0?nv.toFixed(1):'—'}</td>
              <td className="num mono strong">{facturado>0?facturado.toFixed(1):'—'}</td>
              <td>
                {cumpl!==null?(
                  <div className="flex center-y gap-2">
                    <div className="mini-bar" style={{width:80}}>
                      <div style={{width:Math.min(cumpl,100)+'%',
                        background:cumpl>=100?'var(--positive)':cumpl>=80?'var(--accent)':cumpl>=60?'var(--warn)':'var(--negative)'}}></div>
                    </div>
                    <span className="mono fw-6 fs-11">{cumpl.toFixed(0)}%</span>
                  </div>
                ):<span className="text-3 fs-11">Sin meta directa</span>}
              </td>
              <td className="num mono">{comision>0?comision.toFixed(2)+' M$':'—'}</td>
            </tr>
          );
        })}
        <tr className="total">
          <td colSpan={3}>TOTAL EQUIPO ACTIVO</td>
          <td className="num mono">{activos.reduce((a,v)=>a+(v.metaMensual||0),0)}</td>
          <td className="num mono">{activos.reduce((a,v)=>a+(v.real?.cotizado||0),0).toFixed(1)}</td>
          <td className="num mono">{activos.reduce((a,v)=>a+(v.real?.nv||0),0).toFixed(1)}</td>
          <td className="num mono">{activos.reduce((a,v)=>a+(v.real?.facturado||0),0).toFixed(1)}</td>
          <td colSpan={2}></td>
        </tr>
      </tbody>
    </table>
  );
}

// ============================================================
// VENDEDOR CARD
// ============================================================
function VendedorCard({ v }) {
  if (v.vacante) {
    return (
      <div className="vendedor-card vacante">
        <div className="vendedor-head">
          <div className="v-avatar" style={{background:'#475569',color:'#aab3c2'}}>?</div>
          <div className="v-info"><div className="v-name">{v.nombre}</div><div className="v-cargo">{v.cargo}</div></div>
        </div>
        <div className="text-3 fs-11 mb-2">Posición vacante</div>
        <div className="flex between fs-11">
          <span className="text-3">Meta proyectada</span>
          <span className="mono fw-6">{v.metaMensual} M$</span>
        </div>
        <div className="text-center mt-3"><span className="badge amber">En búsqueda</span></div>
      </div>
    );
  }
  const facturado = v.real?(v.real.facturado||0):0;
  const nv        = v.real?(v.real.nv       ||0):0;
  const cotizado  = v.real?(v.real.cotizado ||0):0;
  const meta      = v.metaMensual||0;
  const cumpl     = meta>0?(facturado/meta*100):null;
  return (
    <div className="vendedor-card">
      <div className="vendedor-head">
        <div className="v-avatar" style={{background:v.color}}>{v.avatar}</div>
        <div className="v-info"><div className="v-name">{v.nombre}</div><div className="v-cargo">{v.cargo}</div></div>
        <span className="status-dot sd-good"></span>
      </div>
      {cumpl!==null?(
        <>
          <div className="flex between fs-10 text-3 mb-1">
            <span>Cumplimiento MTD</span>
            <span className="mono fw-6 text-1">{cumpl.toFixed(0)}%</span>
          </div>
          <div className="mini-bar mb-2">
            <div style={{width:Math.min(cumpl,100)+'%',
              background:cumpl>=100?'var(--positive)':cumpl>=80?'var(--accent)':'var(--warn)'}}></div>
          </div>
        </>
      ):<div className="text-3 fs-11 mb-2">Sin meta directa · gestión de equipo</div>}
      <table className="tbl" style={{fontSize:11}}>
        <tbody>
          <tr><td className="text-3">Meta mes</td><td className="num mono">{meta||'—'} M$</td></tr>
          <tr><td className="text-3">Cotizado MTD</td><td className="num mono">{cotizado>0?cotizado.toFixed(1):'—'} M$</td></tr>
          <tr><td className="text-3">NV emitidas MTD</td><td className="num mono">{nv>0?nv.toFixed(1):'—'} M$</td></tr>
          <tr><td className="text-3">Facturado MTD</td><td className="num mono strong">{facturado>0?facturado.toFixed(1):'—'} M$</td></tr>
          <tr><td className="text-3">Sueldo fijo</td><td className="num mono">{v.sueldoFijo||'—'} M$</td></tr>
          <tr><td className="text-3">Comisión</td><td className="num mono">{v.comision||'—'}%</td></tr>
          {v.bonoExtra&&<tr><td className="text-3">Bono extra</td><td className="num mono t-up">+{v.bonoExtra} M$</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================
// COSTOS TABLE
// ============================================================
function CostosTable() {
  const c = D3.COSTOS_MES;
  return (
    <table className="tbl">
      <thead><tr><th>Concepto</th><th className="num">Mensual</th><th className="num">Anual proy.</th><th>%</th></tr></thead>
      <tbody>
        <tr><td className="strong">Sueldos fijos</td><td className="num mono">{c.remuneraciones_fijo}</td><td className="num mono text-2">205,5</td><td><div className="mini-bar"><div style={{width:'63%',background:'var(--accent)'}}></div></div></td></tr>
        <tr><td>Comisiones (proy.)</td><td className="num mono">{c.comisiones}</td><td className="num mono text-2">66,7</td><td><div className="mini-bar"><div style={{width:'17%',background:'var(--info)'}}></div></div></td></tr>
        <tr><td>Bono Cristóbal Bretón</td><td className="num mono">{c.bono_cb}</td><td className="num mono text-2">4,2</td><td><div className="mini-bar"><div style={{width:'1%',background:'var(--purple)'}}></div></div></td></tr>
        <tr><td>Marketing Digital</td><td className="num mono">{c.marketing}</td><td className="num mono text-2">66,9</td><td><div className="mini-bar"><div style={{width:'19%',background:'var(--warn)'}}></div></div></td></tr>
        <tr><td>Gastos representación</td><td className="num mono">{c.representacion}</td><td className="num mono text-2">1,8</td><td></td></tr>
        <tr><td>Suscripciones</td><td className="num mono">{c.suscripciones}</td><td className="num mono text-2">0,7</td><td></td></tr>
        <tr className="total">
          <td>Costo total comercial</td><td className="num mono">{c.total}</td><td className="num mono">345,8</td>
          <td><span className="badge gray">6,4% s/ventas</span></td>
        </tr>
        <tr>
          <td className="t-up strong">(–) Ahorro Gerente Comercial</td>
          <td className="num mono t-up">−{c.ahorro_gerente}</td>
          <td className="num mono t-up">−59,4</td>
          <td><span className="badge green">Activo</span></td>
        </tr>
        <tr className="total">
          <td>Costo neto</td>
          <td className="num mono">{(c.total-c.ahorro_gerente).toFixed(2)}</td>
          <td className="num mono">286,4</td>
          <td><span className="badge green">5,3% s/ventas</span></td>
        </tr>
      </tbody>
    </table>
  );
}

// ============================================================
// AHORRO GERENCIA
// ============================================================
function AhorroGerencia() {
  return (
    <div>
      <div className="text-3 fs-10 uppercase">Ahorro mensual</div>
      <div className="mono fw-7" style={{fontSize:30}}>4,94<span className="text-3 fs-12" style={{marginLeft:4}}>M$</span></div>
      <div className="mt-2 fs-11 text-2">Pedro Teani · Gerente Comercial</div>
      <div className="badge red mt-2" style={{display:'inline-block'}}>Cargo no ocupado</div>
      <div className="mt-3" style={{paddingTop:10,borderTop:'1px solid var(--border-soft)'}}>
        <div className="flex between fs-11 mb-1"><span className="text-3">Ahorro YTD (Ene–Jun)</span><span className="mono fw-6 t-up">29,6 M$</span></div>
        <div className="flex between fs-11 mb-1"><span className="text-3">Ahorro proyectado 2026</span><span className="mono fw-6 t-up">59,4 M$</span></div>
        <div className="flex between fs-11"><span className="text-3">Costo bono CB compensación</span><span className="mono fw-6 t-down">−4,2 M$</span></div>
        <div className="flex between fs-11 mt-2" style={{paddingTop:8,borderTop:'1px solid var(--border-soft)'}}>
          <span className="text-2 fw-6">Ahorro neto 2026</span><span className="mono fw-7 t-up">+55,2 M$</span>
        </div>
      </div>
      <div className="mt-3 fs-11 text-3" style={{paddingTop:10,borderTop:'1px solid var(--border-soft)'}}>
        Cristóbal Bretón asume gerencia interina con bono compensatorio.
      </div>
    </div>
  );
}

// ============================================================
// BONO CB
// ============================================================
function BonoCB() {
  return (
    <div>
      <div className="text-3 fs-10 uppercase">Bono mensual</div>
      <div className="mono fw-7" style={{fontSize:30}}>350<span className="text-3 fs-12" style={{marginLeft:4}}>K$</span></div>
      <div className="mt-2 fs-11 text-2">Cristóbal Bretón · Jefe de Ventas</div>
      <div className="mt-3" style={{paddingTop:10,borderTop:'1px solid var(--border-soft)'}}>
        <div className="text-3 fs-10 uppercase mb-2">Plan original vs proyectado</div>
        <div className="flex gap-2">
          {Array.from({length:12}).map((_,i) => {
            const isProy=i>=3;
            return (
              <div key={i} style={{flex:1,textAlign:'center'}}>
                <div style={{height:24,background:isProy?'repeating-linear-gradient(45deg,#475569 0 3px,#1d2532 3px 6px)':'var(--accent)',borderRadius:3,border:i<=3?'none':'1px dashed #475569'}}></div>
                <div className="fs-10 text-3 mt-1">{D3.MESES[i]}</div>
              </div>
            );
          })}
        </div>
        <div className="flex gap-3 mt-2 fs-10 text-3">
          <span><span style={{display:'inline-block',width:10,height:10,background:'var(--accent)',borderRadius:2,marginRight:4}}></span>Original (3 meses)</span>
          <span><span style={{display:'inline-block',width:10,height:10,background:'#475569',borderRadius:2,marginRight:4}}></span>Extensión 12 meses</span>
        </div>
      </div>
      <div className="mt-3" style={{paddingTop:10,borderTop:'1px solid var(--border-soft)'}}>
        <div className="flex between fs-11 mb-1"><span className="text-3">Plan original</span><span className="mono fw-6">1,05 M$</span></div>
        <div className="flex between fs-11 mb-1"><span className="text-3">Proyectado año completo</span><span className="mono fw-6 t-warn">4,20 M$</span></div>
        <div className="flex between fs-11"><span className="text-3">Diferencial</span><span className="mono fw-6 t-down">+3,15 M$</span></div>
      </div>
    </div>
  );
}

// ============================================================
// PRODUCTIVIDAD TABLE
// ============================================================
function ProductividadTable() {
  const activos = D3.VENDEDORES.filter(v => v.activo && v.real);
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Vendedor</th>
          <th className="num">Cotizado MTD</th><th className="num">NV MTD</th>
          <th className="num">Facturado MTD</th><th className="num">Conv. cot→NV</th><th className="num">Conv. NV→Fact</th>
        </tr>
      </thead>
      <tbody>
        {activos.map((v) => {
          const cot  = v.real.cotizado ||0;
          const nv   = v.real.nv       ||0;
          const fact = v.real.facturado||0;
          const convCotNV  = cot >0?Math.round(nv  /cot *100):null;
          const convNVFact = nv  >0?Math.round(fact/nv  *100):null;
          return (
            <tr key={v.id}>
              <td className="strong">{v.nombre} <span className="text-3 fs-10">· {v.rol}</span></td>
              <td className="num mono">{cot >0?cot.toFixed(1) +' M$':'—'}</td>
              <td className="num mono">{nv  >0?nv.toFixed(1)  +' M$':'—'}</td>
              <td className="num mono">{fact>0?fact.toFixed(1)+' M$':'—'}</td>
              <td className="num mono">{convCotNV !==null?convCotNV +'%':'—'}</td>
              <td className="num mono">{convNVFact!==null?convNVFact+'%':'—'}</td>
            </tr>
          );
        })}
        <tr className="total">
          <td>Total equipo</td>
          <td className="num mono">{activos.reduce((a,v)=>a+(v.real?.cotizado||0),0).toFixed(1)} M$</td>
          <td className="num mono">{activos.reduce((a,v)=>a+(v.real?.nv||0),0).toFixed(1)} M$</td>
          <td className="num mono">{activos.reduce((a,v)=>a+(v.real?.facturado||0),0).toFixed(1)} M$</td>
          <td colSpan={2}></td>
        </tr>
      </tbody>
    </table>
  );
}

// ============================================================
// MIX VENDEDOR
// ============================================================
function MixVendedor() {
  const activos   = D3.VENDEDORES.filter(v => v.activo && v.real && v.real.facturado>0);
  const totalFact = activos.reduce((a,v) => a+(v.real?.facturado||0), 0);
  if (!activos.length) return <div className="text-3 fs-11 text-center mt-3">Cargando datos del equipo...</div>;
  return (
    <div>
      {activos.map((v,i) => {
        const pct   = totalFact>0?(v.real.facturado/totalFact*100):0;
        const cumpl = v.metaMensual>0?(v.real.facturado/v.metaMensual*100):0;
        return (
          <div key={i} className="mb-3">
            <div className="flex between fs-12 mb-1">
              <span className="fw-6">{v.nombre}</span>
              <span className="mono fw-6 fs-11">{v.real.facturado.toFixed(1)} M$ · {pct.toFixed(1)}% del total</span>
            </div>
            <div style={{height:20,background:'var(--bg-3)',borderRadius:3,overflow:'hidden',position:'relative'}}>
              <div style={{width:Math.min(100,cumpl)+'%',height:'100%',
                background:cumpl>=100?'var(--positive)':cumpl>=80?'var(--accent)':'var(--warn)',
                borderRadius:3,display:'flex',alignItems:'center',paddingLeft:6,
                fontSize:10,color:'white',fontWeight:600}}>
                {cumpl>10?cumpl.toFixed(0)+'% de meta':''}
              </div>
            </div>
            <div className="flex between fs-10 text-3 mt-1">
              <span>Meta: {v.metaMensual||'—'} M$</span>
              <span>Facturado: {v.real.facturado.toFixed(1)} M$</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

window.TeamTab = TeamTab;