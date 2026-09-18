/* Keyboard and TV remote behavior shared by the existing portal screens. */
(() => {
  const app = document.querySelector('.cockpit-app');
  const menu = document.getElementById('sidebar');
  const menuToggle = document.getElementById('sidebar-toggle');
  const focusable = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]';
  const visibleControls = root => [...root.querySelectorAll(focusable)].filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
  let activeDialog = null;
  let returnFocus = null;
  let lastExternalFocus = document.activeElement;
  document.addEventListener('focusin', event => {
    if (!event.target.closest('.pf-modal-backdrop')) lastExternalFocus = event.target;
  });

  function syncDialogs() {
    const next = [...document.querySelectorAll('.pf-modal-backdrop.open')].at(-1) || null;
    if (next === activeDialog) return;
    if (next) {
      if (!activeDialog) returnFocus = lastExternalFocus;
      app.inert = true;
      activeDialog = next;
      (visibleControls(next).find(el => el.tagName === 'INPUT') || visibleControls(next)[0])?.focus();
    } else {
      app.inert = false;
      activeDialog = null;
      if (returnFocus?.isConnected) returnFocus.focus();
      returnFocus = null;
    }
  }
  const observer = new MutationObserver(syncDialogs);
  document.querySelectorAll('.pf-modal-backdrop').forEach(dialog => {
    observer.observe(dialog, { attributes: true, attributeFilter: ['class'] });
    dialog.addEventListener('click', event => {
      if (event.target === dialog) {
        closeCommandPalette(); closeModal(); closeConfirmModal();
      }
    });
  });
  new MutationObserver(() => {
    menuToggle.setAttribute('aria-expanded', String(menu.classList.contains('open')));
  }).observe(menu, { attributes: true, attributeFilter: ['class'] });

  document.getElementById('masthead-search-input').addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openCommandPalette(); }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.classList.contains('open')) {
      menu.classList.remove('open');
      document.getElementById('sidebar-backdrop').classList.remove('open');
      menuToggle.focus();
    }
    if (event.key === 'Tab' && activeDialog) {
      const controls = visibleControls(activeDialog);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && (document.activeElement === first || !activeDialog.contains(document.activeElement))) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first?.focus();
      }
      return;
    }
    // Preserve text editing and native select behavior; arrows navigate other controls spatially.
    if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target.matches('input, textarea, select, [contenteditable="true"]')) return;
    const controls = visibleControls(activeDialog || document);
    const current = document.activeElement;
    if (!controls.includes(current)) { event.preventDefault(); controls[0]?.focus(); return; }
    const rect = current.getBoundingClientRect();
    const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
    const horizontal = ['ArrowLeft', 'ArrowRight'].includes(event.key);
    const sign = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
    const candidates = controls.filter(el => el !== current && !el.closest('[inert]')).map(el => {
      const r = el.getBoundingClientRect();
      const dx = r.left + r.width / 2 - x, dy = r.top + r.height / 2 - y;
      const along = (horizontal ? dx : dy) * sign;
      return { el, along, score: along + Math.abs(horizontal ? dy : dx) * 3 };
    }).filter(item => item.along > 5).sort((a, b) => a.score - b.score);
    if (candidates[0]) { event.preventDefault(); candidates[0].el.focus(); }
  });
})();
