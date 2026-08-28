import React, { useEffect, useState, useCallback } from "react";
import { Camera, Users, Receipt, TrendingUp, Check, X, Upload, ChevronRight, UserPlus, Plus } from "lucide-react";
import {
  fetchCentros,
  agregarCentroCosto,
  fetchPersonas,
  agregarPersona,
  fetchIniciativas,
  fetchAsistenciaDelDia,
  marcarAsistencia,
  fetchGastosDelDia,
  agregarGasto,
  subirFactura,
  fetchFacturaPorId,
  fetchFacturasCentro,
  fetchFacturacion,
  eliminarFactura,
} from "./data";
import ResumenGeneral from "./ResumenGeneral";

const clp = (n) => (n ?? 0).toLocaleString("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });
const hoy = () => new Date().toISOString().slice(0, 10);

const estadoColor = {
  en_curso: "bg-[#4C9A2A] text-[#1F3D26]",
  planificada: "bg-[#5E7A63]/20 text-[#5E7A63]",
  completada: "bg-[#2C5233]/20 text-[#2C5233]",
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
  const [facturasSubidas, setFacturasSubidas] = useState([]);
  const [guardandoTodo, setGuardandoTodo] = useState(false);
  const [mostrarNuevoCentro, setMostrarNuevoCentro] = useState(false);
  const [mesFiltro, setMesFiltro] = useState("todos");
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
      const [asis, gts, inis, fact, fotos] = await Promise.all([
        fetchAsistenciaDelDia(id, fecha),
        fetchGastosDelDia(id, fecha),
        fetchIniciativas(id),
        fetchFacturacion(id),
        fetchFacturasCentro(id),
      ]);
      const asisMap = {};
      asis.forEach((a) => (asisMap[a.persona_id] = a.presente));
      setAsistencia(asisMap);
      setGastos(gts);
      setIniciativas(inis);
      setFacturacion(fact);
      setFacturasSubidas(fotos);
    } catch (e) {
      setError(e.message);
    }
  }, [fecha]);

  useEffect(() => {
    recargarCentro(centroId);
  }, [centroId, recargarCentro]);

  const centroActivo = centros.find((c) => c.id === centroId);

  const [guardadoAsistencia, setGuardadoAsistencia] = useState({}); // personaId -> 'guardando' | 'guardado' | null

  const togglePresente = async (personaId) => {
    const nuevoValor = !asistencia[personaId];
    setAsistencia((s) => ({ ...s, [personaId]: nuevoValor }));
    setGuardadoAsistencia((s) => ({ ...s, [personaId]: "guardando" }));
    try {
      await marcarAsistencia(centroId, personaId, fecha, nuevoValor);
      setGuardadoAsistencia((s) => ({ ...s, [personaId]: "guardado" }));
      setTimeout(() => {
        setGuardadoAsistencia((s) => ({ ...s, [personaId]: null }));
      }, 1500);
    } catch (e) {
      setError(e.message);
      setGuardadoAsistencia((s) => ({ ...s, [personaId]: null }));
      // revertir el cambio optimista si falló el guardado
      setAsistencia((s) => ({ ...s, [personaId]: !nuevoValor }));
    }
  };

  const sueldoDia = personas.reduce((acc, p) => (asistencia[p.id] ? acc + Number(p.tarifa_diaria || 0) : acc), 0);
  const gastosDia = gastos.reduce((acc, g) => acc + Number(g.monto || 0), 0);

  const [facturaLeida, setFacturaLeida] = useState(null);

  const onSeleccionarFoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setOcrEstado("leyendo");
    try {
      await subirFactura(centroId, file);
      setOcrEstado(null);
      recargarCentro(centroId); // refresca la galería para que se vea la foto nueva
    } catch (e2) {
      setError(e2.message);
      setOcrEstado(null);
    }
  };

  // Consulta cada 2s hasta que la Edge Function termine de procesar (máx. 30s)
  const pollFactura = (facturaId, intentos = 0) => {
    setTimeout(async () => {
      try {
        const f = await fetchFacturaPorId(facturaId);
        if (f.estado_ocr === "leida") {
          setFacturaLeida(f);
          setOcrEstado("leida");
        } else if (f.estado_ocr === "error") {
          setOcrEstado("error");
        } else if (intentos < 15) {
          pollFactura(facturaId, intentos + 1);
        } else {
          setOcrEstado("timeout");
        }
      } catch (e) {
        setError(e.message);
        setOcrEstado(null);
      }
    }, 2000);
  };

  const confirmarFacturaLeida = async () => {
    if (!facturaLeida) return;
    try {
      await agregarGasto({
        centroCostoId: centroId,
        fecha: facturaLeida.fecha || fecha,
        descripcion: `Factura — ${facturaLeida.proveedor || "sin proveedor"}`,
        monto: facturaLeida.monto || 0,
        categoria: "Materiales",
        facturaId: facturaLeida.id,
      });
      setFacturaLeida(null);
      setOcrEstado(null);
      recargarCentro(centroId);
    } catch (e) {
      setError(e.message);
    }
  };

  const agregarTrabajador = async (nombre, cargo, tarifaDiaria) => {
    try {
      await agregarPersona({ nombre, cargo, tarifaDiaria });
      const ps = await fetchPersonas();
      setPersonas(ps);
    } catch (e) {
      setError(e.message);
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

  // Reconfirma en Supabase la asistencia de todos los trabajadores tal como
  // está marcada en pantalla, y refresca todo desde la base de datos.
  const guardarTodo = async () => {
    setGuardandoTodo(true);
    try {
      await Promise.all(
        personas.map((p) => marcarAsistencia(centroId, p.id, fecha, !!asistencia[p.id]))
      );
      await recargarCentro(centroId);
    } catch (e) {
      setError(e.message);
    } finally {
      setGuardandoTodo(false);
    }
  };

  const agregarNuevoCentro = async (codigo, nombre, facturaA, presupuestoMensual) => {
    try {
      const nuevo = await agregarCentroCosto({ codigo, nombre, facturaA, presupuestoMensual });
      const cs = await fetchCentros();
      setCentros(cs);
      setCentroId(nuevo.id);
      setMostrarNuevoCentro(false);
    } catch (e) {
      setError(e.message);
    }
  };

  if (cargando) {
    return (
      <div className="min-h-screen bg-[#EAF2E9] flex items-center justify-center text-[#1F3D26] font-mono text-sm">
        Cargando datos…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#EAF2E9] text-[#1F3D26]">
      <header className="border-b-4 border-[#1F3D26] bg-[#1F3D26] text-[#EAF2E9] px-5 py-4">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          <div>
            <p className="text-[10px] tracking-[0.25em] uppercase text-[#4C9A2A] font-semibold">Control diario</p>
            <h1 className="text-xl font-bold tracking-tight">App Sotito</h1>
          </div>
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-wider text-[#EAF2E9]/60">Fecha</p>
            <p className="font-mono text-sm font-semibold">{fecha}</p>
          </div>
        </div>
      </header>

      {error && (
        <div className="max-w-lg mx-auto mt-3 px-4 py-2 bg-red-100 border-2 border-red-700 text-red-800 text-xs font-mono">
          {error}
        </div>
      )}

      <div className="max-w-lg mx-auto px-5 pt-4 flex gap-2 items-start">
        <select
          value={centroId ?? ""}
          onChange={(e) => setCentroId(e.target.value)}
          className="flex-1 bg-white border-2 border-[#1F3D26] px-3 py-2.5 font-mono text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-[#4C9A2A]"
        >
          {centros.map((c) => (
            <option key={c.id} value={c.id}>
              {c.codigo} — {c.nombre}
            </option>
          ))}
        </select>
        <button
          onClick={() => setMostrarNuevoCentro((v) => !v)}
          title="Agregar centro de costo"
          className="shrink-0 w-11 h-11 flex items-center justify-center bg-[#1F3D26] text-white border-2 border-[#1F3D26]"
        >
          <Plus size={18} />
        </button>
      </div>

      {mostrarNuevoCentro && (
        <div className="max-w-lg mx-auto px-5 pt-2">
          <FormNuevoCentro onAgregar={agregarNuevoCentro} onCancelar={() => setMostrarNuevoCentro(false)} />
        </div>
      )}

      <div className="max-w-lg mx-auto px-5 pt-3 flex gap-2">
        {[
          { id: "formulario", label: "Formulario diario" },
          { id: "dashboard", label: "Resumen" },
          { id: "general", label: "General" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 py-2 text-sm font-semibold uppercase tracking-wide border-2 border-[#1F3D26] transition-colors ${
              tab === t.id ? "bg-[#1F3D26] text-[#EAF2E9]" : "bg-transparent text-[#1F3D26]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <main className={`mx-auto px-5 py-5 space-y-5 ${tab === "general" ? "max-w-4xl" : "max-w-lg"}`}>
        {tab === "general" ? (
          <ResumenGeneral />
        ) : tab === "formulario" ? (
          <>
            <section className="bg-white border-2 border-[#1F3D26]">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b-2 border-[#1F3D26] bg-[#EFF6EE]">
                <Users size={16} />
                <h2 className="text-sm font-bold uppercase tracking-wide">Asistencia de hoy</h2>
              </div>
              <div className="divide-y divide-[#1F3D26]/10">
                {personas.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => togglePresente(p.id)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left"
                  >
                    <div>
                      <p className="text-sm font-semibold">{p.nombre}</p>
                      <p className="text-xs text-[#1F3D26]/50">
                        {p.cargo} · {clp(p.tarifa_diaria)}/día
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {guardadoAsistencia[p.id] === "guardando" && (
                        <span className="text-[9px] uppercase tracking-wide text-[#1F3D26]/40 font-mono">Guardando…</span>
                      )}
                      {guardadoAsistencia[p.id] === "guardado" && (
                        <span className="text-[9px] uppercase tracking-wide text-[#2C5233] font-mono flex items-center gap-1">
                          <Check size={10} /> Guardado
                        </span>
                      )}
                      <div
                        className={`w-6 h-6 flex items-center justify-center border-2 border-[#1F3D26] ${
                          asistencia[p.id] ? "bg-[#2C5233]" : "bg-white"
                        }`}
                      >
                        {asistencia[p.id] && <Check size={14} className="text-white" />}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
              <div className="px-4 py-2.5 bg-[#EFF6EE] border-t-2 border-[#1F3D26] flex justify-between text-sm font-mono font-semibold">
                <span>Gasto en sueldos hoy</span>
                <span>{clp(sueldoDia)}</span>
              </div>
              <div className="p-3 border-t-2 border-[#1F3D26]">
                <FormNuevoTrabajador onAgregar={agregarTrabajador} />
              </div>
            </section>

            <section className="bg-white border-2 border-[#1F3D26]">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b-2 border-[#1F3D26] bg-[#EFF6EE]">
                <Receipt size={16} />
                <h2 className="text-sm font-bold uppercase tracking-wide">Cargar factura</h2>
              </div>
              <div className="p-4">
                {!ocrEstado && (
                  <label className="w-full border-2 border-dashed border-[#1F3D26]/40 py-6 flex flex-col items-center gap-2 text-[#1F3D26]/60 hover:border-[#4C9A2A] hover:text-[#1F3D26] transition-colors cursor-pointer">
                    <Camera size={22} />
                    <span className="text-xs font-semibold uppercase tracking-wide">Tomar foto de la factura</span>
                    <input type="file" accept="image/*" capture="environment" className="hidden" onChange={onSeleccionarFoto} />
                  </label>
                )}
                {ocrEstado === "leyendo" && (
                  <div className="py-6 flex flex-col items-center gap-2 text-[#1F3D26]/70">
                    <Upload size={20} className="animate-pulse" />
                    <span className="text-xs font-mono">Subiendo imagen…</span>
                  </div>
                )}
                {ocrEstado === "procesando" && (
                  <div className="py-6 flex flex-col items-center gap-2 text-[#1F3D26]/70">
                    <Upload size={20} className="animate-pulse" />
                    <span className="text-xs font-mono">Leyendo factura con OCR…</span>
                  </div>
                )}
                {ocrEstado === "leida" && facturaLeida && (
                  <div className="space-y-3">
                    <div className="bg-[#EFF6EE] border border-[#1F3D26]/20 p-3 font-mono text-sm space-y-1">
                      <p><span className="text-[#1F3D26]/50">Proveedor:</span> {facturaLeida.proveedor || "(no detectado)"}</p>
                      <p><span className="text-[#1F3D26]/50">Monto:</span> {facturaLeida.monto ? clp(facturaLeida.monto) : "(no detectado)"}</p>
                      <p><span className="text-[#1F3D26]/50">Fecha:</span> {facturaLeida.fecha || "(no detectada)"}</p>
                    </div>
                    <p className="text-[10px] text-[#1F3D26]/40 uppercase tracking-wide">
                      Revisa y corrige en Supabase si algo quedó mal leído antes de confirmar
                    </p>
                    <div className="flex gap-2">
                      <button onClick={confirmarFacturaLeida} className="flex-1 bg-[#2C5233] text-white py-2 text-sm font-semibold uppercase tracking-wide">
                        Confirmar y agregar gasto
                      </button>
                      <button onClick={() => { setOcrEstado(null); setFacturaLeida(null); }} className="px-4 border-2 border-[#1F3D26]">
                        <X size={16} />
                      </button>
                    </div>
                  </div>
                )}
                {(ocrEstado === "error" || ocrEstado === "timeout") && (
                  <div className="py-4 flex flex-col items-center gap-2 text-[#1F3D26]/70">
                    <X size={20} className="text-red-700" />
                    <span className="text-xs font-mono text-center">
                      {ocrEstado === "error" ? "No se pudo leer la factura automáticamente." : "El OCR está tardando más de lo normal."}
                    </span>
                    <button onClick={() => { setOcrEstado(null); setFacturaLeida(null); }} className="text-xs underline">Intentar de nuevo</button>
                  </div>
                )}
              </div>
              {!!facturasSubidas.length && (
                <div className="border-t-2 border-[#1F3D26] p-3">
                  <p className="text-[10px] uppercase tracking-wide text-[#1F3D26]/50 font-mono mb-2">
                    Fotos subidas de este centro ({facturasSubidas.length})
                  </p>
                  <div className="grid grid-cols-3 gap-2">
                    {facturasSubidas.map((f) => (
                      <a key={f.id} href={f.foto_url} target="_blank" rel="noreferrer" className="relative block border-2 border-[#1F3D26]">
                        <img src={f.foto_url} alt={f.proveedor || "Factura"} className="w-full h-20 object-cover" />
                        <span
                          className={`absolute bottom-0 left-0 right-0 text-[8px] font-mono uppercase text-center py-0.5 ${
                            f.estado_ocr === "leida"
                              ? "bg-[#4C9A2A] text-[#1F3D26]"
                              : f.estado_ocr === "error"
                              ? "bg-red-600 text-white"
                              : "bg-[#1F3D26]/70 text-white"
                          }`}
                        >
                          {f.estado_ocr}
                        </span>
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="bg-white border-2 border-[#1F3D26]">
              <div className="flex items-center justify-between px-4 py-2.5 border-b-2 border-[#1F3D26] bg-[#EFF6EE]">
                <h2 className="text-sm font-bold uppercase tracking-wide">Gastos de hoy</h2>
                <span className="font-mono text-sm font-semibold">{clp(gastosDia)}</span>
              </div>
              <div className="divide-y divide-[#1F3D26]/10">
                {gastos.map((g) => (
                  <div key={g.id} className="flex justify-between px-4 py-2.5 text-sm">
                    <div>
                      <p className="font-medium">{g.descripcion}</p>
                      <p className="text-xs text-[#1F3D26]/50">{g.categoria}</p>
                    </div>
                    <span className="font-mono">{clp(g.monto)}</span>
                  </div>
                ))}
                {!gastos.length && (
                  <p className="px-4 py-3 text-xs text-[#1F3D26]/40 font-mono">Sin gastos registrados hoy.</p>
                )}
              </div>
              <div className="p-3 border-t-2 border-[#1F3D26]">
                <FormGastoManual onAgregar={agregarGastoManual} />
              </div>
            </section>

            <button
              onClick={guardarTodo}
              disabled={guardandoTodo}
              className="w-full bg-[#4C9A2A] text-[#1F3D26] py-3 text-sm font-bold uppercase tracking-wide border-2 border-[#1F3D26] disabled:opacity-60"
            >
              {guardandoTodo ? "Guardando todo…" : "Guardar todo"}
            </button>
          </>
        ) : (
          <>
            <section className="bg-[#1F3D26] text-[#EAF2E9] border-2 border-[#1F3D26] p-4">
              <p className="text-[10px] uppercase tracking-[0.2em] text-[#4C9A2A] font-semibold">{centroActivo?.codigo}</p>
              <h2 className="text-lg font-bold mb-3">{centroActivo?.nombre}</h2>
              <div className="grid grid-cols-2 gap-3 font-mono">
                <div>
                  <p className="text-[10px] uppercase text-[#EAF2E9]/50">Sueldos (mes est.)</p>
                  <p className="text-lg font-semibold">{clp(sueldoDia * 22)}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase text-[#EAF2E9]/50">Presupuesto</p>
                  <p className="text-lg font-semibold">{clp(centroActivo?.presupuesto_mensual)}</p>
                </div>
              </div>
              <div className="mt-3 h-2 bg-[#EAF2E9]/15">
                <div
                  className="h-2 bg-[#4C9A2A]"
                  style={{
                    width: `${Math.min(100, ((sueldoDia * 22) / (centroActivo?.presupuesto_mensual || 1)) * 100)}%`,
                  }}
                />
              </div>
            </section>

            <section className="bg-white border-2 border-[#1F3D26]">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b-2 border-[#1F3D26] bg-[#EFF6EE]">
                <TrendingUp size={16} />
                <h2 className="text-sm font-bold uppercase tracking-wide">Iniciativas</h2>
              </div>
              <div className="divide-y divide-[#1F3D26]/10">
                {iniciativas.map((it) => (
                  <div key={it.id} className="flex items-center justify-between px-4 py-3">
                    <span className="text-sm font-medium">{it.nombre}</span>
                    <span className={`text-[10px] font-semibold uppercase tracking-wide px-2 py-1 ${estadoColor[it.estado]}`}>
                      {estadoLabel[it.estado]}
                    </span>
                  </div>
                ))}
                {!iniciativas.length && (
                  <p className="px-4 py-3 text-xs text-[#1F3D26]/40 font-mono">Sin iniciativas registradas.</p>
                )}
              </div>
            </section>

            <section className="bg-white border-2 border-[#1F3D26]">
              <div className="flex items-center justify-between px-4 py-2.5 border-b-2 border-[#1F3D26] bg-[#EFF6EE]">
                <h2 className="text-sm font-bold uppercase tracking-wide">Facturación</h2>
                <ChevronRight size={16} className="text-[#1F3D26]/40" />
              </div>
              {facturacion.length > 1 && (
                <div className="px-4 py-2 border-b border-[#1F3D26]/10">
                  <select
                    value={mesFiltro}
                    onChange={(e) => setMesFiltro(e.target.value)}
                    className="w-full bg-white border-2 border-[#1F3D26] px-2 py-1.5 text-xs font-mono"
                  >
                    <option value="todos">Todos los períodos</option>
                    {facturacion.map((f) => (
                      <option key={f.id} value={f.periodo_inicio}>
                        {new Date(f.periodo_inicio).toLocaleDateString("es-CL", { day: "2-digit", month: "short" })}
                        {" – "}
                        {new Date(f.periodo_fin).toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" })}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div className="px-4 py-3 space-y-3 font-mono text-sm">
                {facturacion
                  .filter((f) => mesFiltro === "todos" || f.periodo_inicio === mesFiltro)
                  .map((f) => (
                    <div key={f.id} className="border-b border-[#1F3D26]/10 pb-2 last:border-0">
                      <div className="flex justify-between text-xs text-[#1F3D26]/50 mb-1">
                        <span>
                          {new Date(f.periodo_inicio).toLocaleDateString("es-CL", { day: "2-digit", month: "short" })}
                          {" – "}
                          {new Date(f.periodo_fin).toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" })}
                        </span>
                        {centroActivo?.factura_a && <span>Factura a: {centroActivo.factura_a}</span>}
                      </div>
                      <div className="flex justify-between"><span className="text-[#1F3D26]/60">Mano de obra</span><span>{clp(f.mano_obra)}</span></div>
                      <div className="flex justify-between"><span className="text-[#1F3D26]/60">Gastos netos</span><span>{clp(f.gastos_netos)}</span></div>
                      <div className="flex justify-between font-bold"><span>Total (mano de obra + gastos)</span><span>{clp(f.total)}</span></div>
                    </div>
                  ))}
                {!facturacion.length && <p className="text-xs text-[#1F3D26]/40">Sin registros de facturación.</p>}
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function FormNuevoCentro({ onAgregar, onCancelar }) {
  const [codigo, setCodigo] = useState("");
  const [nombre, setNombre] = useState("");
  const [facturaA, setFacturaA] = useState("");
  const [presupuesto, setPresupuesto] = useState("");

  const submit = (e) => {
    e.preventDefault();
    if (!codigo || !nombre) return;
    onAgregar(codigo.toUpperCase(), nombre, facturaA, presupuesto ? Number(presupuesto) : null);
    setCodigo("");
    setNombre("");
    setFacturaA("");
    setPresupuesto("");
  };

  return (
    <form onSubmit={submit} className="bg-white border-2 border-[#1F3D26] p-3 flex flex-col gap-2">
      <p className="text-xs font-bold uppercase tracking-wide text-[#1F3D26]">Nuevo centro de costo</p>
      <div className="flex gap-2">
        <input
          placeholder="Código (ej. CYS-BUIN)"
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          className="flex-1 border-2 border-[#1F3D26] px-2 py-1.5 text-sm font-mono"
        />
        <input
          placeholder="Nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          className="flex-1 border-2 border-[#1F3D26] px-2 py-1.5 text-sm"
        />
      </div>
      <div className="flex gap-2">
        <input
          placeholder="Factura a (opcional)"
          value={facturaA}
          onChange={(e) => setFacturaA(e.target.value)}
          className="flex-1 border-2 border-[#1F3D26] px-2 py-1.5 text-sm"
        />
        <input
          type="number"
          placeholder="Presupuesto mensual (opcional)"
          value={presupuesto}
          onChange={(e) => setPresupuesto(e.target.value)}
          className="w-40 border-2 border-[#1F3D26] px-2 py-1.5 text-sm font-mono"
        />
      </div>
      <div className="flex gap-2">
        <button type="submit" className="flex-1 bg-[#1F3D26] text-white py-2 text-sm font-semibold uppercase tracking-wide">
          Crear centro de costo
        </button>
        <button type="button" onClick={onCancelar} className="px-4 border-2 border-[#1F3D26]">
          <X size={16} />
        </button>
      </div>
    </form>
  );
}

function FormNuevoTrabajador({ onAgregar }) {
  const [abierto, setAbierto] = useState(false);
  const [nombre, setNombre] = useState("");
  const [cargo, setCargo] = useState("");
  const [tarifa, setTarifa] = useState("");

  const submit = (e) => {
    e.preventDefault();
    if (!nombre || !tarifa) return;
    onAgregar(nombre, cargo, Number(tarifa));
    setNombre("");
    setCargo("");
    setTarifa("");
    setAbierto(false);
  };

  if (!abierto) {
    return (
      <button
        onClick={() => setAbierto(true)}
        className="w-full flex items-center justify-center gap-2 border-2 border-dashed border-[#1F3D26]/40 py-2.5 text-xs font-semibold uppercase tracking-wide text-[#1F3D26]/60 hover:border-[#4C9A2A] hover:text-[#1F3D26] transition-colors"
      >
        <UserPlus size={14} /> Agregar trabajador
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <input
        placeholder="Nombre"
        value={nombre}
        onChange={(e) => setNombre(e.target.value)}
        className="border-2 border-[#1F3D26] px-2 py-1.5 text-sm"
      />
      <div className="flex gap-2">
        <input
          placeholder="Cargo"
          value={cargo}
          onChange={(e) => setCargo(e.target.value)}
          className="flex-1 border-2 border-[#1F3D26] px-2 py-1.5 text-sm"
        />
        <input
          type="number"
          placeholder="Tarifa/día"
          value={tarifa}
          onChange={(e) => setTarifa(e.target.value)}
          className="w-28 border-2 border-[#1F3D26] px-2 py-1.5 text-sm font-mono"
        />
      </div>
      <div className="flex gap-2">
        <button type="submit" className="flex-1 bg-[#1F3D26] text-white py-2 text-sm font-semibold uppercase tracking-wide">
          Guardar
        </button>
        <button type="button" onClick={() => setAbierto(false)} className="px-4 border-2 border-[#1F3D26]">
          <X size={16} />
        </button>
      </div>
    </form>
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
        className="border-2 border-[#1F3D26] px-2 py-1.5 text-sm"
      />
      <div className="flex gap-2">
        <input
          type="number"
          placeholder="Monto"
          value={monto}
          onChange={(e) => setMonto(e.target.value)}
          className="flex-1 border-2 border-[#1F3D26] px-2 py-1.5 text-sm font-mono"
        />
        <select
          value={categoria}
          onChange={(e) => setCategoria(e.target.value)}
          className="border-2 border-[#1F3D26] px-2 py-1.5 text-sm"
        >
          <option>Transporte</option>
          <option>Materiales</option>
          <option>Alimentación</option>
          <option>Otros</option>
        </select>
      </div>
      <button type="submit" className="bg-[#1F3D26] text-white py-2 text-sm font-semibold uppercase tracking-wide">
        Agregar gasto
      </button>
    </form>
  );
}
