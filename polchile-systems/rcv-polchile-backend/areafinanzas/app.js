/* ---------------------------------------------------------
   Estado de la app (en memoria, no persiste entre sesiones)
--------------------------------------------------------- */
let state = {
  mode: 'demo',           // 'demo' | 'live'
  tipoActivo: 'compra',   // 'compra' | 'venta'
  documentos: { compra: [], venta: [] },
  seleccionados: new Set(),
  cargando: false,
};

/* ---------------------------------------------------------
   Generador de datos de ejemplo (modo Demo)
--------------------------------------------------------- */
function generarDemo(periodo){
  const tiposDoc = ['Factura Electr\u00f3nica','Nota de Cr\u00e9dito','Nota de D\u00e9bito','Factura Exenta'];
  const empresas = [
    'Aceros del Pac\u00edfico Ltda.','Comercial Rioblanco SpA','Distribuidora Andes S.A.',
    'Poliuretanos del Sur Ltda.','Transportes Cordillera SpA','Insumos Industriales Maule',
    'Metalmec\u00e1nica Bio Bio S.A.','Constructora Los Alerces Ltda.'
  ];
  const estados = ['pendiente','aceptado','reclamado'];
  const out = { compra: [], venta: [] };
  ['compra','venta'].forEach(tipo=>{
    const n = 9 + Math.floor(Math.random()*6);
    for(let i=0;i<n;i++){
      const neto = Math.round((80000 + Math.random()*1800000)/10)*10;
      const iva = Math.round(neto*0.19);
      out[tipo].push({
        id: tipo+'-'+i,
        origen: tipo,
        subido: false,
        folio: 100000 + Math.floor(Math.random()*899999),
        tipoDoc: tiposDoc[Math.floor(Math.random()*tiposDoc.length)],
        rut: (Math.floor(Math.random()*90000000)+9000000)+'-'+Math.floor(Math.random()*9),
        razonSocial: empresas[Math.floor(Math.random()*empresas.length)],
        fecha: periodo+'-'+String(1+Math.floor(Math.random()*27)).padStart(2,'0'),
        neto, iva, total: neto+iva,
        estado: estados[Math.floor(Math.random()*estados.length)]
      });
    }
  });
  return out;
}

/* ---------------------------------------------------------
   Consulta al backend propio (no a SimpleAPI directo).
   El backend guarda el certificado .pfx, su password y el ApiKey
   en variables de entorno — el navegador nunca los ve.
--------------------------------------------------------- */
async function consultarRCV(periodo){
  const resp = await fetch(`/api/rcv?periodo=${encodeURIComponent(periodo)}`);
  const data = await resp.json().catch(()=>({}));
  if(!resp.ok) throw new Error(data.error || `Error del backend (${resp.status})`);
  return { compra: data.compra || [], venta: data.venta || [] };
}

/* ---------------------------------------------------------
   Render
--------------------------------------------------------- */
function fmt(n){ return '$'+n.toLocaleString('es-CL'); }

function docsVista(){
  if(state.tipoActivo === 'subidas'){
    return [...state.documentos.compra, ...state.documentos.venta].filter(d=>d.subido);
  }
  return (state.documentos[state.tipoActivo] || []).filter(d=>!d.subido);
}

function renderSummary(){
  const docs = docsVista();
  const neto = docs.reduce((a,d)=>a+d.neto,0);
  const iva = docs.reduce((a,d)=>a+d.iva,0);
  const total = docs.reduce((a,d)=>a+d.total,0);
  document.getElementById('summary').innerHTML = `
    <div class="card"><div class="label">Documentos</div><div class="value">${docs.length}</div></div>
    <div class="card"><div class="label">Monto neto</div><div class="value">${fmt(neto)}</div></div>
    <div class="card azul"><div class="label">IVA</div><div class="value">${fmt(iva)}</div></div>
    <div class="card celeste"><div class="label">Total</div><div class="value">${fmt(total)}</div></div>
  `;
}

