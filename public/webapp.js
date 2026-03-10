(function () {
  const mount = document.getElementById('app');
  const path = window.location.pathname;

  const baseFields = `
    <label>ФИО <input name="fullName" required /></label>
    <label>Телефон <input name="phone" required /></label>
  `;

  const vehicleFields = `
    <label>Марка <input name="brand" /></label>
    <label>Модель <input name="model" /></label>
    <label>Год <input name="year" /></label>
    <label>VIN <input name="vin" /></label>
    <label>Госномер <input name="plateNumber" /></label>
  `;

  const forms = {
    '/forms/service-request': { title: 'Заявка на сервис', endpoint: '/api/client/requests/service', extra: `${vehicleFields}<label>Проблема <textarea name="description" required></textarea></label>` },
    '/forms/parts-request': { title: 'Запрос запчастей', endpoint: '/api/client/requests/parts', extra: `${vehicleFields}<label>Описание запроса <textarea name="description" required></textarea></label>` },
    '/forms/consultation': { title: 'Вопрос мастеру', endpoint: '/api/client/requests/consultation', extra: '<label>Вопрос <textarea name="question" required></textarea></label>' },
    '/forms/warranty-request': { title: 'Гарантийное обращение', endpoint: '/api/client/requests/warranty', extra: `${vehicleFields}<label>Описание проблемы <textarea name="description" required></textarea></label><label>Дата/контекст визита <input name="visitContext" /></label>` },
    '/forms/data-change-request': { title: 'Изменение данных', endpoint: '/api/client/requests/data-change', extra: '<label>Что изменилось <textarea name="changeDetails" required></textarea></label>' }
  };

  async function submitForm(event, endpoint) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const payload = Object.fromEntries(formData.entries());
    const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await response.json();
    mount.insertAdjacentHTML('beforeend', `<p class="ok">Обращение создано: ${data.id}</p>`);
  }

  async function renderRequests() {
    mount.innerHTML = '<h2>Мои обращения</h2><p>Укажите телефон: <input id="phone"/> <button id="load">Показать</button></p><ul id="list"></ul>';
    document.getElementById('load').onclick = async () => {
      const phone = document.getElementById('phone').value;
      const response = await fetch(`/api/client/requests?phone=${encodeURIComponent(phone)}`);
      const data = await response.json();
      document.getElementById('list').innerHTML = data.items.map((item) => `<li>${item.requestType} | ${item.status} | ${new Date(item.createdAt).toLocaleString()} | ${item.summary}</li>`).join('');
    };
  }

  async function renderRecommendations() {
    const response = await fetch('/api/client/recommendations');
    const data = await response.json();
    mount.innerHTML = `<h2>Актуальные рекомендации</h2><ul>${data.items.map((item) => `<li><b>${item.severity}</b>: ${item.text} <button data-id="${item.id}">Хочу устранить</button></li>`).join('')}</ul>`;
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
    mount.innerHTML = `<h2>${cfg.title}</h2><form id="request-form">${baseFields}${cfg.extra}<button type="submit">Отправить</button></form>`;
    document.getElementById('request-form').addEventListener('submit', (e) => submitForm(e, cfg.endpoint));
    return;
  }

  if (path === '/requests') return renderRequests();
  if (path === '/recommendations') return renderRecommendations();

  mount.innerHTML = '<p>Добро пожаловать! Используйте формы для обращений, разделы "Мои обращения" и "Рекомендации".</p>';
})();
