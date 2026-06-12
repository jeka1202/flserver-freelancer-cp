function flpFindButtonByDataset(selector, key, value) {
  return Array.from(document.querySelectorAll(selector)).find((item) => item.dataset && item.dataset[key] === value) || null;
}

function flpActivateMainTab(id, {persist = true} = {}) {
  const target = String(id || '').trim();
  if (!target) return false;

  const tabExists = Boolean(flpFindButtonByDataset('.tab[data-tab]', 'tab', target));
  const panelExists = Boolean(document.getElementById(target));
  if (!tabExists || !panelExists) return false;

  document.querySelectorAll('.tab[data-tab]').forEach((item) => {
    item.classList.toggle('active', item.dataset.tab === target);
  });

  document.querySelectorAll('.tab-panel').forEach((panel) => {
    panel.classList.toggle('active', panel.id === target);
  });

  if (persist) {
    try { localStorage.setItem('flp_main_tab', target); } catch (error) {}
  }

  return true;
}

function flpCurrentMainTab() {
  return document.querySelector('.tab[data-tab].active')?.dataset?.tab
    || document.querySelector('.tab-panel.active')?.id
    || 'hold';
}

function flpCaptureActiveTabs() {
  return {
    main: flpCurrentMainTab(),
    warehouse: document.querySelector('#warehouse-content .warehouse-subtab.active')?.dataset?.warehouseTab || '',
    contracts: document.querySelector('#contracts .contract-subtab.active')?.dataset?.contractTab || '',
    craft: document.querySelector('#craft-content .craft-subtab.active')?.dataset?.craftTab || '',
  };
}

function flpRestoreActiveTabs(state = {}) {
  if (state.main) flpActivateMainTab(state.main, {persist: true});

  if (state.warehouse && typeof initWarehouseSubtabs === 'function') {
    initWarehouseSubtabs(state.warehouse);
  }

  if (state.contracts && typeof initContractSubtabs === 'function') {
    initContractSubtabs(state.contracts);
  }

  if (state.craft && typeof initCraftSubtabs === 'function') {
    initCraftSubtabs(state.craft);
  }
}

document.addEventListener('click', (event) => {
  const tab = event.target.closest('[data-tab]');
  if (!tab) return;

  event.preventDefault();
  flpActivateMainTab(tab.dataset.tab || 'hold');
});

document.addEventListener('DOMContentLoaded', () => {
  try {
    const saved = localStorage.getItem('flp_main_tab');
    if (saved) flpActivateMainTab(saved, {persist: false});
  } catch (error) {}
});

function setFinanceMessage(message, ok) {
  const box = document.querySelector('#finance-message');
  if (!box) return;

  box.hidden = false;
  const translated = (typeof flpTranslateText === 'function') ? flpTranslateText(message, flpGetLang()) : null;
  box.textContent = translated || message;
  box.classList.toggle('money', Boolean(ok));
  box.classList.toggle('negative', !ok);
}


function showWarehouseNotice(message, ok = false) {
  const notice = document.querySelector('#warehouse-modal-notice');
  if (notice) {
    notice.hidden = false;
    notice.textContent = message;
    notice.classList.toggle('money', Boolean(ok));
    notice.classList.toggle('negative', !ok);
  }

  setFinanceMessage(message, ok);
}

function clearWarehouseNotice() {
  const notice = document.querySelector('#warehouse-modal-notice');
  if (notice) {
    notice.hidden = true;
    notice.textContent = '';
    notice.classList.remove('money', 'negative');
  }
}

function normalizeDigitsOnly(value) {
  return String(value || '').replace(/\D+/g, '');
}

function numericInputMax(input) {
  const max = parseInt(input.getAttribute('max') || '0', 10);
  return Number.isFinite(max) && max > 0 ? max : 0;
}

function validateWarehouseAmountInput(input, {showNotice = true} = {}) {
  const original = input.value;
  const cleaned = normalizeDigitsOnly(original);

  if (original !== cleaned) {
    input.value = cleaned;
    if (showNotice) {
      showWarehouseNotice('Количество: только цифры, без пробелов и спецсимволов.', false);
    }
    return false;
  }

  const amount = parseInt(cleaned || '0', 10);
  const max = numericInputMax(input);

  if (!amount || amount <= 0) {
    if (showNotice) showWarehouseNotice('Укажи количество больше нуля.', false);
    return false;
  }

  if (max && amount > max) {
    if (showNotice) {
      showWarehouseNotice(`На складе только ${max} шт. Нельзя передать ${amount} шт.`, false);
    }
    return false;
  }

  return true;
}

function validateWarehouseForm(form) {
  const amountInput = form.querySelector('input[name="amount"], input[name="quantity"]');
  if (!amountInput) return true;

  return validateWarehouseAmountInput(amountInput, {showNotice: true});
}


function setBalance(selector, value, formatted) {
  const element = document.querySelector(selector);
  if (!element) return;

  element.dataset.balance = String(value);
  element.textContent = formatted;
}

function buildFinanceBody(form) {
  const body = new URLSearchParams();

  for (const element of Array.from(form.elements)) {
    if (!element.name || element.disabled) continue;

    if ((element.type === 'checkbox' || element.type === 'radio') && !element.checked) {
      continue;
    }

    body.append(element.name, element.value);
  }

  return body;
}

document.addEventListener('submit', async (event) => {
  const form = event.target.closest('form[data-ajax-finance="true"]');
  if (!form) return;

  event.preventDefault();
  event.stopPropagation();

  if (form.dataset.loading === '1') {
    return;
  }

  form.dataset.loading = '1';

  const button = form.querySelector('button[type="submit"], button:not([type])');
  const originalText = button ? button.textContent : '';

  if (button) {
    button.disabled = true;
    button.textContent = 'Выполняю...';
  }

  try {
    const actionUrl = form.getAttribute('action') || window.location.href;
    const body = buildFinanceBody(form);

    const response = await fetch(actionUrl, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    });

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const payload = await response.json();

    setFinanceMessage(payload.message || 'Операция завершена.', payload.ok && response.ok);
    setBalance('#character-money', payload.character_money, payload.character_money_formatted);
    setBalance('#bank-money', payload.bank, payload.bank_formatted);

    if (payload.finance_history_html) {
      const history = document.querySelector('#finance-history');
      if (history) {
        history.outerHTML = payload.finance_history_html;
      }
      if (typeof flpApplyI18n === 'function') {
        flpApplyI18n(document.querySelector('#finance') || document);
      }
    }

    if (response.ok && payload.ok) {
      const amountInput = form.querySelector('[name="amount"]');
      if (amountInput) amountInput.value = '';
    }
  } catch (error) {
    console.error('Finance AJAX failed:', error);
    setFinanceMessage('Фоновая операция не выполнена: сервер вернул неожиданный ответ. Обновите страницу и попробуйте ещё раз.', false);
  } finally {
    form.dataset.loading = '0';

    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
});



function closeWarehouseLocationModal() {
  const modal = document.querySelector('#warehouse-location-modal');
  if (modal) modal.hidden = true;

  // If /api/live was skipped while this modal was open, refresh shortly after
  // closing so the list catches up without waiting for the next 12s tick.
  if (typeof flpRefreshLivePanels === 'function') {
    window.setTimeout(() => flpRefreshLivePanels({silent: true}), 80);
  }
}

function openWarehouseLocationModal(row) {
  const modal = document.querySelector('#warehouse-location-modal');
  if (!modal) return;

  const templateId = row.dataset.template || '';
  const template = templateId ? document.getElementById(templateId) : null;
  const body = modal.querySelector('#warehouse-location-modal-body');
  const title = modal.querySelector('#warehouse-location-modal-title');

  if (!template || !body) return;

  if (title) title.textContent = row.dataset.locationName || 'Склад';
  body.innerHTML = template.innerHTML;
  if (typeof flpApplyI18n === 'function') flpApplyI18n(modal);
  modal.hidden = false;
}


function ensureWarehouseModalInBody() {
  const modal = document.querySelector('#warehouse-modal');
  if (modal && modal.parentElement !== document.body) {
    document.body.appendChild(modal);
  }
  return modal;
}

function openWarehousePane(name) {
  document.querySelectorAll('.warehouse-pane').forEach((pane) => {
    pane.hidden = pane.id !== `warehouse-pane-${name}`;
  });
}

function closeWarehouseModal() {
  const modal = document.querySelector('#warehouse-modal');
  if (modal) modal.hidden = true;
  clearWarehouseNotice();
  document.querySelectorAll('.warehouse-row.is-modal-source').forEach((item) => item.classList.remove('is-modal-source'));
}


function positionWarehouseModal(row) {
  // v23: centered modal; intentionally no dynamic positioning.
}


function openWarehouseModal(row) {
  const modal = ensureWarehouseModalInBody();
  if (!modal) return;

  document.querySelectorAll('.warehouse-row.is-modal-source').forEach((item) => item.classList.remove('is-modal-source'));
  row.classList.add('is-modal-source');

  const itemHash = row.dataset.itemHash || '';
  const itemName = row.dataset.itemName || 'Предмет';
  const quantity = row.dataset.quantity || '0';
  const volume = row.dataset.volume || '0';
  const description = row.dataset.description || 'Описание пока не импортировано.';
  const icon = row.dataset.icon || '';
  const cargoEligible = row.dataset.cargoEligible === '1';
  const cargoReason = row.dataset.cargoReason || 'В трюм через панель пока можно переносить только обычный груз / commodity с объёмом больше 0.';
  const locationHash = row.dataset.locationHash || '';
  const locationName = row.dataset.locationName || '';
  const locationType = row.dataset.locationType || 'base';
  const isCurrentLocation = row.dataset.currentLocation !== '0';

  clearWarehouseNotice();

  const title = modal.querySelector('#warehouse-modal-title');
  const qty = modal.querySelector('#warehouse-modal-qty');
  const vol = modal.querySelector('#warehouse-modal-volume');
  const desc = modal.querySelector('#warehouse-modal-description');
  const iconEl = modal.querySelector('#warehouse-modal-icon');

  if (title) title.textContent = itemName;
  if (qty) qty.textContent = quantity;
  if (vol) vol.textContent = volume;
  if (desc) desc.textContent = description;

  for (const input of modal.querySelectorAll('input[name="item_hash"]')) {
    input.value = itemHash;
  }
  for (const input of modal.querySelectorAll('input[name="location_hash"]')) {
    input.value = locationHash;
  }
  for (const input of modal.querySelectorAll('input[name="location_name"]')) {
    input.value = locationName;
  }
  for (const input of modal.querySelectorAll('input[name="location_type"]')) {
    input.value = locationType;
  }

  const maxQuantity = normalizeDigitsOnly(quantity) || '0';
  for (const input of modal.querySelectorAll('input[name="amount"], input[name="quantity"]')) {
    input.max = maxQuantity;
    input.value = input.id === 'warehouse-delete-amount' ? maxQuantity : '1';
    input.dataset.available = maxQuantity;
  }

  const contractPrice = modal.querySelector('#warehouse-contract-price');
  const contractLifetime = modal.querySelector('#warehouse-contract-lifetime');
  const contractLifetimeUnit = modal.querySelector('#warehouse-contract-lifetime-unit');
  if (contractPrice) contractPrice.value = '';
  if (contractLifetime) contractLifetime.value = '24';
  if (contractLifetimeUnit) contractLifetimeUnit.value = 'hours';

  const shipButton = modal.querySelector('[data-warehouse-pane="ship"]');
  const shipWarning = modal.querySelector('#warehouse-ship-warning');
  const shipForm = modal.querySelector('#warehouse-ship-form');

  const shipDisabledReason = !isCurrentLocation
    ? 'Перенос в трюм доступен только на текущей базе пилота.'
    : cargoReason;
  const shipAllowed = cargoEligible && isCurrentLocation;

  if (shipButton) {
    shipButton.disabled = !shipAllowed;
    shipButton.title = shipAllowed ? '' : shipDisabledReason;
  }
  if (shipWarning) {
    shipWarning.hidden = shipAllowed;
    shipWarning.textContent = shipDisabledReason;
  }
  if (shipForm) {
    shipForm.hidden = !shipAllowed;
  }

  if (iconEl) {
    if (icon) {
      iconEl.src = `/static/${icon}`;
      iconEl.hidden = false;
    } else {
      iconEl.hidden = true;
      iconEl.removeAttribute('src');
    }
  }

  document.querySelectorAll('.warehouse-pane').forEach((pane) => { pane.hidden = true; });
  if (typeof flpApplyI18n === 'function') flpApplyI18n(modal);
  modal.hidden = false;
  // v24: modal is centered by CSS; no side positioning.
}

document.addEventListener('click', (event) => {
  const locationClose = event.target.closest('[data-warehouse-location-close]');
  if (locationClose) {
    event.preventDefault();
    closeWarehouseLocationModal();
    return;
  }

  const locationItemRow = event.target.closest('.warehouse-location-item-row');
  if (locationItemRow) {
    event.preventDefault();
    closeWarehouseLocationModal();
    openWarehouseModal(locationItemRow);
    return;
  }

  const locationRow = event.target.closest('.warehouse-location-row');
  if (locationRow) {
    event.preventDefault();
    openWarehouseLocationModal(locationRow);
    return;
  }

  const close = event.target.closest('[data-warehouse-close]');
  if (close) {
    event.preventDefault();
    closeWarehouseModal();
    return;
  }

  const paneButton = event.target.closest('[data-warehouse-pane]');
  if (paneButton && !paneButton.disabled) {
    event.preventDefault();
    openWarehousePane(paneButton.dataset.warehousePane);
    return;
  }

  const row = event.target.closest('.warehouse-row');
  if (row) {
    event.preventDefault();
    openWarehouseModal(row);
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeWarehouseModal();
  }

  if ((event.key === 'Enter' || event.key === ' ') && event.target.classList && event.target.classList.contains('warehouse-row')) {
    event.preventDefault();
    openWarehouseModal(event.target);
  }
});


