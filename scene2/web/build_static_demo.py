#!/usr/bin/env python3
"""
把 report_demo/wafer_*.json 內嵌進 wafer_map_template.html，產生可直接開的靜態 demo。
    python web/build_static_demo.py --report report_demo --out web/wafer_map_demo.html
正式版：同一份 template，把 __DATA__ 換成從 /api/state 取得的資料即可。
"""
import argparse, glob, json, os

ap = argparse.ArgumentParser()
ap.add_argument("--report", default="report_demo")
ap.add_argument("--out", default="web/wafer_map_demo.html")
ap.add_argument("--template", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "wafer_map_template.html"))
a = ap.parse_args()

data = {}
for p in sorted(glob.glob(os.path.join(a.report, "wafer_W*.json"))):
    d = json.load(open(p))
    # 內嵌用：把浮點數截到 4 位，縮小檔案
    def rnd(o):
        if isinstance(o, float): return round(o, 4)
        if isinstance(o, list): return [rnd(x) for x in o]
        if isinstance(o, dict): return {k: rnd(v) for k, v in o.items()}
        return o
    data[d["wafer_id"]] = rnd(d)
html = open(a.template, encoding="utf-8").read().replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
open(a.out, "w", encoding="utf-8").write(html)
print("寫入", a.out, f"({os.path.getsize(a.out)//1024} KB, wafers: {list(data)})")
