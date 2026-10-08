/* Seoul Day Trips — vanilla JS front end. Data comes from data/*.json (built by scripts/fetch.py). */
(function () {
  "use strict";

  const LANGS = ["en", "ja"];
  const CATEGORIES = ["attraction", "culture", "leisure", "food", "festival"];
  const REGIONS = ["gyeonggi", "incheon"];
  const COLORS = { attraction: "#1f6feb", culture: "#8250df", leisure: "#1a7f37", food: "#d1242f", festival: "#bf8700" };
  const PAGE = 24;

  const $ = (sel) => document.querySelector(sel);
  const state = {
    lang: pickLang(),
    data: {},          // lang -> {places, festivals, updated}
    photos: [],
    region: "all",
    category: "all",
    city: "",
    query: "",
    shown: PAGE,
    festivalRegion: "all",
    photoRegion: "all",
  };

  function pickLang() {
    const fromUrl = new URLSearchParams(location.search).get("lang");
    if (LANGS.includes(fromUrl)) return fromUrl;
    try {
      const saved = localStorage.getItem("lang");
      if (LANGS.includes(saved)) return saved;
    } catch (e) { /* storage unavailable */ }
    const browser = (navigator.languages || [navigator.language || "en"]).map((l) => String(l).toLowerCase());
    return browser.some((l) => l.startsWith("ja")) ? "ja" : "en";
  }

  const t = (key) => (I18N[state.lang] && I18N[state.lang][key]) || I18N.en[key] || key;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function todayKST() {
    // YYYYMMDD in Asia/Seoul, regardless of the visitor's time zone.
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(new Date());
    const get = (type) => parts.find((p) => p.type === type).value;
    return get("year") + get("month") + get("day");
  }

  function fmtDate(ymd) {
    if (!/^\d{8}$/.test(ymd || "")) return "";
    const d = new Date(Date.UTC(+ymd.slice(0, 4), +ymd.slice(4, 6) - 1, +ymd.slice(6, 8)));
    return d.toLocaleDateString(state.lang === "ja" ? "ja-JP" : "en-US", { timeZone: "UTC", year: "numeric", month: "short", day: "numeric" });
  }

  // ------------------------------------------------------------ data

  async function loadJSON(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(path + " " + res.status);
    return res.json();
  }

  async function ensureLang(lang) {
    if (!state.data[lang]) {
      try { state.data[lang] = await loadJSON("data/" + lang + ".json"); }
      catch (e) { state.data[lang] = { places: [], festivals: [], error: true }; }
    }
    return state.data[lang];
  }

  // ------------------------------------------------------------ map

  let map, cluster;
  const markers = new Map();

  function initMap() {
    if (!window.L) return;
    map = L.map("map", { scrollWheelZoom: false, tap: true }).setView([37.45, 126.95], 9);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    cluster = L.markerClusterGroup ? L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45 }) : L.layerGroup();
    map.addLayer(cluster);
    // Seoul reference marker
    L.circleMarker([37.5665, 126.978], { radius: 7, color: "#111", weight: 2, fillColor: "#fff", fillOpacity: 1 })
      .bindTooltip("Seoul", { permanent: true, direction: "right", className: "seoul-label" }).addTo(map);
  }

  function popupHtml(p) {
    const img = p.thumb ? '<img src="' + esc(p.thumb) + '" alt="" loading="lazy">' : "";
    const dates = p.start ? '<div class="pop-dates">' + esc(fmtDate(p.start)) + " – " + esc(fmtDate(p.end)) + "</div>" : "";
    return '<div class="pop">' + img + "<strong>" + esc(p.title) + "</strong>" + dates +
      '<div class="pop-meta">' + esc(t("cat." + p.category)) + (p.city ? " · " + esc(p.city) : "") + "</div>" +
      '<a href="' + dirUrl(p) + '" target="_blank" rel="noopener">' + esc(t("card.directions")) + " ↗</a></div>";
  }

  function dirUrl(p) {
    return "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(p.lat + "," + p.lng);
  }

  function renderMarkers(list) {
    if (!map) return;
    cluster.clearLayers();
    markers.clear();
    const layers = [];
    list.forEach((p) => {
      if (p.lat == null || p.lng == null) return;
      const m = L.circleMarker([p.lat, p.lng], {
        radius: 7, weight: 2, color: "#fff", fillColor: COLORS[p.category] || "#555", fillOpacity: 0.95,
      }).bindPopup(() => popupHtml(p), { maxWidth: 240 });
      markers.set(p.category + ":" + p.id, m);
      layers.push(m);
    });
    if (cluster.addLayers) cluster.addLayers(layers); else layers.forEach((l) => cluster.addLayer(l));
  }

  function focusPlace(p) {
    const m = markers.get(p.category + ":" + p.id);
    if (!m || !map) return;
    $("#map").scrollIntoView({ behavior: "smooth", block: "center" });
    const open = () => { m.openPopup(); };
    if (cluster.zoomToShowLayer) cluster.zoomToShowLayer(m, open);
    else { map.setView(m.getLatLng(), 14); open(); }
  }

  // ------------------------------------------------------------ explore

  function allItems() {
    const d = state.data[state.lang] || {};
    return (d.places || []).concat(d.festivals || []);
  }

  function filtered() {
    const q = state.query.trim().toLowerCase();
    return allItems().filter((p) =>
      (state.region === "all" || p.region === state.region) &&
      (state.category === "all" || p.category === state.category) &&
      (!state.city || p.city === state.city) &&
      (!q || (p.title + " " + (p.title_ko || "") + " " + (p.addr || "") + " " + (p.city || "")).toLowerCase().includes(q)));
  }

  function chips(el, values, current, labelFn, onPick) {
    el.innerHTML = values.map((v) =>
      '<button type="button" class="chip' + (v === current ? " on" : "") + '" data-v="' + esc(v) + '" aria-pressed="' + (v === current) + '">' +
      (COLORS[v] ? '<i style="background:' + COLORS[v] + '"></i>' : "") + esc(labelFn(v)) + "</button>").join("");
    el.onclick = (e) => {
      const b = e.target.closest("button[data-v]");
      if (b) onPick(b.dataset.v);
    };
  }

  function renderFilters() {
    chips($("#region-chips"), ["all"].concat(REGIONS), state.region, (v) => t("region." + v), (v) => {
      state.region = v; state.city = ""; state.shown = PAGE; renderExplore();
    });
    chips($("#category-chips"), ["all"].concat(CATEGORIES), state.category, (v) => t("cat." + v), (v) => {
      state.category = v; state.shown = PAGE; renderExplore();
    });
    const cities = Array.from(new Set(allItems()
      .filter((p) => p.city && (state.region === "all" || p.region === state.region))
      .map((p) => p.city))).sort((a, b) => a.localeCompare(b, state.lang));
    if (state.city && !cities.includes(state.city)) state.city = "";
    $("#city").innerHTML = '<option value="">' + esc(t("explore.allCities")) + "</option>" +
      cities.map((c) => '<option' + (c === state.city ? " selected" : "") + ">" + esc(c) + "</option>").join("");
    $("#city").hidden = cities.length === 0;
  }

  function card(p) {
    const img = p.thumb
      ? '<img src="' + esc(p.thumb) + '" alt="" loading="lazy" decoding="async">'
      : '<div class="noimg" style="background:' + (COLORS[p.category] || "#999") + '22"></div>';
    const dates = p.start ? '<p class="dates">' + esc(fmtDate(p.start)) + " – " + esc(fmtDate(p.end)) + "</p>" : "";
    const meta = [t("region." + p.region), p.city].filter(Boolean).join(" · ");
    return '<article class="card" data-key="' + esc(p.category + ":" + p.id) + '">' + img +
      '<div class="body"><span class="tag" style="--c:' + (COLORS[p.category] || "#555") + '">' + esc(t("cat." + p.category)) + "</span>" +
      "<h3" + (p.ko ? ' lang="ko"' : "") + ">" + esc(p.title) + "</h3>" + dates +
      '<p class="meta">' + esc(meta) + "</p>" +
      (p.addr ? '<p class="addr">' + esc(p.addr) + "</p>" : "") +
      (p.supplement ? '<p class="note">' + esc(t("card.supplement")) + "</p>" : "") +
      (p.title_ko ? '<p class="orig" lang="ko">' + esc(p.title_ko) + "</p>" : "") +
      (p.ko ? '<p class="note">' + esc(t("festivals.ko")) + "</p>" : "") +
      '<div class="actions">' +
      (p.lat != null ? '<button type="button" class="link" data-act="map">' + esc(t("card.map")) + "</button>" +
        '<a href="' + dirUrl(p) + '" target="_blank" rel="noopener">' + esc(t("card.directions")) + " ↗</a>" : "") +
      "</div></div></article>";
  }

  function renderExplore() {
    renderFilters();
    const list = filtered().sort((a, b) => (!!b.thumb - !!a.thumb) || a.title.localeCompare(b.title, state.lang));
    $("#count").textContent = t("explore.count").replace("{n}", list.length);
    renderMarkers(list);
    const d = state.data[state.lang] || {};
    const cards = $("#cards");
    if (d.error) cards.innerHTML = '<p class="empty">' + esc(t("loadError")) + "</p>";
    else if (!list.length) cards.innerHTML = '<p class="empty">' + esc(t("explore.empty")) + "</p>";
    else cards.innerHTML = list.slice(0, state.shown).map(card).join("");
    $("#more").hidden = list.length <= state.shown;
    cards.onclick = (e) => {
      const btn = e.target.closest("[data-act=map]");
      if (!btn) return;
      const key = btn.closest(".card").dataset.key;
      const p = list.find((x) => x.category + ":" + x.id === key);
      if (p) focusPlace(p);
    };
  }

  // ------------------------------------------------------------ festivals

  function renderFestivals() {
    chips($("#festival-chips"), ["all"].concat(REGIONS), state.festivalRegion, (v) => t("region." + v), (v) => {
      state.festivalRegion = v; renderFestivals();
    });
    const today = todayKST();
    const list = ((state.data[state.lang] || {}).festivals || [])
      .filter((f) => f.end >= today && (state.festivalRegion === "all" || f.region === state.festivalRegion))
      .sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end));
    const box = $("#festival-list");
    if (!list.length) { box.innerHTML = '<p class="empty">' + esc(t("festivals.empty")) + "</p>"; return; }
    let month = "";
    const koNote = list.some((f) => f.ko) ? '<p class="muted ko-note">' + esc(t("festivals.koNote")) + "</p>" : "";
    box.innerHTML = koNote + list.map((f) => {
      const startKey = f.start < today ? today : f.start;
      const m = startKey.slice(0, 6);
      let head = "";
      if (m !== month) {
        month = m;
        const label = new Date(Date.UTC(+m.slice(0, 4), +m.slice(4, 6) - 1, 1))
          .toLocaleDateString(state.lang === "ja" ? "ja-JP" : "en-US", { timeZone: "UTC", year: "numeric", month: "long" });
        head = '<h3 class="month">' + esc(label) + "</h3>";
      }
      const ongoing = f.start <= today;
      return head + '<article class="fest">' +
        (f.thumb ? '<img src="' + esc(f.thumb) + '" alt="" loading="lazy">' : '<div class="noimg"></div>') +
        '<div class="body">' +
        (ongoing ? '<span class="badge">' + esc(t("festivals.ongoing")) + "</span>" : "") +
        "<h4" + (f.ko ? ' lang="ko"' : "") + ">" + esc(f.title) + "</h4>" +
        (f.title_ko ? '<p class="orig" lang="ko">' + esc(f.title_ko) + "</p>" : "") +
        (f.ko ? '<p class="note">' + esc(t("festivals.ko")) + "</p>" : "") +
        '<p class="dates">' + esc(fmtDate(f.start)) + " – " + esc(fmtDate(f.end)) + "</p>" +
        '<p class="meta">' + esc([t("region." + f.region), f.city].filter(Boolean).join(" · ")) + "</p>" +
        (f.overview ? "<details><summary>" + esc(t("festivals.more")) + "</summary><p>" + esc(f.overview) + "</p></details>" : "") +
        '<div class="actions">' +
        (f.homepage ? '<a href="' + esc(f.homepage) + '" target="_blank" rel="noopener">' + esc(t("festivals.website")) + " ↗</a>" : "") +
        (f.lat != null ? '<a href="' + dirUrl(f) + '" target="_blank" rel="noopener">' + esc(t("card.directions")) + " ↗</a>" : "") +
        "</div></div></article>";
    }).join("");
  }

  // ------------------------------------------------------------ gallery

  function renderGallery() {
    chips($("#photo-chips"), ["all"].concat(REGIONS), state.photoRegion, (v) => t("region." + v), (v) => {
      state.photoRegion = v; renderGallery();
    });
    const list = state.photos.filter((p) => state.photoRegion === "all" || p.region === state.photoRegion);
    const grid = $("#photo-grid");
    if (!list.length) { grid.innerHTML = '<p class="empty">' + esc(t("gallery.empty")) + "</p>"; return; }
    grid.innerHTML = list.map((p, i) =>
      '<button type="button" class="photo" data-i="' + i + '"><img src="' + esc(p.img) + '" alt="' + esc(p.label[state.lang] || p.label.en) + '" loading="lazy" decoding="async">' +
      "<span>" + esc(p.label[state.lang] || p.label.en) + "</span></button>").join("");
    grid.onclick = (e) => {
      const b = e.target.closest(".photo");
      if (!b) return;
      const p = list[+b.dataset.i];
      const dlg = $("#lightbox");
      dlg.querySelector("img").src = p.img;
      dlg.querySelector("img").alt = p.label[state.lang] || p.label.en;
      const when = /^\d{6}$/.test(p.month) ? p.month.slice(0, 4) + "." + p.month.slice(4) : "";
      dlg.querySelector(".caption").textContent = [p.label[state.lang] || p.label.en, when,
        p.photographer ? t("gallery.by") + ": " + p.photographer : "", "© Korea Tourism Organization"].filter(Boolean).join(" · ");
      if (dlg.showModal) dlg.showModal(); else window.open(p.img, "_blank", "noopener");
    };
  }

  // ------------------------------------------------------------ access guide

  function renderAccess() {
    const a = t("access");
    $("#access-tips").innerHTML = a.tips.map((x) => '<div class="tip"><h3>' + esc(x[0]) + "</h3><p>" + esc(x[1]) + "</p></div>").join("");
    $("#access-list").innerHTML = a.routes.map((r) =>
      '<details class="route"><summary><span class="rname">' + esc(r.name) + '</span><span class="rmeta">' +
      esc(t("region." + r.region)) + " · " + esc(r.time) + "</span></summary><p>" + esc(r.how) + "</p></details>").join("");
  }

  // ------------------------------------------------------------ chrome

  function applyStatic() {
    document.documentElement.lang = state.lang;
    document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === state.lang));
    const d = state.data[state.lang] || {};
    $("#updated").textContent = d.updated ? t("updated") + ": " + d.updated.slice(0, 10) : "";
  }

  async function setLang(lang) {
    state.lang = lang;
    try { localStorage.setItem("lang", lang); } catch (e) { /* ignore */ }
    const url = new URL(location.href);
    url.searchParams.set("lang", lang);
    history.replaceState(null, "", url);
    await ensureLang(lang);
    state.city = "";
    state.shown = PAGE;
    applyStatic();
    renderExplore();
    renderFestivals();
    renderGallery();
    renderAccess();
  }

  function bind() {
    document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
    $("#city").addEventListener("change", (e) => { state.city = e.target.value; state.shown = PAGE; renderExplore(); });
    let timer;
    $("#search").addEventListener("input", (e) => {
      clearTimeout(timer);
      timer = setTimeout(() => { state.query = e.target.value; state.shown = PAGE; renderExplore(); }, 200);
    });
    $("#more").addEventListener("click", () => { state.shown += PAGE; renderExplore(); });
    const dlg = $("#lightbox");
    dlg.querySelector(".close").addEventListener("click", () => dlg.close());
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  }

  async function start() {
    bind();
    initMap();
    $("#cards").innerHTML = '<p class="empty">' + esc(t("loading")) + "</p>";
    loadJSON("data/photos.json").then((d) => { state.photos = d.photos || []; renderGallery(); }).catch(() => renderGallery());
    await setLang(state.lang);
  }

  start();
})();