window.addEventListener('resize', () => {
  const modal = document.querySelector('#warehouse-modal');
  const active = document.querySelector('.warehouse-row.is-modal-source');
  if (modal && !modal.hidden && active) {
    positionWarehouseModal(active);
  }
});









/* v79: warehouse inner subtabs */
function initWarehouseSubtabs(preferredTab = '') {
  const root = document.querySelector('#warehouse-content');
  if (!root) return;

  const buttons = Array.from(root.querySelectorAll('.warehouse-subtab'));
  const panels = Array.from(root.querySelectorAll('.warehouse-subpanel'));
  if (!buttons.length || !panels.length) return;

  const activate = (name) => {
    const target = name || 'stock';
    buttons.forEach((button) => {
      button.classList.toggle('active', button.dataset.warehouseTab === target);
    });
    panels.forEach((panel) => {
      panel.classList.toggle('active', panel.dataset.warehousePanel === target);
    });
    root.dataset.activeWarehouseTab = target;
  };

  buttons.forEach((button) => {
    if (button.dataset.ready === '1') return;
    button.dataset.ready = '1';

    button.addEventListener('click', () => {
      activate(button.dataset.warehouseTab || 'stock');
    });
  });

  const active = preferredTab || root.dataset.activeWarehouseTab || (root.querySelector('.warehouse-subtab.active') || {}).dataset?.warehouseTab || 'stock';
  activate(active);
}

document.addEventListener('DOMContentLoaded', () => initWarehouseSubtabs());
document.addEventListener('click', () => requestAnimationFrame(() => initWarehouseSubtabs()));


/* v86: inner tabs for Contracts section, preserving active subtab after /api/live */
function initContractSubtabs(preferredTab = "") {
  const root = document.querySelector('#contracts');
  if (!root) return;

  const buttons = Array.from(root.querySelectorAll('.contract-subtab'));
  const panels = Array.from(root.querySelectorAll('.contract-subpanel'));
  if (!buttons.length || !panels.length) return;

  const activate = (name) => {
    let target = name || root.dataset.activeContractTab || root.querySelector('.contract-subtab.active')?.dataset?.contractTab || 'server';

    if (!root.querySelector(`[data-contract-panel="${target}"]`)) {
      target = buttons[0]?.dataset?.contractTab || 'server';
    }

    buttons.forEach((button) => {
      button.classList.toggle('active', button.dataset.contractTab === target);
    });

    panels.forEach((panel) => {
      panel.classList.toggle('active', panel.dataset.contractPanel === target);
    });

    root.dataset.activeContractTab = target;
  };

  buttons.forEach((button) => {
    if (button.dataset.contractReady === '1') return;
    button.dataset.contractReady = '1';

    button.addEventListener('click', () => {
      activate(button.dataset.contractTab || 'server');
    });
  });

  activate(preferredTab);
}

document.addEventListener('DOMContentLoaded', () => initContractSubtabs());
document.addEventListener('click', () => requestAnimationFrame(() => initContractSubtabs()));


/* v48: craft timers, progressbars and AJAX craft actions */
function flpPad(num) {
  return String(num).padStart(2, '0');
}

function flpFormatSeconds(value) {
  let seconds = Math.max(0, Math.floor(Number(value) || 0));
  const days = Math.floor(seconds / 86400);
  seconds -= days * 86400;
  const hours = Math.floor(seconds / 3600);
  seconds -= hours * 3600;
  const minutes = Math.floor(seconds / 60);
  seconds -= minutes * 60;

  if (days > 0) return `${days}д ${flpPad(hours)}:${flpPad(minutes)}:${flpPad(seconds)}`;
  if (hours > 0) return `${hours}:${flpPad(minutes)}:${flpPad(seconds)}`;
  return `${minutes}:${flpPad(seconds)}`;
}

