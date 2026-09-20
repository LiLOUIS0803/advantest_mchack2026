(() => {
  const selected = new URLSearchParams(location.search).get('run');
  const nav = document.createElement('nav');
  nav.className = 'task-nav';
  nav.setAttribute('aria-label', 'Task navigation');
  nav.innerHTML = '<a href="/">Test monitoring</a><a href="/anomaly">Anomaly detection</a><a href="/temperature">Temperature prediction</a><label>Source <select id="hc-source"></select></label><span class="source-status" id="hc-status"></span>';
  for (const link of nav.querySelectorAll('a')) {
    if (link.pathname === location.pathname) {
      link.classList.add('active');link.setAttribute('aria-current', 'page');
    }
    if (selected && link.pathname !== '/') link.search = '?run=' + encodeURIComponent(selected);
  }
  document.body.prepend(nav);
  const select = document.getElementById('hc-source'), statusLabel = document.getElementById('hc-status');
  select.onchange = e => { location.search = e.target.value ? '?run=' + encodeURIComponent(e.target.value) : ''; };
  async function status() {
    try {
      const response = await fetch('/api/streams', {cache: 'no-store'});
      if (!response.ok) throw Error('Source list unavailable');
      const streams = await response.json();
      select.replaceChildren(new Option('Latest stream', ''), ...streams.streams.map(s =>
        new Option(s.tester + ' / ' + new Date(s.received_at * 1000).toLocaleString('en-US'), s.run_id)));
      if (selected && !streams.streams.some(s => s.run_id === selected)) select.add(new Option('Selected run unavailable', selected));
      select.value = selected || '';
      const r = await fetch('/api/source' + (selected ? '?run=' + encodeURIComponent(selected) : ''), {cache: 'no-store'});
      if (!r.ok) { statusLabel.textContent = 'Waiting for Edge';return; }
      const p = await r.json();
      statusLabel.textContent = p.age_seconds > 10
        ? `Stale / ${Math.floor(p.age_seconds)}s since last update`
        : `Connected / ${p.tester}`;
      statusLabel.title = p.last_event_at ? 'Last test event: ' + new Date(p.last_event_at * 1000).toLocaleString('en-US') : 'No test event received';
    } catch (e) { statusLabel.textContent = 'HC connection unavailable'; }
    setTimeout(status, 1500);
  }
  status();
})();
