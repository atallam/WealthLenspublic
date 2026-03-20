/**
 * WealthLens OSS — API Client
 * Handles all fetch calls with JWT auth headers.
 * Supports email/password + Google OAuth flows.
 */

const BASE = '';

let _token = localStorage.getItem('wl_token') || '';

export const setToken = (t) => { _token = t; localStorage.setItem('wl_token', t); };
export const getToken = () => _token;
export const clearToken = () => { _token = ''; localStorage.removeItem('wl_token'); localStorage.removeItem('wl_user'); };

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (_token) headers['Authorization'] = `Bearer ${_token}`;
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401) { clearToken(); window.location.reload(); throw new Error('Session expired'); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

export const api = {
  // Auth — email/password
  register: (d) => request('/api/auth/register', { method: 'POST', body: JSON.stringify(d) }),
  login: (d) => request('/api/auth/login', { method: 'POST', body: JSON.stringify(d) }),
  me: () => request('/api/auth/me'),

  // Auth — Google OAuth
  getGoogleClientId: () => request('/api/auth/google-client-id'),
  googleLogin: (id_token) => request('/api/auth/google', { method: 'POST', body: JSON.stringify({ id_token }) }),
  vaultSetup: (pin) => request('/api/auth/vault/setup', { method: 'POST', body: JSON.stringify({ pin }) }),
  vaultUnlock: (pin) => request('/api/auth/vault/unlock', { method: 'POST', body: JSON.stringify({ pin }) }),

  // Portfolio
  getPortfolio: () => request('/api/portfolio'),
  savePortfolio: (d) => request('/api/portfolio', { method: 'PUT', body: JSON.stringify(d) }),

  // Holdings
  getHoldings: () => request('/api/holdings'),
  createHolding: (d) => request('/api/holdings', { method: 'POST', body: JSON.stringify(d) }),
  updateHolding: (id, d) => request(`/api/holdings/${id}`, { method: 'PUT', body: JSON.stringify(d) }),
  deleteHolding: (id) => request(`/api/holdings/${id}`, { method: 'DELETE' }),

  // Transactions
  addTransaction: (d) => request('/api/transactions', { method: 'POST', body: JSON.stringify(d) }),
  getTransactions: (hid) => request(`/api/transactions/${hid}`),
  deleteTransaction: (tid) => request(`/api/transactions/${tid}`, { method: 'DELETE' }),

  // Market — MF (multi-source)
  mfSearch: (q) => request(`/api/mf/search?q=${encodeURIComponent(q)}`),
  mfAmfiSearch: (q) => request(`/api/mf/amfi/search?q=${encodeURIComponent(q)}`),
  mfNav: (code) => request(`/api/mf/nav/${code}`),
  mfSipNavs: (d) => request('/api/mf/sip-navs', { method: 'POST', body: JSON.stringify(d) }),
  manualNav: (d) => request('/api/mf/manual-nav', { method: 'POST', body: JSON.stringify(d) }),

  // Market — Stocks/FX
  stockInfo: (t) => request(`/api/stock/info/${encodeURIComponent(t)}`),
  etfSearch: (q) => request(`/api/etf/search?q=${encodeURIComponent(q)}`),
  forexUsdInr: () => request('/api/forex/usdinr'),
  refreshPrices: () => request('/api/prices/refresh', { method: 'POST' }),

  // AI
  aiChat: (d) => request('/api/ai/chat', { method: 'POST', body: JSON.stringify(d) }),

  // Budget
  budgetImport: (file, sourceHint, sourceName) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('source_hint', sourceHint || 'auto');
    fd.append('source_name', sourceName || '');
    return request('/api/budget/import', { method: 'POST', body: fd, headers: {} });
  },
  budgetImports: () => request('/api/budget/imports'),
  deleteBudgetImport: (id) => request(`/api/budget/imports/${id}`, { method: 'DELETE' }),
  budgetTransactions: (month, catId, type) => {
    const p = new URLSearchParams();
    if (month) p.set('month', month);
    if (catId) p.set('category_id', catId);
    if (type) p.set('txn_type', type);
    return request(`/api/budget/transactions?${p}`);
  },
  updateBudgetTxnCategory: (id, catId) => request(`/api/budget/transactions/${id}`, { method: 'PUT', body: JSON.stringify({ category_id: catId }) }),
  addManualBudgetTxn: (d) => request('/api/budget/transactions/manual', { method: 'POST', body: JSON.stringify(d) }),
  deleteBudgetTxn: (id) => request(`/api/budget/transactions/${id}`, { method: 'DELETE' }),
  budgetCategories: () => request('/api/budget/categories'),
  createBudgetCategory: (d) => request('/api/budget/categories', { method: 'POST', body: JSON.stringify(d) }),
  updateBudgetCategory: (id, d) => request(`/api/budget/categories/${id}`, { method: 'PUT', body: JSON.stringify(d) }),
  deleteBudgetCategory: (id) => request(`/api/budget/categories/${id}`, { method: 'DELETE' }),
  budgetBuckets: (month) => request(`/api/budget/buckets${month ? '?month=' + month : ''}`),
  setBudgetBucket: (d) => request('/api/budget/buckets', { method: 'POST', body: JSON.stringify(d) }),
  updateBudgetBucket: (id, d) => request(`/api/budget/buckets/${id}`, { method: 'PUT', body: JSON.stringify(d) }),
  deleteBudgetBucket: (id) => request(`/api/budget/buckets/${id}`, { method: 'DELETE' }),
  budgetSummary: (month) => request(`/api/budget/summary/${month}`),
  budgetCategorizeAI: (month) => request('/api/budget/categorize-ai', { method: 'POST', body: JSON.stringify({ month }) }),

  // Artifacts
  uploadArtifact: (holdingId, desc, file) => {
    const fd = new FormData();
    fd.append('holding_id', holdingId);
    fd.append('description', desc);
    fd.append('file', file);
    return request('/api/artifacts/upload', { method: 'POST', body: fd, headers: {} });
  },
  downloadArtifact: (id) => fetch(`${BASE}/api/artifacts/${id}`, { headers: { Authorization: `Bearer ${_token}` } }),
  deleteArtifact: (id) => request(`/api/artifacts/${id}`, { method: 'DELETE' }),
};
