const state = {
  admin: null,
  clients: [],
  partners: [],
  promos: [],
  currentClientId: null,
  currentPartnerId: null,
};

async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "same-origin",
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    window.location.href = "/admin/login";
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    throw new Error(data.error || "Ошибка запроса");
  }
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatMoney(n) {
  return new Intl.NumberFormat("ru-RU").format(Number(n) || 0) + " ₽";
}

function formatDate(iso) {
  if (!iso) return "—";
  const s = String(iso).replace("T", " ").slice(0, 19);
  return s;
}

function todayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function monthStartISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function eyeIcon() {
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" stroke="currentColor" stroke-width="1.8"/>
    <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/>
  </svg>`;
}

function bindTabs() {
  document.querySelectorAll(".cabinet-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".cabinet-tab").forEach((b) => b.classList.toggle("is-active", b === btn));
      document.querySelectorAll(".cabinet-panel").forEach((p) => {
        p.classList.toggle("is-active", p.id === `tab-${tab}`);
      });
      if (tab === "clients") loadClients();
      if (tab === "partners") loadPartners();
      if (tab === "promos") loadPromos();
      if (tab === "audit") loadAudit();
      if (tab === "stats") loadStats();
    });
  });
}

function bindLogout() {
  document.getElementById("logout-btn").addEventListener("click", async () => {
    await api("/api/admin/logout", { method: "POST", body: "{}" });
    window.location.href = "/admin/login";
  });
}

function bindModals() {
  document.querySelectorAll("[data-close-modal]").forEach((el) => {
    el.addEventListener("click", () => {
      document.querySelectorAll(".admin-modal").forEach((m) => {
        m.hidden = true;
      });
    });
  });
}

async function loadMe() {
  const data = await api("/api/admin/me");
  state.admin = data.admin;
  document.getElementById("admin-name").textContent = `Админ: ${data.admin.login}`;
}

function renderStatCards(stats) {
  const items = [
    { label: "Куплено монет", value: stats.coins_bought },
    { label: "В кассе (к оплате)", value: formatMoney(stats.cash_rub) },
    { label: "Покупок", value: stats.purchase_count },
    { label: "Списано монет", value: stats.coins_spent },
    { label: "Списаний", value: stats.spend_count },
    { label: "Рег. клиентов", value: stats.client_registrations },
    { label: "Рег. партнёров", value: stats.partner_registrations },
    { label: "Активаций промо", value: stats.promo_redemptions },
    { label: "Клиентов всего", value: stats.clients_total },
    { label: "Партнёров всего", value: stats.partners_total },
    { label: "Монет на счетах", value: stats.coins_in_wallets },
  ];
  document.getElementById("stats-cards").innerHTML = items
    .map(
      (i) => `<div class="admin-stat-card"><span>${escapeHtml(i.label)}</span><strong>${escapeHtml(i.value)}</strong></div>`
    )
    .join("");

  const tbody = document.querySelector("#stats-partners-table tbody");
  const empty = document.getElementById("stats-partners-empty");
  if (!stats.top_partners.length) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  tbody.innerHTML = stats.top_partners
    .map(
      (p) => `<tr>
        <td>${escapeHtml(p.business_name)}</td>
        <td>${escapeHtml(p.city || "—")}</td>
        <td>${p.ops_count}</td>
        <td>${p.coins_total}</td>
      </tr>`
    )
    .join("");
}

async function loadStats(from, to) {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const data = await api(`/api/admin/stats?${params}`);
  const s = data.stats;
  document.getElementById("stats-period-label").textContent =
    `Период: ${s.period.from} — ${s.period.to}`;
  document.getElementById("stats-from").value = s.period.from;
  document.getElementById("stats-to").value = s.period.to;
  renderStatCards(s);
}

function bindStats() {
  document.querySelectorAll("[data-period]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const kind = btn.dataset.period;
      if (kind === "today") {
        const t = todayISO();
        loadStats(t, t);
      } else if (kind === "month") {
        loadStats(monthStartISO(), todayISO());
      } else {
        loadStats("2020-01-01", todayISO());
      }
    });
  });
  document.getElementById("stats-apply").addEventListener("click", () => {
    loadStats(
      document.getElementById("stats-from").value,
      document.getElementById("stats-to").value
    );
  });
}

async function loadClients() {
  const data = await api("/api/admin/clients");
  state.clients = data.clients;
  const tbody = document.querySelector("#clients-table tbody");
  const empty = document.getElementById("clients-empty");
  if (!data.clients.length) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  tbody.innerHTML = data.clients
    .map(
      (c) => `<tr>
        <td>${c.id}</td>
        <td>${escapeHtml(c.fio)}</td>
        <td>${escapeHtml(c.phone)}</td>
        <td>${escapeHtml(c.selected_city || c.city)}</td>
        <td>${c.coins}</td>
        <td>${
          c.is_blocked
            ? '<span class="admin-badge admin-badge-off">Заблокирован</span>'
            : '<span class="admin-badge admin-badge-ok">Активен</span>'
        }</td>
        <td><button class="admin-icon-btn" type="button" data-open-client="${c.id}" title="Открыть" aria-label="Открыть клиента">${eyeIcon()}</button></td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll("[data-open-client]").forEach((btn) => {
    btn.addEventListener("click", () => openClientModal(Number(btn.dataset.openClient)));
  });
}

