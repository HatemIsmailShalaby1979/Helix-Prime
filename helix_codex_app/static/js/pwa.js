const BANNER_KEY = "helix-install-banner-shown";

function showInstallBanner(installEvent) {
  if (localStorage.getItem(BANNER_KEY)) {
    return;
  }
  const banner = document.getElementById("install-banner");
  if (!banner) {
    return;
  }
  banner.hidden = false;
  const button = banner.querySelector("[data-install]");
  if (button) {
    button.addEventListener("click", async () => {
      if (!installEvent) {
        return;
      }
      installEvent.prompt();
      await installEvent.userChoice;
      localStorage.setItem(BANNER_KEY, "1");
      banner.hidden = true;
    });
  }
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js");
  });
}

let deferredInstallPrompt = null;

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  showInstallBanner(event);
});

window.addEventListener("appinstalled", () => {
  localStorage.setItem(BANNER_KEY, "1");
  const banner = document.getElementById("install-banner");
  if (banner) {
    banner.hidden = true;
  }
});