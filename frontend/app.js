import { api } from './api.js';
import { ageLabel } from './lifecycle.js';
import { initializeQuickCapture } from './quick-capture.js';

const GOAL = 80;
const STAGES = {
  creation: { title: 'Reprodução', description: 'Cruzas e previsões de nascimento.', overline: 'ETAPA 1 DE 4', add: 'Nova cruza' },
  foals: { title: 'Potros e Desenvolvimento', description: 'Animais em fase de crescimento.', overline: 'ETAPA 2 DE 4', add: 'Novo potro' },
  training: { title: 'Preparação e Treinamento', description: 'Controle dos treinos.', overline: 'ETAPA 3 DE 4', add: 'Novo cavalo' },
  ready: { title: 'Tropa pronta', description: 'Cavalos preparados para torneios.', overline: 'ETAPA 4 DE 4', add: 'Novo integrante' },
};
const COST_CATEGORIES = {
  food: 'Alimentação', veterinary: 'Veterinário', farrier: 'Ferrageamento', training: 'Treinamento',
  transport: 'Transporte', medicine: 'Medicamentos', fees: 'Taxas', other: 'Outros',
};
const ASSISTANT_LABELS = {
  clarification: 'CONFIRMAÇÃO', parentage: 'FILIAÇÃO', births: 'NASCIMENTOS',
  workouts: 'TREINOS', age: 'IDADE', count: 'QUANTIDADE', location: 'LOCALIZAÇÃO',
  stage: 'ETAPAS', details: 'CADASTRO', costs: 'CUSTOS E ANÁLISES', audit: 'AUDITORIA DOS DADOS', help: 'EXEMPLOS', empty: 'SEM REGISTROS',
};
const $ = selector => document.querySelector(selector);
const state = { horses: [], expenses: [], stage: null, costs: false, costMonth: '', editing: null, editingExpense: null, costImportPreview: [], assistantContext: {}, pending: null, pendingCancel: null, setupRequired: false, authMode: 'login', accountEmail: '', accountInfo: null };
let installPrompt = null;
const APPEARANCE_KEY = 'radames_appearance_v1';
const FONT_OPTIONS = new Set(['professional', 'classic', 'modern']);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const uiIcon = (name, extra = '') => '<svg class="ui-icon' + (extra ? ' ' + extra : '') + '" aria-hidden="true"><use href="#ui-icon-' + name + '"></use></svg>';

function readAppearance() {
  try {
    const stored = JSON.parse(localStorage.getItem(APPEARANCE_KEY) || '{}');
    const legacySizes = { small: 90, standard: 100, large: 115 };
    const requestedSize = legacySizes[stored.size] || Number(stored.size);
    return {
      font: FONT_OPTIONS.has(stored.font) ? stored.font : 'professional',
      size: Number.isFinite(requestedSize) ? Math.min(160, Math.max(85, requestedSize)) : 100,
    };
  } catch {
    return { font: 'professional', size: 100 };
  }
}

function applyAppearance(preference, save = false) {
  const font = FONT_OPTIONS.has(preference.font) ? preference.font : 'professional';
  const requestedSize = Number(preference.size);
  const size = Number.isFinite(requestedSize) ? Math.min(160, Math.max(85, requestedSize)) : 100;
  document.documentElement.dataset.font = font;
  document.documentElement.dataset.fontSize = String(size);
  document.documentElement.classList.toggle('font-size-expanded', size >= 130);
  document.documentElement.style.setProperty('--font-scale', String(size / 100));
  if ($('#fontPreference')) $('#fontPreference').value = font;
  if ($('#fontSizePreference')) $('#fontSizePreference').value = String(size);
  if ($('#fontSizeValue')) $('#fontSizeValue').value = size + '%';
  if (save) {
    try { localStorage.setItem(APPEARANCE_KEY, JSON.stringify({ font, size })); } catch { /* Navegador sem armazenamento local. */ }
  }
}

applyAppearance(readAppearance());

function formatDate(value, fallback = 'Não informada') {
  if (!value) return fallback;
  return new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC' }).format(new Date(value + 'T12:00:00Z'));
}

function toast(message, error = false) {
  const item = document.createElement('div');
  item.className = 'toast' + (error ? ' is-error' : '');
  item.textContent = message;
  $('#toasts').append(item);
  setTimeout(() => item.remove(), 3600);
}

function assistantMessage(text, user = false, error = false, options = [], intent = '', actions = []) {
  const item = document.createElement('div');
  item.className = 'assistant-message assistant-message--' + (user ? 'user' : 'bot') + (error ? ' is-error' : '');
  if (user) {
    const label = document.createElement('small');
    label.className = 'assistant-message__label';
    label.textContent = 'SUA PERGUNTA';
    item.append(label);
  } else if (ASSISTANT_LABELS[intent]) {
    const label = document.createElement('small');
    label.className = 'assistant-message__label';
    label.innerHTML = uiIcon('assistant') + escapeHtml(ASSISTANT_LABELS[intent]);
    item.append(label);
  }
  const copy = document.createElement('span');
  copy.className = 'assistant-message__text';
  copy.textContent = text;
  item.append(copy);
  if (!user && options.length) {
    const choices = document.createElement('div');
    choices.className = 'assistant-message__options';
    options.forEach(option => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = option.label;
      button.addEventListener('click', () => askAssistant(option.question));
      choices.append(button);
    });
    item.append(choices);
  }
  if (!user && actions.length) {
    const tools = document.createElement('div');
    tools.className = 'assistant-message__actions';
    actions.forEach(action => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = action.label;
      button.addEventListener('click', async () => {
        button.disabled = true;
        const original = button.textContent;
        button.textContent = 'Gerando…';
        try {
          const file = await api.downloadFinancialReport(action.format, action.period);
          const url = URL.createObjectURL(file.blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = file.filename;
          document.body.append(link);
          link.click();
          link.remove();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
          toast('Relatório gerado com sucesso.');
        } catch (downloadError) {
          toast(downloadError.message, true);
        } finally {
          button.disabled = false;
          button.textContent = original;
        }
      });
      tools.append(button);
    });
    item.append(tools);
  }
  $('#assistantMessages').append(item);
  item.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

async function askAssistant(question) {
  const text = String(question || '').trim();
  if (!text) return;
  assistantMessage(text, true);
  $('#assistantQuestion').value = '';
  const button = $('#assistantSend');
  button.disabled = true;
  button.textContent = 'Consultando…';
  try {
    const result = await api.askAssistant(text, state.assistantContext);
    state.assistantContext = result.context || {};
    assistantMessage(result.answer, false, false, result.options || [], result.intent || '', result.actions || []);
  } catch (error) {
    assistantMessage(error.message, false, true);
  } finally {
    button.disabled = false;
    button.textContent = 'Enviar';
    $('#assistantQuestion').focus();
  }
}

function showAuth(session) {
  state.setupRequired = session.setupRequired;
  state.accountEmail = session.email || '';
  state.authMode = session.setupRequired ? 'signup' : 'login';
  $('#app').hidden = true;
  $('#auth').hidden = false;
  $('#authEmail').value = state.accountEmail;
  $('#authPassword').value = '';
  $('#authFirstName').value = '';
  $('#authLastName').value = '';
  $('#authError').textContent = '';
  renderAuthMode();
}

function renderAuthMode() {
  const signup = state.authMode === 'signup';
  $('#authTitle').textContent = signup ? 'Criar conta' : 'Bem-vindo de volta';
  $('#authCopy').textContent = signup ? 'Cadastre o e-mail e a senha de quem vai acessar a cocheira.' : 'Entre para acompanhar a cocheira.';
  $('#authButton').textContent = signup ? 'Criar conta' : 'Entrar';
  $('#authSwitch').textContent = signup ? 'Já tem conta? Entrar' : 'Não tem conta? Criar conta';
  $('#authNote').textContent = signup ? 'Sua conta ficará conectada neste aparelho por até 90 dias.' : 'Você continuará conectado neste aparelho.';
  $('#authPassword').autocomplete = signup ? 'new-password' : 'current-password';
  $('#authFirstNameField').hidden = !signup;
  $('#authLastNameField').hidden = !signup;
  $('#authFirstName').required = signup;
  $('#authLastName').required = signup;
}

