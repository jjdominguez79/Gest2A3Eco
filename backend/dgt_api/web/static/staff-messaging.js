const API='/api/v1/messaging';
const byId=id=>document.getElementById(id);
const channelLabels={laboral:'Laboral',fiscal:'Contable / Fiscal',private:'Directo'};
const filterTitles={all:'Todos los clientes',laboral:'Clientes · Laboral',fiscal:'Clientes · Contable / Fiscal',private:'Privados con clientes',unread:'Mensajes no leídos'};
let me=null,conversations=[],internalThreads=[],staffDirectory=[],selectedId='',selectedInternalId='',filter='all',space='clients',events=null,selectedStaffFiles=[];

async function request(path,options={}){
  const response=await fetch(API+path,{credentials:'same-origin',...options});
  if(!response.ok){const error=new Error((await response.json().catch(()=>({}))).detail||'Error de comunicación');error.status=response.status;throw error}
  return (response.headers.get('content-type')||'').includes('json')?response.json():response;
}
function toast(message){const box=byId('toast');box.textContent=message;box.hidden=false;setTimeout(()=>box.hidden=true,3500)}
function pushErrorMessage(error){const message=String(error?.message||error||'');if(/push service error|registration failed/i.test(message))return navigator.brave?'Brave no tiene activo el servicio de mensajeria push. Abre brave://settings/privacy y activa "Utilizar los servicios de Google para la mensajeria push"; despues reinicia Brave.':'El navegador no ha podido conectar con su servicio de notificaciones. Reinicialo y comprueba los permisos del sitio.';return message||'No se pudieron activar los avisos'}
function staffFileSummary(file){const size=file.size<1024*1024?`${Math.max(1,Math.round(file.size/1024))} KB`:`${(file.size/1024/1024).toFixed(1)} MB`;return `${file.name} (${size})`}
function renderStaffFiles(){const summary=byId('message-selected-files');const label=byId('message-files-label');const picker=byId('composer-attach');if(!selectedStaffFiles.length){summary.hidden=true;summary.textContent='';label.textContent='Adjuntar';picker.classList.remove('has-files');return}summary.hidden=false;summary.textContent=`Adjuntos preparados: ${selectedStaffFiles.map(staffFileSummary).join(' · ')}`;label.textContent=selectedStaffFiles.length===1?'1 archivo':'Archivos ('+selectedStaffFiles.length+')';picker.classList.add('has-files')}
function clearStaffFiles(){selectedStaffFiles=[];byId('message-files').value='';renderStaffFiles()}
byId('message-files').addEventListener('change',()=>{selectedStaffFiles=Array.from(byId('message-files').files||[]);renderStaffFiles()})
function escapeText(value){return String(value||'')}

