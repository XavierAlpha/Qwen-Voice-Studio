import {t, initI18n, getLocale, formatNumber, presetCopy} from './i18n.js';
import {initAppearance} from './appearance.js';
import {initNavigation, closeMenu, refreshNavigation} from './navigation.js';
import {$,$$,api,setToken,node,button,toast,action,timeText,dateText,remember,recall,rememberSession,recallSession,confirmAction,configureDrafts} from './core.js';
import {hydrate,icon,replaceIcon} from './icons.js';
import {Player} from './player.js';
import {Recorder} from './recorder.js';
import {SettingsPanel} from './settings.js';

hydrate();
const player=new Player(), recorder=new Recorder();
let settings;
const modeName = mode => t('mode.' + mode);
const typeNames={design:'VoiceDesign',clone:'Base',custom:'CustomVoice'};
const state={mode:'design',view:'studio',models:[],presets:[],runtime:{},reference:null,selected:'',jobs:[],seen:new Set(),history:[],historyTotal:0,busy:false,editingPreset:null,polling:false,submitting:false};
const params={'temperature':'temperature','top-p':'top_p','top-k':'top_k','repeat':'repetition_penalty','max-tokens':'max_new_tokens','seed':'seed'};
let draftTimer=null,searchTimer=null,offline=false;
let formErrorTimer;
function clearFormError(){
  clearTimeout(formErrorTimer);formErrorTimer=undefined;
  $('form-error').classList.add('hidden');$('form-error').textContent='';
}
function showFormError(message){
  clearFormError();$('form-error').textContent=message;
  $('form-error').classList.remove('hidden');
  formErrorTimer=setTimeout(clearFormError,10000);
}


