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

function formatPhone(phone) {
  const d = String(phone || "");
  if (d.length === 11) {
    return `+${d[0]} (${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9)}`;
  }
  return phone;
}

const state = {
  client: null,
  cities: [],
  selectedCity: "",
  coinPrice: 100,
  coinTiers: [
    { min_coins: 1, max_coins: 4, unit_price_rub: 100, discount_pct: 0 },
    { min_coins: 5, max_coins: 9, unit_price_rub: 90, discount_pct: 10 },
    { min_coins: 10, max_coins: null, unit_price_rub: 80, discount_pct: 20 },
  ],
};

function setCoins(value) {
  document.getElementById("coins-value").textContent = value;
  document.getElementById("wallet-coins").textContent = value;
}

function setSelectedCityUI(city) {
  state.selectedCity = city || "";
  const label = city || "Не выбран";
  const partnersValue = document.getElementById("partners-city-value");
  if (partnersValue) partnersValue.textContent = label;
  document.querySelectorAll(".select-search-list .city-option").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.city === city);
  });
}

function firstLetter(city) {
  const ch = (city || "").trim().charAt(0).toUpperCase();
  return ch || "#";
}

function renderCityList(filter = "") {
  const listEl = document.getElementById("partners-city-list");
  if (!listEl) return;
  const q = filter.trim().toLowerCase();
  const cities = state.cities.filter((c) => !q || c.toLowerCase().includes(q));

  if (!cities.length) {
    listEl.innerHTML = `<p class="city-empty">Ничего не найдено. Измените запрос.</p>`;
    return;
  }

  let html = "";
  let lastLetter = "";
  cities.forEach((city) => {
    const letter = firstLetter(city);
    if (letter !== lastLetter) {
      lastLetter = letter;
      html += `<div class="city-option-letter">${letter}</div>`;
    }
    const active = city === state.selectedCity ? " is-active" : "";
    html += `<button type="button" class="city-option${active}" role="option" data-city="${city}">${city}</button>`;
  });
  listEl.innerHTML = html;
}

async function saveSelectedCity(city) {
  const status = document.getElementById("partners-city-status");
  if (status) status.textContent = "";
  if (!city) {
    if (status) status.textContent = "Сначала выберите город из списка.";
    return false;
  }
  try {
    const data = await api("/api/city", {
      method: "POST",
      body: JSON.stringify({ city }),
    });
    state.client = data.client;
    setSelectedCityUI(data.client.selected_city);
    if (status) status.textContent = `Город: ${city}`;
    await loadPartners();
    return true;
  } catch (err) {
    if (status) status.textContent = err.message;
    return false;
  }
}

function activateTab(name, options = {}) {
  document.querySelectorAll(".cabinet-tab").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".cabinet-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${name}`);
  });
  if (name === "partners") loadPartners();
  if (name === "pay" && options.openPanel) {
    openPayPanel(options.openPanel);
  }
}

function openPayPanel(panelKey) {
  const map = {
    card: "pay-panel-card",
    invite: "pay-panel-invite",
    promo: "pay-panel-promo",
  };
  const id = map[panelKey] || map.card;

  document.querySelectorAll(".pay-icon-tab").forEach((btn) => {
    const active = btn.dataset.payPanel === panelKey;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", String(active));
  });

  document.querySelectorAll(".pay-panel-content").forEach((panel) => {
    const active = panel.id === id;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  });
}

function bindPayIcons() {
  document.querySelectorAll(".pay-icon-tab").forEach((btn) => {
    btn.addEventListener("click", () => openPayPanel(btn.dataset.payPanel));
  });
}

async function loadMe() {
  const data = await api("/api/me");
  state.client = data.client;
  state.coinPrice = data.coin_price_rub || 100;
  if (Array.isArray(data.coin_tiers) && data.coin_tiers.length) {
    state.coinTiers = data.coin_tiers;
  }
  document.getElementById("user-name").textContent = state.client.fio;
  setSelectedCityUI(state.client.selected_city || "");
  updatePayQuote();
  setCoins(state.client.coins);
}

