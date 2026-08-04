// ============================================================
// ResumenTab  — Resumen grupo empresarial (Polchile / M5 / CYS)
// Con botones de navegación a cada tab de empresa
// ============================================================
(function() {
  const { useState, useEffect } = React;

  function fmtCLP(n) {
    if (n == null || n === '' || isNaN(Number(n))) return '—';
    const v = Number(n);
    if (Math.abs(v) >= 1e9) return '$' + (v/1e9).toFixed(1) + 'B';
    if (Math.abs(v) >= 1e6) return '$' + (v/1e6).toFixed(1) + 'M';
    if (Math.abs(v) >= 1e3) return '$' + (v/1e3).toFixed(0) + 'K';
    return '$' + v.toLocaleString('es-CL');
  }
  function pct(a, b) {
    if (!b || b === 0) return 0;
    return Math.min(Math.round((a / b) * 100), 999);
  }
  function colorBarra(p) {
    if (p >= 90) return '#1e8c45';
    if (p >= 60) return '#e8710a';
    return '#c0392b';
  }

  const S = {
    page:     { padding:'20px', background:'#f4f6fa', minHeight:'calc(100vh - 60px)' },
    header:   { display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:24 },
    h1:       { fontSize:20, fontWeight:700, color:'#1a2b4a', margin:0 },
    badgeMes: { background:'#1e3a6e', color:'#fff', padding:'4px 14px', borderRadius:20, fontSize:12, fontWeight:700 },
    grid:     { display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:20 },
    card:     { background:'#fff', borderRadius:12, border:'1px solid #dce3ef', overflow:'hidden', boxShadow:'0 2px 8px rgba(0,0,0,0.05)', display:'flex', flexDirection:'column' },
    cardHead: { padding:'14px 18px', display:'flex', alignItems:'center', gap:10 },
    inicial:  { width:36, height:36, borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', fontWeight:800, fontSize:14, color:'#fff', flexShrink:0 },
    nombre:   { fontSize:15, fontWeight:700, color:'#1a2b4a' },
    subtit:   { fontSize:11, color:'#6b7a99' },
    chipLive: { marginLeft:'auto', fontSize:10, padding:'3px 8px', borderRadius:10, fontWeight:700, background:'#e8f5e9', color:'#1e8c45', whiteSpace:'nowrap' },
    chipWip:  { marginLeft:'auto', fontSize:10, padding:'3px 8px', borderRadius:10, fontWeight:700, background:'#fff3e0', color:'#e65100', whiteSpace:'nowrap' },
    body:     { padding:'14px 18px 4px', flex:1 },
    footer:   { padding:'12px 18px 16px', borderTop:'1px solid #f0f3f9', marginTop:'auto' },
    kpiMain:  { display:'flex', flexDirection:'column', alignItems:'center', borderRadius:10, padding:'14px 10px', marginBottom:14, textAlign:'center' },
    kpiEtq:   { fontSize:11, color:'rgba(255,255,255,0.6)', marginBottom:4 },
    kpiMonto: { fontSize:22, fontWeight:800, color:'#fff' },
    kpiSub:   { fontSize:11, color:'rgba(255,255,255,0.5)', marginTop:2 },
    secTitle: { fontSize:10, fontWeight:700, textTransform:'uppercase', color:'#6b7a99', letterSpacing:'0.5px', margin:'12px 0 8px', borderBottom:'1px solid #dce3ef', paddingBottom:4 },
    row:      { display:'flex', justifyContent:'space-between', alignItems:'center', padding:'5px 0', borderBottom:'1px solid #f0f3f9' },
    lbl:      { fontSize:12, color:'#6b7a99' },
    val:      { fontSize:13, fontWeight:700 },
    barraWrap:{ margin:'10px 0 4px' },
    barraLbl: { display:'flex', justifyContent:'space-between', fontSize:11, color:'#6b7a99', marginBottom:4 },
    barraBg:  { background:'#e8edf5', borderRadius:6, height:8, overflow:'hidden' },
    loader:   { textAlign:'center', padding:'30px', color:'#6b7a99', fontSize:13 },
    placeh:   { textAlign:'center', color:'#6b7a99', fontSize:13, padding:'40px 20px' },
    btnAccion:{
      width:'100%', padding:'10px 14px', border:'none', borderRadius:8,
      fontSize:13, fontWeight:700, cursor:'pointer',
      display:'flex', alignItems:'center', justifyContent:'center', gap:6,
      transition:'all 0.2s', color:'#fff',
    },
    btnDisabled:{
      width:'100%', padding:'10px 14px', border:'1px solid #dce3ef', borderRadius:8,
      fontSize:13, fontWeight:600, cursor:'not-allowed',
      background:'#f4f6fa', color:'#9aa5bd',
      display:'flex', alignItems:'center', justifyContent:'center', gap:6,
    },
  };

  // Navegación helper
  function irA(tabId) {
    if (window.__setTab) window.__setTab(tabId);
  }

  function CardPolchile({ data, loading, error }) {
    if (loading) return <div style={S.loader}>⏳ Cargando Polchile...</div>;
    if (error)   return <div style={{...S.loader, color:'#c0392b'}}>❌ {error}</div>;
    if (!data)   return <div style={S.loader}>Sin datos</div>;
    const p = pct(data.facturadoMTD, data.presupuestoMes);
    return (
      <div style={S.body}>
        <div style={{...S.kpiMain, background:'#1a2b4a'}}>
          <div style={S.kpiEtq}>Facturado MTD</div>
          <div style={S.kpiMonto}>{fmtCLP(data.facturadoMTD)}</div>
          <div style={S.kpiSub}>Presupuesto: {fmtCLP(data.presupuestoMes)}</div>
        </div>
        <div style={S.barraWrap}>
          <div style={S.barraLbl}><span>Avance vs Presupuesto</span><span>{p}%</span></div>
          <div style={S.barraBg}><div style={{height:8, borderRadius:6, width:Math.min(p,100)+'%', background:colorBarra(p), transition:'width 0.7s ease'}}/></div>
        </div>
        <div style={S.secTitle}>Ventas</div>
        {[
          ['Ventas MTD (NV)',        data.ventasMTD,      '#2d5faa'],
          ['Cotizado MTD',           data.cotizadoMTD,    '#1a2b4a'],
          ['Forecast Facturación',   data.forecastFact,   '#e8710a'],
          ['Forecast Cierre Ventas', data.forecastVentas, '#1e8c45'],
        ].map(([l,v,c]) => (
          <div key={l} style={S.row}>
            <span style={S.lbl}>{l}</span>
            <span style={{...S.val, color:c}}>{fmtCLP(v)}</span>
          </div>
        ))}
        <div style={S.secTitle}>Cobranza</div>
        <div style={S.row}>
          <span style={S.lbl}>CxC (NV Pendientes)</span>
          <span style={{...S.val, color:'#c0392b'}}>{fmtCLP(data.totalCXC)}</span>
        </div>
      </div>
    );
  }

  function CardM5({ data, loading, error }) {
    if (loading) return <div style={S.loader}>⏳ Consultando Chipax...</div>;
    if (error)   return <div style={{...S.loader, color:'#c0392b'}}>❌ Chipax: {error}</div>;
    if (!data)   return <div style={S.loader}>Sin datos</div>;
    return (
      <div style={S.body}>
        <div style={{...S.kpiMain, background:'#9c3d11'}}>
          <div style={S.kpiEtq}>Facturado MTD · Chipax</div>
          <div style={S.kpiMonto}>{fmtCLP(data.facturadoMTD)}</div>
          <div style={S.kpiSub}>Saldo Bancos: {fmtCLP(data.saldoBancos)}</div>
        </div>
        <div style={S.secTitle}>Ventas</div>
        {[
          ['Ventas MTD',             data.ventasMTD,      '#2d5faa'],
          ['Forecast Facturación',   data.forecastFact,   '#e8710a'],
          ['Forecast Cierre Ventas', data.forecastCierre, '#1e8c45'],
        ].map(([l,v,c]) => (
          <div key={l} style={S.row}>
            <span style={S.lbl}>{l}</span>
            <span style={{...S.val, color:c}}>{fmtCLP(v)}</span>
          </div>
        ))}
        <div style={S.secTitle}>Tesorería</div>
        {[
          ['CxC (por cobrar)', data.totalCXC,    '#c0392b'],
          ['CxP (por pagar)',  data.totalCXP,    '#e8710a'],
          ['Saldo Bancos',     data.saldoBancos, '#1e8c45'],
        ].map(([l,v,c]) => (
          <div key={l} style={S.row}>
            <span style={S.lbl}>{l}</span>
            <span style={{...S.val, color:c}}>{fmtCLP(v)}</span>
          </div>
        ))}
      </div>
    );
  }

  function ResumenTab() {
    const [polchile, setPolchile] = useState(null);
    const [m5,       setM5]       = useState(null);
    const [loadingP, setLoadingP] = useState(true);
    const [loadingM, setLoadingM] = useState(true);
    const [errorP,   setErrorP]   = useState(null);
    const [errorM,   setErrorM]   = useState(null);

    const now      = new Date();
    const meses    = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
    const mesBadge = meses[now.getMonth()] + ' ' + now.getFullYear();

    useEffect(() => {
      if (window.__DATA && window.__DATA.kpis) {
        const k = window.__DATA.kpis;
        setPolchile({
          presupuestoMes : (k.presupuestoMes || 0) * 1e6,
          facturadoMTD   : k.facturadoMTD    || 0,
          ventasMTD      : k.nvEmitidasMTD   || 0,
          cotizadoMTD    : k.cotizadoMTD     || 0,
          forecastFact   : k.porFacturar      || 0,
          forecastVentas : k.nvEmitidasYTD   || 0,
          totalCXC       : k.nvPendientesYTD || 0,
        });
        setLoadingP(false);
      } else {
        google.script.run
          .withSuccessHandler(d => { setPolchile(d); setLoadingP(false); })
          .withFailureHandler(e => { setErrorP(e.message); setLoadingP(false); })
          .getResumenPolchile();
      }

      google.script.run
        .withSuccessHandler(d => {
          if (d && d.error) setErrorM(d.error);
          else              setM5(d);
          setLoadingM(false);
        })
        .withFailureHandler(e => { setErrorM(e.message); setLoadingM(false); })
        .getResumenM5Chipax();
    }, []);

    const empresas = [
      {
        id:'polchile', nombre:'Polchile SpA',  subtit:'Paneles Sandwich',   color:'#1a2b4a', ini:'P',
        chipTxt:'● LIVE', chipSt:S.chipLive,
        body: <CardPolchile data={polchile} loading={loadingP} error={errorP}/>,
        accion: { label: 'Ver Dashboard Polchile', tab: 'exec', color: '#1a2b4a' },
      },
      {
        id:'m5',       nombre:'M5 Industrial', subtit:'Finanzas vía Chipax', color:'#e8710a', ini:'M5',
        chipTxt:'● LIVE', chipSt:S.chipLive,
        body: <CardM5 data={m5} loading={loadingM} error={errorM}/>,
        accion: { label: 'Ver Dashboard M5 · Chipax', tab: 'chipax', color: '#9c3d11' },
      },
      {
        id:'cys',      nombre:'CYS',           subtit:'En configuración',    color:'#1e8c45', ini:'C',
        chipTxt:'⏳ Próximo', chipSt:S.chipWip,
        body: <div style={S.placeh}><div style={{fontSize:32,marginBottom:10}}>🏗️</div>KPIs en configuración.<br/>Próximamente disponible.</div>,
        accion: null, // sin botón
      },
    ];

    return (
      <div style={S.page}>
        <div style={S.header}>
          <div>
            <h1 style={S.h1}>Resumen Grupo Empresarial</h1>
            <div style={{fontSize:12, color:'#6b7a99', marginTop:4}}>Actualizado: {now.toLocaleString('es-CL')}</div>
          </div>
          <span style={S.badgeMes}>{mesBadge}</span>
        </div>
        <div style={S.grid}>
          {empresas.map(e => (
            <div key={e.id} style={S.card}>
              <div style={{...S.cardHead, background: e.color + '18'}}>
                <div style={{...S.inicial, background: e.color}}>{e.ini}</div>
                <div>
                  <div style={S.nombre}>{e.nombre}</div>
                  <div style={S.subtit}>{e.subtit}</div>
                </div>
                <span style={e.chipSt}>{e.chipTxt}</span>
              </div>
              {e.body}
              <div style={S.footer}>
                {e.accion ? (
                  <button
                    style={{...S.btnAccion, background: e.accion.color}}
                    onClick={() => irA(e.accion.tab)}
                    onMouseEnter={(ev) => ev.currentTarget.style.opacity = '0.85'}
                    onMouseLeave={(ev) => ev.currentTarget.style.opacity = '1'}
                  >
                    {e.accion.label} →
                  </button>
                ) : (
                  <button style={S.btnDisabled} disabled>
                    Próximamente
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  window.ResumenTab = ResumenTab;
})();
