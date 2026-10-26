import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { ageLabel } from '../frontend/lifecycle.js';

const root = fileURLToPath(new URL('..', import.meta.url));

test('idade exata respeita o aniversário', () => {
  assert.equal(ageLabel({ birthDate: '2023-10-20' }, new Date('2026-10-13T12:00:00')), '2 anos');
  assert.equal(ageLabel({ birthDate: '2023-10-10' }, new Date('2026-10-13T12:00:00')), '3 anos');
});

test('animal com menos de um ano aparece em meses', () => {
  assert.equal(ageLabel({ birthDate: '2026-04-13' }, new Date('2026-10-13T12:00:00')), '6 meses');
});

test('idade informada progride anualmente sem inventar nascimento', () => {
  const horse = { age: 3, ageRecordedAt: '2026-10-13', birthDate: null };
  assert.equal(ageLabel(horse, new Date('2027-10-12T12:00:00')), '3 anos');
  assert.equal(ageLabel(horse, new Date('2027-10-13T12:00:00')), '4 anos');
});

test('os quatro cartões usam os ícones PNG profissionais', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  for (const icon of ['cruzas-microscopio.png', 'potros-tropa-final-contorno-principal-2x.png', 'cavalo.png', 'polo-sem-dobras-camisa.png']) {
    assert.match(html, new RegExp(`/icons/${icon.replace('.', '\\.')}`));
    assert.equal(existsSync(`${root}/frontend/icons/${icon}`), true);
  }
});

test('ícones principais e dos cartões estão ampliados em quinze por cento', () => {
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(styles, /stage-menu \.stage-card__icon\{width:69px;height:69px\}/);
  assert.match(styles, /horse-identity__silhouette\{width:83px;height:106px\}/);
  assert.match(styles, /stage-menu \.stage-card__icon\{width:48px;height:48px[^}]*\}/);
});

test('configurações ficam no canto superior direito da barra', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(html, /topbar__actions[\s\S]*topbar-settings[\s\S]*id="openSettings"/);
  assert.match(styles, /topbar-settings \.settings-fab\{position:fixed;top:11px;right:/);
});

test('ícones diferentes recebem normalização óptica sem invadir os textos', () => {
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  for (const stage of ['creation', 'foals', 'training', 'ready']) {
    assert.match(styles, new RegExp(`data-stage="${stage}"\\] \\.stage-card__icon img\\{width:`));
  }
  assert.match(styles, /stage-card__quantity\{z-index:3\}/);
  assert.match(styles, /stage-card__name,[^}]+overflow-wrap:anywhere/);
});

test('ícone da tropa pronta mantém o contorno completo sem recorte', () => {
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(styles, /data-stage="ready"\] \.stage-card__icon\{overflow:visible\}/);
  assert.match(styles, /data-stage="ready"\] \.stage-card__icon img\{width:100%;height:100%;object-fit:contain\}/);
});

test('gerenciamento oferece fontes e tamanhos persistentes', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(html, /id="fontPreference"/);
  assert.match(html, /id="fontSizePreference" type="range"/);
  assert.match(html, /id="fontSizePreference"[^>]*max="160"/);
  assert.match(html, /id="manageAppearance"/);
  assert.match(html, /id="openSettings"/);
  assert.match(html, /id="settingsMenu"/);
  assert.match(html, /id="appearanceModal"/);
  assert.match(html, /DM\+Sans/);
  assert.match(app, /radames_appearance_v1/);
  assert.match(app, /localStorage\.setItem/);
  assert.match(styles, /data-font="professional"|--text:"DM Sans"/);
  assert.match(app, /--font-scale/);
  assert.match(app, /Math\.min\(160, Math\.max\(85/);
  assert.match(app, /font-size-expanded/);
  assert.match(styles, /font-size-control/);
  assert.match(styles, /Leitura ampliada/);
  assert.match(styles, /font-size-expanded \.stage-menu \.stage-card/);
  assert.match(styles, /settings-popover/);
});

test('custos aparecem abaixo das etapas com gráfico bruto e lançamento inteligente', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(html, /id="openCosts"/);
  assert.match(html, /id="costCategoryChart"/);
  assert.match(html, /id="smartExpense"/);
  assert.match(html, /id="importExpenses"/);
  assert.match(html, /id="expenseRecurring"/);
  assert.match(html, /id="costPerHorse"/);
  assert.match(html, /id="costHorseCount"/);
  assert.doesNotMatch(html, /Maior categoria/);
  assert.match(html, /id="costSpreadsheetFile"/);
  assert.match(html, /id="costNotesText"/);
  assert.doesNotMatch(html, /id="expenseHorse"|id="costHorseFilter"/);
  assert.match(app, /parseExpense/);
  assert.match(app, /scope: 'general'/);
  assert.match(app, /previewExpenseImport/);
  assert.match(app, /recurringProjection/);
  assert.match(app, /\['foals', 'training', 'ready'\]/);
  assert.match(styles, /\.finance-entry/);
  assert.match(styles, /\.costs-simple__sheet/);
});

