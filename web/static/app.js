(() => {
  const ZONE_ORDER = [
    "Timbúes",
    "San Lorenzo",
    "Rosario",
    "Punta Alvear",
    "Gral. Lagos",
    "Arroyo Seco",
    "Villa Constitución",
    "San Nicolás",
    "Ramallo",
  ];

  const STATUS_LABEL = {
    cargando: "Cargando",
    en_rada: "En rada",
    arribando: "Arribando",
    en_cola: "En cola",
  };

  const COMMODITY_COLOR = {
    soja: "#2E7D32",
    maiz: "#F57C00",
    trigo: "#C4A35A",
    girasol: "#F9A825",
    sorgo: "#C62828",
    cebada: "#8D6E63",
    biodiesel: "#00695C",
    otro: "#607D8B",
  };

  let vesselsPayload = null;
  let trucksPayload = null;
  let terminalsPayload = null;
  let map = null;
  let markerLayer = null;
  let mapReady = false;

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
      return d.toLocaleString("es-AR", {
        timeZone: "America/Argentina/Buenos_Aires",
        dateStyle: "short",
        timeStyle: "short",
      }) + " ART";
    } catch {
      return iso;
    }
  }

  function upRiverVessels() {
    const all = vesselsPayload?.vessels || [];
    return all.filter((v) => v.up_river);
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
    const zones = [...new Set(list.map((v) => v.zone))].sort((a, b) => {
      const ia = ZONE_ORDER.indexOf(a);
      const ib = ZONE_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b, "es");
    });
    sel.innerHTML = '<option value="">Todas</option>' + zones.map((z) => `<option value="${z}">${z}</option>`).join("");
    if (zones.includes(cur)) sel.value = cur;
  }

  function chip(commodity, label) {
    const c = commodity || "otro";
    return `<span class="chip ${c}">${label || c}</span>`;
  }

  function statusBadge(st) {
    return `<span class="status ${st}">${STATUS_LABEL[st] || st}</span>`;
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

  /** Resolve vessel zone/port/terminal to a terminal coord entry. */
  function resolveTerminal(v) {
    const terminals = terminalsPayload?.terminals || [];
    if (!terminals.length) return null;

    const zoneN = norm(v.zone);
    byLabel: for (const t of terminals) {
      if (norm(t.label) === zoneN) return t;
    }

    const hay = [v.zone, v.port, v.port_raw, v.terminal].map(norm).filter(Boolean);
    for (const t of terminals) {
      const aliases = [t.label, ...(t.aliases || [])].map(norm);
      for (const a of aliases) {
        for (const h of hay) {
          if (h === a || h.includes(a) || a.includes(h)) return t;
        }
      }
    }
    return null;
  }

  /** Deterministic jitter so vessels at same terminal don't fully overlap. */
  function jitterLatLon(baseLat, baseLon, key) {
    let h = 0;
    const s = String(key || "x");
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    const ang = ((h % 360) * Math.PI) / 180;
    const r = 0.0022 + ((h % 17) / 17) * 0.0045; // ~250–750 m
    return [baseLat + Math.sin(ang) * r, baseLon + Math.cos(ang) * r * 1.15];
  }

  function initMap() {
    if (map || typeof L === "undefined") return;
    map = L.map("map", {
      zoomControl: true,
      attributionControl: true,
    }).setView([-33.05, -60.55], 9);

    // Free dark basemap (no API key). Fallback: Esri World Dark Gray Canvas.
    L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      {
        attribution:
          "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
        maxZoom: 16,
      }
    ).addTo(map);

    markerLayer = L.markerClusterGroup({
      showCoverageOnHover: false,
      maxClusterRadius: 42,
      spiderfyOnMaxZoom: true,
    });
    map.addLayer(markerLayer);
    mapReady = true;

    $("mapLegend").innerHTML = [
      "soja|Soja",
      "maiz|Maíz",
      "trigo|Trigo",
      "girasol|Girasol",
      "sorgo|Sorgo",
      "cebada|Cebada",
      "otro|Otros",
    ]
      .map((x) => {
        const [c, l] = x.split("|");
        return chip(c, l);
      })
      .join("");

    setTimeout(() => map.invalidateSize(), 80);
  }

  function renderMap(list) {
    if (!mapReady) initMap();
    if (!map || !markerLayer) return;

    markerLayer.clearLayers();
    const bounds = [];
    let plotted = 0;

    for (const v of list) {
      const term = resolveTerminal(v);
      if (!term) continue;
      const key = `${v.vessel}|${v.terminal}|${v.commodity}|${v.status}`;
      const [lat, lon] = jitterLatLon(term.lat, term.lon, key);
      const colorClass = v.commodity || "otro";
      const icon = L.divIcon({
        className: "",
        html: `<div class="vessel-marker ${colorClass}" title="${escapeHtml(v.vessel)}"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      });

      const timingBits = [
        v.eta ? `<div class="pop-row"><strong>ETA</strong> ${escapeHtml(v.eta)}</div>` : "",
        v.etb ? `<div class="pop-row"><strong>ETB</strong> ${escapeHtml(v.etb)}</div>` : "",
        v.etf ? `<div class="pop-row"><strong>ETF</strong> ${escapeHtml(v.etf)}</div>` : "",
      ].join("");

      const html = `
        <div class="pop-name">${escapeHtml(v.vessel)}</div>
        <div class="pop-row"><strong>Terminal</strong> ${escapeHtml(v.terminal || term.label)}</div>
        <div class="pop-row"><strong>Zona</strong> ${escapeHtml(v.zone || term.label)}</div>
        <div class="pop-row"><strong>Estado</strong> ${escapeHtml(STATUS_LABEL[v.status] || v.status)}</div>
        <div class="pop-row"><strong>Commodity</strong> ${escapeHtml(v.commodity_label || v.commodity || "—")}</div>
        <div class="pop-row"><strong>Toneladas</strong> ${escapeHtml(fmtTonsShort(v.tons))}</div>
        ${timingBits}
      `;

      const m = L.marker([lat, lon], { icon }).bindPopup(html);
      markerLayer.addLayer(m);
      bounds.push([lat, lon]);
      plotted += 1;
    }

    $("mapCount").textContent = String(plotted);

    if (bounds.length) {
      try {
        map.fitBounds(bounds, { padding: [36, 36], maxZoom: 11 });
      } catch {
        /* ignore */
      }
    } else {
      map.setView([-33.05, -60.55], 9);
    }
    setTimeout(() => map.invalidateSize(), 50);
  }

  function renderQueue(list) {
    const waiting = list.filter((v) => v.status !== "arribando");
    $("queueCount").textContent = String(waiting.length);

    const byZone = new Map();
    for (const v of waiting) {
      if (!byZone.has(v.zone)) byZone.set(v.zone, []);
      byZone.get(v.zone).push(v);
    }

    const zones = [...byZone.keys()].sort((a, b) => {
      const ia = ZONE_ORDER.indexOf(a);
      const ib = ZONE_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b, "es");
    });

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
            (v) => `
          <div class="vessel-card">
            <div>
              <div class="v-name">${escapeHtml(v.vessel)}</div>
              <div class="v-term">${escapeHtml(v.terminal || v.port)}</div>
            </div>
            <div class="v-meta">${chip(v.commodity, v.commodity_label)}<div style="margin-top:.35rem">${statusBadge(v.status)}</div></div>
            <div class="v-meta"><div class="tons">${fmtTonsShort(v.tons)}</div><small>${escapeHtml(v.ops || "")}</small></div>
            <div class="v-meta">${escapeHtml(timing(v))}<div style="color:var(--muted);font-size:.75rem;margin-top:.2rem">${escapeHtml(v.destination || "")}</div></div>
          </div>`
          )
          .join("");
        return `<div class="port-block"><div class="port-title"><span>${escapeHtml(zone)}</span><span class="meta">${rows.length} buques · ${fmtTons(tons)}</span></div>${cards}</div>`;
      })
      .join("");
  }

  function renderArrivals(list) {
    const arrivals = list
      .filter((v) => v.status === "arribando")
      .slice()
      .sort((a, b) => String(a.eta).localeCompare(String(b.eta)));
    $("arrivalsCount").textContent = String(arrivals.length);
    if (!arrivals.length) {
      $("arrivalsBody").innerHTML = '<div class="empty">Sin arribos anunciados con estos filtros.</div>';
      return;
    }
    $("arrivalsBody").innerHTML = arrivals
      .map(
        (v) => `
      <div class="vessel-card">
        <div>
          <div class="v-name">${escapeHtml(v.vessel)}</div>
          <div class="v-term">${escapeHtml(v.zone)} · ${escapeHtml(v.terminal || "")}</div>
        </div>
        <div class="v-meta">${chip(v.commodity, v.commodity_label)}<div class="tons" style="margin-top:.35rem">${fmtTonsShort(v.tons)}</div></div>
        <div class="v-meta"><strong>${escapeHtml(v.eta || "ETA")}</strong><div style="color:var(--muted);font-size:.75rem;margin-top:.2rem">${escapeHtml(v.charterer || "")}</div></div>
      </div>`
      )
      .join("");
  }

  function renderKpis(list) {
    const cola = list.filter((v) => v.status !== "arribando");
    const uniqueCola = new Set(cola.map((v) => v.vessel + "|" + v.terminal));
    const tons = list.reduce((s, v) => s + (v.tons || 0), 0);
    $("kpiCola").textContent = fmtNum(uniqueCola.size);
    $("kpiTons").textContent = tons >= 1000 ? fmtNum(Math.round(tons / 1000)) + "k" : fmtNum(tons);
    if (trucksPayload) {
      $("kpiTrucks").textContent = fmtNum(trucksPayload.total_camiones);
    }
    const updated = vesselsPayload?.updated_at || trucksPayload?.updated_at;
    $("kpiUpdated").textContent = toAR(updated);
    const live = vesselsPayload?.live && vesselsPayload?.parse_ok;
    $("liveLabel").textContent = live ? "NABSA en vivo" : "Datos locales / muestra";
    $("kpiSource").textContent = vesselsPayload?.meta?.header || vesselsPayload?.source || "NABSA";
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
        (p) => `
      <div class="bar-row">
        <div class="bar-label">${escapeHtml(p.label)}</div>
        <div class="bar-track"><div class="bar-fill ${p.product}" style="width:${(100 * p.camiones) / max}%"></div></div>
        <div class="bar-val">${fmtNum(p.camiones)}</div>
      </div>`
      )
      .join("");
    $("truckZones").innerHTML = (t.by_zone || [])
      .map(
        (z) => `
      <div class="zone-card">
        <strong>${escapeHtml(z.zone)}</strong>
        <span>${fmtNum(z.camiones)} camiones</span>
      </div>`
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
        ? "Camiones: muestra realista local (MAGyP/BCR sin API estructurada). Actualizar con scripts/refresh_data.py."
        : `Fuente camiones: ${t.source}`;
  }

  function renderAll() {
    const base = upRiverVessels();
    fillZones(base);
    const filtered = applyFilters(base);
    renderKpis(filtered);
    renderQueue(filtered);
    renderArrivals(filtered);
    renderTrucks();
    renderMap(filtered);
  }

  async function load() {
    $("queueBody").innerHTML = '<div class="loading">Cargando lineup…</div>';
    try {
      const [vRes, tRes, termRes] = await Promise.all([
        fetch("/api/vessels"),
        fetch("/api/trucks"),
        fetch("/api/terminals"),
      ]);
      vesselsPayload = await vRes.json();
      trucksPayload = await tRes.json();
      terminalsPayload = termRes.ok ? await termRes.json() : { terminals: [] };
      initMap();
      renderAll();
    } catch (err) {
      console.error(err);
      $("queueBody").innerHTML = `<div class="empty">Error al cargar datos: ${escapeHtml(err.message)}</div>`;
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

  load();
})();
