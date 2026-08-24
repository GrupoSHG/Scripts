import { supabase } from "./supabaseClient";

// Todas las tablas de esta app viven en el esquema shg_dashboards del proyecto
// Supabase compartido (ffxopvzxyeacpbtxuagu) — no en "public".
const db = supabase.schema("shg_dashboards");

export async function fetchCentros() {
  const { data, error } = await db
    .from("centros_costo")
    .select("*")
    .eq("activo", true)
    .order("codigo");
  if (error) throw error;
  return data;
}

export async function agregarCentroCosto({ codigo, nombre, facturaA, presupuestoMensual }) {
  const { data, error } = await db
    .from("centros_costo")
    .insert({
      codigo,
      nombre,
      factura_a: facturaA || null,
      presupuesto_mensual: presupuestoMensual || null,
      activo: true,
    })
    .select()
    .single();
  if (error) throw error;
  return data;
}

export async function fetchPersonas() {
  const { data, error } = await db
    .from("personas")
    .select("*")
    .eq("activo", true)
    .order("nombre");
  if (error) throw error;
  return data;
}

export async function agregarPersona({ nombre, cargo, tarifaDiaria }) {
  const { data, error } = await db
    .from("personas")
    .insert({ nombre, cargo, tarifa_diaria: tarifaDiaria, activo: true })
    .select()
    .single();
  if (error) throw error;
  return data;
}

export async function fetchIniciativas(centroCostoId) {
  const { data, error } = await db
    .from("iniciativas")
    .select("*")
    .eq("centro_costo_id", centroCostoId);
  if (error) throw error;
  return data;
}

export async function fetchAsistenciaDelDia(centroCostoId, fecha) {
  const { data, error } = await db
    .from("asistencia")
    .select("*")
    .eq("centro_costo_id", centroCostoId)
    .eq("fecha", fecha);
  if (error) throw error;
  return data;
}

export async function marcarAsistencia(centroCostoId, personaId, fecha, presente) {
  const { error } = await db.from("asistencia").upsert(
    {
      centro_costo_id: centroCostoId,
      persona_id: personaId,
      fecha,
      presente,
    },
    { onConflict: "centro_costo_id,persona_id,fecha" }
  );
  if (error) throw error;
}

export async function fetchGastosDelDia(centroCostoId, fecha) {
  const { data, error } = await db
    .from("gastos")
    .select("*")
    .eq("centro_costo_id", centroCostoId)
    .eq("fecha", fecha)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return data;
}

export async function agregarGasto({ centroCostoId, fecha, descripcion, monto, categoria, facturaId }) {
  const { error } = await db.from("gastos").insert({
    centro_costo_id: centroCostoId,
    fecha,
    descripcion,
    monto,
    categoria,
    factura_id: facturaId ?? null,
  });
  if (error) throw error;
}

// Sube la foto a Storage y crea el registro de factura en estado 'pendiente'.
// El OCR (Google Cloud Vision) se llama desde una Edge Function de Supabase
export async function subirFactura(centroCostoId, file) {
  const path = `facturas/${centroCostoId}/${Date.now()}_${file.name}`;
  const { error: uploadError } = await supabase.storage.from("facturas").upload(path, file);
  if (uploadError) throw uploadError;

  const { data: publicUrl } = supabase.storage.from("facturas").getPublicUrl(path);

  const { data, error } = await db
    .from("facturas")
    .insert({
      centro_costo_id: centroCostoId,
      foto_url: publicUrl.publicUrl,
      estado_ocr: "confirmada", // ya no se procesa con OCR, queda guardada directamente
    })
    .select()
    .single();
  if (error) throw error;
  return data;
}

export async function fetchFacturasCentro(centroCostoId, soloHoy = true) {
  let query = db
    .from("facturas")
    .select("*")
    .eq("centro_costo_id", centroCostoId)
    .order("created_at", { ascending: false })
    .limit(30);

  if (soloHoy) {
    const inicio = new Date();
    inicio.setHours(0, 0, 0, 0);
    query = query.gte("created_at", inicio.toISOString());
  }

  const { data, error } = await query;
  if (error) throw error;
  return data;
}

export async function fetchFacturaPorId(id) {
  const { data, error } = await db.from("facturas").select("*").eq("id", id).single();
  if (error) throw error;
  return data;
}

export async function fetchFacturacion(centroCostoId) {
  const { data, error } = await db
    .from("facturacion")
    .select("*")
    .eq("centro_costo_id", centroCostoId)
    .order("mes", { ascending: false });
  if (error) throw error;
  return data;
}

// ---- Dashboard general (todos los centros de costo) ----

export async function fetchResumenGeneral() {
  const [{ data: centros, error: e1 }, { data: fact, error: e2 }, { data: gastos, error: e3 }] = await Promise.all([
    db.from("centros_costo").select("*").eq("activo", true).order("nombre"),
    db.from("facturacion").select("*"),
    db.from("gastos").select("centro_costo_id, monto, fecha"),
  ]);
  if (e1) throw e1;
  if (e2) throw e2;
  if (e3) throw e3;
  return { centros, facturacion: fact, gastos };
}

export async function eliminarFactura(id, fotoUrl) {
  // Borra el archivo de Storage también, usando la ruta dentro del bucket
  if (fotoUrl) {
    const path = fotoUrl.split("/storage/v1/object/public/facturas/")[1];
    if (path) {
      await supabase.storage.from("facturas").remove([path]);
    }
  }
  const { error } = await db.from("facturas").delete().eq("id", id);
  if (error) throw error;
}