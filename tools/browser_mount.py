"""Restricted-container test adapter, NOT part of the application.

It mounts the real UI in about:blank, uses HTTP against the running local API,
and substitutes an in-memory Storage object. It does not verify browser origin,
CSP enforcement, native persistence, native downloads or microphone permissions.
No browser administrative policies are changed.
"""
import base64
from pathlib import Path
import re
import httpx


def mount(page, root: Path, base: str, storage_seed=None):
    client = httpx.Client(base_url=base, timeout=20)

    def request(payload):
        url = payload['url']
        if not (url.startswith('/api/') or (payload.get('method','GET') == 'GET' and url in {'/ui/locales/zh-CN.json', '/ui/locales/en.json'})):
            raise ValueError('Test bridge allows only relative local API requests')
        body = base64.b64decode(payload['body64']) if 'body64' in payload else payload.get('body')
        response = client.request(payload.get('method', 'GET'), url,
                                  headers=payload.get('headers', {}), content=body)
        return {'status': response.status_code, 'headers': dict(response.headers),
                'body': base64.b64encode(response.content).decode('ascii')}

    page.expose_function('_localHttp', request)
    html = (root / 'ui/index.html').read_text(encoding='utf-8')
    html = re.sub(r'<link[^>]+>', '', html)
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.S)
    html = html.replace('</head>', '<style>' + (root / 'ui/styles.css').read_text(encoding='utf-8') + '</style></head>')
    page.set_content(html)
    page.add_script_tag(content=r'''
    const nativeFetch = window.fetch.bind(window);
    const memory = Object.create(null);
    const storage = Object.create(null);
    Object.defineProperties(storage, {
      getItem: {value: key => Object.hasOwn(memory,key) ? memory[key] : null},
      setItem: {value: (key,value) => {memory[key]=String(value); Object.defineProperty(storage,key,{value:String(value),configurable:true,enumerable:true});}},
      removeItem: {value: key => {delete memory[key]; delete storage[key];}},
      clear: {value: () => {Object.keys(memory).forEach(key=>{delete memory[key];delete storage[key];});}},
      length: {get: () => Object.keys(memory).length},
      key: {value: index => Object.keys(memory)[index] ?? null}
    });
    Object.defineProperty(window,'localStorage',{value:storage});
    const sessionData = Object.create(null);
    const sessionShim = Object.create(null);
    Object.defineProperties(sessionShim, {
      getItem: {value: key => Object.hasOwn(sessionData,key) ? sessionData[key] : null},
      setItem: {value: (key,value) => {sessionData[key]=String(value); Object.defineProperty(sessionShim,key,{value:String(value),configurable:true,enumerable:true});}},
      removeItem: {value: key => {delete sessionData[key];delete sessionShim[key];}},
      clear: {value: () => {Object.keys(sessionData).forEach(key=>{delete sessionData[key];delete sessionShim[key];});}},
      length: {get: () => Object.keys(sessionData).length},
      key: {value: index => Object.keys(sessionData)[index] ?? null}
    });
    Object.defineProperty(window,'sessionStorage',{value:sessionShim});
    window.fetch = async (url,options={}) => {
      if(String(url).startsWith('blob:')||String(url).startsWith('data:'))return nativeFetch(url,options);
      const payload = {url:String(url),method:options.method||'GET',headers:options.headers||{}};
      if(options.body instanceof Blob){
        const bytes=new Uint8Array(await options.body.arrayBuffer());let binary='';
        for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
        payload.body64=btoa(binary);
      }else if(options.body!==undefined)payload.body=options.body;
      const result=await window._localHttp(payload);
      return new Response(Uint8Array.from(atob(result.body),c=>c.charCodeAt(0)),{status:result.status,headers:result.headers});
    };
    const source=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'src');
    Object.defineProperty(HTMLMediaElement.prototype,'src',{get:source.get,set(value){
      if(String(value).startsWith('/api/')){
        fetch(value).then(r=>r.blob()).then(blob=>source.set.call(this,URL.createObjectURL(blob)));
      }else source.set.call(this,value);
    }});
    window.__exports=[];
    const click=HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click=function(){
      if(!this.hasAttribute('download'))return click.call(this);
      const name=this.download, url=this.getAttribute('href');
      fetch(url).then(r=>r.blob()).then(async blob=>{
        const data=await blob.arrayBuffer();window.__exports.push({name,size:data.byteLength,text:await blob.text()});
      });
    };
    ''')
    if storage_seed:
        page.evaluate("""(seed) => {
          for (const [key, value] of Object.entries(seed.local || {})) localStorage.setItem(key, value);
          for (const [key, value] of Object.entries(seed.session || {})) sessionStorage.setItem(key, value);
        }""", storage_seed)
    names = ['bootstrap.js' , 'icons.js', 'i18n.js', 'core.js', 'appearance.js', 'navigation.js', 'player.js', 'recorder.js', 'settings.js', 'app.js']
    code = '\n'.join((root / 'ui' / name).read_text(encoding='utf-8') for name in names)
    code = re.sub(r'^import .*?;\s*$', '', code, flags=re.M)
    code = re.sub(r'\bexport (?=(async )?(function|class|const))', '', code)
    page.add_script_tag(content=code)
    return client
