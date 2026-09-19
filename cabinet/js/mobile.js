/**
 * FlowBonus — мобильная навигация ЛК клиента
 * Редактируйте отдельно от cabinet.js.
 * Синхронизирует нижнюю панель с вкладками кабинета.
 */
(function () {
  const MQ = window.matchMedia("(max-width: 768px)");

  function syncTabbar(name) {
    document.querySelectorAll(".m-tabbar .m-tab").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.tab === name);
    });
  }

  function currentTab() {
    const active = document.querySelector(".cabinet-tab.is-active");
    return active ? active.dataset.tab : "partners";
  }

  function goTab(name) {
    const desktopTab = document.querySelector(`.cabinet-tab[data-tab="${name}"]`);
    if (desktopTab) {
      desktopTab.click();
    } else if (typeof activateTab === "function") {
      activateTab(name);
    }
    syncTabbar(name);
  }

  function init() {
    const bar = document.getElementById("m-tabbar");
    if (!bar) return;

    bar.querySelectorAll(".m-tab").forEach((btn) => {
      btn.addEventListener("click", () => goTab(btn.dataset.tab));
    });

    document.querySelectorAll(".cabinet-tab").forEach((btn) => {
      btn.addEventListener("click", () => syncTabbar(btn.dataset.tab));
    });

    document.querySelectorAll("[data-goto-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        setTimeout(() => syncTabbar(btn.dataset.gotoTab || currentTab()), 0);
      });
    });

    const observer = new MutationObserver(() => syncTabbar(currentTab()));
    document.querySelectorAll(".cabinet-tab").forEach((el) => {
      observer.observe(el, { attributes: true, attributeFilter: ["class"] });
    });

    syncTabbar(currentTab());
    MQ.addEventListener("change", () => syncTabbar(currentTab()));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
