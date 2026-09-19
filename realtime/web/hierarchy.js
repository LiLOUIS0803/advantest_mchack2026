/* Progressive disclosure: overview -> distribution -> records -> evidence. */
(() => {
const $=id=>document.getElementById(id),main=document.querySelector('main');

const heading=(n,title)=>{const x=document.createElement('div');x.className='layer-heading';x.innerHTML=`<b>${n}</b><h2>${title}</h2>`;return x;};
const hero=document.createElement('section');hero.id='wafer-summary';hero.className='hero';hero.innerHTML='<div><div class="hero-label">WAFER OVERVIEW</div><div id="hero-identity"></div><div id="hero-status"></div></div><div class="hero-end"><div class="sub">Completed / Total dies</div><div id="hero-completed"></div><div id="hero-batch"></div></div>';
hero.querySelector('#hero-identity').append($('identity'));hero.querySelector('#hero-status').append($('status'));hero.querySelector('#hero-completed').append($('completed'));hero.querySelector('#hero-batch').append($('batch'));
const actual=$('actual-overview');actual.before(hero);
const waferShell=$('wafer-panel'),waferCard=$('wafer-map').closest('.card'),measurement=$('raw-chart').closest('.card');
const trend=$('chart').closest('.card'),oldTrend=trend.parentElement,benefits=$('potential').closest('.card');
const distribution=document.createElement('section');distribution.id='distribution';distribution.className='overview-grid';distribution.append(waferCard,trend);waferShell.replaceWith(distribution);
distribution.before(heading('','Wafer overview'));
const records=document.createElement('section');records.id='records';records.className='card record-shell';records.innerHTML='<div class="record-tabs" role="tablist" aria-label="Event history"><button id="fail-tab" role="tab" aria-controls="fail-results" aria-selected="true">Confirmed Fail</button><button id="alert-tab" role="tab" aria-controls="alerts-panel" aria-selected="false">Model alerts</button></div>';
const fails=$('fail-results'),alerts=$('alerts-panel');fails.before(heading('','Records'),records);records.append(fails,alerts);alerts.hidden=true;
fails.setAttribute('role','tabpanel');alerts.setAttribute('role','tabpanel');fails.setAttribute('aria-labelledby','fail-tab');alerts.setAttribute('aria-labelledby','alert-tab');
function tab(which){fails.hidden=which!=='fail';alerts.hidden=which!=='alert';$('fail-tab').setAttribute('aria-selected',String(which==='fail'));$('alert-tab').setAttribute('aria-selected',String(which==='alert'));}
$('fail-tab').onclick=()=>tab('fail');$('alert-tab').onclick=()=>tab('alert');
for(const button of [$('fail-tab'),$('alert-tab')])button.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();const next=button.id==='fail-tab'?'alert':'fail';tab(next);$(next+'-tab').focus();}};
const evidence=$('evidence').closest('section'),investigation=document.createElement('aside');investigation.id='investigation';investigation.className='inspector';investigation.hidden=true;investigation.setAttribute('role','dialog');investigation.setAttribute('aria-modal','false');investigation.setAttribute('aria-labelledby','inspector-title');investigation.innerHTML='<div class="inspector-header"><h2 id="inspector-title">Test details</h2><button id="close-inspector" aria-label="Close details">✕</button></div>';records.after(investigation);investigation.append($('die-info'),measurement,evidence);
let restoreFocus=null;
window.openInvestigation=()=>{if(investigation.hidden)restoreFocus=document.activeElement;investigation.hidden=false;};
const close=()=>{investigation.hidden=true;restoreFocus?.focus?.({preventScroll:true});};
$('close-inspector').onclick=close;
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!investigation.hidden){close();e.preventDefault();}});
$('start').addEventListener('click',close);
const choose=window.selectWaferDevice;window.selectWaferDevice=key=>{choose?.(key);window.openInvestigation();};
$('wafer-map').addEventListener('click',e=>{if(e.target.closest('[data-key]'))window.openInvestigation();});
$('wafer-map').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.closest('[data-key]'))window.openInvestigation();});
$('alerts').addEventListener('click',e=>{if(e.target.closest('[data-id]'))window.openInvestigation();});
const technical=document.createElement('details');technical.className='card technical';technical.innerHTML='<summary>Model details, alerts and potential savings</summary>';investigation.after(technical);
const model=document.querySelector('.model-overview'),labels=$('formal-labels').closest('section'),evaluation=$('model').closest('details');technical.append(model,labels,benefits,evaluation);oldTrend.remove();
const leftover=model.querySelectorAll('.card');for(const c of leftover)if(!c.querySelector('.value'))c.remove();
const progressNote=trend.querySelector('.note');if(progressNote)technical.append(progressNote);
// Keep operational context visible; put implementation notes behind disclosure.
for(const note of [...waferCard.querySelectorAll('.note'), ...fails.querySelectorAll('.note')]){
 if(note.id!=='map-count')technical.append(note);
}
hero.querySelector('.hero-label').textContent='Current wafer';
hero.querySelector('#hero-status').insertAdjacentHTML('afterbegin','<span class="sub">Model monitoring</span>');
document.querySelector('.breadcrumb').textContent='Test monitoring / Live overview';
document.querySelector('header h1').textContent='Wafer Watch';document.querySelector('header .sub:last-child').textContent='From wafer overview to individual die measurements.';
const links=document.querySelectorAll('.side-nav a');[['#wafer-summary','◉ Overview'],['#distribution','▦ Map & trends'],['#records','☷ Failed dies'],['#investigation','⌕ Test evidence']].forEach(([href,label],i)=>{links[i].href=href;links[i].textContent=label;links[i].title=label.slice(2);if(i===3)links[i].onclick=e=>{e.preventDefault();window.openInvestigation();$('close-inspector').focus({preventScroll:true});};});
// Explanations belong in help, not in the primary monitoring surface.
for(const note of [...measurement.querySelectorAll('.note'),...evidence.querySelectorAll('.note')]){
 if(note.id!=='test-name')technical.append(note);
}
technical.querySelector('summary').textContent='Help & model info';
document.querySelector('header .sub:last-child').hidden=true;
document.querySelector('.breadcrumb').hidden=true;
$('map-count').hidden=true;
document.querySelector('footer').hidden=true;
waferCard.querySelector('h2').textContent='Wafer';trend.querySelector('h2').textContent='Yield';
measurement.querySelector('h2').textContent='Tests';evidence.querySelector('h2').firstChild.textContent='Model evidence ';
actual.children[2].querySelector('.sub').textContent='Latest batch Fail';actual.children[3].querySelector('.sub').textContent='Current yield';
fails.querySelector('h2').hidden=true;fails.querySelector('summary').textContent='Fail details';
alerts.querySelector('.row .sub').hidden=true;
})();
