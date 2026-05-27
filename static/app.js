(function () {
  "use strict";

  // --- Tema chiaro/scuro (attivo su tutte le pagine) ---
  var toggle = document.getElementById("themeToggle");
  if (toggle) {
    var root = document.documentElement;
    function syncLabel() {
      var dark = root.getAttribute("data-theme") === "dark";
      toggle.textContent = dark ? "Tema chiaro" : "Tema scuro";
      toggle.setAttribute(
        "aria-label",
        dark ? "Passa al tema chiaro" : "Passa al tema scuro"
      );
    }
    syncLabel();
    toggle.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try {
        localStorage.setItem("theme", next);
      } catch (e) {}
      syncLabel();
    });
  }
})();

(function () {
  "use strict";

  var search = document.getElementById("search");
  var grid = document.getElementById("cardGrid");
  if (!search || !grid) return;

  var cards = Array.prototype.slice.call(grid.querySelectorAll(".card"));
  var catButtons = Array.prototype.slice.call(
    document.querySelectorAll(".tag-filter")
  );
  var noResults = document.getElementById("noResults");
  var resultCount = document.getElementById("resultCount");

  var query = "";
  var activeCat = "all";

  function apply() {
    var q = query.trim().toLowerCase();
    var filtering = q !== "" || activeCat !== "all";
    var visible = 0;

    cards.forEach(function (card) {
      var blob = card.getAttribute("data-search") || "";
      var cat = card.getAttribute("data-cat") || "";
      var matchQuery = q === "" || blob.indexOf(q) !== -1;
      var matchCat = activeCat === "all" || cat === activeCat;
      var show = matchQuery && matchCat;
      card.hidden = !show;
      if (show) visible++;
    });

    grid.classList.toggle("is-filtering", filtering);

    if (noResults) noResults.hidden = visible !== 0;
    if (resultCount) {
      if (filtering) {
        resultCount.textContent =
          visible === 1 ? "1 notizia trovata" : visible + " notizie trovate";
      } else {
        resultCount.textContent = "";
      }
    }
  }

  search.addEventListener("input", function (e) {
    query = e.target.value;
    apply();
  });

  catButtons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      activeCat = btn.getAttribute("data-cat");
      catButtons.forEach(function (b) {
        b.classList.toggle("is-active", b === btn);
      });
      apply();
    });
  });

  apply();
})();
