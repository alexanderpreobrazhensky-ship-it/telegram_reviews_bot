const tg = window.Telegram?.WebApp;

const defaultAddress = "Удмуртская 10";

const buildMapUrls = (address) => {
  const encoded = encodeURIComponent(address);
  return {
    yandexUrl: `https://yandex.ru/maps/?text=${encoded}`,
    googleUrl: `https://www.google.com/maps/search/?api=1&query=${encoded}`,
  };
};

const baseConfig = {
  address: defaultAddress,
  phone: "",
  mapUrl: "",
  ...buildMapUrls(defaultAddress),
};

const updateTheme = () => {
  if (!tg?.themeParams) {
    return;
  }
  const params = tg.themeParams;
  if (params.bg_color) {
    document.documentElement.style.setProperty("--tg-bg", params.bg_color);
  }
  if (params.text_color) {
    document.documentElement.style.setProperty("--tg-text", params.text_color);
  }
};

const fetchConfig = async () => {
  try {
    const response = await fetch("/webapp/config.json", { cache: "no-store" });
    if (!response.ok) {
      return baseConfig;
    }
    const data = await response.json();
    const address = data.address || baseConfig.address;
    return {
      ...baseConfig,
      ...buildMapUrls(address),
      address,
      phone: data.phone || baseConfig.phone,
      mapUrl: data.mapUrl || data.map_url || baseConfig.mapUrl,
      yandexUrl: data.yandexUrl || data.yandex_url || baseConfig.yandexUrl,
      googleUrl: data.googleUrl || data.google_url || baseConfig.googleUrl,
    };
  } catch (error) {
    console.warn("WebApp config load failed", error);
    return baseConfig;
  }
};

const sendAction = (action) => {
  const payload = {
    v: 1,
    action,
    ts: Date.now(),
  };
  if (tg?.sendData) {
    tg.sendData(JSON.stringify(payload));
  } else {
    console.log("sendData", payload);
  }
};

const openLink = (url) => {
  if (!url) return;
  if (tg?.openLink) {
    tg.openLink(url);
  } else {
    window.open(url, "_blank");
  }
};

const closeWebApp = () => {
  if (tg?.close) {
    setTimeout(() => tg.close(), 200);
  }
};

const init = async () => {
  tg?.ready();
  tg?.expand();
  updateTheme();

  const config = await fetchConfig();
  const addressText = document.getElementById("addressText");
  if (addressText) {
    addressText.textContent = `Адрес: ${config.address}`;
  }

  const callButton = document.getElementById("callButton");
  if (callButton) {
    callButton.hidden = !config.phone;
  }

  const buttons = document.querySelectorAll("[data-action]");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.action;
      if (!action) return;
      sendAction(action);

      if (action === "call" && config.phone) {
        const telLink = `tel:${config.phone.replace(/[^\d+]/g, "")}`;
        openLink(telLink);
        closeWebApp();
        return;
      }
      if (action === "route") {
        openLink(config.mapUrl || config.yandexUrl || config.googleUrl);
        closeWebApp();
        return;
      }
      closeWebApp();
    });
  });
};

init();
