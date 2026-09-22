async function api(url, options = {}) {
  const res = await fetch(url, {
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

async function boot() {
  const title = document.getElementById("login-title");
  const note = document.getElementById("login-note");
  const status = document.getElementById("login-status");
  const form = document.getElementById("admin-login-form");

  try {
    const data = await api("/api/admin/bootstrap-status");
    if (data.needs_bootstrap) {
      title.textContent = "Создание администратора";
      note.textContent =
        "Администратора ещё нет. Введите логин и пароль — система сохранит их как единственный доступ. Другие логины потом не примутся.";
      document.getElementById("login-submit").textContent = "Создать и войти";
    }
  } catch (_) {
    /* ignore */
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "";
    const login = document.getElementById("admin-login").value.trim();
    const password = document.getElementById("admin-password").value;
    try {
      const data = await api("/api/admin/login", {
        method: "POST",
        body: JSON.stringify({ login, password }),
      });
      window.location.href = data.redirect || "/admin/";
    } catch (err) {
      status.textContent = err.message;
    }
  });
}

boot();
