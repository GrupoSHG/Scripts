// ============================================================
// POLCHILE - DATOS DEL DASHBOARD COMERCIAL
// Fuente: Presupuesto P&L 2026 + payload live desde Firebase Function
// ============================================================

const HOY          = new Date();
const DIA_DEL_MES  = HOY.getDate();
const MES_ACTUAL   = HOY.getMonth();
const ANIO         = HOY.getFullYear();

const MESES       = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const MESES_LARGO = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

const ESTACIONALIDAD    = [7.10,7.80,8.10,6.80,8.30,9.30,8.50,8.70,8.50,7.70,9.90,9.30];
const PRESUPUESTO_ANUAL = { base:5400, optimista:6480, pesimista:4320 };
const presupMensual     = (esc='base') => ESTACIONALIDAD.map(p => PRESUPUESTO_ANUAL[esc] * p / 100);

const REAL_2026 = {
  cotizado:  [1240,1180,1295,680,0,0,0,0,0,0,0,0],
  nv:        [ 368, 428, 375,152,0,0,0,0,0,0,0,0],
  facturado: [ 354, 411, 362,148,0,0,0,0,0,0,0,0],
};
const REAL_2025_FACTURADO = [336,254,323,343,313,274,365,244,329,178,295,280];

const PIPELINE_CRM = [
  { etapa:'Lead Nuevo',         monto:285, n:47, prob:5,   colorIdx:0 },
  { etapa:'Contactado',         monto:412, n:38, prob:15,  colorIdx:1 },
  { etapa:'Calificado',         monto:386, n:29, prob:30,  colorIdx:2 },
  { etapa:'Cotización Enviada', monto:524, n:24, prob:50,  colorIdx:3 },
  { etapa:'Negociación',        monto:318, n:14, prob:70,  colorIdx:4 },
  { etapa:'NV en Proceso',      monto:196, n: 9, prob:90,  colorIdx:5 },
  { etapa:'Ganado (Mes)',       monto:152, n:12, prob:100, colorIdx:6 },
];
let FORECAST_CRM_PONDERADO = PIPELINE_CRM.reduce((a,e) => a + e.monto * e.prob / 100, 0);

const VENDEDORES = [
  { id:'cb',  nombre:'Cristóbal Bretón',   cargo:'Jefe de Ventas',              metaMensual:0,    sueldoFijo:2.07, comision:0.35, bonoExtra:0.35, avatar:'CB', activo:true,  color:'#6366f1', real:{cotizado:0,nv:0,facturado:0}, rol:'jefatura'  },
  { id:'mj',  nombre:'Melysa Jiménez',     cargo:'Ejecutiva Ventas',             metaMensual:81,   sueldoFijo:1.11, comision:0.75, avatar:'MJ', activo:true,  color:'#0ea5e9', real:{cotizado:0,nv:0,facturado:0}, rol:'ejecutivo' },
  { id:'op',  nombre:'Óscar Paredes',      cargo:'Ejecutivo Ventas',             metaMensual:81,   sueldoFijo:1.30, comision:0.75, avatar:'OP', activo:true,  color:'#10b981', real:{cotizado:0,nv:0,facturado:0}, rol:'ejecutivo' },
  { id:'lb',  nombre:'Linda Bayle',        cargo:'Ejecutiva Ventas',             metaMensual:81,   sueldoFijo:1.11, comision:0.75, avatar:'LB', activo:true,  color:'#ec4899', real:{cotizado:0,nv:0,facturado:0}, rol:'ejecutivo' },
  { id:'oa',  nombre:'Orlando Armas',      cargo:'Ejecutivo Ventas',             metaMensual:81,   sueldoFijo:1.30, comision:0.75, avatar:'OA', activo:true,  color:'#f97316', real:{cotizado:0,nv:0,facturado:0}, rol:'ejecutivo' },
  { id:'hp',  nombre:'Hernán Paulsen',     cargo:'Ejecutivo Ventas',             metaMensual:81,   sueldoFijo:1.30, comision:0.75, avatar:'HP', activo:true,  color:'#a855f7', real:{cotizado:0,nv:0,facturado:0}, rol:'ejecutivo' },
  { id:'v1',  nombre:'Vacante Ejecutivo 1',cargo:'Ejecutivo Ventas',             metaMensual:81,   vacante:true, rol:'ejecutivo', activo:false },
  { id:'v2',  nombre:'Vacante Ejecutivo 2',cargo:'Ejecutivo Ventas',             metaMensual:81,   vacante:true, rol:'ejecutivo', activo:false },
  { id:'v3',  nombre:'Vacante Ejecutivo 3',cargo:'Ejecutivo Ventas',             metaMensual:81,   vacante:true, rol:'ejecutivo', activo:false },
  { id:'kam', nombre:'Vacante KAM',         cargo:'KAM Distrib. y Constructoras', metaMensual:22.5, vacante:true, rol:'kam',       activo:false },
  { id:'ec',  nombre:'Vacante Ecommerce',   cargo:'Encargado Ecommerce',          metaMensual:22.5, vacante:true, rol:'ecommerce', activo:false },
];

