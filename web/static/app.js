(() => {
  const ZONE_ORDER = [
    "Timbúes", "San Lorenzo", "Rosario", "Punta Alvear", "Gral. Lagos",
    "Arroyo Seco", "Villa Constitución", "San Nicolás", "Ramallo",
  ];
  const STATUS_LABEL = {
    cargando: "Cargando", en_rada: "En rada", arribando: "Arribando", en_cola: "En cola",
  };
  const TZ = "America/Argentina/Cordoba";
  const DEST_META = {
    ALGERIA: { label: "Argelia", lat: 28.0, lon: 3.0 },
    AUSTRALIA: { label: "Australia", lat: -25.0, lon: 134.0 },
    BRAZIL: { label: "Brasil", lat: -14.2, lon: -51.9 },
    CAMEROON: { label: "Camerún", lat: 5.7, lon: 12.0 },
    CANADA: { label: "Canadá", lat: 56.1, lon: -106.3 },
    CHILE: { label: "Chile", lat: -35.7, lon: -71.5 },
    CHINA: { label: "China", lat: 35.9, lon: 104.2 },
    DENMARK: { label: "Dinamarca", lat: 56.3, lon: 9.5 },
    "DOMINICAN REPUB": { label: "Rep. Dominicana", lat: 18.7, lon: -70.2 },
    ECUADOR: { label: "Ecuador", lat: -1.8, lon: -78.2 },
    EGYPT: { label: "Egipto", lat: 26.8, lon: 30.8 },
    "EL SALVADOR": { label: "El Salvador", lat: 13.8, lon: -88.9 },
    FRANCE: { label: "Francia", lat: 46.2, lon: 2.2 },
    GERMANY: { label: "Alemania", lat: 51.2, lon: 10.4 },
    GREECE: { label: "Grecia", lat: 39.1, lon: 21.8 },
    GUATEMALA: { label: "Guatemala", lat: 15.8, lon: -90.2 },
    INDIA: { label: "India", lat: 20.6, lon: 79.0 },
    INDONESIA: { label: "Indonesia", lat: -2.5, lon: 118.0 },
    IRAQ: { label: "Irak", lat: 33.2, lon: 43.7 },
    IRELAND: { label: "Irlanda", lat: 53.1, lon: -8.0 },
    ISRAEL: { label: "Israel", lat: 31.0, lon: 34.9 },
    ITALY: { label: "Italia", lat: 41.9, lon: 12.6 },
    KOREA: { label: "Corea", lat: 35.9, lon: 127.8 },
    LATVIA: { label: "Letonia", lat: 56.9, lon: 24.1 },
    LIBYA: { label: "Libia", lat: 26.3, lon: 17.2 },
    MADAGASCAR: { label: "Madagascar", lat: -18.8, lon: 46.9 },
    MALAYSIA: { label: "Malasia", lat: 4.2, lon: 101.9 },
    MEXICO: { label: "México", lat: 23.6, lon: -102.5 },
    MOROCCO: { label: "Marruecos", lat: 31.8, lon: -7.1 },
    NETHERLANDS: { label: "Países Bajos", lat: 52.1, lon: 5.3 },
    "NEW ZEALAND": { label: "Nueva Zelanda", lat: -40.9, lon: 174.9 },
    OMAN: { label: "Omán", lat: 21.5, lon: 55.9 },
    PARAGUAY: { label: "Paraguay", lat: -23.4, lon: -58.4 },
    PERU: { label: "Perú", lat: -9.2, lon: -75.0 },
    PHILIPPINES: { label: "Filipinas", lat: 12.9, lon: 121.8 },
    POLAND: { label: "Polonia", lat: 51.9, lon: 19.1 },
    PORTUGAL: { label: "Portugal", lat: 39.4, lon: -8.2 },
    "PUERTO RICO": { label: "Puerto Rico", lat: 18.2, lon: -66.6 },
    "SAUDI ARABIA": { label: "Arabia Saudita", lat: 23.9, lon: 45.1 },
    SINGAPORE: { label: "Singapur", lat: 1.35, lon: 103.8 },
    SPAIN: { label: "España", lat: 40.5, lon: -3.7 },
    THAILAND: { label: "Tailandia", lat: 15.9, lon: 100.9 },
    TUNISIA: { label: "Túnez", lat: 33.9, lon: 9.5 },
    TURKEY: { label: "Turquía", lat: 38.96, lon: 35.2 },
    "UNITED ARAB EMIR": { label: "Emiratos Árabes", lat: 23.4, lon: 53.8 },
    "UNITED KINGDOM": { label: "Reino Unido", lat: 55.4, lon: -3.4 },
    "UNITED STATES": { label: "Estados Unidos", lat: 39.8, lon: -98.5 },
    URUGUAY: { label: "Uruguay", lat: -32.5, lon: -55.8 },
    VENEZUELA: { label: "Venezuela", lat: 6.4, lon: -66.6 },
    VIETNAM: { label: "Vietnam", lat: 14.1, lon: 108.3 },
    YEMEN: { label: "Yemen", lat: 15.6, lon: 48.5 },
  };
  const PIE_COLORS = [
    "#1B5E3B", "#1565C0", "#F57C00", "#6A1B9A", "#00838F",
    "#C62828", "#2E7D32", "#EF6C00", "#4527A0", "#00695C",
    "#AD1457", "#0277BD", "#558B2F", "#5D4037", "#37474F",
    "#7B1FA2", "#0097A7", "#E65100", "#283593", "#546E7A",
  ];
  /** Conservative charterer → country (same keys as NABSA / DEST_META). */
  const CHARTERER_DEST_INFER = {
    "AL GHURAIR": "UNITED ARAB EMIR",
    "COFCO": "CHINA",
    "CJ INTERNATIONAL": "KOREA",
    "CJ CHEILJEDANG": "KOREA",
    "ARASCO": "SAUDI ARABIA",
    "AL QAIRAWAN": "YEMEN",
  };

  let vesselsPayload = null;
  let trucksPayload = null;
  let coveragePayload = null;
  let worldMap = null;
  let worldLayer = null;
  let worldMapReady = false;
  const arrivalsCollapsed = new Set();
  const $ = (id) => document.getElementById(id);

  function fmtNum(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return new Intl.NumberFormat("es-AR").format(Math.round(n));
  }
  function fmtTons(n) {
    if (n == null || Number.isNaN(n)) return "—";
    if (n >= 1000) return fmtNum(n / 1000) + " mil tn";
    return fmtNum(n) + " tn";
  }
  function fmtTonsShort(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return fmtNum(n) + " tn";
  }
  function toAR(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString("es-AR", { timeZone: TZ, dateStyle: "short", timeStyle: "short" }) + " ART";
    } catch { return iso; }
  }
  function todayCordoba() {
    return new Date().toLocaleDateString("en-CA", { timeZone: TZ });
  }
  function parseEtaYmd(eta) {
    const m = String(eta || "").match(/(\d{1,2})\s*\/\s*(\d{1,2})/);
    if (!m) return null;
    const day = parseInt(m[1], 10);
    const month = parseInt(m[2], 10);
    if (month < 1 || month > 12 || day < 1 || day > 31) return null;
    const today = todayCordoba();
    const year = parseInt(today.slice(0, 4), 10);
    return year + "-" + String(month).padStart(2, "0") + "-" + String(day).padStart(2, "0");
  }
  function isPastEta(eta) {
    const ymd = parseEtaYmd(eta);
    if (!ymd) return false;
    return ymd < todayCordoba();
  }
  function isStaleArrival(v) {
    return v.status === "arribando" && isPastEta(v.eta);
  }
  function upRiverVessels() {
    const all = vesselsPayload?.vessels || [];
    return all.filter((v) => v.up_river && !isStaleArrival(v));
  }
  function sortZones(keys) {
    return [...keys].sort((a, b) => {
      const ia = ZONE_ORDER.indexOf(a);
      const ib = ZONE_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b, "es");
    });
  }
  function currentFilters() {
    return {
      zone: $("fZone").value,
      commodity: $("fCommodity").value,
      status: $("fStatus").value,
      search: ($("fSearch").value || "").trim().toLowerCase(),
    };
  }
  function applyFilters(list) {
    const f = currentFilters();
    return list.filter((v) => {
      if (f.zone && v.zone !== f.zone) return false;
      if (f.commodity) {
        if (f.commodity === "otro") {
          if (["soja", "maiz", "trigo", "girasol", "sorgo", "cebada"].includes(v.commodity)) return false;
        } else if (v.commodity !== f.commodity) return false;
      }
      if (f.status && v.status !== f.status) return false;
      if (f.search && !(v.vessel || "").toLowerCase().includes(f.search)) return false;
      return true;
    });
  }
  function fillZones(list) {
    const sel = $("fZone");
    const cur = sel.value;
    const zones = sortZones([...new Set(list.map((v) => v.zone))]);
    sel.innerHTML = '<option value="">Todas</option>' + zones.map((z) => '<option value="' + z + '">' + z + "</option>").join("");
    if (zones.includes(cur)) sel.value = cur;
  }
  function chip(commodity, label) {
    const c = commodity || "otro";
    return '<span class="chip ' + c + '">' + (label || c) + "</span>";
  }
  function statusBadge(st) {
    return '<span class="status ' + st + '">' + (STATUS_LABEL[st] || st) + "</span>";
  }
  function timing(v) {
    return [v.etf, v.etb, v.eta].filter(Boolean).join(" · ") || "—";
  }
  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function norm(s) {
    return String(s || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  function rawDestination(v) {
    return String(v.destination || v.destino || "").trim();
  }
  function isArgentinaDest(raw) {
    const n = norm(raw);
    return n === "argentina" || n === "ar" || n === "arg" || n.startsWith("argentina ");
  }
  function isUnknownDest(raw) {
    const n = norm(raw);
    if (!n) return true;
    return (
      n === "not available" ||
      n === "n a" ||
      n === "na" ||
      n === "n/a" ||
      n === "unknown" ||
      n === "tbd" ||
      n === "-" ||
      n === "sin destino" ||
      n === "otros"
    );
  }
  function isUnknownCharterer(ch) {
    return isUnknownDest(ch);
  }
  function destKey(raw) {
    return String(raw || "").trim().toUpperCase();
  }
  function destLabel(key) {
    if (DEST_META[key]) return DEST_META[key].label;
    // title-case fallback
    return key
      .toLowerCase()
      .split(" ")
      .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
      .join(" ");
  }
  function inferFromCharterer(charterer) {
    if (isUnknownCharterer(charterer)) return null;
    const n = destKey(charterer);
    if (CHARTERER_DEST_INFER[n]) return CHARTERER_DEST_INFER[n];
    const keys = Object.keys(CHARTERER_DEST_INFER).sort((a, b) => b.length - a.length);
    for (const key of keys) {
      if (n.includes(key)) return CHARTERER_DEST_INFER[key];
    }
    return null;
  }
  /** Effective export/AR destination: NABSA first; else conservative charterer estimate. */
  function effectiveDestination(v) {
    if (v.destination_source === "inferred" && v.destination_inferred) {
      return String(v.destination_inferred).trim();
    }
    const raw = rawDestination(v);
    if (!isUnknownDest(raw)) return raw;
    if (v.destination_inferred) return String(v.destination_inferred).trim();
    return inferFromCharterer(v.charterer) || "";
  }
  function isDestinationInferred(v) {
    if (v.destination_source === "inferred" && v.destination_inferred) return true;
    const raw = rawDestination(v);
    if (!isUnknownDest(raw)) return false;
    if (v.destination_inferred) return true;
    return !!inferFromCharterer(v.charterer);
  }
  function formatDestDisplay(v) {
    const raw = rawDestination(v);
    if (isDestinationInferred(v)) {
      const key = destKey(effectiveDestination(v));
      return (
        escapeHtml(destLabel(key)) +
        ' <span class="badge estimado" title="Estimado por charterer">estimado</span>'
      );
    }
    if (isUnknownDest(raw)) return "Sin destino";
    if (isArgentinaDest(raw)) return "Descarga AR";
    return escapeHtml(destLabel(destKey(raw)));
  }

  /** Aggregate tons: known foreign exports, Descarga AR, and Sin destino (NABSA). */
  function aggregateDestinations(list) {
    const exportMap = new Map();
    let arTons = 0;
    let arCount = 0;
    let sinDestTons = 0;
    let sinDestCount = 0;
    let inferredCount = 0;
    let inferredTons = 0;
    for (const v of list) {
      const tons = Number(v.tons) || 0;
      const raw = rawDestination(v);
      const inferred = isDestinationInferred(v);
      const eff = effectiveDestination(v);
      if (isArgentinaDest(raw) || isArgentinaDest(eff)) {
        arTons += tons;
        arCount += 1;
        continue;
      }
      if (!eff || isUnknownDest(eff)) {
        sinDestTons += tons;
        sinDestCount += 1;
        continue;
      }
      const key = destKey(eff);
      const cur = exportMap.get(key) || { key, label: destLabel(key), tons: 0, count: 0, inferredCount: 0 };
      cur.tons += tons;
      cur.count += 1;
      if (inferred) {
        cur.inferredCount += 1;
        inferredCount += 1;
        inferredTons += tons;
      }
      exportMap.set(key, cur);
    }
    const exports = [...exportMap.values()].sort((a, b) => b.tons - a.tons || a.label.localeCompare(b.label, "es"));
    return {
      exports,
      arTons,
      arCount,
      sinDestTons,
      sinDestCount,
      otrosTons: sinDestTons,
      otrosCount: sinDestCount,
      inferredCount,
      inferredTons,
    };
  }

  function initWorldMap() {
    if (worldMap || typeof L === "undefined") return;
    const el = $("worldMap");
    if (!el) return;
    worldMap = L.map(el, { zoomControl: true, attributionControl: true, worldCopyJump: true }).setView([10, 20], 2);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      attribution: "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
      maxZoom: 8,
      minZoom: 1,
    }).addTo(worldMap);
    worldLayer = L.layerGroup().addTo(worldMap);
    worldMapReady = true;
    setTimeout(() => worldMap.invalidateSize(), 80);
  }

  function renderWorldMap(exports) {
    if (!worldMapReady) initWorldMap();
    if (!worldMap || !worldLayer) return;
    worldLayer.clearLayers();
    const maxTons = Math.max(...exports.map((e) => e.tons), 1);
    const bounds = [];
    exports.forEach((e, i) => {
      const meta = DEST_META[e.key];
      if (!meta || meta.lat == null) return;
      const r = 4 + Math.sqrt(e.tons / maxTons) * 22;
      const color = PIE_COLORS[i % PIE_COLORS.length];
      const circle = L.circleMarker([meta.lat, meta.lon], {
        radius: r,
        color: "#0B1F3A",
        weight: 1,
        fillColor: color,
        fillOpacity: 0.72,
      });
      circle.bindPopup(
        '<div class="pop-name">' + escapeHtml(e.label) + "</div>" +
        '<div class="pop-row"><strong>Toneladas</strong> ' + escapeHtml(fmtTonsShort(e.tons)) + "</div>" +
        '<div class="pop-row"><strong>Embarques</strong> ' + escapeHtml(String(e.count)) + "</div>"
      );
      worldLayer.addLayer(circle);
      bounds.push([meta.lat, meta.lon]);
    });
    if (bounds.length) {
      try { worldMap.fitBounds(bounds, { padding: [28, 28], maxZoom: 4 }); }
      catch { worldMap.setView([10, 20], 2); }
    } else {
      worldMap.setView([10, 20], 2);
    }
    setTimeout(() => worldMap.invalidateSize(), 50);
  }

  function drawDestPie(exports) {
    const canvas = $("destChart");
    if (!canvas) return;
    const rect = canvas.parentElement?.getBoundingClientRect();
    const size = Math.max(220, Math.min(360, Math.floor((rect?.width || 320))));
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = size + "px";
    canvas.style.height = size + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);

    // Show enough named countries so "Resto países" is a true remainder of known destinations,
    // not a misleading "Otros"/unknown bucket (~53% when TOP was 8).
    const TOP = 14;
    let slices = exports.slice(0, TOP).map((e, i) => ({
      label: e.label, tons: e.tons, color: PIE_COLORS[i % PIE_COLORS.length],
    }));
    const restTons = exports.slice(TOP).reduce((s, e) => s + e.tons, 0);
    if (restTons > 0) {
      slices.push({ label: "Resto países", tons: restTons, color: "#90A4AE" });
    }
    const total = slices.reduce((s, x) => s + x.tons, 0);
    const cx = size / 2;
    const cy = size / 2;
    const radius = size * 0.38;
    const inner = radius * 0.55;

    if (total <= 0) {
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.fillStyle = "#e8eef5";
      ctx.fill();
      ctx.beginPath();
      ctx.arc(cx, cy, inner, 0, Math.PI * 2);
      ctx.fillStyle = "#fff";
      ctx.fill();
      ctx.fillStyle = "#5b6b7c";
      ctx.font = "600 13px system-ui,sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("Sin exportaciones", cx, cy);
      return slices;
    }

    let angle = -Math.PI / 2;
    for (const sl of slices) {
      const sweep = (sl.tons / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, angle, angle + sweep);
      ctx.closePath();
      ctx.fillStyle = sl.color;
      ctx.fill();
      angle += sweep;
    }
    ctx.beginPath();
    ctx.arc(cx, cy, inner, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.fillStyle = "#0B1F3A";
    ctx.font = "800 15px system-ui,sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(fmtTons(total).replace(" mil tn", "k"), cx, cy - 8);
    ctx.fillStyle = "#5b6b7c";
    ctx.font = "600 11px system-ui,sans-serif";
    ctx.fillText("export tn", cx, cy + 12);
    return slices;
  }

  function renderDestinations(list) {
    const agg = aggregateDestinations(list);
    $("destCount").textContent = String(agg.exports.length);
    $("destArTons").textContent = fmtTons(agg.arTons);
    $("destArHint").textContent =
      agg.arCount + " embarque(s) · destino Argentina = descarga (no export)";
    $("destOtrosTons").textContent = fmtTons(agg.sinDestTons);
    const sinHint = $("destSinHint") || $("destOtrosHint");
    if (sinHint) {
      sinHint.textContent =
        agg.sinDestCount + " embarque(s) NABSA sin país" +
        (agg.inferredCount
          ? " · " + agg.inferredCount + " estimado(s) por charterer ya en la torta"
          : "");
    }
    const slices = drawDestPie(agg.exports);
    const exportTons = agg.exports.reduce((s, e) => s + e.tons, 0);
    $("destChartNote").textContent =
      "Exportación conocida: " + fmtTons(exportTons) +
      " · Descarga AR y Sin destino aparte" +
      (agg.inferredTons ? " · incluye " + fmtTons(agg.inferredTons) + " estimadas" : "");

    const colorByLabel = new Map((slices || []).map((s) => [s.label, s.color]));
    const maxExport = Math.max(...agg.exports.map((e) => e.tons), 1);
    $("destList").innerHTML = agg.exports.length
      ? agg.exports
          .map((e, i) => {
            const col = colorByLabel.get(e.label) || PIE_COLORS[i % PIE_COLORS.length];
            const est =
              e.inferredCount > 0
                ? ' <span class="badge estimado" title="Incluye destino estimado por charterer">estimado</span>'
                : "";
            const pct = Math.max(2, Math.round((100 * e.tons) / maxExport));
            return (
              '<div class="dest-row">' +
              '<span class="dest-swatch" style="background:' + col + '"></span>' +
              '<div class="dest-rank">' +
              '<div class="dest-name-row"><span class="dest-name">' + escapeHtml(e.label) + est +
              '</span><span class="dest-tons">' + escapeHtml(fmtTonsShort(e.tons)) + "</span></div>" +
              '<div class="dest-bar-track"><div class="dest-bar-fill" style="width:' + pct +
              "%;background:" + col + '"></div></div>' +
              "</div></div>"
            );
          })
          .join("")
      : '<div class="empty">Sin destinos de exportación con estos filtros.</div>';

    renderWorldMap(agg.exports);
  }

  function renderQueue(list) {
    const waiting = list.filter((v) => v.status !== "arribando");
    $("queueCount").textContent = String(waiting.length);
    const byZone = new Map();
    for (const v of waiting) {
      if (!byZone.has(v.zone)) byZone.set(v.zone, []);
      byZone.get(v.zone).push(v);
    }
    const zones = sortZones([...byZone.keys()]);
    if (!zones.length) {
      $("queueBody").innerHTML = '<div class="empty">Sin buques en cola con los filtros actuales.</div>';
      return;
    }
    $("queueBody").innerHTML = zones
      .map((zone) => {
        const rows = byZone.get(zone);
        const tons = rows.reduce((s, v) => s + (v.tons || 0), 0);
        const cards = rows
          .map(
            (v) =>
              '<div class="vessel-card">' +
              "<div><div class=\"v-name\">" + escapeHtml(v.vessel) + '</div><div class="v-term">' + escapeHtml(v.terminal || v.port) + "</div></div>" +
              '<div class="v-meta">' + chip(v.commodity, v.commodity_label) + '<div style="margin-top:.35rem">' + statusBadge(v.status) + "</div></div>" +
              '<div class="v-meta"><div class="tons">' + fmtTonsShort(v.tons) + "</div><small>" + escapeHtml(v.ops || "") + "</small></div>" +
              '<div class="v-meta">' + escapeHtml(timing(v)) + '<div style="color:var(--muted);font-size:.75rem;margin-top:.2rem">' + formatDestDisplay(v) + "</div></div>" +
              "</div>"
          )
          .join("");
        return (
          '<div class="port-block"><div class="port-title"><span>' +
          escapeHtml(zone) +
          '</span><span class="meta">' +
          rows.length +
          " buques · " +
          fmtTons(tons) +
          "</span></div>" +
          cards +
          "</div>"
        );
      })
      .join("");
  }

  function renderArrivals(list) {
    const arrivals = list
      .filter((v) => v.status === "arribando")
      .slice()
      .sort((a, b) => {
        const da = parseEtaYmd(a.eta) || "9999";
        const db = parseEtaYmd(b.eta) || "9999";
        return da.localeCompare(db) || String(a.eta).localeCompare(String(b.eta));
      });
    $("arrivalsCount").textContent = String(arrivals.length);
    if (!arrivals.length) {
      $("arrivalsBody").innerHTML = '<div class="empty">Sin arribos anunciados con estos filtros.</div>';
      return;
    }
    const byZone = new Map();
    for (const v of arrivals) {
      const z = v.zone || "Otro";
      if (!byZone.has(z)) byZone.set(z, []);
      byZone.get(z).push(v);
    }
    const zones = sortZones([...byZone.keys()]);
    $("arrivalsBody").innerHTML = zones
      .map((zone) => {
        const rows = byZone.get(zone);
        const collapsed = arrivalsCollapsed.has(zone);
        const cards = rows
          .map(
            (v) =>
              '<div class="vessel-card arrival-card">' +
              "<div><div class=\"v-name\">" + escapeHtml(v.vessel) + '</div><div class="v-term">' + escapeHtml(v.terminal || "") + "</div></div>" +
              '<div class="v-meta">' + chip(v.commodity, v.commodity_label) + '<div class="tons" style="margin-top:.35rem">' + fmtTonsShort(v.tons) + "</div></div>" +
              '<div class="v-meta"><strong>' + escapeHtml(v.eta || "ETA") + '</strong><div style="color:var(--muted);font-size:.75rem;margin-top:.2rem">' + escapeHtml(v.charterer || "") + "</div></div>" +
              "</div>"
          )
          .join("");
        return (
          '<details class="port-fold" data-zone="' + escapeHtml(zone) + '" ' + (collapsed ? "" : "open") + ">" +
          '<summary class="port-title"><span class="port-title-main"><span class="fold-chevron" aria-hidden="true"></span>' +
          escapeHtml(zone) +
          '</span><span class="meta">' +
          rows.length +
          " · ETA ≥ hoy</span></summary>" +
          '<div class="port-fold-body">' + cards + "</div></details>"
        );
      })
      .join("");
    $("arrivalsBody").querySelectorAll("details.port-fold").forEach((el) => {
      el.addEventListener("toggle", () => {
        const z = el.getAttribute("data-zone");
        if (!z) return;
        if (el.open) arrivalsCollapsed.delete(z);
        else arrivalsCollapsed.add(z);
      });
    });
  }


  // Truck coverage KPI — factors Diego: 30 tn/cam (25 girasol). Semáforo by days_to_cover.
  // Calibration: MAGyP 2025 Rosario 964.503 cam/año ≈ 2.640/día; early Aug 2026 ~2.4k–4.5k/día;
  // picos AgroEntregas/BCR 5.500–7.000; stock Up-River ~3,5–5 Mt. At ~4,8 Mt: ~60d promedio (rojo),
  // ~40d flujo bueno (amarillo), ≤30d picos (verde).
  const GRAIN_COMMODITIES = new Set(["soja", "maiz", "trigo", "girasol", "sorgo", "cebada"]);
  const TN_TRUCK = 30;
  const TN_TRUCK_GIRASOL = 25;
  const DAYS_GREEN_MAX = 30;
  const DAYS_YELLOW_MAX = 55;

  function truckFactor(product) {
    return String(product || "").toLowerCase() === "girasol" ? TN_TRUCK_GIRASOL : TN_TRUCK;
  }

  function estimateTruckTn(trucks) {
    let truck_tn = 0;
    let total_camiones = 0;
    const by_product = [];
    for (const row of trucks?.by_product || []) {
      const camiones = Number(row.camiones) || 0;
      const factor = truckFactor(row.product);
      const tn = camiones * factor;
      by_product.push({ product: row.product, camiones, tn_per_truck: factor, tn });
      truck_tn += tn;
      total_camiones += camiones;
    }
    if (!by_product.length && trucks?.total_camiones) {
      total_camiones = Number(trucks.total_camiones) || 0;
      truck_tn = total_camiones * TN_TRUCK;
    }
    return { truck_tn, total_camiones, by_product, source: trucks?.source };
  }

  function estimateDemandTn(list) {
    let demand_tn = 0;
    let vessel_count = 0;
    let excluded_ar_tn = 0;
    for (const v of list) {
      if (!GRAIN_COMMODITIES.has(v.commodity)) continue;
      const tons = Number(v.tons) || 0;
      const raw = rawDestination(v);
      const eff = effectiveDestination(v);
      if (isArgentinaDest(raw) || isArgentinaDest(eff)) {
        excluded_ar_tn += tons;
        continue;
      }
      demand_tn += tons;
      vessel_count += 1;
    }
    return { demand_tn, vessel_count, excluded_ar_tn };
  }

  function classifySemaforo(days) {
    if (days == null || Number.isNaN(days)) {
      return { color: "gray", code: "sin_datos", label: "Sin datos", hint: "Sin flujo o sin demanda" };
    }
    if (days <= DAYS_GREEN_MAX) {
      return { color: "green", code: "verde", label: "Alto", hint: "Flujo alto · ≤ 30 días de cobertura" };
    }
    if (days <= DAYS_YELLOW_MAX) {
      return { color: "yellow", code: "amarillo", label: "Normal", hint: "Flujo normal · 30–55 días de cobertura" };
    }
    return { color: "red", code: "rojo", label: "Bajo", hint: "Flujo flojo · > 55 días de cobertura" };
  }

  function computeCoverageClient() {
    const trucksEst = estimateTruckTn(trucksPayload);
    // Full Up-River grain export demand (not UI filters) — matches /api/coverage
    const demandEst = estimateDemandTn(upRiverVessels());
    const truck_tn = trucksEst.truck_tn;
    const demand_tn = demandEst.demand_tn;
    const coverage_pct = demand_tn > 0 ? (100 * truck_tn) / demand_tn : null;
    const days_to_cover = truck_tn > 0 ? demand_tn / truck_tn : null;
    return {
      truck_tn,
      demand_tn,
      coverage_pct,
      days_to_cover,
      semaforo: classifySemaforo(days_to_cover),
      trucks: trucksEst,
      demand: demandEst,
    };
  }

  function fmtPct(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(n) + "%";
  }
  function fmtDays(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(n) + " d";
  }
  function fmtMt(n) {
    if (n == null || Number.isNaN(n)) return "—";
    if (n >= 1e6) return new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(n / 1e6) + " Mt";
    if (n >= 1000) return fmtNum(n / 1000) + " mil tn";
    return fmtNum(n) + " tn";
  }

  function renderCoverage() {
    const c = computeCoverageClient();
    coveragePayload = c;
    $("kpiTruckTn").textContent = c.truck_tn >= 1000 ? fmtNum(Math.round(c.truck_tn / 1000)) + "k" : fmtNum(c.truck_tn);
    $("kpiTruckTnHint").textContent =
      fmtNum(c.trucks.total_camiones) + " cam · 30 tn (25 girasol)";
    $("kpiCoveragePct").textContent = fmtPct(c.coverage_pct);
    $("kpiCoveragePctHint").textContent =
      "Demanda export " + fmtMt(c.demand_tn) + " · " + fmtNum(c.demand.vessel_count) + " buques";
    $("kpiDaysCover").textContent = fmtDays(c.days_to_cover);
    const sem = c.semaforo;
    const dot = $("semaforoDot");
    const lab = $("semaforoLabel");
    const card = $("kpiSemaforoCard");
    dot.className = "semaforo-dot " + (sem.color || "gray");
    lab.textContent = sem.label || "—";
    lab.className = "semaforo-label " + (sem.label || "");
    card.className = "kpi coverage kpi-semaforo " + (sem.code || "");
    $("kpiDaysHint").textContent = sem.hint || "Demanda ÷ tn camiones";

    const sampleCaveat =
      trucksPayload?.source === "sample"
        ? " Camiones: datos muestra (no MAGyP en vivo)."
        : "";
    $("coverageFootnote").textContent =
      "Cobertura: tn camiones = Σ by_product.camiones × 30 tn (girasol × 25). " +
      "Demanda = tn anunciadas Up-River (soja, maíz, trigo, girasol, sorgo, cebada) excl. Argentina / Descarga AR. " +
      "Semáforo (días cobertura): Verde ≤30 Alto · Amarillo 30–55 Normal · Rojo >55 Bajo (flujo vs stock). " +
      "Calibración: MAGyP 2025 Rosario ≈2.640 cam/día; ago-2026 ~2,4–4,5k; picos 5,5–7k; stock típico 3,5–5 Mt " +
      "(a ~4,8 Mt: ~60d promedio / ~40d bueno / ≤30d pico)." +
      sampleCaveat;
  }

  function renderKpis(list) {
    const cola = list.filter((v) => v.status !== "arribando");
    const uniqueCola = new Set(cola.map((v) => v.vessel + "|" + v.terminal));
    const tons = list.reduce((s, v) => s + (v.tons || 0), 0);
    $("kpiCola").textContent = fmtNum(uniqueCola.size);
    $("kpiTons").textContent = tons >= 1000 ? fmtNum(Math.round(tons / 1000)) + "k" : fmtNum(tons);
    if (trucksPayload) $("kpiTrucks").textContent = fmtNum(trucksPayload.total_camiones);
    const updated = vesselsPayload?.updated_at || trucksPayload?.updated_at;
    $("kpiUpdated").textContent = toAR(updated);
    const live = vesselsPayload?.live && vesselsPayload?.parse_ok;
    const stale = vesselsPayload?.cache?.stale;
    const refreshing = vesselsPayload?.cache?.refresh_in_progress;
    let liveText = live ? "NABSA en vivo" : "Datos locales / muestra";
    if (refreshing) liveText = "Actualizando NABSA…";
    else if (stale && live) liveText = "NABSA (cache)";
    $("liveLabel").textContent = liveText;
    const src = vesselsPayload?.meta?.header || vesselsPayload?.source || "NABSA";
    $("kpiSource").textContent = src;
  }

  function renderTrucks() {
    const t = trucksPayload;
    if (!t) {
      $("truckBars").innerHTML = '<div class="empty">Sin datos de camiones.</div>';
      return;
    }
    $("trucksCount").textContent = fmtNum(t.total_camiones);
    const max = Math.max(...t.by_product.map((p) => p.camiones), 1);
    $("truckBars").innerHTML = t.by_product
      .map(
        (p) =>
          '<div class="bar-row"><div class="bar-label">' +
          escapeHtml(p.label) +
          '</div><div class="bar-track"><div class="bar-fill ' +
          p.product +
          '" style="width:' +
          (100 * p.camiones) / max +
          '%"></div></div><div class="bar-val">' +
          fmtNum(p.camiones) +
          "</div></div>"
      )
      .join("");
    $("truckZones").innerHTML = (t.by_zone || [])
      .map(
        (z) =>
          '<div class="zone-card"><strong>' +
          escapeHtml(z.zone) +
          "</strong><span>" +
          fmtNum(z.camiones) +
          " camiones</span></div>"
      )
      .join("");
    $("legend").innerHTML = ["soja|Soja", "maiz|Maíz", "trigo|Trigo", "girasol|Girasol", "sorgo|Sorgo"]
      .map((x) => {
        const [c, l] = x.split("|");
        return chip(c, l);
      })
      .join("");
    $("truckNote").textContent =
      t.source === "sample"
        ? "Camiones: muestra realista local (MAGyP/BCR sin API estructurada)."
        : "Fuente camiones: " + t.source;
  }

  function renderAll() {
    const base = upRiverVessels();
    fillZones(base);
    const filtered = applyFilters(base);
    renderKpis(filtered);
    renderQueue(filtered);
    renderArrivals(filtered);
    renderTrucks();
    renderDestinations(filtered);
  }

  async function load() {
    $("queueBody").innerHTML = '<div class="loading">Cargando lineup…</div>';
    try {
      const [vRes, tRes] = await Promise.all([fetch("/api/vessels"), fetch("/api/trucks")]);
      vesselsPayload = await vRes.json();
      trucksPayload = await tRes.json();
      initWorldMap();
      renderAll();
      if (vesselsPayload?.cache?.refresh_in_progress || vesselsPayload?.cache?.stale) {
        setTimeout(async () => {
          try {
            const r = await fetch("/api/vessels");
            const next = await r.json();
            if (next?.updated_at && next.updated_at !== vesselsPayload?.updated_at) {
              vesselsPayload = next;
              renderAll();
            } else if (next?.cache) {
              vesselsPayload = next;
              renderKpis(applyFilters(upRiverVessels()));
            }
          } catch { /* ignore */ }
        }, 8000);
      }
    } catch (err) {
      console.error(err);
      $("queueBody").innerHTML = '<div class="empty">Error al cargar datos: ' + escapeHtml(err.message) + "</div>";
      $("liveLabel").textContent = "Error de carga";
    }
  }

  $("fZone").addEventListener("change", renderAll);
  $("fCommodity").addEventListener("change", renderAll);
  $("fStatus").addEventListener("change", renderAll);
  $("fSearch").addEventListener("input", renderAll);
  $("btnReset").addEventListener("click", () => {
    $("fZone").value = "";
    $("fCommodity").value = "";
    $("fStatus").value = "";
    $("fSearch").value = "";
    renderAll();
  });
  $("btnReload").addEventListener("click", load);
  window.addEventListener("resize", () => {
    if (vesselsPayload) {
      const filtered = applyFilters(upRiverVessels());
      renderDestinations(filtered);
    }
  });

  load();
})();
