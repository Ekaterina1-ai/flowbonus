async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "same-origin",
    ...options,
  });
  let data = {};
  try {
    data = await res.json();
  } catch (_) {
    data = {};
  }
  if (!res.ok) {
    const err = new Error(data.error || `Ошибка сервера (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

const state = {
  partner: null,
  stats: null,
  cities: [],
  selectedCity: "",
  pendingToken: "",
  scanner: null,
  scanning: false,
};

function setSelectedCityUI(city) {
  state.selectedCity = city || "";
  const valueEl = document.getElementById("profile-city-value");
  const hidden = document.getElementById("profile-city");
  if (valueEl) valueEl.textContent = city || "Не выбран";
  if (hidden) hidden.value = city || "";
  document.querySelectorAll("#profile-city-list .city-option").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.city === city);
  });
}

function firstLetter(city) {
  const ch = (city || "").trim().charAt(0).toUpperCase();
  return ch || "#";
}

function renderPartnerCityList(filter = "") {
  const list = document.getElementById("profile-city-list");
  if (!list) return;
  const q = filter.trim().toLowerCase();
  const cities = (state.cities || []).filter((c) => !q || c.toLowerCase().includes(q));
  if (!cities.length) {
    list.innerHTML = `<p class="city-empty">Ничего не найдено. Измените запрос.</p>`;
    return;
  }
  let html = "";
  let last = "";
  cities.forEach((city) => {
    const letter = firstLetter(city);
    if (letter !== last) {
      last = letter;
      html += `<div class="city-option-letter">${letter}</div>`;
    }
    const active = city === state.selectedCity ? " is-active" : "";
    html += `<button type="button" class="city-option${active}" data-city="${city}">${city}</button>`;
  });
  list.innerHTML = html;
}

function ensureCategoryOption(value) {
  const select = document.getElementById("profile-category");
  if (!select || !value) return;
  const exists = [...select.options].some((o) => o.value === value);
  if (!exists) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    select.appendChild(opt);
  }
  select.value = value;
}

function activateTab(name) {
  document.querySelectorAll(".cabinet-tab").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".cabinet-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${name}`);
  });
}

function renderStats(stats) {
  state.stats = stats;
  document.getElementById("stats-coins").textContent = stats.coins_total || 0;
  document.getElementById("stats-ops").textContent = stats.ops_count || 0;
  document.getElementById("stats-coins-2").textContent = stats.coins_total || 0;

  const list = document.getElementById("recent-list");
  const recent = stats.recent || [];
  if (!recent.length) {
    list.innerHTML = `<p class="form-note">Пока нет списаний. Отсканируйте первый QR клиента.</p>`;
    return;
  }
  list.innerHTML = recent
    .map(
      (r) => `
      <div class="recent-item">
        <div>
          <div>${r.client_fio}</div>
          <div class="form-note">${r.client_phone} · ${r.created_at}</div>
        </div>
        <strong>-${r.coins}</strong>
      </div>`
    )
    .join("");
}

function fillProfile(partner) {
  document.getElementById("partner-name").textContent = partner.contact_name;
  document.getElementById("business-title").textContent = partner.business_name;
  document.getElementById("offer-spend-coins").value = partner.spend_coins || 2;
  document.getElementById("profile-business").value = partner.business_name || "";
  ensureCategoryOption(partner.category || "");
  setSelectedCityUI(partner.city || "");
  renderPartnerCityList(document.getElementById("profile-city-search")?.value || "");
  document.getElementById("profile-address").value = partner.address || "";
  document.getElementById("profile-hours").value = partner.hours || "";
  document.getElementById("profile-website").value = partner.website || "";
  document.getElementById("profile-description").value = partner.description || "";
  document.getElementById("profile-comment").value = partner.comment || "";
  renderGallery(partner.images || []);
}

function renderGallery(images) {
  const grid = document.getElementById("gallery-grid");
  if (!images.length) {
    grid.innerHTML = `<p class="form-note">Пока нет фото. Добавьте первое изображение.</p>`;
    return;
  }
  grid.innerHTML = images
    .map(
      (img) => `
      <div class="gallery-item">
        <img src="${img.path}" alt="" />
        <button type="button" data-del-image="${img.id}" aria-label="Удалить">×</button>
      </div>`
    )
    .join("");
}

