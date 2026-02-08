const tg = window.Telegram?.WebApp;

const baseConfig = {
  address: "",
  phone: "",
  mapUrl: "",
  yandexUrl: "",
  googleUrl: "",
};

const state = {
  step: 1,
  carKnown: false,
};

const elements = {
  form: document.getElementById("requestForm"),
  steps: Array.from(document.querySelectorAll(".step")),
  backButton: document.getElementById("backButton"),
  nextButton: document.getElementById("nextButton"),
  submitButton: document.getElementById("submitButton"),
  status: document.getElementById("formStatus"),
  plate: document.getElementById("carPlate"),
  carDetails: document.getElementById("carDetails"),
  knownCar: document.getElementById("knownCar"),
  knownCarData: document.getElementById("knownCarData"),
  editCarButton: document.getElementById("editCarButton"),
  addressText: document.getElementById("addressText"),
};

const defaultThemes = {
  light: {
    bg: "#f3f4f6",
    text: "#151922",
    hint: "#667085",
    card: "#ffffff",
    stroke: "rgba(16, 24, 40, 0.12)",
    primary: "#2c58ff",
    primaryText: "#ffffff",
    bgAccent: "#e6ebf2",
  },
  dark: {
    bg: "#0b0f13",
    text: "#f3f6fb",
    hint: "#a7b0bd",
    card: "rgba(19, 26, 36, 0.92)",
    stroke: "rgba(255, 255, 255, 0.1)",
    primary: "#7aa6ff",
    primaryText: "#0b0f13",
    bgAccent: "#111823",
  },
};

const applyTheme = () => {
  const scheme = tg?.colorScheme === "dark" ? "dark" : "light";
  const defaults = defaultThemes[scheme];
  const params = tg?.themeParams || {};
  const root = document.documentElement;
  root.style.setProperty("--bg", params.bg_color || defaults.bg);
  root.style.setProperty("--text", params.text_color || defaults.text);
  root.style.setProperty("--hint", params.hint_color || defaults.hint);
  root.style.setProperty("--card", params.secondary_bg_color || defaults.card);
  root.style.setProperty("--stroke", params.section_separator_color || defaults.stroke);
  root.style.setProperty("--primary", params.button_color || defaults.primary);
  root.style.setProperty("--primaryText", params.button_text_color || defaults.primaryText);
  root.style.setProperty("--bg-accent", params.bg_color || defaults.bgAccent);
  if (tg?.setBackgroundColor) {
    tg.setBackgroundColor(params.bg_color || defaults.bg);
  }
  if (tg?.setHeaderColor) {
    tg.setHeaderColor(params.bg_color || defaults.bg);
  }
};

const fetchConfig = async () => {
  try {
    const response = await fetch("/WEBAPP/config.json", { cache: "no-store" });
    if (!response.ok) {
      return baseConfig;
    }
    return { ...baseConfig, ...(await response.json()) };
  } catch (error) {
    console.warn("WebApp config load failed", error);
    return baseConfig;
  }
};

const showStep = (step) => {
  state.step = step;
  elements.steps.forEach((item) => {
    item.classList.toggle("step-active", Number(item.dataset.step) === step);
  });
  elements.backButton.hidden = step === 1;
  elements.nextButton.hidden = step === elements.steps.length;
  elements.submitButton.hidden = step !== elements.steps.length;
};

const setStatus = (text, isError = false) => {
  elements.status.textContent = text;
  elements.status.style.color = isError ? "#ffb4b4" : "var(--muted)";
};

const isEmpty = (value) => !value || !String(value).trim();

const setInvalid = (element, invalid) => {
  if (!element) {
    return;
  }
  element.classList.toggle("is-invalid", invalid);
};

const validateStep = (step) => {
  if (step === 1) {
    return true;
  }
  if (step === 2) {
    const makeField = document.getElementById("carMakeModel");
    const yearField = document.getElementById("carYear");
    const plateInvalid = isEmpty(elements.plate.value);
    setInvalid(elements.plate, plateInvalid);
    if (plateInvalid) {
      setStatus("Укажите госномер.", true);
      return false;
    }
    if (!state.carKnown) {
      const makeInvalid = isEmpty(makeField.value);
      const yearInvalid = isEmpty(yearField.value);
      setInvalid(makeField, makeInvalid);
      setInvalid(yearField, yearInvalid);
      if (makeInvalid || yearInvalid) {
        setStatus("Укажите марку/модель и год.", true);
        return false;
      }
    }
    return true;
  }
  if (step === 3) {
    const descriptionField = document.getElementById("description");
    const phoneField = document.getElementById("phone");
    const descriptionInvalid = isEmpty(descriptionField.value);
    const phoneInvalid = isEmpty(phoneField.value);
    setInvalid(descriptionField, descriptionInvalid);
    setInvalid(phoneField, phoneInvalid);
    if (descriptionInvalid || phoneInvalid) {
      setStatus("Заполните описание и телефон.", true);
      return false;
    }
    return true;
  }
  return true;
};