function showView(view){
  if(!['studio','history','presets'].includes(view))view='studio';
  state.view=view;remember('view',view);$$('.view').forEach(x=>x.classList.toggle('hidden',x.id!==`view-${view}`));
  $$('[data-view]').forEach(x=>x.classList.toggle('active',x.dataset.view===view));
  $$('[data-mode]').forEach(x=>x.classList.toggle('active',view==='studio'&&x.dataset.mode===state.mode));
  $('breadcrumb-current').textContent=view==='studio'?modeName(state.mode):view==='history'?t('nav.library'):t('nav.presets');
  closeMenu(false);
}
function readSampling(){const obj={};for(const [id,key] of Object.entries(params))obj[key]=Number($(id).value);return obj;}
// Ordinary generation choices are durable even when private transcript retention
// is disabled. Text and reference identifiers are kept in the current tab only
// unless the user explicitly enables long-term draft storage.
const workflowFields={
  'split-lines':'checked','split-text':'checked','xvector-only':'checked',
  'chunk-chars':'value','pause-ms':'value','variations':'value',
};
function readWorkflow(){
  const options={language:$('language').value,sampling:readSampling(),advanced:$('advanced-settings').open};
  for(const [id,property] of Object.entries(workflowFields))options[id]=$(id)[property];
  return options;
}
function restoreWorkflow(options){
  if(!options)return;
  const language=$('language');
  if([...language.options].some(o=>o.value===options.language))language.value=options.language;
  if(options.sampling)for(const [id,key] of Object.entries(params)){
    const value=Number(options.sampling[key]),element=$(id);
    if(Number.isFinite(value)&&value>=Number(element.min)&&value<=Number(element.max))element.value=String(value);
  }
  for(const [id,property] of Object.entries(workflowFields)){
    const value=options[id],element=$(id);
    if(value===undefined)continue;
    if(property==='checked')element.checked=value===true;
    else if(element.tagName==='SELECT'){
      if([...element.options].some(o=>o.value===String(value)))element.value=String(value);
    }else{
      const number=Number(value);
      if(Number.isFinite(number)&&number>=Number(element.min)&&number<=Number(element.max))element.value=String(number);
    }
  }
  if(typeof options.advanced==='boolean')$('advanced-settings').open=options.advanced;
}
function saveDraft(){
  remember('workflow.'+state.mode,readWorkflow());
  remember('draft.'+state.mode,{
    text:$('script-text').value,instruct:$('voice-instruct').value,
    custom:$('custom-instruct').value,ref:state.mode==='clone'?state.reference:null,
    ref_text:$('ref-text').value,
  });
}
function loadDraft(){
  const d=recall('draft.'+state.mode,null);
  // Migrate legacy v3.4 draft controls without losing the user's selections.
  restoreWorkflow(recall('workflow.'+state.mode,null)||d);
  if(d){
    $('script-text').value=d.text||'';
    $('voice-instruct').value=d.instruct||'';
    $('custom-instruct').value=d.custom||'';
    if(state.mode==='clone')$('ref-text').value=d.ref_text||'';
  }
  if(state.mode==='clone'){state.reference=d?.ref||null;updateReference();verifyReference();}
  updateCounters();
}
async function verifyReference(){
  const id=state.reference?.id;
  if(!id)return;
  try{
    const ref=await api('/references/'+encodeURIComponent(id));
    if(state.reference?.id===id){state.reference=ref;updateReference();}
  }catch(error){
    if(error.status===404&&state.reference?.id===id){
      state.reference=null;updateReference();saveDraft();toast(t('notice.referenceMissing'),true);
    }
  }
}
function setMode(mode,save=true){
  if(recorder.active){toast(t('error.stopRecording'));return;}
  if(save)saveDraft();state.mode=mode;remember('mode',mode);
  $('workspace-title').textContent=modeName(mode);$$('.mode-controls').forEach(x=>x.classList.toggle('hidden',x.id!==`${mode}-controls`));
  $$('[data-mode]').forEach(x=>{x.classList.toggle('active',x.dataset.mode===mode);if(x.dataset.mode===mode)x.setAttribute('aria-current','page');else x.removeAttribute('aria-current');});
  loadDraft();renderModels();showView('studio');
}
function renderModels(){
  const options=state.models.filter(m=>m.mode===state.mode && (m.status||'ready')==='ready'), select=$('model-select'),previous=state.selected;
  select.replaceChildren();
  if(!options.length){const o=node('option','',t('models.addType',{type:typeNames[state.mode]}));o.value='';select.append(o);}
  options.forEach(m=>{const o=node('option','',m.name.replace('Qwen3-TTS-12Hz-','').replace('Qwen3-TTS ',''));o.value=m.id;o.textContent+=' · '+m.id.slice(0,6);select.append(o);});
  const remembered=recall('model.'+state.mode,'');
  state.selected=options.find(m=>m.id===previous)?.id||options.find(m=>m.id===remembered)?.id||options[0]?.id||'';
  select.value=state.selected;modelChanged();
}
function modelChanged(){
  state.selected=$('model-select')?.value || '';
  if(state.selected){remember('model.'+state.mode,state.selected);remember('lastModel',state.selected);}
  const model=state.models.find(m=>m.id===state.selected);
  $('model-subtitle').textContent=model?(model.size||typeNames[state.mode]):t('models.incompatible');
  const manage=$('add-model-shortcut').querySelector('span');
  manage.dataset.i18n=model?'models.manage':'models.addLocal';manage.textContent=t(manage.dataset.i18n);
  $('generate-btn').disabled=!model;
  $('custom-instruct').disabled=model?.capabilities?.instruct===false;
  const lang=$('language');
  [...lang.options].forEach(o=>o.disabled=Boolean(model?.languages?.length&&!model.languages.includes(o.value)));
  if(lang.selectedOptions[0]?.disabled)lang.value=model.languages.includes('Chinese')?'Chinese':model.languages[0];
  const selector=$('speaker');
  const speakers=Array.isArray(model?.speakers)?model.speakers.filter(s=>typeof s==='string'&&s.trim()):[];
  const previous=selector.value;
  if(!model || !speakers.length){
    const key=model?'speaker.noSpeakers':'speaker.addModel';
    const hint=model?'speaker.noSpeakersHint':'speaker.addModelHint';
    const empty=node('option','',t(key));empty.value='';selector.replaceChildren(empty);
    selector.disabled=true;$('speaker-hint').textContent=t(hint);
  }else{
    selector.disabled=false;
    selector.replaceChildren(...speakers.map(s=>{
      const label=t('speaker.voice.'+s.toLowerCase());
      const option=node('option','',label.startsWith('speaker.voice.')?s:`${s} · ${label}`);
      option.value=s;return option;
    }));
    const saved=recall('speaker.'+state.selected,'');
    selector.value=speakers.includes(previous)?previous:speakers.includes(saved)?saved:speakers[0];
    $('speaker-hint').textContent=t('speaker.readyHint');
  }
}
function updateCounters(){
  $('char-counter').textContent=t('counter.characters',{count:formatNumber(Array.from($('script-text').value).length)});
  for(const [id] of Object.entries(params))if($(id+'-value'))$(id+'-value').textContent=$(id).value;
}
function updateReference(){
  const ref=state.reference;
  $('reference-title').textContent=ref?.name||t('reference.drop');
  $('reference-detail').textContent=ref?`${ref.duration.toFixed(1)} s / ${ref.sample_rate} Hz`:'WAV / FLAC / OGG';
  if(ref)$('reference-player').src=`/api/references/${ref.id}/audio`;
  else{$('reference-player').pause();$('reference-player').removeAttribute('src');$('reference-player').load();}
  $('remove-ref').disabled=!ref;$('voice-consent').checked=false;
}
async function upload(file){
  if(!file)return;if(file.size>25*1024*1024)throw new Error(t('error.uploadSize'));
  const result=await api('/references',{method:'POST',body:file,headers:{'Content-Type':file.type||'application/octet-stream','X-Filename':encodeURIComponent(file.name)}});
  state.reference=result;updateReference();saveDraft();toast(t('notice.referenceReady'));
}
function formRequest(text=$('script-text').value.trim()){
  if(!state.selected)throw new Error(t('error.addModel',{type:typeNames[state.mode]}));
  if(!text)throw new Error(t('error.script'));
  if(state.mode==='design'&&!$('voice-instruct').value.trim())throw new Error(t('error.direction'));
  if(state.mode==='clone'&&(!state.reference||!$('voice-consent').checked))throw new Error(t('error.consent'));
  if(state.mode==='clone'&&!$('xvector-only').checked&&!$('ref-text').value.trim()){
    $('ref-text').focus();
    throw new Error(t('error.referenceTranscript'));
  }
  if(!Number.isFinite(Number($('chunk-chars').value))||!Number.isFinite(Number($('pause-ms').value)))throw new Error(t('error.segments'));
  return {model_id:state.selected,mode:state.mode,text,language:$('language').value,
    instruct:state.mode==='custom'?($('custom-instruct').disabled?'':$('custom-instruct').value.trim()):$('voice-instruct').value.trim(),
    speaker:$('speaker').value||'',reference_id:state.reference?.id||null,ref_text:$('ref-text').value.trim(),
    x_vector_only:$('xvector-only').checked,consent:$('voice-consent').checked,
    split_text:$('split-text').checked,chunk_chars:Number($('chunk-chars').value),pause_ms:Number($('pause-ms').value),
    sampling:readSampling(),runtime:state.runtime};
}
async function generate(){
  if(state.submitting)return;state.submitting=true;
  clearFormError();let submitted=0;
  try{
    saveDraft();
    const text=$('script-text').value.trim();const lines=$('split-lines').checked?text.split(/\r?\n/).map(t=>t.trim()).filter(Boolean):[text];
    const count=Number($('variations').value);
    if(lines.length*count>12)throw new Error(t('error.batch'));
    // Validate all payloads before submitting any to avoid needless partial batches.
    const requests=[];for(const line of lines){for(let i=0;i<count;i++){const r=formRequest(line);if(i&&r.sampling.seed>=0)r.sampling.seed=(r.sampling.seed+i)%2147483647;requests.push(r);}}
    if(!requests.length)throw new Error(t('error.script'));
    $('generate-btn').disabled=true;
    for(const request of requests){await api('/jobs',{method:'POST',body:request});submitted++;}
    toast(submitted===1?t('notice.queued'):t('notice.queuedMany',{count:submitted}));await poll();
  }catch(error){showFormError((submitted?t('notice.partial',{count:submitted}):'')+error.message);}
  finally{state.submitting=false;$('generate-btn').disabled=!state.selected;}
}
function restore(request){
  setMode(request.mode);state.selected=request.model_id;renderModels();$('script-text').value=request.text;
  $('voice-instruct').value=request.instruct;$('custom-instruct').value=request.instruct;$('language').value=request.language;
  $('speaker').value=request.speaker;
  if(state.mode==='custom'&&request.speaker&&$('speaker').value!==request.speaker)toast(t('speaker.noSpeakers'),true);
  $('ref-text').value=request.ref_text;$('xvector-only').checked=request.x_vector_only;
  if(request.reference_id){state.reference={id:request.reference_id,name:t('reference.title'),duration:0,sample_rate:0};updateReference();verifyReference();}
  $('split-text').checked=request.split_text;$('chunk-chars').value=request.chunk_chars;$('pause-ms').value=request.pause_ms;
  for(const [id,key] of Object.entries(params))if(request.sampling[key]!==undefined)$(id).value=request.sampling[key];
  updateCounters();saveDraft();toast(t('notice.restored'));
}
async function showTrack(id){const t=await api('/history/'+id);player.set(t);showView('studio');return t;}
let jobsSignature='';
function jobFailure(job){
  const key='failure.'+job.error_code;
  const translated=job.error_code?t(key):key;
  const message=translated!==key?translated:(job.error||t('error.generation'));
  return job.error_ref?`${message} [${job.error_ref}]`:message;
}
function renderJobs(force=false){
  const signature=JSON.stringify(state.jobs);
  if(!force&&signature===jobsSignature)return;
  jobsSignature=signature;
  const active=state.jobs.filter(j=>['queued','loading','running','cancelling'].includes(j.status));
  state.busy=active.length>0;if($('release-model'))$('release-model').disabled=state.busy||!systemSnapshot?.model?.loaded;
  $('task-status').textContent=active.length?t('counter.jobs',{count:active.length}):t('model.ready');$('task-dot').classList.toggle('busy',state.busy);
  const current=active.find(j=>j.status!=='queued')||active[active.length-1];
  $('job-progress').classList.toggle('hidden',!current);
  if(current){
    const labels={queued:t('job.waiting'),loading:t('job.loading'),running:t('job.running'),cancelling:t('job.stopAfterSegment')};
    $('job-step-text').textContent=labels[current.status];$('job-percent').textContent=current.total?t('counter.segments',{done:current.completed,total:current.total}):'';
    $('job-progress-fill').style.width=current.total?`${100*current.completed/current.total}%`:'0%';
    $('cancel-job').disabled=current.status==='cancelling';$('cancel-job').onclick=action(async()=>{await api(`/jobs/${current.id}/cancel`,{method:'POST'});await poll();});
  }
  const list=$('session-tracks');list.replaceChildren();$('session-count').textContent=t('counter.records',{count:state.jobs.filter(j=>j.kind==='generate').length});
  for(const j of state.jobs.filter(j=>j.kind==='generate').slice(0,10)){
    const row=node('div','session-row'+(j.status==='failed'?' failed':''));
    row.append(icon(j.status==='done'?'audio-waveform':j.status==='failed'?'alert':j.status==='cancelled'?'square':'clock-3'));
    const text=node('button','row-text',j.request.text.slice(0,36));text.title=j.request.text;
    text.onclick=action(async()=>{if(j.track_id)await showTrack(j.track_id);else if(j.error)toast(jobFailure(j),true);else restore(j.request);});row.append(text);
    const label={queued:t('job.queued'),loading:t('action.load'),running:t('job.running'),cancelling:t('job.cancelling'),cancelled:t('job.cancelled'),failed:t('job.failed'),done:t('job.done'),interrupted:t('job.interrupted')};
    row.append(node('small','',label[j.status]||j.status));
    if(['queued','loading','running'].includes(j.status))row.append(button(t('action.cancel'),'x',action(async()=>{await api(`/jobs/${j.id}/cancel`,{method:'POST'});await poll();})));
    else row.append(button(t('action.reuse'),'rotate-ccw',()=>restore(j.request)));
    list.append(row);
  }
  if(!list.children.length)list.append(node('div','muted-empty',t('jobs.none')));
}
async function poll(){
  if(state.polling)return;state.polling=true;
  try{
    state.jobs=await api('/jobs');renderJobs();
    for(const j of [...state.jobs].reverse()){
      if(state.seen.has(j.id))continue;
      if(['done','failed','cancelled','interrupted'].includes(j.status)){
        state.seen.add(j.id);
        if(j.status==='done'&&j.track_id){const track=await api('/history/'+j.track_id);player.set(track);clearFormError();if(state.view==='history')await loadHistory();await updateSystem();}
        if(j.status==='done'&&j.kind==='load'){toast(t('notice.loaded'));await updateSystem();}
        if(j.status==='failed'){toast(jobFailure(j),true);}
      }
    }
    offline=false;
  }catch(error){if(!offline){toast(t('error.offline'),true);offline=true;}}
  finally{state.polling=false;}
}
async function pollLoop(){if(!document.hidden)await poll();setTimeout(pollLoop,document.hidden?10000:state.busy?900:4000);}
let systemSnapshot=null;
async function updateSystem(){
  const info=await api('/system');systemSnapshot=info;$('runtime-device').textContent=info.error?t('system.unknown'):(info.gpu||'CPU');
  const resolved=info.model?.runtime?.device;
  const runtimeNames={cpu:'CPU / FP32',hybrid:'GPU + CPU / FP32',cuda_bf16:'GPU / BF16',cuda_fp32:'GPU / FP32',cuda_fp16:'GPU / FP16'};
  $('runtime-sub').textContent=info.error?t('system.detectionError'):(info.model?.loaded?(runtimeNames[resolved]||info.model.backend||'Qwen3-TTS'):t('system.unloaded'));
  $('device-dot').classList.toggle('off',!info.cuda);$('settings-hardware').textContent=info.gpu||'CPU';$('settings-engine').textContent=info.hybrid_ready?t('settings.hybridReady'):t('settings.hybridUnavailable');
  $('system-details').textContent=JSON.stringify(info,null,2);
  $('release-model').disabled=state.busy||!info.model?.loaded;
}
function renderPresets(){
  $('preset-strip').replaceChildren();$('preset-grid').replaceChildren();
  if(!state.presets.length){
    const empty=node('div','preset-empty-state');
    empty.append(node('p','',t('presets.emptyHint')));
    empty.append(button(t('action.restorePresets'),'rotate-ccw',action(restoreFactoryPresets),'outlined-button'));
    empty.lastElementChild.append(node('span','',t('action.restorePresets')));
    $('preset-grid').append(empty);
    return;
  }
  state.presets.forEach(p=>{
    const display=presetCopy(p);
    const chip=button(display.name,'sparkles',()=>{$('voice-instruct').value=p.instruct;$('language').value=p.language||'Chinese';saveDraft();},'preset-chip');chip.append(node('span','',display.name));$('preset-strip').append(chip);
    const card=node('article','preset-card'),head=node('div','preset-card-header');head.append(icon('audio-waveform'),node('strong','',display.name));
    const controls=node('div','preset-card-actions');const use=button(t('action.use'),'arrow-right',()=>{setMode('design');$('voice-instruct').value=p.instruct;$('language').value=p.language||'Chinese';saveDraft();},'outlined-button');use.append(node('span','',t('action.use')));
    controls.append(use,button(t('action.edit'),'edit',()=>openPreset(p)),button(t('action.delete'),'trash',action(async()=>{if(await confirmAction(t('confirm.deletePreset',{name:p.name}))){await api('/presets/'+p.id,{method:'DELETE'});await refreshPresets();}})));
    card.append(head,node('p','',display.instruct),controls);$('preset-grid').append(card);
  });
}
async function refreshPresets(){state.presets=await api('/presets');renderPresets();}
async function restoreFactoryPresets(){
  state.presets=await api('/presets/restore',{method:'POST'});
  renderPresets();toast(t('notice.presetsRestored'));
}
function openPreset(p=null){state.editingPreset=p?.id||null;$('preset-name').value=p?.name||'';$('preset-instruct').value=p?.instruct||$('voice-instruct').value;$('preset-dialog').showModal();$('preset-name').focus();}
let historyRequest=0;
async function loadHistory(append=false){
  const requestId=++historyRequest;
  const offset=append?state.history.length:0;
  const q=new URLSearchParams({q:$('history-search').value,mode:$('history-filter').value,favorite:$('favorites-only').checked,offset,limit:40});
  const result=await api('/history?'+q);if(requestId!==historyRequest)return;state.history=append?[...state.history,...result.items]:result.items;state.historyTotal=result.total;renderHistory();
}
function renameTrack(track){state.renameId=track.id;$('rename-value').value=track.title;$('rename-dialog').showModal();$('rename-value').focus();}
function renderHistory(){
  const list=$('history-list');list.replaceChildren();
  state.history.forEach(track=>{
    const row=node('article','library-item'),art=node('div','item-icon');art.append(icon('audio-waveform'));
    const info=node('button','item-info');info.append(node('span','item-title',track.title),node('small','item-detail',`${modeName(track.mode)} / ${timeText(track.duration)} / ${dateText(track.created)}`));info.onclick=()=>{player.set(track);showView('studio');};
    const controls=node('div','item-actions');
    const fav=button(t('action.favorite'),'star',action(async()=>{const updated=await api('/history/'+track.id,{method:'PATCH',body:{favorite:!track.favorite}});Object.assign(track,updated);if(player.track?.id===track.id)player.set(track);renderHistory();}));fav.classList.toggle('active',track.favorite);
    controls.append(fav,button(t('action.rename'),'edit',()=>renameTrack(track)),button(t('action.reuse'),'rotate-ccw',()=>restore(track.request)),button(t('action.downloadWav'),'download',()=>{const a=node('a');a.href=`/api/audio/${track.id}?download=true`;a.download='';a.click();}),button(t('action.delete'),'trash',action(async()=>{if(await confirmAction(t('confirm.deleteAudio'))){await api('/history/'+track.id,{method:'DELETE'});if(player.track?.id===track.id)player.clear();await loadHistory();}})));
    row.append(art,info,controls);list.append(row);
  });
  if(!state.history.length)list.append(node('div','library-empty',t('library.empty')));
  $('history-more').classList.toggle('hidden',state.history.length>=state.historyTotal);
}
function initSplitter(){
  const target=$('panel-splitter');const set=x=>{const r=$('workspace').getBoundingClientRect(),percent=Math.min(65,Math.max(38,(x-r.left)/r.width*100));document.documentElement.style.setProperty('--split',percent+'%');remember('split',percent);target.setAttribute('aria-valuenow',Math.round(percent));};
  target.setAttribute('aria-valuemin','38');target.setAttribute('aria-valuemax','65');const saved=Number(recall('split',55));const initial=Number.isFinite(saved)?Math.min(65,Math.max(38,saved)):55;
  document.documentElement.style.setProperty('--split',initial+'%');target.setAttribute('aria-valuenow',initial);
  target.ondblclick=()=>{document.documentElement.style.setProperty('--split','55%');remember('split',55);target.setAttribute('aria-valuenow','55');};
  target.addEventListener('pointerdown',event=>{target.setPointerCapture(event.pointerId);target.dataset.drag='1';});
  target.addEventListener('pointermove',event=>{if(target.dataset.drag)set(event.clientX);});
  for(const name of ['pointerup','pointercancel'])target.addEventListener(name,()=>delete target.dataset.drag);
  target.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();const value=Number(recall('split',55))+(event.key==='ArrowRight'?2:-2),r=$('workspace').getBoundingClientRect();set(r.left+value*r.width/100);}});
}
function bind(){
  $$('[data-mode]').forEach(b=>b.onclick=()=>setMode(b.dataset.mode));
  $$('[data-view]').forEach(b=>b.onclick=action(async()=>{showView(b.dataset.view);if(b.dataset.view==='history')await loadHistory();}));
  for(const id of ['history-shortcut'])$(id).onclick=action(async()=>{showView('history');await loadHistory();});
  $('back-to-studio').onclick=()=>showView('studio');$('model-select').onchange=modelChanged;
  $('speaker').onchange=()=>{if(state.selected&&$('speaker').value)remember('speaker.'+state.selected,$('speaker').value);saveDraft();};
  $('generate-btn').onclick=generate;$('clear-text').onclick=()=>{$('script-text').value='';updateCounters();saveDraft();$('script-text').focus();};
  const scheduleDraft=()=>{updateCounters();clearTimeout(draftTimer);draftTimer=setTimeout(saveDraft,250);};
  for(const id of ['script-text','voice-instruct','custom-instruct','ref-text','language',...Object.keys(params),...Object.keys(workflowFields)]){
    $(id).addEventListener('input',scheduleDraft);
    $(id).addEventListener('change',scheduleDraft);
  }
  $('advanced-settings').addEventListener('toggle',scheduleDraft);
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!document.querySelector('dialog[open]')&&!document.body.classList.contains('menu-open')){e.preventDefault();generate();}});
  $('settings-toggle').onclick=()=>settings.open();
  $('add-model-shortcut').onclick=()=>settings.open('models');
  $('refresh-models').onclick=action(()=>settings.scan());
  $('release-model').onclick=action(async()=>{await api('/models/unload',{method:'POST'});await updateSystem();toast(t('notice.unloaded'));});
  $('ref-file').onchange=action(e=>upload(e.target.files[0]));
  $('upload-zone').onclick=()=>{$('ref-file').value='';$('ref-file').click();};
  $('upload-zone').onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();$('ref-file').click();}};
  $('ref-file').onclick=e=>e.stopPropagation();
  for(const name of ['dragover','dragenter'])$('upload-zone').addEventListener(name,e=>{e.preventDefault();$('upload-zone').classList.add('dragging');});
  $('upload-zone').ondragleave=()=>$('upload-zone').classList.remove('dragging');
  $('upload-zone').ondrop=action(async e=>{e.preventDefault();$('upload-zone').classList.remove('dragging');await upload(e.dataTransfer.files[0]);});
  $('remove-ref').onclick=action(async()=>{if(state.reference)await api('/references/'+state.reference.id,{method:'DELETE'});state.reference=null;updateReference();saveDraft();});
  $('record-btn').onclick=action(async()=>{
    $('record-btn').disabled=true;try{
    if(recorder.active){const file=await recorder.stop();$('record-label').textContent=t('action.record');$('record-btn').classList.remove('active');if(file)await upload(file);}
    else{await recorder.start(()=>$('record-btn').click());$('record-label').textContent=t('action.stopRecording');$('record-btn').classList.add('active');}
    }finally{$('record-btn').disabled=false;}
  });
  window.addEventListener('beforeunload',()=>{saveDraft();recorder.abort();});
  for(const id of ['new-preset','add-preset'])$(id).onclick=()=>openPreset();
  $('restore-presets').onclick=action(restoreFactoryPresets);
  $$('.close-preset').forEach(x=>x.onclick=()=>$('preset-dialog').close());
  $('preset-form').onsubmit=action(async e=>{e.preventDefault();const body={name:$('preset-name').value,instruct:$('preset-instruct').value,language:$('language').value};await api('/presets'+(state.editingPreset?'/'+state.editingPreset:''),{method:state.editingPreset?'PUT':'POST',body});$('preset-dialog').close();await refreshPresets();toast(t('notice.presetSaved'));});
  $('reuse-output').onclick=()=>player.track&&restore(player.track.request);
  $('use-reference').onclick=action(async()=>{if(!player.track)return;const ref=await api('/history/'+player.track.id+'/reference',{method:'POST'});setMode('clone');state.reference=ref;updateReference();$('ref-text').value=ref.transcript||'';saveDraft();});
  $('favorite-output').onclick=action(async()=>{if(player.track)player.set(await api('/history/'+player.track.id,{method:'PATCH',body:{favorite:!player.track.favorite}}));});
  $('rename-form').onsubmit=action(async e=>{e.preventDefault();const updated=await api('/history/'+state.renameId,{method:'PATCH',body:{title:$('rename-value').value}});$('rename-dialog').close();if(player.track?.id===updated.id)player.set(updated);await loadHistory();});
  $('rename-cancel').onclick=()=>$('rename-dialog').close();
  $('export-metadata').onclick=action(async()=>{if(!player.track)return;const metadata=await api('/history/'+player.track.id+'/metadata');const b=new Blob([JSON.stringify(metadata,null,2)],{type:'application/json'}),a=node('a');a.href=URL.createObjectURL(b);a.download='voice-'+player.track.id.slice(0,8)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);});
  $('import-text').onclick=()=>$('text-file').click();
  $('text-file').onchange=action(async e=>{const file=e.target.files[0];if(!file)return;if(file.size>100000)throw new Error(t('error.textFileSize'));const text=await file.text();if(text.length>6000)throw new Error(t('error.textLength'));$('script-text').value=text;updateCounters();saveDraft();e.target.value='';});
  $('playback-rate').onchange=()=>{
    player.audio.playbackRate=Number($('playback-rate').value);
    remember('playbackRate',$('playback-rate').value);
  };
  $('export-format').onchange=()=>remember('exportFormat',$('export-format').value);
  $('history-refresh').onclick=action(()=>loadHistory());$('history-more').onclick=action(()=>loadHistory(true));
  for(const id of ['history-filter','favorites-only'])$(id).onchange=action(()=>{
    remember('history.'+id,$(id).type==='checkbox'?$(id).checked:$(id).value);
    return loadHistory();
  });
  $('history-search').oninput=()=>{
    rememberSession('history.search',$('history-search').value);
    clearTimeout(searchTimer);searchTimer=setTimeout(()=>loadHistory().catch(e=>toast(e.message,true)),250);
  };
  initSplitter();
}
function restoreUtilityPreferences(){
  for(const [id,key] of [['playback-rate','playbackRate'],['export-format','exportFormat'],['history-filter','history.history-filter']]){
    const select=$(id),saved=String(recall(key,select.value));
    if([...select.options].some(o=>o.value===saved&&!o.disabled))select.value=saved;
  }
  player.audio.playbackRate=Number($('playback-rate').value);
  $('favorites-only').checked=recall('history.favorites-only',false)===true;
  $('history-search').value=String(recallSession('history.search','')).slice(0,200);
}

