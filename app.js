/* Offline-first catalog, with optional localhost preparation engine. */
'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const mediaURL = (client, path) => `projects/${encodeURIComponent(client)}/${path.split('/').map(encodeURIComponent).join('/')}`;
const size = n => n >= 1024**3 ? `${(n/1024**3).toFixed(1)} GB` : n >= 1024**2 ? `${(n/1024**2).toFixed(1)} MB` : `${Math.round(n/1024)} KB`;
let data = window.OFFLINE_CATALOG || {clients:[],jobs:[]};
let online = false, clientId = '', kind = 'video', selected = '', token = '', pollBusy = false;
const handled = new Set(), pending = new Map();
const client = () => data.clients.find(c => c.id === clientId);
const clip = () => client()?.clips?.[selected] || {};
const currentItem = () => client()?.media[kind].find(f => f.path === selected);
function associated(file) {
  const c=client();if(!c)return {};
  if(kind==='video')return c.clips[file.path]||{};
  const records=Object.entries(c.clips||{});
  const exact=records.find(([,s])=>[s.final,s.master,s.clean_audio].includes(file.path));
  if(exact)return exact[1];
  const candidates=records.filter(([path])=>file.name.startsWith(path.split('/').pop().replace(/\.[^.]+$/,'')+'_'));
  return candidates.length===1?candidates[0][1]:{};
}

function notice(message, error = false) {
  $('notice').textContent = message; $('notice').hidden = false; $('notice').classList.toggle('error', error);
}
async function action(path, payload = {}) {
  if (!online) throw new Error('Start the local app with Start_Windows.bat or Start_Mac.command to use this action.');
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-Editor-Token':token}, body:JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The action failed.');
  return result;
}
async function safely(work) { try { await work(); } catch (e) { notice(e.message, true); } }
function bind(id, event, fn) { $(id).addEventListener(event, e => safely(() => fn(e))); }