function renderTable(){
  const docs = docsVista();
  const esSubidas = state.tipoActivo === 'subidas';
  const wrap = document.getElementById('table-wrap');
  if(!docs.length){
    const vacioTexto = esSubidas
      ? 'A\u00fan no hay facturas cargadas a Manager. Las que subas desde Compras o Ventas aparecer\u00e1n aqu\u00ed.'
      : `A\u00fan no hay ${state.tipoActivo === 'compra' ? 'facturas de compra' : 'facturas de venta'} pendientes. Ingresa el per\u00edodo y presiona <strong>Consultar RCV</strong>.`;
    wrap.innerHTML = `
      <div class="empty-state">
        <div class="glyph">&sect;</div>
        <p>${vacioTexto}</p>
      </div>`;
    return;
  }
  const esCompra = state.tipoActivo === 'compra';
  const rows = docs.map(d => {
    let detalleCell = '';
    if(esCompra){
      let estadoDetalle = '<span class="detalle-pendiente">buscando&hellip;</span>';
      if(d.items === null) estadoDetalle = '<span class="detalle-error">sin XML</span>';
      else if(Array.isArray(d.items)) estadoDetalle = '<span class="detalle-listo">&#10003; listo</span>';
      detalleCell = `<td><button class="btn-fila-detalle" data-id="${d.id}">Ver detalle</button> ${estadoDetalle}</td>`;
    }
    return `
    <tr>
      ${esSubidas ? '' : `<td class="checkbox-cell"><input type="checkbox" data-id="${d.id}" ${state.seleccionados.has(d.id)?'checked':''}></td>`}
      ${esSubidas ? `<td><span class="tipo-badge ${d.origen}">${d.origen === 'compra' ? 'Compra' : 'Venta'}</span></td>` : ''}
      <td class="mono">${d.folio}</td>
      <td>${d.tipoDoc}</td>
      <td class="mono">${d.rut}</td>
      <td>${d.razonSocial}</td>
      <td class="mono">${d.fecha}</td>
      <td class="num">${fmt(d.neto)}</td>
      <td class="num">${fmt(d.iva)}</td>
      <td class="num">${fmt(d.total)}</td>
      <td><span class="stamp ${d.estado}">${d.estado}</span></td>
      ${detalleCell}
    </tr>`;
  }).join('');
  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          ${esSubidas ? '<th>Tipo</th>' : '<th></th>'}
          <th>Folio</th><th>Tipo Doc.</th><th>RUT</th><th>Raz&oacute;n social</th>
          <th>Fecha</th><th>Neto</th><th>IVA</th><th>Total</th><th>Estado</th>
          ${esCompra ? '<th>Detalle</th>' : ''}
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  wrap.querySelectorAll('input[type=checkbox]').forEach(cb=>{
    cb.addEventListener('change', e=>{
      const id = e.target.dataset.id;
      if(e.target.checked) state.seleccionados.add(id);
      else state.seleccionados.delete(id);
      renderActionBar();
    });
  });
  wrap.querySelectorAll('.btn-fila-detalle').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const doc = (state.documentos.compra || []).find(d => d.id === btn.dataset.id);
      if(!doc) return;
      document.getElementById('f-folio').value = doc.folio;
      document.getElementById('folio-panel').scrollIntoView({behavior:'smooth', block:'start'});
      folioActual = doc.folio;
      proveedorActual = doc.razonSocial;
      fechaActual = doc.fecha;

      if(Array.isArray(doc.items)){
        // Ya se trajo autom\u00e1ticamente al consultar el RCV - instant\u00e1neo
        itemsActuales = doc.items;
        renderItemsFolio();
      } else {
        // No se encontr\u00f3 antes (o a\u00fan est\u00e1 buscando) - reintentar
        btn.disabled = true; btn.textContent = 'Buscando...';
        try{
          doc.items = await obtenerItemsFactura(doc);
          itemsActuales = doc.items;
          renderItemsFolio();
        } catch(err){
          mostrarToast('No se encontr\u00f3 el XML para este folio: '+err.message);
        } finally {
          btn.disabled = false; btn.textContent = 'Ver detalle';
        }
      }
    });
  });
}