async function showApp(initial = null) {
  const bootstrap = initial || await api.bootstrap();
  if (!bootstrap.session?.authenticated) {
    showAuth(bootstrap.session || { setupRequired: false, authenticated: false, email: null });
    return;
  }
  $('#auth').hidden = true;
  $('#app').hidden = false;
  state.stage = null;
  state.costs = false;
  state.query = '';
  $('#search').value = '';
  state.accountEmail = bootstrap.session.email || '';
  state.horses = Array.isArray(bootstrap.horses) ? bootstrap.horses : [];
  state.expenses = Array.isArray(bootstrap.expenses) ? bootstrap.expenses : [];
  render();
  renderCosts();
}

async function loadHorses() {
  try {
    state.horses = await api.horses();
    render();
  } catch (error) {
    if (error.status === 401) showAuth(await api.session());
    else toast(error.message, true);
  }
}

async function loadExpenses() {
  try {
    state.expenses = await api.expenses();
    renderCosts();
  } catch (error) {
    if (error.status === 401) showAuth(await api.session());
    else toast(error.message, true);
  }
}

const money = cents => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format((Number(cents) || 0) / 100);

function localIsoDate(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function monthOffset(month, delta) {
  const [year, value] = month.split('-').map(Number);
  const date = new Date(year, value - 1 + delta, 1);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function renderCosts() {
  if (!state.costMonth) state.costMonth = localIsoDate().slice(0, 7);
  $('#costMonth').value = state.costMonth;
  const expensesForMonth = month => state.expenses.flatMap(expense => {
    const sourceMonth = String(expense.date || '').slice(0, 7);
    if (sourceMonth === month) return [expense];
    if (!expense.recurring || !sourceMonth || sourceMonth > month) return [];
    const [year, monthNumber] = month.split('-').map(Number);
    const maximumDay = new Date(year, monthNumber, 0).getDate();
    const day = Math.min(maximumDay, Math.max(1, Number(expense.recurrenceDay) || Number(String(expense.date).slice(8, 10)) || 1));
    return [{ ...expense, date: `${month}-${String(day).padStart(2, '0')}`, recurringProjection: true }];
  });
  const current = expensesForMonth(state.costMonth);
  const previousMonth = monthOffset(state.costMonth, -1);
  const previous = expensesForMonth(previousMonth);
  const total = current.reduce((sum, expense) => sum + Number(expense.amountCents || 0), 0);
  const previousTotal = previous.reduce((sum, expense) => sum + Number(expense.amountCents || 0), 0);
  const horseCount = state.horses.filter(horse => ['foals', 'training', 'ready'].includes(horse.stage)).length;
  $('#costTotal').textContent = money(total);
  $('#costPerHorse').textContent = money(horseCount ? Math.round(total / horseCount) : 0);
  $('#costHorseCount').textContent = `${horseCount} ${horseCount === 1 ? 'cavalo considerado' : 'cavalos considerados'}`;
  if (!previousTotal) $('#costComparison').textContent = total ? 'Primeiro período com lançamentos' : 'Sem comparação anterior';
  else {
    const change = Math.round(((total - previousTotal) / previousTotal) * 100);
    $('#costComparison').textContent = `${change > 0 ? '+' : ''}${change}% em relação ao mês anterior`;
  }
  const categoryTotals = Object.fromEntries(Object.keys(COST_CATEGORIES).map(key => [key, 0]));
  current.forEach(expense => { categoryTotals[expense.category] = (categoryTotals[expense.category] || 0) + Number(expense.amountCents || 0); });
  $('#costEntriesCount').textContent = `${current.length} ${current.length === 1 ? 'lançamento' : 'lançamentos'}`;
  renderCategoryChart(categoryTotals, total);
  renderExpenseList(current);
}

function renderCategoryChart(totals, total) {
  const entries = Object.entries(totals).filter(([, value]) => value > 0).sort((a, b) => b[1] - a[1]);
  $('#costCategoryChart').innerHTML = entries.length ? entries.map(([key, value]) => {
    const percent = total ? Math.round((value / total) * 100) : 0;
    return '<div class="category-row"><strong>' + escapeHtml(COST_CATEGORIES[key]) + '</strong><div class="category-track"><i style="width:' + percent + '%"></i></div><span>' + escapeHtml(money(value)) + '</span></div>';
  }).join('') : '<div class="cost-empty">Adicione uma despesa para visualizar a distribuição por categoria.</div>';
}

function renderExpenseList(expenses) {
  const sorted = expenses.slice().sort((a, b) => String(b.date).localeCompare(String(a.date)) || String(b.createdAt).localeCompare(String(a.createdAt))).slice(0, 8);
  $('#costList').innerHTML = sorted.length ? sorted.map(expense => '<article class="cost-row"><div class="cost-row__date"><strong>' + String(expense.date).slice(8, 10) + '</strong><span>' + new Intl.DateTimeFormat('pt-BR', { month: 'short', timeZone: 'UTC' }).format(new Date(expense.date + 'T12:00:00Z')).replace('.', '') + '</span></div><div class="cost-row__info"><strong>' + escapeHtml(COST_CATEGORIES[expense.category] || 'Outros') + (expense.recurring ? '<em title="Despesa fixa mensal">Fixa</em>' : '') + '</strong><span>' + escapeHtml(expense.description || 'Despesa da cocheira') + '</span></div><b>' + escapeHtml(money(expense.amountCents)) + '</b><div class="cost-row__actions"><button type="button" data-cost-action="edit" data-id="' + expense.id + '">Editar</button><button type="button" data-cost-action="delete" data-id="' + expense.id + '">Excluir</button></div></article>').join('') : '<div class="cost-empty">Nenhuma despesa lançada neste mês.</div>';
}

function renderAccount() {
  const info = state.accountInfo;
  if (!info) return;
  state.accountEmail = info.currentEmail || '';
  $('#accountEmails').innerHTML = info.emails.map(email => {
    const current = email === info.currentEmail;
    return '<div class="account-email"><div><strong>' + escapeHtml(email) + '</strong>' +
      (current ? '<span>E-mail em uso neste aparelho</span>' : '<span>Acesso adicional</span>') +
      '</div>' + (current ? '<b>Atual</b>' : '<button class="button button--soft" type="button" data-remove-email="' + escapeHtml(email) + '">Remover</button>') + '</div>';
  }).join('');
}

async function loadAccount() {
  state.accountInfo = await api.account();
  renderAccount();
}

async function openAccountManager() {
  $('#addEmailError').textContent = '';
  $('#passwordError').textContent = '';
  $('#addEmailForm')?.reset();
  $('#changePasswordForm')?.reset();
  try {
    await loadAccount();
    $('#accountModal').showModal();
  } catch (error) {
    toast(error.message, true);
  }
}

function pedigree(horse) {
  const parents = [horse.father, horse.mother].filter(Boolean).map(escapeHtml).join(' × ');
  return parents ? '<p class="horse-card__pedigree"><span>Filiação</span>' + parents + '</p>' : '';
}

function horseIdentityHeader(horse, stage, status, detail = '') {
  const parents = [horse.father, horse.mother].filter(Boolean).map(escapeHtml).join(' × ');
  const silhouettes = {
    foals: '/icons/potros-tropa-final-contorno-principal-2x.png?v=v4',
    training: '/icons/cavalo-treinamento-v6.png?v=v6',
    ready: '/icons/polo-sem-dobras-camisa.png?v=v4',
  };
  const silhouette = silhouettes[stage] || silhouettes.foals;
  return [
    '<header class="horse-identity horse-identity--', stage, '">',
    '<img class="horse-identity__silhouette" src="', silhouette, '" alt="" aria-hidden="true">',
    '<div class="horse-identity__status"><span>', escapeHtml(status), '</span>',
    detail ? '<strong>' + detail + '</strong>' : '', '</div>',
    '<div class="horse-identity__name"><h2>', escapeHtml(horse.name || 'Nome a definir'), '</h2>',
    '<p>', parents || 'Filiação não informada', '</p></div>',
    '</header>',
  ].join('');
}

function commonActions(horse) {
  const previous = { training: 'foals', ready: 'training' }[horse.stage];
  const back = previous
    ? '<button data-action="previous-stage" data-target="' + previous + '" data-id="' + horse.id + '">' + uiIcon('arrow-left') + '<span>Voltar etapa</span></button>'
    : '';
  return '<div class="card-actions">' + back + '<button data-action="edit" data-id="' + horse.id + '">Editar</button><button data-action="delete" data-id="' + horse.id + '">Excluir</button></div>';
}

function creationCard(horse) {
  const father = escapeHtml(horse.father || 'Não informado');
  const mother = escapeHtml(horse.mother || 'Não informada');
  return [
    '<article class="horse-card creation-card" data-horse-id="', horse.id, '" role="button" tabindex="0" aria-label="Abrir ficha da cruza">',
    '<div class="creation-card__date"><div class="creation-card__date-label">', uiIcon('calendar'), '<span>Previsão de nascimento</span></div><strong>', formatDate(horse.expectedBirthDate, 'Sem previsão'), '</strong></div>',
    '<div class="horse-card__body"><span class="creation-card__label">CRUZAMENTO</span>',
    '<div class="creation-card__pair"><div><span>PAI</span><strong>', father, '</strong></div><div><span>MÃE</span><strong>', mother, '</strong></div></div>',
    '<button class="button button--primary" data-action="born" data-id="', horse.id, '">Registrar nascimento</button>',
    commonActions(horse), '</div></article>',
  ].join('');
}

function foalCard(horse) {
  return [
    '<article class="horse-card" data-horse-id="', horse.id, '" role="button" tabindex="0" aria-label="Abrir ficha de ', escapeHtml(horse.name), '">',
    horseIdentityHeader(horse, 'foals', 'POTRO', escapeHtml(ageLabel(horse))),
    '<div class="horse-card__body">',
    '<button class="button button--primary" data-action="to-training" data-id="', horse.id, '">Enviar para treinamento</button>',
    commonActions(horse), '</div></article>',
  ].join('');
}

function trainingCard(horse) {
  const workouts = Number(horse.workouts) || 0;
  const done = workouts >= GOAL;
  const percentage = Math.min(100, Math.max(0, Math.round((workouts / GOAL) * 100)));
  return [
    '<article class="horse-card', done ? ' is-done' : '', '" data-horse-id="', horse.id, '" role="button" tabindex="0" aria-label="Abrir ficha de ', escapeHtml(horse.name), '">',
    horseIdentityHeader(horse, 'training', done ? 'META CONCLUÍDA' : 'EM TREINAMENTO', workouts + ' / ' + GOAL),
    '<div class="horse-card__body">',
    '<p class="horse-card__age">', escapeHtml(ageLabel(horse)), '</p>',
    '<div class="progress" role="progressbar" aria-label="Progresso de treinos" aria-valuemin="0" aria-valuemax="', GOAL, '" aria-valuenow="', Math.min(workouts, GOAL), '"><span style="width:', percentage, '%"></span></div>',
    '<div class="horse-card__meta"><span>', percentage, '% da meta</span>', done ? '<b>Meta alcançada</b>' : '', '</div>',
    '<p class="horse-card__date">Último treino: ', formatDate(horse.lastWorkout, 'Nenhum registrado'), '</p>',
    '<div class="workout-actions"><button class="button button--soft" data-action="workout-minus" data-id="', horse.id, '" aria-label="Descontar um treino" ', workouts < 1 ? 'disabled' : '', '>', uiIcon('minus'), '<span>Descontar treino</span></button>',
    '<button class="button button--primary" data-action="workout-plus" data-id="', horse.id, '" aria-label="Somar um treino">', uiIcon('plus'), '<span>Somar treino</span></button></div>',
    done ? '<button class="button button--gold button--wide transfer-button" data-action="to-ready" data-id="' + horse.id + '">Enviar para tropa pronta</button>' : '',
    commonActions(horse), '</div></article>',
  ].join('');
}

function readyCard(horse) {
  return [
    '<article class="horse-card ready-card" data-horse-id="', horse.id, '" role="button" tabindex="0" aria-label="Abrir ficha de ', escapeHtml(horse.name), '">',
    horseIdentityHeader(horse, 'ready', 'TROPA PRONTA', 'TORNEIO'),
    '<div class="horse-card__body">',
    '<p class="horse-card__age">', escapeHtml(ageLabel(horse)), '</p>',
    commonActions(horse), '</div></article>',
  ].join('');
}

function readyGroupHeader(count) {
  const label = count === 1 ? 'cavalo pronto' : 'cavalos prontos';
  return [
    '<header class="ready-group__head">',
    '<span class="ready-group__icon" aria-hidden="true"><img src="/icons/polo-sem-dobras-camisa.png?v=v4" alt=""></span>',
    '<div><span>GRUPO DE COMPETIÇÃO</span><h2>Tropa pronta para torneio</h2>',
    '<p>Animais que concluíram a preparação e integram a tropa pronta.</p></div>',
    '<strong><b>', count, '</b><span>', label, '</span></strong>',
    '</header>',
  ].join('');
}

function renderCard(horse) {
  if (horse.stage === 'creation') return creationCard(horse);
  if (horse.stage === 'foals') return foalCard(horse);
  if (horse.stage === 'ready') return readyCard(horse);
  return trainingCard(horse);
}

function detailItem(label, value, wide = false) {
  return '<div class="horse-detail-item' + (wide ? ' horse-detail-item--wide' : '') + '"><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(value || 'Não informado') + '</strong></div>';
}

function optionalDetailItem(label, value, wide = false) {
  return value ? detailItem(label, value, wide) : '';
}

function missingHorseFields(horse) {
  const hasAge = Boolean(horse.birthDate || horse.age !== null && horse.age !== undefined && horse.age !== '');
  return [
    { present: hasAge, label: 'idade ou nascimento', ids: ['birthDate', 'age'] },
    { present: horse.father, label: 'pai', ids: ['father'] },
    { present: horse.mother, label: 'mãe', ids: ['mother'] },
    { present: horse.breed, label: 'raça', ids: ['breed'] },
    { present: horse.sex, label: 'sexo', ids: ['sex'] },
    { present: horse.owner, label: 'proprietário', ids: ['owner'] },
    { present: horse.location, label: 'localização', ids: ['location'] },
  ].filter(field => !field.present);
}

function openHorseDetails(horse) {
  const stage = STAGES[horse.stage] || STAGES.training;
  const isCreation = horse.stage === 'creation';
  const isTraining = horse.stage === 'training';
  const isReady = horse.stage === 'ready';
  const workouts = Number(horse.workouts) || 0;
  const percentage = Math.min(100, Math.max(0, Math.round((workouts / GOAL) * 100)));
  $('#detailEyebrow').textContent = stage.title.toUpperCase();
  $('#detailName').textContent = isCreation ? 'Cruza registrada' : (horse.name || 'Cavalo');
  $('#detailEdit').dataset.id = horse.id;
  const pedigreeItems = optionalDetailItem('Pai', horse.father) + optionalDetailItem('Mãe', horse.mother);
  const pedigree = pedigreeItems ? '<section class="horse-detail-pedigree"><p>FILIAÇÃO</p><div>' + pedigreeItems + '</div></section>' : '';
  const hasAge = Boolean(horse.birthDate) || horse.age !== null && horse.age !== undefined && horse.age !== '';
  const dates = isCreation
    ? optionalDetailItem('Nascimento previsto', horse.expectedBirthDate ? formatDate(horse.expectedBirthDate) : '', true)
    : optionalDetailItem('Nascimento', horse.birthDate ? formatDate(horse.birthDate) : '') + optionalDetailItem('Idade atual', hasAge ? ageLabel(horse) : '');
  const summaryItems = dates + optionalDetailItem('Raça', horse.breed) + optionalDetailItem('Sexo', horse.sex) +
    optionalDetailItem('Proprietário', horse.owner) + (isCreation ? '' : optionalDetailItem('Localização atual', horse.location));
  const summary = summaryItems ? '<section class="horse-detail-summary">' + summaryItems + '</section>' : '';
  const missingFields = isCreation ? [] : missingHorseFields(horse).map(field => field.label);
  const missingLabel = missingFields.length === 1 ? '1 informação ainda não preenchida' : missingFields.length + ' informações ainda não preenchidas';
  const missing = missingFields.length ? '<section class="horse-detail-missing"><div><span>CADASTRO INCOMPLETO</span><strong>' + missingLabel + '</strong><p>' + escapeHtml(missingFields.join(', ')) + '</p></div><button class="button button--soft" type="button" data-complete-details>Completar cadastro</button></section>' : '';
  const training = isTraining ? '<section class="horse-detail-training"><div><span>PROGRESSO DE TREINAMENTO</span><strong>' + workouts + ' de ' + GOAL + ' treinos</strong></div><div class="progress"><span style="width:' + percentage + '%"></span></div><small>' + percentage + '% da meta</small></section>' : '';
  const ready = isReady ? '<div class="horse-detail-ready"><img class="ready-inline-icon" src="/icons/polo-sem-dobras-camisa.png?v=v4" alt="" aria-hidden="true"><strong>Pronto para torneio</strong></div>' : '';
  $('#horseDetailsBody').innerHTML = [
    ready, summary, pedigree, missing, training,
    horse.notes ? '<section class="horse-detail-notes"><span>OBSERVAÇÕES</span><p>' + escapeHtml(horse.notes) + '</p></section>' : '',
  ].join('');
  $('#horseDetailsModal').showModal();
}

function horseShareFields(horse) {
  const isCreation = horse.stage === 'creation';
  const hasAge = Boolean(horse.birthDate) || horse.age !== null && horse.age !== undefined && horse.age !== '';
  const fields = [];
  const add = (label, value) => { if (value !== null && value !== undefined && String(value).trim()) fields.push([label, String(value).trim()]); };
  if (isCreation) add('Previsão de nascimento', horse.expectedBirthDate ? formatDate(horse.expectedBirthDate) : 'Sem previsão');
  else {
    add('Idade', hasAge ? ageLabel(horse) : '');
    add('Nascimento', horse.birthDate ? formatDate(horse.birthDate) : '');
  }
  add('Pai', horse.father);
  add('Mãe', horse.mother);
  add('Raça', horse.breed);
  add('Sexo', horse.sex);
  add('Proprietário', horse.owner);
  if (!isCreation) add('Localização', horse.location);
  if (horse.stage === 'training') {
    add('Treinos', (Number(horse.workouts) || 0) + ' de ' + GOAL);
    add('Último treino', horse.lastWorkout ? formatDate(horse.lastWorkout) : 'Nenhum registrado');
  }
  if (horse.stage === 'ready') add('Situação', 'Pronto para torneio');
  add('Observações', horse.notes);
  return fields;
}

function horseShareText(horse) {
  const stage = STAGES[horse.stage] || STAGES.training;
  const name = horse.stage === 'creation'
    ? [horse.father, horse.mother].filter(Boolean).join(' × ') || 'Cruza registrada'
    : horse.name || 'Cavalo';
  return [
    '*COCHEIRA RADAMÉS*',
    '*' + name.toLocaleUpperCase('pt-BR') + '*',
    stage.title,
    '',
    ...horseShareFields(horse).map(([label, value]) => '*' + label + ':* ' + value),
  ].join('\n');
}

function wrapCanvasText(context, text, maxWidth) {
  const words = String(text).split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  words.forEach(word => {
    const candidate = line ? line + ' ' + word : word;
    if (line && context.measureText(candidate).width > maxWidth) {
      lines.push(line);
      line = word;
    } else line = candidate;
  });
  if (line) lines.push(line);
  return lines.length ? lines : [''];
}

function canvasToBlob(canvas) {
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Não foi possível gerar o cartão.')), 'image/png'));
}

function fillRoundedRect(context, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.moveTo(x + r, y);
  context.lineTo(x + width - r, y);
  context.quadraticCurveTo(x + width, y, x + width, y + r);
  context.lineTo(x + width, y + height - r);
  context.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  context.lineTo(x + r, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - r);
  context.lineTo(x, y + r);
  context.quadraticCurveTo(x, y, x + r, y);
  context.closePath();
  context.fill();
}

async function createHorseShareCard(horse) {
  const canvas = document.createElement('canvas');
  canvas.width = 1080;
  const fields = horseShareFields(horse);
  const contentHeight = fields.reduce((total, [label]) => total + (label === 'Observações' ? 164 : 108), 0);
  canvas.height = Math.max(1350, 700 + contentHeight);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Este navegador não conseguiu criar o cartão.');
  const stage = STAGES[horse.stage] || STAGES.training;
  const name = horse.stage === 'creation'
    ? [horse.father, horse.mother].filter(Boolean).join(' × ') || 'Cruza registrada'
    : horse.name || 'Cavalo';

  const background = context.createLinearGradient(0, 0, 1080, 1350);
  background.addColorStop(0, '#173f30');
  background.addColorStop(1, '#08241a');
  context.fillStyle = background;
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = 'rgba(210,170,82,.12)';
  context.beginPath();
  context.arc(970, 120, 280, 0, Math.PI * 2);
  context.fill();
  context.strokeStyle = '#d2aa52';
  context.lineWidth = 4;
  context.strokeRect(48, 48, 984, canvas.height - 96);

  context.fillStyle = '#efd183';
  context.font = '700 30px Georgia, serif';
  context.letterSpacing = '5px';
  context.fillText('COCHEIRA RADAMÉS', 100, 135);
  context.font = '700 25px Arial, sans-serif';
  context.fillText(stage.title.toLocaleUpperCase('pt-BR'), 100, 215);
  context.fillStyle = '#ffffff';
  context.font = '700 66px Georgia, serif';
  const nameLines = wrapCanvasText(context, name.toLocaleUpperCase('pt-BR'), 860).slice(0, 2);
  let y = 310;
  nameLines.forEach(line => { context.fillText(line, 100, y); y += 76; });
  context.fillStyle = '#d2aa52';
  context.fillRect(100, y + 8, 140, 5);
  y += 80;

  fields.forEach(([label, value], index) => {
    const isNotes = label === 'Observações';
    context.fillStyle = 'rgba(255,255,255,.075)';
    const rowHeight = isNotes ? 150 : 94;
    fillRoundedRect(context, 88, y - 42, 904, rowHeight, 16);
    context.fillStyle = '#efd183';
    context.font = '700 20px Arial, sans-serif';
    context.fillText(label.toLocaleUpperCase('pt-BR'), 118, y - 5);
    context.fillStyle = '#ffffff';
    context.font = '600 30px Arial, sans-serif';
    const lines = wrapCanvasText(context, value, 820).slice(0, isNotes ? 3 : 1);
    lines.forEach((line, lineIndex) => context.fillText(line, 118, y + 37 + lineIndex * 34));
    y += rowHeight + (index === fields.length - 1 ? 0 : 14);
  });

  context.fillStyle = '#b9c8c0';
  context.font = '500 20px Arial, sans-serif';
  context.fillText('Ficha compartilhada pela Cocheira RADAMÉS', 100, canvas.height - 90);
  return canvasToBlob(canvas);
}

async function shareHorse(horse) {
  const text = horseShareText(horse);
  const image = await createHorseShareCard(horse);
  const safeName = String(horse.name || 'cruza').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase();
  const file = new File([image], 'ficha-' + (safeName || 'cavalo') + '.png', { type: 'image/png' });
  if (navigator.share && navigator.canShare?.({ files: [file] })) {
    await navigator.share({ title: 'Ficha do cavalo', text, files: [file] });
    return;
  }
  if (navigator.share) {
    await navigator.share({ title: 'Ficha do cavalo', text });
    return;
  }
  const imageUrl = URL.createObjectURL(image);
  const download = document.createElement('a');
  download.href = imageUrl;
  download.download = file.name;
  document.body.append(download);
  download.click();
  download.remove();
  setTimeout(() => URL.revokeObjectURL(imageUrl), 1500);
  window.open('https://wa.me/?text=' + encodeURIComponent(text), '_blank', 'noopener');
  toast('Cartão salvo. No WhatsApp Web, anexe a imagem baixada à conversa.');
}

function render() {
  Object.keys(STAGES).forEach(stage => {
    $('#count-' + stage).textContent = state.horses.filter(horse => horse.stage === stage).length;
  });
  $('#homeView').hidden = Boolean(state.stage || state.costs);
  $('#stageView').hidden = !state.stage;
  $('#costsView').hidden = !state.costs;
  $('#openAssistant')?.classList.toggle('is-home', !state.stage && !state.costs);
  $('#app')?.classList.toggle('assistant-home', !state.stage && !state.costs);
  if (state.costs) renderCosts();
  if (!state.stage) return;
  document.querySelectorAll('.stage-card').forEach(button => button.classList.toggle('is-active', button.dataset.stage === state.stage));
  const config = STAGES[state.stage];
  $('#stageOverline').textContent = config.overline;
  $('#stageTitle').textContent = config.title;
  $('#stageDescription').textContent = config.description;
  $('#addHorseLabel').textContent = config.add;
  $('#horseGrid').classList.toggle('horse-grid--creation', state.stage === 'creation');
  $('#horseGrid').classList.toggle('horse-grid--ready', state.stage === 'ready');
  const query = state.query.trim().toLocaleLowerCase('pt-BR');
  let list = state.horses.filter(horse => horse.stage === state.stage && [horse.name, horse.father, horse.mother, horse.owner, horse.location].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(query)));
  if (state.stage === 'creation') {
    list.sort((a, b) => {
      if (a.expectedBirthDate && b.expectedBirthDate) return a.expectedBirthDate.localeCompare(b.expectedBirthDate);
      if (a.expectedBirthDate) return -1;
      if (b.expectedBirthDate) return 1;
      return String(a.father || '').localeCompare(String(b.father || ''), 'pt-BR', { sensitivity: 'base' });
    });
  }
  const currentYear = new Date().getFullYear();
  const ageInMonths = horse => {
    if (horse.birthDate) {
      const born = new Date(horse.birthDate + 'T12:00:00');
      const today = new Date();
      return Math.max(0, (today.getFullYear() - born.getFullYear()) * 12 + today.getMonth() - born.getMonth() - (today.getDate() < born.getDate()));
    }
    if (horse.age === null || horse.age === undefined || horse.age === '') return null;
    const recordedYear = Number(String(horse.ageRecordedAt || '').slice(0, 4)) || currentYear;
    return (Number(horse.age) + Math.max(0, currentYear - recordedYear)) * 12;
  };
  if (state.stage !== 'creation') list.sort((a, b) => {
    const byName = String(a.name || 'Nome a definir').localeCompare(String(b.name || 'Nome a definir'), 'pt-BR', { sensitivity: 'base', numeric: true });
    if (byName) return byName;
    const ageA = ageInMonths(a);
    const ageB = ageInMonths(b);
    if (ageA === null && ageB === null) return 0;
    if (ageA === null) return 1;
    if (ageB === null) return -1;
    return ageB - ageA;
  });
  $('#horseGrid').innerHTML = list.length
    ? (state.stage === 'ready' ? readyGroupHeader(list.length) : '') + list.map(renderCard).join('')
    : '<div class="empty"><strong>Nenhum registro em ' + escapeHtml(config.title) + '</strong><span>' + (query ? 'Tente outro termo de busca.' : 'Use “' + escapeHtml(config.add) + '” para começar.') + '</span></div>';
}

function openExpenseForm(expense = null) {
  const editing = Boolean(expense?.id);
  state.editingExpense = editing ? expense.id : null;
  $('#expenseForm')?.reset();
  $('#expenseError').textContent = '';
  $('#expenseModalTitle').textContent = editing ? 'Editar despesa' : 'Adicionar despesa';
  $('#expenseAmount').value = expense ? (Number(expense.amountCents || 0) / 100).toFixed(2).replace('.', ',') : '';
  $('#expenseDate').value = expense?.date || localIsoDate();
  $('#expenseCategory').value = expense?.category || 'food';
  $('#expenseDescription').value = expense?.description || '';
  $('#expenseRecurring').checked = Boolean(expense?.recurring);
  $('#expenseModal').showModal();
}

function applyExpenseDraft(draft, issues = []) {
  openExpenseForm({
    id: null,
    amountCents: draft.amountCents || 0,
    date: draft.date,
    category: draft.category,
    scope: 'general',
    horseId: '',
    description: draft.description,
    recurring: Boolean(draft.recurring),
  });
  state.editingExpense = null;
  if (issues.length) $('#expenseError').textContent = issues.join(' ');
}

function fileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Não foi possível ler o arquivo.'));
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.readAsDataURL(file);
  });
}

