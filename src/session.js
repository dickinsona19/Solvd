/* Server-issued sessions for the client dashboard.

   The browser stores only a short-lived signed token. Credentials and token
   signing secrets live in the backend service, and every account/inbox API
   request is authorized there. The token is intentionally kept out of URLs
   and never sent to OpenAI. */

import { apiUrl } from './api-config.js'

const KEY = 'solvd.session'

export async function signIn(username, password) {
  const response = await fetch(apiUrl('/api/v1/session'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (response.status === 401) return null
  if (!response.ok) throw new Error(`Portal service returned ${response.status}`)

  const session = await response.json()
  try {
    sessionStorage.setItem(KEY, JSON.stringify(session))
  } catch {
    return null
  }
  return session
}

export function currentSession() {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const session = JSON.parse(raw)
    if (!session?.token || !session?.account || Number(session.exp) * 1000 <= Date.now()) {
      signOut()
      return null
    }
    return session
  } catch {
    return null
  }
}

export function signOut() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // Nothing to clean up if storage was never available.
  }
}