async function loadMe() {
  const data = await api("/api/partner/me");
  state.partner = data.partner;
  fillProfile(data.partner);
  renderStats(data.stats);
}

async function loadCities() {
  const data = await api("/api/cities");
  state.cities = [...(data.cities || [])].sort((a, b) => a.localeCompare(b, "ru"));
  renderPartnerCityList("");
  setSelectedCityUI(state.selectedCity || state.partner?.city || "");
}

function bindCityPicker() {
  const root = document.getElementById("city-select-search");
  const trigger = document.getElementById("city-select-trigger");
  const panel = document.getElementById("city-select-panel");
  const search = document.getElementById("profile-city-search");
  const list = document.getElementById("profile-city-list");
  if (!root || !trigger || !panel || !search || !list) return;

  const openPanel = () => {
    panel.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    search.value = "";
    renderPartnerCityList("");
    search.focus();
  };

  const closePanel = () => {
    panel.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  };

  trigger.addEventListener("click", () => {
    if (panel.hidden) openPanel();
    else closePanel();
  });

  search.addEventListener("input", () => renderPartnerCityList(search.value));

  list.addEventListener("click", (event) => {
    const btn = event.target.closest(".city-option");
    if (!btn) return;
    setSelectedCityUI(btn.dataset.city);
    closePanel();
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) closePanel();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closePanel();
  });
}

function extractToken(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  if (text.includes("token=")) {
    try {
      const url = new URL(text, window.location.origin);
      return url.searchParams.get("token") || text.split("token=")[1].split("&")[0];
    } catch (_) {
      return text.split("token=")[1].split("&")[0];
    }
  }
  return text;
}

async function prepareRedeem(tokenRaw) {
  const token = extractToken(tokenRaw);
  const status = document.getElementById("scan-status");
  status.textContent = "Проверяем QR…";
  try {
    const data = await api("/api/partner/lookup-token", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
    state.pendingToken = data.spend.token;
    document.getElementById("redeem-fio").textContent = data.spend.client_fio;
    document.getElementById("redeem-phone").textContent = data.spend.client_phone;
    document.getElementById("redeem-balance").textContent = data.spend.client_coins;
    const suggested = Math.min(
      Number(data.suggested_coins || state.partner?.spend_coins || 2),
      Number(data.spend.client_coins || 0) || 1
    );
    document.getElementById("redeem-coins").value = Math.max(1, suggested);
    document.getElementById("redeem-coins").max = Math.max(1, data.spend.client_coins);
    document.getElementById("redeem-card").hidden = false;
    document.getElementById("redeem-status").textContent = "";
    status.textContent = "QR распознан. Подтвердите списание.";
    await stopScanner();
  } catch (err) {
    status.textContent = err.message;
  }
}

async function startScanner() {
  const status = document.getElementById("scan-status");
  const box = document.getElementById("scan-box");
  if (typeof Html5Qrcode === "undefined") {
    status.textContent = "Не удалось загрузить модуль камеры. Проверьте интернет.";
    return;
  }
  if (state.scanning) return;

  box.hidden = false;
  document.getElementById("start-scan-btn").hidden = true;
  document.getElementById("stop-scan-btn").hidden = false;
  status.textContent = "Разрешите доступ к камере…";

  state.scanner = new Html5Qrcode("qr-reader");
  try {
    await state.scanner.start(
      { facingMode: "environment" },
      { fps: 8, qrbox: { width: 240, height: 240 } },
      async (decoded) => {
        if (!state.scanning) return;
        state.scanning = false;
        await prepareRedeem(decoded);
      },
      () => {}
    );
    state.scanning = true;
    status.textContent = "Наведите камеру на QR клиента.";
  } catch (err) {
    status.textContent = "Не удалось включить камеру. Разрешите доступ в браузере.";
    document.getElementById("start-scan-btn").hidden = false;
    document.getElementById("stop-scan-btn").hidden = true;
    box.hidden = true;
  }
}

async function stopScanner() {
  document.getElementById("start-scan-btn").hidden = false;
  document.getElementById("stop-scan-btn").hidden = true;
  document.getElementById("scan-box").hidden = true;
  state.scanning = false;
  if (state.scanner) {
    try {
      await state.scanner.stop();
      await state.scanner.clear();
    } catch (_) {
      /* ignore */
    }
    state.scanner = null;
  }
}

function bindTabs() {
  document.querySelectorAll(".cabinet-tab").forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  });
}

