/* global React */

// ============================================================
// TAB 4: GLOSARIO Y FUENTES DE DATOS
// ============================================================
function GlosarioTab() {
  return (
    <React.Fragment>
      <div style={{padding:'12px 16px',background:'var(--bg-2)',borderBottom:'1px solid var(--border)'}}>
        <div className="flex between center-y">
          <div>
            <div className="fs-14 fw-7">Glosario de métricas y fuentes de datos</div>
            <div className="text-3 fs-11 mt-1">
              Todos los montos expresados en M$ CLP
              <span className="badge gray" style={{marginLeft:6}}>NETOS · SIN IVA</span>
              · Origen: Presupuesto P&amp;L 2026 + Manager ERP + GHL CRM
            </div>
          </div>
          <div className="flex gap-2">
            <span className="badge green">3 fuentes integradas</span>
            <span className="badge blue">Sync horario</span>
          </div>
        </div>
      </div>

      <div className="section-title">Convenciones generales</div>
      <div className="card" style={{marginBottom:10}}>
        <table className="tbl">
          <thead><tr><th style={{width:180}}>Concepto</th><th>Definición usada en este dashboard</th></tr></thead>
          <tbody>
            <tr><td className="strong">M$</td><td>Millones de pesos chilenos. Ej: <span className="mono">437,4 M$</span> = $437.400.000.</td></tr>
            <tr><td className="strong">Neto / sin IVA</td><td><strong>Todos</strong> los montos están expresados netos. El P&amp;L de Polchile se mide en valores netos.</td></tr>
            <tr><td className="strong">MTD</td><td><em>Month-to-date.</em> Acumulado desde el día 1 del mes actual hasta hoy.</td></tr>
            <tr><td className="strong">YTD</td><td><em>Year-to-date.</em> Acumulado desde enero hasta hoy.</td></tr>
            <tr><td className="strong">YoY</td><td><em>Year-over-year.</em> Mismo período del año anterior.</td></tr>
            <tr><td className="strong">WoW</td><td><em>Week-over-week.</em> Misma semana de la semana previa.</td></tr>
            <tr><td className="strong">Día hábil</td><td>Lunes a viernes excluyendo feriados oficiales.</td></tr>
            <tr><td className="strong">"Hoy"</td><td>Fecha de visualización. Se toma de <span className="mono">Date.now()</span> en zona horaria <span className="mono">America/Santiago</span>.</td></tr>
          </tbody>
        </table>
      </div>

      <div className="section-title">Fuentes de datos · 3 sistemas integrados</div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:10,marginBottom:10}}>
        <FuenteCard
          color="#5b8cff" nombre="Presupuesto P&L 2026"
          tipo="Google Sheet · estático" frecuencia="Carga única + ajustes mensuales"
          owner="Hugo Ponce / Cristóbal Bretón"
          datos={['Presupuesto anual: 5.400 M$ neto (escenario base)','Estacionalidad mensual oficial (12 valores)','Mix por pilar (Proyectos 90% / Ecom 5% / Distrib. 5%)','Mix por familia y márgenes objetivo','Costos depto. comercial','Metas individuales por vendedor']}
        />
        <FuenteCard
          color="#10b981" nombre="Manager ERP"
          tipo="Sistema transaccional · base de datos" frecuencia="Sync diario vía pipeline Python"
          owner="IT / Administración"
          datos={['Cotizaciones emitidas (monto neto, cliente, vendedor, fecha)','Notas de Venta (NV) con monto neto','Facturas emitidas (FAV − NCV)','Despachos confirmados','Cuentas por cobrar (aging por cliente)','Detalle por familia/clase de producto (CLASE1)']}
        />
        <FuenteCard
          color="#a855f7" nombre="Go High Level (GHL)"
          tipo="CRM · API REST" frecuencia="Sync cada 1h vía Apps Script"
          owner="Cristóbal Bretón / Hugo Ponce"
          datos={['Pipeline "Televenta" — etapas y oportunidades','Monto bruto pipeline (suma de oportunidades abiertas)','Probabilidades por etapa (configurables en Sheet)','Atribución de leads por fuente (Google Ads, Meta, etc.)','Tags de cliente (Nuevo / Recurrente)','Última actividad por contacto']}
        />
      </div>

      <div className="section-title">KPIs principales (strip superior)</div>
      <div className="card tight" style={{marginBottom:10}}>
        <table className="tbl">
          <thead><tr><th style={{width:170}}>KPI</th><th style={{width:120}}>Fuente</th><th>Cálculo</th><th style={{width:100}}>Unidad</th></tr></thead>
          <tbody>
            <MetricRow nombre="Presupuesto Mes"      fuente="Presupuesto" calc="Presupuesto anual × % estacionalidad del mes. Ej. junio = 5.400 × 9,30% = 502,2 M$."                            unit="M$ neto"/>
            <MetricRow nombre="Facturado MTD"        fuente="Manager ERP" calc="Σ monto neto de todas las FAV emitidas desde día 1 del mes hasta hoy, menos NCV."                               unit="M$ neto"/>
            <MetricRow nombre="NV Emitidas MTD"      fuente="Manager ERP" calc="Σ monto neto de las Notas de Venta emitidas en el mes."                                                          unit="M$ neto"/>
            <MetricRow nombre="Cotizado MTD"         fuente="Manager ERP" calc="Σ monto neto de cotizaciones emitidas en el mes (no necesariamente convertidas)."                                unit="M$ neto"/>
            <MetricRow nombre="Forecast Cierre Mes"  fuente="Calculado"   calc="Facturado + NV + (Backlog × 70%) + (Cotizado × 24%)."                                                           unit="M$ neto"/>
            <MetricRow nombre="Pipeline Ponderado"   fuente="GHL"         calc="Σ (monto_etapa × prob_etapa). Probabilidades por etapa configurables en GHL_PipelineSummary."                   unit="M$ neto"/>
            <MetricRow nombre="Cumplimiento"         fuente="Calculado"   calc="Forecast mes ÷ Presupuesto del mes × 100."                                                                       unit="%"/>
            <MetricRow nombre="Run-rate requerido"   fuente="Calculado"   calc="(Presupuesto mes − Facturado MTD) ÷ días hábiles restantes."                                                    unit="M$/día"/>
            <MetricRow nombre="Backlog NV→Fact"      fuente="Manager ERP" calc="Σ NV emitidas con status abierto, sin factura asociada al cierre del día."                                      unit="M$ neto"/>
          </tbody>
        </table>
      </div>

      <div className="section-title">Pipeline CRM y conversión</div>
      <div className="card tight" style={{marginBottom:10}}>
        <table className="tbl">
          <thead><tr><th style={{width:170}}>Métrica</th><th style={{width:120}}>Fuente</th><th>Cálculo</th><th style={{width:100}}>Unidad</th></tr></thead>
          <tbody>
            <MetricRow nombre="Etapas pipeline"       fuente="GHL"       calc='Pipeline "Televenta". Etapas: Lead Nuevo → Contactado → Calificado → Cotización Enviada → Negociación → NV en Proceso → Ganado.' unit="—"/>
            <MetricRow nombre="Monto bruto pipeline"  fuente="GHL"       calc="Σ monto neto de oportunidades abiertas."                                                                                           unit="M$ neto"/>
            <MetricRow nombre="Probabilidad por etapa" fuente="Manual"   calc="Default: 5/15/30/50/70/90/100%. Sobrescribible vía pestaña GHL_PipelineSummary."                                                  unit="%"/>
            <MetricRow nombre="Forecast ponderado"    fuente="Calculado" calc="Σ (monto × prob ÷ 100) por etapa."                                                                                                 unit="M$ neto"/>
            <MetricRow nombre="Win rate"              fuente="Calculado" calc="Oportunidades Ganadas ÷ oportunidades cerradas (Ganado + Perdido) en el período."                                                  unit="%"/>
            <MetricRow nombre="Ciclo promedio"        fuente="GHL"       calc="Promedio de días entre fecha de creación de oportunidad y fecha de cierre."                                                        unit="días"/>
            <MetricRow nombre="Conv. cot → NV"        fuente="Manager"   calc="N° cotizaciones convertidas a NV ÷ N° cotizaciones emitidas (mismo período)."                                                     unit="%"/>
            <MetricRow nombre="Conv. NV → Factura"    fuente="Manager"   calc="Monto NV facturado ÷ Monto NV emitido (con desfase de hasta 30 días)."                                                            unit="%"/>
          </tbody>
        </table>
      </div>

      <div className="section-title">Mix de productos y clientes</div>
      <div className="card tight" style={{marginBottom:10}}>
        <table className="tbl">
          <thead><tr><th style={{width:170}}>Métrica</th><th style={{width:120}}>Fuente</th><th>Cálculo</th><th style={{width:100}}>Unidad</th></tr></thead>
          <tbody>
            <MetricRow nombre="Mix por pilar"         fuente="Manager ERP" calc="Proyectos / Ecommerce / Distribución. Mix = facturado pilar ÷ facturado total mes."   unit="%"/>
            <MetricRow nombre="Mix por familia"       fuente="Manager ERP" calc="Familias desde campo CLASE1. Mix por familia = facturado familia ÷ total."            unit="%"/>
            <MetricRow nombre="Margen real"           fuente="Manager ERP" calc="(TOTAL_NETO − CTO_PROMEDIO_TOTAL) ÷ TOTAL_NETO. Desde hoja Ventas Full Manager."     unit="%"/>
            <MetricRow nombre="Margen presupuestado"  fuente="Presupuesto" calc="Margen objetivo definido en P&L 2026 por familia desde Supuestos y Parámetros."       unit="%"/>
            <MetricRow nombre="Top 10 clientes YTD"   fuente="Manager ERP" calc="Ranking por Σ FAV neto YTD. Tipo (Nuevo/Recurrente) según fecha primer compra."      unit="M$ neto"/>
            <MetricRow nombre="Concentración Pareto"  fuente="Calculado"   calc="% del total YTD que representan los Top 10. Sobre 60% = concentración alta."          unit="%"/>
          </tbody>
        </table>
      </div>

      <div className="section-title">Equipo comercial y costos</div>
      <div className="card tight" style={{marginBottom:10}}>
        <table className="tbl">
          <thead><tr><th style={{width:170}}>Métrica</th><th style={{width:120}}>Fuente</th><th>Cálculo</th><th style={{width:100}}>Unidad</th></tr></thead>
          <tbody>
            <MetricRow nombre="Meta mensual vendedor" fuente="Presupuesto" calc="Ejecutivos: 81 M$/mes; KAM: 22,5; Ecommerce: 22,5; Jefe Ventas: 0 (gestiona equipo)." unit="M$ neto"/>
            <MetricRow nombre="Cumplimiento individual" fuente="Calculado" calc="Facturado MTD del vendedor ÷ Meta mes × 100."                                          unit="%"/>
            <MetricRow nombre="Comisión proyectada"   fuente="Calculado"   calc="Facturado MTD × % comisión (0,75% ejecutivos / 0,35% jefatura)."                      unit="M$"/>
            <MetricRow nombre="Ahorro Gerente Comercial" fuente="Presupuesto" calc="Sueldo presupuestado del cargo no ocupado (~4,94 M$/mes)."                          unit="M$"/>
            <MetricRow nombre="Bono Jefe de Ventas"   fuente="Acuerdo"     calc="350 K$/mes por asumir gerencia interina."                                              unit="K$/mes"/>
            <MetricRow nombre="Costo neto comercial"  fuente="Calculado"   calc="Costo total comercial − Ahorro Gerente Comercial."                                     unit="M$/mes"/>
          </tbody>
        </table>
      </div>

      <div className="section-title">Frecuencia de actualización por origen</div>
      <div className="card" style={{marginBottom:10}}>
        <table className="tbl">
          <thead><tr><th>Origen</th><th>Frecuencia actual</th><th>Frecuencia objetivo</th><th>Tecnología</th></tr></thead>
          <tbody>
            <tr>
              <td><span className="status-dot" style={{background:'#5b8cff',marginRight:6}}></span>Presupuesto P&amp;L 2026</td>
              <td className="text-2">Carga única</td><td className="text-2">Ajuste mensual</td>
              <td className="mono fs-11">Google Sheet</td>
            </tr>
            <tr>
              <td><span className="status-dot" style={{background:'#10b981',marginRight:6}}></span>Manager ERP</td>
              <td className="text-2 t-up">Activo · diario</td><td className="text-2">Cada 1 hora</td>
              <td className="mono fs-11">Python + SQL Server + Google Sheets</td>
            </tr>
            <tr>
              <td><span className="status-dot" style={{background:'#a855f7',marginRight:6}}></span>GHL CRM</td>
              <td className="text-2 t-up">Activo · 1h</td><td className="text-2">Cada 15 min (webhook)</td>
              <td className="mono fs-11">REST API · Apps Script</td>
            </tr>
            <tr>
              <td><span className="status-dot" style={{background:'#f59e0b',marginRight:6}}></span>BUK (RRHH)</td>
              <td className="text-2 t-warn">Manual</td><td className="text-2">Mensual al cierre planilla</td>
              <td className="mono fs-11">Carga CSV</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="section-title">Alertas automáticas</div>
      <div className="card" style={{marginBottom:10}}>
        <table className="tbl">
          <thead><tr><th>Alerta</th><th style={{width:120}}>Severidad</th><th>Trigger</th></tr></thead>
          <tbody>
            <tr><td className="strong">Forecast por debajo de meta</td><td><span className="badge red">Crítica</span></td><td>Forecast cierre mes &lt; 90% de presupuesto.</td></tr>
            <tr><td className="strong">Pipeline insuficiente</td><td><span className="badge red">Crítica</span></td><td>Pipeline ponderado &lt; 80% del faltante mensual.</td></tr>
            <tr><td className="strong">Cotizaciones estancadas</td><td><span className="badge amber">Alta</span></td><td>Cotización con &gt;15 días sin cambio de etapa.</td></tr>
            <tr><td className="strong">NV sin facturar</td><td><span className="badge amber">Alta</span></td><td>NV emitida &gt;7 días sin factura asociada.</td></tr>
            <tr><td className="strong">Vendedor bajo cumplimiento</td><td><span className="badge amber">Media</span></td><td>Cumplimiento individual &lt;75% al día 16 del mes.</td></tr>
            <tr><td className="strong">DSO subiendo</td><td><span className="badge amber">Media</span></td><td>DSO &gt;40 días por 2 meses consecutivos.</td></tr>
          </tbody>
        </table>
      </div>

      <div className="section-title">Notas importantes</div>
      <div className="card" style={{marginBottom:20}}>
        <ul style={{paddingLeft:18,lineHeight:1.7}} className="fs-12 text-2">
          <li><strong className="text-1">IVA:</strong> el dashboard nunca muestra montos con IVA. Para valor bruto multiplicar × 1,19.</li>
          <li><strong className="text-1">Seguridad:</strong> el dashboard requiere autenticación Firebase. Sin sesión activa no se muestran datos reales.</li>
          <li><strong className="text-1">Escenarios:</strong> el switch PES / BASE / OPT reescala el presupuesto anual ±20%. No afecta datos reales.</li>
          <li><strong className="text-1">Zona horaria:</strong> America/Santiago. Días hábiles calculados según calendario chileno.</li>
          <li><strong className="text-1">Persistencia:</strong> el dashboard no almacena datos localmente. Los lee del Google Sheet en cada sesión via Firebase Function.</li>
          <li><strong className="text-1">Refresco:</strong> los datos se actualizan automáticamente cada 5 minutos mientras la sesión esté activa.</li>
        </ul>
      </div>
    </React.Fragment>
  );
}

