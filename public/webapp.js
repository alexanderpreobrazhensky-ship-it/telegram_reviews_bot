(function () {
  const mount = document.getElementById('app');
  const path = window.location.pathname;
  const runtime = window.__WEBAPP_RUNTIME__ || {};
  const params = new URLSearchParams(window.location.search);
  const platform = params.get('channel') || 'telegram';
  const startAppPayload = params.get('startapp') || '';
  const channelLink = window.__WEBAPP_TELEGRAM_CHANNEL_LINK__ || '#';
  const logoSrc = '/logo.png';
  const PHONE_HINT = 'Введите 10 цифр';
  const PHONE_MAX_LENGTH = 10;
  let phoneValidityState = null;

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

  function extractPhoneDigits(value) {
    return String(value || '').replace(/\D/g, '');
  }

  function stripRussianPrefix(digits) {
    if (digits.length >= PHONE_MAX_LENGTH + 1 && /^[78]/.test(digits)) return digits.slice(1);
    return digits;
  }

  function sanitizePhoneDigits(value, options = {}) {
    const digits = stripRussianPrefix(extractPhoneDigits(value));
    if (!digits) return '';
    if (options.truncate === false) return digits;
    return digits.slice(0, PHONE_MAX_LENGTH);
  }

  function normalizePhone10(value) {
    const digits = extractPhoneDigits(value);
    if (!digits) return '';
    if (digits.length === PHONE_MAX_LENGTH) return digits;
    if (digits.length === PHONE_MAX_LENGTH + 1 && /^[78]/.test(digits)) return digits.slice(1);
    return digits;
  }

  function normalizePhoneInputValue(value) {
    return sanitizePhoneDigits(value);
  }

  function onlyPhoneDigits(value) {
    return normalizePhoneInputValue(value);
  }

  function countDigitsBeforeCaret(value, caret) {
    const safeValue = String(value || '');
    const safeCaret = Math.max(0, Math.min(Number(caret) || 0, safeValue.length));
    return normalizePhoneInputValue(safeValue.slice(0, safeCaret)).length;
  }

  function formatPhoneMask(rawValue) {
    const digits = normalizePhoneInputValue(rawValue);
    return { masked: digits, digits };
  }

  function phoneDigitIndexFromCaret(caret) {
    return Math.max(0, Math.min(PHONE_MAX_LENGTH, Number(caret) || 0));
  }

  function phoneCaretFromDigitIndex(index) {
    return phoneDigitIndexFromCaret(index);
  }

  function applyPhoneEdit(rawValue, selection, inputType, text) {
    const currentDigits = normalizePhoneInputValue(rawValue);
    const start = phoneCaretFromDigitIndex(selection?.start);
    const end = phoneCaretFromDigitIndex(selection?.end);
    const replacementDigits = sanitizePhoneDigits(text, { truncate: false });
    let nextDigits = currentDigits;
    let caret = start;

    if (inputType === 'deleteContentBackward') {
      if (start !== end) {
        nextDigits = `${currentDigits.slice(0, start)}${currentDigits.slice(end)}`;
        caret = start;
      } else if (start > 0) {
        nextDigits = `${currentDigits.slice(0, start - 1)}${currentDigits.slice(start)}`;
        caret = start - 1;
      }
    } else if (inputType === 'deleteContentForward') {
      if (start !== end) {
        nextDigits = `${currentDigits.slice(0, start)}${currentDigits.slice(end)}`;
      } else {
        nextDigits = `${currentDigits.slice(0, start)}${currentDigits.slice(start + 1)}`;
      }
      caret = start;
    } else if (inputType === 'deleteByCut') {
      nextDigits = `${currentDigits.slice(0, start)}${currentDigits.slice(end)}`;
      caret = start;
    } else {
      nextDigits = `${currentDigits.slice(0, start)}${replacementDigits}${currentDigits.slice(end)}`;
      caret = start + replacementDigits.length;
    }

    nextDigits = normalizePhoneInputValue(nextDigits);
    return {
      digits: nextDigits,
      caret: Math.min(caret, nextDigits.length)
    };
  }

  function createPhoneInputController(input, options = {}) {
    if (!input) return null;

    const onChange = typeof options.onChange === 'function' ? options.onChange : () => {};
    let digits = normalizePhoneInputValue(input.value);

    function render(caret = digits.length) {
      digits = normalizePhoneInputValue(digits);
      input.value = digits;
      input.dataset.phoneDigits = digits;
      if (typeof input.setSelectionRange === 'function') {
        const nextCaret = phoneCaretFromDigitIndex(Math.min(caret, digits.length));
        input.setSelectionRange(nextCaret, nextCaret);
      }
      onChange(digits);
    }

    function syncFromDom() {
      const caret = countDigitsBeforeCaret(input.value, input.selectionStart);
      digits = normalizePhoneInputValue(input.value);
      render(caret);
    }

    function applyEdit(inputType, text = '') {
      const result = applyPhoneEdit(digits, {
        start: input.selectionStart,
        end: input.selectionEnd
      }, inputType, text);
      digits = result.digits;
      render(result.caret);
    }

    function onBeforeInput(event) {
      if (event.isComposing || !event.cancelable) return;
      const supported = new Set(['insertText', 'insertFromPaste', 'deleteContentBackward', 'deleteContentForward']);
      if (!supported.has(event.inputType)) return;
      event.preventDefault();
      applyEdit(event.inputType, event.data || '');
    }

    function onInput() {
      syncFromDom();
    }

    function onPaste(event) {
      if (!event.clipboardData && !window.clipboardData) return;
      event.preventDefault();
      applyEdit('insertFromPaste', (event.clipboardData || window.clipboardData).getData('text') || '');
    }

    function onCut(event) {
      event.preventDefault();
      applyEdit('deleteByCut');
    }

    input.addEventListener('beforeinput', onBeforeInput);
    input.addEventListener('input', onInput);
    input.addEventListener('paste', onPaste);
    input.addEventListener('cut', onCut);

    render(digits.length);

    return {
      getDigits: () => digits,
      setDigits(value) {
        digits = normalizePhoneInputValue(value);
        render(digits.length);
      },
      syncFromDom,
      applyEdit,
      destroy() {
        input.removeEventListener('beforeinput', onBeforeInput);
        input.removeEventListener('input', onInput);
        input.removeEventListener('paste', onPaste);
        input.removeEventListener('cut', onCut);
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
    if (name === 'phone') return `<label data-field="phone">Телефон<input name="phone" inputmode="tel" autocomplete="tel" maxlength="10" placeholder="9991234567"/><small class="hint">Введите 10 цифр без кода страны.</small><small class="field-error"></small></label>`;
    if (name === 'visitDate') return `<label data-field="visitDate">${label(name)}<input type="date" name="visitDate"/><small class="field-error"></small></label>`;
    return `<label data-field="${name}">${label(name)}<input name="${name}"/><small class="field-error"></small></label>`;
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
      if (nextState === 'invalid') track('phone_invalid', { status: 'invalid_phone', metaJson: { digitsLength: String(digits || '').length, path } });
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
      track('request_created', { requestType: cfg.type, requestId: data.id, status: 'created' });
      renderResult(true, data.id);
    } catch {
      track('request_failed', { requestType: cfg.type, status: 'client_error' });
      renderResult(false);
    }
  }

  async function renderRequests() {
    mount.innerHTML = '<section><img class="brand-logo" src="/logo.png" alt="logo"/><h2>Мои обращения</h2><p><label data-field="phone"><input id="phone" inputmode="tel" autocomplete="tel" maxlength="10" placeholder="9991234567"/><small class="field-error"></small></label> <button id="load" class="inline">Показать</button></p><ul id="list"></ul></section>'; 
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
    onlyPhoneDigits,
    normalizePhone10,
    formatPhoneMask,
    phoneDigitIndexFromCaret,
    phoneCaretFromDigitIndex,
    applyPhoneEdit,
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
    createPhoneInputController(phoneField, {
      onChange(digits) {
        updatePhoneFieldState(form, digits, { touched: phoneTouched });
      }
    });
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
