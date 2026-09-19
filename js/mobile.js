/**
 * FlowBonus — мобильная логика публичных страниц
 * Редактируйте отдельно от main.js. Работает при ширине ≤ 768px.
 *
 * Меню выносится в <body>, иначе sticky/backdrop-filter хедера
 * превращают position:fixed в «полоску» без пунктов.
 */
(function () {
  const MQ = window.matchMedia("(max-width: 768px)");

  function initMobileNav() {
    const toggle = document.querySelector(".nav-toggle");
    const menu = document.querySelector(".nav-links");
    if (!toggle || !menu) return;

    const home = document.createComment("nav-links-home");
    if (!menu.previousSibling || menu.previousSibling !== home) {
      menu.parentNode.insertBefore(home, menu);
    }

    const pinToBody = () => {
      if (menu.parentElement !== document.body) {
        document.body.appendChild(menu);
      }
      menu.classList.add("m-nav-drawer");
    };

    const restore = () => {
      menu.classList.remove("is-open", "m-nav-drawer");
      toggle.setAttribute("aria-expanded", "false");
      document.body.classList.remove("m-nav-open");
      if (home.parentNode && menu.parentElement === document.body) {
        home.parentNode.insertBefore(menu, home.nextSibling);
      }
    };

    const openMenu = () => {
      pinToBody();
      menu.classList.add("is-open");
      toggle.setAttribute("aria-expanded", "true");
      document.body.classList.add("m-nav-open");
    };

    const closeMenu = () => {
      menu.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      document.body.classList.remove("m-nav-open");
    };

    const syncMode = () => {
      if (MQ.matches) {
        pinToBody();
        if (!menu.classList.contains("is-open")) {
          document.body.classList.remove("m-nav-open");
        }
      } else {
        restore();
      }
    };

    syncMode();

    toggle.addEventListener("click", (event) => {
      if (!MQ.matches) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (menu.classList.contains("is-open")) closeMenu();
      else openMenu();
    }, true);

    menu.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        if (MQ.matches) closeMenu();
      });
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && menu.classList.contains("is-open")) closeMenu();
    });

    MQ.addEventListener("change", syncMode);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMobileNav);
  } else {
    initMobileNav();
  }
})();