function unitPriceFor(coins) {
  const n = Math.max(1, Number(coins) || 1);
  if (n >= 10) return { unit: 80, discount: 20 };
  if (n >= 5) return { unit: 90, discount: 10 };
  return { unit: state.coinPrice || 100, discount: 0 };
}

function quotePurchase(coins) {
  const n = Math.max(1, Math.min(100, Number(coins) || 1));
  const { unit, discount } = unitPriceFor(n);
  return {
    coins: n,
    amount: n * unit,
    unit,
    discount,
  };
}

function updatePayQuote() {
  const coinsInput = document.getElementById("pay-coins");
  const amountEl = document.getElementById("pay-amount");
  const hintEl = document.getElementById("pay-pack-hint");
  if (!coinsInput || !amountEl) return;
  const q = quotePurchase(coinsInput.value);
  amountEl.textContent = String(q.amount);
  if (hintEl) {
    if (q.discount) {
      hintEl.textContent = `${q.coins} монет × ${q.unit} ₽ (−${q.discount}%) · к оплате ${q.amount} ₽`;
    } else {
      hintEl.textContent = `1–4 монеты — по ${state.coinPrice} ₽ · 5–9 — по 90 ₽ · от 10 — по 80 ₽`;
    }
  }
}

async function loadCities() {
  const data = await api("/api/cities");
  state.cities = [...(data.cities || [])].sort((a, b) => a.localeCompare(b, "ru"));
  renderCityList("");
  setSelectedCityUI(state.selectedCity || state.client?.selected_city || "");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadPartners() {
  const city = state.client?.selected_city || state.selectedCity || "";
  const partnersStatus = document.getElementById("partners-city-status");
  if (partnersStatus) {
    partnersStatus.textContent = city
      ? `Город: ${city}`
      : "Выберите город, чтобы увидеть партнёров.";
  }

  const grid = document.getElementById("partners-grid");
  const empty = document.getElementById("partners-empty");
  grid.innerHTML = "";

  if (!city) {
    empty.hidden = false;
    empty.textContent = "Сначала выберите город в списке выше.";
    return;
  }

  const data = await api(`/api/partners?city=${encodeURIComponent(city)}`);
  const partners = data.partners || [];
  if (!partners.length) {
    empty.hidden = false;
    empty.textContent = "В этом городе пока нет партнёров. Выберите другой город или загляните позже.";
    return;
  }

  empty.hidden = true;
  grid.innerHTML = partners
    .map((p) => {
      const images = (p.images && p.images.length ? p.images : [p.image]).filter(Boolean);
      const slides = images
        .map(
          (src, idx) =>
            `<img src="${src}" alt="${escapeHtml(p.name)}" class="${idx === 0 ? "is-active" : ""}" data-slide="${idx}" />`
        )
        .join("");
      const dots =
        images.length > 1
          ? `<div class="partner-carousel-dots">${images
              .map((_, idx) => `<span class="${idx === 0 ? "is-active" : ""}" data-dot="${idx}"></span>`)
              .join("")}</div>`
          : "";
      const controls =
        images.length > 1
          ? `<button type="button" class="partner-carousel-btn prev" data-dir="-1" aria-label="Назад">‹</button>
             <button type="button" class="partner-carousel-btn next" data-dir="1" aria-label="Вперёд">›</button>`
          : "";
      const hoursPhone = [p.hours, p.phone].filter(Boolean).join(" · ");
      const cityLabel = (p.city || city || "").trim().toUpperCase();
      const spend = p.spend_coins ?? 2;
      return `
      <article class="partner-card">
        <div class="partner-visual" data-carousel>
          <div class="partner-carousel-track">${slides || `<img src="/assets/partners/norma-tela.png" alt="" class="is-active" />`}</div>
          ${controls}
          ${dots}
          <div class="partner-visual-scrim" aria-hidden="true"></div>
          <div class="partner-visual-copy">
            <h3>${escapeHtml(p.name)}</h3>
            ${p.category ? `<span class="partner-tag">${escapeHtml(p.category)}</span>` : ""}
          </div>
        </div>
        <div class="partner-card-body">
          ${cityLabel ? `<p class="partner-card-city">${escapeHtml(cityLabel)}</p>` : ""}
          <div class="partner-card-row">
            <div class="partner-card-side">
              ${p.address ? `<p class="partner-card-addr">${escapeHtml(p.address)}</p>` : ""}
              ${hoursPhone ? `<p class="partner-card-hours">${escapeHtml(hoursPhone)}</p>` : ""}
            </div>
            <div class="partner-limit-box" title="Сколько монет списывается у партнёра">
              <span class="partner-limit-label">Списание</span>
              <div class="partner-limit-value">
                <strong>${spend}</strong>
                <img class="coin-icon" src="/assets/coin.svg" alt="монета" />
              </div>
            </div>
          </div>
          <button type="button" class="partner-details-btn" data-details-toggle aria-expanded="false">Детали →</button>
          <div class="partner-details" hidden>
            <p>${escapeHtml(p.description || "Описание появится позже.")}</p>
            ${
              p.website
                ? `<a href="${escapeHtml(p.website)}" target="_blank" rel="noopener">Сайт партнёра</a>`
                : ""
            }
          </div>
        </div>
      </article>`;
    })
    .join("");

  bindCarousels(grid);
  bindPartnerDetails(grid);
}

function bindCarousels(root) {
  root.querySelectorAll("[data-carousel]").forEach((carousel) => {
    const imgs = [...carousel.querySelectorAll(".partner-carousel-track img")];
    if (imgs.length < 2) return;
    let index = 0;
    const dots = [...carousel.querySelectorAll("[data-dot]")];
    const show = (next) => {
      index = (next + imgs.length) % imgs.length;
      imgs.forEach((img, i) => img.classList.toggle("is-active", i === index));
      dots.forEach((dot, i) => dot.classList.toggle("is-active", i === index));
    };
    carousel.querySelectorAll("[data-dir]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.stopPropagation();
        show(index + Number(btn.dataset.dir));
      });
    });
  });
}

