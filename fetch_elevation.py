"""
fetch_elevation.py — Obtiene elevación (msnm) para todos los puntos de la grilla.

Usa la API gratuita de Open-Meteo (sin clave API).
Output: data/grid_elevation.json  →  {"lat,lon": metros, ...}

Uso:
  uv run python fetch_elevation.py
  uv run python fetch_elevation.py --csv heladas.csv --out data/grid_elevation.json
"""
import argparse, csv, json, os, sys, time
import requests, urllib3

_HERE = os.path.dirname(os.path.abspath(__file__))
ELEV_URL   = "https://api.open-meteo.com/v1/elevation"
BATCH_SIZE = 50
SLEEP_S    = 2.0
MAX_RETRY  = 4

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def load_grid(csv_path: str) -> list[tuple[float, float]]:
    pts = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                pts.append((round(float(row["lat"]), 4), round(float(row["lon"]), 4)))
            except (ValueError, KeyError):
                pass
    return pts


def fetch_batch(lats: list[float], lons: list[float]) -> list[float | None]:
    params = {
        "latitude":  ",".join(f"{v:.4f}" for v in lats),
        "longitude": ",".join(f"{v:.4f}" for v in lons),
    }
    wait = 5.0
    for attempt in range(MAX_RETRY):
        try:
            r = requests.get(ELEV_URL, params=params, timeout=30)
            if r.status_code == 429:
                print(f"  429 rate-limit, esperando {wait:.0f}s...")
                time.sleep(wait)
                wait *= 2
                continue
            r.raise_for_status()
            return r.json().get("elevation", [None] * len(lats))
        except Exception as exc:
            if attempt < MAX_RETRY - 1:
                time.sleep(wait); wait *= 2
            else:
                print(f"  ERROR: {exc}")
    return [None] * len(lats)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(_HERE, "heladas.csv"))
    p.add_argument("--out", default=os.path.join(_HERE, "data", "grid_elevation.json"))
    args = p.parse_args()

    print(f"Cargando grilla: {args.csv}")
    pts = load_grid(args.csv)
    print(f"  {len(pts)} puntos")

    # Load existing data to resume interrupted runs
    result: dict[str, float] = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            result = json.load(f)
        print(f"  Cargando {len(result)} elevaciones existentes de {args.out}")

    # Only fetch points not yet in result
    pending = [(lat, lon) for lat, lon in pts if f"{lat},{lon}" not in result]
    print(f"  Pendientes: {len(pending)} puntos")
    if not pending:
        print("  Todos los puntos ya tienen elevación.")
        return

    chunks = [pending[i:i+BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]

    for ci, chunk in enumerate(chunks):
        lats = [p[0] for p in chunk]  # type: ignore
        lons = [p[1] for p in chunk]  # type: ignore
        elevs = fetch_batch(lats, lons)
        for (lat, lon), elev in zip(chunk, elevs):
            if elev is not None:
                result[f"{lat},{lon}"] = round(elev, 1)
        pct = (ci+1)/len(chunks)*100
        ok  = sum(1 for e in elevs if e is not None)
        print(f"  Batch {ci+1}/{len(chunks)} ({pct:.0f}%)  OK:{ok}/{len(chunk)}  total={len(result)}")
        # Save incrementally so interruptions don't lose progress
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
        if ci < len(chunks)-1:
            time.sleep(SLEEP_S)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    kb = os.path.getsize(args.out) // 1024
    print(f"\nGuardado: {args.out}  ({len(result)} puntos, {kb} KB)")

    vals = sorted(result.values())
    if vals:
        print(f"Elevación  min={vals[0]}m  p25={vals[len(vals)//4]}m"
              f"  p50={vals[len(vals)//2]}m  p75={vals[3*len(vals)//4]}m  max={vals[-1]}m")


if __name__ == "__main__":
    main()
