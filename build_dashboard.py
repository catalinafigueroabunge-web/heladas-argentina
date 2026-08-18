"""
build_dashboard.py — Genera el HTML del dashboard multi-capa con date picker dinámico.

Uso:
  uv run python build_dashboard.py
  uv run python build_dashboard.py data/metrics_YYYYMMDD_HHMM.json --open
"""
import argparse, csv, json, os, sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))

# ── Leaflet.Sync inlined (evita dependencia de CDN en redes corporativas) ──────
_LEAFLET_SYNC_JS = """/*
 * Extends L.Map to synchronize the interaction on one map to one or more other maps.
 */
(function () {
    var NO_ANIMATION = {
        animate: false,
        reset: true,
        disableViewprereset: true
    };

    L.Sync = function () {};
    L.Sync.offsetHelper = function (ratioRef, ratioTarget) {
        var or = L.Util.isArray(ratioRef) ? ratioRef : [0.5, 0.5];
        var ot = L.Util.isArray(ratioTarget) ? ratioTarget : [0.5, 0.5];
        return function (center, zoom, refMap, targetMap) {
            var rs = refMap.getSize();
            var ts = targetMap.getSize();
            var pt = refMap.project(center, zoom)
                           .subtract([(0.5 - or[0]) * rs.x, (0.5 - or[1]) * rs.y])
                           .add([(0.5 - ot[0]) * ts.x, (0.5 - ot[1]) * ts.y]);
            return refMap.unproject(pt, zoom);
        };
    };

    L.Map.include({
        sync: function (map, options) {
            this._initSync();
            options = L.extend({
                noInitialSync: false,
                syncCursor: false,
                syncCursorMarkerOptions: {
                    radius: 10,
                    fillOpacity: 0.3,
                    color: '#da291c',
                    fillColor: '#fff'
                },
                offsetFn: function (center, zoom, refMap, targetMap) {
                    return center;
                }
            }, options);

            if (this._syncMaps.indexOf(map) === -1) {
                this._syncMaps.push(map);
                this._syncOffsetFns[L.Util.stamp(map)] = options.offsetFn;
            }

            if (!options.noInitialSync) {
                map.setView(
                    options.offsetFn(this.getCenter(), this.getZoom(), this, map),
                    this.getZoom(), NO_ANIMATION);
            }
            if (options.syncCursor) {
                if (typeof map.cursor === 'undefined') {
                    map.cursor = L.circleMarker([0, 0], options.syncCursorMarkerOptions).addTo(map);
                }
                this._cursors.push(map.cursor);
                this.on('mousemove', this._cursorSyncMove, this);
                this.on('mouseout', this._cursorSyncOut, this);
            }

            this.on('resize zoomend', this._selfSetView);
            this.on('moveend', this._syncOnMoveend);
            this.on('dragend', this._syncOnDragend);
            return this;
        },

        unsync: function (map) {
            var self = this;
            if (this._cursors) {
                this._cursors.forEach(function (cursor, indx, _cursors) {
                    if (cursor === map.cursor) { _cursors.splice(indx, 1); }
                });
            }
            if (map.cursor) { map.cursor.setLatLng([0, 0]); }
            if (this._syncMaps) {
                this._syncMaps.forEach(function (synced, id) {
                    if (map === synced) {
                        delete self._syncOffsetFns[L.Util.stamp(map)];
                        self._syncMaps.splice(id, 1);
                    }
                });
            }
            if (!this._syncMaps || this._syncMaps.length == 0) {
                this.off('resize zoomend', this._selfSetView);
                this.off('moveend', this._syncOnMoveend);
                this.off('dragend', this._syncOnDragend);
            }
            return this;
        },

        isSynced: function (otherMap) {
            var has = (this.hasOwnProperty('_syncMaps') && Object.keys(this._syncMaps).length > 0);
            if (has && otherMap) {
                has = false;
                this._syncMaps.forEach(function (synced) {
                    if (otherMap == synced) { has = true; }
                });
            }
            return has;
        },

        _cursorSyncMove: function (e) {
            this._cursors.forEach(function (cursor) { cursor.setLatLng(e.latlng); });
        },
        _cursorSyncOut: function (e) {
            this._cursors.forEach(function (cursor) { cursor.setLatLng([0, 0]); });
        },
        _selfSetView: function (e) {
            this.setView(this.getCenter(), this.getZoom(), NO_ANIMATION);
        },
        _syncOnMoveend: function (e) {
            if (this._syncDragend) {
                this._syncDragend = false;
                this._selfSetView(e);
                this._syncMaps.forEach(function (toSync) { toSync.fire('moveend'); });
            }
        },
        _syncOnDragend: function (e) { this._syncDragend = true; },

        _initSync: function () {
            if (this._syncMaps) { return; }
            var originalMap = this;
            this._syncMaps = [];
            this._cursors = [];
            this._syncOffsetFns = {};

            L.extend(originalMap, {
                setView: function (center, zoom, options, sync) {
                    function sandwich (obj, fn) {
                        var viewpreresets = [];
                        var doit = options && options.disableViewprereset && obj && obj._events;
                        if (doit) {
                            viewpreresets = obj._events.viewprereset;
                            obj._events.viewprereset = [];
                        }
                        var ret = fn(obj);
                        if (doit) { obj._events.viewprereset = viewpreresets; }
                        return ret;
                    }
                    var ret = sandwich(this, function (obj) {
                        return L.Map.prototype.setView.call(obj, center, zoom, options);
                    });
                    if (!sync) {
                        originalMap._syncMaps.forEach(function (toSync) {
                            sandwich(toSync, function (obj) {
                                return toSync.setView(
                                    originalMap._syncOffsetFns[L.Util.stamp(toSync)](center, zoom, originalMap, toSync),
                                    zoom, options, true);
                            });
                        });
                    }
                    return ret;
                },
                panBy: function (offset, options, sync) {
                    if (!sync) {
                        originalMap._syncMaps.forEach(function (toSync) {
                            toSync.panBy(offset, options, true);
                        });
                    }
                    return L.Map.prototype.panBy.call(this, offset, options);
                },
                _onResize: function (event, sync) {
                    if (!sync) {
                        originalMap._syncMaps.forEach(function (toSync) {
                            toSync._onResize(event, true);
                        });
                    }
                    return L.Map.prototype._onResize.call(this, event);
                },
                _stop: function (sync) {
                    L.Map.prototype._stop.call(this);
                    if (!sync) {
                        originalMap._syncMaps.forEach(function (toSync) { toSync._stop(true); });
                    }
                }
            });

            originalMap.dragging._draggable._updatePosition = function () {
                L.Draggable.prototype._updatePosition.call(this);
                var self = this;
                originalMap._syncMaps.forEach(function (toSync) {
                    L.DomUtil.setPosition(toSync.dragging._draggable._element, self._newPos);
                    toSync.eachLayer(function (layer) {
                        if (layer._google !== undefined) {
                            var offsetFn = originalMap._syncOffsetFns[L.Util.stamp(toSync)];
                            var center = offsetFn(originalMap.getCenter(), originalMap.getZoom(), originalMap, toSync);
                            layer._google.setCenter(center);
                        }
                    });
                    toSync.fire('move');
                });
            };
        }
    });
})();"""


