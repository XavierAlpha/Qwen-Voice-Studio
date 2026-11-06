"""Check the design system's ordinary text pairs, not full WCAG conformance."""
from pathlib import Path
import re
import pytest

CSS = (Path(__file__).resolve().parents[1] / 'ui/styles.css').read_text(encoding='utf-8')


def palette(theme):
    pattern = r':root \{(.*?)\}' if theme == 'light' else r':root\[data-theme="dark"\] \{(.*?)\}'
    block = re.search(pattern, CSS, re.S).group(1)
    return dict(re.findall(r'--([\w-]+):\s*(#[0-9a-fA-F]{6})\b', block))


def luminance(hex_color):
    rgb = [int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055)**2.4 for v in rgb]
    return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))


def ratio(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + .05) / (low + .05)


@pytest.mark.parametrize('theme', ('light', 'dark'))
def test_reading_text_token_pairs(theme):
    colors = palette(theme)
    for text in ('text', 'muted', 'faint'):
        for surface in ('bg', 'panel', 'raised', 'field'):
            assert ratio(colors[text], colors[surface]) >= 4.5, (theme, text, surface)


@pytest.mark.parametrize('theme', ('light', 'dark'))
def test_primary_action_text_token_pair(theme):
    colors = palette(theme)
    assert ratio(colors['accent-text'], colors['accent']) >= 4.5