function renderClients() {
  $('clients').innerHTML = data.clients.map(c => `<button class="client-button ${c.id===clientId?'active':''}" data-client="${esc(c.id)}" ${c.id===clientId?'aria-current="true"':''}><span>${esc(c.name)}</span><span class="client-count">${c.media.video.length}</span></button>`).join('');
  $('clients').querySelectorAll('button').forEach(b => b.onclick = () => chooseClient(b.dataset.client));
  const c=client();
  if (!c) return;
  $('client-title').textContent=c.name;
  $('client-summary').textContent=`${c.media.video.length} camera videos · ${c.media.audio.length} recordings / clean WAVs · ${c.media.final.length} exports`;
  $('rename-client').value=c.name;
  for (const type of ['video','audio','final']) $('count-'+type).textContent=c.media[type].length;
  $('storage').textContent=data.free_bytes ? `${size(data.free_bytes)} free on library drive` : '';
  $('engine-state').textContent=online ? (data.ffmpeg?'FFmpeg ready. CPU encoding works on either platform.':'FFmpeg not found. Choose its executable below.') : 'Read-only HTML mode. Launch the local engine for preparation.';
}
function stateLabel(file) {
  if (kind==='audio') return file.name.endsWith('_clean_dialogue.wav') ? ['Clean WAV','good'] : ['Source audio',''];
  if (kind==='final') {
    if(associated(file).camera_fallback)return ['Camera fallback','warn'];
    if(file.name.includes('_prepared_'))return ['Review export',''];
    return file.name.includes('4K') ? ['4K master','good'] : ['1080p export','good'];
  }
  const s=client().clips[file.path] || {};
  if (s.camera_fallback) return ['Camera fallback','warn'];
  const labels={ready:'Ready for edit',review:'Needs review',hold:'On hold',new:'Needs prep'};
  return [labels[s.status] || 'Needs prep',s.status==='ready'?'good':s.status==='hold'?'warn':''];
}
function renderFiles() {
  const c=client(); if(!c) return;
  const query=$('search').value.toLowerCase();
  const items=c.media[kind].filter(f => f.name.toLowerCase().includes(query) || f.path.toLowerCase().includes(query));
  $('list-type').textContent=kind==='video'?'SYNC / REVIEW':kind==='audio'?'RECORDING TYPE':'EXPORT TYPE';
  document.querySelectorAll('[data-kind]').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.kind===kind)));
  if(!items.length) {
    $('files').innerHTML=`<div class="empty"><h2>${query?'No files found':`No ${kind==='final'?'finished exports':kind==='audio'?'recordings':'camera videos'} yet`}</h2><p>${query?'Try another filename.':'Import this client’s folders to start. Prepared videos appear under Final.'}</p></div>`;
    return;
  }
  $('files').innerHTML=items.map(f=> {
    const s=associated(f), [label,tone]=stateLabel(f);
    const thumb=s.poster ? `<img src="${mediaURL(c.id,s.poster)}" alt="" loading="lazy">` : (kind==='audio'?'♫':'▸');
    return `<button class="file-row ${f.path===selected?'selected':''}" data-file="${esc(f.path)}" ${f.path===selected?'aria-current="true"':''}><span class="file-symbol">${thumb}</span><span class="file-name"><strong>${esc(f.name)}</strong><small>${esc(size(f.bytes))}${kind==='video'&&s.audio?' · '+esc(s.audio.split('/').pop()):''}</small></span><span class="status ${tone}">${label}</span></button>`;
  }).join('');
  $('files').querySelectorAll('button').forEach(b=>b.onclick=()=>selectFile(b.dataset.file));
}
function chooseClient(id) {
  clientId=id; selected=''; $('search').value=''; $('video-folder').value=''; $('audio-folder').value='';
  renderClients(); renderFiles(); selectFile(client()?.media[kind][0]?.path || '');
}
function details(rows) {
  $('file-detail').innerHTML=rows.map(([label,value])=>`<div class="detail-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
}
function selectFile(path) {
  selected=path; renderFiles();
  $('clip-panel').hidden=true; $('handoff-links').hidden=true; $('download').hidden=true; $('candidates').replaceChildren();
  const item=currentItem();
  if(!item) {
    $('selected-title').textContent='Select a file'; $('viewer').innerHTML='<div class="viewer-empty">Your next client starts here<br><span>Import camera videos and separate recordings</span></div>';
    $('file-detail').replaceChildren(); $('media-help').textContent=''; return;
  }
  const url=mediaURL(clientId,path);
  $('selected-title').textContent=item.name; $('preview-type').textContent=kind==='video'?'CAMERA ORIGINAL':kind==='audio'?'DIALOGUE AUDIO':'FINISHED EXPORT';
  $('download').href=url; $('download').download=item.name; $('download').hidden=false;
  const element=document.createElement(kind==='audio'?'audio':'video');
  element.controls=true; element.preload='metadata'; element.src=url;
  if(kind!=='audio'){element.playsInline=true;if(clip().poster)element.poster=mediaURL(clientId,clip().poster);}
  element.addEventListener('error',()=>{$('media-help').textContent='This browser cannot preview this codec, or the media file is missing. Save it and open in your editor. H.264 1080p exports are the most compatible.';});
  $('viewer').replaceChildren(element);
  $('media-help').textContent=kind==='video'?'Original camera image, not the graded preview. Rotation below affects preparation, not this source player.':kind==='audio'?'Listen here before choosing this recording for a camera shot.':'Prepared for human editing. Review the complete clip before delivery.';
  details([['File size',size(item.bytes)],['Library path',path]]);
  if(kind==='final'&&associated(item).camera_fallback) {
    details([['File size',size(item.bytes)],['Audio source','Camera-audio fallback; separate recording unconfirmed'],['Library path',path]]);
    $('media-help').textContent='Camera-audio fallback. Room noise and other voices may remain; listen through before handoff.';
  }
  if(kind==='video') {
    const s=clip(); $('clip-panel').hidden=false;
    $('audio-source').innerHTML='<option value="">Choose a separate recording</option>'+client().media.audio.filter(f=>!f.name.endsWith('_clean_dialogue.wav')).map(f=>`<option value="${esc(f.path)}">${esc(f.name)}</option>`).join('');
    $('audio-source').value=s.audio||''; $('camera-fallback').checked=!!s.camera_fallback;
    $('offset').value=s.offset??0; $('start').value=s.start??0; $('end').value=s.end||'';
    $('rotation').value=s.rotation||'none'; $('profile').value=s.profile||'unconfirmed'; $('review-status').value=s.status||'new'; $('clip-note').value=s.note||'';
    $('clip-warning').hidden=!s.camera_fallback;
    $('clip-warning').textContent='Separate audio is not confirmed for this clip. Camera audio is a fallback and may contain room noise or other voices.';
    element.addEventListener('loadedmetadata',()=>{if(selected===path&&kind==='video'&&!$('end').value&&Number.isFinite(element.duration))$('end').value=element.duration.toFixed(2);});
    const rows=[['File size',size(item.bytes)],['Recording',s.audio?s.audio.split('/').pop():s.camera_fallback?'Camera audio fallback':'Not selected']];
    if(s.end)rows.push(['Selected camera range',`${(s.start||0).toFixed(2)} → ${Number(s.end).toFixed(2)} s`]);
    if(s.coverage)rows.push(['Verified audio coverage',`${s.coverage[0].toFixed(2)} → ${s.coverage[1].toFixed(2)} s`]);
    if(s.sync_confidence)rows.push(['Original sync audit',s.sync_confidence]);
    details(rows);
    const isNew=s.final?.includes('_prepared_');
    const audit=isNew?s.final.substring(0,s.final.lastIndexOf('/'))+'/PREPARATION.json':s.qa;
    const links=[['1080p prepared clip',s.final],['4K master',s.master],['Clean dialogue WAV',s.clean_audio],['Original finishing notes',s.notes],[isNew?'New preparation report':'Original export verification',audit]].filter(([,p])=>p);
    $('handoff-links').innerHTML='<h2>Editor handoff</h2>'+links.map(([label,p])=>`<a class="handoff-link" href="${mediaURL(clientId,p)}" target="_blank" rel="noopener">${label} ↗</a>`).join('');
    $('handoff-links').hidden=!links.length;
  }
  if(!online) $('media-help').textContent+=' Viewing-only mode: use the launcher to save notes or process files.';
}
function settings() {
  return {audio:$('audio-source').value,camera_fallback:$('camera-fallback').checked,offset:Number($('offset').value),
    start:Number($('start').value),end:Number($('end').value)||0,rotation:$('rotation').value,profile:$('profile').value,status:$('review-status').value,note:$('clip-note').value};
}
async function save(showMessage=true) {
  if(!selected||kind!=='video')throw new Error('Select a camera video first.');
  await action('/api/save',{client:clientId,video:selected,settings:settings()});
  if(showMessage)notice('Settings and handoff notes saved.');
  await load();
}
async function process(path) {
  const target={client:clientId,video:selected};
  if(path!=='/api/match')await save(false);
  const result=await action(path,target);pending.set(result.id,{...target,path});
  notice('Added to the local preparation queue.'); await load();
}
function renderJobs() {
  const jobs=(data.jobs||[]).slice(-8).reverse();
  for(const [id,label] of [['match-button','Find audio candidates'],['preview-button','Grade preview'],['prepare-button','Prepare 1080p']]) {
    const jobLabel=id==='match-button'?'Find audio candidates':id==='preview-button'?'Grade preview':'Prepare clip';
    const busy=(data.jobs||[]).some(j=>j.client===clientId&&j.video===selected&&j.label===jobLabel&&['running','queued'].includes(j.status));
    $(id).disabled=busy;$(id).textContent=busy?'Queued / working…':label;
  }
  if(!jobs.length)return;
  $('jobs').innerHTML=jobs.map(j=>`<div class="job"><div><strong>${esc(j.label)}${j.video?' · '+esc(j.video.split('/').pop()):''}</strong><span class="status ${j.status==='error'?'warn':j.status==='done'?'good':''}">${esc(j.status)}</span></div><p>${esc(j.stage)}</p>${j.status==='running'||j.status==='queued'?`<progress max="100" value="${Number(j.progress)||0}" aria-label="${esc(j.label)} progress"></progress>`:''}</div>`).join('');
  for(const job of jobs) {
    if(!['done','error'].includes(job.status)||handled.has(job.id))continue;
    handled.add(job.id); const target=pending.get(job.id);
    if(job.status==='error'){notice(`${job.label}: ${job.stage}`,true);continue;}
    if(!target)continue;
    if(job.result?.candidates && target.client===clientId && target.video===selected) {
      const candidates=job.result.candidates;
      $('candidates').innerHTML=candidates.length?'<p class="hint">Suggestions only. Listen, check sync, then choose a candidate.</p>'+candidates.map((r,i)=>`<button type="button" class="candidate" data-candidate="${i}"><strong>${esc(r.name)}</strong><span>Score ${r.score.toFixed(3)} · offset ${r.offset.toFixed(3)} s · camera coverage ${r.coverage_start.toFixed(2)}–${r.coverage_end.toFixed(2)} s</span></button>`).join(''):'<p class="warning">No usable candidate found. Choose a recording manually or explicitly use camera-audio fallback.</p>';
      $('candidates').querySelectorAll('button').forEach(b=>b.onclick=()=> {
        const r=candidates[Number(b.dataset.candidate)];$('audio-source').value=r.audio;$('offset').value=r.offset.toFixed(6);$('camera-fallback').checked=false;
        $('start').value=(Math.ceil(r.coverage_start*100)/100).toFixed(2);$('end').value=(Math.floor(r.coverage_end*100)/100).toFixed(2);
        notice('Candidate entered, not approved. Listen and check camera in/out times before preparing.');
      });
    }
    if(job.result?.preview&&target.client===clientId&&target.video===selected) {
      const image=document.createElement('img');image.src=mediaURL(clientId,job.result.preview);image.alt='Prepared grade preview';$('viewer').replaceChildren(image);
      $('media-help').textContent='Grade preview only. Check skin tone, exposure, highlights and rotation before rendering.';
    }
    if(job.result?.output)notice('Prepared export finished and decoded successfully. Find it in Final; human sync and grade review are still required.');
    if(job.result?.files)notice(`Imported ${job.result.files} files into this client library.`);
  }
}
async function load(refresh=false) {
  if(location.protocol==='file:')return;
  const response=await fetch(refresh?'/api/refresh':'/api/catalog',{cache:'no-store'});
  if(!response.ok)throw new Error('Local engine is not responding.');
  const next=await response.json();
  const changed=JSON.stringify(data.clients)!==JSON.stringify(next.clients);
  data=next; token=data.token; online=true;
  if(!clientId||!client())clientId=data.clients.find(c=>c.id==='trudent')?.id||data.clients[0]?.id||'';
  $('connection').textContent='● Local engine connected';
  if(changed||refresh){renderClients();renderFiles();}
  renderJobs();
}
function toggle(panel,button) {const open=$(panel).hidden;$(panel).hidden=!open;$(button).setAttribute('aria-expanded',String(open));}
function renderInventory() {
  const inv=window.DRIVE_INVENTORY;
  if(!inv){$('drive-summary').textContent='No source inventory available. Import your own folders to build a client library.';return;}
  const c=inv.counts;
  $('drive-toggle').textContent=`Drive inventory · ${c.video} videos`;
  $('drive-summary').textContent=`${c.video} video files · ${c.audio} audio files · ${c.photo} photos · ${size(inv.total_bytes)} in the production folder. Snapshot: ${inv.scanned_at}.`;
  $('drive-groups').innerHTML=inv.groups.map(g=>`<tr><th scope="row">${esc(g.name)}</th><td>${g.video}</td><td>${g.audio}</td><td>${g.photo}</td><td>${size(g.bytes)}</td></tr>`).join('');
}
bind('drive-toggle','click',()=>toggle('drive-panel','drive-toggle'));
bind('drive-close','click',()=>{$('drive-panel').hidden=true;$('drive-toggle').setAttribute('aria-expanded','false');});
bind('settings-toggle','click',()=>toggle('settings-panel','settings-toggle'));
bind('import-toggle','click',()=>toggle('import-panel','import-toggle'));
bind('add-toggle','click',()=>{toggle('add-form','add-toggle');if(!$('add-form').hidden)$('client-name').focus();});
bind('search','input',renderFiles);
document.querySelectorAll('[data-kind]').forEach(b=>b.onclick=()=>{kind=b.dataset.kind;selected='';$('search').value='';renderFiles();selectFile(client()?.media[kind][0]?.path||'');});
bind('refresh','click',async()=>{await load(true);notice('Library refreshed from local folders.');});
bind('add-form','submit',async e=>{e.preventDefault();const r=await action('/api/client',{name:$('client-name').value});await load();chooseClient(r.id);$('add-form').hidden=true;$('add-toggle').setAttribute('aria-expanded','false');$('import-panel').hidden=false;$('import-toggle').setAttribute('aria-expanded','true');notice('Client created. Choose this client’s source folders.');});
bind('rename-button','click',async()=>{await action('/api/rename',{client:clientId,name:$('rename-client').value});await load();notice('Client renamed.');});
bind('import-form','submit',async e=>{e.preventDefault();await action('/api/import',{client:clientId,video:$('video-folder').value,audio:$('audio-folder').value});notice('Import queued. Keep the drive connected until copying finishes.');await load();});
document.querySelectorAll('[data-browse]').forEach(b=>b.onclick=()=>safely(async()=>{b.disabled=true;try{const r=await action('/api/browse');if(r.path)$(b.dataset.browse).value=r.path;}finally{b.disabled=false;}}));
bind('engine-form','submit',async e=>{e.preventDefault();await action('/api/settings',{ffmpeg:$('ffmpeg-path').value});await load();notice('FFmpeg path saved.');});
bind('clip-form','submit',async e=>{e.preventDefault();await save();});
bind('match-button','click',()=>process('/api/match'));
bind('preview-button','click',()=>process('/api/preview'));
bind('prepare-button','click',()=>process('/api/prepare'));
bind('camera-fallback','change',()=>{$('clip-warning').hidden=!$('camera-fallback').checked;$('clip-warning').textContent='Camera-audio fallback selected. Check for room noise and other voices before handing off.';});

(async()=> {
  renderInventory();
  try{await load();}catch(e){notice('Local engine unavailable. The saved catalog is available for viewing. Use the launcher for import and processing.',true);}
  if(!clientId)clientId=data.clients.find(c=>c.id==='trudent')?.id||data.clients[0]?.id||'';
  $('connection').textContent=online?'● Local engine connected':'● Offline showcase';
  renderClients();renderFiles();selectFile(client()?.media.video[0]?.path||'');
  if(!data.clients.length)notice('No library loaded. Start the local app to create a client.',true);
  if(online)setInterval(async()=>{if(pollBusy)return;pollBusy=true;try{await load();}catch(e){$('connection').textContent='Local engine disconnected';}finally{pollBusy=false;}},2500);
})();
