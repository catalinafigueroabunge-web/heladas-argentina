"""
Interactive folium map: Argentina frost hours visualization.
"""

import os
import json
import requests
import urllib3
import folium
import branca.colormap as cm
from config import ARGENTINA_GEOJSON_URLS, VERIFY_SSL
from argentina_boundary import ARGENTINA_GEOJSON as _EMBEDDED_GEOJSON

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


_GEOJSON_CACHE = os.path.join(
    os.path.dirname(__file__), "cache", "argentina_provinces.geojson"
)


def _load_geojson() -> dict | None:
    """Return Argentina provinces GeoJSON; download and cache if needed."""
    if os.path.exists(_GEOJSON_CACHE):
        with open(_GEOJSON_CACHE, "r", encoding="utf-8") as fh:
            return json.load(fh)

    print("  Descargando GeoJSON de provincias de Argentina...")
    for url in ARGENTINA_GEOJSON_URLS:
        try:
            resp = requests.get(url, timeout=30, verify=VERIFY_SSL)
            resp.raise_for_status()
            geojson = resp.json()
            os.makedirs(os.path.dirname(_GEOJSON_CACHE), exist_ok=True)
            with open(_GEOJSON_CACHE, "w", encoding="utf-8") as fh:
                json.dump(geojson, fh, ensure_ascii=False)
            print("  GeoJSON guardado en cache.")
            return geojson
        except Exception as exc:
            print(f"  Intentando siguiente URL... ({exc})")

    print("  Usando bordes de provincias embebidos (simplificados).")
    return _EMBEDDED_GEOJSON


def _color_scale(results: list) -> cm.LinearColormap:
    valid_hours = [r["frost_hours"] for r in results if r["frost_hours"] is not None]
    vmax = max(valid_hours) if valid_hours else 1
    vmin = 0
    return cm.LinearColormap(
        colors=["#deebf7", "#9ecae1", "#4292c6", "#2171b5", "#084594"],
        vmin=vmin,
        vmax=max(vmax, 1),
        caption="Horas de helada acumuladas (T < 0 °C)",
    )


def _radius(hours: int, max_hours: int) -> float:
    """Scale circle radius between 7 and 22 px based on frost hours."""
    if max_hours == 0:
        return 7
    return 7 + (hours / max_hours) * 15


def _fmt_date(raw: str) -> str:
    return raw.split("T")[0]


