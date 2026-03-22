(function () {
  const mount = document.getElementById('app');
  const path = window.location.pathname;
  const runtime = window.__WEBAPP_RUNTIME__ || {};
  const params = new URLSearchParams(window.location.search);
  const platform = params.get('channel') || 'telegram';
  const startAppPayload = params.get('startapp') || '';
  const channelLink = window.__WEBAPP_TELEGRAM_CHANNEL_LINK__ || '#';
  const logoSrc = '/logo.png';
  const PHONE_HINT = 'Введите корректный номер (10 цифр)';
  const PHONE_MAX_LENGTH = 10;
  let phoneValidityState = null;
  let nativeContactState = null;

  const requestTypeLabels = {
    service_request: 'Заявка на сервис',
    parts_request: 'Запрос запчастей',
    consultation_request: 'Вопрос мастеру',
    warranty_request: 'Гарантийное обращение',
    data_change_request: 'Изменение данных'
  };

  const forms = {
    '/forms/service-request': { title: requestTypeLabels.service_request, endpoint: '/api/client/requests/service', type: 'service_request', fields: ['fullName', 'phone', 'wasClientBefore', 'brand', 'model', 'year', 'vin', 'description'] },
    '/forms/parts-request': { title: requestTypeLabels.parts_request, endpoint: '/api/client/requests/parts', type: 'parts_request', fields: ['fullName', 'phone', 'wasClientBefore', 'brand', 'model', 'year', 'vin', 'description'] },
    '/forms/consultation': { title: requestTypeLabels.consultation_request, endpoint: '/api/client/requests/consultation', type: 'consultation_request', fields: ['fullName', 'phone', 'wasClientBefore', 'car', 'vin', 'question'] },
    '/forms/warranty-request': { title: requestTypeLabels.warranty_request, endpoint: '/api/client/requests/warranty', type: 'warranty_request', fields: ['fullName', 'phone', 'visitDate', 'description'] },
    '/forms/data-change-request': { title: requestTypeLabels.data_change_request, endpoint: '/api/client/requests/data-change', type: 'data_change_request', fields: ['fullName', 'phone', 'changeDetails'] }
  };

  const requiredByType = {
    service_request: ['fullName', 'phone', 'wasClientBefore', 'brand', 'model', 'year', 'vin', 'description'],
    parts_request: ['fullName', 'phone', 'wasClientBefore', 'year', 'vin', 'description'],
    consultation_request: ['fullName', 'phone', 'wasClientBefore', 'car', 'vin', 'question'],
    warranty_request: ['fullName', 'phone', 'visitDate', 'description'],
    data_change_request: ['fullName', 'phone', 'changeDetails']
  };

  function normalizePhone(value) {
    return String(value || '').replace(/\D/g, '').slice(0, PHONE_MAX_LENGTH);
  }

  function normalizePhone10(value) {
    return normalizePhone(value);
  }

  function onlyPhoneDigits(value) {
    return normalizePhone(value);
  }

  function formatPhoneMask(rawValue) {
    const digits = normalizePhone(rawValue);
    return { masked: digits, digits };
  }

  function createPhoneInputController(input, options = {}) {
    if (!input) return null;

    const onChange = typeof options.onChange === 'function' ? options.onChange : () => {};

    function sync() {
      const digits = normalizePhone(input.value);
      if (input.value !== digits) input.value = digits;
      input.dataset.phoneDigits = digits;
      onChange(digits);
      return digits;
    }

    function onInput() {
      sync();
    }

    function onPaste(event) {
      const clipboard = event.clipboardData || window.clipboardData;
      if (!clipboard) return;
      event.preventDefault();
      const digits = normalizePhone(clipboard.getData('text') || '');
      if (typeof input.setRangeText === 'function') {
        const start = input.selectionStart ?? input.value.length;
        const end = input.selectionEnd ?? start;
        input.setRangeText(digits, start, end, 'end');
      } else {
        const start = input.selectionStart ?? input.value.length;
        const end = input.selectionEnd ?? start;
        input.value = `${input.value.slice(0, start)}${digits}${input.value.slice(end)}`;
      }
      sync();
    }

    input.addEventListener('input', onInput);
    input.addEventListener('paste', onPaste);

    sync();

    return {
      getDigits: () => normalizePhone(input.value),
      setDigits(value) {
        input.value = normalizePhone(value);
        sync();
      },
      syncFromDom: sync,
      destroy() {
        input.removeEventListener('input', onInput);
        input.removeEventListener('paste', onPaste);
      }
    };
  }

  function label(name) {
    const labels = { fullName: 'ФИО', phone: 'Телефон', year: 'Год', vin: 'VIN', description: 'Описание проблемы', question: 'Вопрос', changeDetails: 'Что изменилось', brand: 'Марка', model: 'Модель', car: 'Автомобиль', visitDate: 'Дата визита', wasClientBefore: 'Были у нас ранее?' };
    return labels[name] || name;
  }

  function analyticsBase() {
    return {
      channel: platform,
      platform,
      metaJson: {
        path,
        startAppPayload
      }
    };
  }

  function track(eventType, payload = {}) {
    if (String(window.navigator?.userAgent || '').toLowerCase().includes('jsdom')) return;
    const body = Object.assign(analyticsBase(), payload, { eventType });
    fetch('/api/analytics/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).catch(() => {});
  }

  function renderResult(ok, requestId) {
    mount.innerHTML = `<section class="result ${ok ? 'ok' : 'error'}"><img class="brand-logo" src="${logoSrc}" alt="logo"/><h2>${ok ? 'Ваша заявка принята' : 'Не удалось отправить заявку'}</h2><p>${ok ? 'Мы свяжемся с вами в ближайшее время.' : 'Повторите попытку позднее.'}</p>${requestId ? `<p class="result-id">Номер обращения: ${requestId}</p>` : ''}<div class="result-actions"><a class="btn" href="${channelLink}" target="_blank" rel="noopener">Подписаться на Telegram-канал</a><a class="btn ghost" href="${channelLink}" target="_blank" rel="noopener">Ссылка на Telegram-канал</a><a class="btn" href="${path}">Создать ещё одно обращение</a><a class="btn ghost" href="/">На главную</a></div></section>`;
  }

  function detectChannelIdentity() {
    if (platform === 'max') {
      const maxUserId = window.MAX?.WebApp?.initDataUnsafe?.user?.id || localStorage.getItem('webapp_max_id') || '';
      if (maxUserId) localStorage.setItem('webapp_max_id', maxUserId);
      return { sourceChannel: 'max_webapp', maxId: maxUserId || undefined };
    }
    const telegramId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || localStorage.getItem('webapp_telegram_id') || '';
    if (telegramId) localStorage.setItem('webapp_telegram_id', telegramId);
    return { sourceChannel: 'webapp', telegramId: telegramId || undefined };
  }

  function resolveStartPayloadRedirect(payload) {
    const routeByPayload = {
      form_service: '/forms/service-request',
      form_parts: '/forms/parts-request',
      form_consultation: '/forms/consultation',
      form_warranty: '/forms/warranty-request',
      form_data_change: '/forms/data-change-request',
      requests: '/requests'
    };
    return routeByPayload[payload] || '';
  }

  function renderField(name) {
    if (name === 'wasClientBefore') {
      return `<fieldset data-field="wasClientBefore"><legend>${label(name)}</legend><label><input type="radio" name="wasClientBefore" value="yes"> Да</label><label><input type="radio" name="wasClientBefore" value="no"> Нет</label><small class="field-error"></small></fieldset>`;
    }
    if (name === 'description' || name === 'question' || name === 'changeDetails') return `<label data-field="${name}">${label(name)}<textarea name="${name}"></textarea><small class="field-error"></small></label>`;
    if (name === 'phone') return `<label data-field="phone">Телефон<input name="phone" inputmode="tel" autocomplete="tel" maxlength="10" placeholder="9999999999"/><button type="button" class="inline native-contact-btn" hidden>Заполнить из профиля</button><small class="hint">Введите 10 цифр без кода страны.</small><small class="field-error"></small></label>`;
    if (name === 'visitDate') return `<label data-field="visitDate">${label(name)}<input type="date" name="visitDate"/><small class="field-error"></small></label>`;
    return `<label data-field="${name}">${label(name)}<input name="${name}"/><small class="field-error"></small></label>`;
  }


  function getNativeContactRequester() {
    const maxRequester = window.MAX?.WebApp?.requestContact;
    if (typeof maxRequester === 'function') {
      return {
        source: 'max_webapp_requestContact',
        request: () => maxRequester.call(window.MAX.WebApp)
      };
    }
    const telegramRequester = window.Telegram?.WebApp?.requestContact;
    if (typeof telegramRequester === 'function') {
      return {
        source: 'telegram_webapp_requestContact',
        request: () => telegramRequester.call(window.Telegram.WebApp)
      };
    }
    return null;
  }

  function normalizeNativeContactPayload(result, source) {
    if (!result) return null;
    if (typeof result === 'string') {
      const phoneNumber = normalizePhone10(result);
      return phoneNumber ? { phoneNumber, source } : null;
    }
    const phoneNumber = normalizePhone10(result.phoneNumber || result.phone_number || result.phone || result.contact?.phoneNumber || result.contact?.phone_number);
    if (!phoneNumber) return null;
    return {
      phoneNumber,
      source,
      raw: result
    };
  }

  async function requestNativeContact() {
    const requester = getNativeContactRequester();
    if (!requester) return null;
    try {
      const result = await requester.request();
      return normalizeNativeContactPayload(result, requester.source);
    } catch {
      return null;
    }
  }

  function clearErrors(form) {
    form.querySelectorAll('.field-error').forEach((el) => { el.textContent = ''; });
    form.querySelectorAll('[data-field]').forEach((el) => el.classList.remove('has-error'));
  }

  function setFieldError(form, field, message) {
    const box = form.querySelector(`[data-field="${field}"]`);
    if (!box) return;
    box.classList.add('has-error');
    const error = box.querySelector('.field-error');
    if (error) error.textContent = message;
  }

  function validatePayload(type, payload) {
    const errors = [];
    (requiredByType[type] || []).forEach((field) => {
      if (!String(payload[field] || '').trim()) errors.push({ field, message: `Поле «${label(field)}» обязательно` });
    });
    if (!/^\d{10}$/.test(String(payload.phone || ''))) errors.push({ field: 'phone', message: PHONE_HINT });
    return errors;
  }


  function updatePhoneFieldState(form, digits, options = {}) {
    const phoneBox = form.querySelector('[data-field="phone"]');
    const phoneError = phoneBox?.querySelector('.field-error');
    const submit = form.querySelector('button[type="submit"]');
    const isValid = /^\d{10}$/.test(String(digits || ''));
    const shouldShowError = options.forceError || (options.touched && !isValid && String(digits || '').length > 0);
    const nextState = isValid ? 'valid' : (String(digits || '').length ? 'invalid' : 'empty');
    if (nextState !== phoneValidityState) {
      if (nextState === 'valid') track('phone_valid');
      if (nextState === 'invalid') track('invalid_phone', { status: 'invalid_phone', metaJson: { digitsLength: String(digits || '').length, path } });
      phoneValidityState = nextState;
    }

    phoneBox?.classList.toggle('has-error', shouldShowError);
    if (phoneError) phoneError.textContent = shouldShowError ? PHONE_HINT : '';
    if (submit) submit.disabled = !isValid;
    return isValid;
  }

  async function submitForm(event, cfg) {
    event.preventDefault();
    const form = event.target;
    if (form.dataset.submitting === '1') return;
    clearErrors(form);
    const globalError = form.querySelector('.form-error');
    const submit = form.querySelector('button[type="submit"]');
    globalError.textContent = '';

    const payload = Object.fromEntries(new FormData(form).entries());
    payload.phone = normalizePhone10(payload.phone);
    if (nativeContactState?.phoneNumber) {
      payload.phone = nativeContactState.phoneNumber;
      payload.contactSource = nativeContactState.source;
      payload.nativeContact = nativeContactState;
    }
    Object.assign(payload, detectChannelIdentity());

    const phoneIsValid = updatePhoneFieldState(form, payload.phone, { touched: true, forceError: !/^\d{10}$/.test(String(payload.phone || '')) });
    const errors = validatePayload(cfg.type, payload);
    if (!phoneIsValid || errors.length) {
      errors.forEach((err) => setFieldError(form, err.field, err.message));
      globalError.textContent = 'Пожалуйста, исправьте ошибки в форме.';
      return;
    }

    form.dataset.submitting = '1';
    submit.disabled = true;
    submit.textContent = 'Отправка...';
    track('submit_attempt', { requestType: cfg.type, metaJson: { endpoint: cfg.endpoint } });
    try {
      const response = await fetch(cfg.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'REQUEST_FAILED');
      track('submit_success', { requestType: cfg.type, requestId: data.id, status: 'created' });
      renderResult(true, data.id);
    } catch {
      track('request_failed', { requestType: cfg.type, status: 'client_error' });
      renderResult(false);
    }
  }

  async function renderRequests() {
    mount.innerHTML = '<section><img class="brand-logo" src="/logo.png" alt="logo"/><h2>Мои обращения</h2><p><label data-field="phone"><input id="phone" inputmode="tel" autocomplete="tel" maxlength="10" placeholder="9999999999"/><small class="field-error"></small></label> <button id="load" class="inline">Показать</button></p><ul id="list"></ul></section>'; 
    const input = document.getElementById('phone');
    const error = mount.querySelector('[data-field="phone"] .field-error');
    const phoneMask = createPhoneInputController(input, {
      onChange(digits) {
        error.textContent = /^\d{10}$/.test(digits) ? '' : (String(digits || '').length ? PHONE_HINT : '');
      }
    });
    const list = document.getElementById('list');
    document.getElementById('load').onclick = async () => {
      const digits = phoneMask.getDigits();
      error.textContent = '';
      if (!/^\d{10}$/.test(digits)) {
        error.textContent = PHONE_HINT;
        list.innerHTML = '';
        return;
      }
      const response = await fetch(`/api/client/requests?phone=${encodeURIComponent(digits)}`);
      const data = await response.json();
      list.innerHTML = data.items.map((item) => `<li>${requestTypeLabels[item.requestType] || item.requestType} | ${item.status} | ${new Date(item.createdAt).toLocaleString()} | ${item.summary}</li>`).join('') || '<li>Ничего не найдено</li>';
    };
  }

  async function renderRecommendations() {
    mount.innerHTML = '<section><img class="brand-logo" src="/logo.png" alt="logo"/><h2>Рекомендации</h2><p id="auth"></p><ul id="recs"></ul></section>';
    if (platform === 'max') {
      document.getElementById('auth').textContent = 'Рекомендации в MAX пока не активированы. Раздел оставлен как неактивный foundation.';
      return;
    }
    const telegramId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || localStorage.getItem('webapp_telegram_id') || '';
    if (!telegramId) {
      document.getElementById('auth').textContent = 'Раздел доступен только авторизованным пользователям Telegram WebApp.';
      return;
    }
    localStorage.setItem('webapp_telegram_id', telegramId);
    const response = await fetch(`/api/client/recommendations?telegramId=${encodeURIComponent(telegramId)}`);
    const data = await response.json();
    if (!Array.isArray(data.items) || !data.items.length) {
      document.getElementById('auth').textContent = 'Рекомендации появятся после синхронизации с 1С.';
      return;
    }
    document.getElementById('recs').innerHTML = data.items.map((item) => `<li><b>${item.severity}</b>: ${item.text} <button class="inline" data-id="${item.id}">Хочу устранить</button></li>`).join('');
    mount.querySelectorAll('button[data-id]').forEach((button) => {
      button.onclick = async () => {
        await fetch(`/api/client/recommendations/${button.dataset.id}/interest`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ telegramId }) });
        button.textContent = 'Заявка отправлена';
        button.disabled = true;
      };
    });
  }

  window.__WEBAPP_TEST_API__ = {
    PHONE_HINT,
    normalizePhone,
    onlyPhoneDigits,
    normalizePhone10,
    formatPhoneMask,
    createPhoneInputController,
    validatePayload
  };

  if (forms[path]) {
    const cfg = forms[path];
    track('webapp_opened', { requestType: cfg.type });
    track('form_started', { requestType: cfg.type });
    mount.innerHTML = `<section><img class="brand-logo" src="${logoSrc}" alt="logo"/><h2>${cfg.title}</h2><form id="request-form"><p class="form-error"></p>${cfg.fields.map(renderField).join('')}<button type="submit">Отправить</button></form></section>`;
    const form = document.getElementById('request-form');
    const phoneField = form.querySelector('input[name="phone"]');
    let phoneTouched = false;
    const phoneController = createPhoneInputController(phoneField, {
      onChange(digits) {
        if (nativeContactState?.phoneNumber !== digits) nativeContactState = null;
        updatePhoneFieldState(form, digits, { touched: phoneTouched });
      }
    });
    const nativeContactButton = form.querySelector('.native-contact-btn');
    const nativeContactRequester = getNativeContactRequester();
    if (nativeContactButton && nativeContactRequester) {
      nativeContactButton.hidden = false;
      nativeContactButton.addEventListener('click', async () => {
        nativeContactButton.disabled = true;
        nativeContactButton.textContent = 'Запрашиваю...';
        const contact = await requestNativeContact();
        nativeContactButton.disabled = false;
        nativeContactButton.textContent = contact ? 'Телефон получен' : 'Заполнить из профиля';
        if (!contact) return;
        nativeContactState = contact;
        phoneController.setDigits(contact.phoneNumber);
        phoneTouched = true;
        updatePhoneFieldState(form, contact.phoneNumber, { touched: true });
      });
    }
    phoneField.addEventListener('blur', () => {
      phoneTouched = true;
      updatePhoneFieldState(form, phoneField.value, { touched: true });
    });
    updatePhoneFieldState(form, phoneField.value);
    form.addEventListener('submit', (e) => {
      phoneTouched = true;
      submitForm(e, cfg);
    });
    return;
  }

  track('webapp_opened');
  if (path === '/requests') return renderRequests();
  if (path === '/recommendations') return renderRecommendations();

  if (path === '/' && startAppPayload) {
    const redirectPath = resolveStartPayloadRedirect(startAppPayload);
    if (redirectPath) {
      const next = new URL(redirectPath, window.location.origin);
      next.searchParams.set('channel', platform);
      if (startAppPayload) next.searchParams.set('startapp', startAppPayload);
      window.location.replace(next.toString());
      return;
    }
  }

  mount.innerHTML = '<section><img class="brand-logo" src="/logo.png" alt="logo"/><h1>Автосервис</h1><p>Создайте обращение, отследите статус и посмотрите рекомендации.</p></section>';
})();