function flpParseLocalDate(value) {
  if (!value) return null;
  const normalized = String(value).replace(' ', 'T');
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function updateCraftTimers() {
  const rows = document.querySelectorAll('.craft-job-row');
  const now = Date.now();
  const lang = flpGetLang();
  const readyLabel = flpTranslateText('Готово', lang) || 'Готово';
  const progressLabel = flpTranslateText('В работе', lang) || 'В работе';

  rows.forEach((row) => {
    const finish = flpParseLocalDate(row.dataset.finishAt);
    const total = Math.max(1, Number(row.dataset.totalSeconds || 1));
    if (!finish) return;

    const left = Math.max(0, Math.ceil((finish.getTime() - now) / 1000));
    const progress = left <= 0 ? 100 : Math.max(0, Math.min(100, ((total - left) / total) * 100));

    const bar = row.querySelector('.craft-progress span');
    if (bar) bar.style.width = `${progress.toFixed(2)}%`;

    const leftBox = row.querySelector('.craft-job-left');
    if (leftBox) leftBox.textContent = left <= 0 ? readyLabel : flpFormatSeconds(left);

    const statusBox = row.querySelector('.craft-job-status');
    if (statusBox) statusBox.textContent = left <= 0 ? readyLabel : progressLabel;

    const claim = row.querySelector('.craft-claim-form');
    const cancel = row.querySelector('.craft-cancel-form');

    if (left <= 0) {
      row.dataset.ready = '1';
      if (claim) {
        claim.classList.remove('is-hidden');
        claim.classList.add('is-visible');
        const readyButton = claim.querySelector('button');
        if (readyButton) {
          readyButton.textContent = readyLabel;
          readyButton.classList.add('craft-ready-button');
        }
      }
      if (cancel) {
        cancel.classList.remove('is-visible');
        cancel.classList.add('is-hidden');
      }
    }
  });
}

function setCraftMessage(message, ok) {
  const box = document.querySelector('#craft-message');
  if (!box) return;

  if (!message) {
    box.hidden = true;
    box.textContent = '';
    return;
  }

  box.hidden = false;
  box.textContent = message;
  box.classList.toggle('money', Boolean(ok));
  box.classList.toggle('negative', !ok);
}

async function refreshCraftPanel(message, ok) {
  const response = await fetch('/api/craft', {
    method: 'GET',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
  });

  const payload = await response.json();
  if (payload.html) {
    const oldBox = document.querySelector('#craft-content');
    if (oldBox) {
      oldBox.outerHTML = payload.html;
    }
  }

  setCraftMessage(message || payload.message || '', ok ?? payload.ok);
  flpApplyI18n(document.querySelector('#craft-content') || document);
  initCraftSubtabs();
  updateCraftTimers();
}

document.addEventListener('submit', async (event) => {
  const form = event.target.closest('form[data-ajax-craft="true"]');
  if (!form) return;

  event.preventDefault();
  event.stopPropagation();

  if (!validateWarehouseForm(form)) return;

  if (form.dataset.loading === '1') return;
  form.dataset.loading = '1';

  const button = form.querySelector('button[type="submit"], button:not([type])');
  const oldText = button ? button.textContent : '';

  if (button) {
    button.disabled = true;
    button.textContent = 'Выполняю...';
  }

  try {
    const response = await fetch(form.getAttribute('action') || window.location.href, {
      method: 'POST',
      credentials: 'same-origin',
      body: new URLSearchParams(new FormData(form)),
      headers: {
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    });

    const payload = await response.json();

    if (payload.html) {
      const oldBox = document.querySelector('#craft-content');
      if (oldBox) {
        oldBox.outerHTML = payload.html;
      }
    }

    setCraftMessage(payload.message || (response.ok ? 'Операция выполнена.' : 'Операция не выполнена.'), payload.ok && response.ok);
    flpApplyI18n(document.querySelector('#craft-content') || document);
    initCraftSubtabs();
    updateCraftTimers();
  } catch (error) {
    console.error('Craft AJAX failed:', error);
    setCraftMessage('Фоновая операция крафта не выполнена. Обнови страницу и попробуй ещё раз.', false);
  } finally {
    form.dataset.loading = '0';
    if (button) {
      button.disabled = false;
      button.textContent = oldText;
    }
  }
});

if (!window.__flpCraftTimer) {
  window.__flpCraftTimer = window.setInterval(updateCraftTimers, 1000);
}

document.addEventListener('DOMContentLoaded', updateCraftTimers);
document.addEventListener('click', () => requestAnimationFrame(updateCraftTimers));


/* v71: instant bidirectional multilingual UI, RU/EN */
const FLP_I18N = {
  "en": {
    "LANG": "LANG",
    "RU": "RU",
    "EN": "EN",
    "Кабинет": "Cabinet",
    "Кабинет пилота": "Pilot cabinet",
    "Личный кабинет пилота": "Pilot account",
    "Введите имя персонажа или ID аккаунта. Пароль можно указать из файла name; для совместимости старый вход по ID аккаунта работает без пароля.": "Enter a character name or account ID. Password can be taken from the name file; legacy account-ID login still works without password.",
    "Логин": "Login",
    "Пароль": "Password",
    "Персонаж, если вошли по ID аккаунта": "Character, if logged in by account ID",
    "Войти в кабинет": "Log in",
    "Навигационная сеть": "Navigation network",
    "персонажей в архиве": "characters in archive",
    "записей IONCROSS": "IONCROSS records",
    "Администрирование вынесено отдельно:": "Administration is separate:",
    "Клиентская часть не показывает список чужих аккаунтов.": "Client side does not show other accounts.",
    "Freelancer Account Panel · клиентская часть показывает только персонажа после входа · админская логика отдельно в /admin": "Freelancer Account Panel · client side shows only the logged-in character · admin logic is separate in /admin",
    "← выйти": "← logout",
    "Трюм корабля": "Ship hold",
    "Склад базы": "Base warehouse",
    "Крафт": "Craft",
    "Контракты": "Contracts",
    "Снаряжение": "Equipment",
    "Статистика": "Statistics",
    "Финансы": "Finance",
    "Репутация": "Reputation",
    "Навигация": "Navigation",
    "Трюм — это текущее содержимое корабля пилота. Оно читается из .fl-файла персонажа и показывает груз, боеприпасы, батареи, нанороботы и оборудование корабля.": "Ship hold is the current content of the pilot's ship. It is read from the character .fl file and shows cargo, ammo, batteries, nanobots and equipment.",
    "Во вкладке «Трюм корабля» показываются только товары / commodity, которые занимают место в трюме. Боеприпасы, нанороботы, батареи щита и остальная экипировка вынесены во вкладку «Снаряжение».": "The Ship hold tab shows only commodity cargo that takes hold space. Ammo, nanobots, shield batteries and equipment are moved to the Equipment tab.",
    "Во вкладке «Трюм корабля» показываются только товары / commodity, которые занимают место в трюме. Боеприпасы, нанороботы, батареи щита и остальная экипировка вын": "The Ship hold tab shows only commodity cargo that takes hold space. Ammo, nanobots, shield batteries and equipment are moved to the Equipment tab.",
    "Товары / commodity в трюме": "Cargo / commodity in hold",
    "Товаров в трюме нет.": "No cargo in hold.",
    "Корабль": "Ship",
    "Нанороботы": "Nanobots",
    "Батареи щита": "Shield batteries",
    "Боеприпасы": "Ammo",
    "Масса груза": "Cargo mass",
    "Свободно": "Free",
    "Склад ограничен высотой экрана. Клик по строке предмета открывает действия.": "Warehouse height is limited by the screen. Click an item row to open actions.",
    "Склад базы:": "Base warehouse:",
    "Личный склад пилота": "Personal pilot warehouse",
    "Кликни по строке предмета: можно удалить, передать другому пилоту на склад, посмотреть свойства. Перенос на свой корабль будет отдельным действием через FLHook.": "Click an item row: you can delete it, send it to another pilot's warehouse, or view details. Moving to your ship will be a separate FLHook action.",
    "Передача другому пилоту выполняется только склад → склад. Корабль получателя, его .fl-файл и FLHook не затрагиваются.": "Transfer to another pilot is warehouse → warehouse only. Receiver ship, .fl file and FLHook are not touched.",
    "Тестово добавить в склад БД. Трюм корабля не меняется.": "Test add to DB warehouse. Ship hold is not changed.",
    "Предмет склада": "Warehouse item",
    "На складе": "In warehouse",
    "Объём 1": "Volume 1",
    "В трюм": "To hold",
    "Передать пилоту": "Send to pilot",
    "Передать": "Send",
    "Удалить": "Delete",
    "Да, удалить": "Yes, delete",
    "Нет": "No",
    "Удалить предмет из SQLite-склада?": "Delete item from SQLite warehouse?",
    "Никнейм пилота": "Pilot nickname",
    "Никнейм получателя": "Receiver nickname",
    "Количество": "Quantity",
    "На склад": "To warehouse",
    "Предметов": "Items",
    "Объём": "Volume",
    "Предмет": "Item",
    "Название": "Name",
    "Кол-во": "Qty",
    "Кол-во / слот": "Qty / slot",
    "Тип": "Type",
    "Склад этой базы пока пуст.": "This base warehouse is empty.",
    "Рецепты": "Recipes",
    "Активные крафты": "Active crafts",
    "Разделы крафта": "Craft sections",
    "Личный крафт пилота на текущей базе / планете": "Personal pilot craft on current base / planet",
    "Крафт работает через личный SQLite-склад конкретного пилота: ресурсы списываются только у него, результат возвращается только ему. .fl и FLHook пока не трогаются.": "Craft uses the personal SQLite warehouse of this pilot: resources are taken only from this pilot, and result returns only to this pilot. .fl and FLHook are not touched yet.",
    "Активных заданий крафта на этой базе нет.": "No active craft jobs on this base.",
    "Рецепт": "Recipe",
    "Нужно": "Required",
    "Получится": "Output",
    "Время": "Time",
    "Запуск": "Start",
    "Создать": "Create",
    "Задание": "Job",
    "Статус": "Status",
    "Прогресс": "Progress",
    "Действие": "Action",
    "Готово": "Ready",
    "Отменить": "Cancel",
    "В работе": "In progress",
    "Осталось": "Left",
    "Запустить": "Start",
    "Выполняю...": "Working...",
    "Запущено": "Started",
    "Рецепты не найдены. Положи recipes.json в папку craft рядом с account_panel.py или в fl_panel/data/craft_recipes.json.": "Recipes not found. Put recipes.json into the craft folder near account_panel.py or into fl_panel/data/craft_recipes.json.",
    "Минимальный формат recipes.json": "Minimal recipes.json format",
    "Активные контракты сервера": "Server active contracts",
    "Мои контракты": "My contracts",
    "История контрактов": "Contract history",
    "Разделы контрактов": "Contract sections",
    "Выставить предмет со склада на продажу": "Create sale contract from warehouse item",
    "Предмет со склада": "Warehouse item",
    "Цена за весь контракт": "Full contract price",
    "Срок": "Lifetime",
    "часов": "hours",
    "дней": "days",
    "Выставить контракт": "Create contract",
    "Купить": "Buy",
    "Цена": "Price",
    "Продавец": "Seller",
    "База / планета": "Base / planet",
    "Где лежит": "Stored at",
    "Место": "Location",
    "Истёк": "Expired",
    "Активен": "Active",
    "Продан": "Sold",
    "Отменён": "Cancelled",
    "Активных контрактов пока нет.": "No active contracts yet.",
    "У этого пилота ещё нет своих контрактов.": "This pilot has no contracts yet.",
    "Покупок по контрактам пока нет.": "No contract purchases yet.",
    "История контрактов пока пустая.": "Contract history is empty.",
    "Текущая база / планета для выставления": "Current base / planet for listing",
    "При выставлении товар сразу снимается со склада и резервируется в контракте. Если срок истечёт — товар вернётся на склад продавца.": "When listed, the item is immediately removed from the warehouse and reserved in the contract. If the lifetime expires, the item returns to the seller warehouse.",
    "Товар будет лежать здесь. Проверь, что база/планета доступна по репутации.": "The item will be stored here. Check that the base/planet is accessible by reputation.",
    "Оборудование": "Equipment",
    "Здесь собрано всё, что не относится к обычному товару в трюме: вооружение, турели, щиты, сканеры, боеприпасы, ID пилота, нанороботы, батареи щита и прочая корабельная экипировка.": "This contains everything that is not regular cargo: weapons, turrets, shields, scanners, ammo, pilot ID, nanobots, shield batteries and other ship equipment.",
    "Здесь собрано всё, что не относится к обычному товару в трюме: вооружение, турели, щиты, сканеры, боеприпасы, ID пилота, нанороботы, батареи щита и прочая корабе": "This contains everything that is not regular cargo: weapons, turrets, shields, scanners, ammo, pilot ID, nanobots, shield batteries and other ship equipment.",
    "Текущая база": "Current base",
    "Последняя база": "Last base",
    "Оружие / турели": "Weapons / turrets",
    "Щиты / защита": "Shields / protection",
    "Сканеры / электроника": "Scanners / electronics",
    "Двигатели / форсаж": "Engines / thrusters",
    "Прочее оборудование": "Other equipment",
    "Боеприпасы / расходники": "Ammo / consumables",
    "Слот": "Slot",
    "Оружие не установлено.": "No weapons installed.",
    "Щитов и защитных модулей нет.": "No shields or protection modules.",
    "Сканеры отсутствуют.": "No scanners.",
    "Двигатели и форсаж не найдены.": "No engines or thrusters found.",
    "Прочее оборудование не найдено.": "No other equipment found.",
    "Боеприпасов и расходников нет.": "No ammo or consumables.",
    "Нанороботов нет.": "No nanobots.",
    "Батарей щита нет.": "No shield batteries.",
    "Деньги персонажа": "Character credits",
    "Банк аккаунта": "Account bank",
    "Банк аккаунта хранит кредиты отдельно от текущего корабля.": "Account bank stores credits separately from the current ship.",
    "Перевод другому пилоту": "Transfer to another pilot",
    "Имя пилота-получателя": "Receiver pilot name",
    "Сумма перевода": "Transfer amount",
    "Перевести": "Transfer",
    "Банк персонажа": "Character bank",
    "Операция": "Operation",
    "Перевести с персонажа в банк": "Deposit from character to bank",
    "Перевести из банка персонажу": "Withdraw from bank to character",
    "Сумма": "Amount",
    "Выполнить": "Execute",
    "Сначала списывается игровой счёт персонажа. Если его не хватает, остаток берётся из банка аккаунта.": "Character in-game credits are used first. If not enough, the rest is taken from the account bank.",
    "Фракция": "Faction",
    "Шкала": "Scale",
    "Значение": "Value",
    "Шкала слева направо: от красного (-1.0) через нейтральное белое (0.0) к зелёному (+1.0). Заливка идёт от центра: влево красным для отрицательной репутации, вправо зелёным для положительной.": "Scale left to right: red (-1.0), neutral white (0.0), green (+1.0). Fill goes from the center: left red for negative reputation, right green for positive.",
    "Шкала слева направо: от красного (-1.0) через нейтральное белое (0.0) к зелёному (+1.0). Заливка идёт от центра: влево красным для отрицательной репутации, вправ": "Scale left to right: red (-1.0), neutral white (0.0), green (+1.0). Fill goes from the center.",
    "Неизвестно": "Unknown",
    "Текущая система": "Current system",
    "Систем": "Systems",
    "Планет / станций": "Planets / stations",
    "Отметок карты": "Map marks",
    "Ниже показаны реально посещённые объекты: отдельно системы, отдельно планеты и станции/базы.": "Below are actually visited objects: systems, planets and stations/bases are separated.",
    "Системы": "Systems",
    "Планеты": "Planets",
    "Станции / базы": "Stations / bases",
    "Прыжковые дыры и сырые отметки карты": "Jump holes and raw map marks",
    "Первые 250 отметок карты": "First 250 map marks",
    "Объект": "Object",
    "Система": "System",
    "Нет посещённых систем.": "No visited systems.",
    "Нет посещённых планет.": "No visited planets.",
    "Нет посещённых станций и баз.": "No visited stations or bases.",
    "Нет записей прыжковых дыр.": "No jump-hole records.",
    "Нет отметок карты.": "No map marks.",
    "Время в игре": "Time played",
    "Создан аккаунт": "Account created",
    "Создан персонаж / первая дата файла": "Character created / first file date",
    "Последнее изменение": "Last modified",
    "Убийства": "Kills",
    "Смерти": "Deaths",
    "Миссии успех/провал": "Missions success/fail",
    "Всего": "Total",
    "Персонаж": "Character",
    "Имя персонажа": "Character name",
    "Файл": "File",
    "Кредиты": "Credits",
    "Админская зона": "Admin area",
    "Персонажи": "Characters",
    "Поиск по аккаунту или персонажу...": "Search by account or character...",
    "главной": "home",
    "админка": "admin",
    "выйти": "logout",
    "Неизвестный предмет": "Unknown item",
    "Описание пока не импортировано. Запусти: py -m fl_panel.import_item_assets --data путь_к_DATA --img fl_panel/static/img/items": "Description is not imported yet. Run: py -m fl_panel.import_item_assets --data path_to_DATA --img fl_panel/static/img/items"
  }
};

const FLP_TRANSLATABLE_ATTRS = ['placeholder', 'title', 'aria-label'];
const FLP_TEXT_ORIGINALS = new WeakMap();

/* v53: extra EN translations from UI screenshots */
Object.assign(FLP_I18N.en, {
  "ранг": "rank",
  "Склад базы:": "Base warehouse:",
  "Личное хранилище пилота": "Personal pilot storage",
  "Не пересекается с трюмом корабля и другими персонажами.": "Does not overlap with ship hold or other characters.",
  "DB-only рынок в стиле EVE: товар продаётся из склада базы, резервируется в SQLite и после покупки попадает на склад покупателя в той же локации.": "DB-only EVE-style market: the item is sold from the base warehouse, reserved in SQLite, and after purchase goes to the buyer warehouse in the same location.",
  "Важно: покупатель заберёт товар именно на этой базе/планете. В списке контрактов место указано отдельно, чтобы пилот заранее понимал, доступна ли ему эта локация по репутации.": "Important: the buyer receives the item on this exact base/planet. The contract list shows the location separately so the pilot can check whether reputation allows access.",
  "Ваш контракт": "Your contract",
  "ВАШ КОНТРАКТ": "YOUR CONTRACT",
  "Оружие": "Weapon",
  "Турели": "Turrets",
  "Щиты": "Shields",
  "Сканеры": "Scanners",
  "Форсаж": "Thruster",
  "Неизвестные": "Unknown",
  "Тракторы": "Tractors",
  "Шины": "Mines",
  "минесеквипмент": "Mine equipment",
  "miscEquipment": "Misc equipment",
  "misc_equipment": "Misc equipment",
  "Текущая база / планета для выставления": "Current base / planet for listing",
  "База / планета Planet Erie": "Base / planet Planet Erie",
  "Ваш контракт": "Your contract",
  "Личный склад пилота": "Personal pilot warehouse"
});

const FLP_DYNAMIC_EN_RULES = [
  {
    re: /^Ресурсы\s+на\s+складе:\s*(.+)$/i,
    fn: (m) => `Resources in warehouse: ${m[1]}`
  },
  {
    re: /^([\d\s.,]+)\s+кредитов\s+выведено\s+из\s+bank\.ini\s+персонажу\s+\(([^)]+)\)\.?$/i,
    fn: (m) => `${m[1]} credits withdrawn from bank.ini to character (${m[2].replace('через файл', 'via file').replace('через FLHook', 'via FLHook')}).`
  },
  {
    re: /^Получено\s+([\d\s.,]+)\s+кредитов\s+от\s+пилота\s+(.+)\.?$/i,
    fn: (m) => `Received ${m[1]} credits from pilot ${m[2]}.`
  },
  {
    re: /^НАНОРОБОТОВ\s+БОЛЬШЕ\s+ШТАТНОГО\s+ЛИМИТА\s+КОРАБЛЯ:\s*([\d\s.,]+)\s*>\s*([\d\s.,]+)\.\s*ПРИНЯТО\s+КАК\s+ТЕКУЩИЙ\s+ЗАПАС\s+ПЕРСОНАЖА\.?$/i,
    fn: (m) => `Nanobots exceed ship limit: ${m[1]} > ${m[2]}. Accepted as current character stock.`
  },
  {
    re: /^ПЕРЕДАНО\s+СКЛАД\s*→\s*СКЛАД:\s*([\d\s.,]+)\s*ШТ\.\s*«([^»]+)»\s+НА\s+ЛИЧНЫЙ\s+СКЛАД\s+ПИЛОТА\s+«([^»]+)»\s+НА\s+БАЗЕ\s+«([^»]+)»\.\s*КОРАБЛЬ\s+ПОЛУЧАТЕЛЯ\s+НЕ\s+ЗАТРАГИВАЛСЯ\.?$/i,
    fn: (m) => `Transferred warehouse → warehouse: ${m[1]} pcs. “${m[2]}” to personal warehouse of pilot “${m[3]}” at “${m[4]}”. Receiver ship was not touched.`
  },
  {
    re: /^ПЕРЕВОД\s+([\d\s.,]+)\s+КРЕДИТОВ\s+ПИЛОТУ\s+(.+?)\s+ВЫПОЛНЕН:\s*СПИСАНО\s+([\d\s.,]+)\s+С\s+ПЕРСОНАЖА\.\s*РЕЖИМ:\s*ФАЙЛОВЫЙ\s+РЕЖИМ\.?$/i,
    fn: (m) => `Transfer of ${m[1]} credits to pilot ${m[2]} completed: ${m[3]} deducted from character. `
  },
  {
    re: /^ПЕРЕВОД\s+([\d\s.,]+)\s+КРЕДИТОВ\s+ПИЛОТУ\s+(.+?)\s+ВЫПОЛНЕН\.?$/i,
    fn: (m) => `Transfer of ${m[1]} credits to pilot ${m[2]} completed.`
  },
  {
    re: /^([\d\s.,]+)\s+кредитов\s+переведено\s+с\s+персонажа\s+в\s+bank\.ini\s+\(через\s+файл\)\.?$/i,
    fn: (m) => `${m[1]} credits transferred from character to bank.ini.`
  },
  {
    re: /^([\d\s.,]+)\s+кредитов\s+переведено\s+из\s+bank\.ini\s+персонажу\s+\(через\s+файл\)\.?$/i,
    fn: (m) => `${m[1]} credits transferred from bank.ini to character.`
  },
  {
    re: /^([\d\s.,]+)\s+кредитов\s+переведено\s+другому\s+пилоту\.?$/i,
    fn: (m) => `${m[1]} credits transferred to another pilot.`
  },
  {
    re: /^([\d\s.,]+)\s+кредитов\s+списано\.?$/i,
    fn: (m) => `${m[1]} credits deducted.`
  },
  {
    re: /^([\d\s.,]+)\s+кредитов\s+зачислено\.?$/i,
    fn: (m) => `${m[1]} credits credited.`
  },
  {
    re: /^(.+?)\s*·\s*ранг\s*(\d+)$/i,
    fn: (m) => `${m[1]} · rank ${m[2]}`
  },
  {
    re: /^ранг\s*(\d+)$/i,
    fn: (m) => `rank ${m[1]}`
  },
  {
    re: /^Склад базы:\s*(.+)$/i,
    fn: (m) => `Base warehouse: ${m[1]}`
  },
  {
    re: /^Личное хранилище пилота\s+«([^»]+)»\.\s*Не пересекается с трюмом корабля и другими персонажами\.$/i,
    fn: (m) => `Personal pilot storage “${m[1]}”. Does not overlap with ship hold or other characters.`
  },
  {
    re: /^Личный склад пилота\s+«([^»]+)»\.\s*Не пересекается с трюмом корабля и другими персонажами\.$/i,
    fn: (m) => `Personal pilot warehouse “${m[1]}”. Does not overlap with ship hold or other characters.`
  },
  {
    re: /^Репутация\s+(.+)$/i,
    fn: (m) => `Reputation ${m[1]}`
  },
  {
    re: /^Свободно:\s*(.+)$/i,
    fn: (m) => `Free: ${m[1]}`
  },
  {
    re: /^Запущено\s*×\s*(.+)$/i,
    fn: (m) => `Started ×${m[1]}`
  },
  {
    re: /^до\s+(.+)$/i,
    fn: (m) => `until ${m[1]}`
  },
  {
    re: /^Продажа\s*→\s*(.+)$/i,
    fn: (m) => `Sale → ${m[1]}`
  },
  {
    re: /^Покупка\s*→\s*(.+)$/i,
    fn: (m) => `Purchase → ${m[1]}`
  },
  {
    re: /^На складе:\s*(.+)$/i,
    fn: (m) => `In warehouse: ${m[1]}`
  },
  {
    re: /^База\s*\/\s*планета:\s*(.+)$/i,
    fn: (m) => `Base / planet: ${m[1]}`
  },
  {
    re: /^(.+?)\s+—\s+на\s+складе\s+([\d\s.,]+)\s+шт\.?$/i,
    fn: (m) => `${m[1]} — in warehouse ${m[2]} pcs.`
  },
  {
    re: /^(Металлургия|Переработка|Плавка|Огранка|Топливо|Химия|Электроника|Электротехника|Боеприпасы|Фармацевтика|Сборка|Производство|Компоненты):\s+(.+)$/i,
    fn: (m) => {
      const map = {
        'Металлургия': 'Metallurgy',
        'Переработка': 'Recycling',
        'Плавка': 'Smelting',
        'Огранка': 'Cutting',
        'Топливо': 'Fuel',
        'Химия': 'Chemistry',
        'Электроника': 'Electronics',
        'Электротехника': 'Electronics',
        'Боеприпасы': 'Ammunition',
        'Фармацевтика': 'Pharmaceuticals',
        'Сборка': 'Assembly',
        'Производство': 'Production',
        'Компоненты': 'Components'
      };
      return `${map[m[1]] || m[1]}: ${m[2]}`;
    }
  }
];


/* v55: finance flash EN translations */
Object.assign(FLP_I18N.en, {
  "кредитов переведено с персонажа в bank.ini (через файл).": "credits transferred from character to bank.ini.",
  "кредитов переведено из bank.ini персонажу (через файл).": "credits transferred from bank.ini to character.",
  "кредитов переведено другому пилоту.": "credits transferred to another pilot.",
  "Кредиты переведены.": "Credits transferred.",
  "Недостаточно кредитов.": "Not enough credits.",
  "Недостаточно средств.": "Not enough funds.",
  "Сумма должна быть больше нуля.": "Amount must be greater than zero.",
  "Некорректная сумма.": "Invalid amount."
});


/* v56: extra EN translations from reported screenshots */
Object.assign(FLP_I18N.en, {
  "НЕИЗВЕСТНЫЙ ПРЕДМЕТ": "UNKNOWN ITEM",
  "Неизвестный предмет": "Unknown item",
  "Нанороботов больше штатного лимита корабля": "Nanobots exceed ship limit",
  "Принято как текущий запас персонажа": "Accepted as current character stock",
  "Передано склад → склад": "Transferred warehouse → warehouse",
  "Корабль получателя не затрагивался": "Receiver ship was not touched",
  "Перевод кредитов выполнен": "Credits transfer completed",
  "Режим: файловый режим": ""
});


/* v58: finance history EN translations */
Object.assign(FLP_I18N.en, {
  "История финансовых операций": "Financial operation history",
  "История хранится отдельно для каждого пилота: входящие и исходящие переводы, а также переводы между персонажем и bank.ini.": "History is stored separately for each pilot: incoming and outgoing transfers, plus transfers between character and bank.ini.",
  "Финансовых операций у этого пилота пока нет.": "This pilot has no financial operations yet.",
  "Дата": "Date",
  "Контрагент": "Counterparty",
  "Примечание": "Note",
  "Персонаж → банк": "Char → bank",
  "Банк → персонаж": "Bank → char",
  "Входящий перевод": "Incoming",
  "Исходящий перевод": "Outgoing",
  "Перевод пилоту": "Pilot transfer",
  "Свои счета": "Own accounts",
  "через файл": "via file",
  "через FLHook": "via FLHook",
  "файловый режим": "file mode",
  "Получено": "Received",
  "от пилота": "from pilot",
  "кредитов выведено из bank.ini персонажу": "credits withdrawn from bank.ini to character"
});


/* v59: hide finance mode labels from UI */
Object.assign(FLP_I18N.en, {
  "кредитов переведено с персонажа в bank.ini.": "credits transferred from character to bank.ini.",
  "кредитов выведено из bank.ini персонажу.": "credits withdrawn from bank.ini to character.",
  "Кто": "Who"
});


/* v62: extra EN cleanup for mixed craft/contracts/finance texts */
Object.assign(FLP_I18N.en, {
  "в bank.ini": "to bank.ini",
  "на складе": "in warehouse",
  "шт.": "pcs."
});

/* v63: exact craft recipe names and descriptions EN translations */
Object.assign(FLP_I18N.en, {
  "Плавка: Aluminium Ore → Aluminium": "Smelting: Aluminium Ore → Aluminium",
  "Плавка: Beryllium Ore → Beryllium": "Smelting: Beryllium Ore → Beryllium",
  "Плавка: Cobalt Ore → Cobalt": "Smelting: Cobalt Ore → Cobalt",
  "Плавка: Copper Ore → Copper": "Smelting: Copper Ore → Copper",
  "Плавка: Gold Ore → Gold": "Smelting: Gold Ore → Gold",
  "Плавка: Niobium Ore → Niobium": "Smelting: Niobium Ore → Niobium",
  "Плавка: Platinum Ore → Platinum": "Smelting: Platinum Ore → Platinum",
  "Плавка: Silver Ore → Silver": "Smelting: Silver Ore → Silver",
  "Огранка: Uncut Diamonds → Diamonds": "Cutting: Uncut Diamonds → Diamonds",
  "Переработка: Scrap Metal → Basic Alloy": "Recycling: Scrap Metal → Basic Alloy",
  "Переработка: Premium Scrap → Super Alloy": "Recycling: Premium Scrap → Super Alloy",
  "Металлургия: Basic Alloy": "Metallurgy: Basic Alloy",
  "Производство: Industrial Materials": "Production: Industrial Materials",
  "Металлургия: High Temperature Alloy": "Metallurgy: High Temperature Alloy",
  "Металлургия: Super Alloy": "Metallurgy: Super Alloy",
  "Электрометаллургия: Superconductors": "Electrometallurgy: Superconductors",
  "Корпусные панели: Hull Panels": "Hull panels: Hull Panels",
  "Механика: Manifolds": "Mechanics: Manifolds",
  "Электролиз: Water → Oxygen": "Electrolysis: Water → Oxygen",
  "Изотопное разделение: Helium → Helium-3": "Isotope separation: Helium → Helium-3",
  "Изотопное разделение: Water → Deuterium": "Isotope separation: Water → Deuterium",
  "Переработка: Oil → LPG": "Refining: Oil → LPG",
  "Крекинг: Hydrocarbons → Petrochemicals": "Cracking: Hydrocarbons → Petrochemicals",
  "Полимеризация: Petrochemicals → Plastics": "Polymerization: Petrochemicals → Plastics",
  "Полимеры: Plastics → Polymers": "Polymers: Plastics → Polymers",
  "Топливо: H-Fuel": "Fuel: H-Fuel",
  "Топливо: MOX (Bretonia)": "Fuel: MOX (Bretonia)",
  "Топливо: MOX (Rheinland)": "Fuel: MOX (Rheinland)",
  "Тара: Hazmat Canisters": "Containers: Hazmat Canisters",
  "Электроника: Optical Chips": "Electronics: Optical Chips",
  "Электроника: Nanocapacitors": "Electronics: Nanocapacitors",
  "Электроника: Optronics": "Electronics: Optronics",
  "Электроника: Quantum Multiplexors": "Electronics: Quantum Multiplexors",
  "Электроника: Bioneural Processors": "Electronics: Bioneural Processors",
  "Электроника: Counterfeit Software": "Electronics: Counterfeit Software",
  "Фильтрация: Xenobiotic Filters": "Filtration: Xenobiotic Filters",
  "Промышленность: Engine Components": "Industry: Engine Components",
  "Промышленность: Robotics": "Industry: Robotics",
  "Промышленность: Mining Machinery": "Industry: Mining Machinery",
  "Инфраструктура: Jump Gate / Trade Lane Parts": "Infrastructure: Jump Gate / Trade Lane Parts",
  "Промышленность: Military Vehicles (Liberty)": "Industry: Military Vehicles (Liberty)",
  "Промышленность: Military Vehicles (Rheinland)": "Industry: Military Vehicles (Rheinland)",
  "Агро: Fertilizer": "Agro: Fertilizer",
  "Агро: FloraGro": "Agro: FloraGro",
  "Пища: Food Rations": "Food: Food Rations",
  "Пища: Luxury Food": "Food: Luxury Food",
  "Агро: Tea": "Agro: Tea",
  "Агро: Tobacco": "Agro: Tobacco",
  "Пища: Wine": "Food: Wine",
  "Пища: Synth Paste": "Food: Synth Paste",
  "Медицина: Pharmaceuticals": "Medicine: Pharmaceuticals",
  "Медицина: Cryocubes": "Medicine: Cryocubes",
  "Товары: Consumer Goods": "Goods: Consumer Goods",
  "Развлечения: Holo-tainment Bands": "Entertainment: Holo-tainment Bands",
  "Развлечения: Hypno-tainment Bands": "Entertainment: Hypno-tainment Bands",
  "Luxury: Holosculptures": "Luxury: Holosculptures",
  "Luxury: Luxury Consumer Goods": "Luxury: Luxury Consumer Goods",
  "Вооружение: Light Arms": "Weapons: Light Arms",
  "Вооружение: Munitions": "Weapons: Munitions",
  "Вооружение: Blackmarket Munitions": "Weapons: Blackmarket Munitions",
  "Вооружение: Nuclear Devices": "Weapons: Nuclear Devices",
  "Базовая переплавка алюминиевой руды в металл.": "Basic smelting of aluminium ore into metal.",
  "Базовая переплавка бериллиевой руды в металл.": "Basic smelting of beryllium ore into metal.",
  "Базовая переплавка кобальтовой руды в металл.": "Basic smelting of cobalt ore into metal.",
  "Базовая переплавка медной руды в металл.": "Basic smelting of copper ore into metal.",
  "Переплавка золотой руды. Дорогой металл используется только в электронике и luxury-цепочках.": "Smelting gold ore. This expensive metal is used only in electronics and luxury chains.",
  "Переплавка ниобиевой руды для сверхпроводников и продвинутых сплавов.": "Smelting niobium ore for superconductors and advanced alloys.",
  "Переплавка платиновой руды. Платина используется ограниченно в дорогих high-tech цепочках.": "Smelting platinum ore. Platinum is used only in expensive high-tech chains.",
  "Переплавка серебряной руды для электроники и проводников.": "Smelting silver ore for electronics and conductors.",
  "Огранка необработанных алмазов в товарные Diamonds.": "Cutting unprocessed diamonds into marketable Diamonds.",
  "Дешёвая переработка металлолома в базовый сплав.": "Cheap recycling of scrap metal into a basic alloy.",
  "Переработка качественного лома в продвинутый сплав.": "Recycling high-grade scrap into an advanced alloy.",
  "Алюминий и медь дают базовый конструкционный сплав.": "Aluminium and copper form a basic structural alloy.",
  "Конструкционный материал для заводов и machinery-цепочек.": "Structural material for factories and machinery chains.",
  "Термостойкие сплавы для двигателей, корпусов и сложного оборудования.": "Heat-resistant alloys for engines, hulls and complex equipment.",
  "Продвинутый сплав без абсурдных luxury-компонентов.": "Advanced alloy without absurd luxury components.",
  "Логичная цепочка сверхпроводников из меди, серебра и ниобия.": "A logical superconductor chain made from copper, silver and niobium.",
  "Простые корпусные панели из лёгких сплавов.": "Simple hull panels made from light alloys.",
  "Механические коллекторы и силовые узлы из термостойких материалов.": "Mechanical manifolds and power units made from heat-resistant materials.",
  "Получение кислорода из воды.": "Producing oxygen from water.",
  "Очистка гелия с выделением Helium-3.": "Helium purification with Helium-3 extraction.",
  "Получение дейтерия из воды на промышленной установке.": "Producing deuterium from water at an industrial plant.",
  "Нефтепереработка в Liquified Petroleum Gas.": "Oil refining into Liquified Petroleum Gas.",
  "Химическая переработка углеводородов в petrochemicals.": "Chemical processing of hydrocarbons into petrochemicals.",
  "Пластики делаются из нефтехимии и воды, а не из драгоценных металлов.": "Plastics are made from petrochemicals and water, not precious metals.",
  "Базовая цепочка полимерных материалов.": "Basic polymer material chain.",
  "Топливная смесь из LPG и дейтерия.": "Fuel mixture from LPG and deuterium.",
  "MOX как продвинутое топливо: дейтерий, плутоний и термостойкие контейнеры.": "MOX as advanced fuel: deuterium, plutonium and heat-resistant containers.",
  "Рейнландский вариант MOX с более дорогими сплавами.": "Rheinland MOX variant with more expensive alloys.",
  "Контейнеры для опасных материалов.": "Containers for hazardous materials.",
  "Чипы используют дорогие металлы только там, где это логично — в электронике.": "Chips use expensive metals only where it makes sense — in electronics.",
  "Наноконденсаторы из проводников, золота и полимеров.": "Nanocapacitors made from conductors, gold and polymers.",
  "Сложная оптроника из чипов, наноконденсаторов и сверхпроводников.": "Complex optronics made from chips, nanocapacitors and superconductors.",
  "Квантовые мультиплексоры — high-tech, поэтому золото здесь уместно.": "Quantum multiplexors are high-tech, so gold is appropriate here.",
  "Бионейронные процессоры как продвинутая электронно-полимерная цепочка.": "Bioneural processors as an advanced electronic-polymer chain.",
  "Носители и аппаратные ключи для Counterfeit Software.": "Media and hardware keys for Counterfeit Software.",
  "Фильтры из полимеров, электроники и герметичной тары.": "Filters made from polymers, electronics and sealed containers.",
  "Компоненты двигателя из термостойких сплавов и проводников.": "Engine components made from heat-resistant alloys and conductors.",
  "Роботизированная строительная техника из industrial materials и двигателя.": "Robotic construction equipment from industrial materials and engine components.",
  "Горнодобывающая техника на базе robotics/industrial machinery.": "Mining machinery based on robotics and industrial machinery.",
  "Детали торговых линий требуют двигателя, сверхпроводников и термостойких материалов.": "Trade lane parts require engine components, superconductors and heat-resistant materials.",
  "Военная техника Liberty из техники, двигателей и вооружения.": "Liberty military vehicles made from machinery, engines and weapons.",
  "Военная техника Rheinland с усиленной бронёй.": "Rheinland military vehicles with reinforced armor.",
  "Удобрения из нефтехимии и воды.": "Fertilizer made from petrochemicals and water.",
  "FloraGro как агро-химическая смесь.": "FloraGro as an agrochemical mixture.",
  "Простейшая пищевая цепочка: вода + удобрения.": "The simplest food chain: water + fertilizer.",
  "Luxury Food получается из food rations и агро-компонента, без металлов.": "Luxury Food is made from food rations and an agro component, without metals.",
  "Чай выращивается из агро-смеси и воды.": "Tea is grown from an agro mixture and water.",
  "Табак как агро-товар с химической обработкой.": "Tobacco as an agro commodity with chemical processing.",
  "Wine делается из пищевой/агро-цепочки. Никакого золота, платины или сплавов.": "Wine is made from the food/agro chain. No gold, platinum or alloys.",
  "Синтетическая паста из пищевой базы и упаковочного полимера.": "Synthetic paste made from a food base and packaging polymer.",
  "Фармацевтика из нефтехимии, воды и полимерной упаковки.": "Pharmaceuticals from petrochemicals, water and polymer packaging.",
  "Криокубы требуют воды, лёгкого корпуса и сверхпроводников.": "Cryocubes require water, a light hull and superconductors.",
  "Обычные потребительские товары из пластика, лёгкого металла и простой электроники.": "Regular consumer goods made from plastic, light metal and simple electronics.",
  "Голографические развлекательные устройства.": "Holographic entertainment devices.",
  "Улучшенная версия holo-bands с оптроникой.": "Improved holo-bands with optronics.",
  "Декоративные luxury-изделия. Золото используется как отделка, а не в пищевых рецептах.": "Decorative luxury goods. Gold is used as trim, not in food recipes.",
  "Набор дорогих потребительских товаров.": "A set of expensive consumer goods.",
  "Лёгкое оружие из сплава, пластика и простой электроники.": "Light arms made from alloy, plastic and simple electronics.",
  "Боеприпасы из металла, химии и меди.": "Munitions made from metal, chemicals and copper.",
  "Нелегальная модификация боеприпасов.": "Illegal modification of munitions.",
  "Сложное военное производство из радиоактивных материалов, корпуса и электроники.": "Complex military production from radioactive materials, hull parts and electronics."
});



function flpTranslateDynamic(text, lang) {
  if (lang !== 'en') return null;
  const original = String(text || '').trim();
  for (const rule of FLP_DYNAMIC_EN_RULES) {
    const match = original.match(rule.re);
    if (match) return rule.fn(match);
  }
  // v59 fallback: remove finance technical mode labels from mixed strings.
  if (lang === 'en') {
    const cleaned = original
      .replace(/\s*\((через файл|через FLHook)\)\.?/gi, '.')
      .replace(/\s*Режим:\s*файловый режим\.?/gi, '.')
      .replace(/\.\s*\./g, '.');

    if (cleaned !== original) {
      const translated = flpTranslateDynamic(cleaned, lang);
      if (translated) return translated;
      return cleaned
        .replace(/кредитов/gi, 'credits')
        .replace(/переведено с персонажа в bank\.ini/gi, 'transferred from character to bank.ini')
        .replace(/выведено из bank\.ini персонажу/gi, 'withdrawn from bank.ini to character')
        .replace(/списано/gi, 'deducted')
        .replace(/с персонажа/gi, 'from character');
    }
  }

  return null;
}



/* v92: complete RU/EN localization pass */
Object.assign(FLP_I18N.en, {
  "Админская зона": "Admin zone",
  "Операторская часть: онлайн-пилоты FLHook, консоль команд, аккаунты и просмотр имущества пилота на всех базах.": "Operator panel: FLHook online pilots, command console, accounts, and pilot assets across all bases.",
  "Онлайн-пилоты FLHook": "FLHook online pilots",
  "Онлайн-пилотов нет или FLHook не вернул список.": "No online pilots, or FLHook did not return a list.",
  "FLHook console": "FLHook console",
  "Команды выполняются через WPort FLHook. Например:": "Commands are executed through FLHook WPort. Examples:",
  "Команда:": "Command:",
  "Открыть консоль FLHook": "Open FLHook console",
  "Выполнить": "Run",
  "Аккаунты": "Accounts",
  "Аккаунт": "Account",
  "Raw FLHook": "Raw FLHook",
  "Имущество на всех базах / планетах": "Assets on all bases / planets",
  "Снаряжение корабля": "Ship equipment",
  "Админские операции со складом": "Admin warehouse operations",
  "Админ может создать, удалить или переместить любой item в любом складе пилота. Item указывается как hash / nickname / good_nickname / equipment_nickname.": "Admin can create, delete, or move any item in any pilot warehouse. Item is specified as hash / nickname / good_nickname / equipment_nickname.",
  "Добавить item в склад": "Add item to warehouse",
  "Удалить item со склада": "Delete item from warehouse",
  "Переместить item": "Move item",
  "Создать / добавить": "Create / add",
  "Склад / база": "Warehouse / base",
  "Откуда": "From",
  "Куда": "To",
  "Пилот-получатель": "Target pilot",
  "Item hash": "Item hash",
  "Item hash / nickname": "Item hash / nickname",
  "Пилот сейчас": "Pilot now",
  "в космосе": "in space",
  "Место": "Location",
  "онлайн": "online",
  "offline / unknown": "offline / unknown",
  "аккаунт": "account",
  "админка": "admin",
  "клиентский вход": "client login",
  "← админка": "← admin",
  "Банк аккаунта": "Account bank",
  "Кредиты персонажа": "Character credits",
  ".fl файл": ".fl file",
  "Складов на базах/планетах пока нет.": "No warehouses on bases/planets yet.",
  "строк": "rows",
  "шт.": "pcs.",
  "объём": "volume",
  "текущая": "current",
  "Пусто": "Empty",
  "Ваши склады": "Your warehouses",
  "Ваш склад": "Your warehouse",
  "Здесь показаны все базы и планеты, где у текущего пилота есть складские ресурсы. Нажми на базу, затем на ресурс для операций.": "This shows all bases and planets where the current pilot has warehouse resources. Click a base, then a resource for operations.",
  "У этого пилота пока нет складов на других базах или планетах.": "This pilot has no warehouses on other bases or planets yet.",
  "База / планета": "Base / planet",
  "База / планета Planet Erie": "Base / planet Planet Erie",
  "Ресурсы на складе": "Resources in warehouse",
  "Ресурсы на складе:": "Resources in warehouse:",
  "История операций склада": "Warehouse operation history",
  "История хранится отдельно для каждого пилота и текущей базы: склад → склад, склад ↔ трюм, удаления и пополнения склада.": "History is stored separately for each pilot and current base: warehouse → warehouse, warehouse ↔ hold, removals and additions.",
  "Истории операций склада на этой базе пока нет.": "There is no warehouse operation history on this base yet.",
  "Добавлено в склад": "Added to warehouse",
  "Удалено со склада": "Removed from warehouse",
  "Склад → трюм": "Warehouse → hold",
  "Трюм → склад": "Hold → warehouse",
  "Передано пилоту": "Sent to pilot",
  "Получено от пилота": "Received from pilot",
  "Кому: пилоту": "To: pilot",
  "От: пилота": "From: pilot",
  "Кому:": "To:",
  "От:": "From:",
  "Пилот": "Pilot",
  "Передача другому пилоту выполняется только склад → склад. .fl-файлы, FLHook и корабль получателя не затрагиваются.": "Transfer to another pilot is warehouse → warehouse only. .fl files, FLHook, and the receiver ship are not touched.",
  "Перенос в трюм доступен только на текущей базе пилота.": "Moving to hold is available only at the pilot's current base.",
  "В трюм через панель пока можно переносить только обычный груз / commodity с объёмом больше 0. Эквипмент и снаряжение пока не трогаем.": "Through the panel, only normal cargo / commodity with volume greater than 0 can be moved to the hold. Equipment is not touched yet.",
  "Выставить контракт": "Create contract",
  "Цена за весь контракт": "Full contract price",
  "Срок": "Lifetime",
  "часов": "hours",
  "дней": "days",
  "Предмет со склада": "Warehouse item",
  "Выставить предмет со склада на продажу": "Create sale contract from warehouse item",
  "Создать контракт": "Create contract",
  "Контракт создан": "Contract created",
  "Контракт куплен": "Contract bought",
  "Контракт отменён": "Contract canceled",
  "Контракт создан из склада.": "Contract created from warehouse.",
  "Товар зарезервирован в контракте": "Item reserved in contract",
  "Активные контракты сервера": "Server active contracts",
  "Мои контракты": "My contracts",
  "История контрактов": "Contract history",
  "Разделы контрактов": "Contract sections",
  "Купить": "Buy",
  "Цена": "Price",
  "Продавец": "Seller",
  "Покупатель": "Buyer",
  "Истекает": "Expires",
  "Статус": "Status",
  "истёк": "expired",
  "активен": "active",
  "куплен": "bought",
  "отменён": "canceled",
  "Сессия истекла. Войдите заново.": "Session expired. Log in again.",
  "Количество должно быть положительным целым числом.": "Quantity must be a positive integer.",
  "Предмет не найден в БД.": "Item not found in DB.",
  "Предмет не найден в БД. Укажи hash/nickname/good_nickname/equipment_nickname.": "Item not found in DB. Specify hash/nickname/good_nickname/equipment_nickname.",
  "Не выбран склад / база.": "No warehouse / base selected.",
  "Не выбран исходный или целевой склад.": "Source or target warehouse not selected.",
  "Пилот-получатель не найден.": "Receiver pilot not found.",
  "Найдено несколько пилотов с таким никнеймом.": "Multiple pilots with this nickname found.",
  "Найдено несколько пилотов с таким никнеймом. Нужна более точная идентификация.": "Multiple pilots with this nickname found. More precise identification is required.",
  "Такого предмета нет на исходном складе.": "This item is not in the source warehouse.",
  "Не удалось списать предмет с исходного склада.": "Could not deduct item from the source warehouse.",
  "Нельзя передать предмет самому себе.": "Cannot transfer item to yourself.",
  "Предмет не выбран.": "No item selected.",
  "Укажи никнейм пилота-получателя.": "Enter receiver pilot nickname.",
  "Такого предмета нет в личном складе отправителя на этой базе.": "This item is not in sender's personal warehouse on this base.",
  "Не удалось определить предмет склада.": "Could not identify warehouse item.",
  "На складе только": "Only in warehouse",
  "Нельзя передать": "Cannot transfer",
  "Нельзя переместить": "Cannot move",
  "Недостаточно средств.": "Insufficient funds.",
  "Срок жизни контракта должен быть положительным числом.": "Contract lifetime must be a positive number.",
  "Максимальный срок контракта: 30 дней.": "Maximum contract lifetime: 30 days.",
  "Максимальный срок контракта: 720 часов.": "Maximum contract lifetime: 720 hours.",
  "Цена должна быть положительным целым числом.": "Price must be a positive integer.",
  "Контракт не найден.": "Contract not found.",
  "Этот контракт уже закрыт.": "This contract is already closed.",
  "Можно отменить только свой контракт.": "Only your own contract can be canceled.",
  "Нельзя купить собственный контракт.": "Cannot buy your own contract.",
  "Некорректный номер контракта.": "Invalid contract number.",
  "Файл покупателя не найден.": "Buyer file not found.",
  "Аккаунт продавца не найден. Покупка отменена.": "Seller account not found. Purchase canceled.",
  "Крафт не запущен": "Craft not started",
  "Крафт запущен": "Craft started",
  "Готовый крафт": "Finished craft",
  "добавлен в личный склад пилота": "added to pilot personal warehouse",
  "Задание крафта не найдено.": "Craft job not found.",
  "Крафт ещё не готов.": "Craft is not ready yet.",
  "Готовое задание нельзя отменить. Его нужно забрать.": "A finished job cannot be canceled. It must be claimed.",
  "Это задание уже не активно.": "This job is no longer active.",
  "Ресурсы возвращены в личный склад пилота": "Resources returned to pilot personal warehouse",
  "Дата": "Date",
  "Операция": "Operation",
  "Примечание": "Note",
  "Строк": "Rows",
  "Кол-во": "Qty",
  "Кол-во / слот": "Qty / slot",
  "Объём 1": "Volume 1",
  "Количество": "Quantity",
  "Тип": "Type",
  "Предмет": "Item",
  "Название": "Name",
  "Файл": "File",
  "Персонаж": "Character",
  "Система": "System",
  "База": "Base",
  "Корабль": "Ship",
  "Ранг": "Rank",
  "Кредиты": "Credits",
  "Деньги": "Money",
  "Удалить": "Delete",
  "Да, удалить": "Yes, delete",
  "Нет": "No",
  "Отменить": "Cancel",
  "Создать": "Create",
  "Запустить": "Start",
  "Выполняю...": "Working...",
  "Готово": "Ready",
  "В работе": "In progress",
  "Осталось": "Left",
  "Свободно": "Free",
  "Неизвестная база": "Unknown base",
  "Неизвестный предмет": "Unknown item"
});



/* v92b: remaining static RU labels */
Object.assign(FLP_I18N.en, {
  "Нет данных.": "No data.",
  "Боеприпасов и расходников нет.": "No ammo or consumables.",
  "Батарей щита нет.": "No shield batteries.",
  "Нанороботов нет.": "No nanobots.",
  "Двигатели и форсаж не найдены.": "No engines or thrusters found.",
  "Прочее оборудование не найдено.": "No other equipment found.",
  "Сканеры отсутствуют.": "No scanners.",
  "Щитов и защитных модулей нет.": "No shields or defensive modules.",
  "Оружие не установлено.": "No weapons installed.",
  "Нет записей прыжковых дыр.": "No jump hole records.",
  "Нет посещённых систем.": "No visited systems.",
  "Нет посещённых планет.": "No visited planets.",
  "Нет посещённых станций и баз.": "No visited stations or bases.",
  "Системы": "Systems",
  "Планеты": "Planets",
  "Станции / базы": "Stations / bases",
  "Слот": "Slot",
  "Банк": "Bank",
  "Перс.": "Chars",
  "Переместить": "Move",
  "Запущено": "Started",
  "БД груза недоступна": "Cargo DB unavailable",
  "На личном складе нет предметов для выставления на контракт.": "There are no items in the personal warehouse to create a contract.",
  "На личном складе": "In personal warehouse",
  "нет предметов для выставления на контракт": "no items available to create a contract",
  "до": "until",
  "файл": "file",
  "Аккаунт": "Account",
  "Файл": "File"
});

const FLP_SUBSTRING_EN_V92 = [
  ["хэш предмета из строки склада", "item hash from warehouse row"],
  ["hash предмета из строки склада", "item hash from warehouse row"],
  ["предмета из строки склада", "from warehouse row"],
  ["Хэш / никнейм предмета", "Item hash / nickname"],
  ["Хэш предмета", "Item hash"],
  ["хэш", "hash"],
  ["никнейм", "nickname"],
  ["любой предмет", "any item"],
  ["Нет данных", "No data"],
  ["Боеприпасов и расходников нет", "No ammo or consumables"],
  ["Батарей щита нет", "No shield batteries"],
  ["Нанороботов нет", "No nanobots"],
  ["Двигатели и форсаж не найдены", "No engines or thrusters found"],
  ["Прочее оборудование не найдено", "No other equipment found"],
  ["Сканеры отсутствуют", "No scanners"],
  ["Щитов и защитных модулей нет", "No shields or defensive modules"],
  ["Оружие не установлено", "No weapons installed"],
  ["Нет записей прыжковых дыр", "No jump hole records"],
  ["Нет посещённых систем", "No visited systems"],
  ["Нет посещённых планет", "No visited planets"],
  ["Нет посещённых станций и баз", "No visited stations or bases"],
  ["Системы", "Systems"],
  ["Планеты", "Planets"],
  ["Станции / базы", "Stations / bases"],
  ["Слот", "Slot"],
  ["Банк", "Bank"],
  ["Перс.", "Chars"],
  ["Запущено", "Started"],
  ["БД груза недоступна", "Cargo DB unavailable"],
  ["На личном складе", "In personal warehouse"],
  ["нет предметов для выставления на контракт", "no items available to create a contract"],
  ["файл", "file"],
  ["до", "until"],
  ["Пилот сейчас", "Pilot now"],
  ["в космосе", "in space"],
  ["текущая база", "current base"],
  ["текущая", "current"],
  ["Админские операции со складом", "Admin warehouse operations"],
  ["Добавить item в склад", "Add item to warehouse"],
  ["Удалить item со склада", "Delete item from warehouse"],
  ["Переместить item", "Move item"],
  ["Склад / база", "Warehouse / base"],
  ["Пилот-получатель", "Target pilot"],
  ["Создать / добавить", "Create / add"],
  ["Открыть консоль FLHook", "Open FLHook console"],
  ["Имущество на всех базах / планетах", "Assets on all bases / planets"],
  ["Онлайн-пилоты FLHook", "FLHook online pilots"],
  ["Складов на базах/планетах пока нет", "No warehouses on bases/planets yet"],
  ["Ресурсы на складе", "Resources in warehouse"],
  ["Ваши склады", "Your warehouses"],
  ["Ваш склад", "Your warehouse"],
  ["База / планета", "Base / planet"],
  ["История операций склада", "Warehouse operation history"],
  ["Склад → трюм", "Warehouse → hold"],
  ["Трюм → склад", "Hold → warehouse"],
  ["Передано пилоту", "Sent to pilot"],
  ["Получено от пилота", "Received from pilot"],
  ["Кому:", "To:"],
  ["От:", "From:"],
  ["Выставить контракт", "Create contract"],
  ["Цена за весь контракт", "Full contract price"],
  ["Активные контракты сервера", "Server active contracts"],
  ["Мои контракты", "My contracts"],
  ["История контрактов", "Contract history"],
  ["Количество должно быть положительным целым числом", "Quantity must be a positive integer"],
  ["Предмет не найден в БД", "Item not found in DB"],
  ["Пилот-получатель не найден", "Receiver pilot not found"],
  ["Найдено несколько пилотов с таким никнеймом", "Multiple pilots with this nickname found"],
  ["Такого предмета нет", "This item is not available"],
  ["На складе только", "Only in warehouse"],
  ["На исходном складе только", "Only in source warehouse"],
  ["Нельзя передать", "Cannot transfer"],
  ["Нельзя переместить", "Cannot move"],
  ["Не удалось", "Could not"],
  ["Ошибка", "Error"],
  ["Сессия истекла", "Session expired"],
  ["Войдите заново", "Log in again"],
  ["добавлено", "added"],
  ["удалено", "deleted"],
  ["перемещено", "moved"],
  ["перенесено", "moved"],
  ["пилоту", "to pilot"],
  ["от", "from"],
  ["к", "to"],
  ["на склад", "to warehouse"],
  ["на базе", "at base"],
  ["личный склад", "personal warehouse"],
  ["шт.", "pcs."],
  ["строк", "rows"],
  ["объём", "volume"],
  ["Место", "Location"],
  ["Система", "System"],
  ["База", "Base"],
  ["Корабль", "Ship"],
  ["Ранг", "Rank"],
  ["Кредиты", "Credits"],
  ["Аккаунт", "Account"],
  ["Пилот", "Pilot"],
  ["Предмет", "Item"],
  ["Количество", "Quantity"],
  ["Кол-во", "Qty"],
  ["Объём", "Volume"],
  ["Тип", "Type"],
  ["Дата", "Date"],
  ["Операция", "Operation"],
  ["Примечание", "Note"],
  ["Удалить", "Delete"],
  ["Создать", "Create"],
  ["Отменить", "Cancel"],
  ["Готово", "Ready"],
  ["В работе", "In progress"],
  ["Неизвестный предмет", "Unknown item"],
  ["Неизвестная база", "Unknown base"]
];

function flpTranslateBySubstringsV92(text, lang) {
  if (lang !== 'en') return null;
  let value = String(text || '');
  if (!/[А-Яа-яЁё]/.test(value)) return null;

  let changed = false;
  for (const [ru, en] of FLP_SUBSTRING_EN_V92) {
    if (value.includes(ru)) {
      value = value.split(ru).join(en);
      changed = true;
    }
  }

  value = value
    .replace(/(\d+)\s*д\b/g, '$1d')
    .replace(/(\d+)\s*час(?:ов|а)?\b/gi, '$1 h')
    .replace(/(\d+)\s*дней\b/gi, '$1 days')
    .replace(/\s+·\s+/g, ' · ')
    .replace(/\s{2,}/g, ' ')
    .trim();

  return changed ? value : null;
}

function flpApplyI18nSoonV92(root = document) {
  if (flpGetLang() !== 'en') return;
  if (window.__flpI18nSoonTimer) cancelAnimationFrame(window.__flpI18nSoonTimer);
  window.__flpI18nSoonTimer = requestAnimationFrame(() => {
    window.__flpI18nSoonTimer = null;
    flpApplyI18n(root);
  });
}

function flpStartI18nObserverV92() {
  if (window.__flpI18nObserverV92) return;
  const observer = new MutationObserver((mutations) => {
    if (flpGetLang() !== 'en') return;
    for (const mutation of mutations) {
      if (mutation.type === 'childList' && mutation.addedNodes && mutation.addedNodes.length) {
        flpApplyI18nSoonV92(document);
        return;
      }
      if (mutation.type === 'attributes' || mutation.type === 'characterData') {
        flpApplyI18nSoonV92(document);
        return;
      }
    }
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['placeholder', 'title', 'aria-label']
  });
  window.__flpI18nObserverV92 = observer;
}

document.addEventListener('DOMContentLoaded', () => {
  flpStartI18nObserverV92();
  flpApplyI18n(document);
});


/* v97: admin item hash placeholder localization */
Object.assign(FLP_I18N.en, {
  "Админ может создать, удалить или переместить любой предмет в любом складе пилота. Предмет указывается как хэш, никнейм, good_nickname или equipment_nickname.": "Admin can create, delete, or move any item in any pilot warehouse. Item is specified as hash, nickname, good_nickname, or equipment_nickname.",
  "Хэш / никнейм предмета": "Item hash / nickname",
  "Хэш предмета": "Item hash",
  "commodity_water / хэш / никнейм": "commodity_water / item hash / nickname",
  "хэш предмета из строки склада": "item hash from warehouse row",
  "hash предмета из строки склада": "item hash from warehouse row",
  "hash предмета из строки столада": "item hash from warehouse row",
  "hash предмета из строки стоалада": "item hash from warehouse row",
  "хэш предмета из строки столада": "item hash from warehouse row",
  "хэш предмета из строки стоалада": "item hash from warehouse row",
  "Предмет указывается как хэш, никнейм, good_nickname или equipment_nickname.": "Item is specified as hash, nickname, good_nickname, or equipment_nickname.",
  "любой предмет": "any item"
});


/* v98: admin reputation translations */
Object.assign(FLP_I18N.en, {
  "Ручное изменение репутации": "Manual reputation edit",
  "Кнопки − и + меняют значение с шагом 0.05. После правки нажми «Изменить репутацию» — изменённые строки будут отправлены через FLHook.": "The − and + buttons change the value by 0.05. After editing, press “Change reputation” — changed rows will be sent through FLHook.",
  "Изменить репутацию": "Change reputation",
  "Команда выполняется через FLHook, затем вызывается savechar.": "The command is executed through FLHook, then savechar is called.",
  "Репутация не найдена в файле персонажа.": "No reputation rows found in the character file.",
  "Изменений репутации нет.": "No reputation changes.",
  "Репутация изменена": "Reputation changed"
});

function flpGetLang() {
  return localStorage.getItem('flp_lang') || 'ru';
}

function flpTranslateText(text, lang) {
  const original = String(text || '').trim();
  if (!original) return null;
  if (lang === 'ru') return original;
  const dictionary = FLP_I18N[lang] || {};
  const direct = dictionary[original] || flpTranslateDynamic(original, lang);
  if (direct) return direct;

  const substringTranslated = (typeof flpTranslateBySubstringsV92 === 'function') ? flpTranslateBySubstringsV92(original, lang) : null;
  if (substringTranslated) return substringTranslated;

  // v54 fallback for mixed game/UI strings, e.g. "PENNSYLVANIA · Planet Erie · ранг 1".
  if (lang === 'en' && /(^|\s|·)ранг\s*\d+/i.test(original)) {
    return original.replace(/ранг\s*(\d+)/gi, 'rank $1');
  }

  // v55 fallback for finance flash messages with amounts.
  if (lang === 'en' && /кредит/i.test(original)) {
    return original
      .replace(/кредитов/gi, 'credits')
      .replace(/перевод/gi, 'transfer')
      .replace(/пилоту/gi, 'to pilot')
      .replace(/выполнен/gi, 'completed')
      .replace(/переведено с персонажа в bank\.ini \(через файл\)/gi, 'transferred from character to bank.ini')
      .replace(/переведено из bank\.ini персонажу \(через файл\)/gi, 'transferred from bank.ini to character')
      .replace(/переведено другому пилоту/gi, 'transferred to another pilot')
      .replace(/списано/gi, 'deducted')
      .replace(/с персонажа/gi, 'from character')
      .replace(/режим:\s*файловый режим/gi, '')
      .replace(/зачислено/gi, 'credited');
  }

  if (lang === 'en' && /неизвестный предмет/i.test(original)) {
    return original === original.toUpperCase() ? 'UNKNOWN ITEM' : 'Unknown item';
  }


  // v63: translate craft recipe texts even if an older fallback already changed only the prefix.
  if (lang === 'en') {
    const recipePrefixMap = {
      'Плавка': 'Smelting',
      'Огранка': 'Cutting',
      'Переработка': 'Recycling',
      'Металлургия': 'Metallurgy',
      'Производство': 'Production',
      'Электрометаллургия': 'Electrometallurgy',
      'Корпусные панели': 'Hull panels',
      'Механика': 'Mechanics',
      'Электролиз': 'Electrolysis',
      'Изотопное разделение': 'Isotope separation',
      'Крекинг': 'Cracking',
      'Полимеризация': 'Polymerization',
      'Полимеры': 'Polymers',
      'Топливо': 'Fuel',
      'Тара': 'Containers',
      'Электроника': 'Electronics',
      'Фильтрация': 'Filtration',
      'Промышленность': 'Industry',
      'Инфраструктура': 'Infrastructure',
      'Агро': 'Agro',
      'Пища': 'Food',
      'Медицина': 'Medicine',
      'Товары': 'Goods',
      'Развлечения': 'Entertainment',
      'Вооружение': 'Weapons'
    };
    const recipePrefixMatch = original.match(/^([^:]+):\s*(.+)$/);
    if (recipePrefixMatch && recipePrefixMap[recipePrefixMatch[1]]) {
      return `${recipePrefixMap[recipePrefixMatch[1]]}: ${recipePrefixMatch[2]}`;
    }
  }

  if (lang === 'en' && /в bank\.ini/i.test(original)) {
    return original
      .replace(/\bв\s+bank\.ini\b/gi, 'to bank.ini')
      .replace(/\bиз\s+bank\.ini\b/gi, 'from bank.ini')
      .replace(/\bперсонажу\b/gi, 'character');
  }

  if (lang === 'en' && /^(Металлургия|Переработка|Плавка|Огранка|Топливо|Химия|Электроника|Электротехника|Боеприпасы|Фармацевтика|Сборка|Производство|Компоненты):/i.test(original)) {
    return original
      .replace(/^Металлургия:/i, 'Metallurgy:')
      .replace(/^Переработка:/i, 'Recycling:')
      .replace(/^Плавка:/i, 'Smelting:')
      .replace(/^Огранка:/i, 'Cutting:')
      .replace(/^Топливо:/i, 'Fuel:')
      .replace(/^Химия:/i, 'Chemistry:')
      .replace(/^Электроника:/i, 'Electronics:')
      .replace(/^Электротехника:/i, 'Electronics:')
      .replace(/^Боеприпасы:/i, 'Ammunition:')
      .replace(/^Фармацевтика:/i, 'Pharmaceuticals:')
      .replace(/^Сборка:/i, 'Assembly:')
      .replace(/^Производство:/i, 'Production:')
      .replace(/^Компоненты:/i, 'Components:');
  }

  if (lang === 'en' && /наноробот|штатного лимита|текущий запас персонажа/i.test(original)) {
    return original
      .replace(/нанороботов больше штатного лимита корабля/gi, 'Nanobots exceed ship limit')
      .replace(/принято как текущий запас персонажа/gi, 'accepted as current character stock');
  }

  if (lang === 'en' && /передано склад|корабль получателя не затрагивался/i.test(original)) {
    return original
      .replace(/передано склад/gi, 'Transferred warehouse')
      .replace(/склад:/gi, 'warehouse:')
      .replace(/шт\./gi, 'pcs.')
      .replace(/на личный склад пилота/gi, 'to personal warehouse of pilot')
      .replace(/на базе/gi, 'at base')
      .replace(/корабль получателя не затрагивался/gi, 'receiver ship was not touched');
  }

  return null;
}

function flpReplacePreserveWhitespace(node, replacement) {
  const current = node.nodeValue || '';
  const leading = current.match(/^\s*/)?.[0] || '';
  const trailing = current.match(/\s*$/)?.[0] || '';
  node.nodeValue = leading + replacement + trailing;
}

function flpOriginalAttrName(attr) {
  return `data-flp-i18n-original-${attr}`;
}

function flpRememberTextNode(node) {
  if (!FLP_TEXT_ORIGINALS.has(node)) {
    FLP_TEXT_ORIGINALS.set(node, node.nodeValue || '');
  }
  return FLP_TEXT_ORIGINALS.get(node) || '';
}

function flpApplyI18n(root = document) {
  const lang = flpGetLang();
  document.documentElement.lang = lang;

  document.querySelectorAll('[data-lang-set]').forEach((button) => {
    button.classList.toggle('active', button.dataset.langSet === lang);
  });

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      if (['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
      const text = (node.nodeValue || '').trim();
      if (!text) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });

  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);

  nodes.forEach((node) => {
    const original = flpRememberTextNode(node);
    const key = original.trim();
    if (!key) return;

    if (lang === 'ru') {
      flpReplacePreserveWhitespace(node, key);
      return;
    }

    const translated = flpTranslateText(key, lang);
    if (translated) {
      flpReplacePreserveWhitespace(node, translated);
    }
  });

  document.querySelectorAll('*').forEach((element) => {
    FLP_TRANSLATABLE_ATTRS.forEach((attr) => {
      const value = element.getAttribute(attr);
      if (!value) return;

      const storeAttr = flpOriginalAttrName(attr);
      if (!element.hasAttribute(storeAttr)) {
        element.setAttribute(storeAttr, value);
      }

      const original = element.getAttribute(storeAttr) || value;
      if (lang === 'ru') {
        element.setAttribute(attr, original);
        return;
      }

      const translated = flpTranslateText(original, lang);
      if (translated) element.setAttribute(attr, translated);
    });
  });
}

