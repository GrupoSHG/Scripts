// supabase/functions/procesar-factura/index.ts
//
// Recibe { record: { id, foto_url, centro_costo_id } } (formato de un
// Database Webhook de Supabase disparado on INSERT en 'facturas'),
// llama a Google Cloud Vision para leer el texto de la imagen,
// intenta extraer proveedor / monto / fecha, y actualiza el registro.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const GOOGLE_VISION_API_KEY = Deno.env.get("GOOGLE_VISION_API_KEY")!;

const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

Deno.serve(async (req) => {
  try {
    const payload = await req.json();
    const factura = payload.record ?? payload; // soporta llamada directa o webhook

    console.log("Procesando factura:", factura?.id, factura?.foto_url);

    if (!factura?.id || !factura?.foto_url) {
      return new Response(JSON.stringify({ error: "Falta id o foto_url" }), { status: 400 });
    }

    if (!GOOGLE_VISION_API_KEY) {
      console.error("GOOGLE_VISION_API_KEY no está configurada");
      await supabase.from("facturas").update({ estado_ocr: "error" }).eq("id", factura.id);
      return new Response(JSON.stringify({ error: "Falta GOOGLE_VISION_API_KEY" }), { status: 200 });
    }

    // 1. Descargar la imagen y convertirla a base64
    const imgResp = await fetch(factura.foto_url);
    if (!imgResp.ok) throw new Error(`No se pudo descargar la imagen: ${imgResp.status}`);
    const imgBuffer = await imgResp.arrayBuffer();
    console.log("Imagen descargada, tamaño:", imgBuffer.byteLength, "bytes");
    const base64Image = arrayBufferToBase64(imgBuffer);

    // 2. Llamar a Google Cloud Vision (DOCUMENT_TEXT_DETECTION)
    const visionResp = await fetch(
      `https://vision.googleapis.com/v1/images:annotate?key=${GOOGLE_VISION_API_KEY}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requests: [
            {
              image: { content: base64Image },
              features: [{ type: "DOCUMENT_TEXT_DETECTION" }],
            },
          ],
        }),
      }
    );

    console.log("Status de respuesta de Vision API:", visionResp.status);
    const visionData = await visionResp.json();

    // Si Vision devolvió un error (API key inválida, facturación no habilitada, etc.)
    if (visionData?.responses?.[0]?.error) {
      console.error("Error de Vision API:", JSON.stringify(visionData.responses[0].error));
      await supabase.from("facturas").update({ estado_ocr: "error" }).eq("id", factura.id);
      return new Response(JSON.stringify({ error: visionData.responses[0].error }), { status: 200 });
    }
    if (!visionResp.ok) {
      console.error("Vision API respondió con error HTTP:", JSON.stringify(visionData));
      await supabase.from("facturas").update({ estado_ocr: "error" }).eq("id", factura.id);
      return new Response(JSON.stringify({ error: visionData }), { status: 200 });
    }

    const texto: string = visionData?.responses?.[0]?.fullTextAnnotation?.text ?? "";
    console.log("Texto detectado (primeros 200 caracteres):", texto.slice(0, 200) || "(vacío)");

    if (!texto) {
      console.warn("OCR no devolvió texto para la factura", factura.id);
      await supabase.from("facturas").update({ estado_ocr: "error" }).eq("id", factura.id);
      return new Response(JSON.stringify({ error: "OCR no devolvió texto" }), { status: 200 });
    }

    // 3. Extraer campos con heurísticas simples sobre el texto plano
    const { proveedor, monto, fecha } = extraerCampos(texto);
    console.log("Campos extraídos:", { proveedor, monto, fecha });

    // 4. Guardar resultado — queda en 'leida', el usuario confirma/corrige en la app
    const { error } = await supabase
      .from("facturas")
      .update({
        proveedor,
        monto,
        fecha,
        estado_ocr: "leida",
      })
      .eq("id", factura.id);

    if (error) throw error;

    return new Response(JSON.stringify({ ok: true, proveedor, monto, fecha }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    console.error("Error inesperado en procesar-factura:", err);
    return new Response(JSON.stringify({ error: String(err) }), { status: 500 });
  }
});

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000; // 32 KB por bloque, evita el límite de argumentos de la función
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }
  return btoa(binary);
}

function extraerCampos(texto: string) {
  const lineas = texto.split("\n").map((l) => l.trim()).filter(Boolean);

  // Monto: busca "TOTAL" seguido de un número, o el número más grande con formato $
  let monto: number | null = null;
  const totalRegex = /(total|monto total|total a pagar)[^\d]{0,10}([\d.,]+)/i;
  for (const linea of lineas) {
    const m = linea.match(totalRegex);
    if (m) {
      monto = parsearMonto(m[2]);
      if (monto) break;
    }
  }
  if (!monto) {
    // Fallback: el número más grande encontrado con formato tipo $12.345 o 12345
    const numeros = [...texto.matchAll(/\$?\s?([\d]{1,3}(?:[.,]\d{3})+|\d{4,})/g)]
      .map((m) => parsearMonto(m[1]))
      .filter((n): n is number => n !== null);
    if (numeros.length) monto = Math.max(...numeros);
  }

  // Proveedor: primera línea "razonable" (letras, sin muchos números), típicamente el encabezado
  let proveedor: string | null = null;
  for (const linea of lineas.slice(0, 6)) {
    const letras = (linea.match(/[A-Za-zÁÉÍÓÚÑáéíóúñ]/g) || []).length;
    const digitos = (linea.match(/\d/g) || []).length;
    if (letras >= 4 && digitos <= letras) {
      proveedor = linea;
      break;
    }
  }

  // Fecha: formato dd/mm/yyyy o dd-mm-yyyy
  let fecha: string | null = null;
  const fechaMatch = texto.match(/(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})/);
  if (fechaMatch) {
    let [, d, mo, y] = fechaMatch;
    if (y.length === 2) y = `20${y}`;
    fecha = `${y}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}`;
  }

  return { proveedor, monto, fecha };
}

function parsearMonto(raw: string): number | null {
  // Normaliza "12.345" o "12,345" o "12345" a número entero (CLP sin decimales)
  const limpio = raw.replace(/\./g, "").replace(/,/g, "");
  const n = parseInt(limpio, 10);
  return Number.isFinite(n) ? n : null;
}