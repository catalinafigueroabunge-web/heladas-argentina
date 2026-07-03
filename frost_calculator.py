"""
Parse Meteoblue API responses and calculate accumulated frost hours per location.
"""

from typing import Optional


# Candidate variable names Meteoblue may use for 2m temperature (code 11)
_TEMP_KEY_CANDIDATES = [
    "temperature_air_2m_celsius",
    "temperature_air_2m",
    "temperature_2m_celsius",
    "temperature_2m",
    "temperature",
    "t2m",
    "air_temperature",
    "11_2 m above gnd",
    "11_2m above gnd",
    "2 m above gnd",
]


def _find_temp_array(data_dict: dict) -> Optional[list]:
    """Search for the temperature array inside a location data dict."""
    for key in _TEMP_KEY_CANDIDATES:
        if key in data_dict:
            val = data_dict[key]
            if isinstance(val, (list, tuple)) and val:
                return list(val)

    # Fallback: any key containing 'temp' or matching code 11
    for key, val in data_dict.items():
        k_lower = key.lower()
        if ("temp" in k_lower or "11" in key) and isinstance(val, (list, tuple)):
            return list(val)

    return None


def _parse_raw_list(raw_list: list, chunk_locs: list) -> list:
    """
    Parse the Meteoblue dataset/query JSON-array response format:
      raw_list[0]["codes"][0]["dataPerTimeInterval"][interval_idx]["data"][loc_idx]
      = list of hourly temperature values for that location
    """
    if not raw_list:
        return [
            {"name": l["name"], "lat": l["lat"], "lon": l["lon"],
             "temps": None, "error": "API returned empty array"}
            for l in chunk_locs
        ]

    try:
        item = raw_list[0]
        codes = item.get("codes", [])
        if not codes:
            raise ValueError("No 'codes' in response")

        # Find temperature code (code 11 / variable Temperature)
        temp_code = None
        for c in codes:
            var = str(c.get("variable", "")).lower()
            if "temp" in var or c.get("code") == 11:
                temp_code = c
                break
        if temp_code is None:
            temp_code = codes[0]

        data_per_interval = temp_code.get("dataPerTimeInterval", [])
        if not data_per_interval:
            raise ValueError("No 'dataPerTimeInterval' in code")

        # Merge data across all requested time intervals
        merged: dict[int, list] = {}
        for interval in data_per_interval:
            per_loc = interval.get("data", [])
            for loc_idx, loc_temps in enumerate(per_loc):
                if loc_idx not in merged:
                    merged[loc_idx] = []
                merged[loc_idx].extend(loc_temps)

        results = []
        for i, loc in enumerate(chunk_locs):
            temps = merged.get(i)
            results.append({
                "name": loc["name"],
                "lat": loc["lat"],
                "lon": loc["lon"],
                "temps": temps,
                "error": None if temps is not None else f"Sin datos para índice {i}",
            })
        return results

    except Exception as exc:
        return [
            {"name": l["name"], "lat": l["lat"], "lon": l["lon"],
             "temps": None, "error": f"Error parseando respuesta: {exc}"}
            for l in chunk_locs
        ]