function flpSetLang(lang) {
  localStorage.setItem('flp_lang', lang || 'ru');
  flpApplyI18n(document);
  requestAnimationFrame(() => {
    if (typeof initCraftSubtabs === 'function') initCraftSubtabs();
    if (typeof initContractSubtabs === 'function') initContractSubtabs();
    if (typeof updateCraftTimers === 'function') updateCraftTimers();
  });
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-lang-set]');
  if (!button) return;

  event.preventDefault();
  flpSetLang(button.dataset.langSet || 'ru');
});

document.addEventListener('DOMContentLoaded', () => flpApplyI18n(document));


/* v51: inner tabs for Craft section */
function initCraftSubtabs(preferredTab = '') {
  const root = document.querySelector('#craft-content');
  if (!root) return;

  const buttons = root.querySelectorAll('.craft-subtab');
  const panels = root.querySelectorAll('.craft-subpanel');
  if (!buttons.length || !panels.length) return;

  let saved = preferredTab || localStorage.getItem('flp_craft_subtab') || root.querySelector('.craft-subtab.active')?.dataset?.craftTab || 'recipes';
  if (!root.querySelector(`[data-craft-panel="${saved}"]`)) saved = 'recipes';

  function activate(target) {
    buttons.forEach((item) => item.classList.toggle('active', item.dataset.craftTab === target));
    panels.forEach((panel) => panel.classList.toggle('active', panel.dataset.craftPanel === target));
    localStorage.setItem('flp_craft_subtab', target);
    requestAnimationFrame(updateCraftTimers);
  }

  buttons.forEach((button) => {
    if (button.dataset.craftReady === '1') return;
    button.dataset.craftReady = '1';

    button.addEventListener('click', () => {
      activate(button.dataset.craftTab || 'recipes');
    });
  });

  activate(saved);
}

