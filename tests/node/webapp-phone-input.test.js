const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const html = fs.readFileSync(path.join(process.cwd(), 'public', 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(process.cwd(), 'public', 'webapp.js'), 'utf8');

const formCases = [
  {
    route: '/forms/service-request',
    endpoint: '/api/client/requests/service',
    type: 'service_request',
    fill(form) {
      form.querySelector('input[name="fullName"]').value = 'Иван Иванов';
      form.querySelector('input[name="wasClientBefore"][value="yes"]').checked = true;
      form.querySelector('input[name="brand"]').value = 'Lada';
      form.querySelector('input[name="model"]').value = 'Vesta';
      form.querySelector('input[name="year"]').value = '2023';
      form.querySelector('input[name="vin"]').value = 'VIN-SERVICE';
      form.querySelector('textarea[name="description"]').value = 'Последовательный ввод телефона';
    }
  },
  {
    route: '/forms/parts-request',
    endpoint: '/api/client/requests/parts',
    type: 'parts_request',
    fill(form) {
      form.querySelector('input[name="fullName"]').value = 'Иван Иванов';
      form.querySelector('input[name="wasClientBefore"][value="no"]').checked = true;
      form.querySelector('input[name="brand"]').value = 'Kia';
      form.querySelector('input[name="model"]').value = 'Rio';
      form.querySelector('input[name="year"]').value = '2020';
      form.querySelector('input[name="vin"]').value = 'VIN-PARTS';
      form.querySelector('textarea[name="description"]').value = 'Нужна деталь';
    }
  },
  {
    route: '/forms/consultation',
    endpoint: '/api/client/requests/consultation',
    type: 'consultation_request',
    fill(form) {
      form.querySelector('input[name="fullName"]').value = 'Иван Иванов';
      form.querySelector('input[name="wasClientBefore"][value="yes"]').checked = true;
      form.querySelector('input[name="car"]').value = 'Toyota Camry';
      form.querySelector('input[name="vin"]').value = 'VIN-CONSULT';
      form.querySelector('textarea[name="question"]').value = 'Когда менять масло?';
    }
  },
  {
    route: '/forms/warranty-request',
    endpoint: '/api/client/requests/warranty',
    type: 'warranty_request',
    fill(form) {
      form.querySelector('input[name="fullName"]').value = 'Иван Иванов';
      form.querySelector('input[name="visitDate"]').value = '2026-03-01';
      form.querySelector('textarea[name="description"]').value = 'Повторная неисправность';
    }
  },
  {
    route: '/forms/data-change-request',
    endpoint: '/api/client/requests/data-change',
    type: 'data_change_request',
    fill(form) {
      form.querySelector('input[name="fullName"]').value = 'Иван Иванов';
      form.querySelector('textarea[name="changeDetails"]').value = 'Сменил телефон';
    }
  }
];

function createDom({ route, channel = 'telegram', fetchImpl }) {
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    url: `http://localhost${route}?channel=${channel}`
  });
  dom.window.fetch = fetchImpl || (async () => ({ ok: true, status: 200, json: async () => ({ items: [] }) }));
  dom.window.Telegram = { WebApp: { initDataUnsafe: { user: { id: 101 } } } };
  dom.window.MAX = { WebApp: { initDataUnsafe: { user: { id: 202 } } } };
  dom.window.eval(script);
  return dom;
}

function mutateInput(input, updater) {
  const start = typeof input.selectionStart === 'number' ? input.selectionStart : input.value.length;
  const end = typeof input.selectionEnd === 'number' ? input.selectionEnd : start;
  const next = updater({ value: input.value, start, end });
  input.value = next.value;
  input.setSelectionRange(next.caret, next.caret);
  input.dispatchEvent(new input.ownerDocument.defaultView.Event('input', { bubbles: true }));
}

function editInput(input, inputType, data = '') {
  mutateInput(input, ({ value, start, end }) => {
    if (inputType === 'insertText') {
      const nextValue = `${value.slice(0, start)}${data}${value.slice(end)}`;
      return { value: nextValue, caret: start + data.length };
    }
    if (inputType === 'deleteContentBackward') {
      if (start !== end) return { value: `${value.slice(0, start)}${value.slice(end)}`, caret: start };
      if (start === 0) return { value, caret: start };
      return { value: `${value.slice(0, start - 1)}${value.slice(start)}`, caret: start - 1 };
    }
    if (inputType === 'deleteContentForward') {
      if (start !== end) return { value: `${value.slice(0, start)}${value.slice(end)}`, caret: start };
      return { value: `${value.slice(0, start)}${value.slice(start + 1)}`, caret: start };
    }
    throw new Error(`Unsupported inputType: ${inputType}`);
  });
}

function paste(input, text) {
  const event = new input.ownerDocument.defaultView.Event('paste', {
    bubbles: true,
    cancelable: true
  });
  Object.defineProperty(event, 'clipboardData', {
    value: { getData: () => text }
  });
  input.dispatchEvent(event);
}

