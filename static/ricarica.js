(function () {
  "use strict";

  // Centro mappa di fallback: Bergamo.
  var LAT0 = 45.6983, LON0 = 9.6773, ZOOM0 = 9;
  // Raggio approssimativo attorno alla posizione GPS (gradi ~30 km).
  var GPS_ZOOM = 13, GPS_PAD = 0.28;
  var LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
  var LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function gateLocked() {
    return document.documentElement.classList.contains("gate-locked");
  }

  function loadLeaflet(cb) {
    if (typeof L !== "undefined") { cb(); return; }
    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = LEAFLET_CSS;
    document.head.appendChild(css);
    var js = document.createElement("script");
    js.src = LEAFLET_JS;
    js.onload = cb;
    js.onerror = function () {
      var status = document.getElementById("station-status");
      if (status) status.textContent = "Impossibile caricare la libreria mappa.";
    };
    document.head.appendChild(js);
  }

  ready(function () {
    if (!document.getElementById("map")) return;
    loadLeaflet(initMap);
  });

  function initMap() {
    var map = L.map("map", { scrollWheelZoom: true }).setView([LAT0, LON0], ZOOM0);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19
    }).addTo(map);

    if (gateLocked()) {
      var obs = new MutationObserver(function () {
        if (!gateLocked()) {
          map.invalidateSize();
          obs.disconnect();
        }
      });
      obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    }

    // Geolocalizzazione prima, poi carica le colonnine attorno alla posizione.
    locateAndLoad(map);
  }

  function locateAndLoad(map) {
    var status = document.getElementById("station-status");
    if (!navigator.geolocation) {
      loadStations(map, null);
      return;
    }
    if (status) status.textContent = "Rilevo la tua posizione…";
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
        // Carica le colonnine in un riquadro attorno alla posizione GPS.
        loadStations(map, { lat: lat, lon: lon });
      },
      function () {
        // Permesso negato o timeout: fallback su Bergamo/Lombardia.
        loadStations(map, null);
      },
      { timeout: 8000, maximumAge: 60000 }
    );
  }

  function bboxFromPoint(lat, lon, pad) {
    return "(" + (lat - pad) + "," + (lon - pad) + "),(" + (lat + pad) + "," + (lon + pad) + ")";
  }

  function loadStations(map, userPos) {
    var status = document.getElementById("station-status");
    var key = window.OCM_KEY || "";
    if (!key) {
      if (status) status.textContent = "Chiave OpenChargeMap non configurata: la mappa funziona ma i pin non possono essere caricati.";
      console.error("OpenChargeMap: variabile d'ambiente OPENCHARGEMAP_API_KEY non impostata al build.");
      return;
    }

    var bbox = userPos
      ? bboxFromPoint(userPos.lat, userPos.lon, GPS_PAD)
      : "(44.7,8.5),(46.6,11.5)"; // Lombardia intera come fallback
    var label = userPos ? "nei dintorni" : "in Lombardia";
    if (status) status.textContent = "Carico le colonnine " + label + "…";

    var url = "https://api.openchargemap.io/v3/poi/?output=json&countrycode=IT"
      + "&boundingbox=" + encodeURIComponent(bbox)
      + "&maxresults=2000&compact=true&verbose=false"
      + "&key=" + encodeURIComponent(key);

    fetch(url)
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (items) {
        addMarkers(map, items);
        if (status) {
          status.textContent = items.length + " colonnine " + label + ". Tocca un pin per il listino dell'operatore.";
        }
      })
      .catch(function (err) {
        if (status) {
          status.textContent = err === 403
            ? "OpenChargeMap ha rifiutato la chiave (403). Verifica OPENCHARGEMAP_API_KEY."
            : "Impossibile caricare i dati da OpenChargeMap.";
        }
        console.error("OpenChargeMap:", err);
      });
  }

  function addMarkers(map, items) {
    var layer = L.layerGroup().addTo(map);
    items.forEach(function (s) {
      var info = s.AddressInfo || {};
      var lat = info.Latitude, lon = info.Longitude;
      if (typeof lat !== "number" || typeof lon !== "number") return;
      var m = L.circleMarker([lat, lon], {
        radius: 6,
        weight: 1,
        color: "#7d0013",
        fillColor: "#b3001b",
        fillOpacity: 0.85
      }).addTo(layer);
      m.on("click", function () { showDetails(s); });
    });
  }

  function showDetails(s) {
    var panel = document.getElementById("station-details");
    if (!panel) return;
    var info = s.AddressInfo || {};
    var op = (s.OperatorInfo && s.OperatorInfo.Title) || null;
    var opDeduced = false;
    // Se l'operatore strutturato manca, prova a dedurlo cercando un nome/alias
    // di gestore noto dentro il titolo della stazione (es. "A2A BG Quasimodo").
    if (!op && info.Title) {
      var guessed = guessOperatorFromText(info.Title);
      if (guessed) { op = guessed; opDeduced = true; }
    }
    var conn = s.Connections || [];

    var parts = [];
    parts.push('<h3 class="station-title">' + esc(info.Title || "Colonnina di ricarica") + "</h3>");
    var addr = [info.AddressLine1, info.Town, info.Postcode].filter(Boolean).join(" · ");
    if (addr) parts.push('<p class="station-address">' + esc(addr) + "</p>");

    var opLabel = op ? esc(op) + (opDeduced ? ' <span class="station-hint">(dedotto dal nome)</span>' : "") : "Sconosciuto";
    parts.push('<p class="station-row"><span class="station-label">Operatore:</span> ' + opLabel + "</p>");

    if (conn.length) {
      var maxKw = 0;
      conn.forEach(function (c) { if (c.PowerKW && c.PowerKW > maxKw) maxKw = c.PowerKW; });
      parts.push('<p class="station-row"><span class="station-label">Potenza max:</span> '
        + (maxKw || "n.d.") + " kW · " + conn.length + " connettori</p>");
    }

    var t = lookupTariff(op);
    if (t) {
      parts.push(renderTariff(t));
    } else if (op) {
      parts.push('<p class="station-no-tariff">Listino non disponibile in archivio per <em>'
        + esc(op) + "</em>. Verifica sul sito ufficiale dell'operatore.</p>");
    }

    var T = window.TARIFFE || {};
    parts.push('<p class="station-disclaimer">'
      + 'Tariffe indicative aggiornate al ' + esc(T.ultimo_aggiornamento || "—") + '. '
      + 'Solo il listino diretto del proprietario della colonnina. '
      + 'Se ricarichi via app di un altro operatore (roaming) il prezzo sarà diverso.'
      + '</p>');

    panel.innerHTML = parts.join("");
  }

  function guessOperatorFromText(text) {
    if (!text) return null;
    var T = window.TARIFFE;
    if (!T || !T.gestori) return null;
    var hay = " " + norm(text) + " ";
    for (var i = 0; i < T.gestori.length; i++) {
      var g = T.gestori[i];
      var candidates = [g.nome].concat(g.alias || []);
      for (var j = 0; j < candidates.length; j++) {
        var c = norm(candidates[j]);
        if (c.length < 2) continue;
        if (hay.indexOf(" " + c + " ") !== -1) return g.nome;
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
    // Match parziale sul primo token (es. "Enel X Way S.r.l." -> "enel")
    for (var k = 0; k < T.gestori.length; k++) {
      var g2 = T.gestori[k];
      var key = norm(g2.nome).split(" ")[0];
      if (first && key && (first === key)) return g2;
    }
    return null;
  }

  function renderTariff(t) {
    var rows = t.tariffe.map(function (r) {
      return "<tr><td>" + esc(r.tipo) + "</td><td>" + esc(r.prezzo) + "</td></tr>";
    }).join("");
    var out = '<h4 class="tariff-title">Listino occasionali · ' + esc(t.nome) + "</h4>";
    out += '<table class="tariff-table"><tbody>' + rows + "</tbody></table>";
    if (t.note) out += '<p class="tariff-note">' + esc(t.note) + "</p>";
    if (t.sito) out += '<p class="tariff-link"><a href="' + esc(t.sito)
      + '" target="_blank" rel="noopener">Listino ufficiale &rarr;</a></p>';
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
