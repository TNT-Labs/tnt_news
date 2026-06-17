(function () {
  "use strict";

  // Centro mappa: Bergamo. BBox: Lombardia (sud-ovest, nord-est).
  var LAT0 = 45.6983, LON0 = 9.6773, ZOOM0 = 9;
  var BBOX = "(44.7,8.5),(46.6,11.5)";
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

    // Il gate password nasconde il body finche non si sblocca: in quel caso
    // il container ha dimensioni zero e Leaflet non disegna. Quando il gate
    // viene rimosso, ricalcoliamo le dimensioni.
    if (gateLocked()) {
      var obs = new MutationObserver(function () {
        if (!gateLocked()) {
          map.invalidateSize();
          obs.disconnect();
        }
      });
      obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    }

    loadStations(map);
  }

  function loadStations(map) {
    var status = document.getElementById("station-status");
    var key = window.OCM_KEY || "";
    if (!key) {
      if (status) {
        status.textContent = "Chiave OpenChargeMap non configurata: la mappa funziona ma i pin non possono essere caricati.";
      }
      console.error("OpenChargeMap: variabile d'ambiente OPENCHARGEMAP_API_KEY non impostata al build.");
      return;
    }
    if (status) status.textContent = "Carico le colonnine in Lombardia…";

    var url = "https://api.openchargemap.io/v3/poi/?output=json&countrycode=IT"
      + "&boundingbox=" + encodeURIComponent(BBOX)
      + "&maxresults=2000&compact=true&verbose=false"
      + "&key=" + encodeURIComponent(key);

    fetch(url)
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
      .then(function (items) {
        addMarkers(map, items);
        if (status) {
          status.textContent = items.length + " colonnine in Lombardia. Tocca un pin per il listino dell'operatore.";
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
    var conn = s.Connections || [];

    var parts = [];
    parts.push('<h3 class="station-title">' + esc(info.Title || "Colonnina di ricarica") + "</h3>");
    var addr = [info.AddressLine1, info.Town, info.Postcode].filter(Boolean).join(" · ");
    if (addr) parts.push('<p class="station-address">' + esc(addr) + "</p>");

    parts.push('<p class="station-row"><span class="station-label">Operatore:</span> ' + esc(op || "Sconosciuto") + "</p>");

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
