import { supabase } from "./supabaseClient";

export async function fetchCentros() {
  const { data, error } = await supabase
    .from("centros_costo")
    .select("*")
    .eq("activo", true)
    .order("codigo");
  if (error) throw error;
  return data;
}

export async function fetchPersonas() {
  const { data, error } = await supabase
    .from("personas")
    .select("*")
    .eq("activo", true)
    .order("nombre");
  if (error) throw error;
  return data;
}

export async function fetchIniciativas(centroCostoId) {
  const { data, error } = await supabase
    .from("iniciativas")
    .select("*")
    .eq("centro_costo_id", centroCostoId);
  if (error) throw error;
  return data;
}

export async function fetchAsistenciaDelDia(centroCostoId, fecha) {
  const { data, error } = await supabase
    .from("asistencia")
    .select("*")
    .eq("centro_costo_id", centroCostoId)
    .eq("fecha", fecha);
  if (error) throw error;
  return data;
}

export async function marcarAsistencia(centroCostoId, personaId, fecha, presente) {
  const { error } = await supabase.from("asistencia").upsert(
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
  const { data, error } = await supabase
    .from("gastos")
    .select("*")
    .eq("centro_costo_id", centroCostoId)
    .eq("fecha", fecha)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return data;
}

export async function agregarGasto({ centroCostoId, fecha, descripcion, monto, categoria, facturaId }) {
  const { error } = await supabase.from("gastos").insert({
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
// que procesa la imagen y actualiza el registro a 'leida'.
export async function subirFactura(centroCostoId, file) {
  const path = `facturas/${centroCostoId}/${Date.now()}_${file.name}`;
  const { error: uploadError } = await supabase.storage.from("facturas").upload(path, file);
  if (uploadError) throw uploadError;

  const { data: publicUrl } = supabase.storage.from("facturas").getPublicUrl(path);

  const { data, error } = await supabase
    .from("facturas")
    .insert({
      centro_costo_id: centroCostoId,
      foto_url: publicUrl.publicUrl,
      estado_ocr: "pendiente",
    })
    .select()
    .single();
  if (error) throw error;
  return data;
}

export async function fetchFacturacion(centroCostoId) {
  const { data, error } = await supabase
    .from("facturacion")
    .select("*")
    .eq("centro_costo_id", centroCostoId);
  if (error) throw error;
  return data;
}
