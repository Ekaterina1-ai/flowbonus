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
  card: null,
  plans: [],
  selectedPlan: "m3",
  cities: [],
  selectedCity: "",
};

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function formatDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pluralRu(n, one, few, many) {
  const abs = Math.abs(Number(n)) || 0;
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function privilegesWord(n) {
  return pluralRu(n, "привилегия", "привилегии", "привилегий");
}

function formatRub(n) {
  return `${new Intl.NumberFormat("ru-RU").format(Number(n) || 0)} ₽`;
}

function renderCard(card) {
  state.card = card || { active: false, privileges: 0 };
  const c = state.card;
  const count = c.active ? c.privileges : 0;

  document.getElementById("coins-value").textContent = count;
  document.getElementById("wallet-privileges").textContent = count;
  document.getElementById("card-badge-label").textContent = c.active
    ? `Карта до ${formatDate(c.expires_at)} · привилегий`
    : "Клубная карта не оформлена";

  document.getElementById("card-status").textContent = c.active
    ? `Клубная карта активна до ${formatDate(c.expires_at)} · осталось ${c.days_left} ${pluralRu(c.days_left, "день", "дня", "дней")}`
    : "Клубная карта не оформлена. Оформите карту или активируйте промокод.";

  const split = document.getElementById("card-split");
  split.textContent = c.active
    ? `Оплаченных: ${c.paid_privileges} · бонусных: ${c.bonus_privileges}. Бонусные расходуются первыми.`
    : "";

  const reminder = document.getElementById("card-reminder");
  reminder.hidden = !c.reminder;
  reminder.textContent = c.reminder
    ? `Карта закончится ${formatDate(c.expires_at)}. Неиспользованные привилегии (${c.privileges}) сгорят вместе с ней — используйте их или оформите новую карту: срок продлится, привилегии сохранятся.`
    : "";

  const refund = document.getElementById("card-refund");
  if (c.active && c.refund_rub > 0) {
    refund.hidden = false;
    refund.innerHTML = `При отказе от карты сейчас вам вернут <strong>${formatRub(c.refund_rub)}</strong> за неиспользованные оплаченные привилегии. Заявление — на <a href="mailto:katerina7959@yandex.ru">katerina7959@yandex.ru</a>, порядок — в <a href="/legal/offer-client.html#refund" target="_blank" rel="noopener">оферте</a>.`;
  } else {
    refund.hidden = true;
    refund.textContent = "";
  }

  document.getElementById("card-buy-btn").textContent = c.active ? "Продлить карту" : "Оформить карту";
  updatePayQuote();
}

async function refreshCard() {
  try {
    const data = await api("/api/me");
    state.client = data.client;
    renderCard(data.client.card);
    loadHistory();
  } catch (_) {
    /* обновится при следующем открытии кабинета */
  }
}

async function loadHistory() {
  const list = document.getElementById("card-history");
  if (!list) return;
  try {
    const data = await api("/api/history");
    const items = data.items || [];
    if (!items.length) {
      list.innerHTML = `<p class="form-note">Пока нет операций.</p>`;
      return;
    }
    list.innerHTML = items
      .map((i) => {
        const sign = i.delta > 0 ? "+" : "";
        const cls = i.delta > 0 ? " is-plus" : "";
        return `<div class="card-history-item">
          <div>
            <div>${escapeHtml(i.note)}</div>
            <div class="form-note">${escapeHtml(formatDateTime(i.created_at))}</div>
          </div>
          <strong class="${cls.trim()}">${i.delta ? `${sign}${i.delta}` : "—"}</strong>
        </div>`;
      })
      .join("");
  } catch (err) {
    list.innerHTML = `<p class="form-note">${escapeHtml(err.message)}</p>`;
  }
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
  if (name === "wallet") loadHistory();
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
  state.plans = Array.isArray(data.plans) ? data.plans : [];
  if (!state.plans.some((p) => p.code === state.selectedPlan) && state.plans.length) {
    state.selectedPlan = state.plans[0].code;
  }
  document.getElementById("user-name").textContent = state.client.fio;
  setSelectedCityUI(state.client.selected_city || "");
  renderPlans();
  renderCard(state.client.card);

  const referral = data.referral || {};
  const linkInput = document.getElementById("invite-link");
  if (linkInput) linkInput.value = referral.link || "";
  const bonusEl = document.getElementById("invite-bonus");
  if (bonusEl && referral.bonus_privileges) bonusEl.textContent = referral.bonus_privileges;
}

function addMonths(date, months) {
  const d = new Date(date.getTime());
  const day = d.getDate();
  d.setDate(1);
  d.setMonth(d.getMonth() + months);
  const lastDay = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(day, lastDay));
  return d;
}

