import {t} from './i18n.js';
import {$, $$, api, node, button, toast, action, confirmAction, configureDrafts, clearPreferences, remember, recall, rememberSession, recallSession, forgetSession} from './core.js';

const DEFAULT_PREFERENCES = {
  model_roots: ['models', '../models'], discover_hf_cache: true,
  auto_discover: true, scan_depth: 6, remember_drafts: false, hide_paths: true,
};
const DEFAULT_RUNTIME = {device: 'auto', gpu_gib: 3, cpu_gib: 12, attention: 'sdpa'};
const TABS = new Set(['appearance', 'models', 'runtime', 'privacy']);
const SETTINGS_FIELDS = [
  'scan-roots','scan-cache','scan-startup','scan-depth','remember-drafts',
  'hide-paths','gpu-budget','cpu-budget','attention','new-model-path',
];
const field = (id, property, value) => {
  const element = $(id);
  if (element) element[property] = value;
  return element;
};
const read = (id, property, fallback) => $(id)?.[property] ?? fallback;

export class SettingsPanel {
  constructor(callbacks) {
    this.callbacks = callbacks;
    this.preferences = {...DEFAULT_PREFERENCES};
    this.runtime = {...DEFAULT_RUNTIME};
    this.scanning = false;
    this.picking = false;
    this.lastScanPick = '';
    this.nativeFolderPicker = false;
    this.rootEditorOpen = null;
    this.dialogEpoch = 0;
    const dialog=$('settings-dialog');
    dialog.addEventListener('close', () => { this.dialogEpoch++; });
    dialog.querySelector('form').addEventListener('submit', event => event.preventDefault());
    dialog.querySelector('[value=cancel]').onclick = () => {this.clearPending();dialog.close();};
    dialog.addEventListener('cancel',()=>this.clearPending());
    const capture=event=>{
      if(event.target.matches('input[name=device]'))this.rememberPending();
      else if(SETTINGS_FIELDS.includes(event.target.id)){
        this.rememberPending();
        if(event.target.id==='hide-paths')this.renderScanRoots();
        if(event.target.id==='scan-roots')this.renderScanRoots();
      }
    };
    dialog.addEventListener('input',capture);
    dialog.addEventListener('change',capture);
    $('model-discovery').addEventListener('toggle',event=>remember('models.discovery',event.target.open));
    for (const tab of $$('[data-settings-tab]')) {
      tab.onclick = () => this.selectTab(tab.dataset.settingsTab);
      tab.onkeydown = event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const tabs = $$('[data-settings-tab]');
        const offset = event.key === 'ArrowRight' ? 1 : -1;
        const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 :
          (tabs.indexOf(tab) + offset + tabs.length) % tabs.length;
        this.selectTab(tabs[index].dataset.settingsTab);
        tabs[index].focus();
      };
    }
    // One action saves pending changes in ANY tab, including after switching
    // back to Appearance. Otherwise the Done button silently discarded edits.
    $('save-settings').onclick = action(async () => this.save());
    $('scan-models').onclick = action(() => this.scan(true));
    for(const radio of $$('input[name=device]'))radio.addEventListener('change',()=>this.refreshRuntimeFields());
    $('browse-model-path').onclick = action(() => this.chooseFolder('model'));
    $('browse-scan-root').onclick = action(() => this.chooseFolder('scan'));
    $('edit-scan-roots').onclick = () => {
      this.rootEditorOpen = !this.rootEditorOpen;
      this.updateRootEditor();
      if (this.rootEditorOpen) $('scan-roots').focus();
    };

