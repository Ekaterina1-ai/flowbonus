document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.querySelector(".nav-links");

  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const open = menu.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  const reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.16, rootMargin: "0px 0px -8% 0px" }
    );
    reveals.forEach((el) => observer.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("is-visible"));
  }

  initModals();
  initAuthForms();
  initHeroWipe();
  initFaq();
  initNetworkShowcase();

  if (new URLSearchParams(location.search).get("login") === "1") {
    const loginModal = document.getElementById("client-login");
    if (loginModal) {
      loginModal.hidden = false;
      loginModal.setAttribute("aria-hidden", "false");
      document.body.classList.add("modal-open");
    }
  }

  const params = new URLSearchParams(location.search);
  if (params.get("login") === "partner") {
    const loginModal = document.getElementById("client-login");
    if (loginModal) {
      const partnerRoleBtn = document.querySelector('[data-login-role="partner"]');
      if (partnerRoleBtn) partnerRoleBtn.click();
      loginModal.hidden = false;
      loginModal.setAttribute("aria-hidden", "false");
      document.body.classList.add("modal-open");
    }
  }
});

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "same-origin",
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || "Ошибка запроса");
  }
  return data;
}

function initAuthForms() {
  document.querySelectorAll("[data-login-role]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const role = btn.dataset.loginRole;
      document.querySelectorAll("[data-login-role]").forEach((b) => {
        b.classList.toggle("is-active", b === btn);
      });
      const input = document.getElementById("login-role-input");
      if (input) input.value = role;
      const hint = document.getElementById("login-role-hint");
      if (hint) {
        hint.textContent =
          role === "partner"
            ? "Вход партнёра: телефон и пароль из регистрации бизнеса."
            : "Логин — номер телефона, пароль — из регистрации.";
      }
    });
  });

  const registerForm = document.getElementById("client-register-form");
  if (registerForm) {
    registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const errorEl = document.getElementById("client-register-error");
      const button = registerForm.querySelector('button[type="submit"]');
      const fd = new FormData(registerForm);
      errorEl.textContent = "";
      if (!fd.get("accept_terms")) {
        errorEl.textContent = "Нужно принять пользовательское соглашение и оферту.";
        return;
      }
      if (!fd.get("accept_pd")) {
        errorEl.textContent = "Нужно дать согласие на обработку персональных данных.";
        return;
      }
      button.disabled = true;
      try {
        const data = await api("/api/register", {
          method: "POST",
          body: JSON.stringify({
            fio: fd.get("fio"),
            phone: fd.get("phone"),
            email: fd.get("email"),
            city: fd.get("city"),
            password: fd.get("password"),
            password2: fd.get("password2"),
            accept_terms: true,
            accept_pd: true,
            accept_marketing: Boolean(fd.get("accept_marketing")),
          }),
        });
        window.location.href = data.redirect || "/cabinet/";
      } catch (err) {
        errorEl.textContent = err.message;
        button.disabled = false;
      }
    });
  }

  const loginForm = document.getElementById("client-login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const errorEl = document.getElementById("client-login-error");
      const button = loginForm.querySelector('button[type="submit"]');
      const fd = new FormData(loginForm);
      const role = fd.get("role") || "client";
      errorEl.textContent = "";
      button.disabled = true;
      try {
        const endpoint = role === "partner" ? "/api/partner/login" : "/api/login";
        const data = await api(endpoint, {
          method: "POST",
          body: JSON.stringify({
            phone: fd.get("phone"),
            password: fd.get("password"),
          }),
        });
        window.location.href = data.redirect || (role === "partner" ? "/partner-cabinet/" : "/cabinet/");
      } catch (err) {
        errorEl.textContent = err.message;
        button.disabled = false;
      }
    });
  }

  const partnerForm = document.getElementById("partner-register-form");
  if (partnerForm) {
    partnerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const errorEl = document.getElementById("partner-register-error");
      const button = partnerForm.querySelector('button[type="submit"]');
      const fd = new FormData(partnerForm);
      if (errorEl) errorEl.textContent = "";
      if (!fd.get("accept_terms")) {
        if (errorEl) {
          errorEl.textContent = "Нужно принять пользовательское соглашение и оферту партнёру.";
        }
        return;
      }
      if (!fd.get("accept_pd")) {
        if (errorEl) {
          errorEl.textContent = "Нужно дать согласие на обработку персональных данных.";
        }
        return;
      }
      button.disabled = true;
      try {
        const data = await api("/api/partner/register", {
          method: "POST",
          body: JSON.stringify({
            business: fd.get("business"),
            category: fd.get("category"),
            name: fd.get("name"),
            phone: fd.get("phone"),
            city: fd.get("city"),
            address: fd.get("address"),
            comment: fd.get("comment"),
            password: fd.get("password"),
            password2: fd.get("password2"),
            accept_terms: true,
            accept_pd: true,
            accept_marketing: Boolean(fd.get("accept_marketing")),
          }),
        });
        window.location.href = data.redirect || "/partner-cabinet/";
      } catch (err) {
        if (errorEl) errorEl.textContent = err.message;
        button.disabled = false;
      }
    });
  }
}

