(function () {
  const mount = document.getElementById('app');
  const path = window.location.pathname;
  const runtime = window.__WEBAPP_RUNTIME__ || {};
  const params = new URLSearchParams(window.location.search);
  const platform = params.get('channel') || 'telegram';
  const startAppPayload = params.get('startapp') || '';
  const channelLink = window.__WEBAPP_TELEGRAM_CHANNEL_LINK__ || '#';
  const logoSrc = '/logo.png';
  const PHONE_MASK_TEMPLATE = '+7 (___) ___-__-__';
  const PHONE_DIGIT_POSITIONS = [4, 5, 6, 9, 10, 11, 13, 14, 16, 17];
  const PHONE_INPUT_TYPES = new Set(['insertText', 'insertFromPaste', 'deleteContentBackward', 'deleteContentForward', 'deleteByCut']);

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

  function onlyPhoneDigits(value) {
    const raw = String(value || '');
    const cleaned = raw.replace(/\D/g, '');
    if (!cleaned) return '';
    if (cleaned.length === 1 && cleaned === '7' && /^\s*\+7(?:\D|$)/.test(raw)) return '';
    if (cleaned.length === 1 && cleaned === '8' && /^\s*\+8(?:\D|$)/.test(raw)) return '';
    const normalized = cleaned.length > 10 && (cleaned.startsWith('7') || cleaned.startsWith('8')) ? cleaned.slice(1) : cleaned;
    return normalized.slice(0, 10);
  }

  function formatPhoneMask(rawValue) {
    const digits = onlyPhoneDigits(rawValue);
    const chars = PHONE_MASK_TEMPLATE.split('');
    for (let index = 0; index < PHONE_DIGIT_POSITIONS.length; index += 1) {
      chars[PHONE_DIGIT_POSITIONS[index]] = digits[index] || '_';
    }
    return { masked: chars.join(''), digits };
  }

  function clampPhoneDigitIndex(index) {
    return Math.max(0, Math.min(PHONE_DIGIT_POSITIONS.length, Number(index) || 0));
  }

  function phoneDigitIndexFromCaret(caret) {
    const safeCaret = Math.max(0, Number(caret) || 0);
    return PHONE_DIGIT_POSITIONS.filter((position) => position < safeCaret).length;
  }

  function phoneCaretFromDigitIndex(index) {
    const safeIndex = clampPhoneDigitIndex(index);
    if (safeIndex >= PHONE_DIGIT_POSITIONS.length) return PHONE_MASK_TEMPLATE.length;
    return PHONE_DIGIT_POSITIONS[safeIndex];
  }

  function resolvePhoneSelectionRange(input) {
    const rawStart = typeof input.selectionStart === 'number' ? input.selectionStart : phoneCaretFromDigitIndex(0);
    const rawEnd = typeof input.selectionEnd === 'number' ? input.selectionEnd : rawStart;
    const start = clampPhoneDigitIndex(phoneDigitIndexFromCaret(rawStart));
    const end = clampPhoneDigitIndex(phoneDigitIndexFromCaret(rawEnd));
    return start <= end ? { start, end } : { start: end, end: start };
  }

  function applyPhoneEdit(digits, selection, inputType, text) {
    const currentDigits = onlyPhoneDigits(digits);
    const start = clampPhoneDigitIndex(selection?.start);
    const end = clampPhoneDigitIndex(selection?.end);
    let nextDigits = currentDigits;
    let caretDigitIndex = start;

    if (inputType === 'deleteContentBackward') {
      if (start !== end) {
        nextDigits = currentDigits.slice(0, start) + currentDigits.slice(end);
      } else if (start > 0) {
        nextDigits = currentDigits.slice(0, start - 1) + currentDigits.slice(start);
        caretDigitIndex = start - 1;
      }
    } else if (inputType === 'deleteContentForward') {
      if (start !== end) {
        nextDigits = currentDigits.slice(0, start) + currentDigits.slice(end);
      } else {
        nextDigits = currentDigits.slice(0, start) + currentDigits.slice(start + 1);
      }
    } else if (inputType === 'deleteByCut') {
      nextDigits = currentDigits.slice(0, start) + currentDigits.slice(end);
    } else {
      const insertedDigits = onlyPhoneDigits(text);
      nextDigits = `${currentDigits.slice(0, start)}${insertedDigits}${currentDigits.slice(end)}`.slice(0, 10);
      caretDigitIndex = Math.min(start + insertedDigits.length, nextDigits.length);
    }

    return {
      digits: onlyPhoneDigits(nextDigits),
      caret: phoneCaretFromDigitIndex(caretDigitIndex)
    };
  }

  function createPhoneInputController(input) {
    if (!input) return null;

    let digits = onlyPhoneDigits(input.value);

    function render(caret) {
      const { masked, digits: normalizedDigits } = formatPhoneMask(digits);
      digits = normalizedDigits;
      input.value = masked;
      input.dataset.phoneDigits = digits;
      const nextCaret = typeof caret === 'number' ? caret : phoneCaretFromDigitIndex(Math.min(digits.length, PHONE_DIGIT_POSITIONS.length));
      if (typeof input.setSelectionRange === 'function') {
        input.setSelectionRange(nextCaret, nextCaret);
      }
    }

    function syncFromDom() {
      digits = onlyPhoneDigits(input.value);
      const selection = resolvePhoneSelectionRange(input);
      render(phoneCaretFromDigitIndex(Math.min(selection.start, digits.length)));
    }

    function applyEdit(inputType, text) {
      const selection = resolvePhoneSelectionRange(input);
      const result = applyPhoneEdit(digits, selection, inputType, text);
      digits = result.digits;
      render(result.caret);
    }

    function ensureCaretAfterPrefix() {
      if (typeof input.selectionStart !== 'number' || typeof input.setSelectionRange !== 'function') return;
      if (input.selectionStart < phoneCaretFromDigitIndex(0) || input.selectionEnd < phoneCaretFromDigitIndex(0)) {
        const caret = phoneCaretFromDigitIndex(Math.min(digits.length, PHONE_DIGIT_POSITIONS.length));
        input.setSelectionRange(caret, caret);
      }
    }

    function onBeforeInput(event) {
      if (!PHONE_INPUT_TYPES.has(event.inputType)) return;
      event.preventDefault();
      const text = event.inputType === 'insertFromPaste'
        ? (event.dataTransfer?.getData('text') || event.data || '')
        : (event.data || '');
      applyEdit(event.inputType, text);
    }

    function onInput() {
      syncFromDom();
    }

    function onPaste(event) {
      event.preventDefault();
      applyEdit('insertFromPaste', (event.clipboardData || window.clipboardData)?.getData('text') || '');
    }

    function onKeyDown(event) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (/^\d$/.test(event.key)) {
        event.preventDefault();
        applyEdit('insertText', event.key);
        return;
      }
      if (event.key === 'Backspace') {
        event.preventDefault();
        applyEdit('deleteContentBackward');
        return;
      }
      if (event.key === 'Delete') {
        event.preventDefault();
        applyEdit('deleteContentForward');
        return;
      }
      if (event.key === 'Home') {
        event.preventDefault();
        const caret = phoneCaretFromDigitIndex(0);
        input.setSelectionRange(caret, caret);
      }
    }

    function onFocus() {
      render(phoneCaretFromDigitIndex(Math.min(digits.length, PHONE_DIGIT_POSITIONS.length)));
    }

    function onClick() {
      ensureCaretAfterPrefix();
    }

    input.addEventListener('beforeinput', onBeforeInput);
    input.addEventListener('input', onInput);
    input.addEventListener('paste', onPaste);
    input.addEventListener('keydown', onKeyDown);
    input.addEventListener('focus', onFocus);
    input.addEventListener('click', onClick);

    render(phoneCaretFromDigitIndex(Math.min(digits.length, PHONE_DIGIT_POSITIONS.length)));

    return {
      getDigits: () => digits,
      setDigits(value) {
        digits = onlyPhoneDigits(value);
        render(phoneCaretFromDigitIndex(Math.min(digits.length, PHONE_DIGIT_POSITIONS.length)));
      },
      syncFromDom,
      applyEdit,
      destroy() {
        input.removeEventListener('beforeinput', onBeforeInput);
        input.removeEventListener('input', onInput);
        input.removeEventListener('paste', onPaste);
        input.removeEventListener('keydown', onKeyDown);
        input.removeEventListener('focus', onFocus);
        input.removeEventListener('click', onClick);
      }
    };
  }

  function label(name) {
    const labels = { fullName: 'ФИО', phone: 'Телефон', year: 'Год', vin: 'VIN', description: 'Описание проблемы', question: 'Вопрос', changeDetails: 'Что изменилось', brand: 'Марка', model: 'Модель', car: 'Автомобиль', visitDate: 'Дата визита', wasClientBefore: 'Были у нас ранее?' };
    return labels[name] || name;
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
    if (name === 'phone') return `<label data-field="phone">Телефон<input name="phone" inputmode="numeric" autocomplete="tel" placeholder="+7 (___) ___-__-__"/><small class="hint">Префикс +7 фиксирован</small><small class="field-error"></small></label>`;
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
    if (!/^\d{10}$/.test(String(payload.phone || ''))) errors.push({ field: 'phone', message: 'Телефон должен содержать 10 цифр после +7' });
    return errors;
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
    payload.phone = onlyPhoneDigits(payload.phone);
    Object.assign(payload, detectChannelIdentity());

    const errors = validatePayload(cfg.type, payload);
    if (errors.length) {
      errors.forEach((err) => setFieldError(form, err.field, err.message));
      globalError.textContent = 'Пожалуйста, исправьте ошибки в форме.';
      return;
    }

    form.dataset.submitting = '1';
    submit.disabled = true;
    submit.textContent = 'Отправка...';
    try {
      const response = await fetch(cfg.endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'REQUEST_FAILED');
      renderResult(true, data.id);
    } catch {
      renderResult(false);
    }
  }

  async function renderRequests() {
    mount.innerHTML = '<section><img class="brand-logo" src="/logo.png" alt="logo"/><h2>Мои обращения</h2><p><label data-field="phone"><input id="phone" inputmode="numeric" autocomplete="tel" placeholder="+7 (___) ___-__-__"/><small class="field-error"></small></label> <button id="load" class="inline">Показать</button></p><ul id="list"></ul></section>';
    const input = document.getElementById('phone');
    const phoneMask = createPhoneInputController(input);
    const list = document.getElementById('list');
    const error = mount.querySelector('[data-field="phone"] .field-error');
    document.getElementById('load').onclick = async () => {
      const digits = phoneMask.getDigits();
      error.textContent = '';
      if (!/^\d{10}$/.test(digits)) {
        error.textContent = 'Телефон должен содержать 10 цифр после +7';
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
    PHONE_MASK_TEMPLATE,
    PHONE_DIGIT_POSITIONS,
    onlyPhoneDigits,
    formatPhoneMask,
    phoneDigitIndexFromCaret,
    phoneCaretFromDigitIndex,
    applyPhoneEdit,
    createPhoneInputController,
    validatePayload
  };

  if (forms[path]) {
    const cfg = forms[path];
    mount.innerHTML = `<section><img class="brand-logo" src="${logoSrc}" alt="logo"/><h2>${cfg.title}</h2><form id="request-form"><p class="form-error"></p>${cfg.fields.map(renderField).join('')}<button type="submit">Отправить</button></form></section>`;
    createPhoneInputController(mount.querySelector('input[name="phone"]'));
    document.getElementById('request-form').addEventListener('submit', (e) => submitForm(e, cfg));
    return;
  }

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