function bindPartnerDetails(root) {
  root.querySelectorAll("[data-details-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const details = btn.parentElement.querySelector(".partner-details");
      if (!details) return;
      const open = details.hidden;
      details.hidden = !open;
      btn.setAttribute("aria-expanded", String(open));
      btn.textContent = open ? "Скрыть ↑" : "Детали →";
    });
  });
}

function bindTabs() {
  document.querySelectorAll(".cabinet-tab").forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  });
  document.querySelectorAll("[data-goto-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      activateTab(btn.dataset.gotoTab, {
        openPanel: btn.dataset.openPayPanel || "card",
      });
    });
  });
}

function bindCity() {
  const root = document.getElementById("partners-city-select");
  const trigger = document.getElementById("partners-city-trigger");
  const panel = document.getElementById("partners-city-panel");
  const search = document.getElementById("partners-city-search");
  const list = document.getElementById("partners-city-list");
  if (!root || !trigger || !panel || !search || !list) return;

  const openPanel = () => {
    panel.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    search.value = "";
    renderCityList("");
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

  search.addEventListener("input", () => renderCityList(search.value));

  list.addEventListener("click", async (event) => {
    const btn = event.target.closest(".city-option");
    if (!btn) return;
    const city = btn.dataset.city;
    setSelectedCityUI(city);
    closePanel();
    await saveSelectedCity(city);
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) closePanel();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closePanel();
  });
}

function bindPay() {
  const coinsInput = document.getElementById("pay-coins");
  const cardNumber = document.getElementById("card-number");
  const cardExp = document.getElementById("card-exp");

  coinsInput.addEventListener("input", () => {
    updatePayQuote();
  });

  cardNumber.addEventListener("input", () => {
    const digits = cardNumber.value.replace(/\D/g, "").slice(0, 16);
    cardNumber.value = digits.replace(/(\d{4})(?=\d)/g, "$1 ").trim();
  });

  cardExp.addEventListener("input", () => {
    let v = cardExp.value.replace(/\D/g, "").slice(0, 4);
    if (v.length >= 3) v = `${v.slice(0, 2)}/${v.slice(2)}`;
    cardExp.value = v;
  });

  document.getElementById("pay-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("pay-status");
    status.textContent = "";
    try {
      const data = await api("/api/buy-coins", {
        method: "POST",
        body: JSON.stringify({
          coins: Number(coinsInput.value),
          card_number: cardNumber.value,
          card_exp: cardExp.value,
          card_cvc: document.getElementById("card-cvc").value,
        }),
      });
      setCoins(data.coins);
      status.textContent = data.message;
      document.getElementById("pay-form").reset();
      coinsInput.value = "1";
      updatePayQuote();
    } catch (err) {
      status.textContent = err.message;
    }
  });
}