function renderActionBar(){
  const slot = document.getElementById('action-bar-slot');
  if(state.tipoActivo === 'subidas'){ slot.innerHTML=''; return; }
  const docs = docsVista();
  const sel = docs.filter(d=>state.seleccionados.has(d.id));
  if(!sel.length){ slot.innerHTML=''; return; }
  const total = sel.reduce((a,d)=>a+d.total,0);
  const etiquetaModulo = state.tipoActivo === 'compra' ? 'Facturas de Compra' : 'Facturas de Venta';
  slot.innerHTML = `
    <div class="action-bar">
      <div class="sel-info"><b>${sel.length}</b> seleccionados <span class="amounts">&middot; ${fmt(total)}</span></div>
      <div class="action-bar-btns">
        <button class="btn secondary" id="btn-limpiar">Limpiar selecci\u00f3n</button>
        <button class="btn" id="btn-enviar">Cargar ${etiquetaModulo} a Manager</button>
      </div>
    </div>
  `;
  document.getElementById('btn-limpiar').addEventListener('click', ()=>{
    state.seleccionados.clear(); renderTable(); renderActionBar();
  });
  document.getElementById('btn-enviar').addEventListener('click', ()=>cargarAManager(sel));
}

/* ---------------------------------------------------------
   Carga a Manager (api2) - la llamada real la hace el backend,
   que guarda la URL/Business ID/ApiKey de Manager en .env
--------------------------------------------------------- */
async function cargarAManager(documentos){
  const statusEl = document.getElementById('mp-status');

  if(state.mode === 'demo'){
    await new Promise(r=>setTimeout(r, 400));
    documentos.forEach(d=>{ d.subido = true; state.seleccionados.delete(d.id); });
    statusEl.textContent = 'simulado (demo)';
    statusEl.classList.remove('ok');
    mostrarToast(`Manager (demo): ${documentos.length} documento(s) marcados como subidos.`);
    renderSummary(); renderTable(); renderActionBar();
    return;
  }

  try{
    const resp = await fetch('/api/manager/upload', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ tipo: state.tipoActivo, documentos })
    });
    const data = await resp.json();
    if(!resp.ok) throw new Error(data.error || 'Error al cargar a Manager');

    const okIds = new Set(data.resultados.filter(r=>r.ok).map(r=>r.id));
    const ok = okIds.size, fallidos = data.resultados.length - ok;
    documentos.forEach(d=>{ if(okIds.has(d.id)){ d.subido = true; state.seleccionados.delete(d.id); } });

    statusEl.textContent = fallidos === 0 ? 'conectado' : `${ok} ok / ${fallidos} error`;
    statusEl.classList.toggle('ok', fallidos === 0);
    mostrarToast(`Manager: ${ok} documento(s) cargados, ${fallidos} con error.`);
    renderSummary(); renderTable(); renderActionBar();
  } catch(err){
    mostrarToast('Error: '+err.message);
  }
}

function mostrarToast(msg){
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(), 3600);
}

function renderAll(){ renderSummary(); renderTable(); renderActionBar(); }

/* ---------------------------------------------------------
   Eventos
--------------------------------------------------------- */
const MODULOS = {
  compra: {
    titulo: 'Facturas de Compra',
    subtitulo: 'Documentos recibidos de proveedores, seg\u00fan el Registro de Compras y Ventas del SII.'
  },
  venta: {
    titulo: 'Facturas de Venta',
    subtitulo: 'Documentos emitidos a clientes, seg\u00fan el Registro de Compras y Ventas del SII.'
  },
  subidas: {
    titulo: 'Facturas Subidas',
    subtitulo: 'Documentos de compra y venta ya cargados a Manager.'
  },
  transferencias: {
    titulo: 'Transferencias',
    subtitulo: 'Confirmaci\u00f3n de transferencias recibidas y saldo disponible, v\u00eda Boufin sobre Banco Santander.'
  }
};

