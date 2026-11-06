"""UI integration with a live local API and an explicit test-tone backend.

Default uses normal browser navigation. --mount enables the documented
restricted-container adapter; this does not test native browser security/storage.
"""
from pathlib import Path
import argparse
import json
import socket
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mount', action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/browser')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    results=[];errors=[];external=[]
    def check(name,condition):
        results.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='qvs-browser-') as data:
        log=(args.output/'server.log').open('w')
        process=subprocess.Popen([sys.executable,str(ROOT/'tests/browser_server.py'),'--port',str(port),'--data',data],stdout=log,stderr=log)
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base+'/api/health',timeout=1) as response:
                        if response.status==200:break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Test server did not start')
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
                page=context.new_page();page.set_default_timeout(6000)
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('request',lambda request:external.append(request.url) if not request.url.startswith(base) and not request.url.startswith(('blob:','data:')) else None)
                if args.mount:
                    from browser_mount import mount
                    bridge_client=mount(page,ROOT,base)
                else:page.goto(base)
                page.wait_for_selector('#model-select option[value="demo_design"]',state='attached')
                def exported(button):
                    if args.mount:
                        count=page.evaluate('window.__exports.length')
                        page.locator(button).click()
                        page.wait_for_function('(n)=>window.__exports.length>n',arg=count)
                        return page.evaluate('window.__exports.at(-1)')
                    with page.expect_download() as download:page.locator(button).click()
                    path=Path(download.value.path())
                    return {'name':download.value.suggested_filename,'size':path.stat().st_size,'text':path.read_text(errors='replace')}

                check('bootstrap and model selection',page.locator('#model-select').input_value()=='demo_design')
                check('unique DOM IDs',page.evaluate('''()=>{const ids=[...document.querySelectorAll('[id]')].map(x=>x.id);return new Set(ids).size===ids.length;}'''))
                page.locator('#script-text').fill('A warm voice makes every word feel closer.')
                page.locator('#voice-instruct').fill('An adult narrator, warm and calm, clear pronunciation.')
                page.locator('#generate-btn').click()
                page.wait_for_selector('#active-output:not(.hidden)',timeout=15000)
                check('generation and playback source',bool(page.locator('#audio-player').get_attribute('src')))
                check('real waveform canvas',page.locator('#wave-canvas').evaluate('(canvas)=>canvas.width>0 && canvas.height>0'))
                page.locator('#play-btn').click();page.wait_for_timeout(120)
                check('audio playback',page.locator('#audio-player').evaluate('(audio)=>!audio.paused'))
                page.locator('#play-btn').click()
                page.locator('#playback-rate').select_option('1.25')
                check('playback speed',page.locator('#audio-player').evaluate('(audio)=>audio.playbackRate===1.25'))
                download=exported('#download-audio')
                check('WAV export bytes and filename',download['name'].endswith('.wav') and download['size']>44)
                content=exported('#export-metadata')['text']
                check('metadata excludes text and filesystem', 'A warm voice' not in content and 'sampling' in content and 'path' not in content)
                page.locator('#settings-toggle').click()
                check('settings open',page.locator('#settings-dialog').is_visible())
                check('single settings entry', page.locator('#settings-toggle').count()==1 and page.locator('#density-toggle,#open-settings-from-sidebar,#layout-toggle,#theme-toggle').count()==0)
                check('take count is advanced only',page.locator('#advanced-settings #variations').count()==1)

                check('models displayed',page.locator('.model-item').count()==3)
                page.locator('[data-settings-tab=privacy]').click()
                check('privacy default no persistent drafts',not page.locator('#remember-drafts').is_checked())
                check('no localStorage transcript',page.evaluate("()=>!Object.keys(localStorage).some(k=>k.startsWith('qvs.draft.'))"))
                content=exported('#diagnostics-export')['text']
                check('diagnostics excludes prompt and executable', 'A warm voice' not in content and 'executable' not in content)
                page.locator('[data-settings-tab=runtime]').click()
                check('inference choices remain user-selectable',all(not el.is_disabled() for el in page.locator('input[name=device]').all()))
                page.locator('input[name=device][value=hybrid]').check()
                check('hybrid budgets exposed only when used',page.locator('#hybrid-fields').is_visible())
                page.locator('input[name=device][value=cpu]').check()
                check('unused hybrid budgets hidden',not page.locator('#hybrid-fields').is_visible())
                page.locator('#save-settings').click()
                page.wait_for_function('!document.getElementById("settings-dialog").open')
                check('runtime saved',page.request.get(base+'/api/bootstrap').json()['runtime']['device']=='cpu')
                page.locator('#settings-toggle').click();page.locator('[data-settings-tab=models]').click()
                check('paths obscured by default',page.locator('#scan-roots').evaluate('(e)=>e.classList.contains("private-path")'))
                page.locator('#scan-models').click();page.wait_for_timeout(300)
                check('rescan keeps model selection',page.locator('.model-item').count()==3)
                page.locator('#settings-dialog button[value=cancel]').click()
                page.locator('[data-mode=custom]').click();page.wait_for_timeout(100)
                check('custom mode speaker enumeration',page.locator('#speaker option').count()==2)
                check('selectable CustomVoice speaker',not page.locator('#speaker').is_disabled())
                page.evaluate('''() => {window.__modelsBackup=state.models; state.models=state.models.filter(x=>x.mode!=='custom'); renderModels();}''')
                check('missing CustomVoice model has informative selector',page.locator('#speaker').is_disabled() and page.locator('#speaker option').count()==1 and bool(page.locator('#speaker-hint').inner_text()))
                page.evaluate('''() => {state.models=window.__modelsBackup.map(x=>x.mode==='custom'?{...x,speakers:[]}:x);renderModels();}''')
                check('missing speaker metadata is not an empty menu',page.locator('#speaker').is_disabled() and page.locator('#speaker option').count()==1)
                page.evaluate('''() => {state.models=window.__modelsBackup; renderModels();}''')
                check('speaker selector recovers after re-discovery',page.locator('#speaker option').count()==2 and not page.locator('#speaker').is_disabled())
                page.locator('[data-mode=clone]').click();page.wait_for_timeout(100)
                check('clone mode reference controls',page.locator('#upload-zone').is_visible())
                page.locator('#use-reference').click();page.wait_for_timeout(200)
                check('design result to reference',not page.locator('#remove-ref').is_disabled())
                check('consent resets after reference change',not page.locator('#voice-consent').is_checked())
                page.locator('#voice-consent').check();page.locator('#script-text').fill('A new line using the reference.')
                page.locator('#generate-btn').click();page.wait_for_timeout(1400)
                check('clone request accepted',not page.locator('#form-error').is_visible())
                page.locator('[data-view=history]').click();page.wait_for_selector('.library-item')
                check('history loaded',page.locator('.library-item').count()>=1)
                page.locator('#back-to-studio').click()
                page.locator('#settings-toggle').click()
                page.locator('#interface-layout').select_option('stack')
                check('stack layout',page.locator('body').get_attribute('data-layout')=='stack')
                page.locator('#interface-layout').select_option('split')
                check('split layout',page.locator('body').get_attribute('data-layout')=='split')
                page.locator('#interface-theme').select_option('dark')
                check('theme switch',page.locator('body').get_attribute('data-theme')=='dark')
                page.locator('#save-settings').click()
                for width in (320,375,768,1024,1440,1920):
                    page.set_viewport_size({'width':width,'height':960});page.wait_for_timeout(80)
                    check(f'no page overflow at {width}px',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                    # Settings are reachable through the top bar at every breakpoint.
                    page.locator('#settings-toggle').click()
                    check(f'settings usable at {width}px',page.locator('#settings-dialog').evaluate('(e)=>e.getBoundingClientRect().width<=innerWidth'))
                    page.locator('[data-settings-tab=privacy]').click()
                    check(f'privacy actions fit at {width}px',page.locator('#clear-local-data').evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth+1'))
                    page.locator('#settings-dialog button[value=cancel]').click()
                page.set_viewport_size({'width':1440,'height':1000})
                page.locator('[data-mode=design]').click()
                page.locator('#settings-toggle').click()
                page.locator('#interface-theme').select_option('dark');page.locator('#save-settings').click()
                page.screenshot(path=str(args.output/'studio-dark.png'),full_page=True)
                page.locator('#settings-toggle').click()
                page.locator('#interface-theme').select_option('light');page.locator('#save-settings').click()
                page.screenshot(path=str(args.output/'studio-light.png'),full_page=True)
                page.locator('#settings-toggle').click();page.locator('[data-settings-tab=models]').click()
                page.screenshot(path=str(args.output/'settings.png'),full_page=True)
                page.locator('#settings-dialog button[value=cancel]').click()
                page.set_viewport_size({'width':375,'height':850});page.screenshot(path=str(args.output/'studio-mobile.png'),full_page=True)
                page.evaluate("['toast-a','toast-b','toast-c','toast-d'].forEach(value=>toast(value))")
                check('notice stack capped at three',page.locator('#toasts .toast').count()==3)
                page.evaluate("toast('toast-d')")
                check('repeated notice deduplicates',page.locator('#toasts .toast').count()==3)
                page.wait_for_timeout(3800)
                check('successful notices expire automatically',page.locator('#toasts .toast').count()==0)
                check('no runtime JavaScript exceptions',not errors)
                check('no external requests',not external)
                page.evaluate('for(let i=1;i<10000;i++){clearInterval(i);clearTimeout(i);}')
                page.close()
                browser.close()
                if args.mount:bridge_client.close()
        finally:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            log.close()
            report={'backend':'test-tone (not real inference)','transport':'mounted UI + real localhost HTTP bridge' if args.mount else 'native localhost HTTP', 'limitations': ['synthetic inference, no GPU/model validation']+(['in-memory storage shim; native browser navigation, CSP, microphone and downloads unverified'] if args.mount else []),'checks':results,'errors':errors,'external_requests':external}
            (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'{len(results)} browser checks passed')


if __name__=='__main__':main()