let MIX_FAMILIA = [
  { fam:'Paneles POL',         p_pct:45.0, r_pct:47.2, d_pp: 2.2, m_real:44.9, m_pre:43.5, m_d: 1.4 },
  { fam:'Paneles PUR',         p_pct:10.0, r_pct: 8.7, d_pp:-1.3, m_real:45.4, m_pre:43.5, m_d: 1.9 },
  { fam:'Planchas Industrial', p_pct:22.0, r_pct:19.4, d_pp:-2.6, m_real:36.0, m_pre:43.5, m_d:-7.5 },
  { fam:'Planchas Arquitect.', p_pct: 8.0, r_pct: 6.8, d_pp:-1.2, m_real:51.0, m_pre:43.5, m_d: 7.5 },
  { fam:'Hojalatería',         p_pct: 3.9, r_pct: 4.1, d_pp: 0.2, m_real:30.0, m_pre:43.5, m_d:-13.5 },
  { fam:'Accesorios',          p_pct: 3.6, r_pct: 4.2, d_pp: 0.6, m_real:40.0, m_pre:43.5, m_d:-3.5  },
  { fam:'Despachos/Servicios', p_pct: 5.0, r_pct: 6.1, d_pp: 1.1, m_real:45.0, m_pre:43.5, m_d: 1.5  },
  { fam:'Comercializados',     p_pct: 2.5, r_pct: 3.6, d_pp: 1.1, m_real:18.0, m_pre:43.5, m_d:-25.5 },
];

let TOP_CLIENTES = [
  { rank:1,  n:'Constructora Andes Ltda.',  val:198.4, pct:14.8, type:'REC' },
  { rank:2,  n:'Inmobiliaria Pacífico',      val:142.7, pct:10.7, type:'REC' },
  { rank:3,  n:'Frigoríficos del Sur S.A.', val: 98.3, pct: 7.4, type:'REC' },
  { rank:4,  n:'Distribuidora Maule',        val: 76.1, pct: 5.7, type:'REC' },
  { rank:5,  n:'Constructora Vallejos',      val: 64.8, pct: 4.9, type:'NUEVO'},
  { rank:6,  n:'Agroindustrial Los Lagos',   val: 52.4, pct: 3.9, type:'REC' },
  { rank:7,  n:'Ferretería El Sol Ltda.',    val: 44.9, pct: 3.4, type:'REC' },
  { rank:8,  n:'Cámaras Frigo Patagonia',    val: 38.2, pct: 2.9, type:'NUEVO'},
  { rank:9,  n:'Inversiones Plaza Norte',    val: 31.6, pct: 2.4, type:'REC' },
  { rank:10, n:'Constructora Pucón',         val: 28.9, pct: 2.2, type:'NUEVO'},
];

const ALERTAS = [
  { tipo:'critica', icon:'!', texto:'Run-rate actual proyecta no cumplir el mes', accion:'Revisar cierres pendientes' },
];

const KPI_MES = {
  presupuesto:         presupMensual('base')[MES_ACTUAL],
  facturado:           0,
  nv:                  0,
  cotizado:            0,
  forecast_mes:        0,
  cumplimiento:        0,
  run_rate_diario:     0,
  run_rate_requerido:  0,
  ticket_promedio:     0,
  ticket_mediana:      0,
  win_rate:            34,
  ciclo_dias:          28,
  conv_cot_nv:         24,
  conv_nv_factura:     96,
  clientes_nuevos:     0,
  clientes_recurrentes:0,
  dso:                 47,
  backlog_nv:          0,
  margen_real:         0,
  margen_presup:       43.5,
};

const COSTOS_MES = {
  remuneraciones_fijo:17.13, comisiones:4.53, bono_cb:0.35,
  ahorro_gerente:4.94, marketing:5.08, representacion:0.15,
  suscripciones:0.06, total:27.30,
};

// ── Exponer global ─────────────────────────────────────────
window.PCH = {
  HOY, DIA_DEL_MES, MES_ACTUAL, ANIO, MESES, MESES_LARGO,
  ESTACIONALIDAD, PRESUPUESTO_ANUAL, presupMensual,
  REAL_2026, REAL_2025_FACTURADO,
  PIPELINE_CRM, FORECAST_CRM_PONDERADO,
  VENDEDORES, MIX_FAMILIA, TOP_CLIENTES,
  ALERTAS, KPI_MES, COSTOS_MES,
  SEMANAS: [], diarias: {}, flow7d: {},
  graficoDiario: [], graficoDiarioNV: [],
};