document.addEventListener('DOMContentLoaded', initCraftSubtabs);
document.addEventListener('click', () => requestAnimationFrame(initCraftSubtabs));




/* v67: cargo-only FLHook transfer translations */
Object.assign(FLP_I18N.en, {
  "В трюм через панель пока можно переносить только обычный груз / commodity с объёмом больше 0. Эквипмент и снаряжение пока не трогаем.": "Only regular cargo / commodity with volume greater than 0 can be moved to hold through the panel. Equipment is not handled yet.",
  "В трюм через панель пока можно переносить только обычный груз / commodity с объёмом больше 0.": "Only regular cargo / commodity with volume greater than 0 can be moved to hold through the panel."
});


/* v68: background refresh for finance, hold and warehouse */
function flpApplyLivePayload(payload) {
  if (!payload || payload.ok === false && !payload.hold_html && !payload.warehouse_html) return;

  // v86:
  // /api/live must update data only. It must not throw the user back to default
  // main tab/subtab every 12 seconds.
  const activeTabsBeforeLive = flpCaptureActiveTabs();

  if (Object.prototype.hasOwnProperty.call(payload, 'character_money_formatted')) {
    setBalance('#character-money', payload.character_money, payload.character_money_formatted);
  }
  if (Object.prototype.hasOwnProperty.call(payload, 'bank_formatted')) {
    setBalance('#bank-money', payload.bank, payload.bank_formatted);
  }

  if (payload.finance_history_html) {
    const history = document.querySelector('#finance-history');
    if (history) history.outerHTML = payload.finance_history_html;
  }

  if (payload.hold_html) {
    const hold = document.querySelector('#hold-live-content');
    if (hold) hold.innerHTML = payload.hold_html;
  }

  if (payload.warehouse_html) {
    const itemModalOpen = document.querySelector('#warehouse-modal:not([hidden])');
    const locationModalOpen = document.querySelector('#warehouse-location-modal:not([hidden])');
    const warehouse = document.querySelector('#warehouse-live-content');

    // v81:
    // Do not replace #warehouse-live-content while any warehouse modal is open.
    // The "Ваши склады" resource-list modal lives inside that HTML, so live
    // refresh used to delete it every 12 seconds and the modal closed by itself.
    if (warehouse && !itemModalOpen && !locationModalOpen) {
      const activeWarehouseTab = activeTabsBeforeLive.warehouse || 'stock';
      document.querySelectorAll('body > #warehouse-modal').forEach((modal) => modal.remove());
      warehouse.innerHTML = payload.warehouse_html;
      initWarehouseSubtabs(activeWarehouseTab);
      if (typeof flpApplyI18n === 'function') flpApplyI18n(warehouse);
    }
  }

  if (payload.contracts_html) {
    const contracts = document.querySelector('#contracts');
    if (contracts) {
      const activeContractTab = activeTabsBeforeLive.contracts || 'server';
      contracts.innerHTML = payload.contracts_html;
      if (typeof initContractSubtabs === 'function') initContractSubtabs(activeContractTab);
      if (typeof flpApplyI18n === 'function') flpApplyI18n(contracts);
    }
  }

  flpRestoreActiveTabs(activeTabsBeforeLive);

  if (typeof flpApplyI18n === 'function') {
    flpApplyI18n(document.querySelector('.wrap') || document);
  }
}