function bindLogout() {
  document.getElementById("logout-btn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST", body: "{}" });
    window.location.href = "/";
  });
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.hidden = false;
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeModal(modal) {
  if (!modal) return;
  modal.hidden = true;
  modal.setAttribute("aria-hidden", "true");
  if (modal.id === "spend-qr-modal") stopSpendCountdown();
  if (!document.querySelector(".modal:not([hidden])")) {
    document.body.classList.remove("modal-open");
  }
}

function bindModals() {
  document.querySelectorAll(".modal [data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => closeModal(btn.closest(".modal")));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll(".modal:not([hidden])").forEach((modal) => closeModal(modal));
  });
}

let spendTimerId = null;

function formatCountdown(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const mm = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function stopSpendCountdown() {
  if (spendTimerId) {
    clearInterval(spendTimerId);
    spendTimerId = null;
  }
}

function startSpendCountdown(expiresAtIso, ttlMinutes) {
  stopSpendCountdown();
  const timerEl = document.getElementById("spend-qr-timer");
  const expiredEl = document.getElementById("spend-qr-expired");
  expiredEl.hidden = true;

  let endMs = Date.parse(expiresAtIso);
  if (Number.isNaN(endMs)) {
    endMs = Date.now() + (ttlMinutes || 10) * 60 * 1000;
  }

  const tick = () => {
    const left = Math.ceil((endMs - Date.now()) / 1000);
    timerEl.textContent = formatCountdown(left);
    if (left <= 0) {
      stopSpendCountdown();
      timerEl.textContent = "00:00";
      expiredEl.hidden = false;
    }
  };

  tick();
  spendTimerId = setInterval(tick, 250);
}

function bindSpend() {
  const btn = document.getElementById("spend-btn");
  const status = document.getElementById("spend-status");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    status.textContent = "";
    btn.disabled = true;
    try {
      const data = await api("/api/spend-qr", {
        method: "POST",
        body: "{}",
      });

      document.getElementById("spend-qr-balance").textContent = data.balance ?? state.client?.coins ?? 0;

      const canvas = document.getElementById("spend-qr-canvas");
      if (typeof QRious === "undefined") {
        throw new Error("Не удалось загрузить генератор QR. Проверьте интернет.");
      }
      // eslint-disable-next-line no-new
      new QRious({
        element: canvas,
        value: data.qr_payload,
        size: 220,
        level: "M",
      });

      startSpendCountdown(data.expires_at, data.ttl_minutes);
      openModal("spend-qr-modal");
    } catch (err) {
      status.textContent = err.message;
    } finally {
      btn.disabled = false;
    }
  });
}

function bindPromo() {
  const form = document.getElementById("promo-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("promo-status");
    const input = document.getElementById("promo-code");
    status.textContent = "";
    try {
      const data = await api("/api/promo", {
        method: "POST",
        body: JSON.stringify({ code: input.value }),
      });
      setCoins(data.coins);
      if (state.client) state.client.coins = data.coins;
      status.textContent = data.message;
      input.value = "";
    } catch (err) {
      status.textContent = err.message;
    }
  });
}

async function boot() {
  try {
    await loadMe();
    await loadCities();
    bindTabs();
    bindCity();
    bindPay();
    bindPayIcons();
    bindPromo();
    bindSpend();
    bindModals();
    bindLogout();
    activateTab("partners");
  } catch (err) {
    if (err.status === 401) {
      window.location.href = "/?login=1";
      return;
    }
    alert(err.message || "Не удалось открыть кабинет");
  }
}

boot();