def generate_map(
    results: list,
    date_start: str,
    date_end: str,
    output_path: str,
) -> None:
    """Build and save the interactive HTML map."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Base map – centered on Argentina
    m = folium.Map(
        location=[-35.5, -64.0],
        zoom_start=5,
        tiles="CartoDB positron",
        prefer_canvas=True,
    )

    # Province boundaries
    geojson = _load_geojson()
    if geojson:
        folium.GeoJson(
            geojson,
            style_function=lambda _: {
                "fillColor": "transparent",
                "color": "#555555",
                "weight": 1.0,
                "fillOpacity": 0,
            },
            name="Provincias",
            tooltip=None,
        ).add_to(m)

    # Color scale
    colormap = _color_scale(results)
    colormap.add_to(m)

    valid_results = [r for r in results if r["frost_hours"] is not None]
    max_hours = max((r["frost_hours"] for r in valid_results), default=0)

    period = f"{_fmt_date(date_start)} al {_fmt_date(date_end)}"

    for r in results:
        lat, lon = r["lat"], r["lon"]
        name = r["name"]

        # ── No data marker ────────────────────────────────────────────────
        if r["frost_hours"] is None:
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color="#aaaaaa",
                weight=1,
                fill=True,
                fill_color="#cccccc",
                fill_opacity=0.6,
                tooltip=folium.Tooltip(
                    f"<b>{name}</b><br><i>Sin datos</i><br>"
                    f"<small>{r.get('error','')}</small>"
                ),
                popup=folium.Popup(
                    f"<div style='font-family:Arial;font-size:13px;min-width:160px'>"
                    f"<b>{name}</b><hr style='margin:4px 0'>"
                    f"<i>Sin datos disponibles</i><br>"
                    f"<small style='color:#888'>{r.get('error','')}</small><br>"
                    f"Período: {period}"
                    f"</div>",
                    max_width=280,
                ),
            ).add_to(m)
            continue

        # ── Frost data marker ─────────────────────────────────────────────
        hours = r["frost_hours"]
        total = r["total_hours"]
        tmin = r["min_temp"]
        color = colormap(hours)

        pct = f"{hours / total * 100:.1f}" if total > 0 else "N/A"
        tmin_str = f"{tmin:.1f} °C" if tmin is not None else "N/A"

        tooltip_html = (
            f"<div style='font-family:Arial;font-size:13px'>"
            f"<b>{name}</b><br>"
            f"Heladas: <b>{hours} h</b><br>"
            f"T mínima: {tmin_str}"
            f"</div>"
        )

        popup_html = (
            f"<div style='font-family:Arial;font-size:13px;min-width:190px'>"
            f"<b style='font-size:15px'>{name}</b>"
            f"<hr style='margin:5px 0'>"
            f"Horas de helada: <b>{hours} h</b><br>"
            f"Total horas con dato: {total} h<br>"
            f"Porcentaje: {pct} %<br>"
            f"T mínima registrada: {tmin_str}<br>"
            f"Lat: {lat:.2f} / Lon: {lon:.2f}"
            f"<hr style='margin:5px 0'>"
            f"<small style='color:#555'>Período: {period}</small>"
            f"</div>"
        )

        folium.CircleMarker(
            location=[lat, lon],
            radius=_radius(hours, max_hours),
            color="white",
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.88,
            tooltip=folium.Tooltip(tooltip_html),
            popup=folium.Popup(popup_html, max_width=290),
        ).add_to(m)

        # Label (small text below marker)
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=(
                    f"<div style='font-family:Arial;font-size:10px;"
                    f"font-weight:bold;color:#222;text-align:center;"
                    f"white-space:nowrap;margin-top:18px;margin-left:-40px;width:80px;"
                    f"text-shadow:0 0 3px white,0 0 3px white'>"
                    f"{name}<br>{hours} h</div>"
                ),
                icon_size=(80, 30),
                icon_anchor=(40, 0),
            ),
        ).add_to(m)

    # ── Title overlay ─────────────────────────────────────────────────────
    title_html = (
        "<div style='"
        "position:fixed;top:12px;left:50%;transform:translateX(-50%);"
        "z-index:9999;background:rgba(255,255,255,0.95);"
        "padding:10px 22px;border-radius:8px;"
        "border:2px solid #2171b5;"
        "font-family:Arial;font-size:16px;font-weight:bold;"
        "box-shadow:2px 2px 8px rgba(0,0,0,0.25);text-align:center'>"
        "Mapa de Heladas &mdash; Argentina<br>"
        f"<span style='font-size:12px;font-weight:normal;color:#555'>"
        f"Horas acumuladas con T &lt; 0 °C &nbsp;|&nbsp; {period}"
        f"</span></div>"
    )
    m.get_root().html.add_child(folium.Element(title_html))

    # ── "No data" legend entry ────────────────────────────────────────────
    no_data_html = (
        "<div style='"
        "position:fixed;bottom:30px;right:12px;z-index:9999;"
        "background:rgba(255,255,255,0.9);padding:6px 10px;"
        "border-radius:6px;border:1px solid #ccc;"
        "font-family:Arial;font-size:12px'>"
        "<span style='display:inline-block;width:14px;height:14px;"
        "background:#cccccc;border-radius:50%;margin-right:6px;"
        "vertical-align:middle'></span>Sin datos"
        "</div>"
    )
    m.get_root().html.add_child(folium.Element(no_data_html))

    m.save(output_path)
    print(f"  Mapa guardado en: {output_path}")
