import React, { useEffect, useState } from "react";
import { fetchAsistenciaPorPersona } from "./data";

export default function AsistenciaPorPersona() {
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [abierta, setAbierta] = useState(null); // personaId expandida

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchAsistenciaPorPersona();
        setPersonas(data);
      } catch (e) {
        setError(e.message);
      } finally {
        setCargando(false);
      }
    })();
  }, []);

  if (cargando) {
    return <p className="text-xs text-[#1F3D26]/50 font-mono px-1">Cargando asistencia…</p>;
  }

  return (
    <div className="space-y-3">
      {error && (
        <div className="px-4 py-2 bg-red-100 border-2 border-red-700 text-red-800 text-xs font-mono">{error}</div>
      )}

      {personas.map((p) => (
        <section key={p.personaId} className="bg-white border-2 border-[#1F3D26]">
          <button
            onClick={() => setAbierta(abierta === p.personaId ? null : p.personaId)}
            className="w-full flex items-center justify-between px-4 py-2.5 border-b-2 border-[#1F3D26] bg-[#EFF6EE] text-left"
          >
            <span className="text-sm font-bold uppercase tracking-wide">{p.nombre}</span>
            <span className="text-xs font-mono text-[#1F3D26]/70">{p.totalDias} días este mes</span>
          </button>

          {abierta === p.personaId && (
            <div className="divide-y divide-[#1F3D26]/10">
              {p.centros.length === 0 && (
                <p className="px-4 py-3 text-xs text-[#1F3D26]/40 font-mono">Sin asistencia registrada.</p>
              )}
              {p.centros.map((c) => (
                <div key={c.centro} className="px-4 py-2.5 flex items-center justify-between">
                  <span className="text-sm">{c.centro}</span>
                  <span className="text-xs font-mono text-[#1F3D26]/70">{c.dias} días</span>
                </div>
              ))}
            </div>
          )}
        </section>
      ))}

      {!personas.length && (
        <p className="text-xs text-[#1F3D26]/40 font-mono px-1">Sin personas activas.</p>
      )}
    </div>
  );
}