const applyKnownCar = (data) => {
  if (!data) {
    return;
  }
  const parts = [data.car_make_model, data.car_year, data.car_mileage]
    .filter((item) => item)
    .join(" • ");
  if (!parts) {
    return;
  }
  state.carKnown = true;
  elements.knownCar.hidden = false;
  elements.knownCarData.textContent = parts;
  elements.carDetails.hidden = true;
  if (data.car_make_model) {
    document.getElementById("carMakeModel").value = data.car_make_model;
  }
  if (data.car_year) {
    document.getElementById("carYear").value = data.car_year;
  }
  if (data.car_mileage) {
    document.getElementById("carMileage").value = data.car_mileage;
  }
};

const lookupPlate = async () => {
  if (isEmpty(elements.plate.value)) {
    return;
  }
  try {
    const response = await fetch(`/api/webapp/lookup?plate=${encodeURIComponent(elements.plate.value)}`);
    const payload = await response.json();
    if (payload.ok && payload.data) {
      applyKnownCar(payload.data);
    }
  } catch (error) {
    console.warn("plate lookup failed", error);
  }
};

const buildPayload = () => {
  return {
    type: document.querySelector("input[name='requestType']:checked")?.value || "booking",
    carPlate: elements.plate.value.trim(),
    carMakeModel: document.getElementById("carMakeModel").value.trim(),
    carYear: document.getElementById("carYear").value.trim(),
    carMileage: document.getElementById("carMileage").value.trim(),
    description: document.getElementById("description").value.trim(),
    preferredDate: document.getElementById("preferredDate").value.trim(),
    preferredTime: document.getElementById("preferredTime").value.trim(),
    name: document.getElementById("name").value.trim(),
    phone: document.getElementById("phone").value.trim(),
    car_known: state.carKnown,
  };
};

const submitForm = async (event) => {
  event.preventDefault();
  if (!validateStep(3)) {
    return;
  }
  const initData = (tg?.initData || "").trim();
  if (!initData) {
    setStatus("Откройте форму через кнопку бота (WebApp). В браузере отправка недоступна.", true);
    tg?.showAlert?.("Откройте форму через кнопку бота (WebApp).");
    return;
  }
  setStatus("Отправляем заявку...");
  try {
    const response = await fetch("/api/webapp/submit", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": initData,
      },
      body: JSON.stringify({
        initData,
        form: buildPayload(),
      }),
    });
    const payload = await response.json();
    if (payload.ok) {
      setStatus("Заявка принята. Мы свяжемся с вами.");
      tg?.showAlert?.("Заявка принята. Мы свяжемся с вами.");
      return;
    }
    if (response.status === 403) {
      const message =
        payload.error === "init_data_expired"
          ? "Сессия устарела. Откройте WebApp заново из бота."
          : "Сессия Telegram недействительна. Откройте WebApp заново из бота.";
      setStatus(message, true);
      tg?.showAlert?.(message);
      return;
    }
    setStatus("Не удалось отправить. Попробуйте позже.", true);
  } catch (error) {
    console.warn("submit failed", error);
    setStatus("Не удалось отправить. Попробуйте позже.", true);
  }
};

const init = async () => {
  tg?.ready();
  tg?.expand();
  applyTheme();
  tg?.onEvent?.("themeChanged", applyTheme);
  showStep(1);

  const config = await fetchConfig();
  if (config.address && elements.addressText) {
    elements.addressText.textContent = `Адрес: ${config.address}`;
  }

  elements.backButton.addEventListener("click", () => {
    setStatus("");
    showStep(Math.max(1, state.step - 1));
  });

  elements.nextButton.addEventListener("click", () => {
    if (!validateStep(state.step)) {
      return;
    }
    setStatus("");
    showStep(Math.min(elements.steps.length, state.step + 1));
  });

  elements.form.addEventListener("submit", submitForm);

  elements.plate.addEventListener("blur", lookupPlate);
  elements.editCarButton.addEventListener("click", () => {
    state.carKnown = false;
    elements.knownCar.hidden = true;
    elements.carDetails.hidden = false;
  });
};

init();
