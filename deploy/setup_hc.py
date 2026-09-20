"""Run on HC after upload. Creates private shared token and Edge descriptor."""
import argparse,json,os,secrets
from pathlib import Path
from urllib.parse import urlparse

def main():
    p=argparse.ArgumentParser();p.add_argument('--hc-url',required=True);p.add_argument('--image',default='grp4/py-app:tasks-v6');a=p.parse_args()
    url=a.hc_url.rstrip('/');parsed=urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.hostname in ('localhost','127.0.0.1','0.0.0.0'):
        p.error('Use the HC address reachable from Edge, not localhost or the Edge IP')
    root=Path(__file__).resolve().parents[1];tokenfile=root/'hc-token.txt'
    if tokenfile.exists():token=tokenfile.read_text().strip()
    else:
        token=secrets.token_urlsafe(32)
        fd=os.open(tokenfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(token+'\n')
    descriptor=json.loads((root/'app_descriptor.json').read_text())
    container=descriptor['edge']['containers'][0];container['image']=a.image
    container['environment'].update(HC_INGEST_URL=url+'/api/ingest',HC_SHARED_TOKEN=token)
    output=root/'app_descriptor.hc.json'
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(descriptor,f,indent=2)
    print('Created hc-token.txt and app_descriptor.hc.json (contains private shared token).')
    print('Copy app_descriptor.hc.json into the existing SmarTest folder as app_descriptor.json.')
    print('Start HC: python3 hc/start.py --token-file hc-token.txt --data hc-reports.sqlite3')
if __name__=='__main__':main()
