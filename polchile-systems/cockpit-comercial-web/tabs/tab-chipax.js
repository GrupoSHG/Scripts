// ============================================================
// ChipaxTab  — Dashboard M5 Industrial via Chipax API
// Se registra en window.ChipaxTab para que App() lo monte
// ============================================================
(function() {
  const { useState, useEffect } = React;

  function fmtCLP(n) {
    if (n == null || n === '' || isNaN(Number(n))) return '—';
    const v = Number(n);
    if (Math.abs(v) >= 1e9) return '$' + (v/1e9).toFixed(1) + 'B';
    if (Math.abs(v) >= 1e6) return '$' + (v/1e6).toFixed(1) + 'M';
    if (Math.abs(v) >= 1e3) return '$' + Math.round(v/1e3) + 'K';
    return '$' + v.toLocaleString('es-CL');
  }
  function fmtFecha(s) {
    if (!s) return '—';
    try { return new Date(s).toLocaleDateString('es-CL'); } catch(e) { return String(s); }
  }

  // ── Estilos ──────────────────────────────────────────────
  const S = {
    page:      { padding:'20px', background:'#f4f6fa', minHeight:'calc(100vh - 60px)' },
    pageHdr:   { display:'flex', alignItems:'center', justifyContent:'space-between', background:'#9c3d11', borderRadius:12, padding:'16px 22px', marginBottom:22, color:'#fff' },
    hdrL:      { },
    hdrH1:     { fontSize:18, fontWeight:800, margin:0 },
    hdrP:      { fontSize:12, opacity:0.7, marginTop:2 },
    hdrR:      { textAlign:'right', fontSize:12, opacity:0.8 },
    btnRef:    { background:'rgba(255,255,255,0.15)', border:'1px solid rgba(255,255,255,0.3)', color:'#fff', padding:'6px 14px', borderRadius:6, fontSize:12, cursor:'pointer', marginTop:6 },
    kpiGrid:   { display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:14, marginBottom:22 },
    kpiCard:   { background:'#fff', borderRadius:10, border:'1px solid #dce3ef', padding:'14px 16px', boxShadow:'0 2px 6px rgba(0,0,0,0.04)' },
    kpiCardAc: { background:'#9c3d11', borderRadius:10, border:'1px solid #9c3d11', padding:'14px 16px' },
    kpiIco:    { fontSize:20, marginBottom:6 },
    kpiLbl:    { fontSize:11, color:'#6b7a99', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.4px' },
    kpiLblAc:  { fontSize:11, color:'rgba(255,255,255,0.65)', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.4px' },
    kpiVal:    { fontSize:20, fontWeight:800, marginTop:4, color:'#1a2b4a' },
    kpiValAc:  { fontSize:20, fontWeight:800, marginTop:4, color:'#fff' },
    kpiSub:    { fontSize:11, color:'#6b7a99', marginTop:2 },
    kpiSubAc:  { fontSize:11, color:'rgba(255,255,255,0.5)', marginTop:2 },
    tabs:      { display:'flex', gap:0, borderBottom:'2px solid #dce3ef', marginBottom:18 },
    tabBtn:    { padding:'9px 18px', fontSize:13, fontWeight:600, background:'none', border:'none', cursor:'pointer', color:'#6b7a99', borderBottom:'3px solid transparent', marginBottom:-2 },
    tabBtnA:   { padding:'9px 18px', fontSize:13, fontWeight:600, background:'none', border:'none', cursor:'pointer', color:'#e8710a', borderBottom:'3px solid #e8710a', marginBottom:-2 },
    dosCol:    { display:'grid', gridTemplateColumns:'1fr 1fr', gap:18, marginBottom:22 },
    seccion:   { background:'#fff', borderRadius:10, border:'1px solid #dce3ef', boxShadow:'0 2px 6px rgba(0,0,0,0.04)', overflow:'hidden' },
    secHdr:    { display:'flex', alignItems:'center', justifyContent:'space-between', padding:'12px 18px', borderBottom:'1px solid #dce3ef', background:'#f8faff' },
    secHdrH3:  { fontSize:13, fontWeight:700, margin:0, color:'#1a2b4a' },
    badge:     { fontSize:11, padding:'3px 9px', borderRadius:20, background:'#e8710a', color:'#fff', fontWeight:700 },
    secBody:   { padding:'16px 18px' },
    tbl:       { width:'100%', borderCollapse:'collapse', fontSize:12 },
    th:        { textAlign:'left', color:'#6b7a99', fontWeight:600, fontSize:10, textTransform:'uppercase', letterSpacing:'0.4px', padding:'6px 8px', borderBottom:'2px solid #dce3ef' },
    td:        { padding:'7px 8px', borderBottom:'1px solid #f0f3f9', color:'#1a2b4a' },
    tdR:       { padding:'7px 8px', borderBottom:'1px solid #f0f3f9', textAlign:'right', fontWeight:700, color:'#1a2b4a' },
    fila:      { display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 0', borderBottom:'1px solid #f0f3f9' },
    filaN:     { display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 0' },
    filaLbl:   { fontSize:13, color:'#6b7a99' },
    filaVal:   { fontSize:14, fontWeight:700 },
    loader:    { textAlign:'center', padding:'30px', color:'#6b7a99', fontSize:13 },
    errMsg:    { textAlign:'center', color:'#c0392b', fontSize:13, padding:'20px' },
  };

  function estadoChip(s) {
    const lower = (s||'').toLowerCase();
    if (lower.includes('pagad') || lower.includes('paid'))
      return <span style={{display:'inline-block',padding:'2px 8px',borderRadius:10,fontSize:10,fontWeight:700,background:'#e8f5e9',color:'#1e8c45'}}>Pagado</span>;
    if (lower.includes('vencid') || lower.includes('overdue'))
      return <span style={{display:'inline-block',padding:'2px 8px',borderRadius:10,fontSize:10,fontWeight:700,background:'#fdecea',color:'#c0392b'}}>Vencido</span>;
    return <span style={{display:'inline-block',padding:'2px 8px',borderRadius:10,fontSize:10,fontWeight:700,background:'#fff3e0',color:'#e65100'}}>Pendiente</span>;
  }

  // ── Sub-tabs ────────────────────────────────────────────
  const SUB_TABS = [
    { id:'ventas',   lbl:'📄 Ventas / CxC' },
    { id:'compras',  lbl:'🧾 Compras / CxP' },
    { id:'bancos',   lbl:'🏦 Bancos' },
    { id:'flujo',    lbl:'📊 Flujo de Caja' },
  ];

  function TabVentas({ data }) {
    const pend = (data.facturasPendientesVenta || []).slice(0,15);
    return (
      <div style={S.dosCol}>
        <div style={S.seccion}>
          <div style={S.secHdr}>
            <h3 style={S.secHdrH3}>Facturas de Venta Pendientes (CxC)</h3>
            <span style={S.badge}>{pend.length} docs</span>
          </div>
          <div style={S.secBody}>
            {pend.length === 0
              ? <div style={S.loader}>Sin facturas pendientes</div>
              : <table style={S.tbl}>
                  <thead><tr>
                    <th style={S.th}>Folio</th><th style={S.th}>Cliente</th>
                    <th style={S.th}>Fecha</th><th style={S.th}>Venc.</th>
                    <th style={{...S.th,textAlign:'right'}}>Monto</th><th style={S.th}>Estado</th>
                  </tr></thead>
                  <tbody>{pend.map((f,i) => (
                    <tr key={i}>
                      <td style={S.td}>{f.number||f.folio||'—'}</td>
                      <td style={S.td}>{f.contact_name||f.client_name||f.cliente||'—'}</td>
                      <td style={S.td}>{fmtFecha(f.date||f.fecha)}</td>
                      <td style={S.td}>{fmtFecha(f.due_date||f.vencimiento)}</td>
                      <td style={S.tdR}>{fmtCLP(f.total||f.monto||f.amount)}</td>
                      <td style={S.td}>{estadoChip(f.status||f.estado)}</td>
                    </tr>
                  ))}</tbody>
                </table>
            }
          </div>
        </div>
        <div style={S.seccion}>
          <div style={S.secHdr}><h3 style={S.secHdrH3}>Resumen Ventas MTD</h3></div>
          <div style={S.secBody}>
            {[
              ['Total Ventas Mes',       data.ventasMTD,  '#2d5faa'],
              ['CxC Total Pendiente',    data.totalCXC,   '#c0392b'],
              ['Facturas Pendientes',    data.cxcCount,   '#1a2b4a'],
              ['Clientes Activos',       data.clientesCount,'#1a2b4a'],
            ].map(([l,v,c],i,arr) => (
              <div key={l} style={i===arr.length-1 ? S.filaN : S.fila}>
                <span style={S.filaLbl}>{l}</span>
                <span style={{...S.filaVal, color:c}}>{typeof v==='number'&&v>999?fmtCLP(v):v||'—'}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  function TabCompras({ data }) {
    const pend = (data.facturasPendientesCompra || []).slice(0,15);
    return (
      <div style={S.dosCol}>
        <div style={S.seccion}>
          <div style={S.secHdr}>
            <h3 style={S.secHdrH3}>Facturas de Compra Pendientes (CxP)</h3>
            <span style={S.badge}>{pend.length} docs</span>
          </div>
          <div style={S.secBody}>
            {pend.length === 0
              ? <div style={S.loader}>Sin facturas pendientes</div>
              : <table style={S.tbl}>
                  <thead><tr>
                    <th style={S.th}>Folio</th><th style={S.th}>Proveedor</th>
                    <th style={S.th}>Fecha</th><th style={S.th}>Venc.</th>
                    <th style={{...S.th,textAlign:'right'}}>Monto</th><th style={S.th}>Estado</th>
                  </tr></thead>
                  <tbody>{pend.map((f,i) => (
                    <tr key={i}>
                      <td style={S.td}>{f.number||f.folio||'—'}</td>
                      <td style={S.td}>{f.contact_name||f.supplier_name||f.proveedor||'—'}</td>
                      <td style={S.td}>{fmtFecha(f.date||f.fecha)}</td>
                      <td style={S.td}>{fmtFecha(f.due_date||f.vencimiento)}</td>
                      <td style={S.tdR}>{fmtCLP(f.total||f.monto||f.amount)}</td>
                      <td style={S.td}>{estadoChip(f.status||f.estado)}</td>
                    </tr>
                  ))}</tbody>
                </table>
            }
          </div>
        </div>
        <div style={S.seccion}>
          <div style={S.secHdr}><h3 style={S.secHdrH3}>Resumen Compras MTD</h3></div>
          <div style={S.secBody}>
            {[
              ['Total Compras Mes',     data.comprasMTD,      '#e8710a'],
              ['CxP Total Pendiente',   data.totalCXP,        '#c0392b'],
              ['Facturas Pendientes',   data.cxpCount,        '#1a2b4a'],
              ['Proveedores Activos',   data.proveedoresCount,'#1a2b4a'],
            ].map(([l,v,c],i,arr) => (
              <div key={l} style={i===arr.length-1 ? S.filaN : S.fila}>
                <span style={S.filaLbl}>{l}</span>
                <span style={{...S.filaVal, color:c}}>{typeof v==='number'&&v>999?fmtCLP(v):v||'—'}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  function TabBancos({ data }) {
    const cuentas = data.cuentasBancarias || [];
    const movs    = (data.movimientosRecientes || []).slice(0,15);
    const total   = cuentas.reduce((a,c) => a + Number(c.balance||c.saldo||0), 0);
    return (
      <div style={S.dosCol}>
        <div style={S.seccion}>
          <div style={S.secHdr}><h3 style={S.secHdrH3}>Cuentas Bancarias</h3></div>
          <div style={S.secBody}>
            {cuentas.length === 0
              ? <div style={S.loader}>Sin cuentas disponibles</div>
              : <table style={S.tbl}>
                  <thead><tr>
                    <th style={S.th}>Banco</th><th style={S.th}>Cuenta</th>
                    <th style={S.th}>Tipo</th><th style={{...S.th,textAlign:'right'}}>Saldo</th>
                  </tr></thead>
                  <tbody>
                    {cuentas.map((c,i) => (
                      <tr key={i}>
                        <td style={S.td}>{c.bank_name||c.banco||c.name||'—'}</td>
                        <td style={S.td}>{c.account_number||c.numero||'—'}</td>
                        <td style={S.td}>{c.account_type||c.tipo||'—'}</td>
                        <td style={{...S.tdR, color:'#1e8c45'}}>{fmtCLP(c.balance||c.saldo||0)}</td>
                      </tr>
                    ))}
                    <tr style={{fontWeight:700, background:'#f8faff'}}>
                      <td style={S.td} colSpan={3}>TOTAL</td>
                      <td style={{...S.tdR, color:'#1e8c45'}}>{fmtCLP(total)}</td>
                    </tr>
                  </tbody>
                </table>
            }
          </div>
        </div>
        <div style={S.seccion}>
          <div style={S.secHdr}><h3 style={S.secHdrH3}>Últimos Movimientos</h3></div>
          <div style={S.secBody}>
            {movs.length === 0
              ? <div style={S.loader}>Sin movimientos recientes</div>
              : <table style={S.tbl}>
                  <thead><tr>
                    <th style={S.th}>Fecha</th><th style={S.th}>Descripción</th>
                    <th style={{...S.th,textAlign:'right'}}>Monto</th>
                  </tr></thead>
                  <tbody>{movs.map((m,i) => {
                    const monto  = Number(m.amount||m.monto||0);
                    const esAb   = monto >= 0;
                    return (
                      <tr key={i}>
                        <td style={S.td}>{fmtFecha(m.date||m.fecha)}</td>
                        <td style={S.td}>
                          <span style={{display:'flex', alignItems:'center', gap:6}}>
                            <span style={{width:8,height:8,borderRadius:'50%',background:esAb?'#1e8c45':'#c0392b',flexShrink:0}}/>
                            {m.description||m.descripcion||'—'}
                          </span>
                        </td>
                        <td style={{...S.tdR, color:esAb?'#1e8c45':'#c0392b'}}>{fmtCLP(Math.abs(monto))}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
            }
          </div>
        </div>
      </div>
    );
  }

  function TabFlujo({ data }) {
    const saldo = Number(data.saldoBancos||0);
    const cxc   = Number(data.totalCXC||0);
    const cxp   = Number(data.totalCXP||0);
    const neto  = saldo + cxc - cxp;
    return (
      <div style={S.seccion}>
        <div style={S.secHdr}><h3 style={S.secHdrH3}>Proyección Flujo de Caja</h3></div>
        <div style={S.secBody}>
          <div style={{display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:14, marginBottom:20}}>
            {[
              { lbl:'Ingresos Proyectados', val:cxc,  bg:'#e8f5e9', c:'#1e8c45', sub:'CxC pendiente de cobro' },
              { lbl:'Egresos Proyectados',  val:cxp,  bg:'#fdecea', c:'#c0392b', sub:'CxP pendiente de pago' },
              { lbl:'Posición Neta',        val:neto, bg:'#1a2b4a', c:neto>=0?'#4cde8a':'#ff6b6b', sub:'Bancos + CxC − CxP' },
            ].map(({lbl,val,bg,c,sub}) => (
              <div key={lbl} style={{background:bg, borderRadius:8, padding:14, textAlign:'center'}}>
                <div style={{fontSize:11, color:c, fontWeight:700, textTransform:'uppercase', marginBottom:6}}>{lbl}</div>
                <div style={{fontSize:22, fontWeight:800, color:c}}>{fmtCLP(val)}</div>
                <div style={{fontSize:11, color:'rgba(0,0,0,0.4)', marginTop:4}}>{sub}</div>
              </div>
            ))}
          </div>
          {[
            ['💰 Saldo actual en bancos', saldo, '#1e8c45', false],
            ['📥 CxC por cobrar',         cxc,   '#2d5faa', false],
            ['📤 CxP por pagar',          cxp,   '#c0392b', false],
            ['Posición Financiera Neta',  neto,  neto>=0?'#1e8c45':'#c0392b', true],
          ].map(([l,v,c,bold]) => (
            <div key={l} style={{...S.fila, ...(bold?{fontWeight:700,borderTop:'2px solid #dce3ef',paddingTop:12,marginTop:4}:{})}}>
              <span style={{...S.filaLbl, ...(bold?{fontWeight:700,color:'#1a2b4a'}:{})}}>{l}</span>
              <span style={{...S.filaVal, color:c, ...(bold?{fontSize:16}:{})}}>{fmtCLP(v)}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Componente principal ─────────────────────────────────
  function ChipaxTab() {
    const [data,     setData]     = useState(null);
    const [loading,  setLoading]  = useState(true);
    const [error,    setError]    = useState(null);
    const [subTab,   setSubTab]   = useState('ventas');
    const [fechaAct, setFechaAct] = useState('');

    const cargar = () => {
      setLoading(true);
      setError(null);
      google.script.run
        .withSuccessHandler(d => {
          if (d && d.error) { setError(d.error); }
          else              { setData(d); }
          setLoading(false);
          setFechaAct(new Date().toLocaleString('es-CL'));
        })
        .withFailureHandler(e => {
          setError(e.message);
          setLoading(false);
        })
        .getChipaxDashboard();
    };

    useEffect(() => { cargar(); }, []);

    const kpis = data ? [
      { ico:'💰', lbl:'Saldo Bancos',   val:fmtCLP(data.saldoBancos), sub:'Todas las cuentas', ac:true  },
      { ico:'📄', lbl:'CxC por cobrar', val:fmtCLP(data.totalCXC),   sub:(data.cxcCount||0)+' facturas' },
      { ico:'🧾', lbl:'CxP por pagar',  val:fmtCLP(data.totalCXP),   sub:(data.cxpCount||0)+' facturas' },
      { ico:'📈', lbl:'Ventas MTD',      val:fmtCLP(data.ventasMTD),  sub:'Mes en curso' },
      { ico:'📉', lbl:'Compras MTD',     val:fmtCLP(data.comprasMTD), sub:'Mes en curso' },
    ] : [];

    return (
      <div style={S.page}>
        {/* Header */}
        <div style={S.pageHdr}>
          <div style={S.hdrL}>
            <h1 style={S.hdrH1}>M5 Industrial · Dashboard Financiero</h1>
            <p style={S.hdrP}>Datos en tiempo real desde Chipax</p>
          </div>
          <div style={S.hdrR}>
            <div>{fechaAct || 'Cargando...'}</div>
            <button style={S.btnRef} onClick={cargar}>↺ Actualizar</button>
          </div>
        </div>

        {/* KPI Cards */}
        {loading
          ? <div style={{...S.loader, gridColumn:'1/-1'}}>⏳ Consultando Chipax...</div>
          : error
            ? <div style={S.errMsg}>❌ Error Chipax: {error}</div>
            : (
              <>
                <div style={S.kpiGrid}>
                  {kpis.map(k => (
                    <div key={k.lbl} style={k.ac ? S.kpiCardAc : S.kpiCard}>
                      <div style={S.kpiIco}>{k.ico}</div>
                      <div style={k.ac ? S.kpiLblAc : S.kpiLbl}>{k.lbl}</div>
                      <div style={k.ac ? S.kpiValAc : S.kpiVal}>{k.val}</div>
                      <div style={k.ac ? S.kpiSubAc : S.kpiSub}>{k.sub}</div>
                    </div>
                  ))}
                </div>

                {/* Sub-tabs */}
                <div style={S.tabs}>
                  {SUB_TABS.map(t => (
                    <button key={t.id} style={subTab===t.id ? S.tabBtnA : S.tabBtn} onClick={() => setSubTab(t.id)}>
                      {t.lbl}
                    </button>
                  ))}
                </div>

                {subTab === 'ventas'  && <TabVentas  data={data}/>}
                {subTab === 'compras' && <TabCompras data={data}/>}
                {subTab === 'bancos'  && <TabBancos  data={data}/>}
                {subTab === 'flujo'   && <TabFlujo   data={data}/>}
              </>
            )
        }
      </div>
    );
  }

  window.ChipaxTab = ChipaxTab;
})();
