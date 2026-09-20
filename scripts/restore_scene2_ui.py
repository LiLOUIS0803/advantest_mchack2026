"""Use the original Scene 2 HTML/CSS unchanged; adapt received JSON only."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    source=(ROOT/'scene2/web/wafer_map_template.html').read_text(encoding='utf-8')
    empty={'wafer_id':'Waiting for Edge','status':'waiting','touchdowns_done':0,
           'devices':[],'history':[],'sensors':{str(k):{'mu0':25,'limit_hi':None} for k in range(1,7)}}
    html=source.replace('__DATA__',json.dumps({'Waiting for Edge':empty}))
    # Navigation is the only addition to the original Scene 2 layout.
    navigation='''<style id="task-navigation-style">
    .task-nav{display:flex;gap:20px;align-items:center;flex-wrap:wrap;padding:14px 16px;border-bottom:1px solid var(--border);background:var(--surface)}
    .task-nav a{color:var(--text-2);text-decoration:none}.task-nav a.active{color:var(--s1);border-bottom:2px solid var(--s1)}
    .task-nav label{display:flex;gap:8px;align-items:center}.task-nav .source-status{margin-left:auto;color:var(--text-2);font-size:13px}
    </style><script src="/task-nav.js" defer></script>'''
    html=html.replace('</head>',navigation+'\n</head>')
    # Use real batch numbers, not the original static-demo assumption of four dies.
    html=html.replace('const td = Math.floor(idx / 4) + 1;', 'const td = v.batch || Math.floor(idx / 4) + 1;')
    html=html.replace("$('tdgrid').innerHTML = html;", "$('tdgrid').style.gridTemplateColumns = `90px repeat(${Math.max(1,rows.length)}, minmax(100px,1fr))`; $('tdgrid').style.overflowX='auto'; $('tdgrid').innerHTML = html;")
    # A live snapshot can contain measurements for only some sites of a batch.
    html=html.replace("v.actual[i] == null ? 'pd' : 'ms'", "v.actual[i] == null ? (v.pred[i] == null ? 'none' : 'pd') : 'ms'")
    hook=(ROOT/'realtime/web/temperature-live.js').read_text(encoding='utf-8')
    html=html.replace('  render();\n})();', '  render();\n'+hook+'\n})();')
    # Keep original PID values, including non-numeric identifiers.
    html=html.replace('+c.dataset.pid', 'c.dataset.pid').replace('+el.dataset.pid','el.dataset.pid')
    (ROOT/'realtime/web/temperature.html').write_text(html,encoding='utf-8')

if __name__=='__main__':main()