// ============================================================
// FUENTE CARD
// ============================================================
function FuenteCard({ color, nombre, tipo, frecuencia, owner, datos }) {
  return (
    <div className="card">
      <div className="flex center-y gap-2 mb-2">
        <span style={{width:10,height:10,borderRadius:2,background:color,display:'inline-block'}}></span>
        <span className="fw-7 fs-13">{nombre}</span>
      </div>
      <div className="text-3 fs-10 uppercase mb-1">Tipo</div>
      <div className="fs-12 mb-2">{tipo}</div>
      <div className="text-3 fs-10 uppercase mb-1">Frecuencia</div>
      <div className="fs-12 mb-2">{frecuencia}</div>
      <div className="text-3 fs-10 uppercase mb-1">Owner</div>
      <div className="fs-12 mb-2">{owner}</div>
      <div className="text-3 fs-10 uppercase mb-1" style={{paddingTop:6,borderTop:'1px solid var(--border-soft)'}}>Datos que aporta</div>
      <ul style={{paddingLeft:16,marginTop:4}} className="fs-11 text-2">
        {datos.map((d,i) => <li key={i} style={{marginBottom:3}}>{d}</li>)}
      </ul>
    </div>
  );
}

// ============================================================
// METRIC ROW
// ============================================================
function MetricRow({ nombre, fuente, calc, unit }) {
  const colores = {
    'Presupuesto':'blue','Manager ERP':'green','Manager':'green',
    'GHL':'gray','Calculado':'amber','Manual':'gray',
    'Acuerdo':'gray','BUK / RRHH':'gray',
  };
  const bc = colores[fuente] || 'gray';
  return (
    <tr>
      <td className="strong">{nombre}</td>
      <td><span className={'badge '+bc}>{fuente}</span></td>
      <td className="text-2 fs-12">{calc}</td>
      <td className="mono text-3 fs-11">{unit}</td>
    </tr>
  );
}

window.GlosarioTab = GlosarioTab;