(() => {
const el=id=>document.getElementById(id), safe=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=x=>Number(x).toLocaleString('en-US',{maximumFractionDigits:3});
let tests=[], chosen=null, eventId=null, last=null, stream='', view='status'; window.vizTest=0;
const styles=document.createElement('style');styles.textContent='.layout.viz-layout{grid-template-columns:minmax(300px,1fr) minmax(400px,1.6fr)}@media(max-width:850px){.layout.viz-layout{grid-template-columns:1fr}}';document.head.append(styles);
const section=document.createElement('section');section.innerHTML=`
<div class="layout viz-layout">
<div class="card"><div class="row"><h2>Wafer map</h2><select id="map-mode" aria-label="Wafer view"><option value="status">Test status</option><option value="value">Selected measurement</option></select></div>
<svg id="wafer-map" viewBox="0 0 480 440" style="height:360px" aria-label="Wafer map of devices with known coordinates"></svg>
<div class="sub" id="map-legend"></div><div id="die-info" style="margin-top:12px">Select a die to inspect its PID and measurements.</div><div class="note" id="map-count"></div>
<div class="note">Received coordinates only. Y points upward; the outline is illustrative. Devices in an analysis window are not necessarily failed dies.</div></div>
<div class="card"><h2>Measurements · Linked to dies and events</h2><div style="display:flex;gap:8px;flex-wrap:wrap"><input id="test-filter" placeholder="Search tests" aria-label="Search tests" style="padding:8px;border-radius:8px;min-width:100px;width:24%"><select id="test-select" style="max-width:100%;flex:1;min-width:160px" aria-label="Select test"></select></div>
<div id="test-name" class="note" style="overflow-wrap:anywhere"></div><svg id="raw-chart" viewBox="0 0 700 220" style="height:240px" aria-label="Measurements and baseline limits"></svg><div class="sub">Green: measured · Dashed: model limits · Red: outlier · Ring: selected die</div>
<div class="note">X-axis: received device order. Hover for PID and value. Shading shows the model reference range, not product specifications.</div>
<h2 style="margin-top:20px">16-die rolling window</h2><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px"><div><div class="sub">Mean shift between 8-die windows / baseline scale</div><svg id="delta-chart" viewBox="0 0 700 220" style="height:165px"></svg></div><div><div class="sub">Standard deviation ratio: last 8 / previous 8 dies</div><svg id="spread-chart" viewBox="0 0 700 220" style="height:165px"></svg></div></div>
<div class="note">Window statistics update every 4 devices after 16 observations. Auxiliary trend evidence requires 5 tests across two windows and a baseline check.</div></div></div>`;
const anchor=document.querySelector('.metrics');anchor.after(section);
el('map-mode').onchange=()=>{view=el('map-mode').value;if(last)draw(last);};
function options(){const q=el('test-filter').value.toLowerCase();const ids=tests.map((t,i)=>i).filter(i=>tests[i].toLowerCase().includes(q)||i===window.vizTest);el('test-select').innerHTML=ids.map(i=>`<option value="${i}">${safe(tests[i])}</option>`).join('');el('test-select').value=window.vizTest;}
function selectTest(i){window.vizTest=i;options();if(typeof poll==='function')poll();}
el('test-filter').oninput=options;el('test-select').onchange=()=>selectTest(Number(el('test-select').value));
function loadTests(){window.dashboardAPI.get('/api/tests').then(d=>{tests=d.tests;options();}).catch(()=>{el('test-name').textContent='Waiting for Edge measurements';setTimeout(loadTests,2000);});}loadTests();
function plot(id,points,thresholds,selectedKey,band=false){
 const svg=el(id), vals=[...points.map(p=>p.v),...thresholds.map(t=>t.v)];
 if(!points.length){svg.innerHTML='<text x="65" y="110" fill="var(--muted)" font-size="17">Waiting for measurements</text>';return;}
 let lo=Math.min(...vals),hi=Math.max(...vals),pad=Math.max((hi-lo)*.12,Math.abs(hi)*.005,1e-5);lo-=pad;hi+=pad;
 const maxN=Math.max(16,...points.map(p=>p.n)),x=n=>62+(n-1)/Math.max(1,maxN-1)*618,y=v=>180-(v-lo)/(hi-lo)*150;
 let html='';if(band&&thresholds.length>=2)html+=`<rect x="62" y="${y(thresholds[1].v)}" width="618" height="${y(thresholds[0].v)-y(thresholds[1].v)}" fill="var(--band-fill)"/>`;
 for(let k=0;k<4;k++){const v=lo+(hi-lo)*k/3;html+=`<line x1="62" x2="680" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="2" y="${y(v)+4}" fill="var(--muted)" font-size="12">${num(v)}</text>`;}
 for(const t of thresholds)html+=`<line x1="62" x2="680" y1="${y(t.v)}" y2="${y(t.v)}" stroke="${t.color||'var(--amber)'}" stroke-dasharray="5 5"><title>${safe(t.name)}: ${num(t.v)}</title></line>`;
 html+=`<polyline fill="none" stroke="var(--green)" stroke-width="2" points="${points.map(p=>`${x(p.n)},${y(p.v)}`).join(' ')}"/>`;
 for(const p of points)html+=`<circle cx="${x(p.n)}" cy="${y(p.v)}" r="${p.key&&p.key===selectedKey?6:3}" fill="${p.outlier?'var(--red)':'var(--green)'}" stroke="${p.key&&p.key===selectedKey?'var(--select)':'none'}" stroke-width="2"><title>${safe(p.label||'Observation '+p.n+' ')} · ${num(p.v)}</title></circle>`;
 html+=`<text x="62" y="207" fill="var(--muted)" font-size="12">Observation 1 </text><text x="603" y="207" fill="var(--muted)" font-size="12">#${maxN} </text>`;svg.innerHTML=html;
}
function draw(s){
 const d=s.devices||[],known=d.filter(v=>v.x!=null&&v.y!=null),c=s.test_chart,valid=c&&c.index===window.vizTest,values=new Map(valid?c.points.map(p=>[p.key,p.value]):[]);
 el('map-count').textContent=`Known coordinates: ${known.length} dies · Coordinates pending: ${d.length-known.length} dies · Unseen devices are not shown`;
 const present=[...values.values()],vmin=Math.min(...present),vmax=Math.max(...present);
 if(view==='status')el('map-legend').innerHTML='<span><i style="background:var(--green)"></i>Pass</span><span><i style="background:var(--red)"></i>Fail</span><span><i style="background:var(--progress-gray)"></i>Testing</span>';
 else el('map-legend').textContent=present.length?`${num(vmin)} → ${num(vmax)}`:'No measurements yet';
 let html='<circle cx="240" cy="210" r="188" fill="var(--panel-alt)" stroke="var(--line)" stroke-dasharray="4 4"/>';
 if(known.length){const xmin=Math.min(...known.map(v=>v.x)),xmax=Math.max(...known.map(v=>v.x)),ymin=Math.min(...known.map(v=>v.y)),ymax=Math.max(...known.map(v=>v.y));
 const step=Math.min(32,310/Math.max(1,xmax-xmin+1,ymax-ymin+1)),xx=x=>240+(x-(xmin+xmax)/2)*step,yy=y=>210-(y-(ymin+ymax)/2)*step;
 for(const die of known){let color=die.completed?(die.passed?'var(--green)':'var(--red)'):'var(--progress-gray)';if(view==='value'){const v=values.get(die.key);color=v==null?'var(--line)':`hsl(${220-175*(v-vmin)/Math.max(vmax-vmin,1e-9)} 75% 62%)`;}
 const tooltip=`${die.pid==null?die.key:'PID '+die.pid} · X=${die.x}, Y=${die.y} · ${die.completed?(die.passed?'Pass':'Fail'):'In progress'}${values.has(die.key)?' · Value '+num(values.get(die.key)):''}`;
 html+=`<g data-key="${safe(die.key)}" role="button" tabindex="0" aria-label="${safe(tooltip)}" style="cursor:pointer"><title>${safe(tooltip)}</title><rect x="${xx(die.x)-step*.4}" y="${yy(die.y)-step*.4}" width="${step*.8}" height="${step*.8}" rx="3" fill="${color}" stroke="${chosen===die.key?'var(--select)':'var(--panel)'}" stroke-width="${chosen===die.key?3:2}"/></g>`;}
 html+=`<text x="50" y="420" fill="var(--muted)" font-size="13">X ${xmin} → ${xmax}  Y ${ymin} → ${ymax} ↑</text>`;
 }else html+='<text x="130" y="215" fill="var(--muted)" font-size="16">Waiting for die coordinates</text>';
 el('wafer-map').innerHTML=html;for(const node of el('wafer-map').querySelectorAll('[data-key]')){const choose=()=>{chosen=node.dataset.key;const die=d.find(x=>x.key===chosen);if(die.point_tests.length)selectTest(die.point_tests[0]);draw(s);};node.onclick=choose;node.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}};}
const die=d.find(v=>v.key===chosen);el('die-info').textContent=die?`${die.pid==null?'PID pending':'PID '+die.pid} · Batch ${die.batch} · Site ${die.site??'—'} · (${die.x??'?'}, ${die.y??'?'}) · ${die.point_tests.length} outlier tests${values.has(die.key)?' · Selected value '+num(values.get(die.key)):''}`:'Select a die to inspect its PID and measurements.';
 if(die)el('die-info').textContent+=` · ${die.completed?(die.passed?'Pass':'Fail'):'Testing'} · PF ${die.pf??'—'} · SBin ${die.sbin??'—'} / HBin ${die.hbin??'—'}`;
 el('test-name').textContent=tests[window.vizTest]||'';
 if(!valid){for(const id of ['raw-chart','delta-chart','spread-chart'])plot(id,[],[],chosen);return;}
 plot('raw-chart',c.points.map(p=>({...p,v:p.value,label:p.pid==null?p.key:'PID '+p.pid})),[{v:c.low,name:'Lower model limit'},{v:c.high,name:'Upper model limit'},{v:c.center,name:'Baseline mean',color:'var(--muted-soft)'}],chosen,true);
 plot('delta-chart',c.windows.map(p=>({...p,v:p.delta})),[{v:c.down,name:'Lower threshold'},{v:c.up,name:'Upper threshold'}]);
 plot('spread-chart',c.windows.map(p=>({...p,v:p.spread})),[{v:c.spread_low,name:'Lower SD ratio'},{v:c.spread_high,name:'Upper SD ratio'}]);
}
window.selectWaferDevice=key=>{chosen=key;view='status';el('map-mode').value=view;if(last)draw(last);};
window.renderVisuals=(s,id)=>{const identity=`${s.lot}:${s.wafer}`;if(identity!==stream||s.batch<(last?.batch||0)){chosen=null;eventId=null;stream=identity;}last=s;
 if(id!==eventId){eventId=id;const a=s.alerts.find(a=>a.id===id),test=a?.evidence.find(e=>e.test)?.test,i=tests.indexOf(test);if(i>=0){window.vizTest=i;options();}}
 draw(s);
 for(const row of document.querySelectorAll('#evidence tr')){const name=row.querySelector('td')?.textContent,index=tests.indexOf(name);if(index>=0){row.style.cursor='pointer';row.title='Select to view this test';row.onclick=()=>selectTest(index);}}
};
})();
