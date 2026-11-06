import {$, $$, remember, recall} from './core.js';
import {t} from './i18n.js';
const mobile = matchMedia('(max-width: 800px)');
let returnFocus;
export function closeMenu(restoreFocus = true) {
  const wasOpen = document.body.classList.contains('menu-open');
  document.body.classList.remove('menu-open');
  document.querySelector('.main-area').inert = false;
  $('menu-toggle').setAttribute('aria-expanded', 'false');
  $('sidebar').removeAttribute('role');
  $('sidebar').removeAttribute('aria-modal');
  $('sidebar').removeAttribute('aria-label');
  if (wasOpen && restoreFocus && returnFocus?.isConnected) returnFocus.focus();
  else if (wasOpen && $('sidebar').contains(document.activeElement)) $('main-content').focus();
}
export function refreshNavigation() {
  const collapsed = document.body.classList.contains('sidebar-collapsed');
  $('collapse-sidebar').title = t(collapsed ? 'a11y.expand' : 'a11y.collapse');
  $('collapse-sidebar').setAttribute('aria-label', $('collapse-sidebar').title);
  $('collapse-sidebar').setAttribute('aria-expanded', String(!collapsed));
}
export function initNavigation() {
  document.body.classList.toggle('sidebar-collapsed', recall('collapsed', false) === true);
  $('menu-toggle').onclick = () => {
    returnFocus = document.activeElement;
    document.body.classList.add('menu-open');
    $('sidebar').setAttribute('role', 'dialog');
    $('sidebar').setAttribute('aria-modal', 'true');
    $('sidebar').setAttribute('aria-label', t('a11y.menu'));
    document.querySelector('.main-area').inert = true;
    $('menu-toggle').setAttribute('aria-expanded', 'true');
    $('sidebar-close').focus();
  };
  for (const id of ['sidebar-close', 'mobile-backdrop']) $(id).onclick = () => closeMenu();
  $('collapse-sidebar').onclick = () => {
    document.body.classList.toggle('sidebar-collapsed');
    remember('collapsed', document.body.classList.contains('sidebar-collapsed')); refreshNavigation();
  };
  document.addEventListener('keydown', event => {
    if (!document.body.classList.contains('menu-open') || !mobile.matches || document.querySelector('dialog[open]')) return;
    if (event.key === 'Escape') { event.preventDefault(); closeMenu(); }
    if (event.key === 'Tab') {
      const focusable = $$('#sidebar button, #sidebar select, #sidebar a').filter(e => !e.disabled && e.getClientRects().length);
      const index = focusable.indexOf(document.activeElement);
      if (event.shiftKey && index <= 0) { event.preventDefault(); focusable.at(-1)?.focus(); }
      else if (!event.shiftKey && index === focusable.length - 1) { event.preventDefault(); focusable[0]?.focus(); }
    }
  });
  mobile.addEventListener('change', () => closeMenu(false));
  refreshNavigation();
}
