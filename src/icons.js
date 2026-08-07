/* The icon sprite, injected at boot.

   It used to sit inline in demo/index.html, but two pages need it now and
   duplicating sixty lines of SVG across both is worse than keeping it here.
   Both pages already require JS to render anything, so nothing is lost. */

export const SPRITE = `
<svg class="sprite" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
  <symbol id="i-overview" viewBox="0 0 24 24">
    <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
    <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
    <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
    <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
  </symbol>
  <symbol id="i-growth" viewBox="0 0 24 24">
    <path d="M3 17.5 9.5 11l4 4L21 7.5" />
    <path d="M15 7.5h6v6" />
  </symbol>
  <symbol id="i-churn" viewBox="0 0 24 24">
    <path d="M2.5 12h3.8l2.2-5.5 3.2 11 2.6-7 1.6 3h5.6" />
  </symbol>
  <symbol id="i-inbox" viewBox="0 0 24 24">
    <path d="M3.5 13.5h4l1.8 3h5.4l1.8-3h4" />
    <path d="M3.5 13.5 6.3 5h11.4l2.8 8.5V18a2 2 0 0 1-2 2H5.5a2 2 0 0 1-2-2z" />
  </symbol>
  <symbol id="i-members" viewBox="0 0 24 24">
    <circle cx="9.5" cy="8" r="3.6" />
    <path d="M3 20a6.5 6.5 0 0 1 13 0" />
    <path d="M16.5 5.4a3.6 3.6 0 0 1 0 5.2" />
    <path d="M18 20a6.6 6.6 0 0 0-1.6-4.3" />
  </symbol>
  <symbol id="i-plug" viewBox="0 0 24 24">
    <path d="M9 3v5M15 3v5" />
    <path d="M6.5 8h11v3.5a5.5 5.5 0 0 1-11 0z" />
    <path d="M12 17v4" />
  </symbol>
  <symbol id="i-back" viewBox="0 0 24 24">
    <path d="M19.5 12H5" />
    <path d="m11 5.5-6 6.5 6 6.5" />
  </symbol>
  <symbol id="i-search" viewBox="0 0 24 24">
    <circle cx="11" cy="11" r="7" />
    <path d="m16.4 16.4 4.6 4.6" />
  </symbol>
  <symbol id="i-chevron" viewBox="0 0 24 24">
    <path d="m6 9.5 6 6 6-6" />
  </symbol>
  <symbol id="i-check" viewBox="0 0 24 24">
    <path d="m5 12.5 4.5 4.5L19.5 7" />
  </symbol>
  <symbol id="i-alert" viewBox="0 0 24 24">
    <path d="M12 3.5 2.5 20h19z" />
    <path d="M12 9.5v4.5M12 16.8v.2" />
  </symbol>
  <symbol id="i-arrow" viewBox="0 0 24 24">
    <path d="M4.5 12h15" />
    <path d="m13.5 5.5 6 6.5-6 6.5" />
  </symbol>
  <symbol id="i-lock" viewBox="0 0 24 24">
    <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
    <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
  </symbol>
  <symbol id="i-out" viewBox="0 0 24 24">
    <path d="M15 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2H15" />
    <path d="M12.5 12h7.5" />
    <path d="m17 8.5 3.5 3.5L17 15.5" />
  </symbol>
</svg>`

export function mountSprite() {
  if (document.querySelector('.sprite')) return
  const holder = document.createElement('div')
  holder.innerHTML = SPRITE.trim()
  document.body.prepend(holder.firstElementChild)
}
