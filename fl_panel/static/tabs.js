document.addEventListener('click', (event) => {
  const tab = event.target.closest('[data-tab]');
  if (!tab) return;
  const id = tab.dataset.tab;
  document.querySelectorAll('.tab').forEach((item) => item.classList.toggle('active', item === tab));
  document.querySelectorAll('.tab-panel').forEach((panel) => panel.classList.toggle('active', panel.id === id));
});

function setFinanceMessage(message, ok) {
  const box = document.querySelector('#finance-message');
  if (!box) return;
  box.hidden = false;
  box.textContent = message;
  box.classList.toggle('money', Boolean(ok));
  box.classList.toggle('negative', !ok);
}

function setBalance(selector, value, formatted) {
  const element = document.querySelector(selector);
  if (!element) return;
  element.dataset.balance = String(value);
  element.textContent = formatted;
}

document.addEventListener('submit', async (event) => {
  const form = event.target.closest('form[data-ajax-finance="true"]');
  if (!form) return;
  event.preventDefault();

  const button = form.querySelector('button[type="submit"], button:not([type])');
  const originalText = button ? button.textContent : '';
  if (button) {
    button.disabled = true;
    button.textContent = 'Выполняю...';
  }

  try {
    const response = await fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      headers: {
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
    });
    const payload = await response.json();
    setFinanceMessage(payload.message || 'Операция завершена.', payload.ok && response.ok);
    if (response.ok) {
      setBalance('#character-money', payload.character_money, payload.character_money_formatted);
      setBalance('#bank-money', payload.bank, payload.bank_formatted);
      if (payload.ok) form.reset();
    }
  } catch (error) {
    setFinanceMessage('Не удалось выполнить операцию без перезагрузки страницы. Попробуйте ещё раз.', false);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
});
