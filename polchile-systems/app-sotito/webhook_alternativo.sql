-- Alternativa al Database Webhook por UI: crea el mismo efecto con un
-- trigger de Postgres que llama directamente a la Edge Function vía pg_net.
-- Usar solo si "Database → Webhooks" sigue fallando con el error de
-- "schema supabase_functions does not exist" después de habilitar pg_net.

create extension if not exists pg_net with schema extensions;

create or replace function fn_llamar_ocr_factura()
returns trigger as $$
begin
  perform net.http_post(
    url := 'https://ffxopvzxyeacpbtxuagu.supabase.co/functions/v1/procesar-factura',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer TU_SERVICE_ROLE_KEY_AQUI'
    ),
    body := jsonb_build_object('record', row_to_json(new))
  );
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists trg_ocr_factura on facturas;
create trigger trg_ocr_factura
after insert on facturas
for each row execute function fn_llamar_ocr_factura();