let flpLiveRefreshInFlight = false;

async function flpRefreshLivePanels({silent = true} = {}) {
  if (!document.querySelector('#hold-live-content') && !document.querySelector('#finance')) return;
  if (document.hidden) return;
  if (flpLiveRefreshInFlight) return;

  flpLiveRefreshInFlight = true;

  try {
    const response = await fetch('/api/live', {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
    });

    if (!response.ok) return;
    const payload = await response.json();
    flpApplyLivePayload(payload);
  } catch (error) {
    if (!silent) console.error('live refresh failed:', error);
  } finally {
    flpLiveRefreshInFlight = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.querySelector('#hold-live-content') || document.querySelector('#finance')) {
    // v84: refresh once immediately, then every 12 seconds.
    // This makes the hold update from FLHook right after login/reload.
    flpRefreshLivePanels({silent: true});
    window.setInterval(() => flpRefreshLivePanels({silent: true}), 12000);
  }
});

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) flpRefreshLivePanels({silent: true});
});


document.addEventListener('beforeinput', (event) => {
  const input = event.target.closest && event.target.closest('input[data-numeric-only="1"], input[inputmode="numeric"][name="amount"], input[inputmode="numeric"][name="quantity"], input[inputmode="numeric"][name="quantity"]');
  if (!input) return;

  if (event.inputType && event.inputType.startsWith('delete')) return;
  if (event.inputType === 'insertText' && event.data && /\D/.test(event.data)) {
    event.preventDefault();
    showWarehouseNotice('Количество: только цифры, без пробелов и спецсимволов.', false);
  }
});

