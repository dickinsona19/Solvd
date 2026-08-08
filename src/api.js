import { apiUrl } from './api-config.js'
import { currentSession, signOut } from './session.js'

export async function apiRequest(path, options = {}) {
  const session = currentSession()
  const headers = new Headers(options.headers || {})
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (session?.token) headers.set('Authorization', `Bearer ${session.token}`)

  const response = await fetch(apiUrl(path), { ...options, headers })
  if (response.status === 401) {
    signOut()
    if (!location.pathname.startsWith('/login')) location.replace('/login/')
    throw new Error('Your session expired. Sign in again.')
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const payload = await response.json()
      if (payload.detail) message = payload.detail
    } catch {
      // The status is still useful when the server did not return JSON.
    }
    throw new Error(message)
  }
  return response.status === 204 ? null : response.json()
}