function initLocaleEvents(){
  document.addEventListener('qvs:locale',()=>{
    $('workspace-title').textContent=modeName(state.mode);
    $('breadcrumb-current').textContent=state.view==='studio'?modeName(state.mode):t(state.view==='history'?'nav.library':'nav.presets');
    renderModels();updateCounters();renderJobs(true);renderPresets();renderHistory();
    if(!state.reference)$('reference-title').textContent=t('reference.drop');
    $('record-label').textContent=t(recorder.active?'action.stopRecording':'action.record');
    if(!systemSnapshot?.model?.loaded)$('runtime-sub').textContent=t('system.unloaded');
    player.relabel();settings.renderModels();settings.renderScanRoots();settings.updateRootEditor();refreshNavigation();
  });
  document.addEventListener('qvs:appearance',()=>player.draw());
  $('load-example').onclick=async()=>{
    if($('script-text').value.trim()&&!await confirmAction(t('confirm.replaceExample')))return;
    $('script-text').value=t('example.script');
    if(state.mode==='design')$('voice-instruct').value=t('example.instruct');
    $('language').value=getLocale()==='en'?'English':'Chinese';updateCounters();saveDraft();
  };
}

async function boot(){
  await initI18n();
  settings=new SettingsPanel({
    models:()=>state.models, runtime:()=>state.runtime,
    onModels:models=>{state.models=Array.isArray(models)?models:[];renderModels();},
    onRuntime:runtime=>{state.runtime=runtime;},
    onRegistered:model=>{state.selected=model.id;setMode(model.mode);}
  });
  bind();initAppearance();initNavigation();initLocaleEvents();restoreUtilityPreferences();

  let data;
  try{data=await api('/bootstrap');}
  catch(error){
    showFormError(t('error.init',{message:error.message}));
    toast(t('error.init',{message:error.message}),true);
    return;
  }
  setToken(data.token);
  settings.setCapabilities({nativeFolderPicker: Boolean(data.native_folder_picker)});
  state.models=Array.isArray(data.models)?data.models:[];
  state.presets=Array.isArray(data.presets)?data.presets:[];
  state.runtime=data.runtime||{device:'auto',gpu_gib:3,cpu_gib:12,attention:'sdpa'};
  configureDrafts(Boolean(data.preferences?.remember_drafts));
  $('demo-badge').classList.toggle('hidden',!data.demo);
  const mp3=document.querySelector('option[value=mp3]');if(mp3)mp3.disabled=!data.mp3;

  // Render critical content before optional settings/system initialization.
  // A broken control cannot blank all models and presets after refresh.
  renderPresets();
  const requested=recall('mode','design');
  const ready=state.models.filter(model=>(model.status||'ready')==='ready');
  const inMode=ready.some(model=>model.mode===requested);
  const last=ready.find(model=>model.id===recall('lastModel',''));
  const initial=inMode?requested:(last||ready[0])?.mode||(Object.hasOwn(typeNames,requested)?requested:'design');
  const lastView=recall('view','studio');
  setMode(initial,false);updateCounters();updateReference();
  if(lastView==='history'||lastView==='presets'){
    showView(lastView);
    if(lastView==='history')loadHistory().catch(error=>toast(error.message,true));
  }
  try{settings.init(data.preferences,state.runtime);}
  catch(error){console.error('Settings initialization failed',error);}

  const results=await Promise.allSettled([
    api('/jobs'),api('/history?limit=1'),updateSystem()
  ]);
  if(results[0].status==='fulfilled'){
    state.jobs=results[0].value;
    state.jobs.filter(j=>!['queued','loading','running','cancelling'].includes(j.status)).forEach(j=>state.seen.add(j.id));
  }
  renderJobs();
  if(results[1].status==='fulfilled'&&results[1].value.items?.length)
    player.set(results[1].value.items[0]);
  for(const result of results){if(result.status==='rejected')console.warn('Noncritical startup request failed:',result.reason);}
  pollLoop();
}

boot().catch(error=>{console.error(error);showFormError(error.message);});
