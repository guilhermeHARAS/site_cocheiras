async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
  } catch {
    throw new Error('Não foi possível conectar ao servidor. Verifique sua internet e tente novamente.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || 'Não foi possível concluir a operação.');
    error.status = response.status;
    throw error;
  }
  return data;
}

async function download(path) {
  let response;
  try {
    response = await fetch(path, { credentials: 'include' });
  } catch {
    throw new Error('Não foi possível conectar ao servidor para gerar o relatório.');
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Não foi possível gerar o relatório.');
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return { blob: await response.blob(), filename: match?.[1] || 'relatorio' };
}

function mutationOptions(method, payload) {
  const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  return {
    method,
    headers: { 'Idempotency-Key': requestId },
    body: JSON.stringify(payload || {}),
  };
}

export const api = {
  session: () => request('/api/session'),
  signup: (email, password) => request('/api/signup', { method: 'POST', body: JSON.stringify({ email, password }) }),
  login: (email, password) => request('/api/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => request('/api/logout', { method: 'POST', body: '{}' }),
  account: () => request('/api/account'),
  addAccountEmail: (email, password) => request('/api/account/emails', { method: 'POST', body: JSON.stringify({ email, password }) }),
  removeAccountEmail: email => request(`/api/account/emails/${encodeURIComponent(email)}`, { method: 'DELETE' }),
  changePassword: (currentPassword, newPassword) => request('/api/account/password', { method: 'POST', body: JSON.stringify({ currentPassword, newPassword }) }),
  horses: () => request('/api/horses'),
  expenses: () => request('/api/expenses'),
  createExpense: expense => request('/api/expenses', mutationOptions('POST', expense)),
  updateExpense: (id, expense) => request(`/api/expenses/${id}`, { method: 'PUT', body: JSON.stringify(expense) }),
  deleteExpense: id => request(`/api/expenses/${id}`, { method: 'DELETE' }),
  parseExpense: text => request('/api/expenses/parse', { method: 'POST', body: JSON.stringify({ text }) }),
  previewExpenseImport: payload => request('/api/expenses/import/preview', { method: 'POST', body: JSON.stringify(payload) }),
  commitExpenseImport: records => request('/api/expenses/import/commit', mutationOptions('POST', { records })),
  askAssistant: (question, context = {}) => request('/api/assistant', { method: 'POST', body: JSON.stringify({ question, context }) }),
  downloadFinancialReport: (format, period) => download(`/api/reports/financial.${encodeURIComponent(format)}?period=${encodeURIComponent(period)}`),
  previewImport: payload => request('/api/import/preview', { method: 'POST', body: JSON.stringify(payload) }),
  commitImport: records => request('/api/import/commit', mutationOptions('POST', { records })),
  createHorse: horse => request('/api/horses', mutationOptions('POST', horse)),
  updateHorse: (id, horse) => request(`/api/horses/${id}`, { method: 'PUT', body: JSON.stringify(horse) }),
  deleteHorse: id => request(`/api/horses/${id}`, { method: 'DELETE' }),
  changeWorkout: (id, delta) => request(`/api/horses/${id}/workouts`, mutationOptions('POST', { delta })),
  transition: (id, target, details = {}) => request(`/api/horses/${id}/transition`, mutationOptions('POST', { target, ...details })),
};
