import {$, $$, remember, recall, toast} from './core.js';
import {getLocale, setLocale, t} from './i18n.js';

const choices = {
  theme: ['system', 'light', 'dark'], font: ['studio', 'editorial'],
  density: ['comfortable', 'compact'], layout: ['split', 'stack'], scale: [100, 110, 120],
};
const defaults = {theme: 'system', font: 'studio', density: 'comfortable', layout: 'split', scale: 100};
const media = matchMedia('(prefers-color-scheme: dark)');
let current = {...defaults};
export function setAppearance(key, value) {
  if (!choices[key]?.includes(value)) return;
  current[key] = value;
  remember(key, value);
  applyAppearance();
}
export function toggleLayout() { setAppearance('layout', current.layout === 'split' ? 'stack' : 'split'); }
export function applyAppearance() {
  const resolvedTheme = current.theme === 'system' ? (media.matches ? 'dark' : 'light') : current.theme;
  for (const element of [document.documentElement, document.body]) {
    element.dataset.theme = resolvedTheme;
    element.dataset.font = current.font;
    element.dataset.density = current.density;
    element.dataset.layout = current.layout;
    element.dataset.scale = String(current.scale);
  }
  for (const key of ['theme', 'density', 'layout', 'scale']) $('interface-' + key).value = String(current[key]);
  for (const radio of $$('[name=font-preset]')) radio.checked = radio.value === current.font;
  $('interface-language').value = getLocale();
  document.dispatchEvent(new CustomEvent('qvs:appearance'));
}
// Move the same action nodes to keep visual order and keyboard order aligned.
function placeComposeActions() {
  const workspace = $('workspace');
  const actions = $('compose-actions');
  if (matchMedia('(max-width: 1060px)').matches || current.layout === 'stack') {
    workspace.querySelector('.editor-panel').after(actions);
  } else {
    workspace.after(actions);
  }
}
export function initAppearance() {
  for (const [key, fallback] of Object.entries(defaults)) {
    const value = recall(key, fallback);
    current[key] = choices[key].includes(value) ? value : fallback;
  }
  $('interface-language').onchange = event => setLocale(event.target.value);
  for (const key of ['theme', 'density', 'layout', 'scale']) {
    $('interface-' + key).onchange = event => setAppearance(key, key === 'scale' ? Number(event.target.value) : event.target.value);
  }
  for (const radio of $$('[name=font-preset]')) radio.onchange = () => setAppearance('font', radio.value);
  $('reset-appearance').onclick = () => {
    for (const [key, value] of Object.entries(defaults)) { current[key] = value; remember(key, value); }
    remember('split', 55); document.documentElement.style.setProperty('--split', '55%');
    $('panel-splitter').setAttribute('aria-valuenow', '55');
    applyAppearance(); toast(t('appearance.resetDone'));
  };
  media.addEventListener('change', () => { if (current.theme === 'system') applyAppearance(); });
  matchMedia('(max-width: 1060px)').addEventListener('change', placeComposeActions);
  window.addEventListener('resize', placeComposeActions);
  document.addEventListener('qvs:appearance', placeComposeActions);
  applyAppearance();
}
