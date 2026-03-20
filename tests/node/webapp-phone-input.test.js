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

function beforeInput(input, inputType, data = '') {
  const event = new input.ownerDocument.defaultView.InputEvent('beforeinput', {
    bubbles: true,
    cancelable: true,
    data,
    inputType
  });
  input.dispatchEvent(event);
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

test('onlyPhoneDigits and formatPhoneMask normalize Russian phone inputs', () => {
  const dom = createDom({ route: '/' });
  const { onlyPhoneDigits, formatPhoneMask } = dom.window.__WEBAPP_TEST_API__;

  assert.equal(onlyPhoneDigits('+7 (999) 111-22-33'), '9991112233');
  assert.equal(onlyPhoneDigits('8 999 111 22 33'), '9991112233');
  assert.equal(onlyPhoneDigits('799911122334455'), '9991112233');
  assert.equal(onlyPhoneDigits('+7 (___) ___-__-__'), '');
  const formattedFull = formatPhoneMask('89991112233');
  assert.equal(formattedFull.digits, '9991112233');
  assert.equal(formattedFull.masked, '+7 (999) 111-22-33');
  const formattedPartial = formatPhoneMask('99911');
  assert.equal(formattedPartial.digits, '99911');
  assert.equal(formattedPartial.masked, '+7 (999) 11_-__-__');
});

test('request form shows client-side validation error near phone field for incomplete number', async () => {
  const dom = createDom({ route: '/forms/service-request' });
  const form = dom.window.document.getElementById('request-form');
  const phone = form.querySelector('input[name="phone"]');
  beforeInput(phone, 'insertText', '9');
  submit(form);
  await flush();
  assert.equal(form.querySelector('[data-field="phone"] .field-error').textContent, 'Телефон должен содержать 10 цифр после +7');
});

for (const channel of ['telegram', 'max']) {
  test(`forms submit normalized 10-digit phone for every request type in simulated ${channel} webview`, async () => {
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

      const api = dom.window.__WEBAPP_TEST_API__;
      const document = dom.window.document;
      const form = document.getElementById('request-form');
      const phone = form.querySelector('input[name="phone"]');

      assert.equal(phone.value, api.PHONE_MASK_TEMPLATE);

      for (const digit of '9123456789') beforeInput(phone, 'insertText', digit);
      assert.equal(phone.value, '+7 (912) 345-67-89');

      phone.setSelectionRange(api.phoneCaretFromDigitIndex(3), api.phoneCaretFromDigitIndex(3));
      beforeInput(phone, 'insertText', '0');
      assert.equal(phone.value, '+7 (912) 034-56-78');

      phone.setSelectionRange(api.phoneCaretFromDigitIndex(4), api.phoneCaretFromDigitIndex(4));
      beforeInput(phone, 'deleteContentBackward');
      assert.equal(phone.value, '+7 (912) 345-67-8_');

      phone.setSelectionRange(api.phoneCaretFromDigitIndex(7), api.phoneCaretFromDigitIndex(7));
      beforeInput(phone, 'deleteContentForward');
      assert.equal(phone.value, '+7 (912) 345-68-__');

      phone.setSelectionRange(api.phoneCaretFromDigitIndex(0), api.phoneCaretFromDigitIndex(10));
      paste(phone, '+7 999 111-22-33');
      assert.equal(phone.value, '+7 (999) 111-22-33');
      assert.equal(phone.selectionStart, api.PHONE_MASK_TEMPLATE.length);

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

test('requests page sends a 10-digit phone and shows validation error for incomplete value', async () => {
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

  const api = dom.window.__WEBAPP_TEST_API__;
  const document = dom.window.document;
  const phone = document.getElementById('phone');
  const button = document.getElementById('load');

  beforeInput(phone, 'insertText', '9');
  button.click();
  await flush();
  assert.equal(document.querySelector('[data-field="phone"] .field-error').textContent, 'Телефон должен содержать 10 цифр после +7');
  assert.equal(requests.length, 0);

  phone.setSelectionRange(api.phoneCaretFromDigitIndex(0), api.phoneCaretFromDigitIndex(10));
  paste(phone, '8 (999) 222-33-44');
  button.click();
  await flush();

  assert.equal(requests[0], '/api/client/requests?phone=9992223344');
  assert.match(document.getElementById('list').textContent, /Заявка на сервис/);
});
