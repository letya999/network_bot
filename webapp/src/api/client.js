/**
 * API client for NetworkBot backend.
 * Automatically attaches Telegram initData for auth when available.
 */

const API_BASE = '/api/webapp'

let _initData = ''

export function setInitData(data) {
  _initData = data
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  // Attach Telegram auth
  if (_initData) {
    headers['X-Telegram-Init-Data'] = _initData
  }

  // Attach session token for web auth
  const token = localStorage.getItem('nb_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(url, { ...options, headers })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(res.status, body.detail || 'Request failed')
  }

  return res.json()
}

class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

// ========================
// Catalog / Public shares
// ========================

export async function getCatalog(limit = 20, offset = 0) {
  return request(`/catalog?limit=${limit}&offset=${offset}`)
}

export async function getShareByToken(token) {
  return request(`/share/${token}`)
}

export async function getShareById(shareId) {
  return request(`/share/id/${shareId}`)
}

// ========================
// User's shares
// ========================

export async function getMyShares() {
  return request('/my/shares')
}

export async function createShare(contactId, data) {
  return request('/my/shares', {
    method: 'POST',
    body: JSON.stringify({ contact_id: contactId, ...data }),
  })
}

export async function updateShare(shareId, data) {
  return request(`/my/shares/${shareId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteShare(shareId) {
  return request(`/my/shares/${shareId}`, { method: 'DELETE' })
}

// ========================
// Contacts
// ========================

export async function getMyContacts(limit = 50, offset = 0) {
  return request(`/my/contacts?limit=${limit}&offset=${offset}`)
}

export async function getContact(contactId) {
  return request(`/my/contacts/${contactId}`)
}

// ========================
// Purchases
// ========================

export async function getMyPurchases() {
  return request('/my/purchases')
}

export async function purchaseContact(shareId, provider = 'free') {
  return request('/purchase', {
    method: 'POST',
    body: JSON.stringify({ share_id: shareId, provider }),
  })
}

// ========================
// Subscription
// ========================

export async function getSubscription() {
  return request('/my/subscription')
}

export async function createSubscriptionPayment(provider = 'yookassa') {
  return request('/subscription/pay', {
    method: 'POST',
    body: JSON.stringify({ provider }),
  })
}

// ========================
// Profile
// ========================

export async function getProfile() {
  return request('/my/profile')
}

// ========================
// Admin
// ========================

export async function getAdminStats() {
  return request('/admin/stats')
}

export async function getAdminUsers(limit = 50) {
  return request(`/admin/users?limit=${limit}`)
}

export async function getAdminPayments(limit = 50) {
  return request(`/admin/payments?limit=${limit}`)
}
