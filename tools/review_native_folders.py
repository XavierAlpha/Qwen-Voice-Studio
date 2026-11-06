"""Browser regression with a fake Windows folder picker; no actual OS dialog."""
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

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mount',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/native-folders')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[]
    def check(title,condition):
        checks.append({'name':title,'passed':bool(condition)})
        if not condition:raise AssertionError(title)
    with socket.socket() as socket_:socket_.bind(('127.0.0.1',0));port=socket_.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='qvs-native-') as data:
        with (args.output/'server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,str(ROOT/'tests/browser_server.py'), '--port',str(port), '--data',data,'--fake-picker'],stdout=log,stderr=log)
        bridge=None
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base+'/api/health',timeout=1)
                    break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('No fake API server')
            with sync_playwright() as play:
                browser=play.chromium.launch(headless=True,executable_path=shutil.which('chromium'),args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1360,'height':920},locale='zh-CN',color_scheme='light',reduced_motion='reduce')
                page.set_default_timeout(7500)
                page.on('pageerror',lambda e:errors.append(str(e)))
                if args.mount:
                    from browser_mount import mount
                    bridge=mount(page,ROOT,base)
                else:page.goto(base)
                page.wait_for_selector('#model-select option[value="demo_design"]',state='attached')
                page.locator('#settings-toggle').click()
                page.locator('[data-settings-tab=models]').click()
                check('Windows native browse actions displayed',page.locator('#browse-model-path').is_visible() and page.locator('#browse-scan-root').count()==1)
                page.locator('#browse-model-path').click()
                page.wait_for_function('document.getElementById("new-model-path").value.endsWith("picker-model")')
                check('selected directory fills registration input',page.locator('#new-model-path').input_value().endswith('picker-model'))
                page.locator('#register-model').click()
                page.wait_for_function('document.getElementById("new-model-path").value === ""')
                check('native-chosen local model registers',page.locator('#model-library .model-item').count()>=4)
                page.locator('#model-discovery summary').click()
                before=page.locator('.scan-root-entry').count()
                check('scan roots list uses compact rows',before>=2 and not page.locator('#scan-root-editor').is_visible())
                page.locator('#browse-scan-root').click()
                page.wait_for_function('document.getElementById("scan-roots").value.includes("scan-A")')
                page.locator('#browse-scan-root').click()
                page.wait_for_function('document.getElementById("scan-roots").value.includes("scan-B")')
                check('repeat native selection appends rather than replaces',page.locator('.scan-root-entry').count()==before+2)
                page.locator('#browse-scan-root').click()
                page.wait_for_timeout(350)
                check('duplicate native selection is ignored',page.locator('.scan-root-entry').count()==before+2)
                page.locator('#browse-scan-root').click()
                page.wait_for_timeout(350)
                check('cancelled system picker does not modify list',page.locator('.scan-root-entry').count()==before+2)
                check('private-path visual mask applies to each row',page.locator('.scan-root-path.private-path').count()==before+2)
                page.screenshot(path=str(args.output/'models-native-folders.png'),full_page=False)
                page.locator('#scan-models').click()
                page.wait_for_function('!document.getElementById("scan-models").disabled')
                prefs=page.request.get(base+'/api/preferences').json()
                check('Save & scan persists new folders before scanning',any(v.endswith('scan-A') for v in prefs['model_roots']) and any(v.endswith('scan-B') for v in prefs['model_roots']))
                page.locator('.scan-root-entry').last.locator('button').click()
                check('remove folder updates pending list',page.locator('.scan-root-entry').count()==before+1)
                page.locator('#settings-dialog button[value=cancel]').click()
                page.locator('#settings-toggle').click()
                page.locator('[data-settings-tab=models]').click()
                page.locator('#model-discovery summary').click() if not page.locator('#model-discovery').evaluate('(e)=>e.open') else None
                check('cancel discards uncommitted folder deletion',page.locator('.scan-root-entry').count()==before+2)
                page.locator('#edit-scan-roots').click()
                check('manual multi-line editing remains available',page.locator('#scan-roots').is_visible())
                page.locator('#scan-roots').fill(page.locator('#scan-roots').input_value()+'\nC:/MoreModels')
                check('manual edit updates root list without reload',page.locator('.scan-root-entry').count()==before+3)
                page.locator('#save-settings').click()
                page.wait_for_function('!document.getElementById("settings-dialog").open')
                check('manual path saved together with native paths',any(v=='C:/MoreModels' for v in page.request.get(base+'/api/preferences').json()['model_roots']))
                page.locator('#settings-toggle').click()
                page.locator('[data-settings-tab=models]').click()
                check('paths remain after reopening settings',page.locator('.scan-root-entry').count()==before+3)
                for width in (320,375,768,1440):
                    page.set_viewport_size({'width':width,'height':830})
                    page.wait_for_timeout(150)
                    check(f'folder controls fit at {width}px',page.locator('#settings-dialog').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.width<=innerWidth+1&&r.right<=innerWidth+1;}'))
                    check(f'no layout overflow at {width}px',page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'))
                page.locator('#browse-model-path').click()
                page.locator('#settings-dialog button[value=cancel]').click()
                page.wait_for_timeout(450)
                page.locator('#settings-toggle').click()
                page.locator('[data-settings-tab=models]').click()
                check('late OS result ignored after Settings is closed',page.locator('#new-model-path').input_value()=='')
                check('no browser script errors',not errors)
                browser.close()
        finally:
            if bridge:bridge.close()
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()
    report={'checks':checks,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'errors':errors,'limits':'Fake Windows chooser on Linux; native Windows dialog itself requires Windows acceptance.'}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'failed':report['failed'],'errors':errors},ensure_ascii=False))

if __name__=='__main__':main()