function initModals() {
  const openModal = (id) => {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    const firstInput = modal.querySelector("input, button, select, textarea");
    if (firstInput) firstInput.focus();
  };

  const closeModal = (modal) => {
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    if (!document.querySelector(".modal:not([hidden])")) {
      document.body.classList.remove("modal-open");
    }
  };

  document.querySelectorAll("[data-open-modal]").forEach((el) => {
    el.addEventListener("click", (event) => {
      const id = el.getAttribute("data-open-modal");
      if (!id) return;
      event.preventDefault();
      // close current modal if opening another from inside
      const current = el.closest(".modal");
      if (current && current.id !== id) closeModal(current);
      openModal(id);
    });
  });

  document.querySelectorAll(".modal").forEach((modal) => {
    modal.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.addEventListener("click", () => closeModal(modal));
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll(".modal:not([hidden])").forEach((modal) => closeModal(modal));
  });

  if (location.hash === "#start" || location.hash === "#join") {
    const target = document.getElementById(location.hash.slice(1));
    if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function initFaq() {
  const items = document.querySelectorAll(".faq-item");
  if (!items.length) return;

  items.forEach((item) => {
    item.addEventListener("toggle", () => {
      if (!item.open) return;
      items.forEach((other) => {
        if (other !== item) other.open = false;
      });
    });
  });

  const hash = location.hash.slice(1);
  if (hash) {
    const target = document.getElementById(hash);
    if (target && target.classList.contains("faq-item")) {
      target.open = true;
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pluralRu(n, one, few, many) {
  const abs = Math.abs(Number(n)) || 0;
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

function bindNetworkCarousel(card) {
  const images = [...card.querySelectorAll(".network-carousel-track img")];
  if (images.length <= 1) return;
  let index = 0;
  let timer = null;
  const dots = card.querySelectorAll(".network-carousel-dots button");
  const show = (next) => {
    index = (next + images.length) % images.length;
    images.forEach((img, i) => img.classList.toggle("is-active", i === index));
    dots.forEach((dot, i) => dot.classList.toggle("is-active", i === index));
  };
  const restart = () => {
    clearInterval(timer);
    timer = setInterval(() => show(index + 1), 4500);
  };
  card.querySelector(".network-carousel-btn.prev")?.addEventListener("click", () => {
    show(index - 1);
    restart();
  });
  card.querySelector(".network-carousel-btn.next")?.addEventListener("click", () => {
    show(index + 1);
    restart();
  });
  dots.forEach((dot, i) =>
    dot.addEventListener("click", () => {
      show(i);
      restart();
    })
  );
  restart();
}

function renderNetworkCard(partner) {
  const images = (partner.images && partner.images.length
    ? partner.images
    : [partner.image || "/assets/partners/norma-tela.png"]
  ).filter(Boolean);
  const spend = Math.max(1, Number(partner.spend_coins) || 1);
  const city = partner.city || "Город уточняется";
  const category = partner.category || "Партнёр";
  const desc = (partner.description || "").trim();
  const name = partner.name || "Партнёр";

  const gallery = images
    .map(
      (src, i) =>
        `<img src="${escapeHtml(src)}" alt="${escapeHtml(name)}" class="${i === 0 ? "is-active" : ""}" loading="lazy" />`
    )
    .join("");

  const controls =
    images.length > 1
      ? `<button class="network-carousel-btn prev" type="button" aria-label="Предыдущее фото">‹</button>
         <button class="network-carousel-btn next" type="button" aria-label="Следующее фото">›</button>
         <div class="network-carousel-dots">
           ${images
             .map(
               (_, i) =>
                 `<button type="button" class="${i === 0 ? "is-active" : ""}" aria-label="Фото ${i + 1}"></button>`
             )
             .join("")}
         </div>`
      : "";

  return `<article class="network-card reveal is-visible">
    <div class="network-visual">
      <div class="network-carousel-track">${gallery}</div>
      ${controls}
      <span class="network-chip network-chip-category">${escapeHtml(category)}</span>
      <span class="network-chip network-chip-city">${escapeHtml(city)}</span>
    </div>
    <div class="network-body">
      <h3>${escapeHtml(name)}</h3>
      ${desc ? `<p class="network-desc">${escapeHtml(desc)}</p>` : ""}
      <div class="network-divider" aria-hidden="true">
        <span class="network-divider-line"></span>
        <svg class="network-divider-ornament" viewBox="0 0 72 22" fill="none" xmlns="http://www.w3.org/2000/svg">
          <ellipse cx="24" cy="11" rx="11" ry="6.2" stroke="currentColor" stroke-width="1.15"/>
          <ellipse cx="48" cy="11" rx="11" ry="6.2" stroke="currentColor" stroke-width="1.15"/>
          <path d="M31.5 6.2 40.5 15.8M40.5 6.2 31.5 15.8" stroke="currentColor" stroke-width="1.15" stroke-linecap="round"/>
        </svg>
        <span class="network-divider-line"></span>
      </div>
      <div class="network-spend" title="Сколько монет клиент может списать у партнёра за визит">
        <span class="network-spend-label">Клиент может списать за визит</span>
        <div class="network-spend-value" data-spend="${spend}">
          <strong>${spend}</strong>
          <img src="/assets/coin.svg" alt="" />
        </div>
      </div>
    </div>
  </article>`;
}

async function fetchLandingSnapshot() {
  const res = await fetch("/api/landing", { credentials: "same-origin" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Не удалось загрузить сеть");
  return data;
}

function applyNetworkClients(clientsCount) {
  const clientsEl = document.getElementById("network-clients");
  const wordEl = document.getElementById("network-clients-word");
  const stat = document.getElementById("network-stat");
  if (clientsEl) clientsEl.textContent = String(clientsCount);
  if (wordEl) {
    wordEl.textContent = pluralRu(clientsCount, "клиент", "клиента", "клиентов");
  }
  if (stat) {
    stat.hidden = false;
    stat.setAttribute(
      "aria-label",
      `Клиентов в FlowBonus: ${clientsCount}`
    );
  }
}

function bindNetworkStatWipe(tile) {
  if (!tile || tile.dataset.wipeBound === "1") return;
  tile.dataset.wipeBound = "1";

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    tile.style.setProperty("--wipe-x", "50%");
    tile.style.setProperty("--wipe-y", "50%");
    tile.style.setProperty("--wipe-size", "140px");
    tile.classList.add("is-open");
    return;
  }

  let pointerActive = false;
  let rafId = 0;
  let autoPhase = 0;

  const setWipe = (xPct, yPct, sizePx) => {
    tile.style.setProperty("--wipe-x", `${xPct}%`);
    tile.style.setProperty("--wipe-y", `${yPct}%`);
    tile.style.setProperty("--wipe-size", `${Math.max(0, sizePx)}px`);
  };

  const autoLoop = (time) => {
    if (!pointerActive) {
      autoPhase = time * 0.0011;
      const pulse = (Math.sin(autoPhase) + 1) / 2;
      const size = 8 + pulse * 16;
      setWipe(52 + Math.sin(autoPhase * 0.7) * 10, 48 + Math.cos(autoPhase * 0.9) * 8, size);
      tile.classList.toggle("is-open", size > 22);
    }
    rafId = requestAnimationFrame(autoLoop);
  };

  const openAt = (event) => {
    const rect = tile.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = ((event.clientY - rect.top) / rect.height) * 100;
    const size = Math.max(rect.width, rect.height) * 1.35;
    setWipe(x, y, size);
    tile.classList.add("is-open");
  };

  tile.addEventListener("pointerenter", (event) => {
    pointerActive = true;
    openAt(event);
  });
  tile.addEventListener("pointermove", (event) => {
    if (!pointerActive) return;
    openAt(event);
  });
  tile.addEventListener("pointerleave", () => {
    pointerActive = false;
    tile.classList.remove("is-open");
  });
  tile.addEventListener("focus", () => {
    pointerActive = true;
    setWipe(50, 50, 160);
    tile.classList.add("is-open");
  });
  tile.addEventListener("blur", () => {
    pointerActive = false;
    tile.classList.remove("is-open");
  });

  rafId = requestAnimationFrame(autoLoop);
  tile.addEventListener(
    "remove",
    () => {
      cancelAnimationFrame(rafId);
    },
    { once: true }
  );
}

async function initNetworkShowcase() {
  const grid = document.getElementById("network-grid");
  if (!grid) return;

  const section = document.getElementById("network");
  const empty = document.getElementById("network-empty");
  const title = document.getElementById("network-title");
  const lead = document.getElementById("network-lead");

  const render = (data) => {
    const partners = data.partners || [];
    const clientsCount = Number(data.clients_count) || 0;
    applyNetworkClients(clientsCount);
    bindNetworkStatWipe(document.getElementById("network-stat"));

    if (!partners.length) {
      grid.innerHTML = "";
      if (empty) empty.hidden = false;
      if (title) title.textContent = "Уже с нами";
      if (lead) lead.textContent = "Скоро добавятся новые точки в вашем городе!";
      return;
    }

    if (empty) empty.hidden = true;
    if (title) title.textContent = "Уже с нами";
    if (lead) {
      lead.textContent =
        partners.length === 1
          ? "Скоро добавятся новые точки в вашем городе!"
          : "Реальные точки, куда можно прийти с монетами FlowBonus.";
    }

    grid.classList.toggle("is-single", partners.length === 1);
    grid.innerHTML = partners.map(renderNetworkCard).join("");
    grid.querySelectorAll(".network-card").forEach(bindNetworkCarousel);
  };

  const partnerSignature = (partners) =>
    (partners || [])
      .map((p) => `${p.partner_id || p.id}:${(p.images || []).length}:${p.spend_coins}:${p.name}`)
      .join("|");

  try {
    const first = await fetchLandingSnapshot();
    grid.dataset.signature = partnerSignature(first.partners);
    render(first);

    setInterval(async () => {
      try {
        const data = await fetchLandingSnapshot();
        applyNetworkClients(Number(data.clients_count) || 0);
        const signature = partnerSignature(data.partners);
        if (grid.dataset.signature !== signature) {
          grid.dataset.signature = signature;
          render(data);
        }
      } catch (_) {
        /* тихо: обновится при следующей загрузке страницы */
      }
    }, 30000);
  } catch (err) {
    console.error(err);
    if (section) section.hidden = true;
  }
}

function initHeroWipe() {
  const hero = document.querySelector("[data-hero-wipe]");
  if (!hero) return;

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    hero.style.setProperty("--wipe-x", "65%");
    hero.style.setProperty("--wipe-y", "40%");
    hero.style.setProperty("--wipe-size", "420px");
    hero.classList.add("is-revealed");
    return;
  }

  let pointerActive = false;
  let autoPhase = 0;
  let rafId = 0;

  const setWipe = (xPct, yPct, sizePx) => {
    hero.style.setProperty("--wipe-x", `${xPct}%`);
    hero.style.setProperty("--wipe-y", `${yPct}%`);
    hero.style.setProperty("--wipe-size", `${Math.max(0, sizePx)}px`);
  };

  const autoLoop = (time) => {
    if (!pointerActive) {
      autoPhase = time * 0.00035;
      const rect = hero.getBoundingClientRect();
      const x = 68 + Math.sin(autoPhase) * 18;
      const y = 38 + Math.cos(autoPhase * 0.85) * 16;
      const pulse = (Math.sin(autoPhase * 1.4) + 1) / 2;
      const size = Math.min(rect.width, rect.height) * (0.28 + pulse * 0.42);
      setWipe(x, y, size);
      hero.classList.toggle("is-revealed", size > 120);
    }
    rafId = requestAnimationFrame(autoLoop);
  };

  const onMove = (event) => {
    const rect = hero.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = ((event.clientY - rect.top) / rect.height) * 100;
    const size = Math.max(rect.width, rect.height) * 0.55;
    setWipe(x, y, size);
    hero.classList.add("is-revealed");
  };

  hero.addEventListener("pointerenter", () => {
    pointerActive = true;
  });

  hero.addEventListener("pointerleave", () => {
    pointerActive = false;
  });

  hero.addEventListener("pointermove", onMove);

  setWipe(72, 42, 0);
  requestAnimationFrame(() => {
    setWipe(72, 42, 180);
    hero.classList.add("is-revealed");
  });
  rafId = requestAnimationFrame(autoLoop);

  window.addEventListener(
    "beforeunload",
    () => {
      if (rafId) cancelAnimationFrame(rafId);
    },
    { once: true }
  );
}
