"""Agente Desarrollador: Claude Code sin interfaz sobre un clon del repo y un PR en borrador.

Nunca fusiona ni publica: deja una rama agente/<id> y un PR en borrador para que alguien lo
revise. Necesita AGENTES_GH_TOKEN (PAT fine-grained del dueño GrupoSHG con Contents y Pull
requests en lectura y escritura sobre GrupoSHG_Systems y Scripts). Scripts es un repo público:
nada de lo que hace Claude Code se imprime en el log; solo queda en la respuesta de Supabase.
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .perfiles import DESARROLLADOR

MODELO = "claude-opus-5-5"
HERRAMIENTAS = "Read,Edit,Write,Glob,Grep"

INSTRUCCIONES = """Eres el agente Desarrollador de la Oficina de Agentes de Grupo SHG. Trabajas sin \
supervisión en un clon del repo {repo}; nadie puede responderte preguntas. Lee primero CLAUDE.md del \
repo y respeta sus reglas (código, comentarios y textos en español). Haz el cambio más chico que \
cumpla lo pedido, con el estilo del código que lo rodea. No toques archivos .env, credenciales, \
.claude/ ni .netlify/. No hagas commit: lo hace el sistema y abre un PR en borrador que una persona \
revisa. Si lo pedido no se puede hacer o no está claro, no cambies nada y explica por qué.

Al terminar responde en español, en Markdown y en pocas líneas: qué cambiaste (archivos), qué falta \
probar a mano y cualquier duda.

Lo pedido:
{texto}"""


class ErrorDesarrollador(RuntimeError):
    pass


def _correr(args, cwd, env=None, entrada=None, timeout=600):
    """Corre un comando sin imprimir nada en el log (el repo es público)."""
    p = subprocess.run(args, cwd=cwd, env=env, input=entrada, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        # Solo el nombre del comando y el código: la salida puede traer código privado.
        raise ErrorDesarrollador(f"Falló `{args[0]} {args[1] if len(args) > 1 else ''}` (código {p.returncode}).")
    return p.stdout


def rama(id_, texto):
    corto = re.sub(r"[^a-z0-9]+", "-", texto.lower())[:40].strip("-") or "cambio"
    return f"agente/{id_}-{corto}"


def entorno_claude():
    """Entorno para Claude Code, sin los tokens de GitHub ni de Supabase, y si usa la suscripción.

    Con CLAUDE_CODE_OAUTH_TOKEN (el que genera `claude setup-token` con una suscripción de Claude)
    Claude Code consume el plan de esa cuenta en vez de la API; se quita ANTHROPIC_API_KEY porque
    si está presente Claude Code la prefiere.
    """
    fuera = {"AGENTES_GH_TOKEN", "SUPABASE_SERVICE_KEY", "GH_TOKEN"}
    suscripcion = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
    if suscripcion:
        fuera.add("ANTHROPIC_API_KEY")
    else:
        fuera.add("CLAUDE_CODE_OAUTH_TOKEN")
    return {k: v for k, v in os.environ.items() if k not in fuera}, suscripcion


def responder(instruccion, tope_usd):
    """Devuelve (respuesta, costo_usd cobrado por la API, tokens) — con suscripción el costo es 0 y
    tokens dice cuánto habría costado por la API."""
    token = os.environ.get("AGENTES_GH_TOKEN")
    if not token:
        raise ErrorDesarrollador("Falta el secret AGENTES_GH_TOKEN en GrupoSHG/Scripts: sin él el Desarrollador "
                                 "no puede clonar ni abrir PRs (ver agentes-ia/README.md).")
    repo = (instruccion.get("parametros") or {}).get("repo") or "GrupoSHG_Systems"
    if repo not in DESARROLLADOR["repos"]:
        raise ErrorDesarrollador(f"Repo no permitido: {repo}")
    id_, texto = instruccion["id"], instruccion["texto"]

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / repo
        url = f"https://x-access-token:{token}@github.com/GrupoSHG/{repo}.git"
        _correr(["git", "clone", "--quiet", "--depth", "20", url, str(dest)], cwd=tmp)
        r = rama(id_, texto)
        _correr(["git", "checkout", "--quiet", "-b", r], cwd=dest)

        env, suscripcion = entorno_claude()
        salida = _correr(["claude", "-p", "--output-format", "json", "--model", MODELO,
                          "--permission-mode", "acceptEdits", "--allowedTools", HERRAMIENTAS,
                          "--max-budget-usd", f"{tope_usd:.2f}"],
                         cwd=dest, env=env, entrada=INSTRUCCIONES.format(repo=repo, texto=texto), timeout=1500)
        try:
            res = json.loads(salida)
        except json.JSONDecodeError as e:
            raise ErrorDesarrollador("Claude Code no devolvió JSON.") from e
        costo = float(res.get("total_cost_usd") or 0)
        info = {"suscripcion": suscripcion, "costo_equivalente_usd": round(costo, 4)}
        cobrado = 0.0 if suscripcion else costo
        resumen = (res.get("result") or "").strip() or "(Claude Code terminó sin texto.)"
        if res.get("is_error"):
            return f"Claude Code terminó con error.\n\n{resumen}", cobrado, info

        _correr(["git", "add", "-A", "--", ".", ":(exclude).claude", ":(exclude).netlify", ":(exclude,glob)**/.env"], cwd=dest)
        if not _correr(["git", "diff", "--cached", "--name-only"], cwd=dest).strip():
            return f"{resumen}\n\n_No hubo cambios en el repo, así que no se abrió PR._", cobrado, info

        titulo = f"Agente: {texto.splitlines()[0][:70]}"
        _correr(["git", "-c", "user.name=Oficina de Agentes", "-c", "user.email=agentes@gruposhg.cl",
                 "commit", "--quiet", "-F", "-"], cwd=dest,
                entrada=f"{titulo}\n\nInstrucción #{id_} de la Oficina de Agentes.\n\n"
                        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")
        _correr(["git", "push", "--quiet", "origin", r], cwd=dest)
        cuerpo = (f"Cambio hecho por el agente Desarrollador de la Oficina de Agentes (instrucción #{id_}).\n\n"
                  f"**Lo pedido:**\n\n> {texto}\n\n**Resumen del agente:**\n\n{resumen}\n\n"
                  "Revisar antes de marcar como listo y fusionar.\n\n"
                  "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n")
        pr = _correr(["gh", "pr", "create", "--draft", "--repo", f"GrupoSHG/{repo}", "--head", r,
                      "--title", titulo, "--body-file", "-"], cwd=dest, entrada=cuerpo,
                     env={**os.environ, "GH_TOKEN": token}).strip().splitlines()[-1]
        return f"{resumen}\n\n**PR en borrador:** {pr}", cobrado, info
