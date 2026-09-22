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
