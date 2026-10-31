'use strict';
const $ = id => document.getElementById(id);
let token = '';
try { token=sessionStorage.getItem('ugc-web-token') || ''; } catch (_) { /* Private browsers may disable storage. */ }
let projectId = '', project = null, draft = null, busy = false, timer = null, voiceEnabled = false, voiceLanguage = '', voiceLanguages = [];
const DISCLOSURE = 'PUBLICITÉ · LIEN AFFILIÉ · INFLUENCEUSE IA';
const show = (id, yes) => $(id).classList.toggle('hidden', !yes);
function message(text, error=false) {const el=$('message'); el.textContent=text; el.className='message '+(error?'error':'good');}
function safeName(name){const index=name.lastIndexOf('.');const base=index<0?name:name.slice(0,index);const ext=index<0?'':name.slice(index).toLowerCase();return ((base.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^A-Za-z0-9._-]/g,'_').replace(/^\.+/,'') || 'media').slice(0,80)+ext);}
async function api(path, opts={}) {
 const headers={...opts.headers,Authorization:'Bearer '+token};
 if (opts.body && typeof opts.body==='object' && !(opts.body instanceof Blob)) {headers['Content-Type']='application/json';opts.body=JSON.stringify(opts.body);}
 const response=await fetch(path,{...opts,headers,cache:'no-store'});
 const data=await response.json().catch(()=>({error:'Réponse serveur illisible'}));
 if(!response.ok)throw new Error(data.error||`HTTP ${response.status}`);
 return data;
}
function el(tag, text, cls) {const e=document.createElement(tag);if(text!=null)e.textContent=String(text);if(cls)e.className=cls;return e;}
function option(select,value,label) {const opt=el('option',label);opt.value=value;select.append(opt);}
function selectOptions(select, type, includeEmpty=true) {
 select.replaceChildren();if(includeEmpty)option(select,'','— Choisir —');
 for(const m of (project?.media||[]).filter(x=>type==='all'||type==='imagevideo'&&['image','video'].includes(x.type)||x.type===type))option(select,m.file,m.file.slice(6));
}
function field(container, labelText, type, value, callback, attr={}) {
 const label=el('label',labelText);const input=el('input');input.type=type;
 input.value=value==null?'':value;
 for(const [key,v] of Object.entries(attr))input.setAttribute(key,v);
 input.addEventListener('input',()=>callback(type==='number'?Number(input.value):input.value));
 label.append(input);container.append(label);return input;
}
function dropdown(container,labelText,values,value,callback) {
 const label=el('label',labelText);const select=el('select');
 for(const [key,name] of values)option(select,key,name);
 select.value=value==null?'':value;select.addEventListener('change',()=>callback(select.value));
 label.append(select);container.append(label);return select;
}
function fileDrop(container,labelText,filter,value,callback,empty=true) {
 const l=el('label',labelText), select=el('select');selectOptions(select,filter,empty);select.value=value||'';
 select.addEventListener('change',()=>callback(select.value));l.append(select);container.append(l);return select;
}
const rightsList=[['','Déclarer les droits…'],['ai_generated','IA générée avec droits'],['owned','Média que je possède'],['licensed','Licence tierce documentée']];
function defaultDraft() {return {product:{name:project?.name||'',claims_verified:false,evidence_urls:[],product_reference:''},talking_clips:[],overlays:[],music:null,srt_assignments:[]};}
async function connect() {
 const proposed=$('token').value.trim();if(!proposed){message('Saisir le jeton affiché par le serveur.',true);return;}
 token=proposed;
 try{const health=await api('/api/health');voiceEnabled=health.voice_generation_enabled===true;voiceLanguage=health.voice_language||'';voiceLanguages=Array.isArray(health.voice_languages)?health.voice_languages.filter(x=>x==='fr'||x==='en'):[];if(!voiceLanguages.length&&voiceLanguage)voiceLanguages=[voiceLanguage.split('_')[0]];try { sessionStorage.setItem('ugc-web-token',token); } catch (_) { /* Session-only token. */ }$('connection').textContent='Connecté • local';$('connection').classList.add('ok');show('projectsPanel',true);await listProjects();message('Connexion privée établie.');}catch(e){$('connection').textContent='Accès refusé';message(e.message,true);}
}
async function listProjects(){const data=await api('/api/projects');const sel=$('projects');sel.replaceChildren();option(sel,'','— Sélectionner —');for(const item of data.projects)option(sel,item.id,item.name);if(projectId)sel.value=projectId;}
async function createProject(){const name=$('projectName').value.trim();if(!name){message('Donner un nom au projet.',true);return;}try{const r=await api('/api/projects',{method:'POST',body:{name}});projectId=r.id;await listProjects();await loadProject();message('Projet créé. Commence par importer les fichiers.');}catch(e){message(e.message,true);}}
async function loadProject(){if(!projectId)return;project=await api('/api/projects/'+projectId);draft=project.draft?structuredClone(project.draft):defaultDraft();$('projectInfo').textContent='Projet : '+project.name+' • médias stockés localement sur le serveur';show('mediaPanel',true);show('voicePanel',true);show('narratedPanel',true);show('editorPanel',true);show('resultPanel',true);updateVoiceChoices();renderMedia();renderEditor();renderOutputs();updateJob();}
function updateVoiceChoices(){
 const select=$('voiceLanguage'),previous=select.value;
 select.replaceChildren();
 const names={fr:'Français',en:'English'};
 for(const language of ['fr','en']){
  const installed=voiceLanguages.includes(language);
  const item=el('option',names[language]+(installed?'':' · non installé'));
  item.value=language;item.disabled=!installed;select.append(item);
 }
 const chosen=voiceLanguages.includes(previous)?previous:(voiceLanguages.includes('fr')?'fr':voiceLanguages[0]);
 select.value=chosen||'';
 if(!chosen)select.selectedIndex=-1;
 const states=['fr','en'].map(lang=>names[lang]+': '+(voiceLanguages.includes(lang)?'prête':'modèle absent'));
 $('voiceAvailability').textContent=states.join(' · ')+'. Le texte n’est pas traduit automatiquement. La voix produite n’est pas synchronisée avec une vidéo.';
 $('voiceGenerate').disabled=!voiceLanguages.includes(select.value);
}
function renderMedia(){const box=$('mediaGrid');box.replaceChildren();for(const m of project.media){const card=el('div',null,'media-item');card.append(el('div',m.file.slice(6),'name'));const props=[m.type,m.bytes?Math.round(m.bytes/1024)+' Ko':'',m.duration?m.duration+' s':'',m.language?({fr:'Français',en:'English'}[m.language]||m.language):'',m.has_audio===false&&m.type==='video'?'sans audio':''].filter(Boolean).join(' · ');card.append(el('small',props));if(m.type==='image'){const pic=el('img');pic.src=m.url;pic.alt=m.file.slice(6);card.append(pic);}if(m.type==='audio'){const player=el('audio');player.controls=true;player.preload='none';player.src=m.url;card.append(player);}box.append(card);}if(!project.media.length)box.append(el('p','Aucun média importé.','hint'));renderNarratedOptions();}
function clipCard(clip,i){const card=el('div',null,'entry');const head=el('div',null,'entry-head');head.append(el('b','Plan parlé '+(i+1)));const rem=el('button','Retirer','danger');rem.type='button';rem.addEventListener('click',()=>{collectForm();draft.talking_clips.splice(i,1);draft.srt_assignments=draft.srt_assignments.filter(x=>x.clip!==i).map(x=>({...x,clip:x.clip>i?x.clip-1:x.clip}));renderEditor();});head.append(rem);card.append(head);
 fileDrop(card,'Vidéo avec voix native','video',clip.file,x=>clip.file=x);
 const times=el('div',null,'grid-three');field(times,'Début source (s)','number',clip.source_in,x=>clip.source_in=x,{min:0,step:'.001'});field(times,'Durée (s)','number',clip.duration,x=>clip.duration=x,{min:.1,step:'.001'});dropdown(times,'Cadrage',[['off','Original'],['face','Visage (OpenCV)']],clip.smart_crop,x=>clip.smart_crop=x);card.append(times);
 const row=el('div',null,'grid-two');dropdown(row,'Droits du clip',rightsList,clip.rights,x=>{clip.rights=x;collectForm();renderEditor();});if(clip.rights==='licensed')field(row,'Référence de licence','text',clip.license_ref||'',x=>clip.license_ref=x);card.append(row);
 const a=draft.srt_assignments.find(x=>x.clip===i)||null;const cap=el('div',null,'grid-two');fileDrop(cap,'SRT (optionnel)','subtitle',a?.file||'',x=>{draft.srt_assignments=draft.srt_assignments.filter(z=>z.clip!==i);if(x)draft.srt_assignments.push({clip:i,file:x,timebase:a?.timebase||'clip'});collectForm();renderEditor();});if(a)dropdown(cap,'Horaires du SRT',[['clip','0 = début de ce segment'],['source','Horaires source complète']],a.timebase,x=>a.timebase=x);card.append(cap);return card;}
