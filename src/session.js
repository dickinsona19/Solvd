/* Sign-in for the client dashboard.

   READ THIS BEFORE SHIPPING. This is not authentication. The credentials are
   in the table below, which means they are in the JavaScript bundle, which
   means anyone can read them with view-source. The session is a flag in
   sessionStorage that any visitor can set themselves, and /app/ is a static
   page that will render for anyone who asks for it, logged in or not.

   It is a facade good enough to demo a per-tenant dashboard and nothing more.
   Real multi-tenant auth needs a server that holds the password hashes, issues
   a session cookie, and only ever sends a client the rows they own. Until that
   exists, do not put a real gym's data in accounts/. */

const KEY = 'solvd.session'

const ACCOUNTS = {
  test: { password: '1234', account: 'test', label: 'Northside Barbell' },
}

export function signIn(username, password) {
  const record = ACCOUNTS[String(username).trim().toLowerCase()]
  if (!record || record.password !== password) return null

  const session = { account: record.account, label: record.label, at: Date.now() }
  try {
    sessionStorage.setItem(KEY, JSON.stringify(session))
  } catch {
    // Private browsing can refuse storage. The sign-in still "works" for this
    // page load; the next one will bounce back to the form.
  }
  return session
}

export function currentSession() {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    const session = JSON.parse(raw)
    return session && ACCOUNTS[session.account] ? session : null
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
