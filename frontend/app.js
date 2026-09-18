import { api } from './api.js';

const GOAL = 60;
const $ = selector => document.querySelector(selector);
const state = { horses: [], filter: 'all', query: '', editing: null, pending: null, setupRequired: false };
let installPrompt = null;
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const formatDate = value => value ? new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC' }).format(new Date(`${value}T12:00:00Z`)) : 'Nenhum treino registrado';

function toast(message, error = false) {
  const item = document.createElement('div');
  item.className = `toast${error ? ' is-error' : ''}`;
  item.textContent = message;
  $('#toasts').append(item);
  setTimeout(() => item.remove(), 3500);
}

function showAuth(session) {
  state.setupRequired = session.setupRequired;
  $('#app').hidden = true;
  $('#auth').hidden = false;
  $('#authTitle').textContent = session.setupRequired ? 'Crie seu acesso' : 'Bem-vindo de volta';
  $('#authCopy').textContent = session.setupRequired ? 'Cadastre o acesso do responsável pela cocheira.' : 'Entre para acessar o controle da cocheira.';
  $('#authButton').textContent = session.setupRequired ? 'Criar acesso' : 'Entrar';
  $('#authNote').textContent = session.setupRequired ? 'A senha é protegida e armazenada somente neste computador.' : 'Ambiente reservado à equipe da Cocheira RADAMÉS.';
  $('#authEmail').value = session.email || '';
  $('#authPassword').value = '';
  $('#authError').textContent = '';
}

