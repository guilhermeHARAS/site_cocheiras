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

export const api = {
  session: () => request('/api/session'),
  signup: (email, password) => request('/api/signup', { method: 'POST', body: JSON.stringify({ email, password }) }),
  login: (email, password) => request('/api/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => request('/api/logout', { method: 'POST', body: '{}' }),
  horses: () => request('/api/horses'),
  createHorse: horse => request('/api/horses', { method: 'POST', body: JSON.stringify(horse) }),
  updateHorse: (id, horse) => request(`/api/horses/${id}`, { method: 'PUT', body: JSON.stringify(horse) }),
  deleteHorse: id => request(`/api/horses/${id}`, { method: 'DELETE' }),
  train: id => request(`/api/horses/${id}/train`, { method: 'POST', body: '{}' }),
  undo: id => request(`/api/horses/${id}/undo`, { method: 'POST', body: '{}' }),
};
