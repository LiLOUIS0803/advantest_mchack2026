(() => {
const $=id=>document.getElementById(id),api=window.dashboardAPI;
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const score=c=>c?`${(c.score*100).toFixed(1)}%`:'—';
const confidence=document.createElement('span');confidence.id='classification-score';confidence.className='sub';confidence.title='Classifier probability; uncalibrated, not measured accuracy.';$('hero-status').append(confidence);
const render=window.renderVisuals;window.renderVisuals=(s,id)=>{render(s,id);confidence.textContent=s.classification_confidence?`Confidence ${score(s.classification_confidence)} · Uncalibrated`:'';};
const button=document.createElement('button');button.id='open-inbox';button.textContent='Notifications';document.querySelector('.controls').append(button);
const panel=document.createElement('aside');panel.id='inbox';panel.className='inspector';panel.hidden=true;panel.setAttribute('role','dialog');panel.setAttribute('aria-label','Notifications & report history');panel.innerHTML=`<div class="inspector-header"><h2>Notifications & reports</h2><button id="close-inbox" aria-label="Close notifications">✕</button></div><div class="inbox-filters"><input id="inbox-search" placeholder="Lot / Wafer / Class" aria-label="Search notifications"><select id="inbox-status" aria-label="Notification status"><option value="">All</option><option value="new">New</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option></select></div><div id="inbox-error" role="alert"></div><div id="inbox-list"></div><div id="inbox-report"></div><p class="note">Local notifications only. Replay events are simulated. Confidence is uncalibrated.</p>`;document.body.append(panel);
const toast=document.createElement('button');toast.className='notification-toast';toast.hidden=true;toast.setAttribute('aria-live','polite');document.body.append(toast);
let previous=null,selected=null,busy=false,closingFocus=null;
function open(){closingFocus=document.activeElement;panel.hidden=false;toast.hidden=true;refresh();}
function close(){panel.hidden=true;closingFocus?.focus?.({preventScroll:true});}
button.onclick=open;toast.onclick=open;$('close-inbox').onclick=close;
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!panel.hidden)close();});
async function detail(id){selected=id;try{const d=await api.get('/api/notifications/'+id),s=d.report.state;
$('inbox-report').innerHTML=`<hr><h2>W${esc(s.wafer)} · ${esc(d.label)}</h2><p>${esc(new Date(d.created_at).toLocaleString('en-US'))} · ${s.mode==='replay'?'Replay':'Live'}</p><p>Batch ${s.batch} · Completed ${s.completed} · Fail ${s.failed} · Yield ${s.yield==null?'—':(s.yield*100).toFixed(1)+'%'}</p><p>Confidence ${score(s.classification_confidence)} (Uncalibrated)</p><p>Trigger: ${d.report.trigger==='wafer_end'?'Wafer complete':'Same anomaly class for three consecutive batches'}</p><a href="/api/notifications/${id}" download="notification-${id}.json">Download event JSON</a><div class="inbox-filters"><button id="ack-event" ${d.status!=='new'?'disabled':''}>Acknowledge</button><button id="resolve-event" ${d.status==='resolved'?'disabled':''}>Resolve</button></div><p class="note">Snapshot at detection. Later predictions do not overwrite it. Resolved records an operator action, not confirmed recovery.</p>`;
for(const [key,status] of [['ack-event','acknowledged'],['resolve-event','resolved']])$(key).onclick=async()=>{try{await api.post('/api/notifications/'+id,{status});await detail(id);await refresh();}catch(e){$('inbox-error').textContent=e.message;}};
}catch(e){$('inbox-error').textContent=e.message;}}
async function refresh(){if(busy)return;busy=true;try{
const all=await api.get('/api/notifications');button.textContent=`Notifications${all.unread?' · '+all.unread:''}`;
const fresh=previous?all.items.find(x=>x.status==='new'&&!previous.has(x.id)):null;previous=new Set(all.items.map(x=>x.id));
if(fresh){toast.textContent=`W${fresh.wafer} · ${fresh.label} View notification`;toast.hidden=false;}
if(!panel.hidden){const q=$('inbox-search').value,status=$('inbox-status').value;const d=q||status?await api.get('/api/notifications?q='+encodeURIComponent(q)+'&status='+status):all;
$('inbox-list').innerHTML=d.items.length?d.items.map(x=>`<button class="inbox-item" data-id="${x.id}"><strong>W${esc(x.wafer)} · ${esc(x.label)}</strong><br><span class="sub">${esc(new Date(x.created_at).toLocaleString('en-US'))} · ${{new:'New',acknowledged:'Acknowledged',resolved:'Resolved'}[x.status]} · ${x.mode==='replay'?'Replay':'Live'}</span></button>`).join(''):'<p>No matching notifications.</p>';for(const item of $('inbox-list').querySelectorAll('[data-id]'))item.onclick=()=>detail(item.dataset.id);}
$('inbox-error').textContent='';
}catch(e){button.textContent='Notifications · Connection lost';$('inbox-error').textContent=e.message;}finally{busy=false;}}
$('inbox-search').oninput=refresh;$('inbox-status').onchange=refresh;refresh();setInterval(refresh,2000);
})();