document.addEventListener('paste', (event) => {
  const input = event.target.closest && event.target.closest('input[data-numeric-only="1"], input[inputmode="numeric"][name="amount"], input[inputmode="numeric"][name="quantity"], input[inputmode="numeric"][name="quantity"]');
  if (!input) return;

  event.preventDefault();
  const pasted = (event.clipboardData || window.clipboardData).getData('text') || '';
  const cleaned = normalizeDigitsOnly(pasted);
  input.value = cleaned;
  validateWarehouseAmountInput(input, {showNotice: pasted !== cleaned});
});

document.addEventListener('input', (event) => {
  const input = event.target.closest && event.target.closest('input[data-numeric-only="1"], input[inputmode="numeric"][name="amount"], input[inputmode="numeric"][name="quantity"], input[inputmode="numeric"][name="quantity"]');
  if (!input) return;

  validateWarehouseAmountInput(input, {showNotice: false});
});

document.addEventListener('blur', (event) => {
  const input = event.target.closest && event.target.closest('input[data-numeric-only="1"], input[inputmode="numeric"][name="amount"], input[inputmode="numeric"][name="quantity"], input[inputmode="numeric"][name="quantity"]');
  if (!input) return;

  validateWarehouseAmountInput(input, {showNotice: true});
}, true);


