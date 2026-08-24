import React, { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { fetchResumenGeneral } from "./data";

const clp = (n) => (n ?? 0).toLocaleString("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });

export default function ResumenGeneral() {
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [centros, setCentros] = useState([]);
  const [facturacion, setFacturacion] = useState([]);
  const [gastos, setGastos] = useState([]);
  const [mesFiltro, setMesFiltro] = useState("todos");

  useEffect(() => {
    (async () => {
      try {
        const { centros: cs, facturacion: fs, gastos: gs } = await fetchResumenGeneral();
        setCentros(cs);
        setFacturacion(fs);
        setGastos(gs);
      } catch (e) {
        setError(e.message);
      } finally {
        setCargando(false);
      }
    })();
  }, []);

  if (cargando) {
    return <p className="text-xs text-[#1F3D26]/50 font-mono px-1">Cargando resumen…</p>;
  }

  const mesesDisponibles = [...new Set(facturacion.map((f) => f.mes))].sort().reverse();

  const facturacionFiltrada =
    mesFiltro === "todos" ? facturacion : facturacion.filter((f) => f.mes === mesFiltro);

  const gastosFiltrados =
    mesFiltro === "todos"
      ? gastos
      : gastos.filter((g) => g.fecha && g.fecha.slice(0, 7) === mesFiltro.slice(0, 7));

  const filaPorCentro = centros.map((c) => {
    const factC = facturacionFiltrada.filter((f) => f.centro_costo_id === c.id);
    const totalFacturado = factC.reduce((acc, f) => acc + Number(f.total || 0), 0);
    const totalManoObra = factC.reduce((acc, f) => acc + Number(f.mano_obra || 0), 0);
    const totalGastos = gastosFiltrados
      .filter((g) => g.centro_costo_id === c.id)
      .reduce((acc, g) => acc + Number(g.monto || 0), 0);
    return { ...c, totalFacturado, totalManoObra, totalGastos };
  });

  const chartData = filaPorCentro.map((c) => ({
    nombre: c.nombre,
    "Mano de obra": c.totalManoObra,
    Gastos: c.totalGastos,
    Facturado: c.totalFacturado,
  }));

  const granTotalFacturado = filaPorCentro.reduce((acc, c) => acc + c.totalFacturado, 0);
  const granTotalGastos = filaPorCentro.reduce((acc, c) => acc + c.totalGastos, 0);

  return (
    <div className="space-y-5">
      {error && (
        <div className="px-4 py-2 bg-red-100 border-2 border-red-700 text-red-800 text-xs font-mono">{error}</div>
      )}

      <section className="bg-[#1F3D26] text-[#EAF2E9] border-2 border-[#1F3D26] p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10px] uppercase tracking-[0.2em] text-[#4C9A2A] font-semibold">Todos los centros de costo</p>
          {!!mesesDisponibles.length && (
            <select
              value={mesFiltro}
              onChange={(e) => setMesFiltro(e.target.value)}
              className="bg-[#EAF2E9] text-[#1F3D26] border-2 border-[#4C9A2A] px-2 py-1 text-xs font-mono"
            >
              <option value="todos">Todos los meses</option>
              {mesesDisponibles.map((m) => (
                <option key={m} value={m}>
                  {new Date(m).toLocaleDateString("es-CL", { month: "long", year: "numeric" })}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="grid grid-cols-2 gap-3 font-mono mt-2">
          <div>
            <p className="text-[10px] uppercase text-[#EAF2E9]/50">Facturado total</p>
            <p className="text-lg font-semibold">{clp(granTotalFacturado)}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase text-[#EAF2E9]/50">Gastos totales</p>
            <p className="text-lg font-semibold">{clp(granTotalGastos)}</p>
          </div>
        </div>
      </section>

      <section className="bg-white border-2 border-[#1F3D26]">
        <div className="px-4 py-2.5 border-b-2 border-[#1F3D26] bg-[#EFF6EE]">
          <h2 className="text-sm font-bold uppercase tracking-wide">Mano de obra, gastos y facturación por centro</h2>
        </div>
        <div className="p-3" style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ left: 0, right: 8, top: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1F3D2620" />
              <XAxis dataKey="nombre" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={50} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
              <Tooltip formatter={(v) => clp(v)} />
              <Bar dataKey="Mano de obra" fill="#2C5233" />
              <Bar dataKey="Gastos" fill="#4C9A2A" />
              <Bar dataKey="Facturado" fill="#1F3D26" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="bg-white border-2 border-[#1F3D26] overflow-x-auto">
        <div className="px-4 py-2.5 border-b-2 border-[#1F3D26] bg-[#EFF6EE]">
          <h2 className="text-sm font-bold uppercase tracking-wide">Detalle por centro de costo</h2>
        </div>
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b-2 border-[#1F3D26] text-left">
              <th className="px-3 py-2">Código</th>
              <th className="px-3 py-2">Nombre</th>
              <th className="px-3 py-2">Factura a</th>
              <th className="px-3 py-2 text-right">Mano de obra</th>
              <th className="px-3 py-2 text-right">Gastos</th>
              <th className="px-3 py-2 text-right">Facturado (total c/IVA)</th>
            </tr>
          </thead>
          <tbody>
            {filaPorCentro.map((c) => (
              <tr key={c.id} className="border-b border-[#1F3D26]/10">
                <td className="px-3 py-2">{c.codigo}</td>
                <td className="px-3 py-2">{c.nombre}</td>
                <td className="px-3 py-2">{c.factura_a || "—"}</td>
                <td className="px-3 py-2 text-right">{clp(c.totalManoObra)}</td>
                <td className="px-3 py-2 text-right">{clp(c.totalGastos)}</td>
                <td className="px-3 py-2 text-right font-semibold">{clp(c.totalFacturado)}</td>
              </tr>
            ))}
            {!filaPorCentro.length && (
              <tr>
                <td className="px-3 py-3 text-[#1F3D26]/40" colSpan={6}>Sin centros de costo cargados.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
