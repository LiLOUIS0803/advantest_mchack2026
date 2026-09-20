  // Data adapter only: original Scene 2 layout, CSS and controls are retained.
  let liveIdentity=null;
  let liveTemperature=null;
  const previewPanel=document.createElement('section');previewPanel.className='card';
  previewPanel.style.cssText='margin:16px;overflow-x:auto';
  previewPanel.innerHTML='<h2>Confidence & forecast preview</h2><div id="temperature-confidence"></div><label style="display:flex;align-items:center;gap:12px;margin:14px 0">Forecast horizon <input id="forecast-horizon" type="range" min="1" max="6" value="1"><span id="forecast-distance"></span></label><div id="forecast-preview"></div><p class="muted">Preview only · Uses current measurements · Not sent to tester</p>';
  document.querySelector('main').before(previewPanel);
  const escapePreview=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function renderForecast(){
    const horizon=Number($('forecast-horizon').value);
    $('forecast-distance').textContent='Next '+horizon+' sensor'+(horizon===1?'':'s');
    const uncertainty=liveTemperature?.uncertainty?.sensors?.[String(state.sensor)];
    $('temperature-confidence').textContent=uncertainty
      ? `sensor${state.sensor} · Offline 95th-percentile absolute error: ${uncertainty.absolute_error_p95.toFixed(3)} °C · Live confidence not calibrated`
      : 'Confidence unavailable until Edge provides validation statistics';
    $('temperature-confidence').title='Out-of-wafer raw model errors with preceding measurements available. This is not a 95% guarantee for live or multi-step forecasts.';
    const devices=(liveTemperature?.devices||[]).filter(d=>!d.completed);
    $('forecast-horizon').disabled=!devices.some(d=>d.preview?.length);
    const rows=devices.flatMap(d=>(d.preview||[]).filter(p=>p.steps_ahead<=horizon).map(p=>
      `<tr><td>${escapePreview(d.site)}</td><td>sensor${p.sensor}</td><td>${p.value.toFixed(3)} °C</td><td>${p.measured_inputs} / ${p.total_inputs}</td><td>${p.predicted_inputs}</td><td>${p.imputed_inputs}</td><td>Not calibrated</td></tr>`));
    $('forecast-preview').innerHTML=rows.length?'<table style="width:100%"><thead><tr><th>Site</th><th>Target</th><th>Preview</th><th>Measured inputs</th><th>Predicted inputs</th><th>Imputed inputs</th><th>Confidence</th></tr></thead><tbody>'+rows.join('')+'</tbody></table>':'Waiting for an active die with unmeasured sensors';
  }
  $('forecast-horizon').oninput=renderForecast;
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
    }catch(error){clearLive(error.name==='AbortError'?'HC connection timed out':error.message);}
    finally{clearTimeout(timeout);}
    setTimeout(pollLive,2000);
  }
  pollLive();
