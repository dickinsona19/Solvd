/* The sign-in form.

   There is no server, so this checks the credentials against the table in
   session.js and sets a flag. It is a facade. Read the warning there before
   assuming it protects anything. */

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

form.addEventListener('submit', (event) => {
  event.preventDefault()
  error.hidden = true

  const username = form.username.value.trim()
  const password = form.password.value

  if (!username || !password) {
    fail('Enter an account and a password.')
    return
  }

  if (!signIn(username, password)) {
    // Deliberately does not say which half was wrong, which is the one habit
    // from real auth worth keeping here.
    fail('That account and password do not match.')
    form.password.value = ''
    form.password.focus()
    return
  }

  window.location.assign(DASHBOARD)
})
