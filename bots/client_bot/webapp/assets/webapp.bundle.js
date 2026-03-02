const tg = window.Telegram?.WebApp;

const baseConfig = {
  address: "",
  phone: "",
  mapUrl: "",
  yandexUrl: "",
  googleUrl: "",
  sessionMaxAgeSeconds: 86400,
};

const state = {
  step: 1,
  carKnown: false,
  sessionMaxAgeSeconds: 86400,
  sessionToken: "",
};

const sessionTokenKey = "lira_webapp_session_token";
const sessionTokenTtlMs = 10 * 60 * 1000;

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
  telegramUser: document.getElementById("telegramUser"),
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

const normalizePhone = (value) => String(value || "").replace(/\D/g, "");

const normalizeRuPhone = (value) => {
  let digits = normalizePhone(value);
  if (!digits) {
    return "";
  }
  if (digits.length === 10) {
    digits = `7${digits}`;
  } else if (digits.length === 11 && digits.startsWith("8")) {
    digits = `7${digits.slice(1)}`;
  }
  if (digits.length !== 11 || !digits.startsWith("7")) {
    return "";
  }
  return `+${digits}`;
};

const isValidRuPhone = (value) => Boolean(normalizeRuPhone(value));

const getStoredSessionToken = () => {
  try {
    const raw = localStorage.getItem(sessionTokenKey);
    if (!raw) {
      return "";
    }
    const payload = JSON.parse(raw);
    if (!payload || !payload.token || !payload.expiresAt) {
      return "";
    }
    if (Date.now() > payload.expiresAt) {
      localStorage.removeItem(sessionTokenKey);
      return "";
    }
    return payload.token;
  } catch (error) {
    return "";
  }
};

const storeSessionToken = (token) => {
  state.sessionToken = token;
  try {
    localStorage.setItem(
      sessionTokenKey,
      JSON.stringify({ token, expiresAt: Date.now() + sessionTokenTtlMs })
    );
  } catch (error) {
    console.warn("failed to store session token", error);
  }
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
    const normalizedPhone = normalizeRuPhone(phoneField.value);
    const phoneInvalid = isEmpty(normalizedPhone);
    setInvalid(descriptionField, descriptionInvalid);
    setInvalid(phoneField, phoneInvalid);
    if (descriptionInvalid) {
      setStatus("Заполните описание.", true);
      return false;
    }
    if (phoneInvalid) {
      setStatus("Введите телефон для связи.", true);
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
    phone: normalizeRuPhone(document.getElementById("phone").value),
    car_known: state.carKnown,
  };
};

const updateSubmitState = () => {
  if (!elements.submitButton) {
    return;
  }
  if (elements.submitButton.dataset.locked === "true") {
    return;
  }
  const phoneField = document.getElementById("phone");
  if (!phoneField) {
    return;
  }
  elements.submitButton.disabled = !isValidRuPhone(phoneField.value);
};

const submitForm = async (event) => {
  event.preventDefault();
  if (!validateStep(3)) {
    return;
  }
  const initData = (tg?.initData || "").trim();
  const form = buildPayload();
  if (!form.phone) {
    const message = "Введите телефон";
    setStatus(message, true);
    tg?.showAlert?.(message);
    return;
  }

  let sessionToken = state.sessionToken || getStoredSessionToken();
  if (!sessionToken && initData) {
    try {
      const sessionResp = await fetch("/api/webapp/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initData }),
      });
      const sessionPayload = await sessionResp.json();
      if (sessionPayload.ok && sessionPayload.session_token) {
        sessionToken = sessionPayload.session_token;
        storeSessionToken(sessionToken);
      }
    } catch (error) {
      console.warn("session fetch before submit failed", error);
    }
  }

  const payload = { form };
  if (sessionToken) {
    payload.session_token = sessionToken;
  } else {
    payload.initData = initData;
  }

  try {
    const response = await fetch("/api/webapp/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (response.ok && body.ok) {
      setStatus("Заявка отправлена. Мы скоро свяжемся с вами.");
      tg?.showAlert?.("Заявка отправлена");
      return;
    }
    const reason = body?.error || "unknown";
    if (reason === "phone_required") {
      setStatus("Укажите корректный телефон в формате +79991234567", true);
    } else if (reason === "session_expired") {
      setStatus("Сессия устарела. Откройте WebApp заново из бота.", true);
    } else if (reason === "invalid_init_data") {
      setStatus("Сессия недоступна. Откройте WebApp заново из бота.", true);
    } else {
      setStatus("Не удалось отправить заявку. Попробуйте ещё раз.", true);
    }
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
  state.sessionToken = getStoredSessionToken();

  const config = await fetchConfig();
  if (Number.isFinite(config.sessionMaxAgeSeconds)) {
    state.sessionMaxAgeSeconds = Number(config.sessionMaxAgeSeconds);
  }
  if (config.address && elements.addressText) {
    elements.addressText.textContent = `Адрес: ${config.address}`;
  }
  if (!tg || !tg.initData || tg.initData.length < 10) {
    setStatus("Сессия Telegram недействительна. Откройте WebApp заново из бота.", true);
    elements.submitButton.disabled = true;
    elements.submitButton.dataset.locked = "true";
  } else if (tg.initDataUnsafe?.auth_date) {
    const authDate = Number(tg.initDataUnsafe.auth_date);
    if (Number.isFinite(authDate)) {
      const ageSeconds = Math.floor(Date.now() / 1000) - authDate;
      if (ageSeconds > state.sessionMaxAgeSeconds) {
        setStatus("Сессия Telegram устарела. Откройте WebApp заново из бота.", true);
        elements.submitButton.disabled = true;
        elements.submitButton.dataset.locked = "true";
      }
    }
  }

  const user = tg?.initDataUnsafe?.user;
  if (user && elements.telegramUser) {
    const name = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
    const username = user.username ? `@${user.username}` : "";
    const parts = [name, username].filter(Boolean);
    if (parts.length) {
      elements.telegramUser.textContent = `Ваш Telegram: ${parts.join(" • ")}`;
      elements.telegramUser.hidden = false;
    }
    const nameInput = document.getElementById("name");
    if (nameInput && !nameInput.value && name) {
      nameInput.value = name;
    }
  }

  if (tg?.initData) {
    try {
      const response = await fetch("/api/webapp/session", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ initData: tg.initData }),
      });
      const payload = await response.json();
    if (payload.ok && payload.session_token) {
        storeSessionToken(payload.session_token);
    } else if (payload.error === "SESSION_INVALID") {
      const message = "Сессия Telegram недействительна. Откройте WebApp заново из бота.";
      setStatus(message, true);
        elements.submitButton.disabled = true;
        elements.submitButton.dataset.locked = "true";
        tg?.showAlert?.(message);
      }
    } catch (error) {
      console.warn("webapp session init failed", error);
    }
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
  const phoneField = document.getElementById("phone");
  if (phoneField) {
    phoneField.addEventListener("input", updateSubmitState);
    updateSubmitState();
  }
  elements.editCarButton.addEventListener("click", () => {
    state.carKnown = false;
    elements.knownCar.hidden = true;
    elements.carDetails.hidden = false;
  });
};

init();
