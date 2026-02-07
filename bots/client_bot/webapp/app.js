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

const updateTheme = () => {
  if (!tg?.themeParams) {
    return;
  }
  const params = tg.themeParams;
  if (params.bg_color) {
    document.documentElement.style.setProperty("--bg", params.bg_color);
  }
  if (params.text_color) {
    document.documentElement.style.setProperty("--text", params.text_color);
  }
};

const fetchConfig = async () => {
  try {
    const response = await fetch("./config.json", { cache: "no-store" });
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

const validateStep = (step) => {
  if (step === 1) {
    return true;
  }
  if (step === 2) {
    if (isEmpty(elements.plate.value)) {
      setStatus("Укажите госномер.", true);
      return false;
    }
    if (!state.carKnown) {
      const make = document.getElementById("carMakeModel").value;
      const year = document.getElementById("carYear").value;
      if (isEmpty(make) || isEmpty(year)) {
        setStatus("Укажите марку/модель и год.", true);
        return false;
      }
    }
    return true;
  }
  if (step === 3) {
    const description = document.getElementById("description").value;
    const name = document.getElementById("name").value;
    const phone = document.getElementById("phone").value;
    if (isEmpty(description) || isEmpty(name) || isEmpty(phone)) {
      setStatus("Заполните описание, имя и телефон.", true);
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
  setStatus("Отправляем заявку...");
  try {
    const response = await fetch("/api/webapp/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        initData: tg?.initData || "",
        form: buildPayload(),
      }),
    });
    const payload = await response.json();
    if (payload.ok) {
      setStatus("Заявка принята. Мы свяжемся с вами.");
      tg?.showAlert?.("Заявка принята. Мы свяжемся с вами.");
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
  updateTheme();
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