document.addEventListener('submit', async (event) => {
  const form = event.target.closest('form[data-ajax-warehouse="true"]');
  if (!form) return;

  event.preventDefault();
  event.stopPropagation();

  if (form.dataset.loading === '1') return;
  form.dataset.loading = '1';

  const button = form.querySelector('button[type="submit"], button:not([type])');
  const originalText = button ? button.textContent : '';

  if (button) {
    button.disabled = true;
    button.textContent = 'Выполняю...';
  }

  try {
    const actionUrl = form.getAttribute('action') || window.location.href;
    const body = buildFinanceBody(form);

    const response = await fetch(actionUrl, {
      method: 'POST',
      body,
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
    });

    const payload = await response.json();
    setFinanceMessage(payload.message || 'Операция завершена.', payload.ok && response.ok);
    flpApplyLivePayload(payload);

    if (response.ok && payload.ok) {
      closeWarehouseModal();
    }

    if (payload.refresh_later) {
      window.setTimeout(() => flpRefreshLivePanels({silent: true}), 80);
    }
  } catch (error) {
    console.error('Warehouse AJAX failed:', error);
    setFinanceMessage('Операция склада не выполнена: сервер вернул неожиданный ответ.', false);
  } finally {
    form.dataset.loading = '0';
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
});



/* v68: live operation translations */
Object.assign(FLP_I18N.en, {
  "Перенести груз из трюма корабля на склад базы": "Move cargo from ship hold to base warehouse",
  "Операция склада не выполнена: сервер вернул неожиданный ответ.": "Warehouse operation failed: unexpected server response.",
  "Выполняю...": "Working..."
});


/* v69: pilot transfer warehouse-only translations */
Object.assign(FLP_I18N.en, {
  "В склад пилота": "To pilot warehouse",
  "Передать в склад": "Send to warehouse",
  "Передача другому пилоту: только склад → склад. Корабль, .fl-файл и FLHook не используются.": "Transfer to another pilot: warehouse → warehouse only. Ship, .fl file and FLHook are not used.",
  "Передано склад → склад:": "Warehouse → warehouse transfer completed:",
  ".fl-файл и корабль получателя не затрагивались.": "Receiver .fl file and ship were not touched."
});


/* v70: new per-character auth code login translations */
Object.assign(FLP_I18N.en, {
  "Введите имя персонажа или ID аккаунта. Код доступа создаётся в игре командой /set mivecharcode или /set cashcode.": "Enter a character name or account ID. Access code is created in-game with /set mivecharcode or /set cashcode.",
  "Код доступа": "Access code",
  "код из /set mivecharcode или /set cashcode": "code from /set mivecharcode or /set cashcode",
  "Имя пилота, ID аккаунта или имя .fl-файла": "Pilot name, account ID, or .fl filename",
  "необязательно, если в аккаунте несколько пилотов": "optional if the account has several pilots",
  "Логин или код не совпали. Сначала в игре сделай /set mivecharcode или /set cashcode для нужного пилота.": "Login or code did not match. First run /set mivecharcode or /set cashcode in-game for the required pilot."
});


/* v71: pilot-name-only login translations */
Object.assign(FLP_I18N.en, {
  "Вход только по имени пилота и коду доступа. Код создаётся в игре командой /set cashcode.": "Login only by pilot name and access code. The code is created in-game with /set cashcode.",
  "Имя пилота": "Pilot name",
  "точное имя пилота в игре": "exact in-game pilot name",
  "код из *-givecash.ini": "code from *-givecash.ini",
  "Имя пилота или код не совпали. Вход только по имени пилота и коду из *-givecash.ini.": "Pilot name or code did not match. Login is only by pilot name and code from *-givecash.ini."
});


/* v74: fast warehouse-to-warehouse transfer translations */
Object.assign(FLP_I18N.en, {
  "warehouse_transfer": "warehouse transfer"
});


/* v75: client disconnect safe live refresh
   Prevents overlapping /api/live fetches while previous request is still running. */


/* v78: warehouse amount validation translations */
Object.assign(FLP_I18N.en, {
  "Количество: только цифры, без пробелов и спецсимволов.": "Quantity: digits only, no spaces or special characters.",
  "Укажи количество больше нуля.": "Enter quantity greater than zero.",
  "Нельзя передать": "Cannot transfer",
  "На складе только": "Only in warehouse"
});


/* v79: warehouse history translations */
Object.assign(FLP_I18N.en, {
  "Склад": "Warehouse",
  "История": "History",
  "История операций склада": "Warehouse operation history",
  "История хранится отдельно для каждого пилота и текущей базы: склад → склад, склад ↔ трюм, удаления и пополнения склада.": "History is stored separately for each pilot and current base: warehouse → warehouse, warehouse ↔ hold, removals and additions.",
  "Истории операций склада на этой базе пока нет.": "There is no warehouse operation history on this base yet.",
  "Добавлено в склад": "Added to warehouse",
  "Удалено со склада": "Removed from warehouse",
  "Склад → трюм": "Warehouse → hold",
  "Трюм → склад": "Hold → warehouse",
  "Передано пилоту": "Sent to pilot",
  "Получено от пилота": "Received from pilot",
  "Предмет": "Item",
  "Кол-во": "Qty",
  "База": "Base",
  "Примечание": "Note"
});


/* v80: warehouse all locations translations */
Object.assign(FLP_I18N.en, {
  "Ваши склады": "Your warehouses",
  "Здесь показаны все базы и планеты, где у текущего пилота есть складские ресурсы. Нажми на базу, затем на ресурс для операций.": "This shows all bases and planets where the current pilot has warehouse resources. Click a base, then click a resource for operations.",
  "У этого пилота пока нет складов на других базах или планетах.": "This pilot has no warehouses on other bases or planets yet.",
  "Ваш склад": "Your warehouse",
  "База / планета": "Base / planet",
  "Тип": "Type",
  "Строк": "Rows",
  "Объём": "Volume",
  "Пилот": "Pilot",
  "Кому:": "To:",
  "От:": "From:",
  "Перенос в трюм доступен только на текущей базе пилота.": "Moving to hold is available only at the pilot's current base."
});


/* v81: keep warehouse location modal open during live refresh */
Object.assign(FLP_I18N.en, {
  "Ваши склады": "Your warehouses"
});


/* v83: givecash-only auth translations */
Object.assign(FLP_I18N.en, {
  "Вход только по имени пилота и коду доступа. Код создаётся в игре командой /set cashcode.": "Login only by pilot name and access code. The code is created in-game with /set cashcode.",
  "код из *-givecash.ini": "code from *-givecash.ini",
  "Имя пилота или код не совпали. Проверь: код должен быть создан после /set cashcode, а панель читает только *-givecash.ini.": "Pilot name or code did not match. Check that the code was created after /set cashcode; the panel reads only *-givecash.ini."
});


/* v84: live hold source from FLHook */
Object.assign(FLP_I18N.en, {
  "Трюм корабля": "Ship hold"
});


/* v85: warehouse contract modal translations */
Object.assign(FLP_I18N.en, {
  "Выставить контракт": "Create contract",
  "Создать контракт прямо из выбранного склада. Товар сразу будет снят со склада и зарезервирован в контракте.": "Create a contract directly from the selected warehouse. The item will be removed from the warehouse and reserved in the contract immediately.",
  "Цена за весь контракт": "Full contract price",
  "Срок": "Lifetime",
  "часов": "hours",
  "дней": "days",
  "Контракт создан": "Contract created",
  "Создано из склада базы.": "Created from base warehouse.",
  "Товар снят со склада и зарезервирован.": "The item was removed from the warehouse and reserved.",
  "Ваш склад": "Your warehouse",
  "Ресурсы на складе": "Resources in warehouse",
  "Склад": "Warehouse",
  "На складе": "In warehouse",
  "Предмет": "Item",
  "Кол-во": "Qty",
  "Объём 1": "Volume 1",
  "База / планета": "Base / planet",
  "Текущая база / планета для выставления": "Current base / planet for listing",
  "Выставить предмет со склада на продажу": "List warehouse item for sale",
  "При выставлении товар сразу снимается со склада и резервируется в контракте. Если срок истечёт — товар вернётся на склад продавца.": "When listed, the item is immediately removed from the warehouse and reserved in the contract. If it expires, the item returns to the seller warehouse."
});


/* v86: preserve active tabs during live refresh */
Object.assign(FLP_I18N.en, {
  "Фоновое обновление не сбрасывает активные вкладки.": "Background refresh does not reset active tabs."
});


/* v87: admin translations */
Object.assign(FLP_I18N.en, {
  "Админская зона": "Admin zone",
  "Онлайн-пилоты FLHook": "FLHook online pilots",
  "FLHook console": "FLHook console",
  "Аккаунты": "Accounts",
  "Выполнить": "Run",
  "Пилот": "Pilot",
  "Система": "System",
  "Корабль": "Ship",
  "Ранг": "Rank",
  "Кредиты": "Credits",
  "Аккаунт": "Account",
  "Имущество на всех базах / планетах": "Assets on all bases / planets",
  "Снаряжение корабля": "Ship equipment",
  "Трюм корабля": "Ship hold"
});


/* v88: admin scroll translations */
Object.assign(FLP_I18N.en, {
  "Прокрутка админки исправлена.": "Admin scrolling fixed."
});


/* v89: admin modal FLHook console and admin warehouse location selects */
function syncAdminLocationSelect(select) {
  if (!select || !select.form) return;
  const option = select.selectedOptions && select.selectedOptions[0] ? select.selectedOptions[0] : null;
  const prefix = select.name.startsWith('source_') ? 'source_' : select.name.startsWith('target_') ? 'target_' : '';
  const nameInput = select.form.querySelector(`input[name="${prefix}location_name"]`);
  const typeInput = select.form.querySelector(`input[name="${prefix}location_type"]`);

  if (nameInput) {
    nameInput.value = option?.dataset?.locationName || option?.textContent?.replace(/— текущая база/g, '').trim() || select.value || '';
  }
  if (typeInput) {
    typeInput.value = option?.dataset?.locationType || 'base';
  }
}

function openAdminFlhookModal() {
  const modal = document.querySelector('#admin-flhook-modal');
  if (modal) {
    if (typeof flpApplyI18n === 'function') flpApplyI18n(modal);
    modal.hidden = false;
  }
}

function closeAdminFlhookModal() {
  const modal = document.querySelector('#admin-flhook-modal');
  if (modal) modal.hidden = true;
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('select[data-location-select]').forEach(syncAdminLocationSelect);
});

document.addEventListener('change', (event) => {
  const select = event.target.closest && event.target.closest('select[data-location-select]');
  if (select) syncAdminLocationSelect(select);
});

document.addEventListener('submit', (event) => {
  const form = event.target.closest && event.target.closest('form.admin-action-form');
  if (!form) return;
  form.querySelectorAll('select[data-location-select]').forEach(syncAdminLocationSelect);
});

document.addEventListener('click', (event) => {
  if (event.target.closest('[data-admin-console-open]')) {
    event.preventDefault();
    openAdminFlhookModal();
    return;
  }

  if (event.target.closest('[data-admin-console-close]')) {
    event.preventDefault();
    closeAdminFlhookModal();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeAdminFlhookModal();
  }
});


/* v89: admin rights translations */
Object.assign(FLP_I18N.en, {
  "Админские операции со складом": "Admin warehouse operations",
  "Добавить item в склад": "Add item to warehouse",
  "Удалить item со склада": "Delete item from warehouse",
  "Переместить item": "Move item",
  "Создать / добавить": "Create / add",
  "Открыть консоль FLHook": "Open FLHook console",
  "Пилот сейчас": "Pilot location now",
  "Склад / база": "Warehouse / base",
  "Откуда": "From",
  "Куда": "To",
  "Пилот-получатель": "Target pilot"
});


/* v90: admin space location translations */
Object.assign(FLP_I18N.en, {
  "в космосе": "in space",
  "Место": "Location",
  "Пилот сейчас": "Pilot now"
});


/* v91: flhook console visible translations */
Object.assign(FLP_I18N.en, {
  "Открыть консоль FLHook": "Open FLHook console"
});


/* v93: inline flhook button translations */
Object.assign(FLP_I18N.en, {
  "JSON API": "JSON API",
  "FLHook console": "FLHook console"
});


/* v94: live admin location translations */
Object.assign(FLP_I18N.en, {
  "Источник местоположения": "Location source",
  "Пилот сейчас": "Pilot now",
  "в космосе": "in space",
  "FLHook online": "FLHook online",
  "FLHook getplayers": "FLHook getplayers",
  "file": "file"
});


/* v95: flhook button height translations */
Object.assign(FLP_I18N.en, {
  "Кнопка FLHook console приведена к общей высоте.": "FLHook console button height aligned."
});


/* v96: system token cleanup translations */
Object.assign(FLP_I18N.en, {
  "Системные имена очищены из UI.": "System tokens cleaned from UI."
});


/* v97: item hash placeholder marker */
Object.assign(FLP_I18N.en, {
  "Плейсхолдеры item hash переведены.": "Item hash placeholders translated."
});


/* v98: admin manual reputation editor */
function flpClampRep(value) {
  const parsed = parseFloat(String(value || '0').replace(',', '.'));
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(-1, Math.min(1, parsed));
}

function flpFormatRep(value) {
  const clamped = flpClampRep(value);
  const text = clamped.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  return (text === '-0' || text === '+0' || text === '') ? '0' : text;
}

function flpUpdateRepRow(row) {
  if (!row) return;
  const input = row.querySelector('.admin-rep-input');
  if (!input) return;

  const value = flpClampRep(input.value);
  input.value = flpFormatRep(value);
  row.classList.toggle('changed', flpFormatRep(value) !== flpFormatRep(input.dataset.originalRep || '0'));

  const bar = row.querySelector('.rep-bar-inline');
  if (!bar) return;

  bar.querySelectorAll('.rep-fill-positive, .rep-fill-negative').forEach((node) => node.remove());

  const width = Math.min(50, Math.abs(value) * 50);
  if (width <= 0) return;

  const fill = document.createElement('span');
  fill.className = value > 0 ? 'rep-fill-positive' : 'rep-fill-negative';
  fill.style.position = 'absolute';
  fill.style.top = '2px';
  fill.style.height = 'calc(100% - 4px)';
  fill.style.width = `${width}%`;
  fill.style.zIndex = '2';

  if (value > 0) {
    fill.style.left = '50%';
    fill.style.background = 'linear-gradient(90deg,rgba(245,245,245,.78),rgba(75,220,110,.96))';
    fill.style.boxShadow = '0 0 8px rgba(75,220,110,.45)';
  } else {
    fill.style.right = '50%';
    fill.style.background = 'linear-gradient(90deg,rgba(220,55,55,.96),rgba(245,245,245,.78))';
    fill.style.boxShadow = '0 0 8px rgba(220,55,55,.45)';
  }

  bar.prepend(fill);
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-rep-delta]');
  if (!button) return;

  event.preventDefault();
  const row = button.closest('[data-admin-rep-row]');
  const input = row?.querySelector('.admin-rep-input');
  if (!input) return;

  const delta = parseFloat(button.dataset.repDelta || '0');
  input.value = flpFormatRep(flpClampRep(input.value) + delta);
  flpUpdateRepRow(row);
});

document.addEventListener('input', (event) => {
  const input = event.target.closest('.admin-rep-input');
  if (!input) return;
  flpUpdateRepRow(input.closest('[data-admin-rep-row]'));
});

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-admin-rep-row]').forEach(flpUpdateRepRow);
});
