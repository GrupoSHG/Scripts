// vales.js — arma los Excel de vales para el importador de Manager (12/11/2026).
//
// Modos (variable MODO):
//   hora  → llama a public.generar_vales_manager() (SQL en GrupoSHG_Systems,
//           Polchile_Systems/dashboard-produccion/vales_manager.sql), que arma un
//           par de vales por OP con el avance de planta de la última hora, y
//           escribe en ./salida los archivos de los vales nuevos.
//   dia   → junta los vales de hoy que aún no se marcan importados (resumen
//           diario por correo, 17:00 / 18:00 lunes y martes).
// Archivos: Excel 5.0 (BIFF5) con títulos, las 18 columnas A..R del diálogo
// "Instrucciones para la importación" de vales de Manager, un archivo para
// los ingresos (MOVIMIENTO I) y otro para las salidas (S). Texto en ASCII
// porque SheetJS escribe BIFF5 sin página de códigos.
// Deja ./salida/resumen.json para enviar.py (Drive + correo).
// El repo es público: el log solo muestra cantidades.
'use strict';
const fs = require('fs');
const path = require('path');
const XLSX = require('xlsx');

const URL = 'https://ffxopvzxyeacpbtxuagu.supabase.co';
const APIKEY = (process.env.SUPABASE_APIKEY || '').trim() || 'sb_publishable_7UxU-do4iR5rP7Fnx8kQiw_XqDLMaHc';
const JWT = process.env.SUPABASE_SERVICE_KEY;
const MODO = (process.env.MODO || 'hora').trim();
const SALIDA = path.join(__dirname, 'salida');

const COLUMNAS = ['NUMERO VALE', 'FECHA VALE', 'MOVIMIENTO', 'TIPO VALE', 'SUCURSAL', 'GLOSAS', 'CODIGOS', 'CANTIDAD',
  'BODEGA', 'COSTO', 'NUMERO OT', 'NUMERO OP', 'NUMERO LOTE', 'VENCIMIENTO', 'NUMERO SERIE', 'CTA CONTABLE',
  'CENTRO COSTO', 'BODEGA TRASPASO'];

const ascii = (s) => typeof s !== 'string' ? s : s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\x20-\x7e]/g, '');
const dma = (iso) => String(iso || '').slice(0, 10).split('-').reverse().join('/');

async function sb(ruta, opciones) {
  const r = await fetch(URL + ruta, {
    ...(opciones || {}),
    headers: { apikey: APIKEY, Authorization: 'Bearer ' + JWT, 'Accept-Profile': 'shg_dashboards',
      'Content-Profile': 'shg_dashboards', 'Content-Type': 'application/json', ...((opciones || {}).headers || {}) },
  });
  const txt = await r.text();
  if (!r.ok) throw new Error('Supabase HTTP ' + r.status + ' en ' + ruta.split('?')[0] + ': ' + txt.slice(0, 200));
  return txt ? JSON.parse(txt) : null;
}

// Filas del archivo: títulos + una fila por línea de vale.
function filas(vales, lineas) {
  const porVale = {};
  lineas.forEach(l => { (porVale[l.vale_id] = porVale[l.vale_id] || []).push(l); });
  const datos = [COLUMNAS.slice()];
  vales.forEach(v => {
    (porVale[v.id] || []).sort((a, b) => a.item - b.item).forEach(l => {
      datos.push([v.numero, dma(v.fecha), v.movimiento, '', 1, ascii(v.glosa || ''), l.codigo, Number(l.cantidad),
        l.bodega || v.bodega || '', '', '', Number(v.num_op), l.lote || '', '', '', '', '', '']);
    });
  });
  return datos;
}

function escribir(nombre, datos) {
  const ws = XLSX.utils.aoa_to_sheet(datos.map(f => f.map(ascii)));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Vales');
  XLSX.writeFile(wb, path.join(SALIDA, nombre), { bookType: 'biff5' });
}

async function main() {
  if (!JWT) throw new Error('Falta SUPABASE_SERVICE_KEY');
  fs.mkdirSync(SALIDA, { recursive: true });
  const inicio = new Date().toISOString();
  const ahora = new Date();
  const hoy = ahora.toLocaleDateString('sv-SE', { timeZone: 'America/Santiago' });
  const hora = ahora.toLocaleTimeString('sv-SE', { timeZone: 'America/Santiago', hour: '2-digit', minute: '2-digit' }).replace(':', '');

  let vales;
  if (MODO === 'hora') {
    const n = await sb('/rest/v1/rpc/generar_vales_manager', { method: 'POST', body: '{}', headers: { 'Content-Profile': 'public' } });
    console.log('OP con vales nuevos: ' + n);
    vales = await sb('/rest/v1/vales_manager?select=*&creado_en=gte.' + encodeURIComponent(inicio) + '&order=movimiento,numero');
  } else {
    vales = await sb('/rest/v1/vales_manager?select=*&fecha=eq.' + hoy + '&estado=eq.generado&order=movimiento,numero');
  }
  if (!vales.length) {
    console.log('Sin vales para enviar.');
    fs.writeFileSync(path.join(SALIDA, 'resumen.json'), JSON.stringify({ modo: MODO, vales: 0 }));
    return;
  }
  const ids = vales.map(v => v.id);
  const lineas = await sb('/rest/v1/vales_manager_lineas?select=*&vale_id=in.(' + ids.join(',') + ')&order=vale_id,item');

  const sufijo = MODO === 'hora' ? hoy.replace(/-/g, '') + '_' + hora : hoy.replace(/-/g, '') + '_dia';
  const ing = vales.filter(v => v.movimiento === 'I'), sal = vales.filter(v => v.movimiento === 'S');
  const archivos = [];
  if (ing.length) { const a = 'Vales_Ingreso_' + sufijo + '.xls'; escribir(a, filas(ing, lineas)); archivos.push(a); }
  if (sal.length) { const a = 'Vales_Salida_' + sufijo + '.xls'; escribir(a, filas(sal, lineas)); archivos.push(a); }

  // Resumen por OP para el correo (no se imprime en el log).
  const porOp = {};
  vales.forEach(v => {
    const o = porOp[v.num_op] = porOp[v.num_op] || { op: v.num_op, nv: v.nota_vta, ingresos: [], salidas: [] };
    const ls = lineas.filter(l => l.vale_id === v.id).sort((a, b) => a.item - b.item)
      .map(l => ({ codigo: l.codigo, nombre: l.nombre, unidad: l.unidad, cantidad: Number(l.cantidad), lote: l.lote, origen: l.origen }));
    (v.movimiento === 'I' ? o.ingresos : o.salidas).push({ numero: v.numero, glosa: v.glosa, lineas: ls });
  });
  fs.writeFileSync(path.join(SALIDA, 'resumen.json'), JSON.stringify({
    modo: MODO, fecha: hoy, hora, vales: vales.length, ingresos: ing.length, salidas: sal.length,
    archivos, ops: Object.values(porOp).sort((a, b) => a.op - b.op),
  }));
  console.log('Vales: ' + ing.length + ' de ingreso y ' + sal.length + ' de salida; archivos: ' + archivos.length);
}

main().catch(e => { console.error(String(e.message || e)); process.exit(1); });