def _parse_chunk(response: dict) -> list:
    """
    Parse one API response chunk and return a list of per-location dicts:
      { name, lat, lon, temps: [float|None, ...] }

    Handles three response shapes Meteoblue may return:
      Shape A: data_1h is a dict keyed by location name
               e.g. data_1h["Pergamino"]["temperature"] = [...]
      Shape B: data_1h is a list of per-location dicts
               e.g. data_1h[0]["temperature"] = [...]
      Shape C: data_1h is a flat dict with one variable array per location
               (rare; fallback)
    """
    chunk_locs = response.get("_chunk_locations", [])

    if "_error" in response:
        return [
            {
                "name": loc["name"],
                "lat": loc["lat"],
                "lon": loc["lon"],
                "temps": None,
                "error": response["_error"],
            }
            for loc in chunk_locs
        ]

    # Handle wrapped list response from client
    raw_list = response.get("_raw_list")
    if raw_list is not None:
        return _parse_raw_list(raw_list, chunk_locs)

    data_1h = response.get("data_1h")
    if data_1h is None:
        return [
            {
                "name": loc["name"],
                "lat": loc["lat"],
                "lon": loc["lon"],
                "temps": None,
                "error": "data_1h ausente en respuesta",
            }
            for loc in chunk_locs
        ]

    results = []

    # ── Shape A: dict keyed by location name ──────────────────────────────
    if isinstance(data_1h, dict):
        # Collect the time array (shared by all locations in this chunk)
        time_arr = data_1h.get("time", [])

        for loc in chunk_locs:
            name = loc["name"]
            loc_data = data_1h.get(name)

            temps = None
            error = None

            if loc_data is None:
                # Try case-insensitive match
                for key in data_1h:
                    if key.lower() == name.lower():
                        loc_data = data_1h[key]
                        break

            if loc_data is not None:
                if isinstance(loc_data, dict):
                    temps = _find_temp_array(loc_data)
                elif isinstance(loc_data, (list, tuple)):
                    # The value itself is the temperature array
                    temps = list(loc_data)
                if temps is None:
                    error = f"No se encontró variable de temperatura para '{name}'"
            else:
                # Shape A might store temps as a flat array when only one location
                # or the data is indexed differently
                temps = _find_temp_array(data_1h)
                if temps is None:
                    error = f"Localidad '{name}' no encontrada en data_1h"

            results.append(
                {
                    "name": name,
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "temps": temps,
                    "error": error,
                }
            )
        return results

    # ── Shape B: list of per-location objects ─────────────────────────────
    if isinstance(data_1h, list):
        for idx, loc in enumerate(chunk_locs):
            temps = None
            error = None
            if idx < len(data_1h):
                loc_data = data_1h[idx]
                if isinstance(loc_data, dict):
                    temps = _find_temp_array(loc_data)
                if temps is None:
                    error = f"Variable de temperatura no encontrada (índice {idx})"
            else:
                error = f"Índice {idx} fuera de rango en data_1h"

            results.append(
                {
                    "name": loc["name"],
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "temps": temps,
                    "error": error,
                }
            )
        return results

    # Unknown shape
    return [
        {
            "name": loc["name"],
            "lat": loc["lat"],
            "lon": loc["lon"],
            "temps": None,
            "error": f"Formato data_1h desconocido: {type(data_1h).__name__}",
        }
        for loc in chunk_locs
    ]


def calculate_frost_hours(
    raw_responses: list, threshold: float = 0.0
) -> list:
    """
    Aggregate all chunks into a final list of per-location frost-hour summaries.

    Returns:
        list of dicts:
          name, lat, lon,
          frost_hours (int | None),
          total_hours (int),
          min_temp (float | None),
          error (str | None)
    """
    parsed = []
    for chunk_response in raw_responses:
        parsed.extend(_parse_chunk(chunk_response))

    final = []
    for item in parsed:
        if item["temps"] is None:
            final.append(
                {
                    "name": item["name"],
                    "lat": item["lat"],
                    "lon": item["lon"],
                    "frost_hours": None,
                    "total_hours": 0,
                    "min_temp": None,
                    "error": item.get("error", "Sin datos"),
                }
            )
            continue

        temps = item["temps"]
        # Filter out None / missing values
        valid_temps = [t for t in temps if t is not None]
        frost_count = sum(1 for t in valid_temps if t < threshold)
        min_temp = min(valid_temps) if valid_temps else None

        final.append(
            {
                "name": item["name"],
                "lat": item["lat"],
                "lon": item["lon"],
                "frost_hours": frost_count,
                "total_hours": len(valid_temps),
                "min_temp": round(min_temp, 1) if min_temp is not None else None,
                "error": item.get("error"),
            }
        )

    return final


def print_summary(results: list, threshold: float = 0.0) -> None:
    """Print a summary table to stdout."""
    print(f"\n{'Localidad':<20} {'Heladas (h)':>12} {'Total (h)':>10} {'T min (°C)':>11}")
    print("-" * 57)
    for r in sorted(results, key=lambda x: -(x["frost_hours"] or -1)):
        if r["frost_hours"] is None:
            print(f"  {r['name']:<18} {'SIN DATOS':>12}   {r.get('error','')}")
        else:
            tmin = f"{r['min_temp']:.1f}" if r["min_temp"] is not None else "N/A"
            print(
                f"  {r['name']:<18} {r['frost_hours']:>12} {r['total_hours']:>10} {tmin:>11}"
            )
