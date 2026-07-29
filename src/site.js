/* Progressive enhancement only. With JS disabled (or reduced motion)
   the page renders complete and static; nothing below is required. */

const docEl = document.documentElement
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches

/* ---------- brand intro ---------- */

const intro = document.getElementById('intro')

function storageGet(key) {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function storageSet(key, value) {
  try {
    sessionStorage.setItem(key, value)
  } catch {
    /* private mode: intro just plays every visit */
  }
}

if (intro) {
  // Play once per session; returning visitors go straight to the page.
  if (reduce || storageGet('solvd-intro')) {
    intro.remove()
  } else {
    storageSet('solvd-intro', '1')
    intro.hidden = false
    docEl.classList.add('intro-playing')

    let finished = false
    const finish = () => {
      if (finished) return
      finished = true
      docEl.classList.remove('intro-playing')
      intro.classList.add('done')
      setTimeout(() => intro.remove(), 750)
    }

    // Double rAF so the initial state paints before .play transitions run.
    requestAnimationFrame(() =>
      requestAnimationFrame(() => intro.classList.add('play')),
    )
    setTimeout(finish, 1750)
    intro.addEventListener('pointerdown', finish)
    window.addEventListener('keydown', finish, { once: true })
  }
}

/* ---------- hero portal: landing + pointer tilt ---------- */

const portal = document.querySelector('.portal')
const heroChoreographed =
  portal && !reduce && docEl.classList.contains('js')

// Resolves once the portal's entrance animation has finished, so
// count-ups start while the panes are igniting instead of before.
const portalLanded = heroChoreographed
  ? new Promise((resolve) => {
      let done = false
      const settle = () => {
        if (done) return
        done = true
        portal.classList.add('landed')
        resolve()
      }
      portal.addEventListener('animationend', (e) => {
        if (e.animationName === 'portal-enter') settle()
      })
      setTimeout(settle, 4500) // safety: intro + entrance worst case
    })
  : Promise.resolve()

if (heroChoreographed && window.matchMedia('(pointer: fine)').matches) {
  const hero = document.querySelector('.hero')

  hero.addEventListener('pointermove', (e) => {
    if (!portal.classList.contains('landed')) return
    const rect = portal.getBoundingClientRect()
    const x = (e.clientX - rect.left) / rect.width - 0.5
    const y = (e.clientY - rect.top) / rect.height - 0.5
    portal.style.setProperty('--ry', `${(x * 2.4).toFixed(2)}deg`)
    portal.style.setProperty('--rx', `${(-y * 2).toFixed(2)}deg`)
  })

  hero.addEventListener('pointerleave', () => {
    portal.style.setProperty('--rx', '0deg')
    portal.style.setProperty('--ry', '0deg')
  })
}

/* ---------- scroll reveals ---------- */

if (!reduce && 'IntersectionObserver' in window) {
  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('in')
          io.unobserve(entry.target)
        }
      }
    },
    { threshold: 0.15, rootMargin: '0px 0px -40px 0px' },
  )

  document
    .querySelectorAll('[data-reveal], [data-stagger]')
    .forEach((el) => io.observe(el))
}

/* ---------- count-up stats in the portal mock ---------- */

if (!reduce && 'IntersectionObserver' in window) {
  const easeOutQuart = (t) => 1 - Math.pow(1 - t, 4)

  const io = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        io.unobserve(entry.target)

        const el = entry.target
        const end = parseFloat(el.dataset.count)
        const prefix = el.dataset.prefix || ''
        const duration = 1100

        portalLanded.then(() => {
          const start = performance.now()
          const tick = (now) => {
            const p = Math.min(1, (now - start) / duration)
            el.textContent = prefix + Math.round(end * easeOutQuart(p))
            if (p < 1) requestAnimationFrame(tick)
          }
          requestAnimationFrame(tick)
        })
      }
    },
    { threshold: 0.5 },
  )

  document.querySelectorAll('[data-count]').forEach((el) => io.observe(el))
}
