"""Restricted-browser regression tests for the specific reported v3.2 failures.

Uses a test-tone backend and an in-memory storage bridge. This does not certify
native Windows filesystem permissions, device inference, or real audio quality.
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

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=ROOT / 'artifacts/recovery')
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    checks, errors = [], []

    def check(name, result):
        checks.append({'name': name, 'passed': bool(result)})
        if not result:
            raise AssertionError(name)

    with tempfile.TemporaryDirectory(prefix='qvs-recovery-') as data:
        with (args.output / 'server.log').open('w') as log:
            process = subprocess.Popen([sys.executable, str(ROOT / 'tests/browser_server.py'),
                                        '--port', str(port), '--data', data], stdout=log, stderr=log)
        bridge = None
        try:
            for _ in range(100):
                try:
                    with urllib.request.urlopen(base + '/api/health', timeout=1) as res:
                        if res.status == 200:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Backend unavailable')
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, executable_path=shutil.which('chromium') or None,
                                             args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1440, 'height': 900}, locale='zh-CN', color_scheme='light')
                page.set_default_timeout(6000)
                page.on('pageerror', lambda exc: errors.append(str(exc)))
                bridge = mount(page, ROOT, base)
                page.wait_for_selector('#model-select option[value="demo_design"]', state='attached')
                check('models visible at first load', len(page.locator('#model-select option').all()) > 0)
                check('factory presets visible at first load', page.locator('.preset-chip').count() >= 3)
                page.locator('#settings-toggle').click()
                check('settings opens', page.locator('#settings-dialog').is_visible())
                page.screenshot(path=str(args.output / 'settings.png'), full_page=True)
                page.locator('#settings-dialog button[value=cancel]').click()
                # A missing non-essential setting control must never stop the dialog.
                page.locator('#scan-roots').evaluate('(element) => element.remove()')
                page.locator('#settings-toggle').click()
                check('settings tolerates missing optional field', page.locator('#settings-dialog').is_visible())
                page.locator('[data-settings-tab=appearance]').click()
                check('appearance still accessible', page.locator('#interface-theme').is_visible())
                page.locator('#save-settings').click()
                # Simulate page bootstrapping against persisted backend data again.
                page.evaluate("async () => { state.models = []; state.presets = []; await boot(); }")
                page.wait_for_timeout(100)
                check('model options restored after reinitialization', page.locator('#model-select option[value="demo_design"]').count() == 1)
                check('preset chips restored after reinitialization', page.locator('.preset-chip').count() >= 3)
                # A database with no presets offers a working recovery action.
                page.evaluate("async () => { for(const p of await api('/presets')) await api('/presets/' + p.id,{method:'DELETE'}); await refreshPresets(); }")
                check('empty preset state contains restore action', page.locator('.preset-empty-state button').count() == 1)
                page.locator('[data-view=presets]').click()
                page.locator('#restore-presets').click()
                page.wait_for_function('document.querySelectorAll(".preset-chip").length>=3')
                check('restore presets repairs empty library', page.locator('.preset-chip').count() >= 3)
                page.locator('[data-view=presets]').click()
                page.screenshot(path=str(args.output / 'presets.png'), full_page=True)
                page.locator('[data-mode=design]').click()
                page.screenshot(path=str(args.output / 'studio-light.png'), full_page=True)
                page.locator('#settings-toggle').click(); page.locator('#interface-theme').select_option('dark'); page.locator('#save-settings').click()
                page.screenshot(path=str(args.output / 'studio-dark.png'), full_page=True)
                for width in [320, 375, 768, 1024, 1440, 1920]:
                    page.set_viewport_size({'width': width, 'height': 900})
                    check(f'no horizontal overflow at {width}px',
                          page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                page.set_viewport_size({'width': 375, 'height': 812})
                page.wait_for_timeout(300)  # allow drawer transition to finish after breakpoint change
                page.screenshot(path=str(args.output / 'studio-mobile.png'), full_page=True)
                check('no JS exceptions', not errors)
                browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
            if bridge:
                bridge.close()
    (args.output / 'report.json').write_text(json.dumps({'checks': checks, 'js_errors': errors,
         'source': 'test-tone engine and isolated browser transport; not physical GPU validation'}, indent=2), encoding='utf-8')
    print(f'{len(checks)} regression checks passed')


if __name__ == '__main__':
    main()
