# Licitaciones Mercado Público · M5 Industrial (nueva versión)

Revisa cada día las licitaciones de Mercado Público (ChileCompra), filtra las que calzan con el
perfil de M5 Industrial (Grupo SHG) y deja el resultado en `salida/`. Reemplazará a
`../mercado-publico/` cuando esté completa.

Etapas: 1 descarga y filtro barato (hecha) · 2 puntuación con Claude · 3 reporte diario ·
4 Supabase · 5 GitHub Actions.

## Instalación

```
cd M5_Systems/licitaciones-m5
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # Windows
```

Credenciales **solo por variables de entorno**: `MP_TICKET`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`,
`SUPABASE_KEY`. Para probar en local, copiar `.env.example` a `.env` en esta carpeta y completarlo
(`.env` está en `.gitignore`). En GitHub Actions son secrets del repo `GrupoSHG/Scripts`.

## Configuración

- `config/perfil_m5.yaml`: qué le interesa a M5 (palabras clave, tipos de obra, regiones, montos...).
  Sin `palabras_clave_incluir` o `tipos_de_obra_que_interesan` el proceso no corre. **El repo es
  público**: en el repo queda la plantilla vacía, y el perfil real se completa solo en local o se
  pasa en Actions con el secret `PERFIL_M5_YAML` (el contenido YAML completo), que tiene prioridad
  sobre el archivo. `--perfil RUTA` usa otro archivo.
- `config/ajustes.yaml`: timeouts, reintentos, pausa entre llamadas, tope de solicitudes (80 % de
  10.000 diarias), ventana nocturna 22:00–07:00 y códigos de estado verificados.

## Ejecución local (desde esta carpeta)

```
.venv\Scripts\python -m licitaciones descargar --max 20          # prueba acotada (de día, máx. 50)
.venv\Scripts\python -m licitaciones descargar --fecha 15102026
.venv\Scripts\python -m licitaciones detalle 4174-34-LP26        # qué entrega la API para una licitación
.venv\Scripts\python -m unittest discover -s tests -t .
```

Salida en `salida/AAAA-MM-DD/`: `listado.json`, `descartadas.json` (con el motivo), `filtradas.json`
(entrada de la etapa 2) y `embudo.json`. Códigos de salida: 0 ok, 1 configuración, 2 error de la
API, 3 tope de solicitudes.

Cómo filtra: el listado solo trae código, nombre, estado y cierre, así que primero filtra por
nombre y pide el detalle (1 solicitud) solo de esas; con el detalle vuelve a filtrar por
descripción, ítems, rubro UNSPSC 72, región y monto.

## Despliegue

Se completa en la etapa 5 (workflow en `.github/workflows/` de este repo).

Lo verificado contra la API real está en `NOTAS_API.md`.
