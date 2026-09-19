"""ACS Python 3.10 entrypoint for the integrated wafer monitor."""
import json
import logging
import os
from pathlib import Path
import signal
import sys
import threading
from oneapi import AppInfo, Interface
from edge_monitor import EdgeMonitor
from realtime.server import Session
from realtime.hc_push import PushClient


def main():
    logging.basicConfig(level=os.environ.get('ACS_LOG_LEVEL','INFO'),
                        format='%(asctime)s %(levelname)s %(message)s')
    if sys.version_info[:2]!=(3,10):
        raise RuntimeError('The supplied native ONEAPI libraries require Python 3.10')
    config=json.loads(Path(os.environ.get('ADAPTER_CONFIG','adapter_config.json')).read_text())
    session=Session();session.engine.mode='live'
    push_url=os.environ.get('HC_INGEST_URL','')
    token_path=Path(os.environ.get('HC_TOKEN_FILE','hc-token.txt'))
    if not push_url:raise RuntimeError('Set HC_INGEST_URL to http://HC_IP:8770/api/ingest')
    token=os.environ.get('HC_SHARED_TOKEN') or token_path.read_text().strip()
    if len(token)<24:raise RuntimeError('HC token must have at least 24 characters')
    push=PushClient(session,push_url,token,os.environ.get('REPORT_DIR','reports'))
    monitor=EdgeMonitor(session,config,push.changed)
    push.start(monitor.bridge)
    Interface.registerMonitor(monitor)
    # HTTP is hosted on HC. Edge only makes outbound JSON requests.
    info=AppInfo();info.name='wafer-watch';info.vendor='hackathon';info.version='1.0.0'
    result=Interface.connect(info,True,True)
    if result!=0:raise RuntimeError('ONEAPI connection request failed: '+str(result))
    logging.info('ONEAPI connection requested; wait for real events to confirm streaming')
    def stop(*args):
        Interface.disconnect();sys.exit(0)
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    while True:signal.pause()


if __name__=='__main__':main()
