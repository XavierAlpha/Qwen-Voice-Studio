import {t} from './i18n.js';
import {$,timeText,dateText,toast} from './core.js';
import {replaceIcon} from './icons.js';
export class Player{
  constructor(){
    this.audio=$('audio-player');this.track=null;this.canvas=$('wave-canvas');
    $('play-btn').onclick=()=>this.toggle();
    this.audio.addEventListener('play',()=>replaceIcon($('play-btn'),'pause'));
    this.audio.addEventListener('pause',()=>replaceIcon($('play-btn'),'play'));
    this.audio.addEventListener('ended',()=>replaceIcon($('play-btn'),'play'));
    this.audio.addEventListener('error',()=>toast(t('error.audio'),true));
    this.audio.addEventListener('timeupdate',()=>this.update());
    this.audio.addEventListener('loadedmetadata',()=>this.update());
    $('audio-progress').oninput=event=>{if(Number.isFinite(this.audio.duration))this.audio.currentTime=this.audio.duration*Number(event.target.value)/100;};
    this.canvas.onclick=event=>{if(Number.isFinite(this.audio.duration)){const r=this.canvas.getBoundingClientRect();this.audio.currentTime=Math.max(0,Math.min(1,(event.clientX-r.left)/r.width))*this.audio.duration;}};
    new ResizeObserver(()=>this.draw()).observe(this.canvas);
    $('download-audio').onclick=()=>{if(this.track){const a=document.createElement('a');a.href=`/api/audio/${this.track.id}?format=${$('export-format').value}&download=true`;a.download=`voice-${this.track.id}.${$('export-format').value}`;a.click();}};
  }
  set(track){
    const changed=this.track?.id!==track.id;
    this.track=track;
    if(changed){this.audio.pause();this.audio.src=`/api/audio/${track.id}`;}
    $('empty-output').classList.add('hidden');$('active-output').classList.remove('hidden');
    $('output-title').textContent=track.title;$('output-time').textContent=dateText(track.created);
    $('duration-label').textContent=timeText(track.duration);$('player-total').textContent=timeText(track.duration);
    $('metric-elapsed').textContent=`${track.seconds.toFixed(1)} s`;
    $('metric-rtf').textContent=track.rtf.toFixed(2);$('metric-vram').textContent=`${track.vram_gib.toFixed(2)} GiB`;
    $('favorite-output').classList.toggle('active',track.favorite);
    $('use-reference').disabled=track.duration>60||track.duration<.5;
    this.update();requestAnimationFrame(()=>this.draw());
  }
  relabel(){if(this.track)$('output-time').textContent=dateText(this.track.created);this.update();}
  clear(){this.audio.pause();this.audio.removeAttribute('src');this.audio.load();this.track=null;$('active-output').classList.add('hidden');$('empty-output').classList.remove('hidden');}
  async toggle(){if(!this.track)return;try{if(this.audio.paused)await this.audio.play();else this.audio.pause();}catch(error){toast(error.message,true);}}
  update(){
    const duration=this.audio.duration||this.track?.duration||0;
    const ratio=duration?this.audio.currentTime/duration:0;
    $('audio-progress').value=ratio*100;$('player-current').textContent=timeText(this.audio.currentTime);
    $('player-total').textContent=timeText(duration);$('playline').style.left=`${Math.min(100,ratio*100)}%`;
    $('play-btn').setAttribute('aria-label',this.audio.paused?t('action.play'):t('action.pause'));
  }
  draw(){
    if(!this.track)return;
    const width=this.canvas.clientWidth,height=this.canvas.clientHeight;if(!width||!height)return;
    const dpr=window.devicePixelRatio||1;this.canvas.width=width*dpr;this.canvas.height=height*dpr;
    const ctx=this.canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
    const data=this.track.peaks||[];if(!data.length)return;
    ctx.fillStyle=getComputedStyle(document.body).getPropertyValue('--accent').trim();
    const n=Math.floor(width/5),max=Math.max(...data,.001);
    for(let i=0;i<n;i++){const v=data[Math.floor(i*data.length/n)]/max,h=Math.max(2,v*(height-18));ctx.globalAlpha=.45+.5*v;ctx.beginPath();ctx.roundRect(i*width/n,height/2-h/2,2.5,h,1.25);ctx.fill();}
    ctx.globalAlpha=1;
  }
}