// ============================================================
// APLICAR PAYLOAD — reemplaza google.script.run
// Llamado desde index.html cuando Firebase Function responde
// ============================================================
window.__applyPayload = function(payload) {
  if (!payload || payload.error) {
    console.error('Payload inválido:', payload && payload.error);
    return;
  }

  // ── 1. YTD + gráfico mensual ────────────────────────────
  if (payload.manager) {
    window.PCH.REAL_YTD    = payload.manager.facturacion / 1000000;
    window.PCH.MARGEN_REAL = payload.manager.margen      / 1000000;
    if (payload.manager.facturacionMensual) {
      window.PCH.REAL_2026.facturado = payload.manager.facturacionMensual.map(m => m / 1000000);
    }
  }

  // ── 2. Pipeline CRM ────────────────────────────────────
  if (payload.pipeline && payload.pipeline.length > 0) {
    window.PCH.PIPELINE_CRM = payload.pipeline.map((e, i) => ({ ...e, colorIdx: i % 7 }));
    window.PCH.FORECAST_CRM_PONDERADO = payload.pipeline.reduce((t, e) => t + (e.ponderado || 0), 0);
  }

  // ── 3. Datos operativos ────────────────────────────────
  if (payload.diarias)       window.PCH.diarias       = payload.diarias;
  if (payload.flow7d)        window.PCH.flow7d        = payload.flow7d;
  if (payload.graficoDiario)   window.PCH.graficoDiario   = payload.graficoDiario;
  if (payload.graficoDiarioNV) window.PCH.graficoDiarioNV = payload.graficoDiarioNV;
  if (payload.SEMANAS)       window.PCH.SEMANAS       = payload.SEMANAS;

  // ── 4. KPIs ────────────────────────────────────────────
  if (payload.kpis) {
    window.PCH.KPI_MES.presupuesto = payload.kpis.presupuestoMes;
    window.PCH.KPI_MES.facturado   = payload.kpis.facturadoMTD  / 1000000;
    window.PCH.KPI_MES.cotizado    = payload.kpis.cotizadoMTD   / 1000000;
    window.PCH.KPI_MES.nv          = payload.kpis.nvEmitidasMTD / 1000000;
    window.PCH.KPI_MES.nvYTD       = (payload.kpis.nvEmitidasYTD || 0) / 1000000;
    window.PCH.KPI_MES.backlog_nv  = payload.kpis.nvPendientesYTD / 1000000;
    window.PCH.BACKLOG_NV          = payload.kpis.nvPendientesYTD / 1000000;
    window.PCH.KPI_MES.mesActual   = payload.kpis.mesActual;
    window.PCH.KPI_MES.fechaHoy    = payload.kpis.fechaHoy;

    if (payload.kpis.presupuestoArray) {
      window.PCH.presupMensual = () => payload.kpis.presupuestoArray;
      let sumYTD = 0;
      for (let i = 0; i <= window.PCH.MES_ACTUAL; i++) sumYTD += payload.kpis.presupuestoArray[i];
      window.PCH.YTD_PRESUPUESTO = sumYTD;
    }

    // Forecast
    const facturadoM = window.PCH.KPI_MES.facturado || 0;
    const nvM        = window.PCH.KPI_MES.nv        || 0;
    const cotizadoM  = window.PCH.KPI_MES.cotizado  || 0;
    const backlogM   = window.PCH.KPI_MES.backlog_nv|| 0;
    const forecast   = facturadoM + nvM + (backlogM * 0.70) + (cotizadoM * 0.24);
    window.PCH.KPI_MES.forecast_mes  = forecast;
    window.PCH.KPI_MES.cumplimiento  = Math.round((forecast / (window.PCH.KPI_MES.presupuesto || 1)) * 100);
  }

  // ── 5. Top Clientes y Mix Familias ─────────────────────
  if (payload.topClientes && payload.topClientes.length > 0) window.PCH.TOP_CLIENTES     = payload.topClientes;
  if (payload.mixFamilias  && payload.mixFamilias.length  > 0) window.PCH.MIX_FAMILIA     = payload.mixFamilias;
  if (payload.familiasMontoYTD && payload.familiasMontoYTD.length > 0) window.PCH.FAMILIAS_MONTO_YTD = payload.familiasMontoYTD;

  // ── 6. Equipo comercial ────────────────────────────────
  if (payload.equipo) {
    window.PCH.VENDEDORES = window.PCH.VENDEDORES.map(v => {
      const eq = payload.equipo[v.id];
      if (eq) {
        return {
          ...v,
          real: {
            cotizado:  Math.round((eq.cotizado  || 0) * 10) / 10,
            nv:        Math.round((eq.nv        || 0) * 10) / 10,
            facturado: Math.round((eq.facturado || 0) * 10) / 10,
          }
        };
      }
      return v;
    });
  }

  console.log('✅ Payload aplicado correctamente');
};