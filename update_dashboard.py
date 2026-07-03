"""
update_dashboard.py -- Orquesta el fetch de datos, regeneracion del dashboard
y deploy automatico a GitHub Pages.

Uso manual:
  uv run python update_dashboard.py              # anio actual, Jan 1 a hoy-5d
  uv run python update_dashboard.py --year 2025  # anio especifico
  uv run python update_dashboard.py --start 2026-04-01 --end 2026-06-30
  uv run python update_dashboard.py --no-deploy  # sin push a GitHub

Disenado para correr desde el Task Scheduler de Windows semanalmente.
Logea en logs/update_YYYYMMDD_HHMM.log
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta, datetime
from pathlib import Path

# Forzar stdout a UTF-8 para evitar UnicodeEncodeError en consola Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_HERE     = Path(__file__).parent.resolve()
LOGS      = _HERE / "logs"
DOCS      = _HERE / "docs"
ERA5T_LAG = 5  # dias de retraso en ERA5T


# -- Logging -------------------------------------------------------------------

_log_file = None

def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}]  {msg}"
    print(line, flush=True)
    if _log_file:
        _log_file.write(line + "\n")
        _log_file.flush()


# -- Date helpers --------------------------------------------------------------

def default_start(year: int) -> str:
    return f"{year}-01-01"

def default_end() -> str:
    return (date.today() - timedelta(days=ERA5T_LAG)).strftime("%Y-%m-%d")


# -- Subprocess runner ---------------------------------------------------------

def run_step(label: str, cmd: list) -> bool:
    """Ejecuta un comando, loguea stdout/stderr, retorna True si exitoso."""
    log(f">> {label}")
    log(f"   Comando: {' '.join(str(c) for c in cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_HERE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in result.stdout.splitlines():
            log(f"   {line}")
        if result.returncode != 0:
            log(f"FALLO: {label} (exit code {result.returncode})")
            return False
        log(f"OK:    {label}")
        return True
    except Exception as exc:
        log(f"ERROR: {label} -- {exc}")
        return False


# -- GitHub deploy -------------------------------------------------------------

def deploy_to_github(start: str, end: str) -> bool:
    """Copia el HTML como docs/index.html y hace git commit + push."""
    log("")
    log(">> PASO 3/3: Deploy a GitHub Pages")

    # Buscar el HTML mas reciente en output/
    output_dir = _HERE / "output"
    htmls = sorted(output_dir.glob("dashboard_*.html"), key=lambda p: p.stat().st_mtime)
    if not htmls:
        log("ERROR: No hay HTML en output/ para deployar.")
        return False

    latest_html = htmls[-1]
    log(f"   HTML fuente: {latest_html.name} ({latest_html.stat().st_size // 1024} KB)")

    # Copiar como docs/index.html
    DOCS.mkdir(exist_ok=True)
    shutil.copy2(latest_html, DOCS / "index.html")
    log(f"   Copiado a: docs/index.html")

    # git add
    ok = run_step("git add docs/index.html", ["git", "add", "docs/index.html"])
    if not ok:
        return False

    # git commit
    commit_msg = f"Dashboard actualizado: {start} al {end}"
    result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(_HERE),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in result.stdout.splitlines():
        log(f"   {line}")
    if result.returncode not in (0, 1):  # 1 = "nothing to commit" es OK
        log(f"FALLO: git commit (exit code {result.returncode})")
        return False
    if "nothing to commit" in result.stdout:
        log("   (sin cambios desde el ultimo commit)")
        return True
    log("OK:    git commit")

    # git push
    ok = run_step("git push", ["git", "push"])
    if not ok:
        return False

    log("OK:    Deploy completado. GitHub Pages actualizara en ~1 minuto.")
    return True


# -- Main ----------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--year",      type=int, default=None)
    p.add_argument("--start",     default=None)
    p.add_argument("--end",       default=None)
    p.add_argument("--no-deploy", action="store_true",
                   help="Saltar el git push a GitHub Pages")
    return p.parse_args()


def main() -> int:
    global _log_file

    args = parse_args()

    year  = args.year or date.today().year
    start = args.start or default_start(year)
    end   = args.end   or default_end()

    if start > end:
        print(f"ERROR: start={start} es posterior a end={end}.")
        print(f"Proba con: --year {year - 1}")
        return 1

    LOGS.mkdir(exist_ok=True)
    log_path = LOGS / f"update_{datetime.now():%Y%m%d_%H%M}.log"
    _log_file = open(log_path, "w", encoding="utf-8")

    try:
        log("=" * 60)
        log("  update_dashboard.py -- inicio")
        log(f"  Periodo: {start} al {end}")
        log(f"  Deploy:  {'NO (--no-deploy)' if args.no_deploy else 'SI (GitHub Pages)'}")
        log(f"  Dir:     {_HERE}")
        log("=" * 60)

        python = sys.executable

        # Paso 1: Fetch de datos
        ok = run_step(
            "PASO 1/3: Fetch de datos (Meteoblue ERA5T)",
            [python, str(_HERE / "fetch_data.py"),
             "--start", start, "--end", end],
        )
        if not ok:
            log("ABORTADO: fallo en el fetch. Revisa el log.")
            return 1

        # Paso 2: Regenerar dashboard
        ok = run_step(
            "PASO 2/3: Regenerar dashboard HTML",
            [python, str(_HERE / "build_dashboard.py"),
             "--start", start, "--end", end],
        )
        if not ok:
            log("ABORTADO: fallo en el build.")
            return 1

        # Paso 3: Deploy a GitHub Pages (saltar si --no-deploy)
        if not args.no_deploy:
            ok = deploy_to_github(start, end)
            if not ok:
                log("ADVERTENCIA: fallo el deploy a GitHub. El dashboard local si se actualizo.")
                # No es fatal — el dashboard local esta actualizado
        else:
            log("Deploy omitido (--no-deploy).")

        log("")
        log("COMPLETADO: Dashboard actualizado exitosamente.")
        log(f"Log: {log_path}")
        return 0

    finally:
        _log_file.close()


if __name__ == "__main__":
    sys.exit(main())
