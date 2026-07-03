"""
Meteoblue dataset/query API client.
Fetches hourly temperature data for a list of locations.
"""

import requests
import json
import os
import time
import urllib3
from config import METEOBLUE_TOKEN, METEOBLUE_URL, CHUNK_SIZE, VERIFY_SSL

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _build_payload(locations: list, date_start: str, date_end: str) -> dict:
    """Build the POST body for the Meteoblue dataset/query endpoint."""
    # GeoJSON coordinates: [longitude, latitude, altitude]
    coordinates = [[loc["lon"], loc["lat"], loc["alt"]] for loc in locations]
    names = [loc["name"] for loc in locations]

    return {
        "units": {
            "temperature": "C",
            "velocity": "km/h",
            "length": "metric",
            "energy": "watts",
        },
        "geometry": {
            "type": "MultiPoint",
            "coordinates": coordinates,
            "locationNames": names,
        },
        "format": "json",
        "timeIntervals": [f"{date_start}/{date_end}"],
        "timeIntervalsAlignment": "none",
        "queries": [
            {
                "domain": "ERA5T",
                "gapFillDomain": "ERA5",
                "timeResolution": "hourly",
                "codes": [{"code": 11, "level": "2 m above gnd"}],
            }
        ],
    }


def _do_request(payload: dict, debug: bool = False) -> dict:
    """Execute a single POST request to Meteoblue and return JSON."""
    headers = {"Content-Type": "application/json"}
    # Meteoblue dataset/query accepts the key as a URL query param
    url = f"{METEOBLUE_URL}?apikey={METEOBLUE_TOKEN}"

    if debug:
        print("\n[DEBUG] Request payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    resp = requests.post(url, json=payload, headers=headers, timeout=120, verify=VERIFY_SSL)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Meteoblue API error {resp.status_code}: {resp.text[:500]}"
        )

    data = resp.json()

    # Normalize: if API returned a JSON array, wrap it
    if isinstance(data, list):
        if debug:
            print(f"\n[DEBUG] API returned JSON array with {len(data)} items")
            if data:
                item0 = data[0]
                if isinstance(item0, dict):
                    all_keys = list(item0.keys())
                    print(f"[DEBUG] Item[0] ALL keys ({len(all_keys)}): {all_keys}")
                    for k in all_keys:
                        v = item0[k]
                        if isinstance(v, list):
                            inner = v[0] if v else None
                            print(f"[DEBUG]   {k}: list[{len(v)}], first item type={type(inner).__name__}")
                            if isinstance(inner, dict):
                                print(f"[DEBUG]     inner keys: {list(inner.keys())}")
                                for ik in list(inner.keys())[:5]:
                                    iv = inner[ik]
                                    print(f"[DEBUG]       {ik}: {str(iv)[:150]}")
                        else:
                            print(f"[DEBUG]   {k}: {str(v)[:150]}")
                else:
                    print(f"[DEBUG] Item[0] type: {type(item0).__name__}, value: {str(item0)[:120]}")
        return {"_raw_list": data}

    if debug:
        print("\n[DEBUG] Response top-level keys:", list(data.keys()))
        if "data_1h" in data:
            d1h = data["data_1h"]
            if isinstance(d1h, dict):
                print("[DEBUG] data_1h keys:", list(d1h.keys())[:10])
            elif isinstance(d1h, list):
                print(f"[DEBUG] data_1h is list of {len(d1h)} items")
                if d1h:
                    print("[DEBUG] First item keys:", list(d1h[0].keys())[:10])

    return data


def fetch_all_temperatures(
    locations: list, date_start: str, date_end: str, debug: bool = False
) -> list:
    """
    Fetch hourly temperatures for all locations, chunking if needed.

    Returns a list of raw API response dicts, one per chunk.
    Each dict includes the names list so the caller knows which
    locations belong to that chunk.
    """
    chunks = [
        locations[i : i + CHUNK_SIZE] for i in range(0, len(locations), CHUNK_SIZE)
    ]

    results = []
    for idx, chunk in enumerate(chunks):
        print(
            f"  Consultando chunk {idx + 1}/{len(chunks)}: "
            f"{[loc['name'] for loc in chunk]}"
        )
        payload = _build_payload(chunk, date_start, date_end)
        try:
            response = _do_request(payload, debug=debug)
            # Meteoblue may return a JSON array; wrap it for consistent handling
            if isinstance(response, list):
                if debug:
                    print(f"  [DEBUG] API returned list of {len(response)} items")
                    if response and isinstance(response[0], dict):
                        print(f"  [DEBUG] First item keys: {list(response[0].keys())[:15]}")
                response = {"_raw_list": response}
            response["_chunk_locations"] = chunk  # attach for downstream parsing
            results.append(response)
        except Exception as exc:
            print(f"  [ERROR] Chunk {idx + 1} falló: {exc}")
            # Return partial results with error markers
            for loc in chunk:
                results.append(
                    {"_error": str(exc), "_chunk_locations": [loc]}
                )
        if idx < len(chunks) - 1:
            time.sleep(1)  # polite delay between requests

    return results


def save_raw_response(responses: list, path: str) -> None:
    """Persist raw API responses for debugging / re-processing."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(responses, fh, ensure_ascii=False, indent=2)
    print(f"  Respuesta raw guardada en: {path}")


def load_raw_response(path: str) -> list:
    """Load previously saved raw API responses."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
