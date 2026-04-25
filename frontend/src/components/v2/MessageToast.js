/**
 * Dynamic Island Toast (Pixel Tyranny Edition)
 * A programmatic utility to spawn hyper-minimalist black/white pill toasts at the top center.
 * Usage: toast.success('Deployed')
 */

let toastContainer = null

function createContainer() {
  if (toastContainer) return
  toastContainer = document.createElement('div')
  toastContainer.id = 'v2-toast-container'
  // Center top, extremely high z-index
  Object.assign(toastContainer.style, {
    position: 'fixed',
    top: '20px',
    left: '50%',
    transform: 'translateX(-50%)',
    zIndex: '99999',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '8px',
    pointerEvents: 'none'
  })
  document.body.appendChild(toastContainer)
}

function spawnToast(msg, type = 'info', duration = 3000) {
  createContainer()

  const el = document.createElement('div')
  
  // Icon based on type (using simple unicode or inline SVG for standalone script)
  let iconHtml = ''
  if (type === 'success') iconHtml = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
  if (type === 'error') iconHtml = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>'
  if (type === 'info') iconHtml = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>'

  el.innerHTML = `<div style="display:flex;align-items:center;gap:8px;">
    <span style="display:flex;align-items:center;opacity:0.7;">${iconHtml}</span>
    <span style="font-size:13px;font-weight:500;">${msg}</span>
  </div>`

  // Dynamic Island styling (Inverse color: black pill on light mode, white pill on dark mode)
  const isDark = document.documentElement.classList.contains('dark')
  
  Object.assign(el.style, {
    backgroundColor: isDark ? '#ffffff' : '#171717',
    color: isDark ? '#000000' : '#ffffff',
    padding: '8px 16px',
    borderRadius: '9999px',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
    fontFamily: '"Geist", "Geist Sans", sans-serif',
    willChange: 'transform, opacity',
    opacity: '0',
    transform: 'translateY(-20px) scale(0.9)',
    transition: 'all 0.4s cubic-bezier(0.16, 1, 0.3, 1)'
  })

  toastContainer.appendChild(el)

  // Trigger animation frame for entrance
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      el.style.opacity = '1'
      el.style.transform = 'translateY(0) scale(1)'
    })
  })

  // Exit
  setTimeout(() => {
    el.style.opacity = '0'
    el.style.transform = 'translateY(-10px) scale(0.95)'
    setTimeout(() => {
      if (el.parentNode) el.parentNode.removeChild(el)
    }, 400)
  }, duration)
}

export const toast = {
  success: (msg, d) => spawnToast(msg, 'success', d),
  error: (msg, d) => spawnToast(msg, 'error', d),
  info: (msg, d) => spawnToast(msg, 'info', d)
}
