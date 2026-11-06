"""State restoration and layout regression using an isolated browser/HTTP bridge.

A second page seeded from the first page's storage simulates refresh and a new
browser session; this is not a native Chromium localhost persistence test.
"""
from pathlib import Path
import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright
from browser_mount import mount

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/persistence')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    checks=[]
    errors=[]
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        print(name, 'OK' if ok else 'FAIL', flush=True)
        if not ok:raise AssertionError(name)
    def snapshot(page):
        return page.evaluate('''() => ({
          local:Object.fromEntries(Object.entries(localStorage).filter(([k])=>k.startsWith('qvs.'))),
          session:Object.fromEntries(Object.entries(sessionStorage).filter(([k])=>k.startsWith('qvs.')))
        })''')
    with tempfile.TemporaryDirectory(prefix='qvs-state-') as data:
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        base=f'http://127.0.0.1:{port}'
        log=(args.output/'server.log').open('w')
        process=subprocess.Popen([sys.executable,str(ROOT/'tests/browser_server.py'),
                                  '--port',str(port),'--data',data],stdout=log,stderr=log)
        bridges=[]
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base+'/api/health',timeout=1)
                    break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Server unavailable')
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path=shutil.which('chromium'),args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':1440,'height':940},locale='zh-CN',reduced_motion='reduce')
                def new_page(seed=None):
                    page=context.new_page();page.set_default_timeout(7500)
                    page.on('pageerror',lambda err:errors.append(str(err)))
                    bridges.append(mount(page,ROOT,base,seed))
                    page.wait_for_selector('#model-select option[value^="demo_"]',state='attached')
                    return page
                p=new_page()
                check('sidebar model area is compact',p.locator('.model-control').evaluate('(e)=>e.getBoundingClientRect().height<110'))
                check('no duplicated model help in sidebar',p.locator('.model-auto-hint,#model-task-tag').count()==0)
                p.locator('[data-mode=custom]').click()
                p.locator('#speaker').select_option('Ryan')
                p.locator('#script-text').fill('A persistent script across a refresh.')
                p.locator('#custom-instruct').fill('Quiet, deliberate, clear.')
                p.locator('#language').select_option('Japanese')
                p.locator('#advanced-settings summary').click()
                p.locator('#variations').select_option('3')
                p.locator('#split-lines').check()
                p.locator('#split-text').check()
                p.locator('#chunk-chars').fill('240')
                p.locator('#pause-ms').fill('600')
                p.locator('#seed').fill('42')
                # Player controls are hidden until a result is available;
                # exercise their actual event handlers without generating audio.
                p.evaluate('''() => {
                    for(const [id,value] of [['playback-rate','1.5'],['export-format','flac']]){
                      const el=document.getElementById(id);
                      el.value=value;el.dispatchEvent(new Event('change',{bubbles:true}));
                    }
                }''')
                p.locator('[data-view=history]').click()
                p.locator('#history-filter').select_option('custom')
                p.locator('#favorites-only').check()
                p.locator('#history-search').fill('needle')
                p.locator('[data-mode=custom]').click()
                p.locator('#settings-toggle').click()
                p.locator('[name=font-preset][value=editorial]').check()
                check('font choice stays below 92px',p.locator('.type-card').first.evaluate('(e)=>e.getBoundingClientRect().height<=92'))
                p.locator('#interface-density').select_option('compact')
                p.locator('#interface-theme').select_option('dark')
                p.locator('[data-settings-tab=models]').click()
                check('advanced scan controls collapsed',not p.locator('#scan-roots').is_visible())
                p.locator('#model-discovery summary').click()
                p.locator('#new-model-path').fill('D:/MyModels/Work')
                p.locator('[data-settings-tab=runtime]').click()
                p.locator('input[name=device][value=hybrid]').check()
                p.locator('#gpu-budget').fill('6.5')
                p.wait_for_timeout(400)
                initial=snapshot(p)
                check('text is session-only with default privacy',
                      'qvs.draft.custom' in initial['session'] and
                      'qvs.draft.custom' not in initial['local'] and
                      'A persistent script' not in str(initial['local']))
                check('ordinary controls durable',
                      'qvs.workflow.custom' in initial['local'] and
                      'qvs.speaker.demo_custom' in initial['local'])
                other_tab=new_page({'local':initial['local'],'session':{}})
                check('private draft is not shared with a new tab',
                      other_tab.locator('#script-text').input_value()=='' and
                      'qvs.draft.custom' not in snapshot(other_tab)['session'])
                other_tab.close()
                p.close()
                p=new_page(initial)
                check('selected mode and speaker survive refresh',
                      p.locator('#view-studio').is_visible() and
                      p.locator('[data-mode=custom]').get_attribute('aria-current')=='page' and
                      p.locator('#speaker').input_value()=='Ryan')
                check('script and instruction restored',
                      p.locator('#script-text').input_value()=='A persistent script across a refresh.' and
                      p.locator('#custom-instruct').input_value()=='Quiet, deliberate, clear.')
                check('language and sampling restored',
                      p.locator('#language').input_value()=='Japanese' and
                      p.locator('#seed').input_value()=='42')
                check('batching and segmentation restored',
                      p.locator('#advanced-settings').evaluate('(e)=>e.open') and
                      p.locator('#variations').input_value()=='3' and
                      p.locator('#split-lines').is_checked() and
                      p.locator('#split-text').is_checked() and
                      p.locator('#chunk-chars').input_value()=='240' and
                      p.locator('#pause-ms').input_value()=='600')
                check('player and library filters restored',
                      p.locator('#playback-rate').input_value()=='1.5' and
                      p.locator('#export-format').input_value()=='flac' and
                      p.locator('#history-filter').input_value()=='custom' and
                      p.locator('#favorites-only').is_checked() and
                      p.locator('#history-search').input_value()=='needle')
                check('appearance restored',
                      p.locator('html').get_attribute('data-font')=='editorial' and
                      p.locator('html').get_attribute('data-theme')=='dark' and
                      p.locator('html').get_attribute('data-density')=='compact')
                p.locator('#settings-toggle').click()
                p.locator('[data-settings-tab=models]').click()
                check('unsubmitted model path and scan section restored',
                      p.locator('#new-model-path').input_value()=='D:/MyModels/Work' and
                      p.locator('#model-discovery').evaluate('(e)=>e.open'))
                p.locator('[data-settings-tab=runtime]').click()
                check('unsubmitted runtime controls restored',
                      p.locator('input[name=device][value=hybrid]').is_checked() and
                      p.locator('#gpu-budget').input_value()=='6.5')
                # Closing on Appearance must not silently discard changes made in other tabs.
                p.locator('[data-settings-tab=appearance]').click()
                p.locator('#save-settings').click()
                p.wait_for_function('!document.getElementById("settings-dialog").open')
                check('saving from appearance persists other tabs',
                      p.request.get(base+'/api/bootstrap').json()['runtime']['device']=='hybrid')
                check('successful save clears pending form',
                      'qvs.settings.pending' not in snapshot(p)['session'])
                # Explicitly opt in to durable text storage.
                p.locator('#settings-toggle').click();p.locator('[data-settings-tab=privacy]').click()
                p.locator('#remember-drafts').check()
                p.locator('#save-settings').click()
                p.wait_for_function('!document.getElementById("settings-dialog").open')
                stored=snapshot(p)
                check('draft moves to durable storage on opt-in',
                      'qvs.draft.custom' in stored['local'] and 'qvs.draft.custom' not in stored['session'])
                p.close()
                p=new_page({'local':stored['local'],'session':{}})
                check('draft persists into a fresh browser session when enabled',
                      p.locator('#script-text').input_value()=='A persistent script across a refresh.')
                p.locator('#settings-toggle').click();p.locator('[data-settings-tab=privacy]').click()
                p.locator('#remember-drafts').uncheck();p.locator('#save-settings').click()
                p.wait_for_function('!document.getElementById("settings-dialog").open')
                demoted=snapshot(p)
                check('disabling retention removes durable transcript',
                      'qvs.draft.custom' not in demoted['local'] and
                      'qvs.draft.custom' in demoted['session'])
                for width in (320,375,768,1024,1440,1920):
                    p.set_viewport_size({'width':width,'height':950})
                    check(f'workspace no horizontal overflow at {width}',
                          p.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                    p.locator('#settings-toggle').click()
                    check(f'settings no horizontal overflow at {width}',
                          p.locator('#settings-dialog').evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth+1'))
                    check(f'font cards compact at {width}',
                          p.locator('.type-card').first.evaluate('(e)=>e.getBoundingClientRect().height<=92'))
                    p.locator('#settings-dialog button[value=cancel]').click()
                p.set_viewport_size({'width':1440,'height':940})
                p.locator('#settings-toggle').click()
                p.screenshot(path=str(args.output/'settings-compact.png'),full_page=True)
                p.locator('[data-settings-tab=models]').click()
                p.screenshot(path=str(args.output/'models-compact.png'),full_page=True)
                p.locator('#settings-dialog button[value=cancel]').click()
                p.screenshot(path=str(args.output/'studio-compact.png'),full_page=True)
                # Reference files are persisted server-side, but the editor must
                # revalidate their identifiers after refresh and never persist consent.
                p.locator('[data-mode=design]').click()
                p.locator('#script-text').fill('A reference restoration test sentence.')
                p.locator('#voice-instruct').fill('Clear adult voice.')
                p.locator('#generate-btn').click()
                p.wait_for_selector('#active-output:not(.hidden)',timeout=15000)
                p.locator('#use-reference').click()
                p.wait_for_function('state.mode==="clone" && state.reference && !document.getElementById("remove-ref").disabled')
                p.locator('#ref-text').fill('A reference restoration test sentence.')
                p.locator('#voice-consent').check()
                ref_seed=snapshot(p)
                check('reference identifier is only in session storage',
                      'qvs.draft.clone' in ref_seed['session'] and
                      'qvs.draft.clone' not in ref_seed['local'])
                reference_id=p.evaluate('state.reference.id')
                p.close();p=new_page(ref_seed)
                p.wait_for_function('state.mode==="clone" && state.reference?.duration>0')
                check('reference metadata revalidated after refresh',
                      p.evaluate('(id)=>state.reference.id===id',reference_id) and
                      not p.locator('#remove-ref').is_disabled())
                check('reference consent never restored automatically',
                      not p.locator('#voice-consent').is_checked())
                p.evaluate('async()=>{await api("/references/"+state.reference.id,{method:"DELETE"})}')
                orphan_seed=snapshot(p)
                p.close();p=new_page(orphan_seed)
                p.wait_for_function('!state.reference')
                check('missing reference is removed from editor',
                      p.locator('#remove-ref').is_disabled())
                p.locator('#settings-toggle').click()
                p.locator('[data-settings-tab=models]').click()
                p.locator('#new-model-path').fill('D:/discard-this-path')
                p.locator('#settings-dialog button[value=cancel]').click()
                p.locator('#settings-toggle').click()
                p.locator('[data-settings-tab=models]').click()
                check('Cancel discards pending model path',
                      p.locator('#new-model-path').input_value()=='' and
                      'qvs.settings.pending' not in snapshot(p)['session'])
                p.locator('#settings-dialog button[value=cancel]').click()
                p.evaluate('clearPreferences()')
                erased=snapshot(p)
                check('clearing browser preferences erases both storage tiers',
                      not erased['local'] and not erased['session'])
                check('no JavaScript exceptions',not errors)
                browser.close()
        finally:
            for bridge in bridges:bridge.close()
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill()
            log.close()
    (args.output/'report.json').write_text(json.dumps({'checks':checks,'errors':errors,
        'limits':'mounted browser with synthetic audio; not native browser storage or real inference'},indent=2),encoding='utf-8')
    print(f'{len(checks)} persistence and layout checks passed')

if __name__=='__main__':main()