function setCostImportMethod(method) {
  document.querySelectorAll('[data-cost-import-method]').forEach(button => button.classList.toggle('is-active', button.dataset.costImportMethod === method));
  document.querySelectorAll('[data-cost-import-panel]').forEach(panel => { panel.hidden = panel.dataset.costImportPanel !== method; });
  $('#costImportReview').hidden = true;
  $('#costImportError').textContent = '';
}

function renderCostImportReview(result) {
  state.costImportPreview = result.records || [];
  $('#costImportSummary').textContent = `${state.costImportPreview.length} ${state.costImportPreview.length === 1 ? 'despesa encontrada' : 'despesas encontradas'}`;
  const categoryOptions = selected => Object.entries(COST_CATEGORIES).map(([value, label]) => `<option value="${value}" ${value === selected ? 'selected' : ''}>${label}</option>`).join('');
  $('#costImportRecords').innerHTML = state.costImportPreview.map((record, index) => {
    const amount = (Number(record.amountCents || 0) / 100).toFixed(2).replace('.', ',');
    const issues = record.issues || [];
    return `<article class="cost-import-record ${issues.length ? 'needs-review' : ''}" data-cost-import-index="${index}">
      <label class="import-select"><input data-cost-import-select type="checkbox" ${record.selected ? 'checked' : ''}><span>Importar</span></label>
      <div class="cost-import-record__fields">
        <label class="field"><span>Descrição</span><input data-cost-field="description" maxlength="180" value="${escapeHtml(record.description || '')}"></label>
        <label class="field"><span>Valor</span><input data-cost-field="amount" inputmode="decimal" value="${escapeHtml(amount)}"></label>
        <label class="field"><span>Data</span><input data-cost-field="date" type="date" value="${escapeHtml(record.date || localIsoDate())}"></label>
        <label class="field"><span>Categoria</span><select data-cost-field="category">${categoryOptions(record.category)}</select></label>
      </div>
      <label class="cost-import-recurring"><input data-cost-field="recurring" type="checkbox" ${record.recurring ? 'checked' : ''}><span>Fixa mensal</span></label>
      ${issues.length ? `<p class="import-alert">${escapeHtml(issues.join(' · '))}</p>` : ''}
    </article>`;
  }).join('');
  $('#costImportReview').hidden = false;
  document.querySelectorAll('[data-cost-import-panel]').forEach(panel => { panel.hidden = true; });
  if ((result.warnings || []).length) $('#costImportError').textContent = result.warnings.join(' ');
}