async function start(){
  try{me=await request('/staff/me')}catch(error){if(error.status===401){byId('staff-login').hidden=false;return}throw error}
  byId('staff-app').hidden=false;byId('staff-name').textContent=me.name;
  byId('admin-open').hidden=me.role!=='admin';
  await Promise.all([loadConversations(),loadInternalThreads(),loadStaffDirectory()]);
  configureNavigation();renderNavigation();
  const requested=new URLSearchParams(location.search).get('conversation');
  const requestedInternal=new URLSearchParams(location.search).get('internal');
  if(requested&&conversations.some(row=>row.id===requested))await selectConversation(requested);
  if(requestedInternal&&internalThreads.some(row=>row.id===requestedInternal))await selectInternalThread(requestedInternal);
  await preparePush();startEvents();
}
async function loadConversations(){
  conversations=await request('/staff/conversations');configureNavigation();renderConversations();renderBadges();
  if(selectedId&&!conversations.some(row=>row.id===selectedId))selectConversation('');
}
async function loadInternalThreads(){
  internalThreads=await request('/staff/internal/threads');renderNavigation();renderBadges();
  if(selectedInternalId&&!internalThreads.some(row=>row.id===selectedInternalId))selectInternalThread('');
}
async function loadStaffDirectory(){
  if(me.role!=='admin'){staffDirectory=[];return}
  staffDirectory=await request('/staff/admin/directory');renderNavigation();
}
function visibleConversations(){
  const query=byId('search').value.trim().toLowerCase();
  return conversations.filter(row=>{
    const channelOk=filter==='all'||(filter==='unread'?row.unread_count>0:row.kind===filter);
    return channelOk&&(!query||`${row.company_code} ${row.company_name}`.toLowerCase().includes(query));
  });
}
function renderConversations(){
  const root=byId('conversation-items');root.replaceChildren(...visibleConversations().map(row=>{
    const button=document.createElement('button');button.className='conversation-item'+(row.id===selectedId?' active':'');
    const top=document.createElement('div');top.className='row';
    const name=document.createElement('strong');name.textContent=row.company_name;
    const time=document.createElement('small');time.textContent=row.last_message?new Date(row.last_message.created_at).toLocaleString():'';
    top.append(name,time);
    const info=document.createElement('div');info.className='row';
    const kind=document.createElement('span');kind.className='pill';kind.textContent=channelLabels[row.kind]||row.kind;
    info.append(kind);
    if(row.unread_count){const unread=document.createElement('span');unread.className='pill unread';unread.textContent=String(row.unread_count);info.append(unread)}
    const preview=document.createElement('p');preview.textContent=row.last_message?.body||'Sin mensajes';
    button.append(top,info,preview);button.onclick=()=>selectConversation(row.id);return button;
  }));
}
function renderBadges(){
  const totals={all:0,laboral:0,fiscal:0,private:0};
  for(const row of conversations){totals.all+=row.unread_count||0;totals[row.kind]=(totals[row.kind]||0)+(row.unread_count||0)}
  for(const key of Object.keys(totals)){const badge=byId(`badge-${key}`);if(badge)badge.textContent=totals[key]?String(totals[key]):''}
  const unread=byId('badge-unread');if(unread)unread.textContent=totals.all?String(totals.all):'';
  const internalTotal=internalThreads.reduce((sum,row)=>sum+(row.unread_count||0),0);renderNavigation();
  const grandTotal=totals.all+internalTotal;if('setAppBadge' in navigator){grandTotal?navigator.setAppBadge(grandTotal):navigator.clearAppBadge()}
}
async function selectConversation(id){
  space='clients';selectedInternalId='';selectedId=id;renderConversations();renderNavigation();byId('empty-thread').hidden=!!id;byId('active-thread').hidden=!id;if(!id)return;
  const row=conversations.find(item=>item.id===id);if(!row)return;
  byId('staff-app').classList.add('thread-open');
  byId('thread-state').hidden=false;byId('composer-attach').hidden=false;
  byId('thread-company').textContent=`${row.company_name} · ${row.company_code}`;
  setThreadAvatar('',row.company_name,'client');
  byId('thread-channel').textContent=channelLabels[row.kind]||row.kind;byId('thread-state').value=row.state;
  const messages=await request(`/staff/conversations/${id}/messages`);
  await request(`/staff/conversations/${id}/read`,{method:'POST'});
  const root=byId('messages');root.replaceChildren(...messages.map(renderMessage));root.scrollTop=root.scrollHeight;
  await loadConversations();
}
async function selectInternalThread(id){
  space='team';selectedId='';selectedInternalId=id;renderConversations();renderNavigation();byId('empty-thread').hidden=!!id;byId('active-thread').hidden=!id;if(!id)return;
  const row=internalThreads.find(item=>item.id===id);if(!row)return;byId('staff-app').classList.add('thread-open');byId('thread-company').textContent=row.title;byId('thread-channel').textContent=row.kind==='group'?'Grupo interno del despacho':'Conversación privada';setThreadAvatar(row.counterpart_avatar_url||'',row.title,row.kind==='group'?'group':'person');byId('thread-state').hidden=true;byId('composer-attach').hidden=true;
  const messages=await request(`/staff/internal/threads/${id}/messages`);await request(`/staff/internal/threads/${id}/read`,{method:'POST'});const root=byId('messages');root.replaceChildren(...messages.map(renderMessage));root.scrollTop=root.scrollHeight;await loadInternalThreads();
}
function initials(value){return String(value||'?').split(/\s+/).filter(Boolean).slice(0,2).map(part=>part[0]).join('').toUpperCase()||'?'}
function setThreadAvatar(url,label,kind){const root=byId('thread-avatar');root.className=`thread-avatar ${kind||''}`;root.replaceChildren();root.hidden=false;if(url){const image=document.createElement('img');image.src=url;image.alt=`Foto de ${label}`;root.append(image)}else{root.textContent=initials(label)}}
function shortcutButton({label,subtitle='',avatarUrl='',unread=0,kind='',active=false,onClick}){const button=document.createElement('button');button.type='button';button.className='staff-shortcut'+(active?' active':'');const avatar=document.createElement('span');avatar.className=`shortcut-avatar ${kind}`;if(avatarUrl){const image=document.createElement('img');image.src=avatarUrl;image.alt='';avatar.append(image)}else avatar.textContent=initials(label);const text=document.createElement('span');text.className='shortcut-copy';const strong=document.createElement('strong');strong.textContent=label;const small=document.createElement('small');small.textContent=subtitle;text.append(strong,small);button.append(avatar,text);if(unread){const badge=document.createElement('span');badge.className='badge unread';badge.textContent=String(unread);button.append(badge)}button.onclick=onClick;return button}
function configureNavigation(){if(!me)return;const kinds=new Set(conversations.map(row=>row.kind));const permissions=new Set(me.channels||[]);const buttons=[...document.querySelectorAll('#client-navigation [data-channel]')];for(const button of buttons){const permission=button.dataset.permission;let visible=true;if(permission==='laboral'||permission==='fiscal')visible=me.role==='admin'||permissions.has(permission);if(permission==='private')visible=kinds.has('private');if(button.dataset.channel==='all'&&me.role!=='admin'){const available=['laboral','fiscal','private'].filter(kind=>(kind==='private'?kinds.has(kind):permissions.has(kind)));visible=available.length>1}button.hidden=!visible}const active=buttons.find(button=>button.dataset.channel===filter&&!button.hidden);if(!active){const first=buttons.find(button=>!button.hidden&&button.dataset.channel!=='unread');filter=first?.dataset.channel||'unread'}for(const button of buttons)button.classList.toggle('active',button.dataset.channel===filter);byId('list-title').textContent=filterTitles[filter]||'Conversaciones'}
function renderNavigation(){if(!me)return;const teams=internalThreads.filter(row=>row.kind==='group');byId('team-navigation').hidden=!teams.length;byId('team-shortcuts').replaceChildren(...teams.map(row=>shortcutButton({label:row.title,subtitle:'Grupo interno',unread:row.unread_count,kind:'group',active:row.id===selectedInternalId,onClick:()=>selectInternalThread(row.id)})));let people=[];if(me.role==='admin'){people=staffDirectory.filter(row=>row.active&&row.id!==me.id).map(person=>({person,thread:internalThreads.find(row=>row.kind==='direct'&&row.counterpart_id===person.id)}))}else{people=internalThreads.filter(row=>row.kind==='direct').map(thread=>({person:{id:thread.counterpart_id,name:thread.counterpart_name||thread.title,chat_alias:thread.title,avatar_configured:!!thread.counterpart_avatar_url},thread}))}byId('people-navigation').hidden=!people.length;byId('people-title').textContent=me.role==='admin'?'Personas':'Privados';byId('people-shortcuts').replaceChildren(...people.map(({person,thread})=>shortcutButton({label:person.chat_alias||person.name,subtitle:thread?'Chat privado':'Abrir chat',avatarUrl:person.avatar_configured?`${API}/staff/avatars/${person.id}`:'',unread:thread?.unread_count||0,kind:'person',active:thread?.id===selectedInternalId,onClick:()=>openPerson(person.id,thread?.id)})))}
async function openPerson(memberId,threadId){try{let id=threadId;if(!id){if(me.role!=='admin')return;const thread=await request(`/staff/internal/direct/${memberId}`,{method:'POST'});id=thread.id;await loadInternalThreads()}await selectInternalThread(id)}catch(error){toast(error.message)}}
function renderMessage(row){
  const article=document.createElement('article');article.className='message'+((row.author_type==='staff'||row.author_id===me.id)?' mine':'');
  const author=document.createElement('div');author.className='message-author';if(row.author_avatar_url){const avatar=document.createElement('img');avatar.className='message-avatar';avatar.src=row.author_avatar_url;avatar.alt='';author.append(avatar)}const meta=document.createElement('span');meta.className='meta';meta.textContent=`${row.author_name} · ${new Date(row.created_at).toLocaleString()}`;author.append(meta);article.append(author);
  if(row.body){const body=document.createElement('div');body.textContent=row.body;article.append(body)}
  for(const file of row.attachments||[]){const link=document.createElement('a');link.textContent=`📎 ${file.name}`;if(!file.local_confirmed)link.href=`${API}/staff/attachments/${file.id}/download`;else link.title='Documento entregado al repositorio del despacho';article.append(link)}
  return article;
}
byId('composer').onsubmit=async event=>{
  event.preventDefault();if(space==='team'){if(!selectedInternalId)return;const data=new FormData();data.append('body',byId('message-body').value);data.append('idempotency_key',crypto.randomUUID());try{await request(`/staff/internal/threads/${selectedInternalId}/messages`,{method:'POST',body:data});byId('message-body').value='';await selectInternalThread(selectedInternalId)}catch(error){toast(error.message)}return}if(!selectedId)return;
  const data=new FormData();data.append('body',byId('message-body').value);data.append('idempotency_key',crypto.randomUUID());
  const files=Array.from(selectedStaffFiles);for(const file of files)data.append('files',file,file.name);const send=byId('send-message');const picker=byId('composer-attach');send.disabled=true;picker.classList.add('uploading');
  try{const sent=await request(`/staff/conversations/${selectedId}/messages`,{method:'POST',body:data});if(files.length&&(sent.attachments||[]).length!==files.length)throw new Error('El mensaje llegó, pero el servidor no confirmó todos los adjuntos. No vuelvas a enviarlo.');byId('message-body').value='';clearStaffFiles();await selectConversation(selectedId)}catch(error){toast(error.message)}finally{send.disabled=false;picker.classList.remove('uploading')}
};
byId('thread-state').onchange=async()=>{if(space==='clients'&&selectedId){await request(`/staff/conversations/${selectedId}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:byId('thread-state').value})});await loadConversations()}};
document.querySelectorAll('#client-navigation .channel').forEach(button=>button.onclick=()=>{space='clients';filter=button.dataset.channel;selectedInternalId='';configureNavigation();renderNavigation();renderConversations()});
function closeMobileThread(){byId('staff-app').classList.remove('thread-open');byId('active-thread').hidden=true;byId('empty-thread').hidden=false;selectedId='';selectedInternalId='';renderConversations();renderNavigation()}
byId('thread-back').onclick=closeMobileThread;
byId('search').oninput=renderConversations;byId('refresh').onclick=()=>Promise.all([loadConversations(),loadInternalThreads(),loadStaffDirectory()]);
byId('staff-logout').onclick=async()=>{await request('/staff-auth/logout',{method:'POST'});location.reload()};
function base64Bytes(value){const padding='='.repeat((4-value.length%4)%4);const raw=atob((value+padding).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...raw].map(char=>char.charCodeAt(0)))}
async function preparePush(){
  const button=byId('push-enable');button.hidden=false;
  if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window)){setPushButton('blocked','Avisos no disponibles');button.disabled=true;return}
  const config=await request('/staff/push/config');if(!config.enabled){setPushButton('blocked','Avisos sin configurar');button.disabled=true;return}
  const registration=await navigator.serviceWorker.ready;const current=await registration.pushManager.getSubscription();
  if(current){await savePush(current);setPushButton('active','Avisos activos');button.onclick=testPush;return}
  if(Notification.permission==='denied'){setPushButton('blocked','Avisos bloqueados');button.onclick=()=>toast('Permite las notificaciones de Gestinem en la configuracion del navegador');return}
  setPushButton('needs-action','Activar avisos');button.onclick=async()=>{try{if(await Notification.requestPermission()!=='granted'){setPushButton('blocked','Avisos bloqueados');return}const subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64Bytes(config.public_key)});await savePush(subscription);setPushButton('active','Avisos activos');button.onclick=testPush;await testPush()}catch(error){toast(pushErrorMessage(error))}};
}
function setPushButton(state,text){const button=byId('push-enable');button.classList.remove('needs-action','active','blocked');button.classList.add(state);button.textContent=text}
async function savePush(subscription){const value=subscription.toJSON();await request('/staff/push/subscriptions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:value.endpoint,p256dh:value.keys.p256dh,auth:value.keys.auth})})}
async function testPush(){try{await request('/staff/push/test',{method:'POST'});toast('Notificación de prueba enviada')}catch(error){toast(error.message)}}
function startEvents(){if(events)events.close();events=new EventSource(`${API}/staff/events`);const refresh=()=>{loadConversations();if(space==='clients'&&selectedId)selectConversation(selectedId)};['message_created','conversation_updated'].forEach(name=>events.addEventListener(name,refresh));events.addEventListener('internal_message',()=>{loadInternalThreads();if(space==='team'&&selectedInternalId)selectInternalThread(selectedInternalId)});events.onerror=()=>{events.close();setTimeout(startEvents,3000)}}

byId('admin-open').onclick=async()=>{await loadAdmin();byId('admin-dialog').showModal()};
async function loadAdmin(){
  const [staff,organizations]=await Promise.all([request('/staff/admin/directory'),request('/staff/admin/organizations')]);const root=byId('staff-directory');root.replaceChildren(...staff.map(row=>{
    const box=document.createElement('div');box.className='staff-row';const who=document.createElement('div');const strong=document.createElement('strong');strong.textContent=row.name;const small=document.createElement('small');small.textContent=row.email||row.id;
    const status=document.createElement('span');status.className='staff-status'+(row.active?'':' suspended');status.textContent=row.active?(row.linked?'Acceso activado':'Pendiente del primer acceso'):'Suspendido';who.append(strong,small,status);
    const identity=document.createElement('div');identity.className='staff-identity';const avatar=document.createElement('div');avatar.className='staff-avatar';if(row.avatar_configured){const image=document.createElement('img');image.src=`${API}/staff/avatars/${row.id}?v=${Date.now()}`;image.alt=`Imagen de ${row.chat_alias||row.name}`;avatar.append(image)}else avatar.textContent=(row.chat_alias||row.name||'?').slice(0,1).toUpperCase();identity.append(avatar,who);
    const profile=document.createElement('div');profile.className='staff-profile';const alias=document.createElement('input');alias.value=row.chat_alias||'';alias.maxLength=160;alias.placeholder='Alias visible en el chat';alias.setAttribute('aria-label',`Alias de ${row.name}`);const avatarFile=document.createElement('input');avatarFile.type='file';avatarFile.accept='image/png,image/jpeg,image/webp';avatarFile.setAttribute('aria-label',`Imagen de ${row.name}`);profile.append(alias,avatarFile);
    const checks=document.createElement('div');checks.className='staff-checks';
    for(const channel of ['laboral','fiscal']){const label=document.createElement('label');const input=document.createElement('input');input.type='checkbox';input.checked=row.channels.includes(channel);input.dataset.channel=channel;label.append(input,document.createTextNode(channel==='laboral'?' Laboral':' Fiscal'));checks.append(label)}
    const adminLabel=document.createElement('label');const adminCheck=document.createElement('input');adminCheck.type='checkbox';adminCheck.checked=row.role==='admin';adminLabel.append(adminCheck,document.createTextNode(' Administrador'));checks.append(adminLabel);
    const activeLabel=document.createElement('label');const activeCheck=document.createElement('input');activeCheck.type='checkbox';activeCheck.checked=row.active;activeLabel.append(activeCheck,document.createTextNode(' Activo'));checks.append(activeLabel);
    const actions=document.createElement('div');actions.className='staff-actions';
    if(row.avatar_configured){const removeAvatar=document.createElement('button');removeAvatar.type='button';removeAvatar.className='ghost danger';removeAvatar.textContent='Quitar imagen';removeAvatar.onclick=async()=>{try{await request(`/staff/admin/directory/${row.id}/avatar`,{method:'DELETE'});toast('Imagen eliminada');await loadAdmin()}catch(error){toast(error.message)}};actions.append(removeAvatar)}
    if(row.linked&&row.id!==me.id){const revoke=document.createElement('button');revoke.type='button';revoke.className='ghost danger';revoke.textContent='Cerrar sesiones';revoke.onclick=async()=>{try{await request(`/staff/admin/directory/${row.id}/revoke-sessions`,{method:'POST'});toast('Sesiones cerradas')}catch(error){toast(error.message)}};actions.append(revoke)}
    const save=document.createElement('button');save.type='button';save.className='ghost';save.textContent='Guardar';save.onclick=async()=>{const channels=[...checks.querySelectorAll('input[data-channel]:checked')].map(input=>input.dataset.channel);try{await request(`/staff/admin/directory/${row.id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({channels,active:activeCheck.checked,role:adminCheck.checked?'admin':'empleado',chat_alias:alias.value.trim()})});if(avatarFile.files[0]){const data=new FormData();data.append('avatar',avatarFile.files[0]);await request(`/staff/admin/directory/${row.id}/avatar`,{method:'PUT',body:data})}toast('Usuario actualizado');await loadAdmin()}catch(error){toast(error.message)}};actions.append(save);box.append(identity,profile,checks,actions);return box;
  }));
  staffDirectory=staff;renderNavigation();
  const owner=byId('invite-owner');owner.replaceChildren(...staff.filter(row=>row.active).map(row=>{const option=document.createElement('option');option.value=row.id;option.textContent=`${row.name} (${row.email||row.id})`;option.selected=row.id===me.id;return option}));
  const organization=byId('invite-organization');const available=organizations.filter(row=>row.active);const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=available.length?'Seleccione un cliente':'No hay clientes sincronizados';organization.replaceChildren(placeholder,...available.map(row=>{const option=document.createElement('option');option.value=row.company_code;option.dataset.name=row.name;option.textContent=`${row.name} (${row.company_code})`;return option}));
}
byId('staff-create-form').onsubmit=async event=>{
  event.preventDefault();const result=byId('staff-create-result');result.textContent='';
  const channels=[];if(byId('staff-create-laboral').checked)channels.push('laboral');if(byId('staff-create-fiscal').checked)channels.push('fiscal');
  try{
    const created=await request('/staff/admin/directory',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:byId('staff-create-name').value.trim(),email:byId('staff-create-email').value.trim(),chat_alias:byId('staff-create-alias').value.trim(),channels,role:byId('staff-create-admin').checked?'admin':'empleado',active:true})});
    if(byId('staff-create-avatar').files[0]){const data=new FormData();data.append('avatar',byId('staff-create-avatar').files[0]);try{await request(`/staff/admin/directory/${created.id}/avatar`,{method:'PUT',body:data})}catch(error){event.target.reset();result.textContent=`Usuario autorizado, pero la imagen no se guardó: ${error.message}`;await loadAdmin();return}}
    event.target.reset();result.textContent='Usuario autorizado. Ya puede entrar con Microsoft 365.';await loadAdmin();
  }catch(error){result.textContent=error.message}
};
byId('invite-form').onsubmit=async event=>{
  event.preventDefault();const organization=byId('invite-organization');const code=organization.value;const company=organization.selectedOptions[0]?.dataset.name||'';
  try{
    await request(`/staff/admin/organizations/${encodeURIComponent(code)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_code:code,name:company,private_owner_external_id:byId('invite-owner').value,active:true})});
    const isTest=byId('invite-test').checked;
    const result=await request('/staff/admin/invitations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_code:code,name:byId('invite-name').value.trim(),email:byId('invite-email').value.trim(),send_email:!isTest})});
    const status=byId('admin-result');status.replaceChildren(document.createTextNode(result.email_queued?'Invitación enviada por email. ':'Cuenta de prueba creada sin enviar email. '));
    const link=document.createElement('a');link.href=result.url;link.target='_blank';link.rel='noopener';link.textContent='Abrir enlace de activación';status.append(link);
  }catch(error){byId('admin-result').textContent=error.message}
};
if('serviceWorker' in navigator)navigator.serviceWorker.register('/equipo/mensajes-sw.js',{scope:'/equipo/'}).catch(()=>{});
start().catch(error=>{byId('staff-login').hidden=false;toast(error.message)});