function overlayCard(overlay,i){const card=el('div',null,'entry');const head=el('div',null,'entry-head');head.append(el('b','Plan produit '+(i+1)));const rem=el('button','Retirer','danger');rem.type='button';rem.addEventListener('click',()=>{collectForm();draft.overlays.splice(i,1);renderEditor();});head.append(rem);card.append(head);
 fileDrop(card,'Photo ou vidéo produit','imagevideo',overlay.file,x=>overlay.file=x);const times=el('div',null,'grid-three');field(times,'Début dans le film (s)','number',overlay.start,x=>overlay.start=x,{min:0,step:'.01'});field(times,'Durée (s)','number',overlay.duration,x=>overlay.duration=x,{min:.05,step:'.01'});field(times,'Fondu (s)','number',overlay.fade,x=>overlay.fade=x,{min:0,max:.5,step:'.01'});card.append(times);
 const sec=el('div',null,'grid-two');dropdown(sec,'Droits du média',rightsList,overlay.rights,x=>{overlay.rights=x;collectForm();renderEditor();});dropdown(sec,'Animation',[['static','Fixe'],['push_in','Zoom progressif'],['pull_out','Dézoom'],['pan_left','Pan gauche'],['pan_right','Pan droite']],overlay.motion,x=>overlay.motion=x);card.append(sec);
 const layoutRow=el('div',null,'grid-two');
 dropdown(layoutRow,'Disposition',[['full','Plein écran'],['pip_left','Carte produit · gauche'],['pip_right','Carte produit · droite']],overlay.layout||'full',x=>overlay.layout=x);
 layoutRow.append(el('p','Les cartes sont au-dessus des sous-titres. Contrôler que le visage reste visible.','hint'));
 card.append(layoutRow);
 if(overlay.rights==='licensed')field(card,'Référence de licence','text',overlay.license_ref||'',x=>overlay.license_ref=x);
 if((overlay.file||'').match(/\.(mp4|mov|mkv|webm)$/i))field(card,'Début dans la vidéo produit (s)','number',overlay.source_in||0,x=>overlay.source_in=x,{min:0,step:'.01'});
 return card;}