function submit(form) {
  const event = new form.ownerDocument.defaultView.Event('submit', {
    bubbles: true,
    cancelable: true
  });
  form.dispatchEvent(event);
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

test('phone helpers keep only digits and cut to 10 symbols', () => {
  const dom = createDom({ route: '/' });
  const { PHONE_HINT, normalizePhone, onlyPhoneDigits, normalizePhone10, formatPhoneMask } = dom.window.__WEBAPP_TEST_API__;

  assert.equal(PHONE_HINT, 'Введите корректный номер (10 цифр)');
  assert.equal(normalizePhone('+7 (999) 111-22-33'), '7999111223');
  assert.equal(onlyPhoneDigits('8 999 111 22 33'), '8999111223');
  assert.equal(normalizePhone10('(999) 111-22-33'), '9991112233');
  assert.equal(normalizePhone10('9991234567890'), '9991234567');
  assert.equal(normalizePhone10('тел: +7 (999) 111-22-33 доб. 55'), '7999111223');
  assert.equal(formatPhoneMask('+7 (999) 111-22-33').masked, '7999111223');
});

test('request form blocks submit for invalid phone and clears error after valid paste', async () => {
  const requests = [];
  const dom = createDom({
    route: '/forms/service-request',
    fetchImpl: async (url, options = {}) => {
      requests.push({ url: String(url), options });
      return { ok: true, status: 201, json: async () => ({ id: 'REQ-1' }) };
    }
  });
  const form = dom.window.document.getElementById('request-form');
  const phone = form.querySelector('input[name="phone"]');

  editInput(phone, 'insertText', '9');
  submit(form);
  await flush();
  assert.equal(form.querySelector('[data-field="phone"] .field-error').textContent, 'Введите корректный номер (10 цифр)');
  assert.equal(requests.length, 0);

  phone.setSelectionRange(0, phone.value.length);
  paste(phone, '(999) 123-45-67');
  await flush();
  assert.equal(phone.value, '9991234567');
  assert.equal(form.querySelector('[data-field="phone"] .field-error').textContent, '');
});

for (const channel of ['telegram', 'max']) {
  test(`forms submit raw 10-digit phone for every request type in simulated ${channel} webview`, async () => {
    for (const formCase of formCases) {
      const requests = [];
      const dom = createDom({
        route: formCase.route,
        channel,
        fetchImpl: async (url, options = {}) => {
          requests.push({ url: String(url), options });
          return {
            ok: true,
            status: 201,
            json: async () => ({ id: 'REQ-1', requestType: formCase.type })
          };
        }
      });

      const document = dom.window.document;
      const form = document.getElementById('request-form');
      const phone = form.querySelector('input[name="phone"]');

      assert.equal(phone.value, '');

      for (const digit of '91234567890123') editInput(phone, 'insertText', digit);
      assert.equal(phone.value, '9123456789');

      phone.setSelectionRange(3, 3);
      editInput(phone, 'insertText', '0');
      assert.equal(phone.value, '9120345678');

      phone.setSelectionRange(5, 5);
      editInput(phone, 'deleteContentBackward');
      assert.equal(phone.value, '912045678');

      phone.setSelectionRange(3, 3);
      editInput(phone, 'deleteContentForward');
      assert.equal(phone.value, '91245678');

      phone.setSelectionRange(0, phone.value.length);
      paste(phone, '+7 (999) 111-22-33');
      assert.equal(phone.value, '7999111223');

      phone.setSelectionRange(1, 1);
      editInput(phone, 'insertText', '5');
      assert.equal(phone.value, '7599911122');

      phone.setSelectionRange(0, phone.value.length);
      paste(phone, '(999) 111-22-33');
      assert.equal(phone.value, '9991112233');

      formCase.fill(form);
      submit(form);
      await flush();

      assert.equal(requests.length, 1, `${channel} ${formCase.route}`);
      assert.equal(requests[0].url, formCase.endpoint);
      const payload = JSON.parse(requests[0].options.body);
      assert.equal(payload.phone, '9991112233');
      assert.match(payload.phone, /^\d{10}$/);
      if (channel === 'telegram') {
        assert.equal(payload.sourceChannel, 'webapp');
        assert.equal(payload.telegramId, 101);
      } else {
        assert.equal(payload.sourceChannel, 'max_webapp');
        assert.equal(payload.maxId, 202);
      }
    }
  });
}

test('requests page sends a 10-digit phone and blocks invalid value', async () => {
  const requests = [];
  const dom = createDom({
    route: '/requests',
    fetchImpl: async (url) => {
      requests.push(String(url));
      return {
        ok: true,
        status: 200,
        json: async () => ({ items: [{ requestType: 'service_request', status: 'new', createdAt: '2026-03-20T12:00:00.000Z', summary: 'Диагностика' }] })
      };
    }
  });

  const document = dom.window.document;
  const phone = document.getElementById('phone');
  const button = document.getElementById('load');

  editInput(phone, 'insertText', '9');
  button.click();
  await flush();
  assert.equal(document.querySelector('[data-field="phone"] .field-error').textContent, 'Введите корректный номер (10 цифр)');
  assert.equal(requests.length, 0);

  phone.setSelectionRange(0, phone.value.length);
  paste(phone, '(999) 222-33-44');
  button.click();
  await flush();

  assert.equal(requests[0], '/api/client/requests?phone=9992223344');
  assert.match(document.getElementById('list').textContent, /Заявка на сервис/);
});