def load_metrics(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_grid_coords() -> list:
    """Carga las coordenadas de la grilla para el fetch JS dinámico."""
    csv_path = os.path.join(_HERE, "heladas.csv")
    pts = []
    if not os.path.exists(csv_path):
        return pts
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pts.append([round(float(row["lat"]), 4), round(float(row["lon"]), 4)])
            except (ValueError, KeyError):
                continue
    return pts


def build_html(
    metrics: list,
    date_start: str,
    date_end: str,
    output_path: str,
    api_key: str = "",
    grid_coords: list | None = None,
) -> None:
    data_json        = json.dumps(metrics, ensure_ascii=False, separators=(",", ":"))
    grid_coords_json = json.dumps(grid_coords or [], separators=(",", ":"))
    period      = f"{date_start.split('T')[0]} al {date_end.split('T')[0]}"
    d_from_init = date_start.split("T")[0]
    d_to_init   = date_end.split("T")[0]
    n_valid     = sum(1 for m in metrics if m.get("frost_hours") is not None)
    n_total     = len(metrics)
    leaflet_sync_js = _LEAFLET_SYNC_JS
    # ── Regiones Nidera ────────────────────────────────────────────────────────
    import csv as _csv
    regions_data: dict = {}
    regions_csv_path = os.path.join(_HERE, "heladas_regions.csv")
    if os.path.exists(regions_csv_path):
        with open(regions_csv_path, "r", encoding="utf-8-sig") as _rf:
            for _row in _csv.DictReader(_rf):
                try:
                    _lat = round(float(_row["lat"]), 4)
                    _lon = round(float(_row["lon"]), 4)
                    _reg = _row["region"].strip()
                    if _reg:
                        regions_data[f"{_lat:.4f},{_lon:.4f}"] = _reg
                except (ValueError, KeyError):
                    pass
    regions_json       = json.dumps(regions_data, separators=(",", ":"))
    unique_regions     = sorted(set(regions_data.values()))
    region_options_html = "\n".join(
        f'  <option value="{r}">{r}</option>' for r in unique_regions
    )

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Dashboard Agrometeorológico — Argentina</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>{leaflet_sync_js}</script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;display:flex;flex-direction:column;height:100vh;background:#f0f4f8}}
/* ── header ── */
#hdr{{background:linear-gradient(90deg,#0d3b6e,#1a6fa8);color:#fff;padding:9px 16px;display:flex;align-items:center;justify-content:space-between;box-shadow:0 2px 5px rgba(0,0,0,.35)}}
#hdr h1{{font-size:16px;font-weight:700}}
#hdr .meta{{font-size:11px;opacity:.85;text-align:right}}
/* ── layer bar ── */
#layer-bar{{background:#fff;border-bottom:2px solid #d0dae8;padding:6px 12px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}}
.lbtn{{padding:5px 11px;border:2px solid #2171b5;background:#fff;color:#2171b5;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600;transition:all .16s;white-space:nowrap}}
.lbtn:hover{{background:#e8f2fb}}
.lbtn.active{{background:#2171b5;color:#fff}}
#gdd-crop{{padding:3px 6px;border:1px solid #b0bec5;border-radius:4px;font-size:11px;color:#444;background:#fff;cursor:pointer;height:26px}}
#export-btn{{padding:5px 11px;background:#2ca02c;color:#fff;border:none;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600}}
#export-btn:hover{{background:#1e7e1e}}
#compare-btn{{margin-left:auto;padding:5px 11px;background:#6c3483;color:#fff;border:none;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600;white-space:nowrap}}
#compare-btn:hover{{background:#7d3c98}}
#compare-btn.active{{background:#4a235a;outline:2px solid #9b59b6}}
/* ── date bar ── */
#date-bar{{background:#f7f9fc;border-bottom:1px solid #dde3ec;padding:6px 14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
#date-bar label{{font-size:12px;color:#444;font-weight:600}}
#campaign-sel{{padding:4px 8px;border:1px solid #b0bec5;border-radius:4px;font-size:13px;color:#222;background:#fff;cursor:pointer;max-width:280px}}
#date-bar input[type=date]{{padding:4px 8px;border:1px solid #b0bec5;border-radius:4px;font-size:13px;color:#222;background:#fff}}
#date-bar input[type=date]:focus{{outline:none;border-color:#2171b5;box-shadow:0 0 0 2px rgba(33,113,181,.2)}}
#update-btn{{padding:5px 14px;background:#2171b5;color:#fff;border:none;border-radius:5px;cursor:pointer;font-size:13px;font-weight:700}}
#update-btn:hover{{background:#1558a0}}
#update-btn:disabled{{background:#90bcd8;cursor:not-allowed}}
/* ── filter bar ── */
#filter-bar{{background:#f0f4f8;border-bottom:1px solid #dde3ec;padding:5px 14px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;flex-shrink:0}}
#filter-bar label{{font-size:12px;color:#444;cursor:pointer;display:flex;align-items:center;gap:4px}}
.filter-sep{{color:#ccc;user-select:none}}
/* ── progress bar ── */
#prog-wrap{{display:none;background:#fff;border-bottom:1px solid #dde3ec;padding:5px 14px;flex-shrink:0}}
#prog-track{{height:7px;background:#dde3ec;border-radius:4px;overflow:hidden;margin-bottom:4px}}
#prog-fill{{height:100%;width:0%;background:linear-gradient(90deg,#2171b5,#56aaf4);border-radius:4px;transition:width .3s ease}}
#prog-text{{font-size:11px;color:#555;display:flex;justify-content:space-between}}
/* ── error banner ── */
#err-banner{{display:none;background:#fff3cd;border:1px solid #ffc107;border-radius:5px;padding:7px 14px;margin:6px 14px;font-size:12px;color:#856404;flex-shrink:0}}
/* ── map wrap — flex column ── */
#map-wrap{{flex:1;display:flex;flex-direction:column;overflow:hidden;min-height:0}}
/* ── split selector bar ── */
#split-bar{{display:none;background:#eef2f7;border-bottom:1px solid #dde3ec;padding:6px 12px;flex-shrink:0;flex-direction:row;gap:8px}}
.split-half{{flex:1;display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:#444;flex-wrap:wrap}}
.split-half select{{padding:3px 7px;border:1px solid #b0bec5;border-radius:4px;font-size:12px;color:#222;background:#fff;cursor:pointer}}
.split-half span{{white-space:nowrap}}
/* ── maps row ── */
#maps-row{{flex:1;display:flex;flex-direction:row;min-height:0}}
/* ── individual panels ── */
#panel-a{{flex:1;position:relative;display:flex;flex-direction:column;min-height:0}}
#panel-b{{flex:1;position:relative;display:none;flex-direction:column;min-height:0;border-left:2px solid #dde3ec}}
#map,#map-b{{flex:1;min-height:0}}
/* ── legends ── */
.map-legend{{position:absolute;bottom:28px;right:10px;z-index:1000;background:rgba(255,255,255,.97);padding:10px 14px;border-radius:8px;border:1px solid #ccc;font-size:12px;min-width:170px;box-shadow:2px 2px 8px rgba(0,0,0,.18)}}
.map-legend h3{{font-size:13px;color:#0d3b6e;margin-bottom:6px;border-bottom:1px solid #ddd;padding-bottom:4px}}
.legend-bar{{height:13px;border-radius:3px;margin-bottom:4px}}
.legend-labels{{display:flex;justify-content:space-between;font-size:11px;color:#555}}
.legend-nodata{{display:none}}
.nd-dot{{width:12px;height:12px;border-radius:50%;background:#ccc;border:1px solid #aaa;flex-shrink:0}}
/* ── location search ── */
#search-box{{position:absolute;top:10px;left:10px;z-index:900;width:230px;background:rgba(255,255,255,.97);border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.2);border:1px solid #ccc}}
#search-input-wrap{{display:flex;align-items:center;padding:5px 8px;gap:4px}}
#search-input{{flex:1;border:none;outline:none;font-size:12px;color:#333;background:transparent;min-width:0}}
#search-input::placeholder{{color:#aaa}}
#search-clear{{cursor:pointer;color:#aaa;font-size:13px;flex-shrink:0;line-height:1;background:none;border:none;padding:0}}
#search-clear:hover{{color:#666}}
#search-results{{max-height:180px;overflow-y:auto;border-top:1px solid #eee}}
.srch-item{{padding:5px 8px;font-size:11px;cursor:pointer;color:#333;border-bottom:1px solid #f4f4f4;line-height:1.35}}
.srch-item:hover{{background:#f0f6fc}}
.srch-item b{{color:#0d3b6e}}
.srch-msg{{padding:5px 8px;font-size:11px;color:#888;font-style:italic}}
/* ── threshold toggle ── */
.thresh-grp{{display:flex;border:1.5px solid #2171b5;border-radius:6px;overflow:hidden;background:#fff}}
.thresh-opt{{padding:4px 11px;font-size:11px;font-weight:600;color:#2171b5;cursor:pointer;border:none;background:transparent;white-space:nowrap;transition:all .15s}}
.thresh-opt:hover{{background:#e8f2fb}}
.thresh-opt.active{{background:#2171b5;color:#fff}}
</style>
</head>
<body>

<!-- ── header ── -->
<div id="hdr">
  <h1>&#127973; Dashboard Agrometeorológico — Argentina</h1>
  <div class="meta" id="hdr-meta">{n_valid}/{n_total} puntos &nbsp;|&nbsp; <span id="hdr-period">{period}</span></div>
</div>

<!-- ── layer buttons ── -->
<div id="layer-bar">
  <button class="lbtn active" onclick="switchLayer('frost',this)">1&#xFE0F;&#x20E3; Horas de helada</button>
  <button class="lbtn"        onclick="switchLayer('dates',this)">2&#xFE0F;&#x20E3; Primera/última helada</button>
  <button class="lbtn" id="gdd-btn" onclick="switchLayer('gdd',this)">3&#xFE0F;&#x20E3; Grados-día</button>
  <select id="gdd-crop" onchange="onGddCropChange()">
    <option value="10">Maíz (base 10°C)</option>
    <option value="6">Girasol (base 6°C)</option>
  </select>
  <button class="lbtn"        onclick="switchLayer('amp',this)">4&#xFE0F;&#x20E3; Amplitud térmica</button>
  <button class="lbtn"        onclick="switchLayer('streak',this)">5&#xFE0F;&#x20E3; Racha sin heladas</button>
  <button class="lbtn"        onclick="switchLayer('wbal',this)">6&#xFE0F;&#x20E3; Balance hídrico</button>
  <button class="lbtn"        onclick="switchLayer('precip',this)">7&#xFE0F;&#x20E3; Lluvia acumulada</button>
  <button class="lbtn"        onclick="switchLayer('drystreak',this)">8&#xFE0F;&#x20E3; Racha seca</button>
  <button class="lbtn"        onclick="switchLayer('humidity',this)">9&#xFE0F;&#x20E3; Humedad relativa</button>
  <button class="lbtn"        onclick="switchLayer('soil',this)">10&#xFE0F;&#x20E3; Humedad del suelo</button>
  <button id="export-btn"     onclick="exportCSV()">&#11123; CSV</button>
  <button id="compare-btn"    onclick="toggleCompare()">Comparar &#8660;</button>
</div>

<!-- ── date picker ── -->
<div id="date-bar">
  <label style="font-weight:700">Mapa A:</label>
  <select id="campaign-sel" onchange="onCampaignChange()"></select>
  <label style="margin-left:4px">Desde</label>
  <input type="date" id="d-from" value="{d_from_init}">
  <label>Hasta</label>
  <input type="date" id="d-to"   value="{d_to_init}">
  <button id="update-btn" onclick="doUpdate()">&#8635; Cargar</button>
</div>

<!-- ── filter bar ── -->
<div id="filter-bar">
  <span id="region-filter-wrap">
    <span class="filter-sep">|</span>
    <label style="font-weight:600">Región:</label>
    <select id="region-sel" multiple size="3" onchange="onRegionChange()"
      style="padding:2px 4px;border:1px solid #b0bec5;border-radius:4px;font-size:12px;color:#222;background:#fff;cursor:pointer;height:58px;min-width:140px;max-width:200px">
{region_options_html}
    </select>
    <button id="region-clear-btn" onclick="clearRegions()"
      style="padding:3px 9px;border:1px solid #b0bec5;border-radius:4px;font-size:11px;font-weight:600;color:#2171b5;background:#fff;cursor:pointer;white-space:nowrap">Todas</button>
    <span id="region-count" style="font-size:10px;color:#888;white-space:nowrap"></span>
  </span>
  <span class="filter-sep">|</span>
  <label style="font-weight:600;font-size:12px;color:#444">Umbral helada:</label>
  <div class="thresh-grp">
    <button class="thresh-opt active" id="thresh-0" onclick="onThresholdChange(0)">T &lt; 0°C</button>
    <button class="thresh-opt" id="thresh-5" onclick="onThresholdChange(5)">T &lt; 5°C</button>
  </div>
</div>

<!-- ── progress ── -->
<div id="prog-wrap">
  <div id="prog-track"><div id="prog-fill"></div></div>
  <div id="prog-text"><span id="prog-label">Consultando API...</span><span id="prog-pct">0%</span></div>
</div>
<div id="err-banner"></div>

<!-- ── map ── -->
<div id="map-wrap">
  <div id="split-bar">
    <div class="split-half" style="flex-direction:column;align-items:flex-start;gap:4px;border-right:1px solid #dde3ec;padding-right:10px">
      <div style="display:flex;align-items:center;gap:6px">
        <span>Mapa A:</span>
        <select id="camp-sel-a" onchange="onSplitSelChange('a')"></select>
      </div>
      <div id="split-a-custom" style="display:none;align-items:center;gap:5px;flex-wrap:wrap">
        <label style="font-size:11px;color:#444;font-weight:600">Desde</label>
        <input type="date" id="split-a-from" style="padding:2px 5px;border:1px solid #b0bec5;border-radius:4px;font-size:11px">
        <label style="font-size:11px;color:#444;font-weight:600">Hasta</label>
        <input type="date" id="split-a-to" style="padding:2px 5px;border:1px solid #b0bec5;border-radius:4px;font-size:11px">
        <button onclick="fetchForMap('a')" style="padding:3px 10px;background:#2171b5;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;font-weight:600;white-space:nowrap">Cargar</button>
      </div>
    </div>
    <div class="split-half" style="flex-direction:column;align-items:flex-start;gap:4px">
      <div style="display:flex;align-items:center;gap:6px">
        <span>Mapa B:</span>
        <select id="camp-sel-b" onchange="onSplitSelChange('b')"></select>
      </div>
      <div id="split-b-custom" style="display:none;align-items:center;gap:5px;flex-wrap:wrap">
        <label style="font-size:11px;color:#444;font-weight:600">Desde</label>
        <input type="date" id="split-b-from" style="padding:2px 5px;border:1px solid #b0bec5;border-radius:4px;font-size:11px">
        <label style="font-size:11px;color:#444;font-weight:600">Hasta</label>
        <input type="date" id="split-b-to" style="padding:2px 5px;border:1px solid #b0bec5;border-radius:4px;font-size:11px">
        <button onclick="fetchForMap('b')" style="padding:3px 10px;background:#2171b5;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;font-weight:600;white-space:nowrap">Cargar</button>
      </div>
    </div>
  </div>
  <div id="maps-row">
    <div id="panel-a">
      <div id="map"></div>
      <div id="search-box">
        <div id="search-input-wrap">
          <span style="color:#aaa;font-size:13px">&#128269;</span>
          <input type="text" id="search-input" placeholder="Buscar localidad..." oninput="onSearchInput()" autocomplete="off">
          <button id="search-clear" onclick="clearSearch()" style="display:none">&#10005;</button>
        </div>
        <div id="search-results"></div>
      </div>
      <div id="legend-a" class="map-legend">
        <h3 id="lg-a-title">Horas de helada</h3>
        <div id="legend-a-bar" class="legend-bar"></div>
        <div class="legend-labels"><span id="lg-a-min">0</span><span id="lg-a-max"></span></div>
        <div id="lg-a-steps" style="display:none"></div>
        <div class="legend-nodata"><div class="nd-dot"></div> Sin datos</div>
      </div>
    </div>
    <div id="panel-b">
      <div id="map-b"></div>
      <div id="legend-b" class="map-legend">
        <h3 id="lg-b-title">&#8593; Seleccioná una campaña</h3>
        <div id="legend-b-bar" class="legend-bar"></div>
        <div class="legend-labels"><span id="lg-b-min"></span><span id="lg-b-max"></span></div>
        <div id="lg-b-steps" style="display:none"></div>
        <div class="legend-nodata"><div class="nd-dot"></div> Sin datos</div>
      </div>
    </div>
  </div>
</div>

<script>
// ── Constants ─────────────────────────────────────────────────────────────────
const API_KEY     = "{api_key}";
const API_URL     = "https://my.meteoblue.com/dataset/query";
const CHUNK_SIZE  = 15;
const GRID_POINTS = {grid_coords_json};
const ERA5T_LAG       = 5;
const MAX_MONTHS      = 13;
const OPENMETEO_URL   = "https://historical-forecast-api.open-meteo.com/v1/forecast";
const SOIL_CHUNK_SIZE = 20;
const POINT_REGIONS   = {regions_json};

// ── State ─────────────────────────────────────────────────────────────────────
let currentData   = {data_json};
let currentFrom   = "{d_from_init}";
let currentTo     = "{d_to_init}";
let currentLayer  = 'frost';
let layerGroup    = null;
let isFetching    = false;
let compareMode   = false;
let mapB          = null;
let activeRegions   = new Set();
let regionSelOrder  = [];
let frostThreshold  = 0;
let layerGroupB    = null;
let currentDataB  = null;

// ── Map init ──────────────────────────────────────────────────────────────────
const map = L.map('map', {{center:[-32,-63],zoom:6}});
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{
  attribution:'&copy; OpenStreetMap &copy; CartoDB',subdomains:'abcd',maxZoom:19
}}).addTo(map);

// ── Color utils ───────────────────────────────────────────────────────────────
const lerp = (t,a,b) => a+(b-a)*Math.max(0,Math.min(1,t));
const blueGrad   = t=>`rgb(${{Math.round(lerp(t,222,8))}},${{Math.round(lerp(t,235,69))}},${{Math.round(lerp(t,247,148))}})`;
const orangeGrad = t=>`rgb(${{Math.round(lerp(t,255,161))}},${{Math.round(lerp(t,255,0))}},${{Math.round(lerp(t,204,0))}})`;
const purpleGrad = t=>`rgb(${{Math.round(lerp(t,237,63))}},${{Math.round(lerp(t,248,0))}},${{Math.round(lerp(t,251,125))}})`;
const greenGrad  = t=>`rgb(${{Math.round(lerp(t,247,0))}},${{Math.round(lerp(t,252,109))}},${{Math.round(lerp(t,245,44))}})`;
// Divergente (rojo=déficit → amarillo → azul=exceso)
function wbalGrad(t){{
  if(t<0.5){{const u=t*2;return `rgb(${{Math.round(lerp(u,215,254))}},${{Math.round(lerp(u,25,224))}},${{Math.round(lerp(u,28,144))}})`;}}
  const u=(t-0.5)*2;return `rgb(${{Math.round(lerp(u,254,69))}},${{Math.round(lerp(u,224,117))}},${{Math.round(lerp(u,144,180))}})`;
}}
// Lluvia: casi blanco → azul oscuro
const rainGrad = t=>`rgb(${{Math.round(lerp(t,247,8))}},${{Math.round(lerp(t,251,81))}},${{Math.round(lerp(t,255,156))}})`;
// Racha seca: verde → naranja → rojo
const dryGrad  = t=>t<0.5
  ? `rgb(${{Math.round(lerp(t*2,44,255))}},${{Math.round(lerp(t*2,162,165))}},${{Math.round(lerp(t*2,95,0))}})`
  : `rgb(${{Math.round(lerp((t-0.5)*2,255,180))}},${{Math.round(lerp((t-0.5)*2,165,0))}},${{Math.round(lerp((t-0.5)*2,0,0))}})`;

function getPointRegion(d){{
  return POINT_REGIONS[d.lat.toFixed(4)+','+d.lon.toFixed(4)]||'';
}}
function isRegionDimmed(d){{
  if(!activeRegions.size) return false;
  return !activeRegions.has(getPointRegion(d));
}}
function fitToRegion(regions, mapRef, data){{
  if(!mapRef||!data) return;
  if(!regions.size){{mapRef.setView([-32,-63],6);return;}}
  const pts=data.filter(d=>regions.has(getPointRegion(d)));
  if(!pts.length) return;
  mapRef.fitBounds(L.latLngBounds(pts.map(d=>[d.lat,d.lon])).pad(0.05));
}}
function updateRegionCount(){{
  const el=document.getElementById('region-count');
  if(el) el.textContent=activeRegions.size?activeRegions.size+' sel.':'';
}}
function onRegionChange(){{
  const sel=document.getElementById('region-sel');
  const now=new Set([...sel.selectedOptions].map(o=>o.value));
  const added=[...now].filter(v=>!activeRegions.has(v));
  const removed=[...activeRegions].filter(v=>!now.has(v));
  regionSelOrder=regionSelOrder.filter(v=>!removed.includes(v));
  regionSelOrder.push(...added);
  if(regionSelOrder.length>3){{
    const excess=regionSelOrder.splice(0,regionSelOrder.length-3);
    [...sel.options].forEach(o=>{{if(excess.includes(o.value)) o.selected=false;}});
  }}
  activeRegions=new Set(regionSelOrder);
  updateRegionCount();
  renderLayer(currentLayer,'a');
  fitToRegion(activeRegions,map,currentData);
  if(compareMode&&mapB){{
    if(currentDataB) renderLayer(currentLayer,'b');
    fitToRegion(activeRegions,mapB,currentDataB||currentData);
  }}
}}
function clearRegions(){{
  activeRegions=new Set();regionSelOrder=[];
  [...document.getElementById('region-sel').options].forEach(o=>o.selected=false);
  updateRegionCount();
  renderLayer(currentLayer,'a');
  fitToRegion(activeRegions,map,currentData);
  if(compareMode&&mapB){{
    if(currentDataB) renderLayer(currentLayer,'b');
    fitToRegion(activeRegions,mapB,currentDataB||currentData);
  }}
}}

function activeData(data){{
  let r=data;
  if(activeRegions.size) r=r.filter(d=>activeRegions.has(getPointRegion(d)));
  return r;
}}

// ── Map layer helpers ─────────────────────────────────────────────────────────
function getRangeFrom(data, key){{
  const vals=data.filter(d=>d[key]!=null).map(d=>d[key]);
  return vals.length ? {{min:Math.min(...vals),max:Math.max(...vals)}} : {{min:0,max:1}};
}}

function clearLayersFor(target){{
  if(target==='b'){{
    if(layerGroupB&&mapB){{mapB.removeLayer(layerGroupB);layerGroupB=null;}}
  }}else{{
    if(layerGroup){{map.removeLayer(layerGroup);layerGroup=null;}}
  }}
}}

// ── Frost continuous gradient (piecewise linear between 5 reference points) ──
const FROST_BP = [
  {{thr:  0, r:214, g: 39, b: 40}},  // #d62728 rojo    0 h
  {{thr:  5, r:255, g:127, b: 14}},  // #ff7f0e naranja 5 h
  {{thr: 40, r:247, g:216, b: 63}},  // #f7d83f amarillo 40 h
  {{thr: 60, r: 44, g:160, b: 44}},  // #2ca02c verde   60 h
  {{thr: 97, r: 33, g:113, b:181}},  // #2171b5 azul    97+ h
];
const FROST_BP_5 = FROST_BP;
function makeFrostColorFn(bp){{
  return function(hours){{
    if(hours<=0) return `rgb(${{bp[0].r}},${{bp[0].g}},${{bp[0].b}})`;
    if(hours>=bp[bp.length-1].thr){{const c=bp[bp.length-1];return `rgb(${{c.r}},${{c.g}},${{c.b}})`;}}
    for(let i=0;i<bp.length-1;i++){{
      const lo=bp[i],hi=bp[i+1];
      if(hours>=lo.thr&&hours<hi.thr){{
        const t=(hours-lo.thr)/(hi.thr-lo.thr);
        return `rgb(${{Math.round(lo.r+(hi.r-lo.r)*t)}},${{Math.round(lo.g+(hi.g-lo.g)*t)}},${{Math.round(lo.b+(hi.b-lo.b)*t)}})`;
      }}
    }}
    return `rgb(33,113,181)`;
  }};
}}
const frostColor  = makeFrostColorFn(FROST_BP);
const frostColor5 = frostColor;
const HUMIDITY_BP = [
  {{thr:  0, r:214, g: 39, b: 40}},  // rojo    0%
  {{thr: 20, r:255, g:127, b: 14}},  // naranja 20%
  {{thr: 40, r:247, g:216, b: 63}},  // amarillo 40%
  {{thr: 60, r: 44, g:160, b: 44}},  // verde   60%
  {{thr: 80, r: 33, g:113, b:181}},  // azul    80%
];
const humidColor = makeFrostColorFn(HUMIDITY_BP);
const SOIL_BP = [
  {{thr:0.00, r:214, g: 39, b: 40}},  // rojo       muy seco
  {{thr:0.10, r:247, g:216, b: 63}},  // amarillo   seco
  {{thr:0.20, r: 44, g:160, b: 44}},  // verde      húmedo adecuado
  {{thr:0.30, r: 33, g:113, b:181}},  // azul       muy húmedo
  {{thr:0.40, r: 78, g:  0, b:128}},  // violeta    saturado
];
const soilColor = makeFrostColorFn(SOIL_BP);
function buildStepMarkers(data, key, stepFn, tipFn){{
  const grp=L.layerGroup();
  data.forEach(d=>{{
    if(isRegionDimmed(d)){{
      L.circleMarker([d.lat,d.lon],{{radius:8,color:'#ccc',weight:.3,fillColor:'#ddd',fillOpacity:.15}}).addTo(grp);
      return;
    }}
    if(d[key]==null){{
      L.circleMarker([d.lat,d.lon],{{radius:8,color:'#aaa',weight:.4,fillColor:'#ddd',fillOpacity:.35}})
       .bindTooltip(`<b>${{d.lat.toFixed(2)}} / ${{d.lon.toFixed(2)}}</b><br>Sin datos`,{{sticky:true}})
       .addTo(grp);
      return;
    }}
    L.circleMarker([d.lat,d.lon],{{
      radius:8,color:'white',weight:.7,
      fillColor:stepFn(d[key]),fillOpacity:.88
    }}).bindTooltip(tipFn(d),{{sticky:true}}).addTo(grp);
  }});
  return grp;
}}
function setStepLegend(target, bp, title, unit){{
  const p=(target==='b')?'b':'a';
  document.getElementById('legend-'+p+'-bar').style.display='none';
  const labRow=document.querySelector('#legend-'+p+' .legend-labels');
  if(labRow) labRow.style.display='none';
  const stepsEl=document.getElementById('lg-'+p+'-steps');
  stepsEl.style.display='block';
  const maxThr=bp[bp.length-1].thr;
  const grad='linear-gradient(to right,'+bp.map((c,i)=>`rgb(${{c.r}},${{c.g}},${{c.b}}) ${{Math.round(i/(bp.length-1)*100)}}%`).join(',')+')';
  const ticks=bp.map((c,i)=>{{
    const pos=Math.round(i/(bp.length-1)*100);
    const lbl=(c.thr===maxThr?maxThr+'+':c.thr)+unit;
    return `<span style="position:absolute;left:${{pos}}%;transform:translateX(${{pos===0?'0':pos===100?'-100%':'-50%'}});">${{lbl}}</span>`;
  }}).join('');
  stepsEl.innerHTML=
    `<div style="height:12px;border-radius:3px;background:${{grad}};margin-bottom:18px"></div>`+
    `<div style="position:relative;height:14px;font-size:10px;color:#555">${{ticks}}</div>`;
  document.getElementById('lg-'+p+'-title').textContent=title;
}}
function setFrostStepLegend(target){{
  const bp=frostThreshold===5?FROST_BP_5:FROST_BP;
  const title=frostThreshold===5?'Horas de helada (T<5°C)':'Horas de helada (T<0°C)';
  setStepLegend(target,bp,title,' h');
}}
function resetLegendFormat(target){{
  const p=(target==='b')?'b':'a';
  document.getElementById('legend-'+p+'-bar').style.display='';
  const labRow=document.querySelector('#legend-'+p+' .legend-labels');
  if(labRow) labRow.style.display='';
  const stepsEl=document.getElementById('lg-'+p+'-steps');
  if(stepsEl) stepsEl.style.display='none';
}}

function buildMarkersFrom(data, key, colorFn, tipFn){{
  const vis=activeData(data);
  const r=getRangeFrom(vis,key); const span=r.max-r.min||1;
  const grp=L.layerGroup();
  data.forEach(d=>{{
    if(isRegionDimmed(d)){{
      L.circleMarker([d.lat,d.lon],{{radius:8,color:'#ccc',weight:.3,fillColor:'#ddd',fillOpacity:.15}}).addTo(grp);
      return;
    }}
    if(d[key]==null){{
      L.circleMarker([d.lat,d.lon],{{radius:8,color:'#aaa',weight:.4,fillColor:'#ddd',fillOpacity:.35}})
       .bindTooltip(`<b>${{d.lat.toFixed(2)}} / ${{d.lon.toFixed(2)}}</b><br>Sin datos`,{{sticky:true}})
       .addTo(grp);
      return;
    }}
    const t=Math.max(0,Math.min(1,(d[key]-r.min)/span));
    L.circleMarker([d.lat,d.lon],{{
      radius:8,color:'white',weight:.7,
      fillColor:colorFn(t),fillOpacity:.88
    }}).bindTooltip(tipFn(d),{{sticky:true}}).addTo(grp);
  }});
  return grp;
}}

function buildDivergingMarkers(data, key, tipFn){{
  const vis=activeData(data);
  const visVals=vis.filter(d=>d[key]!=null).map(d=>d[key]);
  const absMax=visVals.length
    ? Math.max(Math.abs(Math.min(...visVals)),Math.abs(Math.max(...visVals)))||1
    : 1;
  const grp=L.layerGroup();
  data.forEach(d=>{{
    if(isRegionDimmed(d)){{
      L.circleMarker([d.lat,d.lon],{{radius:8,color:'#ccc',weight:.3,fillColor:'#ddd',fillOpacity:.15}}).addTo(grp);
      return;
    }}
    if(d[key]==null){{
      L.circleMarker([d.lat,d.lon],{{radius:8,color:'#aaa',weight:.4,fillColor:'#ddd',fillOpacity:.35}})
       .bindTooltip(`<b>${{d.lat.toFixed(2)}} / ${{d.lon.toFixed(2)}}</b><br>Sin datos`,{{sticky:true}})
       .addTo(grp);
      return;
    }}
    const t=Math.max(0,Math.min(1,(d[key]/absMax+1)/2));
    L.circleMarker([d.lat,d.lon],{{
      radius:8,color:'white',weight:.7,
      fillColor:wbalGrad(t),fillOpacity:.88
    }}).bindTooltip(tipFn(d),{{sticky:true}}).addTo(grp);
  }});
  return grp;
}}

function setLegend(title,gradient,minL,maxL,target){{
  const p=(target==='b')?'b':'a';
  document.getElementById('lg-'+p+'-title').textContent=title;
  document.getElementById('legend-'+p+'-bar').style.background=gradient;
  document.getElementById('lg-'+p+'-min').textContent=minL;
  document.getElementById('lg-'+p+'-max').textContent=maxL;
}}

function renderLayer(name, target){{
  target=target||'a';
  const data  =(target==='b')?currentDataB:currentData;
  const mapRef=(target==='b')?mapB:map;
  if(!data||!mapRef) return;
  clearLayersFor(target);
  resetLegendFormat(target);
  let grp;
  switch(name){{
    case 'frost':{{
      const fField=frostThreshold===5?'frost_hours_5':'frost_hours';
      const fColorFn=frostThreshold===5?frostColor5:frostColor;
      grp=buildStepMarkers(data,fField,fColorFn,
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `Heladas: <b>${{d[fField]??'N/A'}} h</b><br>T min: ${{d.min_temp??'N/A'}} °C`);
      setFrostStepLegend(target);
      break;
    }}
    case 'dates':{{
      grp=L.layerGroup();
      data.forEach(d=>{{
        if(isRegionDimmed(d)){{
          L.circleMarker([d.lat,d.lon],{{radius:8,color:'#ccc',weight:.3,fillColor:'#ddd',fillOpacity:.15}}).addTo(grp);
          return;
        }}
        if(!d.first_frost&&d.frost_hours!==0){{
          L.circleMarker([d.lat,d.lon],{{radius:8,color:'#aaa',weight:.4,fillColor:'#ddd',fillOpacity:.35}}).addTo(grp);
          return;
        }}
        const noFrost=d.frost_hours===0;
        L.circleMarker([d.lat,d.lon],{{
          radius:8,
          color:noFrost?'#e88':'#084594',weight:1,
          fillColor:noFrost?'#fdd':'#4292c6',fillOpacity:.85
        }}).bindTooltip(
          noFrost?`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>Sin heladas`
                 :`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
                  `Primera: <b>${{d.first_frost}}</b><br>Última: <b>${{d.last_frost}}</b><br>`+
                  `Total: ${{d.frost_hours}} h`,
          {{sticky:true}}).addTo(grp);
      }});
      setLegend('Primera / última helada',
        'linear-gradient(to right,#fdd,#c9e8f5,#4292c6,#084594)',
        'Sin heladas','Con heladas',target);
      break;
    }}
    case 'gdd':{{
      const base=parseInt(document.getElementById('gdd-crop')?.value||'10');
      const field=base===6?'degree_days_6':'degree_days';
      const cropName=base===6?'Girasol (base 6°C)':'Maíz (base 10°C)';
      grp=buildMarkersFrom(data,field,orangeGrad,
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `GDD ${{cropName}}: <b>${{d[field]!=null?d[field]:'N/A'}} GD</b>`);
      setLegend('Grados-día — '+cropName,
        'linear-gradient(to right,#ffffcc,#ffae00,#cc3300)',
        '0',getRangeFrom(data,field).max.toFixed(0)+' GD',target);
      break;
    }}
    case 'amp':{{
      grp=buildMarkersFrom(data,'avg_amplitude',purpleGrad,
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `Amplitud media: <b>${{d.avg_amplitude}}°C</b>`);
      setLegend('Amplitud térmica diaria promedio',
        'linear-gradient(to right,#f7f4ff,#9e6db8,#3f007d)',
        '0°C',getRangeFrom(data,'avg_amplitude').max.toFixed(1)+'°C',target);
      break;
    }}
    case 'streak':{{
      grp=buildMarkersFrom(data,'frost_free_streak',greenGrad,
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `Racha sin heladas: <b>${{d.frost_free_streak}} días</b>`);
      setLegend('Racha máxima sin heladas',
        'linear-gradient(to right,#f7fcf5,#74c476,#006d2c)',
        '0 d',getRangeFrom(data,'frost_free_streak').max+' d',target);
      break;
    }}
    case 'wbal':{{
      grp=buildDivergingMarkers(data,'water_balance',
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `Balance hídrico: <b>${{d.water_balance!=null?d.water_balance:'N/A'}} mm</b><br>`+
           `Precip: ${{d.precip_total??'N/A'}} mm`);
      const wbR=getRangeFrom(data,'water_balance');
      const absM=Math.round(Math.max(Math.abs(wbR.min),Math.abs(wbR.max)));
      setLegend('Balance hídrico (Precip − ETP)',
        'linear-gradient(to right,#d73027,#fee090,#4575b4)',
        '-'+absM+' mm','+'+absM+' mm',target);
      break;
    }}
    case 'precip':{{
      grp=buildMarkersFrom(data,'precip_total',rainGrad,
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `Lluvia acumulada: <b>${{d.precip_total!=null?d.precip_total:'N/A'}} mm</b>`);
      setLegend('Lluvia acumulada (mm)',
        'linear-gradient(to right,#f7fbff,#6baed6,#08306b)',
        '0 mm',getRangeFrom(data,'precip_total').max.toFixed(0)+' mm',target);
      break;
    }}
    case 'drystreak':{{
      grp=buildMarkersFrom(data,'dry_streak',dryGrad,
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `Racha seca: <b>${{d.dry_streak!=null?d.dry_streak:'N/A'}} días</b>`);
      setLegend('Racha seca al cierre del período',
        'linear-gradient(to right,#2ca02c,#ff7f0e,#d62728)',
        '0 d',getRangeFrom(data,'dry_streak').max+' d',target);
      break;
    }}
    case 'humidity':{{
      grp=buildStepMarkers(data,'avg_humidity',humidColor,
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `HR media: <b>${{d.avg_humidity!=null?d.avg_humidity+'%':'N/A'}}</b>`);
      setStepLegend(target,HUMIDITY_BP,'Humedad relativa media (%)','%');
      break;
    }}
    case 'soil':{{
      grp=buildStepMarkers(data,'avg_soil_moisture',soilColor,
        d=>`<b>${{d.lat.toFixed(2)}}° / ${{d.lon.toFixed(2)}}°</b><br>`+
           `Humedad suelo 0–5cm: <b>${{d.avg_soil_moisture!=null?d.avg_soil_moisture+' m³/m³':'N/A'}}</b>`);
      setStepLegend(target,SOIL_BP,'Humedad del suelo (0–5 cm)','');
      break;
    }}
  }}
  if(grp){{
    if(target==='b'){{layerGroupB=grp;grp.addTo(mapB);}}
    else{{layerGroup=grp;grp.addTo(map);}}
  }}
}}

function switchLayer(name, btn){{
  document.querySelectorAll('.lbtn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  currentLayer=name;
  renderLayer(name,'a');
  if(compareMode&&mapB&&currentDataB) renderLayer(name,'b');
}}

function onGddCropChange(){{
  if(currentLayer==='gdd'){{
    renderLayer('gdd','a');
    if(compareMode&&mapB&&currentDataB) renderLayer('gdd','b');
  }}
}}

function onThresholdChange(val){{
  frostThreshold=val;
  document.getElementById('thresh-0').classList.toggle('active',val===0);
  document.getElementById('thresh-5').classList.toggle('active',val===5);
  if(currentLayer==='frost'){{
    renderLayer('frost','a');
    if(compareMode&&mapB&&currentDataB) renderLayer('frost','b');
  }}
}}

// ── Date validation ───────────────────────────────────────────────────────────
function showErr(msg){{
  const b=document.getElementById('err-banner');
  b.textContent=msg;b.style.display='block';
  setTimeout(()=>b.style.display='none',8000);
}}
function hideErr(){{document.getElementById('err-banner').style.display='none';}}

function maxDate(){{
  const d=new Date();d.setDate(d.getDate()-ERA5T_LAG);
  return d.toISOString().slice(0,10);
}}

function validateDates(from,to){{
  if(!from||!to)         {{showErr('Ingresá ambas fechas.');return false;}}
  if(from>=to)           {{showErr('La fecha Desde debe ser anterior a Hasta.');return false;}}
  const max=maxDate();
  if(to>max)             {{showErr('Hasta no puede ser posterior a '+max+' (ERA5T tiene 5 días de retraso).');return false;}}
  const days=(new Date(to)-new Date(from))/(1000*86400);
  if(days>MAX_MONTHS*31) {{showErr('El período máximo es 13 meses (403 días).');return false;}}
  hideErr();
  return true;
}}

// ── Campaign selector helpers ─────────────────────────────────────────────────
function campaignDates(label){{
  const year=parseInt(label);
  const from=year+'-01-01';
  const toRaw=year+'-12-31';
  const to=toRaw<=maxDate()?toRaw:maxDate();
  return [from,to];
}}

function buildCampaignOptions(includeAvg5, includeCustom, customAtEnd){{
  const maxD   =maxDate();
  const curYear=new Date().getFullYear();
  const opts   =[];
  if(includeCustom&&!customAtEnd) opts.push({{val:'custom',lbl:'Personalizado'}});
  if(includeAvg5)   opts.push({{val:'avg5',  lbl:'⊘ Promedio últimos 5 años'}});
  for(let y=curYear; y>=curYear-9; y--){{
    if((y+'-01-01')>maxD) continue;
    opts.push({{val:String(y),lbl:String(y)}});
  }}
  if(includeCustom&&customAtEnd) opts.push({{val:'custom',lbl:'Personalizado'}});
  return opts;
}}

function populateSel(selId, includeAvg5, includeCustom, customAtEnd){{
  const sel=document.getElementById(selId);
  if(!sel) return;
  sel.innerHTML='';
  buildCampaignOptions(includeAvg5||false,includeCustom||false,customAtEnd||false).forEach(o=>{{
    const opt=document.createElement('option');
    opt.value=o.val;opt.textContent=o.lbl;sel.appendChild(opt);
  }});
}}

function onCampaignChange(){{
  const val=document.getElementById('campaign-sel').value;
  if(val==='avg5'){{
    doUpdateAvg5();
  }}else if(val){{
    const [f,t]=campaignDates(val);
    document.getElementById('d-from').value=f;
    document.getElementById('d-to').value  =t;
    doUpdate();
  }}
}}

// ── Progress helpers ──────────────────────────────────────────────────────────
function showProgress(){{document.getElementById('prog-wrap').style.display='block';setProgress(0,'');}}
function hideProgress(){{document.getElementById('prog-wrap').style.display='none';}}
function setProgress(frac,label){{
  const pct=Math.round(frac*100);
  document.getElementById('prog-fill').style.width=pct+'%';
  document.getElementById('prog-pct').textContent=pct+'%';
  if(label) document.getElementById('prog-label').textContent=label;
}}

function updateHeader(data,from,to){{
  const nV=data.filter(m=>m.frost_hours!=null).length;
  const label=to?from+' al '+to:from;
  document.getElementById('hdr-meta').innerHTML=
    nV+'/'+data.length+' puntos &nbsp;|&nbsp; <span id="hdr-period">'+label+'</span>';
}}

// ── Meteoblue API fetch (single chunk — temperatura + precipitación) ──────────
async function fetchChunk(pts,dateFrom,dateTo){{
  const payload={{
    units:{{temperature:'C',velocity:'km/h',length:'metric',energy:'watts'}},
    geometry:{{
      type:'MultiPoint',
      coordinates:pts.map(([lat,lon])=>[lon,lat,0]),
      locationNames:pts.map((_,i)=>`p${{i}}`),
    }},
    format:'json',
    timeIntervals:[`${{dateFrom}}T+00:00/${{dateTo}}T+00:00`],
    timeIntervalsAlignment:'none',
    queries:[{{
      domain:'ERA5T',gapFillDomain:'ERA5',timeResolution:'hourly',
      codes:[
        {{code:11,level:'2 m above gnd'}},
        {{code:61,level:'sfc'}},
        {{code:52,level:'2 m above gnd'}},
      ],
    }}],
  }};
  const resp=await fetch(`${{API_URL}}?apikey=${{API_KEY}}`,{{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify(payload),
  }});
  if(!resp.ok) throw new Error(`HTTP ${{resp.status}}: ${{await resp.text().then(t=>t.slice(0,200))}}`);
  return resp.json();
}}

// ── Response parser ───────────────────────────────────────────────────────────
function extractCode(data,n,codeIdx){{
  if(!Array.isArray(data)||!data.length) return Array(n).fill(null);
  const codes=(data[0]?.codes||[]);
  if(codeIdx>=codes.length) return Array(n).fill(null);
  const merged={{}};
  for(const interval of codes[codeIdx].dataPerTimeInterval||[]){{
    for(let i=0;i<(interval.data||[]).length;i++){{
      merged[i]=(merged[i]||[]).concat(interval.data[i]);
    }}
  }}
  return Array.from({{length:n}},(_,i)=>merged[i]||null);
}}
function extractTemps(data,n)  {{return extractCode(data,n,0);}}
function extractPrecip(data,n) {{return extractCode(data,n,1);}}

// ── Open-Meteo soil moisture (segunda fuente — gratuita, sin API key) ─────────
async function fetchSoilChunk(pts,dateFrom,dateTo){{
  const lats=pts.map(([lat,])=>lat).join(',');
  const lons=pts.map(([,lon])=>lon).join(',');
  const url=OPENMETEO_URL
    +'?latitude='+lats+'&longitude='+lons
    +'&hourly=soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm'
    +'&models=icon_seamless&start_date='+dateFrom+'&end_date='+dateTo+'&timezone=UTC';
  for(let attempt=0;attempt<3;attempt++){{
    const resp=await fetch(url);
    if(resp.status===429){{
      await new Promise(r=>setTimeout(r,10000*(attempt+1)));
      continue;
    }}
    if(!resp.ok) throw new Error('Open-Meteo HTTP '+resp.status);
    return resp.json();
  }}
  throw new Error('Open-Meteo rate-limit tras 3 intentos');
}}
function extractSoilData(data,n){{
  const arr=Array.isArray(data)?data:[data];
  return Array.from({{length:n}},(_,i)=>{{
    const h=arr[i]?.hourly;
    if(!h) return [null,null,null];
    return [h.soil_moisture_0_to_1cm||null,h.soil_moisture_1_to_3cm||null,h.soil_moisture_3_to_9cm||null];
  }});
}}
function computeWeightedSoil(sm01,sm13,sm39){{
  if(!sm01||!sm13||!sm39) return null;
  const n=Math.min(sm01.length,sm13.length,sm39.length);
  let sum=0,count=0;
  for(let i=0;i<n;i++){{
    const v1=sm01[i],v2=sm13[i],v3=sm39[i];
    if(v1!=null&&v2!=null&&v3!=null){{sum+=(v1*1+v2*2+v3*2)/5;count++;}}
  }}
  return count?Math.round(sum/count*1000)/1000:null;
}}
async function fetchAllSoilMoisture(pts,dateFrom,dateTo,onProgress){{
  const chunks=[];
  for(let i=0;i<pts.length;i+=SOIL_CHUNK_SIZE) chunks.push(pts.slice(i,i+SOIL_CHUNK_SIZE));
  const soilMap={{}};
  for(let ci=0;ci<chunks.length;ci++){{
    if(onProgress) onProgress(ci,chunks.length);
    const chunk=chunks[ci];
    try{{
      const raw=await fetchSoilChunk(chunk,dateFrom,dateTo);
      const soilData=extractSoilData(raw,chunk.length);
      chunk.forEach(([lat,lon],j)=>{{
        const [s01,s13,s39]=soilData[j];
        soilMap[lat.toFixed(4)+','+lon.toFixed(4)]=computeWeightedSoil(s01,s13,s39);
      }});
    }}catch(e){{
      console.warn('Soil chunk '+ci+' error:',e.message);
      chunk.forEach(([lat,lon])=>soilMap[lat.toFixed(4)+','+lon.toFixed(4)]=null);
    }}
    if(ci<chunks.length-1) await new Promise(r=>setTimeout(r,6000));
  }}
  return soilMap;
}}

// ── Hargreaves-Samani ETP (mm/día) ───────────────────────────────────────────
function calcDailyETP(lat_deg,tmax,tmin,tmean,doy){{
  const lat =lat_deg*Math.PI/180;
  const dr  =1+0.033*Math.cos(2*Math.PI/365*doy);
  const delt=0.409*Math.sin(2*Math.PI/365*doy-1.39);
  const cosW=-Math.tan(lat)*Math.tan(delt);
  const ws  =cosW>=1?0:cosW<=-1?Math.PI:Math.acos(cosW);
  const Ra  =(24*60/Math.PI)*0.082*dr*(ws*Math.sin(lat)*Math.sin(delt)+Math.cos(lat)*Math.cos(delt)*Math.sin(ws));
  return Math.max(0,0.0023*Ra*(tmean+17.8)*Math.sqrt(Math.max(0,tmax-tmin)));
}}

// ── Metrics computation ───────────────────────────────────────────────────────
function idxToDate(idx,dateFrom){{
  try{{
    const d=new Date(dateFrom+'T00:00:00Z');
    d.setUTCHours(d.getUTCHours()+idx);
    return (d.getUTCDate()+'').padStart(2,'0')+'/'+(d.getUTCMonth()+1+'').padStart(2,'0');
  }}catch(e){{return null;}}
}}

function computeMetrics(pts,allTemps,allPrecip,allHumidity,dateFrom,gddBase=10){{
  return pts.map(([lat,lon],i)=>{{
    const base={{lat,lon}};
    const raw =allTemps[i];
    const nullMetrics={{...base,frost_hours:null,frost_hours_5:null,min_temp:null,degree_days:null,degree_days_6:null,
      avg_amplitude:null,first_frost:null,last_frost:null,frost_free_streak:null,
      precip_total:null,water_balance:null,dry_streak:null,avg_humidity:null}};
    if(!raw||!raw.length) return nullMetrics;
    const v=raw.filter(t=>t!=null);
    if(!v.length) return {{...base,frost_hours:0,frost_hours_5:0,min_temp:null,degree_days:null,degree_days_6:null,
      avg_amplitude:null,first_frost:null,last_frost:null,frost_free_streak:Math.floor(raw.length/24),
      precip_total:null,water_balance:null,dry_streak:null,avg_humidity:null}};

    // ── temperatura ────────────────────────────────────────────────────────────
    const frostH =v.filter(t=>t<0).length;
    const frostH5=v.filter(t=>t<5).length;
    const minT   =Math.min(...v);
    const gdd   =v.reduce((s,t)=>s+Math.max(0,t-gddBase),0)/24;
    const gdd6  =v.reduce((s,t)=>s+Math.max(0,t-6),0)/24;
    const amps=[];
    for(let j=0;j<v.length-23;j+=24){{
      const day=v.slice(j,j+24);
      if(day.length===24) amps.push(Math.max(...day)-Math.min(...day));
    }}
    const avgAmp=amps.length?amps.reduce((s,a)=>s+a,0)/amps.length:null;
    const frostIdxs=v.map((t,j)=>t<0?j:-1).filter(j=>j>=0);
    const firstFrost=frostIdxs.length?idxToDate(frostIdxs[0],dateFrom):null;
    const lastFrost =frostIdxs.length?idxToDate(frostIdxs[frostIdxs.length-1],dateFrom):null;
    let maxGap=0,cur=0;
    v.forEach(t=>{{if(t>=0){{cur++;maxGap=Math.max(maxGap,cur)}}else{{cur=0}}}});
    maxGap=Math.max(maxGap,cur);

    // ── hídrico (requiere precipitación) ──────────────────────────────────────
    let precipTotal=null, waterBalance=null, dryStreak=null;
    const rawP=allPrecip?allPrecip[i]:null;
    if(rawP&&rawP.length){{
      const numDays=Math.floor(Math.max(v.length,rawP.length)/24);
      const dailyPrecip=[],dailyTmax=[],dailyTmin=[],dailyTmean=[];
      for(let d=0;d<numDays;d++){{
        const tSlice=v.slice(d*24,d*24+24).filter(t=>t!=null);
        const pSlice=rawP.slice(d*24,d*24+24).map(p=>p!=null?p:0);
        dailyPrecip.push(pSlice.reduce((s,p)=>s+p,0));
        if(tSlice.length){{
          dailyTmax.push(Math.max(...tSlice));
          dailyTmin.push(Math.min(...tSlice));
          dailyTmean.push(tSlice.reduce((s,t)=>s+t,0)/tSlice.length);
        }}else{{dailyTmax.push(null);dailyTmin.push(null);dailyTmean.push(null);}}
      }}
      precipTotal=Math.round(dailyPrecip.reduce((s,p)=>s+p,0)*10)/10;
      const startD=new Date(dateFrom+'T00:00:00Z');
      let etpTotal=0;
      for(let d=0;d<numDays;d++){{
        if(dailyTmax[d]!=null&&dailyTmin[d]!=null&&dailyTmean[d]!=null){{
          const dd=new Date(startD);dd.setUTCDate(startD.getUTCDate()+d);
          const doy=Math.ceil((dd-new Date(dd.getUTCFullYear(),0,0))/86400000);
          etpTotal+=calcDailyETP(lat,dailyTmax[d],dailyTmin[d],dailyTmean[d],doy);
        }}
      }}
      waterBalance=Math.round((precipTotal-etpTotal)*10)/10;
      dryStreak=0;
      for(let d=dailyPrecip.length-1;d>=0;d--){{
        if(dailyPrecip[d]<1) dryStreak++;
        else break;
      }}
    }}

    // ── humedad relativa ───────────────────────────────────────────────────────
    let avgHumidity=null;
    const rawH=allHumidity?allHumidity[i]:null;
    if(rawH&&rawH.length){{
      const vh=rawH.filter(h=>h!=null);
      if(vh.length) avgHumidity=Math.round(vh.reduce((s,h)=>s+h,0)/vh.length*10)/10;
    }}

    return {{
      lat,lon,
      frost_hours:frostH,
      frost_hours_5:frostH5,
      min_temp:Math.round(minT*10)/10,
      degree_days:Math.round(gdd*10)/10,
      degree_days_6:Math.round(gdd6*10)/10,
      avg_amplitude:avgAmp!=null?Math.round(avgAmp*10)/10:null,
      first_frost:firstFrost,last_frost:lastFrost,
      frost_free_streak:Math.floor(maxGap/24),
      precip_total:precipTotal,
      water_balance:waterBalance,
      dry_streak:dryStreak,
      avg_humidity:avgHumidity,
    }};
  }});
}}

// ── Reusable full-campaign fetcher ────────────────────────────────────────────
async function fetchFullCampaign(from,to,onProgress){{
  const chunks=[];
  for(let i=0;i<GRID_POINTS.length;i+=CHUNK_SIZE)
    chunks.push(GRID_POINTS.slice(i,i+CHUNK_SIZE));
  let acc=[];
  for(let ci=0;ci<chunks.length;ci++){{
    if(onProgress) onProgress(ci,chunks.length);
    const chunk=chunks[ci];
    try{{
      const raw    =await fetchChunk(chunk,from,to);
      const temps  =extractCode(raw,chunk.length,0);
      const precip =extractCode(raw,chunk.length,1);
      const humid  =extractCode(raw,chunk.length,2);
      acc=acc.concat(computeMetrics(chunk,temps,precip,humid,from));
    }}catch(e){{
      if(e.message.includes('Failed to fetch')||e.message.includes('NetworkError'))
        throw new Error('CORS:'+from+':'+to);
      acc=acc.concat(chunk.map(([lat,lon])=>
        ({{lat,lon,frost_hours:null,min_temp:null,degree_days:null,degree_days_6:null,
           avg_amplitude:null,first_frost:null,last_frost:null,frost_free_streak:null,
           precip_total:null,water_balance:null,dry_streak:null,avg_humidity:null}})));
    }}
    if(ci<chunks.length-1) await new Promise(r=>setTimeout(r,300));
  }}
  return acc;
}}

// ── Date-string ↔ Julian helpers ──────────────────────────────────────────────
function ddmmToJulian(ddmm){{
  if(!ddmm) return null;
  const parts=ddmm.split('/');
  const dd=parseInt(parts[0]),mm=parseInt(parts[1]);
  const d=new Date(2023,mm-1,dd);
  return Math.floor((d-new Date(2023,0,1))/86400000)+1;
}}
function julianToDdmm(j){{
  if(j==null) return null;
  const d=new Date(2023,0,1);d.setDate(d.getDate()+Math.round(j)-1);
  return (d.getDate()+'').padStart(2,'0')+'/'+((''+( d.getMonth()+1)).padStart(2,'0'));
}}

// ── Dataset averaging ─────────────────────────────────────────────────────────
function averageDatasets(datasets){{
  if(!datasets.length) return [];
  const n=datasets[0].length;
  const NUM=['frost_hours','min_temp','degree_days','degree_days_6',
             'avg_amplitude','frost_free_streak','precip_total','water_balance','dry_streak',
             'avg_humidity','avg_soil_moisture'];
  const DAT=['first_frost','last_frost'];
  return Array.from({{length:n}},(_,i)=>{{
    const base={{lat:datasets[0][i].lat,lon:datasets[0][i].lon}};
    NUM.forEach(f=>{{
      const v=datasets.map(d=>d[i][f]).filter(x=>x!=null);
      base[f]=v.length?Math.round(v.reduce((s,x)=>s+x,0)/v.length*10)/10:null;
    }});
    DAT.forEach(f=>{{
      const js=datasets.map(d=>ddmmToJulian(d[i][f])).filter(j=>j!=null);
      base[f]=js.length?julianToDdmm(js.reduce((s,j)=>s+j,0)/js.length):null;
    }});
    return base;
  }});
}}

// ── Avg-5 orchestrator ────────────────────────────────────────────────────────
async function doUpdateAvg5(){{
  if(isFetching) return;
  const btn=document.getElementById('update-btn');
  isFetching=true;btn.disabled=true;
  showProgress();hideErr();clearLayersFor('a');

  const maxD=maxDate();
  const endYears=[];
  for(let ey=new Date().getFullYear(); ey>=2010&&endYears.length<5; ey--){{
    if((ey+'-12-31')<=maxD) endYears.push(ey);
  }}
  if(endYears.length<5){{
    showErr('No hay 5 años completos disponibles (ERA5T requiere 5 días de retraso).');
    isFetching=false;btn.disabled=false;hideProgress();return;
  }}

  const datasets=[];
  for(let ci=0;ci<endYears.length;ci++){{
    const ey=endYears[ci];
    const from=ey+'-01-01',to=ey+'-12-31';
    try{{
      const data=await fetchFullCampaign(from,to,(chunkIdx,total)=>{{
        const frac=(ci+chunkIdx/total)/endYears.length;
        setProgress(frac,`Año ${{ci+1}}/${{endYears.length}}: ${{ey}} — chunk ${{chunkIdx+1}}/${{total}}`);
      }});
      datasets.push(data);
    }}catch(e){{
      if(e.message.startsWith('CORS')){{
        hideProgress();
        showErr('CORS bloqueado. Usá fetch_data.py para cargar datos offline.');
        isFetching=false;btn.disabled=false;return;
      }}
      console.error('Error campaña '+ey,e.message);
    }}
  }}

  if(!datasets.length){{
    showErr('No se obtuvieron datos de ninguna campaña.');
    isFetching=false;btn.disabled=false;hideProgress();return;
  }}

  currentData=averageDatasets(datasets);
  currentFrom=endYears[endYears.length-1]+'-01-01';
  currentTo  =endYears[0]+'-12-31';
  setProgress(1,'Promedio calculado');
  renderLayer(currentLayer,'a');
  if(compareMode&&mapB&&currentDataB) renderLayer(currentLayer,'b');
  const label=`Promedio 5 años (${{endYears[endYears.length-1]}}–${{endYears[0]}})`;
  updateHeader(currentData,label,'');
  setTimeout(hideProgress,2000);
  isFetching=false;btn.disabled=false;
}}

// ── Main update (single campaign, progressive render) ─────────────────────────
async function doUpdate(){{
  const sel   =document.getElementById('campaign-sel');
  const selVal=sel?sel.value:'custom';
  if(selVal==='avg5'){{await doUpdateAvg5();return;}}

  const from=document.getElementById('d-from').value;
  const to  =document.getElementById('d-to').value;
  if(!validateDates(from,to)) return;
  if(isFetching) return;

  const btn=document.getElementById('update-btn');
  isFetching=true;btn.disabled=true;

  const chunks=[];
  for(let i=0;i<GRID_POINTS.length;i+=CHUNK_SIZE)
    chunks.push(GRID_POINTS.slice(i,i+CHUNK_SIZE));
  const total=chunks.length;
  showProgress();hideErr();clearLayersFor('a');
  let accumulated=[];

  try{{
    for(let ci=0;ci<total;ci++){{
      setProgress(ci/total,`Chunk ${{ci+1}}/${{total}} (${{GRID_POINTS.length}} pts)...`);
      const chunk=chunks[ci];
      let raw;
      try{{
        raw=await fetchChunk(chunk,from,to);
      }}catch(e){{
        if(e.message.includes('Failed to fetch')||e.message.includes('NetworkError')){{
          hideProgress();
          showErr('CORS bloqueado por red corporativa. Corrí: uv run python fetch_data.py --start '+from+' --end '+to+' && uv run python build_dashboard.py --open');
          isFetching=false;btn.disabled=false;return;
        }}
        console.warn('Chunk '+ci+' error:',e.message);
        accumulated=accumulated.concat(chunk.map(([lat,lon])=>
          ({{lat,lon,frost_hours:null,min_temp:null,degree_days:null,degree_days_6:null,
             avg_amplitude:null,first_frost:null,last_frost:null,frost_free_streak:null,
             precip_total:null,water_balance:null,dry_streak:null,avg_humidity:null}})));
        continue;
      }}
      const temps =extractCode(raw,chunk.length,0);
      const precip=extractCode(raw,chunk.length,1);
      const humid =extractCode(raw,chunk.length,2);
      accumulated=accumulated.concat(computeMetrics(chunk,temps,precip,humid,from));
      if((ci+1)%10===0||ci===total-1){{
        currentData=[...accumulated];renderLayer(currentLayer,'a');
      }}
      if(ci<total-1) await new Promise(r=>setTimeout(r,300));
    }}
    currentData=accumulated;currentFrom=from;currentTo=to;
    // ── fase 2: humedad del suelo (Open-Meteo) ────────────────────────────────
    try{{
      setProgress(0,'Cargando humedad del suelo (Open-Meteo)...');
      const soilMap=await fetchAllSoilMoisture(GRID_POINTS,from,to,(ci,tot)=>
        setProgress(ci/tot,'Humedad suelo: '+(ci+1)+'/'+tot+'...'));
      accumulated=accumulated.map(d=>
        ({{...d,avg_soil_moisture:soilMap[d.lat.toFixed(4)+','+d.lon.toFixed(4)]??null}}));
      currentData=accumulated;
    }}catch(e){{console.warn('Humedad del suelo no disponible:',e.message);}}
    setProgress(1,'Completado');
    renderLayer(currentLayer,'a');
    if(compareMode&&mapB&&currentDataB) renderLayer(currentLayer,'b');
    updateHeader(currentData,from,to);
  }}catch(e){{
    hideProgress();showErr('Error inesperado: '+e.message);
  }}finally{{
    setTimeout(hideProgress,2000);isFetching=false;btn.disabled=false;
  }}
}}

// ── CSV export ────────────────────────────────────────────────────────────────
function frostDateWithYear(ddmm){{
  if(!ddmm||!currentFrom) return ddmm??'';
  const [dd,mm]=ddmm.split('/').map(Number);
  const fromYear=parseInt(currentFrom.slice(0,4));
  const fromDate=new Date(currentFrom+'T00:00:00Z');
  const candidate=new Date(Date.UTC(fromYear,mm-1,dd));
  return `${{ddmm}}/${{candidate>=fromDate?fromYear:fromYear+1}}`;
}}

function exportCSV(){{
  const h='lat,lon,region,frost_hours,frost_hours_5,min_temp,degree_days,degree_days_6,avg_amplitude,first_frost,last_frost,frost_free_streak,precip_total,water_balance,dry_streak,avg_humidity,avg_soil_moisture';
  const rows=currentData.map(d=>[d.lat,d.lon,getPointRegion(d),d.frost_hours??'',d.frost_hours_5??'',d.min_temp??'',d.degree_days??'',
    d.degree_days_6??'',d.avg_amplitude??'',
    frostDateWithYear(d.first_frost),frostDateWithYear(d.last_frost),
    d.frost_free_streak??'',d.precip_total??'',d.water_balance??'',d.dry_streak??'',
    d.avg_humidity??'',d.avg_soil_moisture??''].join(','));
  const blob=new Blob([[h,...rows].join('\\n')],{{type:'text/csv'}});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);
  a.download=`heladas_${{currentFrom}}_${{currentTo}}.csv`;a.click();
}}

// ── Compare / split-view ──────────────────────────────────────────────────────
function toggleCompare(){{
  if(!compareMode) enterCompareMode(); else exitCompareMode();
}}

function enterCompareMode(){{
  if(typeof map.sync!=='function'){{
    showErr('Leaflet.Sync no disponible. Intentá recargar la página.');
    return;
  }}
  compareMode=true;
  const btn=document.getElementById('compare-btn');
  btn.textContent='Vista única ✕';btn.classList.add('active');

  document.getElementById('date-bar').style.display='none';
  document.getElementById('split-bar').style.display='flex';
  document.getElementById('panel-b').style.display='flex';

  const mx=maxDate();
  // Mapa A: Personalizado por defecto, fechas actuales pre-cargadas
  populateSel('camp-sel-a',false,true,true);
  document.getElementById('camp-sel-a').value='custom';
  document.getElementById('split-a-custom').style.display='flex';
  document.getElementById('split-a-from').value=currentFrom;
  document.getElementById('split-a-to').value  =currentTo;
  document.getElementById('split-a-from').max  =mx;
  document.getElementById('split-a-to').max    =mx;
  // Mapa B: Personalizado por defecto
  populateSel('camp-sel-b',false,true,true);
  document.getElementById('camp-sel-b').value='custom';
  document.getElementById('split-b-custom').style.display='flex';
  document.getElementById('split-b-from').max=mx;
  document.getElementById('split-b-to').max  =mx;

  mapB=L.map('map-b',{{center:map.getCenter(),zoom:map.getZoom()}});
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{
    attribution:'&copy; OpenStreetMap &copy; CartoDB',subdomains:'abcd',maxZoom:19
  }}).addTo(mapB);

  map.sync(mapB);
  mapB.sync(map);

  setTimeout(()=>{{
    map.invalidateSize();
    mapB.invalidateSize();
    renderLayer(currentLayer,'a');
  }},150);
}}

function exitCompareMode(){{
  compareMode=false;
  const btn=document.getElementById('compare-btn');
  btn.textContent='Comparar ⇔';btn.classList.remove('active');

  if(mapB){{
    map.unsync(mapB);
    mapB.unsync(map);
    clearLayersFor('b');
    mapB.remove();mapB=null;
  }}
  currentDataB=null;layerGroupB=null;

  document.getElementById('date-bar').style.display='';
  document.getElementById('split-bar').style.display='none';
  document.getElementById('panel-b').style.display='none';
  // Sincronizar fechas del top-bar con lo que quedó en currentFrom/currentTo
  document.getElementById('d-from').value=currentFrom;
  document.getElementById('d-to').value  =currentTo;

  setTimeout(()=>{{
    map.invalidateSize();
    renderLayer(currentLayer,'a');
  }},150);
}}

function onSplitSelChange(target){{
  const selId=(target==='b')?'camp-sel-b':'camp-sel-a';
  const cwId =(target==='b')?'split-b-custom':'split-a-custom';
  const val  =document.getElementById(selId).value;
  const cw   =document.getElementById(cwId);
  if(val==='custom'){{
    cw.style.display='flex';
  }}else{{
    cw.style.display='none';
    if(val) fetchForMap(target);
  }}
}}

async function fetchForMap(target){{
  const selId =(target==='b')?'camp-sel-b':'camp-sel-a';
  const fromId=(target==='b')?'split-b-from':'split-a-from';
  const toId  =(target==='b')?'split-b-to':'split-a-to';
  let from,to;
  const val=document.getElementById(selId).value;
  if(!val) return;
  if(val==='custom'){{
    from=document.getElementById(fromId).value;
    to  =document.getElementById(toId).value;
  }}else{{
    [from,to]=campaignDates(val);
  }}
  if(!validateDates(from,to)) return;
  if(isFetching) return;

  const btn=document.getElementById('update-btn');
  isFetching=true;btn.disabled=true;
  showProgress();hideErr();clearLayersFor(target);

  try{{
    const data=await fetchFullCampaign(from,to,(ci,total)=>{{
      setProgress(ci/total,`Mapa ${{target.toUpperCase()}}: chunk ${{ci+1}}/${{total}}...`);
    }});
    let merged=data;
    try{{
      setProgress(0,'Cargando humedad del suelo...');
      const soilMap=await fetchAllSoilMoisture(GRID_POINTS,from,to);
      merged=data.map(d=>({{...d,avg_soil_moisture:soilMap[d.lat.toFixed(4)+','+d.lon.toFixed(4)]??null}}));
    }}catch(e){{console.warn('Humedad del suelo no disponible (mapa '+target+'):',e.message);}}
    if(target==='b'){{
      currentDataB=merged;
    }}else{{
      currentData=merged;currentFrom=from;currentTo=to;
      updateHeader(merged,from,to);
    }}
    setProgress(1,`Mapa ${{target.toUpperCase()}} cargado`);
    renderLayer(currentLayer,target);
  }}catch(e){{
    if(e.message.startsWith('CORS')){{
      showErr('CORS bloqueado. Usá fetch_data.py para cargar datos offline.');
    }}else{{
      showErr('Error Mapa '+target.toUpperCase()+': '+e.message);
    }}
  }}finally{{
    setTimeout(hideProgress,2000);isFetching=false;btn.disabled=false;
  }}
}}

// ── Location search ──────────────────────────────────────────────────────────
let searchMarker=null, searchTimer=null;

function onSearchInput(){{
  const q=document.getElementById('search-input').value.trim();
  document.getElementById('search-clear').style.display=q?'':'none';
  document.getElementById('search-results').innerHTML='';
  clearTimeout(searchTimer);
  if(q.length<2) return;
  searchTimer=setTimeout(()=>doSearch(q),500);
}}

async function doSearch(q){{
  const res=document.getElementById('search-results');
  res.innerHTML='<div class="srch-msg">Buscando...</div>';
  try{{
    const url=`https://nominatim.openstreetmap.org/search?q=${{encodeURIComponent(q+', Argentina')}}&format=json&limit=6&accept-language=es&countrycodes=ar`;
    const data=await fetch(url,{{headers:{{'User-Agent':'heladas-dashboard'}}}}).then(r=>r.json());
    res.innerHTML='';
    if(!data.length){{res.innerHTML='<div class="srch-msg">Sin resultados</div>';return;}}
    data.forEach(item=>{{
      const name=item.display_name.split(',').slice(0,2).join(',').trim();
      const div=document.createElement('div');
      div.className='srch-item';
      div.innerHTML=`<b>${{name}}</b><br><span style="color:#888;font-size:10px">${{item.display_name.split(',').slice(2,4).join(',').trim()}}</span>`;
      div.onclick=()=>selectSearchResult(parseFloat(item.lat),parseFloat(item.lon),name);
      res.appendChild(div);
    }});
  }}catch(e){{
    res.innerHTML='<div class="srch-msg" style="color:#c00">Error de red</div>';
  }}
}}

function selectSearchResult(lat,lon,name){{
  document.getElementById('search-input').value=name;
  document.getElementById('search-results').innerHTML='';
  document.getElementById('search-clear').style.display='';
  highlightNearest(lat,lon,name);
}}

function findNearestPoint(lat,lon){{
  const data=currentData;
  if(!data||!data.length) return null;
  let best=null,bestDist=Infinity;
  data.forEach(d=>{{
    const dist=(d.lat-lat)**2+(d.lon-lon)**2;
    if(dist<bestDist){{bestDist=dist;best=d;}}
  }});
  return best;
}}

function highlightNearest(lat,lon,name){{
  if(searchMarker){{map.removeLayer(searchMarker);searchMarker=null;}}
  map.setView([lat,lon],9,{{animate:true}});
  const pt=findNearestPoint(lat,lon);
  if(!pt) return;
  searchMarker=L.circleMarker([pt.lat,pt.lon],{{
    radius:14,color:'#f7d83f',weight:3,fillColor:'transparent',fillOpacity:0,dashArray:'4 3'
  }}).addTo(map);
  const lines=[
    `<b>${{name}}</b>`,
    `<small style="color:#888">${{pt.lat.toFixed(3)}}° / ${{pt.lon.toFixed(3)}}°</small>`,
    pt.frost_hours!=null?`Heladas: <b>${{pt.frost_hours}} h</b>`:null,
    pt.min_temp!=null?`T min: ${{pt.min_temp}} °C`:null,
    pt.precip_total!=null?`Precip: ${{pt.precip_total}} mm`:null,
  ].filter(Boolean).join('<br>');
  searchMarker.bindPopup(lines,{{maxWidth:180}}).openPopup();
}}

function clearSearch(){{
  document.getElementById('search-input').value='';
  document.getElementById('search-results').innerHTML='';
  document.getElementById('search-clear').style.display='none';
  if(searchMarker){{map.removeLayer(searchMarker);searchMarker=null;}}
}}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
(function(){{
  const mx=maxDate();
  document.getElementById('d-from').max=mx;
  document.getElementById('d-to').max  =mx;
  populateSel('campaign-sel',true,false);  // sin opción "Personalizado"
  // Seleccionar por defecto el año del período cargado
  const dataYear=currentFrom.slice(0,4);
  const sel=document.getElementById('campaign-sel');
  if([...sel.options].some(o=>o.value===dataYear)) sel.value=dataYear;
}})();

renderLayer('frost','a');
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = os.path.getsize(output_path) // 1024
    print(f"  Dashboard: {output_path}  ({size_kb} KB)")


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("metrics_json", nargs="?")
    p.add_argument("--start", default=None)
    p.add_argument("--end",   default=None)
    p.add_argument("--open",  action="store_true")
    return p.parse_args()


def latest_metrics() -> str | None:
    data_dir = os.path.join(_HERE, "data")
    if not os.path.isdir(data_dir):
        return None
    files = sorted(
        (f for f in os.listdir(data_dir) if f.startswith("metrics_") and f.endswith(".json")),
        reverse=True,
    )
    return os.path.join(data_dir, files[0]) if files else None


def main():
    args = parse_args()

    json_path = args.metrics_json or latest_metrics()
    if not json_path or not os.path.exists(json_path):
        print("ERROR: no se encontró archivo de métricas. Corre fetch_data.py primero.")
        sys.exit(1)

    print(f"Cargando: {json_path}")
    metrics = load_metrics(json_path)

    from config import DATE_START, DATE_END, METEOBLUE_TOKEN
    date_start = args.start or DATE_START
    date_end   = args.end   or DATE_END

    grid_coords = load_grid_coords()
    print(f"Grilla embebida: {len(grid_coords)} puntos")

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = os.path.join(_HERE, "output", f"dashboard_{ts}.html")

    print(f"Generando dashboard ({len(metrics)} registros)...")
    build_html(metrics, date_start, date_end, output_path,
               api_key=METEOBLUE_TOKEN, grid_coords=grid_coords)

    if args.open:
        import subprocess
        subprocess.Popen(["start", "", os.path.abspath(output_path)], shell=True)

    print(f"Listo: {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
