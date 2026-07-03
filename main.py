"""
Entry point: fetch frost data → calculate hours → generate interactive map.

Usage:
  python main.py
  python main.py --start 2026-04-01 --end 2026-06-27
  python main.py --start 2026-05-01 --end 2026-06-27 --debug
  python main.py --load-cache output/raw_response.json   # skip API call
"""

import argparse
import os
import sys
from datetime import datetime

from config import DATE_START, DATE_END, LOCATIONS, FROST_THRESHOLD
from meteoblue_client import fetch_all_temperatures, save_raw_response, load_raw_response
from frost_calculator import calculate_frost_hours, print_summary
from map_generator import generate_map


def parse_args():
    parser = argparse.ArgumentParser(
        description="Mapa interactivo de heladas en Argentina"
    )
    parser.add_argument(
        "--start",
        default=DATE_START,
        help=f"Fecha de inicio (YYYY-MM-DD o YYYY-MM-DDT+00:00). Default: {DATE_START}",
    )
    parser.add_argument(
        "--end",
        default=DATE_END,
        help=f"Fecha de fin   (YYYY-MM-DD o YYYY-MM-DDT+00:00). Default: {DATE_END}",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=FROST_THRESHOLD,
        help=f"Umbral de helada en °C. Default: {FROST_THRESHOLD}",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Imprimir estructura de respuesta API para diagnóstico",
    )
    parser.add_argument(
        "--save-cache",
        action="store_true",
        help="Guardar respuesta raw de la API en output/raw_response.json",
    )
    parser.add_argument(
        "--load-cache",
        metavar="FILE",
        default=None,
        help="Saltar llamada API y usar respuesta raw guardada previamente",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="No exportar CSV",
    )
    return parser.parse_args()


def normalise_date(date_str: str) -> str:
    """Ensure date string has the T+00:00 suffix Meteoblue expects."""
    if "T" not in date_str:
        return date_str + "T+00:00"
    return date_str


def export_csv(results: list, path: str) -> None:
    try:
        import pandas as pd

        df = pd.DataFrame(results)[
            ["name", "lat", "lon", "frost_hours", "total_hours", "min_temp", "error"]
        ]
        df.columns = [
            "Localidad",
            "Latitud",
            "Longitud",
            "Horas_helada",
            "Horas_totales",
            "T_min_C",
            "Error",
        ]
        df.sort_values("Horas_helada", ascending=False, inplace=True)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  CSV exportado: {path}")
    except ImportError:
        print("  pandas no instalado; saltando exportación CSV.")


def export_excel(results: list, path: str) -> None:
    try:
        import pandas as pd

        df = pd.DataFrame(results)[
            ["name", "lat", "lon", "frost_hours", "total_hours", "min_temp"]
        ]
        df.columns = [
            "Localidad",
            "Latitud",
            "Longitud",
            "Horas_helada",
            "Horas_totales",
            "T_min_C",
        ]
        df.sort_values("Horas_helada", ascending=False, inplace=True)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        df.to_excel(path, index=False)
        print(f"  Excel exportado: {path}")
    except ImportError:
        print("  openpyxl/pandas no instalado; saltando exportación Excel.")


def main():
    args = parse_args()
    date_start = normalise_date(args.start)
    date_end = normalise_date(args.end)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    # Always resolve output relative to this script's directory
    _here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(_here, "output")
    os.makedirs(out_dir, exist_ok=True)
    map_path = os.path.join(out_dir, f"heladas_{ts}.html")
    csv_path = os.path.join(out_dir, f"heladas_{ts}.csv")
    xlsx_path = os.path.join(out_dir, f"heladas_{ts}.xlsx")
    cache_path = os.path.join(out_dir, f"raw_response_{ts}.json")

    print("=" * 60)
    print("  Mapa de Heladas Argentina")
    print(f"  Periodo: {date_start} al {date_end}")
    print(f"  Umbral:  T < {args.threshold} °C")
    print(f"  Puntos:  {len(LOCATIONS)}")
    print("=" * 60)

    # 1. Fetch or load raw API data
    if args.load_cache:
        print(f"\n[1/3] Cargando respuesta desde caché: {args.load_cache}")
        raw_responses = load_raw_response(args.load_cache)
    else:
        print("\n[1/3] Consultando Meteoblue API...")
        raw_responses = fetch_all_temperatures(
            LOCATIONS, date_start, date_end, debug=args.debug
        )
        if args.save_cache:
            save_raw_response(raw_responses, cache_path)

    # 2. Calculate frost hours
    print("\n[2/3] Calculando horas de helada...")
    results = calculate_frost_hours(raw_responses, threshold=args.threshold)
    print_summary(results, threshold=args.threshold)

    # 3. Generate map & exports
    print("\n[3/3] Generando mapa interactivo...")
    generate_map(results, date_start, date_end, map_path)

    if not args.no_csv:
        export_csv(results, csv_path)
        export_excel(results, xlsx_path)

    print("\nListo.")
    print(f"  Abrir en navegador: {os.path.abspath(map_path)}")


if __name__ == "__main__":
    main()