function renderPlans() {
  const root = document.getElementById("plan-options");
  if (!root) return;
  root.innerHTML = state.plans
    .map((p) => {
      const active = p.code === state.selectedPlan;
      return `<label class="plan-option${active ? " is-active" : ""}">
        <input type="radio" name="plan" value="${escapeHtml(p.code)}" ${active ? "checked" : ""} />
        <span class="plan-option-text">
          <span class="plan-option-title">${escapeHtml(p.title)}</span>
          <span class="plan-option-meta">${p.privileges} ${privilegesWord(p.privileges)} на срок карты</span>
        </span>
        <span class="plan-option-price">${formatRub(p.price_rub)}</span>
      </label>`;
    })
    .join("");
  updatePayQuote();
}

function updatePayQuote() {
  const amountEl = document.getElementById("pay-amount");
  const hintEl = document.getElementById("pay-plan-hint");
  const plan = state.plans.find((p) => p.code === state.selectedPlan);
  if (!amountEl || !plan) return;
  amountEl.textContent = new Intl.NumberFormat("ru-RU").format(plan.price_rub);
  if (!hintEl) return;
  const card = state.card || {};
  if (card.active && card.expires_at) {
    const until = addMonths(new Date(card.expires_at), plan.months);
    hintEl.textContent = `Текущая карта продлится до ${formatDate(until.toISOString())}, ещё ${plan.privileges} ${privilegesWord(plan.privileges)} добавятся сразу.`;
  } else {
    const until = addMonths(new Date(), plan.months);
    hintEl.textContent = `Карта будет действовать до ${formatDate(until.toISOString())}: ${plan.privileges} ${privilegesWord(plan.privileges)}.`;
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
      const privilege = (p.privilege_text || "").trim() || "Вторая позиция той же или меньшей стоимости — в подарок";
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
              <p class="partner-card-privilege">${escapeHtml(privilege)}</p>
            </div>
            <div class="partner-limit-box" title="За 1 привилегию клубной карты — вторая позиция в подарок">
              <span class="partner-limit-label">Подарок за</span>
              <div class="partner-limit-value">
                <strong>1</strong>
                <img class="coin-icon" src="/assets/privilege.svg" alt="привилегию" />
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
  const options = document.getElementById("plan-options");
  options.addEventListener("change", (event) => {
    const input = event.target.closest("input[name='plan']");
    if (!input) return;
    state.selectedPlan = input.value;
    options.querySelectorAll(".plan-option").forEach((label) => {
      label.classList.toggle("is-active", label.contains(input));
    });
    updatePayQuote();
  });

  document.getElementById("pay-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("pay-status");
    const button = event.target.querySelector('button[type="submit"]');
    status.textContent = "";
    button.disabled = true;
    try {
      const data = await api("/api/buy-card", {
        method: "POST",
        body: JSON.stringify({ plan: state.selectedPlan }),
      });
      renderCard(data.card);
      status.textContent = data.message;
    } catch (err) {
      status.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  });
}

function bindInvite() {
  const btn = document.getElementById("invite-copy-btn");
  const input = document.getElementById("invite-link");
  const status = document.getElementById("invite-status");
  if (!btn || !input) return;
  btn.addEventListener("click", async () => {
    status.textContent = "";
    try {
      await navigator.clipboard.writeText(input.value);
      status.textContent = "Ссылка скопирована.";
    } catch (_) {
      input.select();
      status.textContent = "Выделите ссылку и скопируйте её вручную.";
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
  if (modal.id === "spend-qr-modal") {
    stopSpendCountdown();
    refreshCard();
  }
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

      document.getElementById("spend-qr-balance").textContent = data.card?.privileges ?? 0;

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
      renderCard(data.card);
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
    bindInvite();
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
