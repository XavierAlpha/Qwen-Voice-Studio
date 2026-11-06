"""Bilingual/typography interaction audit against an isolated test-tone backend.

Native navigation is the default. --mount is for restricted containers and does
not certify native origin security, persistence, downloads or microphone access.
"""
from pathlib import Path
import argparse
import itertools
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mount', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/ui-review')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results, errors, external = [], [], []
    def check(name, condition):
        results.append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='qvs-ui-') as data:
        with (args.output / 'server.log').open('w') as log:
            process = subprocess.Popen([sys.executable, str(ROOT / 'tests/browser_server.py'), '--port', str(port), '--data', data], stdout=log, stderr=log)
        bridge = None
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base + '/api/health', timeout=1) as response:
                        if response.status == 200: break
                except OSError: time.sleep(.1)
            else: raise RuntimeError('Test server unavailable')
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='zh-CN', color_scheme='light', reduced_motion='reduce')
                page.set_default_timeout(6000)
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: external.append(request.url) if not request.url.startswith((base, 'blob:', 'data:')) else None)
                if args.mount:
                    from browser_mount import mount
                    bridge = mount(page, ROOT, base)
                else:
                    page.goto(base)
                page.wait_for_selector('#model-select option[value="demo_design"]', state='attached')
                def close_settings(): page.locator('#settings-dialog .dialog-header button').click()
                def appearance():
                    page.locator('#settings-toggle').click()
                    page.locator('[data-settings-tab=appearance]').click()
                def locale(value):
                    if page.locator('html').get_attribute('lang') == value: return
                    opened=page.locator('#settings-dialog').is_visible()
                    if not opened: page.locator('#settings-toggle').click()
                    page.locator('[data-settings-tab=appearance]').click()
                    page.locator('#interface-language').select_option(value)
                    if not opened: close_settings()
                check('browser language chooses Chinese', page.locator('html').get_attribute('lang') == 'zh-CN')
                check('no unsolicited starter prompt', not page.locator('#script-text').input_value())
                page.locator('#generate-btn').click()
                check('localized empty-input validation', page.locator('#form-error').is_visible())
                page.locator('#load-example').click()
                check('example is an explicit action', len(page.locator('#script-text').input_value()) > 10)
                script, direction = page.locator('#script-text').input_value(), page.locator('#voice-instruct').input_value()
                page.locator('#generate-btn').click()
                page.wait_for_selector('#active-output:not(.hidden)', timeout=15000)
                check('test-tone generation and waveform', page.locator('#wave-canvas').evaluate('(e)=>e.width>0'))
                page.wait_for_function('document.getElementById("audio-player").readyState>=2')
                page.locator('#play-btn').click()
                locale('en')
                check('English action labels', page.locator('#generate-btn').inner_text().strip() == 'Generate voice')
                check('locale does not pause audio', not page.locator('#audio-player').evaluate('(e)=>e.paused'))
                check('locale preserves script and voice direction', page.locator('#script-text').input_value() == script and page.locator('#voice-instruct').input_value() == direction)
                check('UI language does not change speech language', page.locator('#language').input_value() == 'Chinese')
                page.locator('#favorite-output').click()
                check('favorite does not reload audio source', not page.locator('#audio-player').evaluate('(e)=>e.paused'))
                page.locator('#play-btn').click()
                page.locator('#playback-rate').select_option('1.25')
                check('playback speed control', page.locator('#audio-player').evaluate('(e)=>e.playbackRate===1.25'))
                appearance()
                check('appearance tab exists and is selected', page.locator('[data-settings-tab=appearance]').get_attribute('aria-selected') == 'true')
                check('settings has one primary action', page.locator('#save-settings').is_visible() and page.locator('#settings-dialog .dialog-footer button').count()==1)
                page.locator('[name=font-preset][value=editorial]').check()
                check('serif applies to script', 'Georgia' in page.locator('#script-text').evaluate('(e)=>getComputedStyle(e).fontFamily'))
                check('controls retain sans-serif readability', 'Segoe UI' in page.locator('#generate-btn').evaluate('(e)=>getComputedStyle(e).fontFamily'))
                page.locator('#interface-theme').select_option('dark')
                check('theme changes without reload', page.locator('html').get_attribute('data-theme') == 'dark')
                page.locator('#interface-scale').select_option('120')
                check('readable text scale', float(page.locator('html').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')) >= 16.8)
                page.locator('#interface-density').select_option('compact')
                page.locator('#interface-layout').select_option('stack')
                check('layout and density persist in browser preferences', page.evaluate('JSON.parse(localStorage.getItem("qvs.layout"))==="stack" && JSON.parse(localStorage.getItem("qvs.density"))==="compact"'))
                page.locator('#reset-appearance').click()
                check('reset appearance does not alter locale', page.locator('html').get_attribute('lang') == 'en')
                check('reset restores layout, font and scale', page.locator('html').get_attribute('data-font') == 'studio' and page.locator('html').get_attribute('data-scale') == '100' and page.locator('body').get_attribute('data-layout') == 'split')
                page.emulate_media(color_scheme='dark')
                page.wait_for_function('document.documentElement.dataset.theme==="dark"')
                check('system theme tracks OS', page.locator('html').get_attribute('data-theme') == 'dark')
                page.locator('[data-settings-tab=appearance]').focus()
                page.keyboard.press('ArrowRight')
                check('settings arrow-key navigation', page.locator('[data-settings-tab=models]').get_attribute('aria-selected') == 'true')
                page.locator('#new-model-path').focus(); page.keyboard.press('Enter')
                check('Enter in a model path does not close settings', page.locator('#settings-dialog').is_visible())
                page.locator('[data-settings-tab=models]').focus(); page.keyboard.press('End')
                check('settings End key reaches privacy', page.locator('[data-settings-tab=privacy]').get_attribute('aria-selected') == 'true')
                check('draft persistence stays off by default', not page.locator('#remember-drafts').is_checked())
                page.locator('[data-settings-tab=appearance]').click(); page.locator('#save-settings').click()
                check('appearance Done closes dialog', not page.locator('#settings-dialog').is_visible())
                # Reusing a reference and changing locale must not clear authorization.
                page.locator('#use-reference').click()
                page.wait_for_function('!document.getElementById("remove-ref").disabled')
                page.locator('#voice-consent').check()
                ref_src = page.locator('#reference-player').get_attribute('src')
                locale('zh-CN')
                check('locale preserves reference and consent', page.locator('#voice-consent').is_checked() and page.locator('#reference-player').get_attribute('src') == ref_src)
                page.locator('[data-mode=custom]').click()
                page.locator('#speaker').select_option('Ryan')
                locale('en')
                check('locale preserves selected speaker', page.locator('#speaker').input_value() == 'Ryan')
                page.locator('[data-mode=design]').click()
                # Library actions exercise dynamically translated handlers.
                page.locator('[data-view=history]').click()
                page.wait_for_selector('.library-item')
                check('history renders after translation', page.locator('.item-detail').first.inner_text().startswith('Voice design'))
                page.locator('.library-item').first.get_by_role('button', name='Rename', exact=True).click()
                page.locator('#rename-value').fill('Bilingual test take')
                page.locator('#rename-form button[type=submit]').click()
                page.wait_for_function('document.querySelector(".item-title")?.textContent==="Bilingual test take"')
                check('renaming a clip works', page.locator('.item-title').first.inner_text() == 'Bilingual test take')
                page.locator('.library-item').first.get_by_role('button', name='Favorite', exact=True).click()
                page.wait_for_timeout(100)
                check('favorite handler has no translation-name collision', not errors)
                page.locator('[data-view=presets]').click()
                check('factory preset labels are localized', 'Warm narration' in page.locator('#preset-grid').inner_text())
                page.locator('#new-preset').click()
                page.locator('#preset-name').fill('Original name <safe>')
                page.locator('#preset-instruct').fill('A clear and unhurried voice.')
                page.locator('#preset-form button[type=submit]').click()
                page.wait_for_function('document.getElementById("preset-grid").textContent.includes("Original name <safe>")')
                locale('zh-CN')
                check('user preset is not translated or evaluated', 'Original name <safe>' in page.locator('#preset-grid').inner_text() and page.locator('#preset-grid safe').count() == 0)
                locale('en')
                page.locator('.preset-card').filter(has_text='Original name <safe>').get_by_role('button', name='Delete', exact=True).click()
                page.locator('#confirm-dialog button[value=ok]').click()
                page.wait_for_function('!document.getElementById("preset-grid").textContent.includes("Original name <safe>")')
                page.locator('[data-mode=design]').click()
                page.locator('#panel-splitter').focus(); page.keyboard.press('ArrowLeft')
                check('keyboard splitter stores width', page.locator('#panel-splitter').get_attribute('aria-valuenow') == '53')
                page.locator('#panel-splitter').dblclick()
                check('double click resets splitter', page.locator('#panel-splitter').get_attribute('aria-valuenow') == '55')
                page.locator('#collapse-sidebar').click()
                check('collapsed sidebar keeps accessible nav names', page.locator('[data-mode=clone]').get_attribute('aria-label') is not None)
                page.locator('#collapse-sidebar').click()
                # Coverage matrix: 2 languages x 2 font styles x 2 themes x 6 widths.
                for lang, font, theme in itertools.product(('zh-CN', 'en'), ('studio', 'editorial'), ('light', 'dark')):
                    page.set_viewport_size({'width': 1440, 'height': 1000})
                    locale(lang); appearance()
                    page.locator('[name=font-preset][value=' + font + ']').check()
                    page.locator('#interface-theme').select_option(theme)
                    page.locator('#interface-scale').select_option('120')
                    page.locator('#interface-density').select_option('compact' if font == 'editorial' else 'comfortable')
                    close_settings()
                    for width in (320, 375, 768, 1024, 1440, 1920):
                        page.set_viewport_size({'width': width, 'height': 950})
                        page.wait_for_timeout(30)
                        check(f'reflow {lang}/{font}/{theme}/{width}px/120%', page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                        check(f'primary controls fit {lang}/{font}/{theme}/{width}px', page.locator('#generate-btn').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&r.width>80;}'))
                page.set_viewport_size({'width': 375, 'height': 850})
                # Viewport-dependent rearrangement uses browser resize/media events: wait for settled DOM order.
                page.wait_for_function('''() => {const a=document.getElementById('compose-actions');
                  const b=document.querySelector('.output-panel');
                  return a&&b&&Boolean(a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING); }''')
                check('mobile generate precedes preview in DOM order', page.locator('#compose-actions').evaluate('(e)=>Boolean(e.compareDocumentPosition(document.querySelector(".output-panel")) & Node.DOCUMENT_POSITION_FOLLOWING)'))
                page.locator('#menu-toggle').click()
                check('mobile menu exposes modal navigation semantics', page.locator('#sidebar').get_attribute('aria-modal') == 'true')
                check('mobile menu makes main area inert', page.locator('.main-area').evaluate('(e)=>e.inert'))
                page.locator('#sidebar-close').focus(); page.keyboard.press('Shift+Tab')
                check('mobile menu traps keyboard focus', page.evaluate('document.getElementById("sidebar").contains(document.activeElement)'))
                page.keyboard.press('Escape')
                check('Escape restores menu focus', page.locator('#menu-toggle').evaluate('(e)=>document.activeElement===e'))
                check('menu closing releases main area', not page.locator('.main-area').evaluate('(e)=>e.inert'))
                appearance()
                check('mobile settings remain within viewport', page.locator('#settings-dialog').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1;}'))
                page.locator('[data-settings-tab=privacy]').click()
                check('privacy actions fit mobile viewport', page.locator('#clear-local-data').evaluate('(e)=>e.getBoundingClientRect().right<=innerWidth'))
                close_settings()
                # Representative screenshots use explicitly synthetic test audio.
                page.set_viewport_size({'width': 1440, 'height': 980})
                locale('zh-CN'); appearance()
                page.locator('[name=font-preset][value=studio]').check()
                page.locator('#interface-scale').select_option('100')
                page.locator('#interface-density').select_option('comfortable')
                page.locator('#interface-theme').select_option('dark'); close_settings()
                page.locator('#script-text').fill('\u8ba9\u6587\u5b57\u6709\u6e29\u5ea6\uff0c\u8ba9\u58f0\u97f3\u6709\u8868\u60c5\u3002\u8fd9\u662f\u5c5e\u4e8e\u4f60\u7684\u521b\u4f5c\u65f6\u523b\u3002')
                page.locator('#voice-instruct').fill('\u6210\u5e74\u5973\u58f0\uff0c\u6e29\u6696\u6e05\u6670\uff0c\u81ea\u7136\u4eb2\u5207\uff0c\u8bed\u901f\u4ece\u5bb9\u3002')
                page.locator('#voice-instruct').blur()
                check('Chinese live character counter matches editor', page.locator('#char-counter').inner_text().startswith(str(len(page.locator('#script-text').input_value()))))
                page.screenshot(path=str(args.output / 'studio-zh-dark.png'), full_page=True)
                appearance(); page.locator('#interface-theme').select_option('light'); close_settings()
                page.screenshot(path=str(args.output / 'studio-zh-light.png'), full_page=True)
                appearance(); page.locator('[name=font-preset][value=editorial]').check(); close_settings()
                page.screenshot(path=str(args.output / 'studio-zh-editorial.png'), full_page=True)
                locale('en')
                page.locator('#script-text').fill('Give your words warmth and your voice a little character. This is your moment to create.')
                page.locator('#voice-instruct').fill('An adult narrator, warm and clear, conversational and unhurried, with a hint of a smile.')
                page.locator('#language').select_option('English')
                page.locator('#voice-instruct').blur()
                page.screenshot(path=str(args.output / 'studio-en-editorial.png'), full_page=True)
                appearance(); page.screenshot(path=str(args.output / 'appearance-en.png'), full_page=True); close_settings()
                page.set_viewport_size({'width': 375, 'height': 850})
                page.screenshot(path=str(args.output / 'mobile-en.png'), full_page=True)
                locale('zh-CN'); appearance(); page.screenshot(path=str(args.output / 'appearance-mobile.png'), full_page=True); close_settings()
                check('no runtime JavaScript exceptions', not errors)
                check('no external asset requests', not external)
                browser.close()
        except Exception:
            raise
        finally:
            if bridge: bridge.close()
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill()
            report = {'mode': 'mounted real UI + local API + synthetic audio' if args.mount else 'native local test-tone browser', 'checks': results, 'passed': sum(x['passed'] for x in results), 'failed': sum(not x['passed'] for x in results), 'javascript_errors': errors, 'external_requests': external, 'limitations': ['No real Qwen inference', 'No Windows/CUDA execution', 'No physical microphone test'] + (['Mounted mode does not test native browser navigation, persistence, CSP, permissions or downloads'] if args.mount else [])}
            (args.output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"UI checks: {report['passed']} passed, {report['failed']} failed")


if __name__ == '__main__':
    main()
