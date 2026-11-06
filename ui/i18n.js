// Local-only dictionaries. Never translate user-authored scripts, paths or recordings.
const SUPPORTED = ['zh-CN', 'en'];
const dictionaries = {};
let locale = 'zh-CN';
export function getLocale() { return locale; }
export function t(key, values = {}) {
  const singular = Number(values.count) === 1 ? key + '.one' : key;
  const text = dictionaries[locale]?.[singular] ?? dictionaries[locale]?.[key] ?? dictionaries['en']?.[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? `{${name}}`));
}
export function formatNumber(value, options) {
  return new Intl.NumberFormat(locale, options).format(value);
}
export function applyI18n(root = document) {
  const attributes = ['title', 'aria-label', 'placeholder'];
  root.querySelectorAll('[data-i18n]').forEach(element => {
    element.textContent = t(element.dataset.i18n);
  });
  for (const attribute of attributes) {
    root.querySelectorAll(`[data-i18n-${attribute}]`).forEach(element => {
      element.setAttribute(attribute, t(element.getAttribute(`data-i18n-${attribute}`)));
    });
  }
}
export function setLocale(value, notify = true) {
  if (!SUPPORTED.includes(value)) return;
  locale = value;
  document.documentElement.lang = value;
  try { localStorage.setItem('qvs.locale', JSON.stringify(value)); } catch { /* private browsing */ }
  applyI18n();
  const control = document.getElementById('interface-language');
  if (control) control.value = value;
  if (notify) document.dispatchEvent(new CustomEvent('qvs:locale', {detail: value}));
}
export async function initI18n() {
  await Promise.all(SUPPORTED.map(async key => {
    const response = await fetch(`/ui/locales/${key}.json`);
    if (!response.ok) throw new Error(`Language resource unavailable: ${key}`);
    dictionaries[key] = await response.json();
  }));
  let preferred;
  try { preferred = JSON.parse(localStorage.getItem('qvs.locale')); } catch { /* first run */ }
  setLocale(SUPPORTED.includes(preferred) ? preferred : (navigator.language.startsWith('zh') ? 'zh-CN' : 'en'), false);
}
export function presetCopy(preset) {
  const key = `preset.${preset.id}`;
  const original = dictionaries['zh-CN'];
  // Only untouched factory presets get translated; custom/edited content stays verbatim.
  const builtin = original?.[key + '.name'] === preset.name && original?.[key + '.instruct'] === preset.instruct;
  return builtin ? {name: t(key + '.name'), instruct: t(key + '.instruct')} : preset;
}
