"""
fetch_data.py — Descarga temperaturas + precipitación horaria para la grilla y calcula métricas.

Uso:
  uv run python fetch_data.py
  uv run python fetch_data.py --start 2026-05-01 --end 2026-06-27
  uv run python fetch_data.py --load-cache data/raw_20260702.json   # evita API
  uv run python fetch_data.py --max-points 200                       # subconjunto rápido
"""
import argparse, csv, json, math, os, sys, time
from datetime import datetime, timedelta

import requests, urllib3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import METEOBLUE_TOKEN, METEOBLUE_URL, VERIFY_SSL, DATE_START, DATE_END, FROST_THRESHOLD

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_HERE = os.path.dirname(os.path.abspath(__file__))
CHUNK_SIZE = 15


# ── CSV helpers ────────────────────────────────────────────────────────────────

def load_grid(csv_path: str) -> list:
    points = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                points.append({
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "alt": float(row.get("alt", 0) or 0),
                })
            except (ValueError, KeyError):
                continue
    print(f"  Grilla: {len(points)} puntos cargados de {os.path.basename(csv_path)}")
    return points


# ── API helpers ────────────────────────────────────────────────────────────────

def _build_payload(locs: list, date_start: str, date_end: str) -> dict:
    return {
        "units": {"temperature": "C", "velocity": "km/h", "length": "metric", "energy": "watts"},
        "geometry": {
            "type": "MultiPoint",
            "coordinates": [[loc["lon"], loc["lat"], loc["alt"]] for loc in locs],
            "locationNames": [f"p{i}" for i in range(len(locs))],
        },
        "format": "json",
        "timeIntervals": [f"{date_start}/{date_end}"],
        "timeIntervalsAlignment": "none",
        "queries": [{
            "domain": "ERA5T",
            "gapFillDomain": "ERA5",
            "timeResolution": "hourly",
            "codes": [
                {"code": 11, "level": "2 m above gnd"},
                {"code": 61, "level": "sfc"},
                {"code": 52, "level": "2 m above gnd"},
            ],
        }],
    }


def _extract_code(response, n: int, code_idx: int) -> list:
    """Extrae arrays de datos para un código específico de la respuesta Meteoblue."""
    if not isinstance(response, list) or not response:
        return [None] * n
    item = response[0]
    codes = item.get("codes", [])
    if code_idx >= len(codes):
        return [None] * n
    merged: dict[int, list] = {}
    for interval in codes[code_idx].get("dataPerTimeInterval", []):
        for idx, vals in enumerate(interval.get("data", [])):
            merged.setdefault(idx, []).extend(vals)
    return [merged.get(i) for i in range(n)]


def _extract_temps(response, n: int) -> list:
    return _extract_code(response, n, 0)


def _extract_precip(response, n: int) -> list:
    return _extract_code(response, n, 1)


def fetch_all_data(points: list, date_start: str, date_end: str) -> tuple[list, list, list]:
    """Retorna (all_temps, all_precip, all_humidity) — arrays de arrays horarios por punto."""
    chunks = [points[i:i+CHUNK_SIZE] for i in range(0, len(points), CHUNK_SIZE)]
    all_temps, all_precip, all_humidity = [], [], []
    for ci, chunk in enumerate(chunks):
        print(f"  [{ci+1}/{len(chunks)}] {len(chunk)} pts...", end=" ", flush=True)
        payload = _build_payload(chunk, date_start, date_end)
        url = f"{METEOBLUE_URL}?apikey={METEOBLUE_TOKEN}"
        try:
            resp = requests.post(
                url, json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120, verify=VERIFY_SSL,
            )
            resp.raise_for_status()
            raw = resp.json()
            temps   = _extract_temps(raw, len(chunk))
            precip  = _extract_precip(raw, len(chunk))
            humidity = _extract_code(raw, len(chunk), 2)
            ok = sum(1 for t in temps if t)
            ok_p = sum(1 for p in precip if p)
            ok_h = sum(1 for h in humidity if h)
            print(f"OK (T:{ok}/{len(chunk)}, P:{ok_p}/{len(chunk)}, HR:{ok_h}/{len(chunk)})")
            all_temps.extend(temps)
            all_precip.extend(precip)
            all_humidity.extend(humidity)
        except Exception as exc:
            print(f"ERROR: {exc}")
            all_temps.extend([None] * len(chunk))
            all_precip.extend([None] * len(chunk))
            all_humidity.extend([None] * len(chunk))
        if ci < len(chunks) - 1:
            time.sleep(0.4)
    return all_temps, all_precip, all_humidity


