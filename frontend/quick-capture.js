const STAGE_LABELS = { creation: 'Reprodução', foals: 'Potros e Desenvolvimento', training: 'Preparação e Treinamento', ready: 'Tropa pronta' };
const $ = selector => document.querySelector(selector);

function escapeHtml(value) {
  const node = document.createElement('span');
  node.textContent = String(value ?? '');
  return node.innerHTML;
}

function fileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Não foi possível ler o arquivo.'));
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.readAsDataURL(file);
  });
}

function setBusy(button, busy, label) {
  if (!button.dataset.label) button.dataset.label = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? label : button.dataset.label;
}

function field(label, name, value, type = 'text', extra = '') {
  return `<label class="field"><span>${label}</span><input data-field="${name}" type="${type}" value="${escapeHtml(value ?? '')}" ${extra}></label>`;
}

function stageOptions(selected) {
  return Object.entries(STAGE_LABELS).map(([value, label]) => `<option value="${value}" ${value === selected ? 'selected' : ''}>${label}</option>`).join('');
}

export function initializeQuickCapture({ api, getStage, reload, toast }) {
  let preview = [];
  let documentUrl = '';
  const captureModal = $('#quickCaptureModal');
  const reviewModal = $('#importReviewModal');

  function error(message = '') { $('#captureError').textContent = message; }

  function selectMethod(method) {
    document.querySelectorAll('.capture-method').forEach(button => button.classList.toggle('is-active', button.dataset.capture === method));
    document.querySelectorAll('.capture-panel').forEach(panel => { panel.hidden = panel.dataset.panel !== method; });
    error('');
  }

  function renderReview(result) {
    preview = result.records || [];
    const ready = preview.filter(record => record.selected).length;
    const attention = preview.length - ready;
    $('#importSummary').innerHTML = `<strong>${preview.length} ${preview.length === 1 ? 'registro encontrado' : 'registros encontrados'}</strong><span>${ready} pronto(s) para salvar${attention ? ` · ${attention} precisam de conferência` : ''}</span>`;
    const warnings = result.warnings || [];
    $('#importWarnings').hidden = !warnings.length;
    $('#importWarnings').textContent = warnings.join(' ');
    $('#importRecords').innerHTML = preview.map((record, index) => {
      const alerts = [...(record.issues || [])];
      if (record.duplicate) alerts.push(`Possível duplicado de “${record.duplicate}”`);
      return `<article class="import-record ${alerts.length ? 'needs-review' : ''}" data-index="${index}">
        <div class="import-record__head">
          <label class="import-select"><input data-select type="checkbox" ${record.selected ? 'checked' : ''}><span>Importar</span></label>
          <span class="import-origin">${escapeHtml(record.importOrigin || '')}</span>
        </div>
        ${alerts.length ? `<p class="import-alert">${escapeHtml(alerts.join(' · '))}</p>` : ''}
        <div class="import-record__grid">
          ${field('Nome', 'name', record.name, 'text', 'maxlength="80"')}
          <label class="field"><span>Etapa</span><select data-field="stage">${stageOptions(record.stage)}</select></label>
          ${field('Pai', 'father', record.father, 'text', 'maxlength="80"')}
          ${field('Mãe', 'mother', record.mother, 'text', 'maxlength="80"')}
          ${field('Nascimento', 'birthDate', record.birthDate, 'date')}
          ${field('Idade em anos', 'age', record.age, 'number', 'min="0" max="60"')}
          ${field('Previsão de nascimento', 'expectedBirthDate', record.expectedBirthDate, 'date')}
          ${field('Treinos', 'workouts', record.workouts, 'number', 'min="0"')}
          ${field('Raça', 'breed', record.breed, 'text', 'maxlength="80"')}
          ${field('Sexo', 'sex', record.sex, 'text', 'maxlength="20"')}
          ${field('Proprietário', 'owner', record.owner, 'text', 'maxlength="100"')}
          ${field('Localização', 'location', record.location, 'text', 'maxlength="120"')}
          <label class="field field--wide"><span>Observações</span><textarea data-field="notes" maxlength="600">${escapeHtml(record.notes || '')}</textarea></label>
        </div>
        ${record.duplicate ? '<label class="duplicate-override"><input data-allow-duplicate type="checkbox"> Confirmo que é outro animal com dados semelhantes</label>' : ''}
      </article>`;
    }).join('');
    $('#importError').textContent = '';
    captureModal.close();
    reviewModal.showModal();
  }

  async function previewRequest(payload, button, loading) {
    error('');
    setBusy(button, true, loading);
    try {
      renderReview(await api.previewImport({ defaultStage: getStage() || 'training', ...payload }));
    } catch (failure) {
      error(failure.message);
    } finally {
      setBusy(button, false);
    }
  }

  $('#openQuickCapture').addEventListener('click', () => {
    selectMethod('spreadsheet');
    $('#captureError').textContent = '';
    captureModal.showModal();
  });
  document.querySelectorAll('.capture-method').forEach(button => button.addEventListener('click', () => selectMethod(button.dataset.capture)));
  document.querySelectorAll('.quick-close').forEach(button => button.addEventListener('click', () => captureModal.close()));
  document.querySelectorAll('.review-close').forEach(button => button.addEventListener('click', () => reviewModal.close()));

  $('#analyzeSpreadsheet').addEventListener('click', async event => {
    const file = $('#spreadsheetFile').files[0];
    if (!file) return error('Escolha uma planilha Excel ou CSV.');
    if (file.size > 8 * 1024 * 1024) return error('A planilha deve ter no máximo 8 MB.');
    try {
      await previewRequest({ sourceType: 'spreadsheet', filename: file.name, contentBase64: await fileAsBase64(file) }, event.currentTarget, 'Lendo planilha…');
    } catch (failure) { error(failure.message); }
  });

  $('#notesFile').addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    if (file.size > 1024 * 1024) return error('O arquivo de anotações deve ter no máximo 1 MB.');
    $('#notesImportText').value = await file.text();
  });
  $('#analyzeNotes').addEventListener('click', event => previewRequest({ sourceType: 'text', text: $('#notesImportText').value }, event.currentTarget, 'Organizando…'));
  $('#analyzeVoice').addEventListener('click', event => previewRequest({ sourceType: 'voice', text: $('#voiceText').value }, event.currentTarget, 'Organizando…'));

  $('#startDictation').addEventListener('click', event => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) return error('O ditado não é suportado neste navegador. No celular, use Chrome ou Edge.');
    const recognition = new Recognition();
    recognition.lang = 'pt-BR';
    recognition.continuous = false;
    recognition.interimResults = true;
    const button = event.currentTarget;
    let finalText = '';
    recognition.onstart = () => setBusy(button, true, 'Ouvindo… toque para aguardar');
    recognition.onresult = result => {
      let interim = '';
      for (let index = result.resultIndex; index < result.results.length; index++) {
        if (result.results[index].isFinal) finalText += result.results[index][0].transcript + ' ';
        else interim += result.results[index][0].transcript;
      }
      $('#voiceText').value = (finalText + interim).trim();
    };
    recognition.onerror = result => error(result.error === 'not-allowed' ? 'Autorize o uso do microfone no navegador.' : 'Não foi possível entender o áudio. Tente novamente.');
    recognition.onend = () => setBusy(button, false);
    recognition.start();
  });

  $('#documentPhoto').addEventListener('change', event => {
    const file = event.target.files[0];
    if (documentUrl) URL.revokeObjectURL(documentUrl);
    documentUrl = file ? URL.createObjectURL(file) : '';
    $('#documentPreview').innerHTML = documentUrl ? `<img src="${documentUrl}" alt="Documento selecionado">` : '';
    $('#ocrProgress').textContent = '';
  });

  async function loadOcr() {
    if (window.Tesseract) return window.Tesseract;
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
      script.onload = resolve;
      script.onerror = () => reject(new Error('Não foi possível carregar a leitura de documentos. Verifique a internet.'));
      document.head.append(script);
    });
    return window.Tesseract;
  }

  $('#analyzeDocument').addEventListener('click', async event => {
    const file = $('#documentPhoto').files[0];
    if (!file) return error('Fotografe ou escolha um documento.');
    const button = event.currentTarget;
    error('');
    setBusy(button, true, 'Lendo documento…');
    try {
      const Tesseract = await loadOcr();
      const result = await Tesseract.recognize(file, 'por', { logger: progress => {
        if (progress.status === 'recognizing text') $('#ocrProgress').textContent = `Leitura: ${Math.round((progress.progress || 0) * 100)}%`;
      }});
      const text = result?.data?.text?.trim();
      if (!text) throw new Error('Não foi possível encontrar texto na imagem. Tente uma foto mais nítida e bem iluminada.');
      renderReview(await api.previewImport({ sourceType: 'document', defaultStage: getStage() || 'training', text }));
    } catch (failure) {
      error(failure.message);
    } finally {
      setBusy(button, false);
    }
  });

  $('#confirmImport').addEventListener('click', async event => {
    const records = [...document.querySelectorAll('.import-record')].filter(card => card.querySelector('[data-select]').checked).map(card => {
      const original = preview[Number(card.dataset.index)] || {};
      const value = name => card.querySelector(`[data-field="${name}"]`)?.value ?? '';
      return {
        ...original,
        name: value('name').trim(), stage: value('stage'), father: value('father').trim(), mother: value('mother').trim(),
        birthDate: value('birthDate') || null, age: value('age'), expectedBirthDate: value('expectedBirthDate') || null,
        workouts: value('workouts'), breed: value('breed').trim(), sex: value('sex').trim(), owner: value('owner').trim(), location: value('location').trim(), notes: value('notes').trim(),
        allowDuplicate: Boolean(card.querySelector('[data-allow-duplicate]')?.checked),
      };
    });
    if (!records.length) return void ($('#importError').textContent = 'Selecione pelo menos um cadastro para salvar.');
    const button = event.currentTarget;
    $('#importError').textContent = '';
    setBusy(button, true, 'Salvando…');
    try {
      const result = await api.commitImport(records);
      reviewModal.close();
      await reload();
      toast(`${result.imported} ${result.imported === 1 ? 'cadastro importado' : 'cadastros importados'} com sucesso.`);
      if (result.skipped?.length) toast(`${result.skipped.length} linha(s) não foram importadas. Revise os dados.`, true);
    } catch (failure) {
      $('#importError').textContent = failure.message;
    } finally {
      setBusy(button, false);
    }
  });
}