function renderEditor(){if(!draft)return;
 $('productName').value=draft.product.name||'';$('claims').checked=!!draft.product.claims_verified;$('evidence').value=(draft.product.evidence_urls||[]).join('\n');selectOptions($('productRef'),'image');$('productRef').value=draft.product.product_reference||'';
 const c=$('clips');c.replaceChildren();draft.talking_clips.forEach((clip,i)=>c.append(clipCard(clip,i)));
 const o=$('overlays');o.replaceChildren();draft.overlays.forEach((overlay,i)=>o.append(overlayCard(overlay,i)));
 selectOptions($('music'),'audio');$('music').value=draft.music?.file||'';$('musicVolume').value=draft.music?.volume??0.12;$('musicRights').value=draft.music?.rights||'';$('musicLicense').value=draft.music?.license_ref||'';
}
function collectForm(){draft.product.name=$('productName').value.trim();draft.product.claims_verified=$('claims').checked;draft.product.product_reference=$('productRef').value;draft.product.evidence_urls=$('evidence').value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);const music=$('music').value;if(music){draft.music={file:music,rights:$('musicRights').value,license_ref:$('musicLicense').value.trim(),volume:Number($('musicVolume').value)};}else draft.music=null;return draft;}
async function save(){const config=collectForm();const ret=await api(`/api/projects/${projectId}/configure`,{method:'POST',body:config});project.config=ret.config;showWarnings(ret.warnings||[]);message(`Projet validé : ${ret.clips} plans parlés, ${ret.captions} sous-titres, ${ret.duration.toFixed(1)} s.`);return ret;}
function showWarnings(warnings){const w=$('warnings');w.replaceChildren();for(const notice of warnings)w.append(el('p',notice,'warning'));if(!warnings.length)w.append(el('p','Aucune alerte éditoriale rapportée (vérification humaine toujours obligatoire).','hint'));}
async function uploadFiles(){if(!projectId){message('Créer un projet avant les imports.',true);return;}const files=[...$('uploadFiles').files];if(!files.length){message('Choisir un fichier.',true);return;}
 $('upload').disabled=true;try{for(let i=0;i<files.length;i++){const file=files[i];if(file.size>350*1024*1024)throw new Error('Fichier trop grand: '+file.name);$('uploadStatus').textContent=`Import ${i+1}/${files.length} : ${file.name} (${(file.size/1024/1024).toFixed(1)} Mo)`;const name=safeName(file.name);const r=await api(`/api/projects/${projectId}/media?filename=${encodeURIComponent(name)}`,{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream'},body:file});project.media.push(r.media);renderMedia();}renderEditor();$('uploadFiles').value='';$('uploadStatus').textContent='Import terminé.';message(`${files.length} fichier(s) ajouté(s) avec vérification du format.`);}catch(e){message(e.message,true);}finally{$('upload').disabled=false;}}

function renderNarratedOptions(){
 if(!project)return;
 const selector=$('shortAudio'),previous=selector.value;
 const available=project.media.filter(m=>m.type==='audio'&&m.generated_by==='piper_local');
 selector.replaceChildren();option(selector,'','— Générer une voix FR / EN ci-dessus —');
 for(const m of available)option(selector,m.file,(m.language==='en'?'English':'Français')+' · '+(m.duration||'?')+' s · '+m.file.slice(6));
 if(available.some(x=>x.file===previous))selector.value=previous;
 else if(available.length)selector.value=available[available.length-1].file;
 const container=$('shortImages');
 const checked=new Set([...container.querySelectorAll('input:checked')].map(input=>input.value));
 container.replaceChildren();
 for(const m of project.media.filter(x=>x.type==='image')){
   const label=el('label',null,'short-photo');
   const checkbox=el('input');checkbox.type='checkbox';checkbox.value=m.file;
   checkbox.checked=checked.has(m.file);
   const picture=el('img');picture.src=m.url;picture.alt=m.file.slice(6);picture.loading='lazy';
   label.append(checkbox,picture,el('span',m.file.slice(6)));container.append(label);
 }
 const disabled=project.job&&['queued','running'].includes(project.job.status);
 $('shortPreview').disabled=disabled||!available.length;
 $('shortRender').disabled=disabled||!available.length;
}
async function runNarrated(preview){
 const images=[...$('shortImages').querySelectorAll('input:checked')].map(x=>x.value);
 const audio=$('shortAudio').value,title=$('shortTitle').value.trim();
 if(!audio||!images.length||images.length>6||title.length<2||title.length>48){
    message('Choisir une voix Piper, 1–6 photos et un titre de 2–48 caractères.',true);return;
 }
 if(!$('shortRights').checked||!$('shortClaims').checked){
    message('Confirmer les droits des photos et la véracité du titre.',true);return;
 }
 try {
   await api('/api/projects/'+projectId+'/narrated',{method:'POST',
     body:{audio,images,title,preview,confirm_image_rights:true,claims_verified:true}});
   project.job={status:'queued',kind:'narrated',preview};updateJob();
   message('Short narré en attente : rendu entièrement local sur le serveur.');
   if(timer)clearInterval(timer);timer=setInterval(poll,2500);
 }catch(e){message(e.message,true);}
}
function updateJob(){const job=project?.job||{};const status=$('jobStatus');const labels=job.kind==='narrated'?{idle:'Prêt.',queued:'Short narré en attente…',running:'Images + narration : encodage FFmpeg…',completed:'Short narré terminé. Contrôler la vidéo avant diffusion.',failed:'Échec du Short narré.'}:job.kind==='voice'?{idle:'Aucun travail lancé.',queued:'Voix en attente…',running:'Génération Piper locale en cours…',completed:'Voix générée. Écouter dans les médias.',failed:'Échec de génération vocale.'}:{idle:'Aucun export lancé.',queued:'Export en attente…',running:'Montage FFmpeg en cours…',completed:'Export terminé.',failed:'Échec de l’export.'};status.textContent=labels[job.status]||'Aucun export lancé.';if(job.status==='failed')status.textContent+=' '+(job.error||'');$('preview').disabled=['queued','running'].includes(job.status);$('render').disabled=['queued','running'].includes(job.status);$('voiceGenerate').disabled=!voiceLanguages.includes($('voiceLanguage').value)||['queued','running'].includes(job.status);$('shortPreview').disabled=['queued','running'].includes(job.status)||!project.media.some(x=>x.generated_by==='piper_local');$('shortRender').disabled=$('shortPreview').disabled;}
function renderOutputs(){const box=$('outputs');box.replaceChildren();let videos=[];for(const output of project?.outputs||[]){const anchor=el('a',output.name.endsWith('.mp4')?'Télécharger '+output.name:output.name);anchor.href=output.url;anchor.target='_blank';anchor.rel='noreferrer';box.append(anchor);if(output.name.endsWith('.mp4'))videos.push(output);}const video=$('video');if(videos.length){const last=videos.find(x=>x.name===project?.job?.output)||videos.find(x=>x.name==='final.mp4')||videos.find(x=>x.name==='narrated.mp4')||videos[0];if(!video.src||!video.src.includes(last.url)){video.src=last.url;video.load();}show('video',true);}else show('video',false);}
async function runExport(preview){try{await save();project.job={status:'queued',preview};updateJob();await api(`/api/projects/${projectId}/render`,{method:'POST',body:{preview}});message('Montage demandé. Les médias restent sur ton serveur, sans API de génération.');if(timer)clearInterval(timer);timer=setInterval(poll,2500);}catch(e){project.job={status:'failed',error:e.message};updateJob();message(e.message,true);}}
async function generateVoice(){
 if(!voiceEnabled){message('Modèle Piper non configuré sur le serveur.',true);return;}
 const text=$('voiceText').value.trim(),language=$('voiceLanguage').value;
 if(!voiceLanguages.includes(language)){message('Installer le modèle vocal de la langue choisie sur le serveur.',true);return;}
 if(text.length<2||text.length>1200||!$('voiceConsent').checked){message('Renseigner 2–1200 caractères et confirmer les droits de la voix.',true);return;}
 try{
   await api('/api/projects/'+projectId+'/voice',{method:'POST',body:{text,language,confirm_voice_rights:true}});
   project.job={status:'queued',kind:'voice',language};updateJob();
   message('Génération vocale '+(language==='fr'?'française':'anglaise')+' demandée sur le serveur.');
   if(timer)clearInterval(timer);timer=setInterval(poll,2500);
 }catch(e){message(e.message,true);}
}
async function poll(){if(!projectId)return;try{const latest=await api('/api/projects/'+projectId);project.job=latest.job;project.outputs=latest.outputs;updateJob();if(['completed','failed','idle'].includes(project.job.status)){clearInterval(timer);timer=null;renderOutputs();if(project.job.kind==='voice'&&project.job.status==='completed'){project.media=latest.media;renderMedia();message('Voix '+(project.job.language==='en'?'anglaise':'française')+' générée : écouter le WAV dans la bibliothèque.');}else if(project.job.kind==='narrated'&&project.job.status==='completed')message('Short narré terminé. Visualiser les images, écouter l’audio et vérifier la publicité.');else if(project.job.status==='completed')message('Export terminé. Visionne et vérifie le fichier avant publication.');if(project.job.status==='failed')message(project.job.error||'Erreur du travail.',true);}}catch(e){message(e.message,true);}}
function events(){ $('connect').addEventListener('click',connect);$('token').addEventListener('keydown',e=>{if(e.key==='Enter')connect()});$('create').addEventListener('click',createProject);$('projects').addEventListener('change',async e=>{projectId=e.target.value;try{await loadProject();}catch(err){message(err.message,true);}});$('upload').addEventListener('click',uploadFiles);$('addClip').addEventListener('click',()=>{const v=project.media.find(x=>x.type==='video');if(!v){message('Importer une vidéo parlée d’abord.',true);return;}collectForm();draft.talking_clips.push({file:v.file,source_in:0,duration:Math.max(.2,+(v.duration||0).toFixed(3)),rights:'',sync:'native',smart_crop:'off'});renderEditor();});$('addOverlay').addEventListener('click',()=>{const m=project.media.find(x=>x.type==='image'||x.type==='video');if(!m){message('Importer une image ou une vidéo produit d’abord.',true);return;}collectForm();draft.overlays.push({file:m.file,start:1,duration:2,rights:'',motion:'static',layout:'pip_right',fade:.12});renderEditor();});$('voiceLanguage').addEventListener('change',()=>{if(project)updateJob();});$('voiceGenerate').addEventListener('click',generateVoice);$('shortPreview').addEventListener('click',()=>runNarrated(true));$('shortRender').addEventListener('click',()=>runNarrated(false));$('save').addEventListener('click',async()=>{try{await save();}catch(e){message(e.message,true);}});$('preview').addEventListener('click',()=>runExport(true));$('render').addEventListener('click',()=>runExport(false));}
events();$('token').value=token;if(token)connect();
