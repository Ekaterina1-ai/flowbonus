/**
 * FlowBonus — мобильная навигация кабинета партнёра
 * Редактируйте отдельно от partner.js.
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
    return active ? active.dataset.tab : "scan";
  }

  function goTab(name) {
    const desktopTab = document.querySelector(`.cabinet-tab[data-tab="${name}"]`);
    if (desktopTab) desktopTab.click();
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
