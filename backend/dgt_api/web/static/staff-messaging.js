const API='/api/v1/messaging';
const byId=id=>document.getElementById(id);
const channelLabels={laboral:'Laboral',fiscal:'Contable / Fiscal',private:'Directo'};
let me=null,conversations=[],internalThreads=[],selectedId='',selectedInternalId='',filter='all',space='clients',events=null;

async function request(path,options={}){
  const response=await fetch(API+path,{credentials:'same-origin',...options});
  if(!response.ok){const error=new Error((await response.json().catch(()=>({}))).detail||'Error de comunicación');error.status=response.status;throw error}
  return (response.headers.get('content-type')||'').includes('json')?response.json():response;
}
function toast(message){const box=byId('toast');box.textContent=message;box.hidden=false;setTimeout(()=>box.hidden=true,3500)}
function escapeText(value){return String(value||'')}

async function start(){
  try{me=await request('/staff/me')}catch(error){if(error.status===401){byId('staff-login').hidden=false;return}throw error}
  byId('staff-app').hidden=false;byId('staff-name').textContent=me.name;
  byId('admin-open').hidden=me.role!=='admin';
  await Promise.all([loadConversations(),loadInternalThreads()]);
  const requested=new URLSearchParams(location.search).get('conversation');
  const requestedInternal=new URLSearchParams(location.search).get('internal');
  if(requested&&conversations.some(row=>row.id===requested))await selectConversation(requested);
  if(requestedInternal&&internalThreads.some(row=>row.id===requestedInternal)){switchSpace('team');await selectInternalThread(requestedInternal)}
  await preparePush();startEvents();
}
async function loadConversations(){
  conversations=await request('/staff/conversations');renderConversations();renderBadges();
  if(selectedId&&!conversations.some(row=>row.id===selectedId))selectConversation('');
}
async function loadInternalThreads(){
  internalThreads=await request('/staff/internal/threads');renderConversations();renderBadges();
  if(selectedInternalId&&!internalThreads.some(row=>row.id===selectedInternalId))selectInternalThread('');
}
function visibleConversations(){
  const query=byId('search').value.trim().toLowerCase();
  return conversations.filter(row=>{
    const channelOk=filter==='all'||(filter==='unread'?row.unread_count>0:row.kind===filter);
    return channelOk&&(!query||`${row.company_code} ${row.company_name}`.toLowerCase().includes(query));
  });
}
function renderConversations(){
  if(space==='team'){renderInternalThreads();return}
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
function renderInternalThreads(){
  const query=byId('search').value.trim().toLowerCase();const root=byId('conversation-items');root.replaceChildren(...internalThreads.filter(row=>!query||row.title.toLowerCase().includes(query)).map(row=>{
    const button=document.createElement('button');button.className='conversation-item'+(row.id===selectedInternalId?' active':'');
    const top=document.createElement('div');top.className='row';const name=document.createElement('strong');name.textContent=row.title;const time=document.createElement('small');time.textContent=row.last_message?new Date(row.last_message.created_at).toLocaleString():'';top.append(name,time);
    const info=document.createElement('div');info.className='row';const kind=document.createElement('span');kind.className='pill';kind.textContent=row.kind==='group'?'Grupo interno':'Privado';info.append(kind);if(row.unread_count){const unread=document.createElement('span');unread.className='pill unread';unread.textContent=String(row.unread_count);info.append(unread)}
    const preview=document.createElement('p');preview.textContent=row.last_message?.body||'Sin mensajes';button.append(top,info,preview);button.onclick=()=>selectInternalThread(row.id);return button;
  }))
}
function renderBadges(){
  const totals={all:0,laboral:0,fiscal:0,private:0};
  for(const row of conversations){totals.all+=row.unread_count||0;totals[row.kind]=(totals[row.kind]||0)+(row.unread_count||0)}
  for(const key of Object.keys(totals)){const badge=byId(`badge-${key}`);if(badge)badge.textContent=totals[key]?String(totals[key]):''}
  const internalTotal=internalThreads.reduce((sum,row)=>sum+(row.unread_count||0),0);byId('badge-clients').textContent=totals.all?String(totals.all):'';byId('badge-team').textContent=internalTotal?String(internalTotal):'';
  const grandTotal=totals.all+internalTotal;if('setAppBadge' in navigator){grandTotal?navigator.setAppBadge(grandTotal):navigator.clearAppBadge()}
}
async function selectConversation(id){
  selectedId=id;renderConversations();byId('empty-thread').hidden=!!id;byId('active-thread').hidden=!id;if(!id)return;
  const row=conversations.find(item=>item.id===id);if(!row)return;
  byId('thread-state').hidden=false;byId('composer-attach').hidden=false;
  byId('thread-company').textContent=`${row.company_name} · ${row.company_code}`;
  byId('thread-channel').textContent=channelLabels[row.kind]||row.kind;byId('thread-state').value=row.state;
  const messages=await request(`/staff/conversations/${id}/messages`);
  await request(`/staff/conversations/${id}/read`,{method:'POST'});
  const root=byId('messages');root.replaceChildren(...messages.map(renderMessage));root.scrollTop=root.scrollHeight;
  await loadConversations();
}
async function selectInternalThread(id){
  selectedInternalId=id;renderConversations();byId('empty-thread').hidden=!!id;byId('active-thread').hidden=!id;if(!id)return;
  const row=internalThreads.find(item=>item.id===id);if(!row)return;byId('thread-company').textContent=row.title;byId('thread-channel').textContent=row.kind==='group'?'Grupo interno del despacho':'Conversación privada';byId('thread-state').hidden=true;byId('composer-attach').hidden=true;
  const messages=await request(`/staff/internal/threads/${id}/messages`);await request(`/staff/internal/threads/${id}/read`,{method:'POST'});const root=byId('messages');root.replaceChildren(...messages.map(renderMessage));root.scrollTop=root.scrollHeight;await loadInternalThreads();
}
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
  for(const file of byId('message-files').files)data.append('files',file);
  try{await request(`/staff/conversations/${selectedId}/messages`,{method:'POST',body:data});byId('message-body').value='';byId('message-files').value='';await selectConversation(selectedId)}catch(error){toast(error.message)}
};
byId('thread-state').onchange=async()=>{if(space==='clients'&&selectedId){await request(`/staff/conversations/${selectedId}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:byId('thread-state').value})});await loadConversations()}};
document.querySelectorAll('#client-channels .channel').forEach(button=>button.onclick=()=>{filter=button.dataset.channel;document.querySelectorAll('#client-channels .channel').forEach(item=>item.classList.toggle('active',item===button));renderConversations()});
function switchSpace(next){space=next;byId('space-clients').classList.toggle('active',space==='clients');byId('space-team').classList.toggle('active',space==='team');byId('client-channels').hidden=space==='team';byId('internal-new-direct').hidden=space!=='team'||me.role!=='admin';byId('list-title').textContent=space==='team'?'Equipo':'Conversaciones';byId('search').placeholder=space==='team'?'Buscar chat interno':'Buscar cliente';byId('empty-thread').hidden=false;byId('active-thread').hidden=true;renderConversations()}
byId('space-clients').onclick=()=>switchSpace('clients');byId('space-team').onclick=()=>switchSpace('team');
byId('search').oninput=renderConversations;byId('refresh').onclick=()=>space==='team'?loadInternalThreads():loadConversations();
byId('staff-logout').onclick=async()=>{await request('/staff-auth/logout',{method:'POST'});location.reload()};
function base64Bytes(value){const padding='='.repeat((4-value.length%4)%4);const raw=atob((value+padding).replace(/-/g,'+').replace(/_/g,'/'));return Uint8Array.from([...raw].map(char=>char.charCodeAt(0)))}
async function preparePush(){
  if(!('serviceWorker' in navigator)||!('PushManager' in window))return;
  const config=await request('/staff/push/config');if(!config.enabled)return;
  const registration=await navigator.serviceWorker.ready;const current=await registration.pushManager.getSubscription();
  byId('push-enable').hidden=!!current;if(current)await savePush(current);
  byId('push-enable').onclick=async()=>{if(await Notification.requestPermission()!=='granted')return;const subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:base64Bytes(config.public_key)});await savePush(subscription);byId('push-enable').hidden=true;toast('Avisos activados')};
}
async function savePush(subscription){const value=subscription.toJSON();await request('/staff/push/subscriptions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({endpoint:value.endpoint,p256dh:value.keys.p256dh,auth:value.keys.auth})})}
function startEvents(){if(events)events.close();events=new EventSource(`${API}/staff/events`);const refresh=()=>{loadConversations();if(space==='clients'&&selectedId)selectConversation(selectedId)};['message_created','conversation_updated'].forEach(name=>events.addEventListener(name,refresh));events.addEventListener('internal_message',()=>{loadInternalThreads();if(space==='team'&&selectedInternalId)selectInternalThread(selectedInternalId)});events.onerror=()=>{events.close();setTimeout(startEvents,3000)}}

byId('internal-new-direct').onclick=async()=>{try{const staff=await request('/staff/admin/directory');const select=byId('internal-direct-member');select.replaceChildren(...staff.filter(row=>row.active&&row.id!==me.id).map(row=>{const option=document.createElement('option');option.value=row.id;option.textContent=`${row.chat_alias||row.name} (${row.email})`;return option}));if(!select.options.length){toast('No hay otros usuarios activos');return}byId('internal-direct-dialog').showModal()}catch(error){toast(error.message)}};
byId('internal-direct-form').onsubmit=async event=>{event.preventDefault();try{const thread=await request(`/staff/internal/direct/${byId('internal-direct-member').value}`,{method:'POST'});byId('internal-direct-dialog').close();await loadInternalThreads();switchSpace('team');await selectInternalThread(thread.id)}catch(error){toast(error.message)}};

byId('admin-open').onclick=async()=>{await loadAdmin();byId('admin-dialog').showModal()};
async function loadAdmin(){
  const staff=await request('/staff/admin/directory');const root=byId('staff-directory');root.replaceChildren(...staff.map(row=>{
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
  const owner=byId('invite-owner');owner.replaceChildren(...staff.filter(row=>row.active).map(row=>{const option=document.createElement('option');option.value=row.id;option.textContent=`${row.name} (${row.email||row.id})`;option.selected=row.id===me.id;return option}));
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
  event.preventDefault();const code=byId('invite-code').value.trim();
  try{
    await request(`/staff/admin/organizations/${encodeURIComponent(code)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_code:code,name:byId('invite-company').value.trim(),private_owner_external_id:byId('invite-owner').value,active:true})});
    const result=await request('/staff/admin/invitations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company_code:code,name:byId('invite-name').value.trim(),email:byId('invite-email').value.trim()})});
    byId('admin-result').textContent=result.email_queued?'Invitación enviada por email.':`Invitación creada: ${result.url}`;
  }catch(error){byId('admin-result').textContent=error.message}
};
if('serviceWorker' in navigator)navigator.serviceWorker.register('/static/staff-messaging-sw.js').catch(()=>{});
start().catch(error=>{byId('staff-login').hidden=false;toast(error.message)});