document.querySelectorAll('.navitem').forEach(item=>{
  item.addEventListener('click', ()=>{
    document.querySelectorAll('.navitem').forEach(i=>i.classList.remove('active'));
    item.classList.add('active');
    state.tipoActivo = item.dataset.tipo;
    const m = MODULOS[state.tipoActivo];
    document.getElementById('titulo').textContent = m.titulo;
    document.getElementById('subtitulo').textContent = m.subtitulo;
    state.seleccionados.clear();

    const esTransferencias = state.tipoActivo === 'transferencias';
    const esSubidas = state.tipoActivo === 'subidas';

    document.querySelector('.config').style.display = (esSubidas || esTransferencias) ? 'none' : 'flex';
    document.getElementById('notice').style.display = (esSubidas || esTransferencias) ? 'none' : 'block';
    document.querySelector('.manager-panel').style.display = (esSubidas || esTransferencias) ? 'none' : 'block';
    document.getElementById('folio-panel').style.display = state.tipoActivo === 'compra' ? 'block' : 'none';

    document.getElementById('summary').style.display = esTransferencias ? 'none' : 'grid';
    document.getElementById('table-wrap').style.display = esTransferencias ? 'none' : 'block';
    document.getElementById('action-bar-slot').style.display = esTransferencias ? 'none' : 'block';
    document.getElementById('transferencias-view').style.display = esTransferencias ? 'block' : 'none';

    if(esTransferencias && !document.getElementById('saldo-valor').dataset.cargado){
      actualizarTransferencias();
    }
    renderAll();
  });
});

document.getElementById('mode-demo').addEventListener('click', ()=>{
  state.mode='demo';
  document.getElementById('mode-demo').classList.add('active');
  document.getElementById('mode-live').classList.remove('active');
  document.getElementById('notice').innerHTML = '<strong>Modo Demo activo.</strong> Se muestran datos de ejemplo para revisar el dise\u00f1o y el flujo. Cambia a <strong>Conectado</strong> para consultar el SII real a trav\u00e9s de tu backend.';
});
document.getElementById('mode-live').addEventListener('click', ()=>{
  state.mode='live';
  document.getElementById('mode-live').classList.add('active');
  document.getElementById('mode-demo').classList.remove('active');
  document.getElementById('notice').innerHTML = '<strong>Modo Conectado.</strong> La consulta demora entre 40 y 120 segundos (SimpleAPI hace scraping en vivo al SII). Las credenciales viven en el backend, no aqu\u00ed.';
});