function sourceLabel(source) {
  return (
    {
      purchase: "Покупка",
      promo: "Промокод",
      admin: "Админ",
      spend: "Списание",
    }[source] || source
  );
}

async function openClientModal(clientId) {
  state.currentClientId = clientId;
  const data = await api(`/api/admin/clients/${clientId}`);
  const c = data.client;
  document.getElementById("client-modal-title").textContent = `Клиент #${c.id}`;
  const body = document.getElementById("client-modal-body");
  body.innerHTML = `
    <dl class="admin-detail-grid">
      <dt>ФИО</dt><dd>${escapeHtml(c.fio)}</dd>
      <dt>Телефон (логин)</dt><dd>${escapeHtml(c.phone)}</dd>
      <dt>Email</dt><dd>${escapeHtml(c.email)}</dd>
      <dt>Город регистрации</dt><dd>${escapeHtml(c.city)}</dd>
      <dt>Выбранный город</dt><dd>${escapeHtml(c.selected_city)}</dd>
      <dt>Баланс</dt><dd>${c.coins} монет</dd>
      <dt>Статус</dt><dd>${c.is_blocked ? "Заблокирован" : "Доступен"}</dd>
      <dt>Регистрация</dt><dd>${escapeHtml(formatDate(c.created_at))}</dd>
    </dl>
    <div class="admin-actions">
      <form class="pay-form" id="client-coins-form">
        <label>Начислить монеты
          <input type="number" id="client-coins-amount" min="1" max="10000" value="1" required />
        </label>
        <label>Причина начисления (на русском)
          <input type="text" id="client-coins-note" maxlength="200" minlength="3" required placeholder="Например: компенсация за ошибку" />
        </label>
        <button class="btn btn-primary" type="submit">Начислить</button>
        <p class="form-note" id="client-coins-status"></p>
      </form>
      <div class="pay-form" id="client-password-block">
        <label>Текущий пароль
          <input type="text" id="client-current-password" readonly placeholder="Нажмите «Сбросить пароль»" autocomplete="off" />
        </label>
        <button class="btn btn-ghost" type="button" id="client-reset-password-btn">Сбросить пароль</button>
        <p class="form-note" id="client-password-status">После сброса старый пароль перестанет работать. Передайте клиенту новый из поля выше.</p>
      </div>
      <div class="btn-row">
        ${
          c.is_blocked
            ? '<button class="btn btn-primary" type="button" id="client-unblock-btn">Восстановить доступ</button>'
            : '<button class="btn btn-ghost" type="button" id="client-block-btn">Заблокировать кабинет</button>'
        }
      </div>
      <p class="form-note" id="client-block-status"></p>
    </div>
    <div class="section-head" style="margin-top:1rem"><h3>История монет</h3></div>
    <div class="admin-ledger">
      <table>
        <thead><tr><th>Когда</th><th>Источник</th><th>Δ</th><th>Заметка</th></tr></thead>
        <tbody>
          ${
            c.ledger.length
              ? c.ledger
                  .map(
                    (r) => `<tr>
                      <td>${escapeHtml(formatDate(r.created_at))}</td>
                      <td>${escapeHtml(sourceLabel(r.source))}</td>
                      <td>${r.delta > 0 ? "+" : ""}${r.delta}</td>
                      <td>${escapeHtml(r.note)}</td>
                    </tr>`
                  )
                  .join("")
              : "<tr><td colspan='4'>Пока нет записей</td></tr>"
          }
        </tbody>
      </table>
    </div>
  `;
  document.getElementById("client-modal").hidden = false;

  document.getElementById("client-coins-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = document.getElementById("client-coins-status");
    status.textContent = "";
    try {
      await api(`/api/admin/clients/${clientId}/coins`, {
        method: "POST",
        body: JSON.stringify({
          coins: Number(document.getElementById("client-coins-amount").value),
          note: document.getElementById("client-coins-note").value.trim(),
        }),
      });
      status.textContent = "Монеты начислены.";
      await openClientModal(clientId);
      loadClients();
    } catch (err) {
      status.textContent = err.message;
    }
  });

  document.getElementById("client-reset-password-btn").addEventListener("click", async () => {
    const status = document.getElementById("client-password-status");
    const field = document.getElementById("client-current-password");
    status.textContent = "Генерируем пароль…";
    try {
      const res = await api(`/api/admin/clients/${clientId}/password`, {
        method: "POST",
        body: "{}",
      });
      field.value = res.password;
      status.innerHTML = `Пароль обновлён. Передайте клиенту: <span class="admin-password-reveal">${escapeHtml(
        res.password
      )}</span>. Старый пароль больше не действует.`;
    } catch (err) {
      status.textContent = err.message;
    }
  });

  const blockBtn = document.getElementById("client-block-btn");
  const unblockBtn = document.getElementById("client-unblock-btn");
  if (blockBtn) {
    blockBtn.addEventListener("click", async () => {
      try {
        await api(`/api/admin/clients/${clientId}/block`, { method: "POST", body: "{}" });
        await openClientModal(clientId);
        loadClients();
      } catch (err) {
        document.getElementById("client-block-status").textContent = err.message;
      }
    });
  }
  if (unblockBtn) {
    unblockBtn.addEventListener("click", async () => {
      try {
        await api(`/api/admin/clients/${clientId}/unblock`, { method: "POST", body: "{}" });
        await openClientModal(clientId);
        loadClients();
      } catch (err) {
        document.getElementById("client-block-status").textContent = err.message;
      }
    });
  }
}

