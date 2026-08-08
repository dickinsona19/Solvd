/* The sign-in form. Credentials are checked by the API service, which returns
   a short-lived signed session token for subsequent account requests. */

import { currentSession, signIn } from './session.js'

const DASHBOARD = '/app/'

// Someone who is already signed in has no reason to see this form.
if (currentSession()) window.location.replace(DASHBOARD)

const form = document.getElementById('login-form')
const error = document.getElementById('login-error')

function fail(message) {
  error.textContent = message
  error.hidden = false
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  error.hidden = true

  const username = form.username.value.trim()
  const password = form.password.value

  if (!username || !password) {
    fail('Enter an account and a password.')
    return
  }

  const submit = form.querySelector('button[type="submit"]')
  submit.disabled = true
  submit.textContent = 'Opening portal…'

  let session = null
  try {
    session = await signIn(username, password)
  } catch {
    fail('The portal service is unavailable. Try again in a moment.')
    return
  } finally {
    submit.disabled = false
    submit.textContent = 'Open my portal'
  }

  if (!session) {
    fail('That account and password do not match.')
    form.password.value = ''
    form.password.focus()
    return
  }

  window.location.assign(DASHBOARD)
})