test('cavalos são ordenados por nome e depois por idade', () => {
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  assert.match(app, /localeCompare\(String\(b\.name/);
  assert.match(app, /return ageB - ageA/);
});

test('cartões permitem voltar etapa e controles de treino têm textos claros', () => {
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  assert.match(app, /data-action="previous-stage"/);
  assert.match(app, />Voltar etapa</);
  assert.match(app, />Descontar treino</);
  assert.match(app, />Somar treino</);
  assert.match(app, /Todos os dados e treinos serão preservados/);
});

test('ficha detalhada não repete a etapa em uma etiqueta arredondada', () => {
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  assert.doesNotMatch(app, /class="horse-detail-stage"/);
});

test('assistente oferece memória, voz e downloads de relatório', () => {
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  assert.match(app, /assistantContext/);
  assert.match(app, /SpeechRecognition/);
  assert.match(app, /downloadFinancialReport/);
  assert.match(html, /assistantVoice/);
});

test('perguntas rápidas priorizam alertas e cobrem áreas diferentes', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  assert.ok(html.indexOf('Custos que aumentaram') < html.indexOf('Média por cavalo'));
  for (const area of ['ALERTA', 'AUDITORIA', 'PREVISÃO', 'RELATÓRIO', 'CUSTOS', 'TREINOS', 'NASCIMENTOS', 'FILIAÇÃO', 'ETAPAS']) {
    assert.match(html, new RegExp(`>${area}<`));
  }
  assert.match(html, /data-question=/);
});

test('cruzas usam cartões compactos com hierarquia de agenda', () => {
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(app, /creation-card__label/);
  assert.match(app, /creation-card__pair/);
  assert.match(app, /Registrar nascimento/);
  assert.doesNotMatch(app, /Nome previsto/);
  assert.match(app, /horse-grid--creation/);
  assert.match(styles, /\.horse-grid--creation/);
  assert.match(styles, /\.creation-card::before/);
  assert.match(styles, /\.creation-card__pair/);
});

test('reprodução simplificada, transferência permanece na etapa e celular não aplica zoom nos campos', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const capture = readFileSync(`${root}/frontend/quick-capture.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(html, /Data prevista de nascimento \(opcional\)/);
  assert.match(html, /class="field field--full only-born"/);
  assert.doesNotMatch(app, /state\.stage = '(?:foals|training|ready)'/);
  assert.match(capture, /Previsão de nascimento \(opcional\)/);
  assert.match(capture, /Drink x Juíza/);
  assert.match(styles, /input,select,textarea\{font-size:16px!important\}/);
  assert.match(styles, /\.creation-card__pair\{text-transform:uppercase\}/);
  assert.doesNotMatch(styles, /\.creation-card__pair,\s*\/\* Ações principais/);
});

test('contadores das etapas explicam que representam quantidades', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.equal((html.match(/stage-card__quantity/g) || []).length, 4);
  assert.equal((html.match(/<span>Quantidade<\/span>/g) || []).length, 4);
  assert.match(styles, /\.stage-card__quantity/);
  assert.match(styles, /\.stage-menu \.stage-card__step\{color:#afa99d/);
});

test('localização fica no cadastro e na ficha sem poluir os cartões', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(html, /id="location"/);
  assert.doesNotMatch(app, /function horseLocation/);
  assert.match(app, /optionalDetailItem\('Localização atual'/);
  assert.match(app, /horse\.location/);
  assert.doesNotMatch(styles, /\.horse-card__location/);
  assert.match(app, /horse-card__age/);
  assert.match(app, /Último treino:/);
});

test('cartões de treinamento usam o cavalo v6 exclusivo', () => {
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const serviceWorker = readFileSync(`${root}/frontend/sw.js`, 'utf8');
  const icon = `${root}/frontend/icons/cavalo-treinamento-v6.png`;
  assert.equal(existsSync(icon), true);
  assert.match(app, /training:\s*'\/icons\/cavalo-treinamento-v6\.png\?v=v6'/);
  assert.match(serviceWorker, /cavalo-treinamento-v6\.png\?v=v6/);
});

test('tropa pronta forma um grande cartão com cartões individuais', () => {
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(app, /function readyGroupHeader/);
  assert.match(app, /horse-grid--ready/);
  assert.match(app, /GRUPO DE COMPETIÇÃO/);
  assert.match(styles, /\.horse-grid--ready\{/);
  assert.match(styles, /\.ready-group__head\{/);
  assert.match(app, /polo-sem-dobras-camisa\.png/);
  assert.match(app, /potros-tropa-final-contorno-principal-2x\.png/);
  assert.match(app, /ready-inline-icon/);
  assert.match(app, /horseIdentityHeader\(horse, 'ready', 'TROPA PRONTA', 'TORNEIO'\)/);
  assert.match(styles, /\.horse-grid--ready\{[^}]*background:var\(--paper\)/);
  assert.doesNotMatch(styles, /\.horse-grid--ready\{[^}]*#eee8da/);
});

test('refinamento usa ícones vetoriais e renomeia o agente', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(html, />Agente de IA</);
  assert.match(html, /<h1>Gestão da Cocheira<\/h1>/);
  assert.match(html, /Potros e Desenvolvimento/);
  assert.match(html, /Preparação e Treinamento/);
  assert.match(html, /id="assistantVoice"[^>]*><svg class="ui-icon"/);
  assert.match(styles, /\.assistant__voice\{display:grid;place-items:center/);
  assert.match(html, /ui-icon-spreadsheet/);
  assert.match(html, /ui-icon-microphone/);
  for (const symbol of ['✦', '▦', '≡', '＋', '🎙', '◉', '▣']) assert.doesNotMatch(html, new RegExp(symbol));
  assert.match(app, /uiIcon\('plus'\)/);
  assert.match(styles, /\.ui-icon\{/);
  assert.match(styles, /\.assistant-fab\.is-compact/);
  assert.match(styles, /\.assistant-fab\.is-home\{position:static/);
  assert.match(app, /classList\.toggle\('is-home'/);
});

test('ficha oculta vazios e oferece completar cadastro', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(app, /function optionalDetailItem/);
  assert.match(app, /informações ainda não preenchidas/);
  assert.match(app, /data-complete-details/);
  assert.match(app, /openEdit\(id, true\)/);
  assert.match(html, /id="completionGuide"/);
  assert.match(styles, /data-stage="foals"\] \.optional-details\{display:grid\}/);
  assert.match(styles, /\.stage-menu \.stage-card\{display:grid;grid-template-rows/);
  assert.match(styles, /\.horse-detail-missing/);
  assert.match(styles, /\.horse-detail-summary\{display:flex;flex-wrap:wrap/);
  assert.match(styles, /\.horse-detail-pedigree \.horse-detail-item strong/);
  assert.match(styles, /\.modal__form>\.modal__actions\{position:sticky/);
  assert.match(styles, /\.horse-details\{[^}]*background:var\(--forest\)/);
  assert.match(styles, /\.horse-details__body\{background:[^}]*linear-gradient/);
  assert.match(styles, /\.horse-details \.horse-detail-item strong\{color:#fff\}/);
});

test('ficha gera cartão em PNG e compartilha pelo WhatsApp', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(html, /id="detailShare"/);
  assert.match(html, /ui-icon-share/);
  assert.match(app, /function horseShareFields/);
  assert.match(app, /createHorseShareCard/);
  assert.match(app, /canvas\.toBlob/);
  assert.match(app, /navigator\.canShare/);
  assert.match(app, /navigator\.share/);
  assert.match(app, /https:\/\/wa\.me\/\?text=/);
  assert.match(styles, /\.horse-details__actions \.button--share/);
});

test('ficha mantém ações visíveis e arquivos não escapam do cadastro rápido', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const styles = readFileSync(`${root}/frontend/styles.css`, 'utf8');
  assert.match(html, /styles\.css\?v=85/);
  assert.match(styles, /\.horse-details\[open\]\{display:flex;flex-direction:column/);
  assert.match(styles, /\.horse-details__body\{flex:0 1 auto;min-height:0;max-height:none;overflow-y:auto/);
  assert.match(styles, /\.horse-details__body\{grid-auto-flow:row;grid-auto-rows:max-content;align-content:start\}/);
  assert.match(styles, /\.horse-details__body>\*\{grid-column:1;min-width:0;position:relative\}/);
  assert.match(styles, /\.horse-detail-missing\{display:grid;grid-template-columns:minmax\(0,1fr\);align-items:start;gap:10px;overflow:visible\}/);
  assert.match(styles, /\.horse-details__actions\{position:relative;z-index:5/);
  assert.match(styles, /\.quick-capture\[open\]\{display:flex;flex-direction:column/);
  assert.match(styles, /\.upload-drop input\[type="file"\],\.capture-file input\[type="file"\]\{[^}]*width:100%/);
  assert.match(styles, /::file-selector-button/);
});

test('login não cria conta e cadastro exige identificação completa', () => {
  const html = readFileSync(`${root}/frontend/index.html`, 'utf8');
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const api = readFileSync(`${root}/frontend/api.js`, 'utf8');
  for (const field of ['authFirstName', 'authLastName', 'authEmail', 'authPassword']) {
    assert.match(html, new RegExp(`id="${field}"`));
  }
  assert.match(app, /signup \? await api\.signup\(firstName, lastName, email, password\) : await api\.login\(email, password\)/);
  assert.match(api, /signup: \(firstName, lastName, email, password\)/);
});

test('inicialização usa uma única chamada para sessão, cavalos e despesas', () => {
  const app = readFileSync(`${root}/frontend/app.js`, 'utf8');
  const api = readFileSync(`${root}/frontend/api.js`, 'utf8');
  assert.match(api, /bootstrap: \(\) => request\('\/api\/bootstrap'\)/);
  assert.match(app, /const bootstrap = await api\.bootstrap\(\)/);
  assert.match(app, /state\.horses = Array\.isArray\(bootstrap\.horses\)/);
  assert.match(app, /state\.expenses = Array\.isArray\(bootstrap\.expenses\)/);
  assert.doesNotMatch(app, /async function showApp\([^)]*\) \{[\s\S]{0,500}await loadHorses\(\)/);
});

