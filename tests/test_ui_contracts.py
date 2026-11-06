"""UI release contracts: no AI weights, browser or font downloads required."""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / 'ui'
LOCALES = ('zh-CN', 'en')


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@pytest.fixture
def markup():
    parser = Markup()
    parser.feed((UI / 'index.html').read_text(encoding='utf-8'))
    return parser.elements


def dictionaries():
    return {key: json.loads((UI / 'locales' / f'{key}.json').read_text(encoding='utf-8')) for key in LOCALES}


def test_dictionary_key_parity():
    data = dictionaries()
    assert set(data['en']) == set(data['zh-CN'])
    assert len(data['en']) >= 250


def test_translation_interpolation_parity():
    data = dictionaries()
    for key in data['en']:
        assert re.findall(r'\{\w+\}', data['en'][key]) == re.findall(r'\{\w+\}', data['zh-CN'][key]), key


@pytest.mark.parametrize('locale', LOCALES)
def test_dictionary_is_nonempty_plain_text(locale):
    for key, value in dictionaries()[locale].items():
        assert isinstance(value, str) and value.strip(), key
        assert not re.search(r'<(?:script|iframe|img|svg)', value, re.I), key


def test_static_markup_translation_keys(markup):
    keys = dictionaries()['en']
    for _, attrs in markup:
        for name, value in attrs.items():
            if name == 'data-i18n' or name.startswith('data-i18n-'):
                assert value in keys, value


def test_js_literal_translation_keys():
    keys = dictionaries()['en']
    for source in UI.glob('*.js'):
        for key in re.findall(r"\bt\('([^']+)'\s*[,)]", source.read_text(encoding='utf-8')):
            assert key in keys, (source.name, key)


def test_html_unique_ids(markup):
    ids = [attrs['id'] for _, attrs in markup if 'id' in attrs]
    assert len(ids) == len(set(ids))


def test_settings_tab_relationships(markup):
    by_id = {attrs['id']: attrs for _, attrs in markup if 'id' in attrs}
    tabs = [attrs for _, attrs in markup if attrs.get('role') == 'tab']
    assert len(tabs) == 4
    assert sum(a.get('aria-selected') == 'true' for a in tabs) == 1
    for tab in tabs:
        panel = by_id[tab['aria-controls']]
        assert panel['role'] == 'tabpanel'
        assert panel['aria-labelledby'] == tab['id']


def test_fonts_are_local_only():
    css = (UI / 'styles.css').read_text()
    assert '@font-face' not in css
    assert '@import' not in css
    assert 'url(' not in css
    for suffix in ('ttf', 'otf', 'woff', 'woff2', 'ttc'):
        assert not list(ROOT.rglob('*.' + suffix))
    assert '--font-ui:' in css and '--font-serif:' in css


def test_two_typographic_presets(markup):
    options = [attrs['value'] for tag, attrs in markup if tag == 'input' and attrs.get('name') == 'font-preset']
    assert options == ['studio', 'editorial']


def test_no_remote_runtime_assets(markup):
    for _, attrs in markup:
        for name in ('src', 'href'):
            if name in attrs:
                assert not attrs[name].startswith(('http:', 'https:', '//'))
    for source in UI.glob('*.js'):
        assert not re.search(r'fetch\(["\']https?:', source.read_text())


def test_examples_are_explicit_not_private_starter_content():
    html = (UI / 'index.html').read_text()
    assert 'id="load-example"' in html
    for id_ in ['script-text', 'voice-instruct']:
        match = re.search(r'<textarea\b[^>]*id="' + id_ + '"[^>]*>(.*?)</textarea>', html, re.S)
        assert match and not match[1].strip()


def test_fresh_ui_keeps_content_out_of_language_switch():
    source = (UI / 'i18n.js').read_text()
    assert '.value = value' in source  # Interface language selector only.
    assert 'script-text' not in source and 'voice-instruct' not in source
    assert 'innerHTML' not in source


def test_styles_have_accessibility_rules():
    css = (UI / 'styles.css').read_text()
    for rule in ('prefers-reduced-motion', 'forced-colors', ':focus-visible', '.skip-link', 'pointer: coarse'):
        assert rule in css


def test_theme_initializes_before_css(markup):
    source = (UI / 'index.html').read_text()
    assert source.index('/ui/bootstrap.js') < source.index('/ui/styles.css')


def test_appearance_is_browser_only():
    source = (UI / 'appearance.js').read_text()
    assert "api(" not in source and 'fetch(' not in source
    assert 'setLocale' in source and 'setAppearance' in source


def test_translation_does_not_reset_audio():
    source = (UI / 'app.js').read_text()
    part = source[source.index("'qvs:locale'"):source.index("'qvs:appearance'")]
    assert 'player.relabel()' in part
    assert 'player.set(' not in part and 'updateReference(' not in part


def test_appearance_controls_have_accessible_names(markup):
    controls = {'interface-language', 'interface-theme', 'interface-scale', 'interface-layout', 'interface-density'}
    found = [attrs for _, attrs in markup if attrs.get('id') in controls]
    assert len(found) == len(controls)
    assert all(a.get('data-i18n-aria-label') for a in found)


def test_release_version_matches_project_metadata():
    import tomllib
    from studio import __version__
    metadata = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    assert metadata['project']['version'] == __version__


def test_single_settings_entry_and_advanced_variations(markup):
    ids={attrs.get('id') for _,attrs in markup}
    assert 'settings-toggle' in ids
    for old in ('open-settings-from-sidebar','density-toggle','layout-toggle',
                'theme-toggle','locale-toggle','load-model','unload-model',
                'expand-output','close-appearance'):
        assert old not in ids, old
    html=(UI/'index.html').read_text(encoding='utf-8')
    advanced=html.split('id="advanced-settings"',1)[1].split('</details>',1)[0]
    assert 'id="variations"' in advanced and 'id="split-lines"' in advanced
    assert 'id="release-model"' in html and 'id="speaker-hint"' in html


def test_no_hardware_estimate_or_budget_clamp():
    engine=(ROOT/'studio/engine.py').read_text(encoding='utf-8')
    app=(UI/'app.js').read_text(encoding='utf-8')
    assert 'mem_get_info' not in engine
    assert "$('gpu-budget').max" not in app
    assert "el.disabled=disabled" not in app
    assert 'max_memory={0: int(runtime.gpu_gib * 1024**3)' in engine
    assert 'int(runtime.cpu_gib * 1024**3)' in engine


def test_transient_notifications_have_expiration():
    core=(UI/'core.js').read_text(encoding='utf-8')
    app=(UI/'app.js').read_text(encoding='utf-8')
    assert 'while(region.children.length>3)' in core
    assert 'toastTimers.set(box,setTimeout' in core
    assert 'formErrorTimer=setTimeout(clearFormError,10000)' in app
    assert 'speaker.noSpeakersHint' in app


def test_static_assets_use_release_version():
    from studio import __version__
    html=(UI/'index.html').read_text(encoding='utf-8')
    for asset in ('bootstrap.js','styles.css','app.js'):
        assert f'/ui/{asset}?v={__version__}' in html
