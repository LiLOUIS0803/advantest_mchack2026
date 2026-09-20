  // Data adapter only: original Scene 2 layout, CSS and controls are retained.
  let liveIdentity=null;
  async function pollLive() {
    try {
      const query=new URLSearchParams(location.search).get('run');
      const response=await fetch('/api/temperature'+(query?'?run='+encodeURIComponent(query):''));
      if(!response.ok)throw Error('Waiting for Edge');
      const packet=await response.json(), t=packet.scene2;
      const identity=packet.run_id+':'+t.wafer, name=String(t.wafer||'Waiting for wafer');
      const follow=!state.playing && state.step===maxStep();
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
      }else{DATA[name]=d;setMax();if(follow)state.step=maxStep();}
      $('td').value=state.step;render();
      $('status').textContent=name+' · '+(packet.age_seconds>10?'connection stale':t.ended?'complete':'testing');
    }catch(error){$('status').textContent=error.message;}
    setTimeout(pollLive,2000);
  }
  pollLive();