# ── Hargreaves-Samani ETP ──────────────────────────────────────────────────────

def _calc_daily_etp(lat_deg: float, tmax: float, tmin: float, tmean: float, doy: int) -> float:
    """ETP diaria en mm/día via Hargreaves-Samani."""
    lat  = math.radians(lat_deg)
    dr   = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    delt = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    cos_ws = -math.tan(lat) * math.tan(delt)
    ws   = 0.0 if cos_ws >= 1 else (math.pi if cos_ws <= -1 else math.acos(cos_ws))
    Ra   = (24 * 60 / math.pi) * 0.082 * dr * (
        ws * math.sin(lat) * math.sin(delt) + math.cos(lat) * math.cos(delt) * math.sin(ws)
    )
    td = max(0.0, tmax - tmin)
    return max(0.0, 0.0023 * Ra * (tmean + 17.8) * math.sqrt(td))


# ── Metric calculations ────────────────────────────────────────────────────────

def _idx_to_date(idx: int, date_start: str) -> str | None:
    try:
        start = datetime.strptime(date_start.split("T")[0], "%Y-%m-%d")
        return (start + timedelta(hours=idx)).strftime("%d/%m")
    except Exception:
        return None


def compute_metrics(
    points: list,
    all_temps: list,
    all_precip: list | None,
    all_humidity: list | None,
    date_start: str,
    threshold: float = 0.0,
    gdd_base: float = 10.0,
) -> list:
    results = []
    for i, (point, temps) in enumerate(zip(points, all_temps)):
        base = {"lat": round(point["lat"], 4), "lon": round(point["lon"], 4)}
        null_row = {**base, "frost_hours": None, "frost_hours_5": None, "min_temp": None,
                    "degree_days": None, "degree_days_6": None,
                    "avg_amplitude": None, "first_frost": None, "last_frost": None,
                    "frost_free_streak": None,
                    "precip_total": None, "water_balance": None, "dry_streak": None,
                    "avg_humidity": None}

        if not temps:
            results.append(null_row)
            continue

        valid = [t for t in temps if t is not None]
        if not valid:
            results.append({**base, "frost_hours": 0, "frost_hours_5": 0, "min_temp": None,
                             "degree_days": None, "degree_days_6": None,
                             "avg_amplitude": None, "first_frost": None, "last_frost": None,
                             "frost_free_streak": len(temps) // 24,
                             "precip_total": None, "water_balance": None, "dry_streak": None,
                             "avg_humidity": None})
            continue

        # ── temperatura ────────────────────────────────────────────────────────
        frost_hours   = sum(1 for t in valid if t < threshold)
        frost_hours_5 = sum(1 for t in valid if t < 5.0)
        gdd  = sum(max(0.0, t - gdd_base) for t in valid) / 24.0
        gdd6 = sum(max(0.0, t - 6.0)      for t in valid) / 24.0

        amps = []
        for j in range(0, len(valid) - 23, 24):
            day = valid[j:j+24]
            if len(day) == 24:
                amps.append(max(day) - min(day))
        avg_amp = sum(amps) / len(amps) if amps else None

        frost_idxs = [j for j, t in enumerate(valid) if t < threshold]
        first_frost = _idx_to_date(frost_idxs[0],  date_start) if frost_idxs else None
        last_frost  = _idx_to_date(frost_idxs[-1], date_start) if frost_idxs else None

        if frost_idxs:
            gaps, prev = [], 0
            for idx in frost_idxs:
                gaps.append(idx - prev)
                prev = idx + 1
            gaps.append(len(valid) - prev)
            frost_free_streak = max(gaps) // 24
        else:
            frost_free_streak = len(valid) // 24

        # ── hídrico ────────────────────────────────────────────────────────────
        precip_total = water_balance = dry_streak = None
        raw_p = (all_precip[i] if all_precip else None)
        if raw_p:
            num_days = max(len(valid), len(raw_p)) // 24
            daily_precip, daily_tmax, daily_tmin, daily_tmean = [], [], [], []
            for d in range(num_days):
                t_slice = [t for t in valid[d*24:d*24+24] if t is not None]
                p_slice = [p if p is not None else 0.0 for p in raw_p[d*24:d*24+24]]
                daily_precip.append(sum(p_slice))
                if t_slice:
                    daily_tmax.append(max(t_slice))
                    daily_tmin.append(min(t_slice))
                    daily_tmean.append(sum(t_slice) / len(t_slice))
                else:
                    daily_tmax.append(None)
                    daily_tmin.append(None)
                    daily_tmean.append(None)

            precip_total = round(sum(daily_precip), 1)

            start_dt = datetime.strptime(date_start.split("T")[0], "%Y-%m-%d")
            etp_total = 0.0
            for d in range(num_days):
                if daily_tmax[d] is not None and daily_tmin[d] is not None:
                    day_dt = start_dt + timedelta(days=d)
                    doy = day_dt.timetuple().tm_yday
                    etp_total += _calc_daily_etp(
                        point["lat"], daily_tmax[d], daily_tmin[d], daily_tmean[d], doy
                    )
            water_balance = round(precip_total - etp_total, 1)

            dry_streak = 0
            for d in range(len(daily_precip) - 1, -1, -1):
                if daily_precip[d] < 1.0:
                    dry_streak += 1
                else:
                    break

        # ── humedad relativa ──────────────────────────────────────────────────────
        raw_h = (all_humidity[i] if all_humidity else None)
        avg_humidity = None
        if raw_h:
            valid_h = [h for h in raw_h if h is not None]
            if valid_h:
                avg_humidity = round(sum(valid_h) / len(valid_h), 1)

        results.append({
            **base,
            "frost_hours":      frost_hours,
            "frost_hours_5":    frost_hours_5,
            "avg_humidity":     avg_humidity,
            "min_temp":         round(min(valid), 1),
            "degree_days":      round(gdd, 1),
            "degree_days_6":    round(gdd6, 1),
            "avg_amplitude":    round(avg_amp, 1) if avg_amp is not None else None,
            "first_frost":      first_frost,
            "last_frost":       last_frost,
            "frost_free_streak": frost_free_streak,
            "precip_total":     precip_total,
            "water_balance":    water_balance,
            "dry_streak":       dry_streak,
        })

    return results


