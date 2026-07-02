(function () {
  "use strict";

  // Centro mappa di fallback: Bergamo.
  var LAT0 = 45.6983, LON0 = 9.6773, ZOOM0 = 9;
  // Raggio approssimativo attorno alla posizione GPS (gradi ~30 km).
  var GPS_ZOOM = 13, GPS_PAD = 0.28;
  var LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
  var LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
  var CLUSTER_CSS = "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css";
  var CLUSTER_CSS_DEF = "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css";
  var CLUSTER_JS = "https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js";

  var OCM_MAX_RESULTS = 2000;      // oltre questa soglia OCM tronca l'elenco
  var OCM_CACHE_TTL = 15 * 60000;  // cache della risposta OCM: 15 minuti

  var allStations = [];      // tutte le stazioni caricate (grezze da OCM)
  var stationIds = {};       // ID gia' presenti in allStations (dedup)
  var stationLayer = null;   // layer dei pin filtrabili
  var activeFilter = "all";  // all | slow | fast | hpc | unknown
  var truncated = false;     // true se l'ultimo fetch OCM era troncato
  var fetchedAreas = [];     // aree gia' scaricate: { bounds, complete }
  var fetchInFlight = false; // un solo fetch OCM alla volta
  var queuedMove = false;    // moveend arrivato durante un fetch
  var theMap = null;

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function gateLocked() {
    return document.documentElement.classList.contains("gate-locked");
  }

  function addStyle(href) {
    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = href;
    document.head.appendChild(css);
  }

  function addScript(src, onload, onerror) {
    var js = document.createElement("script");
    js.src = src;
    js.onload = onload;
    js.onerror = onerror;
    document.head.appendChild(js);
  }

  function loadLeaflet(cb) {
    if (typeof L !== "undefined") { cb(); return; }
    addStyle(LEAFLET_CSS);
    addScript(LEAFLET_JS, cb, function () {
      setStatus("Impossibile caricare la libreria mappa.");
    });
  }

  // Carica il plugin di clustering. Se fallisce, si prosegue senza (fallback).
  function loadCluster(cb) {
    if (typeof L !== "undefined" && L.markerClusterGroup) { cb(); return; }
    addStyle(CLUSTER_CSS);
    addStyle(CLUSTER_CSS_DEF);
    addScript(CLUSTER_JS, cb, function () {
      console.warn("markercluster non caricato: pin senza raggruppamento.");
      cb();
    });
  }

  ready(function () {
    if (!document.getElementById("map")) return;
    setupFilters();
    setupSheet();
    loadLeaflet(function () { loadCluster(initMap); });
  });

  function setStatus(text) {
    var el = document.getElementById("station-status");
    if (el) el.textContent = text;
  }

  function initMap() {
    // Canvas al posto dell'SVG: piu' fluido con migliaia di pin e con
    // "tolerance" il tap aggancia il pin anche a 12px di distanza,
    // senza dover centrare il pallino al pixel.
    var mapOpts = { scrollWheelZoom: true };
    if (L.canvas) mapOpts.renderer = L.canvas({ tolerance: 12 });
    var map = L.map("map", mapOpts).setView([LAT0, LON0], ZOOM0);
    theMap = map;
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19
    }).addTo(map);
    stationLayer = L.markerClusterGroup
      ? L.markerClusterGroup({
          chunkedLoading: true,
          showCoverageOnHover: false,
          maxClusterRadius: 55,
          spiderfyOnMaxZoom: true
        })
      : L.layerGroup();
    map.addLayer(stationLayer);

    if (gateLocked()) {
      var obs = new MutationObserver(function () {
        if (!gateLocked()) {
          map.invalidateSize();
          obs.disconnect();
        }
      });
      obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    }

    locateAndLoad(map);
  }

  function locateAndLoad(map) {
    if (!navigator.geolocation) {
      loadStations(map, null);
      return;
    }
    setStatus("Rilevo la tua posizione…");
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        var lat = pos.coords.latitude;
        var lon = pos.coords.longitude;
        map.setView([lat, lon], GPS_ZOOM);
        L.circleMarker([lat, lon], {
          radius: 9, weight: 2,
          color: "#fff", fillColor: "#1a73e8", fillOpacity: 1
        }).addTo(map).bindTooltip("Sei qui", { permanent: false });
        var acc = pos.coords.accuracy;
        if (acc && acc < 5000) {
          L.circle([lat, lon], {
            radius: acc, weight: 1,
            color: "#1a73e8", fillColor: "#1a73e8", fillOpacity: 0.08
          }).addTo(map);
        }
        loadStations(map, { lat: lat, lon: lon });
      },
      function () {
        loadStations(map, null);
      },
      { timeout: 8000, maximumAge: 60000 }
    );
  }

  function bboxFromBounds(b) {
    return "(" + b.getSouth() + "," + b.getWest() + "),(" + b.getNorth() + "," + b.getEast() + ")";
  }

  function areaOf(b) {
    return (b.getNorth() - b.getSouth()) * (b.getEast() - b.getWest());
  }

  // La vista e' gia' coperta? Un'area scaricata ma troncata (2000+ risultati)
  // copre solo viste di dimensione simile: zoomando dentro si rifetcha per
  // recuperare le colonnine tagliate fuori dal tetto.
  function isCovered(view) {
    for (var i = 0; i < fetchedAreas.length; i++) {
      var f = fetchedAreas[i];
      if (!f.bounds.contains(view)) continue;
      if (f.complete) return true;
      if (areaOf(view) > areaOf(f.bounds) * 0.15) return true;
    }
    return false;
  }

  function mergeStations(items) {
    var added = 0;
    (items || []).forEach(function (s) {
      var info = s.AddressInfo || {};
      var id = s.ID != null ? "id" + s.ID : info.Latitude + "," + info.Longitude;
      if (stationIds[id]) return;
      stationIds[id] = true;
      allStations.push(s);
      added++;
    });
    return added;
  }

  // Cache di sessione della risposta OCM, per bbox. Evita di ripetere la
  // chiamata API a ogni visita nella stessa sessione di navigazione.
  function cacheGet(bbox) {
    try {
      var raw = sessionStorage.getItem("ocm:" + bbox);
      if (!raw) return null;
      var entry = JSON.parse(raw);
      if (!entry || Date.now() - entry.t > OCM_CACHE_TTL) return null;
      return entry.items;
    } catch (e) { return null; }
  }

  function cachePut(bbox, items) {
    try {
      sessionStorage.setItem("ocm:" + bbox, JSON.stringify({ t: Date.now(), items: items }));
    } catch (e) { /* storage pieno o non disponibile: si prosegue senza cache */ }
  }

  function loadStations(map, userPos) {
    var key = window.OCM_KEY || "";
    if (!key) {
      setStatus("Chiave OpenChargeMap non configurata: la mappa funziona ma i pin non possono essere caricati.");
      console.error("OpenChargeMap: OPENCHARGEMAP_API_KEY non impostata al build.");
      return;
    }

    var bounds = userPos
      ? L.latLngBounds([userPos.lat - GPS_PAD, userPos.lon - GPS_PAD],
                       [userPos.lat + GPS_PAD, userPos.lon + GPS_PAD])
      : L.latLngBounds([44.7, 8.5], [46.6, 11.5]);
    window.__ricaricaLabel = userPos ? "nei dintorni" : "in Lombardia";

    fetchArea(bounds);
    // Pan/zoom: scarica le zone inquadrate non ancora coperte.
    map.on("moveend", onMoveEnd);
  }

  function onMoveEnd() {
    if (!theMap) return;
    if (fetchInFlight) { queuedMove = true; return; }
    var view = theMap.getBounds();
    if (isCovered(view)) return;
    window.__ricaricaLabel = "caricate";
    // Margine attorno alla vista: meno richieste durante gli spostamenti brevi.
    fetchArea(view.pad(0.35));
  }

  function fetchArea(bounds) {
    var key = window.OCM_KEY || "";
    if (!key) return;
    var bbox = bboxFromBounds(bounds);

    var cached = cacheGet(bbox);
    if (cached) {
      finishArea(bounds, cached);
      return;
    }

    fetchInFlight = true;
    setStatus("Carico le colonnine " + (window.__ricaricaLabel || "") + "…");

    var url = "https://api.openchargemap.io/v3/poi/?output=json&countrycode=IT"
      + "&boundingbox=" + encodeURIComponent(bbox)
      + "&maxresults=" + OCM_MAX_RESULTS + "&compact=true&verbose=false"
      + "&key=" + encodeURIComponent(key);

    fetch(url)
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (items) {
        items = items || [];
        cachePut(bbox, items);
        finishArea(bounds, items);
      })
      .catch(function (err) {
        fetchInFlight = false;
        queuedMove = false;
        setStatus(err === 403
          ? "OpenChargeMap ha rifiutato la chiave (403). Verifica OPENCHARGEMAP_API_KEY."
          : "Impossibile caricare i dati da OpenChargeMap.");
        console.error("OpenChargeMap:", err);
      });
  }

  function finishArea(bounds, items) {
    fetchInFlight = false;
    truncated = items.length >= OCM_MAX_RESULTS;
    fetchedAreas.push({ bounds: bounds, complete: !truncated });
    mergeStations(items);
    renderMarkers();
    if (queuedMove) {
      queuedMove = false;
      onMoveEnd();
    }
  }

  // --- Potenza e categorie ---------------------------------------------------

  function maxPowerKw(s) {
    var conn = s.Connections || [];
    var max = 0;
    conn.forEach(function (c) { if (c.PowerKW && c.PowerKW > max) max = c.PowerKW; });
    return max; // 0 = sconosciuta
  }

  function powerCategory(kw) {
    if (!kw) return "unknown";
    if (kw <= 22) return "slow";
    if (kw < 150) return "fast";
    return "hpc";
  }

  function matchesFilter(s) {
    if (activeFilter === "all") return true;
    return powerCategory(maxPowerKw(s)) === activeFilter;
  }

  function colorForCategory(cat) {
    if (cat === "slow") return { fill: "#2d8a4e", stroke: "#1f6b3a" }; // verde
    if (cat === "fast") return { fill: "#d59500", stroke: "#a06f00" }; // ambra
    if (cat === "hpc")  return { fill: "#b3001b", stroke: "#7d0013" }; // rosso
    return { fill: "#8b93a1", stroke: "#5f6b7a" };                      // grigio
  }

  // --- Rendering pin ---------------------------------------------------------

  function renderMarkers() {
    if (!stationLayer) return;
    stationLayer.clearLayers();
    var markers = [];
    allStations.forEach(function (s) {
      if (!matchesFilter(s)) return;
      var info = s.AddressInfo || {};
      var lat = info.Latitude, lon = info.Longitude;
      if (typeof lat !== "number" || typeof lon !== "number") return;
      var cat = powerCategory(maxPowerKw(s));
      var col = colorForCategory(cat);
      var m = L.circleMarker([lat, lon], {
        radius: 8, weight: 1.5,
        color: col.stroke, fillColor: col.fill, fillOpacity: 0.85
      });
      m.on("click", function () { showDetails(s); });
      markers.push(m);
    });
    // Inserimento in blocco: addLayers (markercluster) o uno alla volta
    if (stationLayer.addLayers) stationLayer.addLayers(markers);
    else markers.forEach(function (m) { stationLayer.addLayer(m); });
    var shown = markers.length;
    var label = window.__ricaricaLabel || "";
    setStatus(shown + " colonnine " + label
      + (activeFilter === "all" ? "" : " (" + filterName(activeFilter) + ")")
      + ". Tocca un pin per il listino."
      + (truncated ? " Elenco parziale: avvicina la mappa o attiva il GPS per la copertura completa." : ""));
  }

  function filterName(f) {
    return f === "slow" ? "lente" : f === "fast" ? "veloci"
      : f === "hpc" ? "ultrarapide" : f === "unknown" ? "potenza n.d." : "tutte";
  }

  // --- Filtri ----------------------------------------------------------------

  function setupFilters() {
    var bar = document.getElementById("ricarica-filters");
    if (!bar) return;
    bar.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest(".rfilter") : null;
      if (!btn) return;
      activeFilter = btn.getAttribute("data-filter") || "all";
      var all = bar.querySelectorAll(".rfilter");
      for (var i = 0; i < all.length; i++) all[i].classList.remove("is-active");
      btn.classList.add("is-active");
      renderMarkers();
    });
  }

  // --- Bottom sheet (mobile) -------------------------------------------------

  function closeSheet() {
    document.documentElement.classList.remove("station-open");
  }

  function setupSheet() {
    var closeBtn = document.getElementById("station-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeSheet();
      });
    }
    // Tasto Esc chiude il bottom sheet
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && document.documentElement.classList.contains("station-open")) {
        closeSheet();
      }
    });
  }

  function openSheet() {
    document.documentElement.classList.add("station-open");
  }

  // --- Dettaglio colonnina ---------------------------------------------------

  function isUnknownOperator(op) {
    if (!op) return true;
    // Nomi interamente tra parentesi (es. "(Unknown Operator)") o segnaposto.
    // Un suffisso tra parentesi (es. "Enel X (Italia)") è invece un nome valido.
    return /unknown|sconosciut|^\(.*\)$/i.test(op);
  }

  function showDetails(s) {
    var panel = document.getElementById("station-details");
    if (!panel) return;
    var info = s.AddressInfo || {};
    var op = (s.OperatorInfo && s.OperatorInfo.Title) || null;
    var opDeduced = false;
    if (isUnknownOperator(op)) {
      var guessed = guessOperatorFromText(info.Title);
      if (guessed) { op = guessed; opDeduced = true; }
      else op = null;
    }
    var conn = s.Connections || [];
    var kw = maxPowerKw(s);
    var cat = powerCategory(kw);

    var parts = [];
    parts.push('<h3 class="station-title">' + esc(info.Title || "Colonnina di ricarica") + "</h3>");
    var addr = [info.AddressLine1, info.Town, info.Postcode].filter(Boolean).join(" · ");
    if (addr) parts.push('<p class="station-address">' + esc(addr) + "</p>");

    // Riga badge: potenza + tipo + connettori
    var badges = [];
    badges.push('<span class="badge badge-' + cat + '">' + (kw ? kw + " kW" : "potenza n.d.") + "</span>");
    badges.push('<span class="badge badge-neutral">' + catLabel(cat) + "</span>");
    if (conn.length) badges.push('<span class="badge badge-neutral">' + conn.length + " connettori</span>");
    parts.push('<div class="station-badges">' + badges.join("") + "</div>");

    var opLabel = op ? esc(op) + (opDeduced ? ' <span class="station-hint">(dedotto dal nome)</span>' : "") : "Sconosciuto";
    parts.push('<p class="station-row"><span class="station-label">Operatore:</span> ' + opLabel + "</p>");

    // Costo dichiarato per questa stazione su OpenChargeMap (testo libero).
    // Sempre esposto, anche quando in archivio c'e' il listino del gestore:
    // sono due fonti indipendenti e il lettore le vede entrambe.
    var usageCost = (s.UsageCost || "").trim();
    parts.push('<p class="station-row"><span class="station-label">Costo segnalato su OpenChargeMap:</span> '
      + (usageCost
          ? esc(usageCost)
          : '<span class="station-hint">non indicato dalla stazione</span>')
      + "</p>");

    var t = lookupTariff(op);
    if (t) {
      parts.push(renderTariff(t));
    } else if (op) {
      parts.push('<p class="station-no-tariff">Listino non disponibile in archivio per <em>'
        + esc(op) + "</em>. Verifica sul sito o sull'app ufficiale.</p>");
    } else {
      parts.push('<p class="station-no-tariff">Operatore non identificato per questa colonnina.</p>');
    }

    var T = window.TARIFFE || {};
    parts.push('<p class="station-disclaimer">'
      + 'Prezzi indicativi aggiornati al ' + esc(T.ultimo_aggiornamento || "—") + '. '
      + 'Solo la tariffa diretta dell\'app del proprietario. '
      + 'In roaming con un altro operatore il prezzo sarà diverso.'
      + '</p>');

    panel.innerHTML = parts.join("");
    openSheet();
  }

  function catLabel(cat) {
    return cat === "slow" ? "Lenta (AC)"
      : cat === "fast" ? "Veloce (DC)"
      : cat === "hpc" ? "Ultrarapida (HPC)"
      : "Tipo n.d.";
  }

  // --- Match operatore -------------------------------------------------------

  function guessOperatorFromText(text) {
    if (!text) return null;
    var T = window.TARIFFE;
    if (!T || !T.gestori) return null;
    var normd = norm(text);
    var hay = " " + normd + " ";
    var words = normd.split(" ");
    for (var i = 0; i < T.gestori.length; i++) {
      var g = T.gestori[i];
      // 1) match per parola intera su nome/alias
      var candidates = [g.nome].concat(g.alias || []);
      for (var j = 0; j < candidates.length; j++) {
        var c = norm(candidates[j]);
        if (c.length < 2) continue;
        if (hay.indexOf(" " + c + " ") !== -1) return g.nome;
      }
      // 2) match per prefisso (es. "enel" -> Eneldrive, EnelX, Enel Energia)
      if (g.prefixes) {
        for (var p = 0; p < g.prefixes.length; p++) {
          var pre = norm(g.prefixes[p]);
          if (pre.length < 3) continue;
          for (var w = 0; w < words.length; w++) {
            if (words[w].indexOf(pre) === 0) return g.nome;
          }
        }
      }
    }
    return null;
  }

  function lookupTariff(opName) {
    if (!opName) return null;
    var T = window.TARIFFE;
    if (!T || !T.gestori) return null;
    var n = norm(opName);
    var first = n.split(" ")[0];
    for (var i = 0; i < T.gestori.length; i++) {
      var g = T.gestori[i];
      if (norm(g.nome) === n) return g;
      if (g.alias) {
        for (var j = 0; j < g.alias.length; j++) {
          if (norm(g.alias[j]) === n) return g;
        }
      }
    }
    for (var k = 0; k < T.gestori.length; k++) {
      var g2 = T.gestori[k];
      var key = norm(g2.nome).split(" ")[0];
      if (first && key && first === key) return g2;
    }
    return null;
  }

  function renderTariff(t) {
    var tariffe = t.tariffe || [];
    var rows = tariffe.map(function (r) {
      return "<tr><td>" + esc(r.tipo) + "</td><td>" + esc(r.prezzo) + "</td></tr>";
    }).join("");
    var out = '<h4 class="tariff-title">Listino · ' + esc(t.nome) + "</h4>";
    // Gestore senza listino diretto (es. servizio dismesso): solo nota e link.
    if (rows) out += '<table class="tariff-table"><tbody>' + rows + "</tbody></table>";
    if (t.verificato_il) {
      out += '<p class="tariff-note">Verificato il ' + esc(t.verificato_il) + '.</p>';
    }
    if (t.note) out += '<p class="tariff-note">' + esc(t.note) + "</p>";
    if (t.sito) out += '<p class="tariff-link"><a href="' + esc(t.sito)
      + '" target="_blank" rel="noopener">Sito ufficiale &rarr;</a></p>';
    return out;
  }

  function norm(s) {
    return String(s).toLowerCase()
      .normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, " ").trim();
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();
