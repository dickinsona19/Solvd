export const API_BASE = String(import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export const apiUrl = (path) => `${API_BASE}${path}`
