// Original compact SVG set, no CDN or external fonts.
const paths = {
  'audio-waveform':'M3 10v4m4-9v14m5-17v20m5-17v14m4-9v4',
  'sparkles':'m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6Z M20 2v4m-2-2h4',
  'wand-sparkles':'m4 20 12-12 4 4L8 24 M13 3v4m-2-2h4 M4 5v4m-2-2h4',
  'mic':'M8 5a4 4 0 0 1 8 0v7a4 4 0 0 1-8 0Zm-3 6v1a7 7 0 0 0 14 0v-1M12 19v4m-4 0h8',
  'users':'M15 21v-3a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v3m15-7a4 4 0 0 1 3 4v3 M13 3a4 4 0 0 1 0 8',
  'user':'M5 21v-3a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v3',
  'chevron-right':'m9 5 7 7-7 7','chevron-down':'m5 9 7 7 7-7','x':'m6 6 12 12M6 18 18 6',
  'refresh-cw':'M20 7a9 9 0 0 0-15-2L2 8m0-5v5h5m-3 9a9 9 0 0 0 15 2l3-3m0 5v-5h-5',
  'download-cloud':'M7 16a5 5 0 1 1-1-10 7 7 0 0 1 13 2 4 4 0 0 1 0 8m-7-5v11m-4-4 4 4 4-4',
  'power':'M12 2v10M5 5a9 9 0 1 0 14 0','folder-plus':'M3 7V4h7l2 3h9v13H3Zm9 4v6m-3-3h6',
  'library':'M4 3v18m5-18v18m5-17 5 17m-5-18 5-1 5 17-5 1',
  'bookmark':'M6 3h12v19l-6-5-6 5Z','bookmark-plus':'M6 3h12v19l-6-5-6 5ZM12 6v6m-3-3h6',
  'settings':'m9 3 6 0 1 3 3 1 2 5-2 2v4l-4 3-3-2-3 2-4-3v-4l-2-2 2-5 3-1Z',
  'settings-2':'M3 6h8m4 0h6M3 12h3m4 0h11M3 18h12m4 0h2M11 3v6M6 9v6m9 0v6',
  'menu':'M3 6h18M3 12h18M3 18h18','columns-2':'M3 4h18v16H3ZM12 4v16',
  'panel-left':'M3 4h18v16H3ZM9 4v16m-4-11h2m-2 4h2',
  'sliders-horizontal':'M3 6h7m4 0h7M3 12h3m4 0h11M3 18h12m4 0h2M10 3v6M6 9v6m9 0v6',
  'sun':'M12 1v2m0 18v2M1 12h2m18 0h2M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2',
  'moon':'M21 14a9 9 0 0 1-11-11A9 9 0 1 0 21 14',
  'languages':'M2 5h12M8 2v3M4 8c2 5 5 7 9 9M12 5c-1 6-4 10-9 13m11 4 5-12 5 12m-8-4h6',
  'clock-3':'M12 7v5l4 2','align-left':'M4 5h16M4 10h12M4 15h16M4 20h10',
  'eraser':'m4 14 9-11 8 7-9 11H8Zm2-2 8 7m-2 2h9',
  'headphones':'M3 15v-3a9 9 0 0 1 18 0v3M3 13h4v8H3Zm14 0h4v8h-4Z',
  'maximize-2':'M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5',
  'play':'m8 4 12 8-12 8Z','pause':'M8 4v16M16 4v16','square':'M5 5h14v14H5Z',
  'download':'M12 3v12m-5-5 5 5 5-5M3 16v5h18v-5',
  'loader-circle':'M21 12a9 9 0 1 1-9-9','arrow-right':'M3 12h18m-6-6 6 6-6 6',
  'arrow-left':'M21 12H3m6-6-6 6 6 6','search':'m16 16 5 5',
  'plus':'M12 4v16M4 12h16','check':'m4 12 5 5L20 6',
  'rotate-ccw':'M3 11a9 9 0 1 1 2 7M3 5v6h6',
  'star':'m12 2 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z',
  'trash':'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7',
  'edit':'m4 16 12-12 4 4L8 20l-5 1Z M14 6l4 4','file':'M5 2h9l5 5v15H5Zm9 0v6h5M8 12h8m-8 4h8',
  'alert':'m12 3 10 18H2ZM12 9v5m0 3v1','volume':'M4 9h4l5-5v16l-5-5H4Zm13-2a7 7 0 0 1 0 10m3-13a11 11 0 0 1 0 16'
};
const circles={ 'users':'<circle cx="9" cy="6" r="4"/>', 'user':'<circle cx="12" cy="6" r="4"/>','settings':'<circle cx="12" cy="12" r="3"/>','sun':'<circle cx="12" cy="12" r="4"/>','clock-3':'<circle cx="12" cy="12" r="9"/>','search':'<circle cx="10" cy="10" r="7"/>' };
export function icon(name){const e=document.createElementNS('http://www.w3.org/2000/svg','svg');e.setAttribute('viewBox','0 0 24 24');e.setAttribute('aria-hidden','true');e.innerHTML=`<path d="${paths[name]||paths['audio-waveform']}"/>${circles[name]||''}`;return e;}
export function hydrate(root=document){root.querySelectorAll('i[data-icon]').forEach(n=>{const e=icon(n.dataset.icon);e.setAttribute('class',n.className);n.replaceWith(e);});}
export function replaceIcon(button,name){const svg=button.querySelector('svg');if(svg)svg.replaceWith(icon(name));}