async function loadPartners() {
  const data = await api("/api/admin/partners");
  state.partners = data.partners;
  const tbody = document.querySelector("#partners-table tbody");
  const empty = document.getElementById("partners-empty");
  if (!data.partners.length) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  tbody.innerHTML = data.partners
    .map(
      (p) => `<tr>
        <td>${p.id}</td>
        <td>${escapeHtml(p.business_name)}</td>
        <td>${escapeHtml(p.contact_name)}</td>
        <td>${escapeHtml(p.phone)}</td>
        <td>${escapeHtml(p.city || "—")}</td>
        <td>${
          p.is_blocked
            ? '<span class="admin-badge admin-badge-off">Заблокирован</span>'
            : '<span class="admin-badge admin-badge-ok">Активен</span>'
        }</td>
        <td><button class="admin-icon-btn" type="button" data-open-partner="${p.id}" title="Открыть" aria-label="Открыть партнёра">${eyeIcon()}</button></td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll("[data-open-partner]").forEach((btn) => {
    btn.addEventListener("click", () => openPartnerModal(Number(btn.dataset.openPartner)));
  });
}

async function openPartnerModal(partnerId) {
  state.currentPartnerId = partnerId;
  const data = await api(`/api/admin/partners/${partnerId}`);
  const p = data.partner;
  document.getElementById("partner-modal-title").textContent = `Партнёр #${p.id}`;
  const body = document.getElementById("partner-modal-body");
  body.innerHTML = `
    <dl class="admin-detail-grid">
      <dt>Бизнес</dt><dd>${escapeHtml(p.business_name)}</dd>
      <dt>Категория</dt><dd>${escapeHtml(p.category)}</dd>
      <dt>Контакт</dt><dd>${escapeHtml(p.contact_name)}</dd>
      <dt>Телефон</dt><dd>${escapeHtml(p.phone)}</dd>
      <dt>Город</dt><dd>${escapeHtml(p.city || "—")}</dd>
      <dt>Адрес</dt><dd>${escapeHtml(p.address || "—")}</dd>
      <dt>Монет за визит</dt><dd>${p.spend_coins}</dd>
      <dt>Списано всего</dt><dd>${p.stats.coins_total} (${p.stats.ops_count} опер.)</dd>
      <dt>Статус</dt><dd>${p.is_blocked ? "Заблокирован" : "Доступен"}</dd>
      <dt>Регистрация</dt><dd>${escapeHtml(formatDate(p.created_at))}</dd>
    </dl>
    <div class="admin-actions">
      <div class="pay-form" id="partner-password-block">
        <label>Текущий пароль
          <input type="text" id="partner-current-password" readonly placeholder="Нажмите «Сбросить пароль»" autocomplete="off" />
        </label>
        <button class="btn btn-ghost" type="button" id="partner-reset-password-btn">Сбросить пароль</button>
        <p class="form-note" id="partner-password-status">После сброса старый пароль перестанет работать. Передайте партнёру новый из поля выше.</p>
      </div>
      <div class="btn-row">
        ${
          p.is_blocked
            ? '<button class="btn btn-primary" type="button" id="partner-unblock-btn">Восстановить доступ</button>'
            : '<button class="btn btn-ghost" type="button" id="partner-block-btn">Заблокировать кабинет</button>'
        }
      </div>
      <p class="form-note" id="partner-block-status"></p>
    </div>
  `;
  document.getElementById("partner-modal").hidden = false;

  document.getElementById("partner-reset-password-btn").addEventListener("click", async () => {
    const status = document.getElementById("partner-password-status");
    const field = document.getElementById("partner-current-password");
    status.textContent = "Генерируем пароль…";
    try {
      const res = await api(`/api/admin/partners/${partnerId}/password`, {
        method: "POST",
        body: "{}",
      });
      field.value = res.password;
      status.innerHTML = `Пароль обновлён. Передайте партнёру: <span class="admin-password-reveal">${escapeHtml(
        res.password
      )}</span>. Старый пароль больше не действует.`;
    } catch (err) {
      status.textContent = err.message;
    }
  });

  const blockBtn = document.getElementById("partner-block-btn");
  const unblockBtn = document.getElementById("partner-unblock-btn");
  if (blockBtn) {
    blockBtn.addEventListener("click", async () => {
      try {
        await api(`/api/admin/partners/${partnerId}/block`, { method: "POST", body: "{}" });
        await openPartnerModal(partnerId);
        loadPartners();
      } catch (err) {
        document.getElementById("partner-block-status").textContent = err.message;
      }
    });
  }
  if (unblockBtn) {
    unblockBtn.addEventListener("click", async () => {
      try {
        await api(`/api/admin/partners/${partnerId}/unblock`, { method: "POST", body: "{}" });
        await openPartnerModal(partnerId);
        loadPartners();
      } catch (err) {
        document.getElementById("partner-block-status").textContent = err.message;
      }
    });
  }
}

async function loadPromos() {
  const data = await api("/api/admin/promos");
  state.promos = data.promos;
  const tbody = document.querySelector("#promos-table tbody");
  const empty = document.getElementById("promos-empty");
  if (!data.promos.length) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  tbody.innerHTML = data.promos
    .map(
      (p) => `<tr>
        <td><strong>${escapeHtml(p.code)}</strong></td>
        <td>${p.coins}</td>
        <td>${p.used_count}${p.max_uses != null ? ` / ${p.max_uses}` : ""} <span style="color:var(--muted)">(${p.clients_used} кл.)</span></td>
        <td>${escapeHtml(p.comment || "—")}</td>
        <td>${
          p.active
            ? '<span class="admin-badge admin-badge-ok">Активен</span>'
            : '<span class="admin-badge admin-badge-off">Закрыт</span>'
        }</td>
        <td>
          ${
            p.active
              ? `<button class="btn btn-ghost" type="button" data-close-promo="${escapeHtml(p.code)}">Закрыть</button>`
              : `<button class="btn btn-ghost" type="button" data-open-promo="${escapeHtml(p.code)}">Открыть</button>`
          }
        </td>
      </tr>`
    )
    .join("");

  tbody.querySelectorAll("[data-close-promo]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/admin/promos/${encodeURIComponent(btn.dataset.closePromo)}/close`, {
        method: "POST",
        body: "{}",
      });
      loadPromos();
    });
  });
  tbody.querySelectorAll("[data-open-promo]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/admin/promos/${encodeURIComponent(btn.dataset.openPromo)}/open`, {
        method: "POST",
        body: "{}",
      });
      loadPromos();
    });
  });
}

