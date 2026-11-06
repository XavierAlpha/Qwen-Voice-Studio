import {t, getLocale} from './i18n.js';
import {icon} from './icons.js';
export const $ = id => document.getElementById(id);
export const $$ = selector => [...document.querySelectorAll(selector)];
let token = '';
let persistDrafts = false;
const drafts = new Map();
const draftPrefix = 'qvs.draft.';
// Every text draft survives a refresh in its tab. Long-term storage remains
// an explicit privacy choice; disabling it removes durable copies.
export function configureDrafts(enabled){
  const durable = Boolean(enabled);
  try {
    const source = durable ? sessionStorage : localStorage;
    const target = durable ? localStorage : sessionStorage;
    for (const key of Object.keys(source).filter(k => k.startsWith(draftPrefix))) {
      try { target.setItem(key, source.getItem(key)); } catch { /* storage quota */ }
      source.removeItem(key);
    }
  } catch { /* private browsing */ }
  persistDrafts = durable;
}
export function clearPreferences(){
  drafts.clear();
  try { for (const storage of [localStorage, sessionStorage]) {
    Object.keys(storage).filter(k=>k.startsWith('qvs.')).forEach(k=>storage.removeItem(k));
  } }catch{}
}
export function setToken(value){token=value;}
export async function api(path, options={}){
  const headers = {'X-Studio-Token':token,...options.headers};
  if(options.body && typeof options.body!=='string' && !(options.body instanceof Blob)){
    options={...options,body:JSON.stringify(options.body)};headers['Content-Type']='application/json';
  }
  const response=await fetch('/api'+path,{...options,headers});
  if(!response.ok){
    let detail;try{detail=(await response.json()).detail;}catch{detail=response.statusText;}
    if(Array.isArray(detail))detail=detail.map(x=>`${x.loc?.slice(1).join('.')}: ${x.msg}`).join('\n');
    const error=new Error(detail||`HTTP ${response.status}`);
    error.status=response.status;
    throw error;
  }
  return response.json();
}
export function node(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
export function button(label,iconName,handler,cls='icon-button tiny'){
  const b=node('button',cls);b.type='button';b.title=label;b.setAttribute('aria-label',label);b.append(icon(iconName));if(handler)b.addEventListener('click',handler);return b;
}
const toastTimers=new WeakMap();
function retireToast(box){
  clearTimeout(toastTimers.get(box));toastTimers.delete(box);box.remove();
}
export function toast(message,error=false){
  const region=$('toasts');if(!region)return;
  const text=String(message||'').trim();if(!text)return;
  // Repeated polling errors should refresh one notice, not create an endless stack.
  const existing=[...region.children].find(box=>box.dataset.message===text&&box.dataset.error===String(error));
  if(existing)retireToast(existing);
  const box=node('div','toast'+(error?' error':''));
  box.dataset.message=text;box.dataset.error=String(error);
  box.setAttribute('role',error?'alert':'status');
  box.append(icon(error?'alert':'check'),node('span','',text));
  const dismiss=button(t('action.close'),'x',()=>retireToast(box),'icon-button tiny toast-close');
  box.append(dismiss);region.append(box);
  while(region.children.length>3)retireToast(region.firstElementChild);
  const duration=error?8500:3500;
  toastTimers.set(box,setTimeout(()=>retireToast(box),duration));
}
export function action(fn){return async event=>{try{await fn(event);}catch(error){toast(error.message,true);console.error(error);}};}
export function timeText(seconds){if(!Number.isFinite(seconds))return '0:00';return `${Math.floor(seconds/60)}:${Math.floor(seconds%60).toString().padStart(2,'0')}`;}
export function dateText(value){return new Date(value*1000).toLocaleString(getLocale(),{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}
export function remember(key,value){
  if(key.startsWith('draft.'))drafts.set(key,value);
  try{(key.startsWith('draft.')&&!persistDrafts?sessionStorage:localStorage).setItem('qvs.'+key,JSON.stringify(value));}catch{}
}
export function recall(key,fallback){
  try{
    const storage=key.startsWith('draft.')&&!persistDrafts?sessionStorage:localStorage;
    const raw=storage.getItem('qvs.'+key);
    if(raw!==null)return JSON.parse(raw)??fallback;
  }catch{}
  return drafts.get(key)??fallback;
}
export function rememberSession(key,value){try{sessionStorage.setItem('qvs.'+key,JSON.stringify(value));}catch{}}
export function recallSession(key,fallback){try{return JSON.parse(sessionStorage.getItem('qvs.'+key))??fallback;}catch{return fallback;}}
export function forgetSession(key){try{sessionStorage.removeItem('qvs.'+key);}catch{}}
export async function confirmAction(message,title=t('confirm.title')){
  const d=$('confirm-dialog');$('confirm-title').textContent=title;$('confirm-message').textContent=message;d.returnValue='cancel';d.showModal();
  return new Promise(resolve=>d.addEventListener('close',()=>resolve(d.returnValue==='ok'),{once:true}));
}