async function showApp() {
  $('#auth').hidden = true;
  $('#app').hidden = false;
  await loadHorses();
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

function horseCard(horse) {
  const done = horse.workouts >= GOAL;
  const percentage = Math.round((horse.workouts / GOAL) * 100);
  const safePercentage = Math.min(100, Math.max(0, percentage));
  const pedigree = [horse.father, horse.mother].filter(Boolean).map(escapeHtml).join(' × ');
  return `<article class="horse-card${done ? ' is-done' : ''}">
    <div class="horse-card__photo">${horse.photo ? `<img src="${horse.photo}" alt="Foto de ${escapeHtml(horse.name)}">` : '<span>R</span>'}</div>
    <div class="horse-card__body">
      <h2>${escapeHtml(horse.name)}${done ? '<span class="star">★</span>' : ''}</h2>
      <p class="horse-card__breed">${escapeHtml(horse.breed || 'Raça não informada')}</p>
      ${pedigree ? `<p class="horse-card__pedigree"><span>Filiação</span>${pedigree}</p>` : ''}
      <div class="horse-card__count">${done ? `★ Meta alcançada — ${horse.workouts}` : `${horse.workouts} treinos de ${GOAL}`}</div>
      <div class="progress"><span style="width:${safePercentage}%"></span></div>
      <div class="horse-card__meta"><span>${percentage}% da meta</span>${done ? '<b>Concluída</b>' : ''}</div>
      <p class="horse-card__date">Último treino: ${formatDate(horse.lastWorkout)}</p>
      <button class="button button--primary" data-action="train" data-id="${horse.id}">＋ Registrar treino</button>
      <button class="button button--soft" data-action="undo" data-id="${horse.id}" ${horse.workouts < 1 ? 'disabled' : ''}>Desfazer último</button>
      <div class="card-actions"><button data-action="edit" data-id="${horse.id}">Editar</button><button data-action="delete" data-id="${horse.id}">Excluir</button></div>
    </div>
  </article>`;
}

function render() {
  $('#total').textContent = state.horses.length;
  $('#goals').textContent = state.horses.filter(h => h.workouts >= GOAL).length;
  const query = state.query.trim().toLocaleLowerCase('pt-BR');
  let list = state.horses.filter(h => [h.name, h.father, h.mother].some(value => String(value || '').toLocaleLowerCase('pt-BR').includes(query)));
  if (state.filter === 'training') list = list.filter(h => h.workouts < GOAL);
  if (state.filter === 'goal') list = list.filter(h => h.workouts >= GOAL);
  $('#horseGrid').innerHTML = list.length
    ? list.map(horseCard).join('')
    : `<div class="empty"><strong>${state.horses.length ? 'Nenhum cavalo encontrado' : 'Nenhum cavalo cadastrado'}</strong><span>${state.horses.length ? 'Tente outro nome ou filtro.' : 'Adicione o primeiro cavalo para começar.'}</span></div>`;
}

function clearForm() {
  $('#horseForm').reset();
  $('#workouts').value = 0;
  $('#photo').dataset.current = '';
  $('#photoPreview').innerHTML = '';
  $('#horseError').textContent = '';
  $('#duplicateNotice').hidden = true;
  delete $('#saveHorse').dataset.confirmDuplicate;
}

function openCreate() {
  state.editing = null;
  clearForm();
  $('#modalTitle').textContent = 'Novo cavalo';
  $('#horseModal').showModal();
}

function openEdit(id) {
  const horse = state.horses.find(h => h.id === id);
  if (!horse) return;
  state.editing = id;
  clearForm();
  $('#modalTitle').textContent = 'Editar cavalo';
  ['name', 'breed', 'sex', 'owner', 'father', 'mother', 'notes'].forEach(key => $(`#${key}`).value = horse[key] || '');
  $('#age').value = horse.age ?? '';
  $('#workouts').value = horse.workouts;
  $('#photo').dataset.current = horse.photo || '';
  previewPhoto(horse.photo);
  $('#horseModal').showModal();
}

function previewPhoto(source) {
  $('#photoPreview').innerHTML = source ? `<img src="${source}" alt="Prévia"><button class="button button--soft" id="removePhoto" type="button">Remover foto</button>` : '';
  $('#removePhoto')?.addEventListener('click', () => { $('#photo').value = ''; $('#photo').dataset.current = ''; previewPhoto(''); });
}

function readPhoto(file) {
  return new Promise((resolve, reject) => {
    if (!file) return resolve($('#photo').dataset.current || '');
    if (file.size > 2_621_440) return reject(new Error('A foto deve ter no máximo 2,5 MB.'));
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Não foi possível ler a foto.'));
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
}

function ask(title, text, callback) {
  state.pending = callback;
  $('#confirmTitle').textContent = title;
  $('#confirmText').textContent = text;
  $('#confirmModal').showModal();
}

function celebrate() {
  const colors = ['#c89d4a', '#efd183', '#102f24', '#fff', '#a95e45'];
  for (let index = 0; index < 52; index++) {
    const piece = document.createElement('i');
    piece.style.left = `${Math.random() * 100}vw`;
    piece.style.background = colors[index % colors.length];
    piece.style.setProperty('--dx', `${Math.random() * 170 - 85}px`);
    piece.style.animationDelay = `${Math.random() * .3}s`;
    $('#confetti').append(piece);
  }
  setTimeout(() => $('#confetti').replaceChildren(), 2200);
}

$('#authForm').addEventListener('submit', async event => {
  event.preventDefault();
  const email = $('#authEmail').value.trim();
  const password = $('#authPassword').value;
  const button = $('#authButton');
  $('#authError').textContent = '';
  if (!/^\S+@\S+\.\S+$/.test(email)) return void ($('#authError').textContent = 'Informe um e-mail válido.');
  if (password.length < 6) return void ($('#authError').textContent = 'A senha precisa ter pelo menos 6 caracteres.');
  button.disabled = true;
  button.textContent = 'Aguarde…';
  try {
    state.setupRequired ? await api.setup(email, password) : await api.login(email, password);
    await showApp();
    toast(state.setupRequired ? 'Acesso criado com sucesso.' : 'Login realizado com sucesso.');
  } catch (error) {
    $('#authError').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = state.setupRequired ? 'Criar acesso' : 'Entrar';
  }
});

$('#logout').addEventListener('click', async () => { await api.logout(); showAuth(await api.session()); });
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
document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.filter').forEach(item => item.classList.remove('is-active'));
  button.classList.add('is-active'); state.filter = button.dataset.filter; render();
}));
document.querySelectorAll('.modal-close').forEach(button => button.addEventListener('click', () => $('#horseModal').close()));
document.querySelectorAll('.confirm-close').forEach(button => button.addEventListener('click', () => { state.pending = null; $('#confirmModal').close(); }));
$('#confirmYes').addEventListener('click', async () => { const callback = state.pending; state.pending = null; $('#confirmModal').close(); await callback?.(); });
$('#photo').addEventListener('change', async event => { try { previewPhoto(await readPhoto(event.target.files[0])); } catch (error) { event.target.value = ''; $('#horseError').textContent = error.message; } });