    $('register-model').onclick = action(async () => {
      const path = read('new-model-path', 'value', '').trim();
      if (!path) { field('new-model-path', 'value', ''); $('new-model-path')?.focus(); return; }
      const model = await api('/models', {method: 'POST', body: {path}});
      this.callbacks.onModels(await api('/models'));
      this.callbacks.onRegistered(model);
      field('new-model-path', 'value', '');
      this.rememberPending();
      this.renderModels();
      toast(t('notice.modelAdded'));
    });
    $('diagnostics-export').onclick = action(async () => this.download(await api('/diagnostics'), 'diagnostics.json'));
    $('clear-local-data').onclick = action(async () => {
      if (!await confirmAction(t('confirm.clearData'))) return;
      await api('/privacy/clear', {method: 'POST', headers: {'X-Confirm-Clear': 'clear-local-history'}});
      clearPreferences();
      location.reload();
    });
  }

  init(preferences, runtime) {
    this.preferences = {...DEFAULT_PREFERENCES, ...(preferences || {})};
    this.runtime = {...DEFAULT_RUNTIME, ...(runtime || {})};
    const pref = this.preferences, rt = this.runtime;
    // Missing optional controls must never prevent model/preset initialization.
    // Reset the transient registration field; restorePending() rehydrates it
    // only when the dialog has an actual unsaved tab-session draft.
    field('new-model-path', 'value', '');
    field('scan-roots', 'value', (pref.model_roots || []).join('\n'));
    field('scan-cache', 'checked', Boolean(pref.discover_hf_cache));
    field('scan-startup', 'checked', Boolean(pref.auto_discover));
    field('scan-depth', 'value', pref.scan_depth);
    field('remember-drafts', 'checked', Boolean(pref.remember_drafts));
    field('hide-paths', 'checked', Boolean(pref.hide_paths));
    this.renderScanRoots();
    this.updateRootEditor();
    const radio = $$('input[name=device]').find(item => item.value === rt.device);
    if (radio) radio.checked = true;
    field('gpu-budget', 'value', rt.gpu_gib);
    field('cpu-budget', 'value', rt.cpu_gib);
    field('attention', 'value', rt.attention);
    this.refreshRuntimeFields();
    this.renderModels();
  }

  refreshRuntimeFields() {
    const device = document.querySelector('[name=device]:checked')?.value || 'auto';
    $('hybrid-fields').classList.toggle('hidden', device !== 'hybrid');
  }

  rememberPending(){
    const value={};
    for(const id of SETTINGS_FIELDS){const element=$(id);if(element)value[id]=element.type==='checkbox'?element.checked:element.value;}
    value.device=$('settings-dialog').querySelector('input[name=device]:checked')?.value;
    rememberSession('settings.pending',value);
  }

  restorePending(){
    const value=recallSession('settings.pending',null);
    if(!value||typeof value!=='object')return;
    for(const id of SETTINGS_FIELDS){
      const element=$(id),stored=value[id];if(!element||stored===undefined)continue;
      if(element.type==='checkbox')element.checked=stored===true;
      else if(element.tagName==='SELECT'){
        if([...element.options].some(option=>option.value===stored))element.value=stored;
      }else element.value=String(stored);
    }
    const radio=$$('input[name=device]').find(element=>element.value===value.device);
    if(radio)radio.checked=true;
    this.renderScanRoots();
    this.refreshRuntimeFields();
  }

  clearPending(){forgetSession('settings.pending');}

  open(tab = 'appearance') {
    this.dialogEpoch++;
    this.init(this.preferences, this.callbacks.runtime() || this.runtime);
    this.restorePending();
    $('model-discovery').open=recall('models.discovery',false)===true;
    this.selectTab(tab);
    if (!$('settings-dialog').open) $('settings-dialog').showModal();
  }

  selectTab(id) {
    if (!TABS.has(id)) id = 'appearance';
    this.activeTab=id;
    const primary=$('settings-primary-label');
    primary.dataset.i18n='action.save';
    primary.textContent=t(primary.dataset.i18n);
    field('settings-feedback', 'textContent', '');
    for (const tab of $$('[data-settings-tab]')) {
      const active = tab.dataset.settingsTab === id;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
    }
    for (const panel of $$('#settings-dialog [role=tabpanel]'))
      panel.classList.toggle('hidden', panel.id !== 'tab-' + id);
  }

  scanRoots() {
    return String(read('scan-roots', 'value', '')).split(/\r?\n/).map(value=>value.trim()).filter(Boolean);
  }

  rootKey(path) {
    // On Windows, drive-letter paths compare case-insensitively and slashes
    // are interchangeable. Relative model root names keep their spelling.
    return (this.nativeFolderPicker ? path.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase() : path.replace(/\/+$/, ''));
  }

  setCapabilities(capabilities = {}) {
    this.nativeFolderPicker = capabilities.nativeFolderPicker === true;
    for(const id of ['browse-model-path','browse-scan-root']) {
      $(id)?.classList.toggle('hidden', !this.nativeFolderPicker);
    }
    if (this.rootEditorOpen === null) this.rootEditorOpen = !this.nativeFolderPicker;
    this.updateRootEditor();
  }

  updateRootEditor() {
    $('scan-root-editor')?.classList.toggle('hidden', !this.rootEditorOpen);
    $('edit-scan-roots')?.setAttribute('aria-expanded', String(Boolean(this.rootEditorOpen)));
    const label=$('edit-scan-roots')?.querySelector('span');
    if(label){
      label.dataset.i18n=this.rootEditorOpen?'action.collapseManualPaths':'action.manualPaths';
      label.textContent=t(label.dataset.i18n);
    }
    // Non-Windows hosts still have an editable manual path form.
    if ($('browse-scan-root')) $('browse-scan-root').disabled = this.picking;
    if ($('browse-model-path')) $('browse-model-path').disabled = this.picking;
  }

  renderScanRoots() {
    const list = $('scan-roots-list');
    if (!list) return;
    list.replaceChildren();
    const roots = this.scanRoots();
    field('scan-root-count', 'textContent', String(roots.length));
    if (!roots.length) list.append(node('p', 'scan-root-empty', t('settings.emptyRoots')));
    for (const root of roots) {
      const row = node('div', 'scan-root-entry');
      const path = node('span', 'scan-root-path', root);
      path.tabIndex = 0;
      path.classList.toggle('private-path', Boolean(read('hide-paths', 'checked', true)));
      row.append(path);
      row.append(button(t('settings.removeRoot'), 'x', () => {
        const key = this.rootKey(root);
        const remaining = this.scanRoots().filter(value => this.rootKey(value) !== key);
        $('scan-roots').value = remaining.join('\n');
        this.rememberPending();
        this.renderScanRoots();
      }));
      list.append(row);
    }
    $('scan-roots')?.classList.toggle('private-path', Boolean(read('hide-paths', 'checked', true)));
  }

  addScanRoot(value) {
    const selected = String(value || '').trim();
    if (!selected) return false;
    const roots = this.scanRoots(), key = this.rootKey(selected);
    if (roots.some(root => this.rootKey(root) === key)) {toast(t('settings.folderDuplicate'));return false;}
    if (roots.length >= 128) {toast(t('settings.rootLimit'), true);return false;}
    $('scan-roots').value = [...roots, selected].join('\n');
    this.rememberPending();
    this.renderScanRoots();
    return true;
  }

  async chooseFolder(purpose) {
    if (!this.nativeFolderPicker || this.picking) return;
    const dialog = $('settings-dialog'), epoch = this.dialogEpoch;
    const initial_path = purpose === 'model' ? $('new-model-path').value.trim() : (this.lastScanPick || this.scanRoots().at(-1) || '');
    this.picking = true;
    this.updateRootEditor();
    try {
      const result = await api('/native/folder', {method:'POST', body:{purpose, initial_path:initial_path || null}});
      // A dialog may be closed/reopened while the OS chooser is still active.
      if (!dialog.open || epoch !== this.dialogEpoch || result.cancelled || !result.path) return;
      if (purpose === 'model') {
        $('new-model-path').value = result.path;
        this.rememberPending();
      } else {
        this.lastScanPick = result.path;
        this.addScanRoot(result.path);
      }
    } finally {
      this.picking = false;
      this.updateRootEditor();
    }
  }

  collectPreferences() {
    return {
      ...this.preferences,
      model_roots: this.scanRoots(),
      discover_hf_cache: Boolean(read('scan-cache', 'checked', this.preferences.discover_hf_cache)),
      auto_discover: Boolean(read('scan-startup', 'checked', this.preferences.auto_discover)),
      scan_depth: Number(read('scan-depth', 'value', this.preferences.scan_depth)),
      remember_drafts: Boolean(read('remember-drafts', 'checked', this.preferences.remember_drafts)),
      hide_paths: Boolean(read('hide-paths', 'checked', this.preferences.hide_paths)),
    };
  }

  async save() {
    const selected = document.querySelector('[name=device]:checked')?.value || this.runtime.device;
    if (selected === 'cuda_fp16' && this.runtime.device !== selected &&
        !await confirmAction(t('confirm.fp16'))) return;
    const preferences = this.collectPreferences();
    const runtime = {
      device: selected,
      gpu_gib: Number(read('gpu-budget', 'value', this.runtime.gpu_gib)),
      cpu_gib: Number(read('cpu-budget', 'value', this.runtime.cpu_gib)),
      attention: read('attention', 'value', this.runtime.attention),
    };
    const save = $('save-settings'); save.disabled = true;
    try {
      const prefChanged=JSON.stringify(preferences)!==JSON.stringify(this.preferences);
      const runtimeChanged=JSON.stringify(runtime)!==JSON.stringify(this.runtime);
      const discoveryChanged=['model_roots','discover_hf_cache','auto_discover','scan_depth']
        .some(key=>JSON.stringify(preferences[key])!==JSON.stringify(this.preferences[key]));
      const savedPreferences=prefChanged?await api('/preferences',{method:'PUT',body:preferences}):this.preferences;
      const savedRuntime=runtimeChanged?await api('/runtime',{method:'PUT',body:runtime}):this.runtime;
      this.callbacks.onRuntime(savedRuntime);
      configureDrafts(savedPreferences.remember_drafts);
      this.init(savedPreferences, savedRuntime);
      if(discoveryChanged){this.callbacks.onModels(await api('/models/scan',{method:'POST'}));}
      field('settings-feedback', 'textContent', t('notice.saved'));
      // Save runtime/preferences without keeping the settings dialog open as a second workflow.
      $('settings-dialog').close();
      this.clearPending();
      toast(t('notice.saved'));
    } finally { save.disabled = false; }
  }

  async scan(applyPending = false) {
    if (this.scanning) return;
    this.scanning = true;
    for (const id of ['scan-models', 'refresh-models']) field(id, 'disabled', true);
    try {
      if (applyPending) {
        // "Save & scan" applies folder changes first, without committing unrelated
        // appearance/privacy/runtime edits still pending in other tabs.
        const next = this.collectPreferences();
        const keys = ['model_roots','discover_hf_cache','auto_discover','scan_depth'];
        if (keys.some(key => JSON.stringify(next[key]) !== JSON.stringify(this.preferences[key]))) {
          const body = {...this.preferences};
          for (const key of keys) body[key] = next[key];
          this.preferences = await api('/preferences', {method:'PUT', body});
          this.rememberPending();
        }
      }
      this.callbacks.onModels(await api('/models/scan', {method: 'POST'}));
      this.renderModels();
      toast(t('notice.modelsUpdated'));
    } finally {
      this.scanning = false;
      for (const id of ['scan-models', 'refresh-models']) field(id, 'disabled', false);
    }
  }

  renderModels() {
    const list = $('model-library');
    if (!list) return;
    list.replaceChildren();
    const models = this.callbacks.models() || [];
    field('model-count','textContent',String(models.length));
    for (const model of models) {
      const row = node('div', 'model-item'), info = node('div', 'model-item-info');
      info.append(node('strong', '', model.name), node('small', '',
        `${model.id.slice(0, 6)}${model.weight_bytes ? ' / ' + (model.weight_bytes / 1024 ** 3).toFixed(2) + ' GiB' : ''}`));
      const status = model.status || 'ready';
      const statusText = {ready: t('model.ready'), missing: t('model.missing'), incomplete: t('model.incomplete')}[status] || status;
      const badge = node('span', 'model-status ' + status, statusText);
      if (model.issues?.length) {
        const details = node('details', 'model-issues');
        details.append(node('summary', '', t('model.checkFiles')), node('p', '', model.issues.join('\n')));
        info.append(details);
      }
      row.append(info);
      if(status!=='ready')row.append(badge);
      row.append(button(t('action.unregister'), 'trash', action(async () => {
        if (!await confirmAction(t('confirm.unregister'))) return;
        await api('/models/' + model.id, {method: 'DELETE'});
        this.callbacks.onModels(await api('/models'));
        this.renderModels();
      }))); 
      list.append(row);
    }
    if (!models.length) list.append(node('p', 'muted-empty', t('models.emptyHint')));
  }

  download(value, name) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json'}));
    const anchor = node('a'); anchor.href = url; anchor.download = name; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
