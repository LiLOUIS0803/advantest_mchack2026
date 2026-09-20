  // Target selection follows the supplied SmarTest flow, independently of live progress.
  let liveIdentity=null;
  let liveTemperature=null;
  let pausedMessage='',lastDisplayedAt=null,selectedPosition=null;
  const previewPanel=document.createElement('section');previewPanel.className='card';
  previewPanel.style.cssText='margin:16px;overflow-x:auto';
  previewPanel.innerHTML='<h2>Prediction target</h2><div id="flow-current" class="muted"></div><progress id="flow-progress" value="0" max="1" style="width:100%" aria-label="Latest received flow position"></progress><label style="display:flex;align-items:center;gap:12px;margin:14px 0">Target in test flow <input id="forecast-target" type="range" min="1" max="1" value="1" style="flex:1" aria-label="Prediction target in test flow"></label><div id="flow-targets" style="display:flex;gap:8px;flex-wrap:wrap"></div><h3 id="forecast-distance"></h3><div id="temperature-confidence" class="muted"></div><div id="forecast-preview"></div><p class="muted">Preview only &middot; Current measurements &middot; Not sent to tester</p>';
  document.querySelector('main').before(previewPanel);
  const escapePreview=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function renderForecast(){
    if(pausedMessage)$('status').textContent=pausedMessage;
    const flow=liveTemperature?.test_flow,steps=flow?.steps||[],targets=flow?.targets||[];
    const devices=(liveTemperature?.devices||[]).filter(d=>!d.completed);
    const active=!pausedMessage&&devices.length>0;
    const positions=devices.map(d=>d.flow_position).filter(Number.isFinite);
    $('flow-current').textContent=devices.length?devices.map(d=>`Site ${d.site}: ${d.current_suite||'Position unknown'}`).join(' | '):'Waiting for an active test';
    $('flow-progress').max=Math.max(1,steps.length);
    $('flow-progress').value=positions.length?Math.min(...positions):0;
    $('flow-progress').title='Received measurement-suite position; sites can advance separately. Not elapsed time.';
    if(selectedPosition===null&&targets.length)selectedPosition=targets.find(t=>devices.some(d=>(d.preview||[]).some(p=>p.sensor===t.sensor)))?.position||targets[0].position;
    const slider=$('forecast-target');slider.max=Math.max(1,steps.length);slider.value=selectedPosition||1;slider.disabled=!active||!steps.length;
    const target=targets.find(t=>t.position===selectedPosition),step=steps.find(s=>s.position===selectedPosition);
    slider.setAttribute('aria-valuetext',step?.suite||'Waiting for flow metadata');
    $('flow-targets').innerHTML=targets.map(t=>`<button type="button" data-position="${t.position}" aria-pressed="${t.position===selectedPosition}" ${!active?'disabled':''} style="${t.position===selectedPosition?'border:2px solid var(--accent,#5684c5)':''}">sensor${t.sensor} &middot; Test ${t.test_number}</button>`).join('');
    $('forecast-distance').textContent=target?`${target.suite} / ${target.pin} - Test ${target.test_number}`:step?`${step.suite} - No forecast model`:'Waiting for Edge flow metadata';
    const uncertainty=target&&liveTemperature?.uncertainty?.sensors?.[String(target.sensor)];
    $('temperature-confidence').textContent=uncertainty?`Offline 95th-percentile absolute error: ${uncertainty.absolute_error_p95.toFixed(3)} \u00b0C | Live forecast confidence: not calibrated`:'';
    $('temperature-confidence').title='Validation uses preceding measured inputs; this error is not a guarantee for recursive previews.';
    const rows=active&&target?devices.map(d=>{
      const p=(d.preview||[]).find(p=>p.sensor===target.sensor);
      const reason=d.actual?.[target.sensor-1]!=null?'Already measured':d.flow_position==null?'Flow position unknown':d.flow_position>=target.position?'Target already passed':'Prediction unavailable';
      return `<tr><td>${escapePreview(d.site)}</td><td>${escapePreview(d.current_suite||'Unknown')}</td><td>${p?p.suites_ahead+' suites':'\u2014'}</td><td>${p?p.value.toFixed(3)+' \u00b0C':reason}</td><td>${p?p.measured_inputs+' / '+p.total_inputs:'\u2014'}</td><td>${p?p.predicted_inputs:'\u2014'}</td><td>${p?p.imputed_inputs:'\u2014'}</td></tr>`;
    }):[];
    $('forecast-preview').innerHTML=rows.length?'<table style="width:100%"><thead><tr><th>Site</th><th>Current test suite</th><th>Distance to target</th><th>Forecast</th><th>Measured inputs</th><th>Predicted inputs</th><th>Imputed inputs</th></tr></thead><tbody>'+rows.join('')+'</tbody></table>':pausedMessage?'Preview paused until fresh data arrives':step&&!target?'No model for this test suite. Select a supported target above.':'Waiting for an active test';
  }
  $('forecast-target').oninput=e=>{selectedPosition=Number(e.target.value);renderForecast();};
  $('flow-targets').onclick=e=>{const button=e.target.closest('button[data-position]');if(button){selectedPosition=Number(button.dataset.position);renderForecast();}};
  const originalRender=render;render=function(){originalRender();renderForecast();};
  // This page follows live events only; no historical run or playback controls.
  const liveURL=new URL(location.href);liveURL.searchParams.delete('run');history.replaceState(null,'',liveURL);
  $('play').onclick=null;$('play').style.display='none';
  $('td').oninput=null;$('td').disabled=true;$('td').closest('label').style.display='none';
  wsel.disabled=true;wsel.onchange=null;
  function clearLive(message){
    liveTemperature=null;
    state.pid=null;state.step=0;liveIdentity=null;
    const empty={wafer_id:'Waiting for Edge',status:'waiting',touchdowns_done:0,devices:[],history:[],sensors:Object.fromEntries([1,2,3,4,5,6].map(k=>[k,{mu0:25,limit_hi:null}]))};
    for(const key of Object.keys(DATA))delete DATA[key];
    DATA[empty.wafer_id]=empty;state.wafer=empty.wafer_id;wsel.replaceChildren(new Option(empty.wafer_id,empty.wafer_id));setMax();render();$('status').textContent=message;
  }
  async function pollLive() {
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),5000);
    try {
      const response=await fetch('/api/temperature?live=1',{cache:'no-store',signal:controller.signal});
      const packet=await response.json();
      if(!response.ok)throw Error(packet.message||'Waiting for Edge');
      const t=packet.scene2;
      pausedMessage='';lastDisplayedAt=packet.received_at;
      liveTemperature=t;
      const identity=packet.run_id+':'+t.wafer, name=String(t.wafer||'Waiting for wafer');
      const devices=t.devices.map(v=>{
        const pred=v.pred.map((x,i)=>v.prediction_timing?.[i]==='late_request_frozen'?null:x);
        const raw=v.raw.map((x,i)=>v.prediction_timing?.[i]==='late_request_frozen'?null:x);
        const over=a=>a.map((x,i)=>x!=null&&t.limits[String(i+1)]&&(x>t.limits[String(i+1)].hi||x<t.limits[String(i+1)].lo));
        return {...v,pid:v.pid==null?'—':String(v.pid),pred,raw,forecast:[null,null,null,null,null,null],over_limit_actual:over(v.actual),over_limit_pred:over(pred)};
      });
      const batches=[...new Set(devices.filter(v=>v.completed).map(v=>v.batch))].sort((a,b)=>a-b);
      const mae=(rows,field,k)=>{const e=rows.filter(v=>v[field][k]!=null&&v.actual[k]!=null).map(v=>Math.abs(v[field][k]-v.actual[k]));return e.length?e.reduce((a,b)=>a+b,0)/e.length:null;};
      const history=batches.map(batch=>{const rows=devices.filter(v=>v.batch<=batch&&v.completed);return {mae_cum:Object.fromEntries([1,2,3,4,5,6].map(k=>[k,mae(rows,'pred',k-1)])),mae_raw_cum:Object.fromEntries([1,2,3,4,5,6].map(k=>[k,mae(rows,'raw',k-1)]))};});
      const d={wafer_id:name,status:t.ended?'done':'testing',touchdowns_done:t.batch,devices,history,sensors:Object.fromEntries([1,2,3,4,5,6].map(k=>[k,{mu0:25,limit_hi:t.limits[String(k)]?.hi}]))};
      if(identity!==liveIdentity){
        if(state.playing){clearInterval(state.playing);state.playing=null;$('play').textContent='▶ Play';}
        for(const key of Object.keys(DATA))delete DATA[key];
        wsel.replaceChildren(new Option(name,name));state.wafer=name;state.pid=null;liveIdentity=identity;
        DATA[name]=d;setMax();state.step=maxStep();
      }else{DATA[name]=d;setMax();state.step=maxStep();}
      $('td').value=state.step;render();
      $('status').textContent=name+' · '+(packet.age_seconds>10?'connection stale':t.ended?'complete':'testing');
    }catch(error){
      const message=error.name==='AbortError'?'HC connection timed out':error.message;
      if(liveIdentity){
        pausedMessage=message+' · Showing last received state ('+new Date(lastDisplayedAt*1000).toLocaleTimeString('en-US')+')';
        renderForecast();
      }else{clearLive(message);}
    }
    finally{clearTimeout(timeout);}
    setTimeout(pollLive,2000);
  }
  pollLive();