$('#horseForm').addEventListener('submit', async event => {
  event.preventDefault();
  const name = $('#name').value.trim();
  const saveButton = $('#saveHorse');
  const duplicate = state.horses.find(h => h.id !== state.editing && h.name.trim().toLocaleLowerCase('pt-BR') === name.toLocaleLowerCase('pt-BR'));
  $('#horseError').textContent = '';
  if (!name) return void ($('#horseError').textContent = 'Informe o nome do cavalo.');
  if (duplicate && !saveButton.dataset.confirmDuplicate) {
    $('#duplicateNotice').textContent = `Já existe um cavalo chamado ${duplicate.name}. Clique novamente em “Salvar cavalo” para confirmar.`;
    $('#duplicateNotice').hidden = false;
    saveButton.dataset.confirmDuplicate = '1';
    return;
  }
  saveButton.disabled = true;
  saveButton.textContent = 'Salvando…';
  try {
    const horse = { name, photo: await readPhoto($('#photo').files[0]), breed: $('#breed').value.trim(), age: $('#age').value, sex: $('#sex').value, owner: $('#owner').value.trim(), father: $('#father').value.trim(), mother: $('#mother').value.trim(), workouts: $('#workouts').value, notes: $('#notes').value.trim() };
    state.editing ? await api.updateHorse(state.editing, horse) : await api.createHorse(horse);
    $('#horseModal').close();
    await loadHorses();
    toast(state.editing ? `${name} atualizado com sucesso.` : `${name} cadastrado com sucesso.`);
  } catch (error) {
    $('#horseError').textContent = error.message;
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = 'Salvar cavalo';
    delete saveButton.dataset.confirmDuplicate;
  }
});

$('#horseGrid').addEventListener('click', async event => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const horse = state.horses.find(h => h.id === button.dataset.id);
  if (!horse) return;
  if (button.dataset.action === 'edit') return openEdit(horse.id);
  if (button.dataset.action === 'delete') return ask('Excluir cavalo', `Tem certeza de que deseja excluir ${horse.name}? Essa ação não poderá ser desfeita.`, async () => { await api.deleteHorse(horse.id); await loadHorses(); toast(`${horse.name} excluído.`); });
  if (button.dataset.action === 'undo') return ask('Desfazer último treino', `Deseja desfazer o último treino de ${horse.name}?`, async () => { await api.undo(horse.id); await loadHorses(); toast(`Último treino de ${horse.name} desfeito.`); });
  if (button.dataset.action === 'train') {
    const before = horse.workouts;
    await api.train(horse.id);
    await loadHorses();
    toast(`Treino de ${horse.name} registrado com sucesso.`);
    if (before === 59) celebrate();
  }
});

async function start() {
  try {
    const session = await api.session();
    session.authenticated ? await showApp() : showAuth(session);
  } catch {
    showAuth({ setupRequired: false, authenticated: false, email: null });
    $('#authError').textContent = 'Não foi possível conectar ao servidor.';
  }
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
}

start();