function bindPromos() {
  document.getElementById("promo-add-btn").addEventListener("click", () => {
    document.getElementById("promo-create-status").textContent = "";
    document.getElementById("promo-create-form").reset();
    document.getElementById("promo-modal").hidden = false;
  });

  document.getElementById("promo-create-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const status = document.getElementById("promo-create-status");
    status.textContent = "";
    const maxUsesRaw = document.getElementById("promo-max-uses").value;
    try {
      await api("/api/admin/promos", {
        method: "POST",
        body: JSON.stringify({
          code: document.getElementById("promo-code").value,
          coins: Number(document.getElementById("promo-coins").value),
          comment: document.getElementById("promo-comment").value,
          max_uses: maxUsesRaw === "" ? null : Number(maxUsesRaw),
        }),
      });
      document.getElementById("promo-modal").hidden = true;
      loadPromos();
    } catch (err) {
      status.textContent = err.message;
    }
  });
}

async function loadAudit() {
  const data = await api("/api/admin/audit");
  const tbody = document.querySelector("#audit-table tbody");
  const empty = document.getElementById("audit-empty");
  if (!data.items.length) {
    tbody.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  tbody.innerHTML = data.items
    .map(
      (i) => `<tr>
        <td>${escapeHtml(formatDate(i.created_at))}</td>
        <td>${escapeHtml(i.action_label || i.action)}</td>
        <td>${escapeHtml(i.target_label || `${i.target_type} ${i.target_id}`)}</td>
        <td>${escapeHtml(i.detail)}</td>
      </tr>`
    )
    .join("");
}

async function boot() {
  try {
    await loadMe();
    bindTabs();
    bindLogout();
    bindModals();
    bindStats();
    bindPromos();
    await loadStats(todayISO(), todayISO());
  } catch (err) {
    if (err.message !== "unauthorized") {
      console.error(err);
    }
  }
}

boot();
