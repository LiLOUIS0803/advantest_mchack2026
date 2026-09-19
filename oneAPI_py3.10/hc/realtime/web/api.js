/* The frontend communicates only through JSON, never through CSV/model files. */
window.dashboardAPI = {
  async request(path, options = {}) {
    const run = new URLSearchParams(location.search).get('run');
    if (run) path += (path.includes('?') ? '&' : '?') + 'run=' + encodeURIComponent(run);
    const response = await fetch(path, {...options, cache: 'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  },
  get(path) { return this.request(path); },
  post(path, body) {
    return this.request(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  }
};
