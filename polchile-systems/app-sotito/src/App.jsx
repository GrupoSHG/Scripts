import React, { useEffect, useState, useCallback } from "react";
import { Camera, Users, Receipt, TrendingUp, Check, X, Upload, ChevronRight } from "lucide-react";
import {
  fetchCentros,
  fetchPersonas,
  fetchIniciativas,
  fetchAsistenciaDelDia,
  marcarAsistencia,
  fetchGastosDelDia,
  agregarGasto,
  subirFactura,
  fetchFacturacion,
} from "./data";

const clp = (n) => (n ?? 0).toLocaleString("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });
const hoy = () => new Date().toISOString().slice(0, 10);

const estadoColor = {
  en_curso: "bg-[#C9A227] text-[#1C1E1B]",
  planificada: "bg-[#4A5D52]/20 text-[#4A5D52]",
  completada: "bg-[#3A5A40]/20 text-[#3A5A40]",
};
const estadoLabel = { en_curso: "En curso", planificada: "Planificada", completada: "Completada" };

export default function App() {
  const [tab, setTab] = useState("formulario");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState(null);

  const [centros, setCentros] = useState([]);
  const [centroId, setCentroId] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [iniciativas, setIniciativas] = useState([]);
  const [facturacion, setFacturacion] = useState([]);
  const [asistencia, setAsistencia] = useState({});
  const [gastos, setGastos] = useState([]);

  const [ocrEstado, setOcrEstado] = useState(null);
  const fecha = hoy();

  // Carga inicial: centros de costo y personas activas
  useEffect(() => {
    (async () => {
      try {
        const [cs, ps] = await Promise.all([fetchCentros(), fetchPersonas()]);
        setCentros(cs);
        setPersonas(ps);
        if (cs.length) setCentroId(cs[0].id);
      } catch (e) {
        setError(e.message);
      } finally {
        setCargando(false);
      }
    })();
  }, []);

  const recargarCentro = useCallback(async (id) => {
    if (!id) return;
    try {
      const [asis, gts, inis, fact] = await Promise.all([
        fetchAsistenciaDelDia(id, fecha),
        fetchGastosDelDia(id, fecha),
        fetchIniciativas(id),
        fetchFacturacion(id),
      ]);
      const asisMap = {};
      asis.forEach((a) => (asisMap[a.persona_id] = a.presente));
      setAsistencia(asisMap);
      setGastos(gts);
      setIniciativas(inis);
      setFacturacion(fact);
    } catch (e) {
      setError(e.message);
    }
  }, [fecha]);

  useEffect(() => {
    recargarCentro(centroId);
  }, [centroId, recargarCentro]);

  const centroActivo = centros.find((c) => c.id === centroId);

  const togglePresente = async (personaId) => {
    const nuevoValor = !asistencia[personaId];
    setAsistencia((s) => ({ ...s, [personaId]: nuevoValor }));
    try {
      await marcarAsistencia(centroId, personaId, fecha, nuevoValor);
    } catch (e) {
      setError(e.message);
    }
  };

  const sueldoDia = personas.reduce((acc, p) => (asistencia[p.id] ? acc + Number(p.tarifa_diaria || 0) : acc), 0);
  const gastosDia = gastos.reduce((acc, g) => acc + Number(g.monto || 0), 0);

  const onSeleccionarFoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setOcrEstado("leyendo");
    try {
      // Sube la foto y crea el registro 'pendiente'; una Edge Function
      // procesa el OCR en el backend y actualiza el registro.
      await subirFactura(centroId, file);
      setOcrEstado("subida");
    } catch (e2) {
      setError(e2.message);
      setOcrEstado(null);
    }
  };

  const agregarGastoManual = async (descripcion, monto, categoria) => {
    try {
      await agregarGasto({ centroCostoId: centroId, fecha, descripcion, monto, categoria });
      recargarCentro(centroId);
    } catch (e) {
      setError(e.message);
    }
  };

  if (cargando) {
    return (
      <div className="min-h-screen bg-[#EDEAE2] flex items-center justify-center text-[#1C1E1B] font-mono text-sm">
        Cargando datos…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#EDEAE2] text-[#1C1E1B]">
      <header className="border-b-4 border-[#1C1E1B] bg-[#1C1E1B] text-[#EDEAE2] px-5 py-4">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          <div>
            <p className="text-[10px] tracking-[0.25em] uppercase text-[#C9A227] font-semibold">Control diario</p>
            <h1 className="text-xl font-bold tracking-tight">App Sotito</h1>
          </div>
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-wider text-[#EDEAE2]/60">Fecha</p>
            <p className="font-mono text-sm font-semibold">{fecha}</p>
          </div>
        </div>
      </header>

      {error && (
        <div className="max-w-lg mx-auto mt-3 px-4 py-2 bg-red-100 border-2 border-red-700 text-red-800 text-xs font-mono">
          {error}
        </div>
      )}

      <div className="max-w-lg mx-auto px-5 pt-4">
        <select
          value={centroId ?? ""}
          onChange={(e) => setCentroId(e.target.value)}
          className="w-full bg-white border-2 border-[#1C1E1B] px-3 py-2.5 font-mono text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-[#C9A227]"
        >
          {centros.map((c) => (
            <option key={c.id} value={c.id}>
              {c.codigo} — {c.nombre}
            </option>
          ))}
        </select>
      </div>

      <div className="max-w-lg mx-auto px-5 pt-3 flex gap-2">
        {[
          { id: "formulario", label: "Formulario diario" },
          { id: "dashboard", label: "Resumen" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 py-2 text-sm font-semibold uppercase tracking-wide border-2 border-[#1C1E1B] transition-colors ${
              tab === t.id ? "bg-[#1C1E1B] text-[#EDEAE2]" : "bg-transparent text-[#1C1E1B]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <main className="max-w-lg mx-auto px-5 py-5 space-y-5">
        {tab === "formulario" ? (
          <>
            <section className="bg-white border-2 border-[#1C1E1B]">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b-2 border-[#1C1E1B] bg-[#F6F4EE]">
                <Users size={16} />
                <h2 className="text-sm font-bold uppercase tracking-wide">Asistencia de hoy</h2>
              </div>
              <div className="divide-y divide-[#1C1E1B]/10">
                {personas.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => togglePresente(p.id)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left"
                  >
                    <div>
                      <p className="text-sm font-semibold">{p.nombre}</p>
                      <p className="text-xs text-[#1C1E1B]/50">
                        {p.cargo} · {clp(p.tarifa_diaria)}/día
                      </p>
                    </div>
                    <div
                      className={`w-6 h-6 flex items-center justify-center border-2 border-[#1C1E1B] ${
                        asistencia[p.id] ? "bg-[#3A5A40]" : "bg-white"
                      }`}
                    >
                      {asistencia[p.id] && <Check size={14} className="text-white" />}
                    </div>
                  </button>
                ))}
              </div>
              <div className="px-4 py-2.5 bg-[#F6F4EE] border-t-2 border-[#1C1E1B] flex justify-between text-sm font-mono font-semibold">
                <span>Gasto en sueldos hoy</span>
                <span>{clp(sueldoDia)}</span>
              </div>
            </section>

            <section className="bg-white border-2 border-[#1C1E1B]">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b-2 border-[#1C1E1B] bg-[#F6F4EE]">
                <Receipt size={16} />
                <h2 className="text-sm font-bold uppercase tracking-wide">Cargar factura</h2>
              </div>
              <div className="p-4">
                {!ocrEstado && (
                  <label className="w-full border-2 border-dashed border-[#1C1E1B]/40 py-6 flex flex-col items-center gap-2 text-[#1C1E1B]/60 hover:border-[#C9A227] hover:text-[#1C1E1B] transition-colors cursor-pointer">
                    <Camera size={22} />
                    <span className="text-xs font-semibold uppercase tracking-wide">Tomar foto de la factura</span>
                    <input type="file" accept="image/*" capture="environment" className="hidden" onChange={onSeleccionarFoto} />
                  </label>
                )}
                {ocrEstado === "leyendo" && (
                  <div className="py-6 flex flex-col items-center gap-2 text-[#1C1E1B]/70">
                    <Upload size={20} className="animate-pulse" />
                    <span className="text-xs font-mono">Subiendo imagen…</span>
                  </div>
                )}
                {ocrEstado === "subida" && (
                  <div className="py-4 flex flex-col items-center gap-2 text-[#1C1E1B]/70">
                    <Check size={20} className="text-[#3A5A40]" />
                    <span className="text-xs font-mono text-center">
                      Factura subida. El OCR la procesará en segundo plano;
                      aparecerá como gasto pendiente de revisión.
                    </span>
                    <button onClick={() => setOcrEstado(null)} className="text-xs underline">Cargar otra</button>
                  </div>
                )}
              </div>
            </section>

            <section className="bg-white border-2 border-[#1C1E1B]">
              <div className="flex items-center justify-between px-4 py-2.5 border-b-2 border-[#1C1E1B] bg-[#F6F4EE]">
                <h2 className="text-sm font-bold uppercase tracking-wide">Gastos de hoy</h2>
                <span className="font-mono text-sm font-semibold">{clp(gastosDia)}</span>
              </div>
              <div className="divide-y divide-[#1C1E1B]/10">
                {gastos.map((g) => (
                  <div key={g.id} className="flex justify-between px-4 py-2.5 text-sm">
                    <div>
                      <p className="font-medium">{g.descripcion}</p>
                      <p className="text-xs text-[#1C1E1B]/50">{g.categoria}</p>
                    </div>
                    <span className="font-mono">{clp(g.monto)}</span>
                  </div>
                ))}
                {!gastos.length && (
                  <p className="px-4 py-3 text-xs text-[#1C1E1B]/40 font-mono">Sin gastos registrados hoy.</p>
                )}
              </div>
              <div className="p-3 border-t-2 border-[#1C1E1B]">
                <FormGastoManual onAgregar={agregarGastoManual} />
              </div>
            </section>
          </>
        ) : (
          <>
            <section className="bg-[#1C1E1B] text-[#EDEAE2] border-2 border-[#1C1E1B] p-4">
              <p className="text-[10px] uppercase tracking-[0.2em] text-[#C9A227] font-semibold">{centroActivo?.codigo}</p>
              <h2 className="text-lg font-bold mb-3">{centroActivo?.nombre}</h2>
              <div className="grid grid-cols-2 gap-3 font-mono">
                <div>
                  <p className="text-[10px] uppercase text-[#EDEAE2]/50">Sueldos (mes est.)</p>
                  <p className="text-lg font-semibold">{clp(sueldoDia * 22)}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-[#EDEAE2]/50">Presupuesto</p>
                  <p className="text-lg font-semibold">{clp(centroActivo?.presupuesto_mensual)}</p>
                </div>
              </div>
              <div className="mt-3 h-2 bg-[#EDEAE2]/15">
                <div
                  className="h-2 bg-[#C9A227]"
                  style={{
                    width: `${Math.min(100, ((sueldoDia * 22) / (centroActivo?.presupuesto_mensual || 1)) * 100)}%`,
                  }}
                />
              </div>
            </section>

            <section className="bg-white border-2 border-[#1C1E1B]">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b-2 border-[#1C1E1B] bg-[#F6F4EE]">
                <TrendingUp size={16} />
                <h2 className="text-sm font-bold uppercase tracking-wide">Iniciativas</h2>
              </div>
              <div className="divide-y divide-[#1C1E1B]/10">
                {iniciativas.map((it) => (
                  <div key={it.id} className="flex items-center justify-between px-4 py-3">
                    <span className="text-sm font-medium">{it.nombre}</span>
                    <span className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-1 ${estadoColor[it.estado]}`}>
                      {estadoLabel[it.estado]}
                    </span>
                  </div>
                ))}
                {!iniciativas.length && (
                  <p className="px-4 py-3 text-xs text-[#1C1E1B]/40 font-mono">Sin iniciativas registradas.</p>
                )}
              </div>
            </section>

            <section className="bg-white border-2 border-[#1C1E1B]">
              <div className="flex items-center justify-between px-4 py-2.5 border-b-2 border-[#1C1E1B] bg-[#F6F4EE]">
                <h2 className="text-sm font-bold uppercase tracking-wide">Facturación</h2>
                <ChevronRight size={16} className="text-[#1C1E1B]/40" />
              </div>
              <div className="px-4 py-3 space-y-2 font-mono text-sm">
                {facturacion.map((f) => (
                  <div key={f.id} className="flex justify-between">
                    <span className="text-[#1C1E1B]/60">{f.tipo === "estimada" ? "Estimada" : "Real"} — {f.referencia}</span>
                    <span>{clp(f.monto)}</span>
                  </div>
                ))}
                {!facturacion.length && <p className="text-xs text-[#1C1E1B]/40">Sin registros de facturación.</p>}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function FormGastoManual({ onAgregar }) {
  const [descripcion, setDescripcion] = useState("");
  const [monto, setMonto] = useState("");
  const [categoria, setCategoria] = useState("Otros");

  const submit = (e) => {
    e.preventDefault();
    if (!descripcion || !monto) return;
    onAgregar(descripcion, Number(monto), categoria);
    setDescripcion("");
    setMonto("");
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <input
        placeholder="Descripción del gasto"
        value={descripcion}
        onChange={(e) => setDescripcion(e.target.value)}
        className="border-2 border-[#1C1E1B] px-2 py-1.5 text-sm"
      />
      <div className="flex gap-2">
        <input
          type="number"
          placeholder="Monto"
          value={monto}
          onChange={(e) => setMonto(e.target.value)}
          className="flex-1 border-2 border-[#1C1E1B] px-2 py-1.5 text-sm font-mono"
        />
        <select
          value={categoria}
          onChange={(e) => setCategoria(e.target.value)}
          className="border-2 border-[#1C1E1B] px-2 py-1.5 text-sm"
        >
          <option>Transporte</option>
          <option>Materiales</option>
          <option>Alimentación</option>
          <option>Otros</option>
        </select>
      </div>
      <button type="submit" className="bg-[#1C1E1B] text-white py-2 text-sm font-semibold uppercase tracking-wide">
        Agregar gasto
      </button>
    </form>
  );
}