document.getElementById('btn-consultar').addEventListener('click', async ()=>{
  const periodo = document.getElementById('f-periodo').value; // YYYY-MM
  const btn = document.getElementById('btn-consultar');
  btn.disabled = true; btn.textContent = 'Consultando...';
  state.seleccionados.clear();
  try{
    if(state.mode === 'demo'){
      await new Promise(r=>setTimeout(r, 500));
      state.documentos = generarDemo(periodo || '2026-07');
    } else {
      btn.textContent = 'Consultando SII (puede tardar ~1-2 min)...';
      state.documentos = await consultarRCV(periodo);
    }
    renderAll();

    // Trae autom\u00e1ticamente el detalle (\u00edtems) de cada factura de compra,
    // buscando el XML en el correo por folio, para que "Ver detalle" quede
    // instant\u00e1neo y solo falte llenar c\u00f3digo/cuenta contable.
    const compras = state.documentos.compra || [];
    for(let i=0; i<compras.length; i++){
      const doc = compras[i];
      btn.textContent = `Trayendo detalle ${i+1}/${compras.length}...`;
      try{
        doc.items = await obtenerItemsFactura(doc);
      } catch(err){
        doc.items = null; // no se encontr\u00f3 o fall\u00f3 - se puede reintentar con "Ver detalle"
      }
      if(state.tipoActivo === 'compra') renderTable(); // refleja el avance en vivo
    }
  } catch(err){
    mostrarToast('Error: '+err.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Consultar RCV';
  }
});

/* Estado de la conexión a Manager, consultado al backend al cargar */
fetch('/api/manager/status').then(r=>r.json()).then(data=>{
  const el = document.getElementById('mp-status');
  if(!el) return;
  el.textContent = data.configurado ? 'configurado' : 'sin configurar';
  el.classList.toggle('ok', data.configurado);
}).catch(()=>{});

/* ---------------------------------------------------------
   Carga masiva por folio: buscar en correo -> items del XML ->
   finanzas asigna c\u00f3digo -> cuenta contable se autocompleta
--------------------------------------------------------- */
let folioActual = null;
let proveedorActual = '';
let fechaActual = '';
let itemsActuales = [];

function fmtN(n){ return Number(n||0).toLocaleString('es-CL'); }

/* Trae los \u00edtems de una factura puntual (por folio), sea en Demo o real.
   La usan tanto el prefetch autom\u00e1tico como el bot\u00f3n "Ver detalle". */
async function obtenerItemsFactura(doc){
  if(state.mode === 'demo'){
    await new Promise(r=>setTimeout(r, 150 + Math.random()*250));
    // ~85% de las facturas demo "encuentran" el XML, para simular casos sin correo
    if(Math.random() < 0.15) return null;
    const catalogo = [
      { descripcion:'Panel PurP 50mm', precioUnitario:18500 },
      { descripcion:'Perfil U galvanizado', precioUnitario:6200 },
      { descripcion:'Tornillo autoperforante', precioUnitario:35 },
      { descripcion:'Sellador poliuretano', precioUnitario:4200 },
      { descripcion:'Plancha ZA prepintada', precioUnitario:12900 },
    ];
    const n = 1 + Math.floor(Math.random()*3);
    return Array.from({length:n}, (_, i) => {
      const base = catalogo[Math.floor(Math.random()*catalogo.length)];
      const cantidad = 1 + Math.floor(Math.random()*30);
      return {
        id:`item-${doc.id}-${i}`, descripcion:base.descripcion, cantidad,
        precioUnitario:base.precioUnitario, monto:cantidad*base.precioUnitario,
        codigo:'', cuentaContable:''
      };
    });
  }
  const resp = await fetch(`/api/dte/folio/${encodeURIComponent(doc.folio)}`);
  const data = await resp.json();
  if(!resp.ok) throw new Error(data.error || 'No se encontró la factura');
  return data.items;
}

document.getElementById('btn-buscar-folio').addEventListener('click', ()=>{
  const folio = document.getElementById('f-folio').value.trim();
  if(!folio){ mostrarToast('Ingresa un folio.'); return; }
  buscarFolio(folio, '', '');
});

async function buscarFolio(folio, proveedor, fecha){
  const resultDiv = document.getElementById('folio-resultado');
  const btn = document.getElementById('btn-buscar-folio');
  btn.disabled = true; btn.textContent = 'Buscando...';
  resultDiv.innerHTML = '';
  proveedorActual = proveedor || '';
  fechaActual = fecha || '';

  try{
    const items = await obtenerItemsFactura({ id:'manual-'+folio, folio });
    if(!items) throw new Error(`No se encontró el XML del folio ${folio} en la casilla DTE`);
    folioActual = folio;
    itemsActuales = items;
    renderItemsFolio();
  } catch(err){
    mostrarToast('Error: '+err.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Buscar en correo';
  }
}

function renderItemsFolio(){
  const resultDiv = document.getElementById('folio-resultado');
  if(!itemsActuales.length){
    resultDiv.innerHTML = '<p style="font-size:12.5px;color:var(--ink-soft);">No se encontraron ítems para este folio.</p>';
    return;
  }
  const filas = itemsActuales.map(it => `
    <tr data-id="${it.id}">
      <td>${it.descripcion}</td>
      <td class="num">${it.cantidad}</td>
      <td class="num">${fmtN(it.precioUnitario)}</td>
      <td class="num">${fmtN(it.monto)}</td>
      <td><input type="text" class="input-codigo" data-id="${it.id}" placeholder="Código" value="${it.codigo||''}"></td>
      <td><input type="text" class="input-cuenta ${it.cuentaContable ? 'cuenta-ok' : ''}" data-id="${it.id}" placeholder="Cuenta contable" value="${it.cuentaContable||''}"></td>
    </tr>
  `).join('');

  resultDiv.innerHTML = `
    <table class="items-table">
      <thead>
        <tr>
          <th>Descripci\u00f3n</th><th>Cant.</th><th>Precio Unit.</th><th>Monto</th>
          <th>C\u00f3digo</th><th>Cuenta Contable</th>
        </tr>
      </thead>
      <tbody>${filas}</tbody>
    </table>
    <div class="items-foot">
      <span style="font-size:12px;color:var(--ink-soft);">Folio <b>${folioActual}</b> &middot; ${itemsActuales.length} \u00edtem(s)</span>
      <button class="btn" id="btn-cargar-detalle">Cargar detalle a Manager</button>
    </div>
  `;

  resultDiv.querySelectorAll('.input-codigo').forEach(inp=>{
    inp.addEventListener('change', async (e)=>{
      const id = e.target.dataset.id;
      const item = itemsActuales.find(i=>i.id===id);
      item.codigo = e.target.value.trim();
      const cuentaInput = resultDiv.querySelector(`.input-cuenta[data-id="${id}"]`);
      if(!item.codigo){ return; }
      cuentaInput.value = 'Buscando...';
      try{
        let cuenta;
        if(state.mode === 'demo'){
          await new Promise(r=>setTimeout(r, 250));
          cuenta = '5-1-' + item.codigo.slice(-3).padStart(3,'0');
        } else {
          const resp = await fetch(`/api/cuenta-contable/${encodeURIComponent(item.codigo)}`);
          const data = await resp.json();
          cuenta = data.encontrado ? data.cuenta : null;
        }
        if(cuenta){
          item.cuentaContable = cuenta;
          cuentaInput.value = cuenta;
          cuentaInput.classList.add('cuenta-ok');
          cuentaInput.classList.remove('cuenta-pendiente');
        } else {
          item.cuentaContable = '';
          cuentaInput.value = '';
          cuentaInput.placeholder = 'No encontrada — ingrésala';
          cuentaInput.classList.add('cuenta-pendiente');
          cuentaInput.classList.remove('cuenta-ok');
        }
      } catch(err){
        cuentaInput.value = '';
        mostrarToast('No se pudo buscar la cuenta contable: '+err.message);
      }
    });
  });

  resultDiv.querySelectorAll('.input-cuenta').forEach(inp=>{
    inp.addEventListener('change', (e)=>{
      const id = e.target.dataset.id;
      const item = itemsActuales.find(i=>i.id===id);
      item.cuentaContable = e.target.value.trim();
      e.target.classList.toggle('cuenta-ok', !!item.cuentaContable);
      e.target.classList.toggle('cuenta-pendiente', !item.cuentaContable);
    });
  });

  document.getElementById('btn-cargar-detalle').addEventListener('click', cargarDetalleAManager);
}

async function cargarDetalleAManager(){
  const faltantes = itemsActuales.filter(it => !it.codigo || !it.cuentaContable);
  if(faltantes.length){
    mostrarToast(`Falta código o cuenta contable en ${faltantes.length} ítem(s).`);
    return;
  }
  const btn = document.getElementById('btn-cargar-detalle');
  btn.disabled = true; btn.textContent = 'Cargando...';

  try{
    if(state.mode === 'demo'){
      await new Promise(r=>setTimeout(r, 500));
      mostrarToast(`(Demo) Folio ${folioActual}: ${itemsActuales.length} ítem(s) listos para Manager.`);
    } else {
      const resp = await fetch('/api/manager/upload-detalle', {
        method:'POST',
        headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({
          folio: folioActual,
          proveedor: proveedorActual,
          fecha: fechaActual || (document.getElementById('f-periodo').value + '-01'),
          items: itemsActuales
        })
      });
      const data = await resp.json();
      if(!resp.ok || !data.ok) throw new Error(data.error || 'Manager rechazó la carga');
      mostrarToast(`Folio ${folioActual} cargado a Manager con ${itemsActuales.length} ítem(s).`);
    }
    document.getElementById('folio-resultado').innerHTML = '';
    document.getElementById('f-folio').value = '';
    itemsActuales = []; folioActual = null; proveedorActual = ''; fechaActual = '';
  } catch(err){
    mostrarToast('Error: '+err.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Cargar detalle a Manager';
  }
}

/* ---------------------------------------------------------
   Transferencias (Boufin / Santander): saldo + movimientos recibidos
--------------------------------------------------------- */
function fmtCLP(n){ return '$'+Number(n||0).toLocaleString('es-CL'); }

async function actualizarTransferencias(){
  const btn = document.getElementById('btn-actualizar-transferencias');
  const saldoEl = document.getElementById('saldo-valor');
  const metaEl = document.getElementById('ultima-actualizacion');
  const tableWrap = document.getElementById('transferencias-table-wrap');

  btn.disabled = true; btn.textContent = 'Actualizando...';
  try{
    let data;
    if(state.mode === 'demo'){
      await new Promise(r=>setTimeout(r, 500));
      data = {
        saldo: 18450320,
        transferencias: [
          { id:1, fecha:'2026-07-27 09:14', monto:1250000, glosa:'Pago factura 88231', origen:'Constructora Los Alerces Ltda.' },
          { id:2, fecha:'2026-07-27 11:02', monto:430000,  glosa:'Abono parcial', origen:'Comercial Rioblanco SpA' },
          { id:3, fecha:'2026-07-26 16:40', monto:2100000, glosa:'Transferencia', origen:'Distribuidora Andes S.A.' },
        ]
      };
    } else {
      const resp = await fetch('/api/transferencias');
      data = await resp.json();
      if(!resp.ok) throw new Error(data.error || 'No se pudo consultar Boufin');
    }

    saldoEl.textContent = fmtCLP(data.saldo);
    saldoEl.dataset.cargado = '1';
    const ahora = new Date();
    metaEl.textContent = 'Actualizado ' + ahora.toLocaleTimeString('es-CL', {hour:'2-digit', minute:'2-digit'});

    if(!data.transferencias.length){
      tableWrap.innerHTML = `
        <div class="empty-state">
          <div class="glyph">&sect;</div>
          <p>No hay transferencias recibidas registradas.</p>
        </div>`;
    } else {
      const filas = data.transferencias.map(t => `
        <tr>
          <td class="mono">${t.fecha}</td>
          <td>${t.origen}</td>
          <td>${t.glosa}</td>
          <td class="num">${fmtCLP(t.monto)}</td>
        </tr>
      `).join('');
      tableWrap.innerHTML = `
        <table>
          <thead><tr><th>Fecha</th><th>Origen</th><th>Glosa</th><th>Monto</th></tr></thead>
          <tbody>${filas}</tbody>
        </table>`;
    }
  } catch(err){
    mostrarToast('Error: '+err.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Actualizar';
  }
}

document.getElementById('btn-actualizar-transferencias').addEventListener('click', actualizarTransferencias);

/* Render inicial con datos demo */
state.documentos = generarDemo('2026-07');
renderAll();
