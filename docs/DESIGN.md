# Interface and typography system

## Intent

A quiet production workspace: soft neutral macOS-inspired surfaces, restrained system-blue accents,
clear two-panel hierarchy, progressive controls and no instructional banners in normal
operation. Synthetic review screenshots are explicitly marked as test audio.

## Type presets

| Preset | Latin preference | CJK preference | Use |
|---|---|---|---|
| Modern sans | system UI (SF Pro when installed), Segoe UI Variable Text, Segoe UI | PingFang SC, Microsoft YaHei UI, Noto Sans SC/CJK SC | Whole workspace |
| Editorial serif | New York (if installed), Georgia | Noto Serif SC/CJK SC, Source Han Serif SC, Songti SC, SimSun | Headline and script editor |

The rest of the editorial workspace remains sans-serif so long labels and small
controls stay readable. Numeric metrics use tabular numerals; keyboard and technical
identifiers have a local monospace stack. These are CSS preferences, not embedded
fonts. No font files, font downloader, CDN requests or fingerprinting probes are included.
Windows can use Segoe UI/Microsoft YaHei and Georgia/SimSun without extra downloads.
Actual availability and glyph metrics vary by OS; validate on the target machine.

## Tokens

`ui/styles.css` owns fonts, semantic colors, radii, panel padding and control height.
Spacing follows 4/8/12/16/20/24/32 px. The base text size is 14 px with 110%/120% options.
Normal controls are 40 px high, compact controls 36 px; coarse-pointer overrides keep
interactive areas larger. Two visual densities do not require duplicated markup.

The 55% split is adjustable from 38 to 65 percent. At <=1060 px or when stacked mode is
selected, the same Generate controls move between editor and preview in DOM order.
At <=800 px the sidebar becomes a modal navigation drawer with focus containment.
Narrow settings and font cards stack without changing the saved desktop preference.

## Localization

`ui/locales/{zh-CN,en}.json` are loaded once per page. Keys are semantic; placeholders
and key coverage are tested. Translation uses textContent/attributes, not HTML injection.
No runtime machine translation is used. Known unchanged factory presets are translated
for display only; custom/edited presets, paths, transcripts and audio titles stay verbatim.
Backend technical error text/logs stay in their original language for debugging.

Interface language does not set synthesis language. The explicit Try Example button may
fill an example for the chosen UI language, after confirmation when the editor is nonempty.

## Interaction integrity

Locale changes update labels without clearing consent or reloading the audio source.
Appearance changes redraw the waveform, not the playback element. Live appearance is
browser-local; model/inference/privacy settings still require their existing save flow.
Unchanged job lists keep their DOM and keyboard focus; stale history requests are ignored.

## Accessibility-oriented checks

Visible focus, a skip link, named icon controls, keyboard settings tabs, keyboard split
adjustment, mobile focus containment, reduced-motion and forced-colors support are included.
Ordinary text tokens across common surfaces pass >=4.5:1 numeric contrast checks in
light/dark palettes. Disabled controls, every composited state and all assistive technology
were not independently certified. This is not a WCAG conformance certification.

The browser matrix checks 320/375/768/1024/1440/1920 CSS px with both locales, both fonts,
both themes and 120% application text. This is not the same as a full browser 200%/400%
zoom audit; include zoom and screen-reader checks in target acceptance.

Design references (guidance only, no imported implementation or font assets):
- W3C Reflow: https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
- W3C Focus Visible: https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html
- MDN reduced motion: https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion
- CSS Fonts specification: https://drafts.csswg.org/css-fonts/

## v3.5 density and persistence refinement

The sidebar model control uses one native select, a single-line detail and a small
management action. Model registration remains in Settings, with discovery options
inside a collapsed details element. The typeface selector uses two horizontal
rows of approximately 66 CSS px height at default text scale instead of large
preview tiles. Both share the app's native border and 4/8/12/16 px spacing scale.

Ordinary workflow and visual preferences use per-origin localStorage. Authored text,
reference transcripts and IDs use tab-scoped sessionStorage unless the user opts in
to long-term draft retention. Incomplete Settings edits use sessionStorage and are
applied only on Save; Cancel discards them. Reference authorization must be checked
again after refresh. This approach is a convenience/privacy balance, not encryption
or secure erasure.