function bindScan() {
  document.getElementById("start-scan-btn").addEventListener("click", startScanner);
  document.getElementById("stop-scan-btn").addEventListener("click", stopScanner);
  document.getElementById("cancel-redeem-btn").addEventListener("click", () => {
    document.getElementById("redeem-card").hidden = true;
    state.pendingToken = "";
  });
  document.getElementById("confirm-redeem-btn").addEventListener("click", async () => {
    const status = document.getElementById("redeem-status");
    status.textContent = "";
    try {
      const data = await api("/api/partner/redeem", {
        method: "POST",
        body: JSON.stringify({
          token: state.pendingToken,
          coins: Number(document.getElementById("redeem-coins").value),
        }),
      });
      status.textContent = `Списано ${data.coins_spent} монет у ${data.client_fio}.`;
      renderStats(data.stats);
      state.pendingToken = "";
      setTimeout(() => {
        document.getElementById("redeem-card").hidden = true;
      }, 1600);
    } catch (err) {
      status.textContent = err.message;
    }
  });
}

function bindForms() {
  document.getElementById("offer-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("offer-status");
    status.textContent = "";
    try {
      const data = await api("/api/partner/profile", {
        method: "POST",
        body: JSON.stringify({
          spend_coins: Number(document.getElementById("offer-spend-coins").value),
          city: state.partner.city,
          address: state.partner.address,
          comment: state.partner.comment,
        }),
      });
      state.partner = data.partner;
      status.textContent = "Условия акции сохранены.";
    } catch (err) {
      status.textContent = err.message;
    }
  });

  document.getElementById("profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("profile-status");
    status.textContent = "";
    try {
      const data = await api("/api/partner/profile", {
        method: "POST",
        body: JSON.stringify({
          business_name: document.getElementById("profile-business").value,
          category: document.getElementById("profile-category").value,
          city: document.getElementById("profile-city").value,
          address: document.getElementById("profile-address").value,
          hours: document.getElementById("profile-hours").value,
          website: document.getElementById("profile-website").value,
          description: document.getElementById("profile-description").value,
          comment: document.getElementById("profile-comment").value,
          spend_coins: state.partner.spend_coins,
        }),
      });
      state.partner = data.partner;
      fillProfile(data.partner);
      status.textContent = "Профиль сохранён. Клиенты увидят обновления в своём кабинете.";
    } catch (err) {
      status.textContent = err.message;
    }
  });

  const galleryInput = document.getElementById("gallery-input");
  galleryInput.addEventListener("change", async () => {
    const file = galleryInput.files?.[0];
    const status = document.getElementById("gallery-status");
    status.textContent = "";
    if (!file) return;
    const body = new FormData();
    body.append("image", file);
    try {
      const res = await fetch("/api/partner/images", {
        method: "POST",
        body,
        credentials: "same-origin",
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Ошибка загрузки");
      state.partner = data.partner;
      fillProfile(data.partner);
      status.textContent = "Фото добавлено.";
    } catch (err) {
      status.textContent = err.message;
    } finally {
      galleryInput.value = "";
    }
  });

  document.getElementById("gallery-grid").addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-del-image]");
    if (!btn) return;
    const status = document.getElementById("gallery-status");
    try {
      const data = await api(`/api/partner/images/${btn.dataset.delImage}`, {
        method: "DELETE",
        body: "{}",
      });
      state.partner = data.partner;
      fillProfile(data.partner);
      status.textContent = "Фото удалено.";
    } catch (err) {
      status.textContent = err.message;
    }
  });
}

function bindLogout() {
  document.getElementById("logout-btn").addEventListener("click", async () => {
    await stopScanner();
    await api("/api/partner/logout", { method: "POST", body: "{}" });
    window.location.href = "/partners.html";
  });
}

async function boot() {
  try {
    await loadMe();
    await loadCities();
    bindTabs();
    bindScan();
    bindForms();
    bindCityPicker();
    bindLogout();

    const params = new URLSearchParams(location.search);
    const scanToken = params.get("scan");
    if (scanToken) {
      activateTab("scan");
      await prepareRedeem(scanToken);
    }
  } catch (err) {
    if (err.status === 401) {
      window.location.href = "/partners.html?login=partner";
      return;
    }
    alert(err.message || "Не удалось открыть кабинет партнёра");
  }
}

boot();