async function previewCostImport(payload, button) {
  const previous = button.textContent;
  $('#costImportError').textContent = '';
  button.disabled = true;
  button.textContent = 'Organizando…';
  try {
    renderCostImportReview(await api.previewExpenseImport(payload));
  } catch (error) {
    $('#costImportError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = previous;
  }
}

function clearForm() {
  $('#horseForm')?.reset();
  $('#workouts').value = 0;
  $('#horseError').textContent = '';
  $('#completionGuide').hidden = true;
  document.querySelectorAll('#horseForm .field.is-missing').forEach(field => field.classList.remove('is-missing'));
}

function configureForm(stage, editing = false) {
  $('#formStage').value = stage;
  $('#horseModal').dataset.stage = stage;
  $('#modalEyebrow').textContent = STAGES[stage].title.toUpperCase();
  $('#modalTitle').textContent = editing ? 'Editar cadastro' : STAGES[stage].add;
  $('#nameLabel').textContent = 'Nome do cavalo *';
  document.querySelectorAll('.creation-required').forEach(item => item.hidden = stage !== 'creation');
}

function openCreate() {
  state.editing = null;
  clearForm();
  configureForm(state.stage, false);
  $('#horseModal').showModal();
}

function openEdit(id, complete = false) {
  const horse = state.horses.find(item => item.id === id);
  if (!horse) return;
  state.editing = id;
  clearForm();
  configureForm(horse.stage, true);
  ['name', 'breed', 'sex', 'owner', 'location', 'father', 'mother', 'notes', 'expectedBirthDate', 'birthDate'].forEach(key => $('#' + key).value = horse[key] || '');
  $('#age').value = horse.birthDate ? '' : (horse.age ?? '');
  $('#workouts').value = horse.workouts ?? 0;
  const missing = complete && horse.stage !== 'creation' ? missingHorseFields(horse) : [];
  if (missing.length) {
    $('#completionGuideText').textContent = 'Faltam: ' + missing.map(field => field.label).join(', ') + '.';
    $('#completionGuide').hidden = false;
    missing.flatMap(field => field.ids).forEach(fieldId => $('#' + fieldId)?.closest('.field')?.classList.add('is-missing'));
  }
  $('#horseModal').showModal();
  if (missing.length) requestAnimationFrame(() => $('#' + missing[0].ids[0])?.focus());
}

function ask(title, text, callback, danger = false, labels = {}, cancelCallback = null) {
  state.pending = callback;
  state.pendingCancel = cancelCallback;
  $('#confirmTitle').textContent = title;
  $('#confirmText').textContent = text;
  $('#confirmYes').className = 'button ' + (danger ? 'button--danger' : 'button--primary');
  $('#confirmYes').textContent = labels.yes || 'Confirmar';
  $('#confirmNo').textContent = labels.no || 'Cancelar';
  $('#confirmModal').showModal();
}

function openBorn(horse) {
  $('#bornHorseId').value = horse.id;
  $('#bornName').value = horse.name || '';
  $('#actualBirthDate').value = '';
  $('#bornError').textContent = '';
  $('#bornModal').showModal();
}

function celebrate() {
  const colors = ['#c89d4a', '#efd183', '#102f24', '#fff', '#a95e45'];
  for (let index = 0; index < 52; index++) {
    const piece = document.createElement('i');
    piece.style.left = (Math.random() * 100) + 'vw';
    piece.style.background = colors[index % colors.length];
    piece.style.setProperty('--dx', (Math.random() * 170 - 85) + 'px');
    piece.style.animationDelay = (Math.random() * .3) + 's';
    $('#confetti').append(piece);
  }
  setTimeout(() => $('#confetti').replaceChildren(), 2200);
}

async function guarded(button, operation) {
  if (button.disabled) return;
  button.disabled = true;
  try { await operation(); }
  catch (error) { toast(error.message, true); }
  finally { button.disabled = false; }
}

$('#authForm').addEventListener('submit', async event => {
  event.preventDefault();
  const email = $('#authEmail').value.trim();
  const password = $('#authPassword').value;
  const firstName = $('#authFirstName').value.trim();
  const lastName = $('#authLastName').value.trim();
  const button = $('#authButton');
  $('#authError').textContent = '';
  if (!/^\S+@\S+\.\S+$/.test(email)) return void ($('#authError').textContent = 'Informe um e-mail válido.');
  if (password.length < 6) return void ($('#authError').textContent = 'A senha precisa ter pelo menos 6 caracteres.');
  if (state.authMode === 'signup' && !firstName) return void ($('#authError').textContent = 'Informe seu nome.');
  if (state.authMode === 'signup' && !lastName) return void ($('#authError').textContent = 'Informe seu sobrenome.');
  button.disabled = true;
  button.textContent = 'Aguarde…';
  try {
    const signup = state.authMode === 'signup';
    signup ? await api.signup(firstName, lastName, email, password) : await api.login(email, password);
    await showApp();
    toast(signup ? 'Conta criada com sucesso.' : 'Login realizado com sucesso.');
  } catch (error) {
    $('#authError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = state.authMode === 'signup' ? 'Criar conta' : 'Entrar';
  }
});

$('#authSwitch').addEventListener('click', () => {
  state.authMode = state.authMode === 'login' ? 'signup' : 'login';
  $('#authError').textContent = '';
  $('#authPassword').value = '';
  $('#authFirstName').value = '';
  $('#authLastName').value = '';
  renderAuthMode();
});

const closeSettingsMenu = () => {
  $('#settingsMenu').hidden = true;
  $('#openSettings').setAttribute('aria-expanded', 'false');
};

$('#openSettings').addEventListener('click', event => {
  event.stopPropagation();
  const willOpen = $('#settingsMenu').hidden;
  $('#settingsMenu').hidden = !willOpen;
  $('#openSettings').setAttribute('aria-expanded', String(willOpen));
});
$('#settingsMenu').addEventListener('click', event => event.stopPropagation());
document.addEventListener('click', closeSettingsMenu);
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeSettingsMenu(); });