# ── I/O helpers ────────────────────────────────────────────────────────────────

def save_json(data, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  Guardado: {path}  ({len(data)} registros, {os.path.getsize(path)//1024} KB)")


def load_json(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Fetch frost + hydric data from Meteoblue")
    p.add_argument("--start", default=DATE_START)
    p.add_argument("--end",   default=DATE_END)
    p.add_argument("--csv",   default=os.path.join(_HERE, "heladas.csv"))
    p.add_argument("--threshold", type=float, default=FROST_THRESHOLD)
    p.add_argument("--gdd-base",  type=float, default=10.0)
    p.add_argument("--max-points", type=int,  default=None)
    p.add_argument("--load-cache", metavar="FILE", default=None,
                   help="Cargar métricas JSON previas y saltar API")
    return p.parse_args()


def normalise_date(s: str) -> str:
    return s if "T" in s else s + "T+00:00"


def main():
    args = parse_args()
    date_start = normalise_date(args.start)
    date_end   = normalise_date(args.end)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    data_dir = os.path.join(_HERE, "data")
    metrics_path = os.path.join(data_dir, f"metrics_{ts}.json")

    print("=" * 60)
    print(f"  fetch_data.py  {date_start} al {date_end}")
    print(f"  Umbral: T < {args.threshold}°C | GDD base: {args.gdd_base}°C")
    print("=" * 60)

    if args.load_cache:
        print(f"\nCargando métricas desde: {args.load_cache}")
        metrics = load_json(args.load_cache)
    else:
        points = load_grid(args.csv)
        if args.max_points:
            points = points[:args.max_points]
            print(f"  (limitado a {len(points)} puntos)")

        print(f"\n[1/2] Consultando Meteoblue ({len(points)} pts, {len(points)//CHUNK_SIZE+1} requests)...")
        all_temps, all_precip, all_humidity = fetch_all_data(points, date_start, date_end)

        print("\n[2/2] Calculando métricas...")
        metrics = compute_metrics(points, all_temps, all_precip, all_humidity, date_start, args.threshold, args.gdd_base)

        save_json(metrics, metrics_path)
        print(f"\nMétricas guardadas: {metrics_path}")

    valid = [m for m in metrics if m["frost_hours"] is not None]
    if valid:
        top5 = sorted(valid, key=lambda x: x["frost_hours"], reverse=True)[:5]
        print(f"\nTop 5 por horas de helada:")
        for m in top5:
            print(f"  lat={m['lat']:>7.1f}  lon={m['lon']:>8.1f}  -> {m['frost_hours']} h  Tmin={m['min_temp']} C  P={m.get('precip_total','N/A')} mm")

    return metrics_path


if __name__ == "__main__":
    main()
