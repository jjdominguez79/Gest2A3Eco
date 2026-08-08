const api='/api/v1/messaging';
const $=id=>document.getElementById(id);
let conversations=[], current='', events;
const invite=new URLSearchParams(location.search).get('invite');
if(invite){$('login-form').hidden=true;$('invite-form').hidden=false;$('auth-help').textContent='Crea una contraseña para activar tu acceso.'}

async function request(path, options={}){
  const response=await fetch(api+path,{credentials:'same-origin',...options});
  if(!response.ok){let detail='Error de comunicación';try{detail=(await response.json()).detail||detail}catch{}throw new Error(detail)}
  const type=response.headers.get('content-type')||'';
  return type.includes('json')?response.json():response;
}
function showError(id,error){$(id).textContent=error?.message||String(error||'')}
$('login-form').addEventListener('submit',async e=>{e.preventDefault();try{const data=await request('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('email').value,password:$('password').value})});openChat(data.client)}catch(err){showError('auth-error',err)}});
$('invite-form').addEventListener('submit',async e=>{e.preventDefault();try{const data=await request('/auth/accept-invite',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:invite,password:$('invite-password').value})});history.replaceState({},'',location.pathname);openChat(data.client)}catch(err){showError('auth-error',err)}});
$('logout').onclick=async()=>{try{await request('/auth/logout',{method:'POST'})}finally{location.reload()}};

async function openChat(client={name:''}){$('auth').hidden=true;$('chat').hidden=false;$('client-name').textContent=client.name||'';await loadConversations();startEvents()}
async function loadConversations(){try{conversations=await request('/client/conversations');$('conversations').replaceChildren(...conversations.map(c=>{const b=document.createElement('button');b.textContent=c.kind==='private'?'Privado':'Despacho';b.className=c.id===current?'active':'';b.onclick=()=>selectConversation(c.id);return b}));if(!current&&conversations.length)await selectConversation(conversations[0].id)}catch(err){showError('chat-error',err)}}
async function selectConversation(id){current=id;await loadConversations();const rows=await request(`/client/conversations/${id}/messages`);await request(`/client/conversations/${id}/read`,{method:'POST'});const thread=$('thread');thread.replaceChildren(...rows.map(renderMessage));thread.scrollTop=thread.scrollHeight}
function renderMessage(m){const box=document.createElement('article');box.className='message '+(m.author_type==='client'?'mine':'');const meta=document.createElement('span');meta.className='meta';meta.textContent=`${m.author_name} · ${new Date(m.created_at).toLocaleString()}`;box.append(meta);if(m.body){const p=document.createElement('div');p.textContent=m.body;box.append(p)}for(const a of m.attachments){const link=document.createElement('a');link.className='attachment';link.textContent=`📎 ${a.name}`;if(a.direction==='outgoing')link.href=`${api}/client/attachments/${a.id}`;else{link.removeAttribute('href');link.title='Documento entregado al despacho'}box.append(link)}return box}
$('composer').addEventListener('submit',async e=>{e.preventDefault();if(!current)return;const form=new FormData();form.append('body',$('body').value);form.append('idempotency_key',crypto.randomUUID());for(const file of $('files').files)form.append('files',file);try{await request(`/client/conversations/${current}/messages`,{method:'POST',body:form});$('body').value='';$('files').value='';await selectConversation(current)}catch(err){showError('chat-error',err)}});
function startEvents(){if(events)events.close();events=new EventSource(`${api}/client/events`);events.onmessage=()=>current&&selectConversation(current);['message_created','conversation_updated'].forEach(name=>events.addEventListener(name,()=>{loadConversations();if(current)selectConversation(current)}));events.onerror=()=>setTimeout(startEvents,3000)}
request('/client/conversations').then(()=>openChat()).catch(()=>{});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/static/messaging-sw.js').catch(()=>{});
