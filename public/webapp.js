(function () {
  const mount = document.getElementById('app');
  const path = window.location.pathname;
  const channelLink = window.__WEBAPP_TELEGRAM_CHANNEL_LINK__ || '#';

  const requestTypeLabels = {
    service_request: 'Заявка на сервис',
    parts_request: 'Запрос запчастей',
    consultation_request: 'Вопрос мастеру',
    warranty_request: 'Гарантийное обращение',
    data_change_request: 'Изменение данных'
  };

  const forms = {
    '/forms/service-request': {
      title: requestTypeLabels.service_request,
      endpoint: '/api/client/requests/service',
      type: 'service_request',
      fields: ['fullName', 'phone', 'year', 'vin', 'description']
    },
    '/forms/parts-request': {
      title: requestTypeLabels.parts_request,
      endpoint: '/api/client/requests/parts',
      type: 'parts_request',
      fields: ['fullName', 'phone', 'brand', 'model', 'year', 'vin', 'description']
    },
    '/forms/consultation': {
      title: requestTypeLabels.consultation_request,
      endpoint: '/api/client/requests/consultation',
      type: 'consultation_request',
      fields: ['fullName', 'phone', 'year', 'vin', 'question']
    },
    '/forms/warranty-request': {
      title: requestTypeLabels.warranty_request,
      endpoint: '/api/client/requests/warranty',
      type: 'warranty_request',
      fields: ['fullName', 'phone', 'year', 'vin', 'description', 'visitContext']
    },
    '/forms/data-change-request': {
      title: requestTypeLabels.data_change_request,
      endpoint: '/api/client/requests/data-change',
      type: 'data_change_request',
      fields: ['fullName', 'phone', 'changeDetails']
    }
  };

  const requiredByType = {
    service_request: ['fullName', 'phone', 'year', 'vin', 'description'],
    parts_request: ['fullName', 'phone', 'year', 'vin', 'description'],
    consultation_request: ['fullName', 'phone', 'year', 'vin', 'question'],
    warranty_request: ['fullName', 'phone', 'year', 'vin', 'description', 'visitContext'],
    data_change_request: ['fullName', 'phone', 'changeDetails']
  };

  function onlyPhoneDigits(value) {
    const cleaned = String(value || '').replace(/\D/g, '');
    if (cleaned.length === 11 && (cleaned.startsWith('7') || cleaned.startsWith('8'))) return cleaned.slice(1);
    if (cleaned.length > 10) return cleaned.slice(cleaned.length - 10);
    return cleaned;
  }

  function formatPhoneMask(rawValue) {
    const digits = onlyPhoneDigits(rawValue).slice(0, 10);
    const p1 = digits.slice(0, 3);
    const p2 = digits.slice(3, 6);
    const p3 = digits.slice(6, 8);
    const p4 = digits.slice(8, 10);
    let out = '+7';
    if (p1) out += ` (${p1}`;
    if (p1.length === 3) out += ')';
    if (p2) out += ` ${p2}`;
    if (p3) out += `-${p3}`;
    if (p4) out += `-${p4}`;
    return { masked: out, digits };
  }

  function getErrorLabel(field) {
    const labels = {
      fullName: 'ФИО', phone: 'Телефон', year: 'Год', vin: 'VIN', description: 'Описание', question: 'Вопрос', visitContext: 'Контекст визита', changeDetails: 'Что изменилось'
    };
    return labels[field] || field;
  }

  function renderResult({ ok, requestId }) {
    mount.innerHTML = `
      <section class="result ${ok ? 'ok' : 'error'}">
        <h2>${ok ? 'Ваша заявка принята' : 'Не удалось отправить заявку'}</h2>
        <p>${ok ? 'Мы свяжемся с вами в ближайшее время.' : 'Повторите попытку позднее.'}</p>
        ${requestId ? `<p class="result-id">Номер обращения: ${requestId}</p>` : ''}
        <div class="result-actions">
          <a class="btn" href="${channelLink}" target="_blank" rel="noopener">Подписаться на Telegram-канал</a>
          <a class="btn ghost" href="${channelLink}" target="_blank" rel="noopener">Ссылка на канал</a>
          <a class="btn" href="${path}">Создать ещё одно обращение</a>
          <a class="btn ghost" href="/">На главную</a>
        </div>
      </section>
    `;
  }

  function renderField(name) {
    if (name === 'description' || name === 'question' || name === 'changeDetails') {
      return `<label data-field="${name}">${getErrorLabel(name)}<textarea name="${name}"></textarea><small class="field-error"></small></label>`;
    }
    if (name === 'phone') {
      return `<label data-field="phone">Телефон<input name="phone" inputmode="numeric" autocomplete="tel" placeholder="+7 (___) ___-__-__"/><small class="hint">Префикс +7 фиксирован</small><small class="field-error"></small></label>`;
    }
    return `<label data-field="${name}">${getErrorLabel(name)}<input name="${name}"/><small class="field-error"></small></label>`;
  }

  function clearFieldErrors(form) {
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
    for (const field of (requiredByType[type] || [])) {
      if (!String(payload[field] || '').trim()) errors.push({ field, message: `Поле «${getErrorLabel(field)}» обязательно` });
    }
    if (!/^\d{10}$/.test(String(payload.phone || ''))) errors.push({ field: 'phone', message: 'Телефон должен содержать 10 цифр после +7' });
    return errors;
  }

  async function submitForm(event, cfg) {
    event.preventDefault();
    const form = event.target;
    clearFieldErrors(form);
    const globalError = form.querySelector('.form-error');
    const submit = form.querySelector('button[type="submit"]');
    globalError.textContent = '';

    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());
    payload.phone = onlyPhoneDigits(payload.phone);

    const errors = validatePayload(cfg.type, payload);
    if (errors.length) {
      errors.forEach((err) => setFieldError(form, err.field, err.message));
      globalError.textContent = 'Пожалуйста, исправьте ошибки в форме.';
      return;
    }

    submit.disabled = true;
    submit.textContent = 'Отправка…';
    try {
      const response = await fetch(cfg.endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'REQUEST_FAILED');
      renderResult({ ok: true, requestId: data.id });
    } catch {
      renderResult({ ok: false });
    }
  }

  async function renderRequests() {
    mount.innerHTML = '<section><h2>Мои обращения</h2><p>Телефон</p><p><input id="phone" placeholder="+7 (___) ___-__-__"/> <button id="load" class="inline">Показать</button></p><ul id="list"></ul></section>';
    const input = document.getElementById('phone');
    input.addEventListener('input', () => { input.value = formatPhoneMask(input.value).masked; });
    document.getElementById('load').onclick = async () => {
      const phone = onlyPhoneDigits(input.value);
      const response = await fetch(`/api/client/requests?phone=${encodeURIComponent(phone)}`);
      const data = await response.json();
      document.getElementById('list').innerHTML = data.items.map((item) => `<li>${requestTypeLabels[item.requestType] || item.requestType} | ${item.status} | ${new Date(item.createdAt).toLocaleString()} | ${item.summary}</li>`).join('') || '<li>Ничего не найдено</li>';
    };
  }

  async function renderRecommendations() {
    const response = await fetch('/api/client/recommendations');
    const data = await response.json();
    mount.innerHTML = `<section><h2>Рекомендации</h2><ul>${data.items.map((item) => `<li><b>${item.severity}</b>: ${item.text} <button class="inline" data-id="${item.id}">Хочу устранить</button></li>`).join('')}</ul></section>`;
    mount.querySelectorAll('button[data-id]').forEach((button) => {
      button.onclick = async () => {
        await fetch(`/api/client/recommendations/${button.dataset.id}/interest`, { method: 'POST' });
        button.textContent = 'Отмечено';
        button.disabled = true;
      };
    });
  }

  if (forms[path]) {
    const cfg = forms[path];
    mount.innerHTML = `<section><h2>${cfg.title}</h2><form id="request-form"><p class="form-error"></p>${cfg.fields.map(renderField).join('')}<button type="submit">Отправить</button></form></section>`;
    const phoneInput = mount.querySelector('input[name="phone"]');
    phoneInput.addEventListener('input', () => {
      phoneInput.value = formatPhoneMask(phoneInput.value).masked;
    });
    phoneInput.addEventListener('paste', (event) => {
      event.preventDefault();
      const text = (event.clipboardData || window.clipboardData).getData('text');
      phoneInput.value = formatPhoneMask(text).masked;
    });
    document.getElementById('request-form').addEventListener('submit', (e) => submitForm(e, cfg));
    return;
  }

  if (path === '/requests') return renderRequests();
  if (path === '/recommendations') return renderRecommendations();

  mount.innerHTML = '<section><h1>Автосервис</h1><p>Создайте обращение, отследите статус и посмотрите рекомендации.</p></section>';
})();