$('#logout').addEventListener('click', async () => { closeSettingsMenu(); await api.logout(); showAuth(await api.session()); });
$('#manageAccount').addEventListener('click', () => { closeSettingsMenu(); openAccountManager(); });
document.querySelectorAll('.account-close').forEach(button => button.addEventListener('click', () => $('#accountModal').close()));
$('#manageAppearance').addEventListener('click', () => {
  closeSettingsMenu();
  applyAppearance(readAppearance());
  $('#appearanceModal').showModal();
});
document.querySelectorAll('.appearance-close').forEach(button => button.addEventListener('click', () => $('#appearanceModal').close()));
$('#fontPreference').addEventListener('change', () => {
  applyAppearance({ font: $('#fontPreference').value, size: $('#fontSizePreference').value }, true);
  toast('Preferência de aparência salva neste aparelho.');
});
$('#fontSizePreference').addEventListener('input', () => {
  applyAppearance({ font: $('#fontPreference').value, size: $('#fontSizePreference').value }, true);
});
$('#fontSizePreference').addEventListener('change', () => toast('Tamanho da fonte salvo neste aparelho.'));
$('#addEmailForm').addEventListener('submit', async event => {
  event.preventDefault();
  const email = $('#newAccessEmail').value.trim();
  const password = $('#newAccessPassword').value;
  const button = event.submitter;
  $('#addEmailError').textContent = '';
  if (!/^\S+@\S+\.\S+$/.test(email)) return void ($('#addEmailError').textContent = 'Informe um e-mail válido.');
  if (password.length < 6) return void ($('#addEmailError').textContent = 'A senha precisa ter pelo menos 6 caracteres.');
  button.disabled = true;
  try {
    await api.addAccountEmail(email, password);
    event.currentTarget.reset();
    await loadAccount();
    toast('Novo e-mail de acesso adicionado.');
  } catch (error) {
    $('#addEmailError').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$('#changePasswordForm').addEventListener('submit', async event => {
  event.preventDefault();
  const currentPassword = $('#currentPassword').value;
  const newPassword = $('#newPassword').value;
  const button = event.submitter;
  $('#passwordError').textContent = '';
  if (newPassword.length < 6) return void ($('#passwordError').textContent = 'A nova senha precisa ter pelo menos 6 caracteres.');
  button.disabled = true;
  try {
    await api.changePassword(currentPassword, newPassword);
    event.currentTarget.reset();
    toast('Senha atualizada com segurança.');
  } catch (error) {
    $('#passwordError').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$('#accountEmails').addEventListener('click', event => {
  const button = event.target.closest('[data-remove-email]');
  if (!button) return;
  const email = button.dataset.removeEmail;
  ask('Remover acesso', 'Deseja impedir o acesso de ' + email + '? Os cavalos da conta não serão apagados.', async () => {
    await api.removeAccountEmail(email);
    await loadAccount();
    toast('Acesso removido.');
  }, true, { yes: 'Remover', no: 'Cancelar' });
});
$('#openAssistant').addEventListener('click', () => { $('#assistantModal').showModal(); $('#assistantQuestion').focus(); });
$('#closeAssistant').addEventListener('click', () => $('#assistantModal').close());
$('#assistantForm').addEventListener('submit', event => { event.preventDefault(); askAssistant($('#assistantQuestion').value); });
document.querySelectorAll('.assistant__examples button').forEach(button => button.addEventListener('click', () => askAssistant(button.dataset.question || button.textContent)));

const SpeechRecognition = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
if (SpeechRecognition) {
  const recognition = new SpeechRecognition();
  recognition.lang = 'pt-BR';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.addEventListener('start', () => {
    $('#assistantVoice').classList.add('is-listening');
    $('#assistantVoice').setAttribute('aria-label', 'Ouvindo pergunta');
  });
  recognition.addEventListener('end', () => {
    $('#assistantVoice').classList.remove('is-listening');
    $('#assistantVoice').setAttribute('aria-label', 'Fazer pergunta por voz');
  });
  recognition.addEventListener('result', event => {
    const transcript = event.results?.[0]?.[0]?.transcript?.trim();
    if (!transcript) return;
    $('#assistantQuestion').value = transcript;
    askAssistant(transcript);
  });
  recognition.addEventListener('error', event => {
    if (event.error !== 'aborted') toast('Não consegui ouvir. Verifique a permissão do microfone e tente novamente.', true);
  });
  $('#assistantVoice').addEventListener('click', () => {
    try { recognition.start(); } catch { recognition.stop(); }
  });
} else {
  $('#assistantVoice').disabled = true;
  $('#assistantVoice').title = 'Perguntas por voz não são compatíveis com este navegador.';
}
function goHome() {
  state.stage = null;
  state.costs = false;
  state.query = '';
  $('#search').value = '';
  render();
}

$('#homeButton').addEventListener('click', goHome);
$('#backHome').addEventListener('click', goHome);
$('#backFromCosts').addEventListener('click', goHome);
$('#openCosts').addEventListener('click', async () => {
  state.stage = null;
  state.costs = true;
  await loadExpenses();
  render();
});
window.addEventListener('beforeinstallprompt', event => { event.preventDefault(); installPrompt = event; $('#installApp').hidden = false; });
if (/iphone|ipad|ipod/i.test(navigator.userAgent) && !navigator.standalone) $('#installApp').hidden = false;
$('#installApp').addEventListener('click', async () => {
  if (installPrompt) {
    await installPrompt.prompt();
    installPrompt = null;
    $('#installApp').hidden = true;
  } else {
    toast('No iPhone, toque em Compartilhar e depois em “Adicionar à Tela de Início”.');
  }
});

$('#addHorse').addEventListener('click', openCreate);
$('#search').addEventListener('input', event => { state.query = event.target.value; render(); });
$('#stageTimeline').addEventListener('click', event => {
  const button = event.target.closest('[data-stage]');
  if (!button) return;
  state.stage = button.dataset.stage;
  state.costs = false;
  state.query = '';
  $('#search').value = '';
  render();
});
document.querySelectorAll('.modal-close').forEach(button => button.addEventListener('click', () => $('#horseModal').close()));
document.querySelectorAll('.born-close').forEach(button => button.addEventListener('click', () => $('#bornModal').close()));
document.querySelectorAll('.confirm-close').forEach(button => button.addEventListener('click', () => {
  const cancelCallback = state.pendingCancel;
  state.pending = null;
  state.pendingCancel = null;
  $('#confirmModal').close();
  cancelCallback?.();
}));
$('#confirmYes').addEventListener('click', async () => {
  const callback = state.pending;
  state.pending = null;
  state.pendingCancel = null;
  $('#confirmModal').close();
  try { await callback?.(); } catch (error) { toast(error.message, true); }
});
$('#birthDate').addEventListener('input', event => { if (event.target.value) $('#age').value = ''; });
$('#age').addEventListener('input', event => { if (event.target.value !== '') $('#birthDate').value = ''; });

$('#horseForm').addEventListener('submit', async event => {
  event.preventDefault();
  const stage = $('#formStage').value;
  const name = $('#name').value.trim();
  const saveButton = $('#saveHorse');
  const duplicate = state.horses.find(horse => horse.id !== state.editing && name && horse.name.trim().toLocaleLowerCase('pt-BR') === name.toLocaleLowerCase('pt-BR'));
  $('#horseError').textContent = '';
  if (stage !== 'creation' && !name) return void ($('#horseError').textContent = 'Informe o nome do cavalo.');
  if (stage === 'creation' && (!$('#father').value.trim() || !$('#mother').value.trim())) return void ($('#horseError').textContent = 'Informe o nome do pai e da mãe.');
  const persistHorse = async () => {
    saveButton.disabled = true;
    saveButton.textContent = 'Salvando…';
    try {
    const horse = {
      stage,
      name,
      father: $('#father').value.trim(),
      mother: $('#mother').value.trim(),
      expectedBirthDate: $('#expectedBirthDate').value || null,
      birthDate: $('#birthDate').value || null,
      age: $('#age').value,
      breed: $('#breed').value.trim(),
      sex: $('#sex').value,
      owner: $('#owner').value.trim(),
      location: $('#location').value.trim(),
      notes: $('#notes').value.trim(),
    };
    if (stage === 'training') horse.workouts = $('#workouts').value;
    state.editing ? await api.updateHorse(state.editing, horse) : await api.createHorse(horse);
    $('#horseModal').close();
    await loadHorses();
    toast(state.editing ? 'Cadastro atualizado com sucesso.' : 'Cadastro realizado com sucesso.');
    } catch (error) {
      if (!$('#horseModal').open) $('#horseModal').showModal();
      $('#horseError').textContent = error.message;
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = 'Salvar';
    }
  };
  if (duplicate) {
    $('#horseModal').close();
    ask(
      'Nome já cadastrado',
      'Já existe um cavalo chamado ' + duplicate.name + '. Você realmente quer cadastrar dois cavalos com o mesmo nome?',
      persistHorse,
      false,
      { yes: '✓ Sim', no: '✕ Não' },
      () => $('#horseModal').showModal(),
    );
    return;
  }
  await persistHorse();
});

$('#bornForm').addEventListener('submit', async event => {
  event.preventDefault();
  const id = $('#bornHorseId').value;
  const birthDate = $('#actualBirthDate').value;
  const button = $('#confirmBorn');
  $('#bornError').textContent = '';
  if (!birthDate) return void ($('#bornError').textContent = 'Informe a data real de nascimento.');
  button.disabled = true;
  try {
    await api.transition(id, 'foals', { birthDate, name: $('#bornName').value.trim() });
    $('#bornModal').close();
    await loadHorses();
    toast('Nascimento confirmado. O animal foi enviado para Potros e Desenvolvimento.');
  } catch (error) {
    $('#bornError').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$('#horseGrid').addEventListener('click', async event => {
  const button = event.target.closest('button[data-action]');
  if (!button) {
    const card = event.target.closest('[data-horse-id]');
    const selected = card && state.horses.find(item => item.id === card.dataset.horseId);
    if (selected) openHorseDetails(selected);
    return;
  }
  const horse = state.horses.find(item => item.id === button.dataset.id);
  if (!horse) return;
  const action = button.dataset.action;
  if (action === 'edit') return openEdit(horse.id);
  if (action === 'born') return openBorn(horse);
  if (action === 'delete') return ask('Excluir cadastro', 'Tem certeza de que deseja excluir ' + (horse.name || 'esta cruza') + '? Essa ação não poderá ser desfeita.', async () => {
    await api.deleteHorse(horse.id);
    await loadHorses();
    toast('Cadastro excluído.');
  }, true);
  if (action === 'previous-stage') {
    const target = button.dataset.target;
    const destination = STAGES[target]?.title || 'a etapa anterior';
    return ask('Voltar para a etapa anterior', 'Deseja mover ' + horse.name + ' para ' + destination + '? Todos os dados e treinos serão preservados.', async () => {
      await api.transition(horse.id, target);
      await loadHorses();
      toast(horse.name + ' voltou para ' + destination + '.');
    });
  }
  if (action === 'to-training') return ask('Iniciar treinamento', 'Deseja mover ' + horse.name + ' para Preparação e Treinamento?', async () => {
    await api.transition(horse.id, 'training');
    await loadHorses();
    toast(horse.name + ' foi enviado para treinamento.');
  });
  if (action === 'to-ready') return ask('Enviar para tropa pronta', 'Confirma que ' + horse.name + ' está pronto para torneio?', async () => {
    await api.transition(horse.id, 'ready');
    await loadHorses();
    celebrate();
    toast(horse.name + ' agora faz parte da Tropa pronta.');
  });
  if (action === 'workout-plus' || action === 'workout-minus') return guarded(button, async () => {
    const before = Number(horse.workouts) || 0;
    await api.changeWorkout(horse.id, action === 'workout-plus' ? 1 : -1);
    await loadHorses();
    toast(action === 'workout-plus' ? 'Treino registrado.' : 'Contagem corrigida.');
    if (action === 'workout-plus' && before === 59) celebrate();
  });
});

$('#horseGrid').addEventListener('keydown', event => {
  if (!['Enter', ' '].includes(event.key) || event.target.closest('button')) return;
  const card = event.target.closest('[data-horse-id]');
  const horse = card && state.horses.find(item => item.id === card.dataset.horseId);
  if (!horse) return;
  event.preventDefault();
  openHorseDetails(horse);
});
document.querySelectorAll('.detail-close').forEach(button => button.addEventListener('click', () => $('#horseDetailsModal').close()));
$('#horseDetailsBody').addEventListener('click', event => {
  if (!event.target.closest('[data-complete-details]')) return;
  const id = $('#detailEdit').dataset.id;
  $('#horseDetailsModal').close();
  openEdit(id, true);
});
$('#detailEdit').addEventListener('click', event => {
  const id = event.currentTarget.dataset.id;
  $('#horseDetailsModal').close();
  openEdit(id);
});
$('#detailShare').addEventListener('click', async event => {
  const button = event.currentTarget;
  const horse = state.horses.find(item => item.id === $('#detailEdit').dataset.id);
  if (!horse) return toast('Não foi possível localizar este cadastro.', true);
  const label = button.querySelector('span');
  const original = label.textContent;
  button.disabled = true;
  label.textContent = 'Preparando cartão…';
  try {
    await shareHorse(horse);
  } catch (shareError) {
    if (shareError?.name !== 'AbortError') toast(shareError.message || 'Não foi possível compartilhar o cartão.', true);
  } finally {
    button.disabled = false;
    label.textContent = original;
  }
});

$('#addExpense').addEventListener('click', () => openExpenseForm());
document.querySelectorAll('.expense-close').forEach(button => button.addEventListener('click', () => $('#expenseModal').close()));
$('#expenseForm').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('#saveExpense');
  const expense = {
    amount: $('#expenseAmount').value.trim(),
    date: $('#expenseDate').value,
    category: $('#expenseCategory').value,
    scope: 'general',
    horseId: '',
    description: $('#expenseDescription').value.trim(),
    recurring: $('#expenseRecurring').checked,
  };
  $('#expenseError').textContent = '';
  if (!expense.amount) return void ($('#expenseError').textContent = 'Informe o valor da despesa.');
  if (!expense.date) return void ($('#expenseError').textContent = 'Informe a data da despesa.');
  button.disabled = true;
  button.textContent = 'Salvando…';
  try {
    state.editingExpense ? await api.updateExpense(state.editingExpense, expense) : await api.createExpense(expense);
    $('#expenseModal').close();
    state.costMonth = expense.date.slice(0, 7);
    await loadExpenses();
    toast(state.editingExpense ? 'Despesa atualizada.' : 'Despesa adicionada.');
    state.editingExpense = null;
  } catch (error) {
    $('#expenseError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = 'Salvar despesa';
  }
});

$('#smartExpense').addEventListener('click', () => {
  $('#smartExpenseForm')?.reset();
  $('#smartExpenseError').textContent = '';
  $('#smartExpenseModal').showModal();
  $('#smartExpenseText').focus();
});
document.querySelectorAll('.smart-expense-close').forEach(button => button.addEventListener('click', () => $('#smartExpenseModal').close()));
$('#smartExpenseForm').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('#interpretExpense');
  const text = $('#smartExpenseText').value.trim();
  $('#smartExpenseError').textContent = '';
  if (!text) return void ($('#smartExpenseError').textContent = 'Descreva a despesa.');
  button.disabled = true;
  button.textContent = 'Organizando…';
  try {
    const result = await api.parseExpense(text);
    $('#smartExpenseModal').close();
    applyExpenseDraft(result.draft, result.issues || []);
  } catch (error) {
    $('#smartExpenseError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = 'Organizar lançamento';
  }
});

$('#importExpenses').addEventListener('click', () => {
  state.costImportPreview = [];
  $('#costSpreadsheetFile').value = '';
  $('#costNotesText').value = '';
  $('#costNotesFile').value = '';
  setCostImportMethod('spreadsheet');
  $('#costImportModal').showModal();
});
document.querySelectorAll('.cost-import-close').forEach(button => button.addEventListener('click', () => $('#costImportModal').close()));
document.querySelectorAll('[data-cost-import-method]').forEach(button => button.addEventListener('click', () => setCostImportMethod(button.dataset.costImportMethod)));
$('#costNotesFile').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 1024 * 1024) return void ($('#costImportError').textContent = 'O arquivo de anotações deve ter no máximo 1 MB.');
  $('#costNotesText').value = await file.text();
});
$('#analyzeCostSpreadsheet').addEventListener('click', async event => {
  const file = $('#costSpreadsheetFile').files[0];
  if (!file) return void ($('#costImportError').textContent = 'Escolha uma planilha Excel ou CSV.');
  if (file.size > 8 * 1024 * 1024) return void ($('#costImportError').textContent = 'A planilha deve ter no máximo 8 MB.');
  try {
    await previewCostImport({ sourceType: 'spreadsheet', filename: file.name, contentBase64: await fileAsBase64(file) }, event.currentTarget);
  } catch (error) {
    $('#costImportError').textContent = error.message;
  }
});
$('#analyzeCostNotes').addEventListener('click', event => previewCostImport({ sourceType: 'notes', text: $('#costNotesText').value }, event.currentTarget));
$('#backCostImport').addEventListener('click', () => setCostImportMethod('spreadsheet'));
$('#confirmCostImport').addEventListener('click', async event => {
  const records = [...document.querySelectorAll('[data-cost-import-index]')].filter(card => card.querySelector('[data-cost-import-select]').checked).map(card => {
    const value = field => card.querySelector(`[data-cost-field="${field}"]`);
    return {
      amount: value('amount').value.trim(),
      date: value('date').value,
      category: value('category').value,
      description: value('description').value.trim(),
      recurring: value('recurring').checked,
      scope: 'general',
      horseId: '',
      importOrigin: state.costImportPreview[Number(card.dataset.costImportIndex)]?.importOrigin || 'Importação',
    };
  });
  if (!records.length) return void ($('#costImportError').textContent = 'Selecione pelo menos uma despesa.');
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = 'Salvando…';
  try {
    const result = await api.commitExpenseImport(records);
    $('#costImportModal').close();
    await loadExpenses();
    toast(`${result.imported} ${result.imported === 1 ? 'despesa importada' : 'despesas importadas'}.`);
  } catch (error) {
    $('#costImportError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = 'Salvar selecionadas';
  }
});

$('#costMonth').addEventListener('change', event => { state.costMonth = event.target.value || localIsoDate().slice(0, 7); renderCosts(); });
$('#previousCostMonth').addEventListener('click', () => { state.costMonth = monthOffset(state.costMonth, -1); renderCosts(); });
$('#nextCostMonth').addEventListener('click', () => { state.costMonth = monthOffset(state.costMonth, 1); renderCosts(); });
$('#costList').addEventListener('click', event => {
  const button = event.target.closest('[data-cost-action]');
  if (!button) return;
  const expense = state.expenses.find(item => item.id === button.dataset.id);
  if (!expense) return;
  if (button.dataset.costAction === 'edit') return openExpenseForm(expense);
  ask('Excluir despesa', 'Deseja excluir esta despesa de ' + money(expense.amountCents) + '?', async () => {
    await api.deleteExpense(expense.id);
    await loadExpenses();
    toast('Despesa excluída.');
  }, true, { yes: 'Excluir', no: 'Cancelar' });
});

initializeQuickCapture({
  api,
  getStage: () => state.stage,
  reload: loadHorses,
  toast,
});

async function start() {
  try {
    const bootstrap = await api.bootstrap();
    bootstrap.session?.authenticated ? await showApp(bootstrap) : showAuth(bootstrap.session);
  } catch {
    showAuth({ setupRequired: false, authenticated: false, email: null });
    $('#authError').textContent = 'Não foi possível conectar ao servidor.';
  }
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
}

function updateAssistantButton() {
  $('#openAssistant')?.classList.toggle('is-compact', window.scrollY > 140);
}
window.addEventListener('scroll', updateAssistantButton, { passive: true });
updateAssistantButton();

start();
