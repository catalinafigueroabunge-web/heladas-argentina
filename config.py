"""
Configuration: API credentials, locations, date range, and thresholds.
"""

# --- API settings ---
METEOBLUE_TOKEN = "synGrImykTlHjR74Y3"
METEOBLUE_URL = "https://my.meteoblue.com/dataset/query"

# --- Frost threshold ---
FROST_THRESHOLD = 0.0  # °C

# --- Default date range ---
# ERA5T data has ~5-day lag from today (2026-07-02 → safe end: 2026-06-27)
DATE_START = "2026-05-01T+00:00"
DATE_END = "2026-06-27T+00:00"

# --- Max locations per API request (Meteoblue recommends ≤50) ---
CHUNK_SIZE = 20

# --- Locations: name, lat, lon, altitude (m) ---
# GeoJSON coordinates order is [lon, lat, alt]
LOCATIONS = [
    {"name": "Pergamino",      "lat": -33.89, "lon": -60.57, "alt": 67},
    {"name": "Junín",          "lat": -34.59, "lon": -60.95, "alt": 81},
    {"name": "Rosario",        "lat": -32.95, "lon": -60.65, "alt": 25},
    {"name": "Córdoba",        "lat": -31.42, "lon": -64.18, "alt": 433},
    {"name": "Marcos Juárez",  "lat": -32.70, "lon": -62.10, "alt": 122},
    {"name": "Venado Tuerto",  "lat": -33.75, "lon": -61.97, "alt": 110},
    {"name": "Rafaela",        "lat": -31.25, "lon": -61.49, "alt": 95},
    {"name": "Paraná",         "lat": -31.73, "lon": -60.52, "alt": 78},
    {"name": "Balcarce",       "lat": -37.85, "lon": -58.26, "alt": 130},
    {"name": "Bahía Blanca",   "lat": -38.72, "lon": -62.27, "alt": 20},
    {"name": "Santa Rosa",     "lat": -36.62, "lon": -64.29, "alt": 210},
    {"name": "Río Cuarto",     "lat": -33.13, "lon": -64.35, "alt": 421},
    {"name": "Tucumán",        "lat": -26.82, "lon": -65.22, "alt": 475},
    {"name": "Salta",          "lat": -24.79, "lon": -65.41, "alt": 1187},
    {"name": "Manfredi",       "lat": -31.85, "lon": -63.75, "alt": 303},
    {"name": "Tres Arroyos",   "lat": -38.38, "lon": -60.28, "alt": 116},
    {"name": "Tandil",         "lat": -37.32, "lon": -59.13, "alt": 189},
    {"name": "General Pico",   "lat": -35.66, "lon": -63.76, "alt": 315},
    {"name": "Laboulaye",      "lat": -34.13, "lon": -63.39, "alt": 221},
    {"name": "San Luis",       "lat": -33.30, "lon": -66.34, "alt": 716},
]

# --- SSL verification (set False in corporate networks with SSL inspection) ---
VERIFY_SSL = False

# --- Argentina provinces GeoJSON sources (tried in order, first success wins) ---
ARGENTINA_GEOJSON_URLS = [
    # Official Argentine IGN
    "https://infra.datos.gob.ar/catalog/modernizacion/dataset/7/distribution/7.1/download/provincias.geojson",
    # GitHub fallback 1
    "https://raw.githubusercontent.com/argob/geo-argentina/master/data/provincias.geojson",
    # GitHub fallback 2
    "https://raw.githubusercontent.com/mattdzugan/Argentina-GeoJSON/master/argentina.geojson",
]
