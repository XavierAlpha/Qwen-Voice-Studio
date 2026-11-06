import test, {before} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {initI18n, setLocale, getLocale, t, presetCopy, formatNumber} from '../ui/i18n.js';

const stored = new Map();
const elements = { 'interface-language': {value: ''}, 'locale-label': {textContent: ''} };
const translated = {dataset: {i18n: 'action.generate'}, textContent: ''};
const calls = [];
globalThis.document = {
  documentElement: {lang: ''},
  querySelectorAll: selector => selector === '[data-i18n]' ? [translated] : [],
  getElementById: id => elements[id],
  dispatchEvent: event => calls.push(event.detail)
};
globalThis.localStorage = {getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value)};
Object.defineProperty(globalThis, 'navigator', {value: {language: 'en-US'}, configurable: true});
globalThis.fetch = async url => ({ok: true, json: async () => JSON.parse(await readFile(new URL('..' + url, import.meta.url), 'utf8'))});

before(async () => initI18n());
test('first visit follows browser language', () => assert.equal(getLocale(), 'en'));
test('static translation uses textContent', () => assert.equal(translated.textContent, 'Generate voice'));
test('interpolates counts', () => assert.equal(t('counter.jobs', {count: 4}), '4 tasks'));
test('uses grammatical singular counts', () => {
  assert.equal(t('counter.jobs', {count: 1}), '1 task');
  assert.equal(t('counter.records', {count: 1}), '1 clip');
});
test('keeps untrusted interpolation as plain text', () => assert.match(t('confirm.deletePreset', {name: '<script>x</script>'}), /<script>x<\/script>/));
test('invalid locale cannot become a file path', () => {setLocale('../bad'); assert.equal(getLocale(), 'en');});
test('language updates lang, storage and event', () => {
  setLocale('zh-CN'); assert.equal(document.documentElement.lang, 'zh-CN');
  assert.equal(JSON.parse(stored.get('qvs.locale')), 'zh-CN'); assert.equal(calls.at(-1), 'zh-CN');
});
test('switching back retains stable language keys', () => {setLocale('en'); assert.equal(elements['interface-language'].value, 'en');});
test('formats numbers in active locale', () => assert.equal(formatNumber(6000), '6,000'));
test('unknown keys remain visible for diagnosis', () => assert.equal(t('missing.key'), 'missing.key'));
test('custom preset content is never translated', () => {
  const p={id:'own',name:'Original',instruct:'Do not modify'}; assert.equal(presetCopy(p), p);
});
test('edited built-in preset content is never overwritten', () => {
  const p={id:'warm',name:'My edit',instruct:'Original'}; assert.equal(presetCopy(p), p);
});
test('built-in labels have localized display only', async () => {
  const zh = JSON.parse(await readFile(new URL('../ui/locales/zh-CN.json', import.meta.url), 'utf8'));
  const p={id:'warm',name:zh['preset.warm.name'],instruct:zh['preset.warm.instruct']};
  const copy=presetCopy(p); assert.equal(copy.name, 'Warm narration'); assert.equal(p.name, zh['preset.warm.name']);
});
