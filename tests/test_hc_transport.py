import gzip,json,re,socket,tempfile,threading,time,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from realtime.hc_server import make_server,Store


class TransportTests(unittest.TestCase):
    def test_live_temperature_rejects_stale_history_but_returns_fresh_final_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'hc.db';server=make_server('127.0.0.1',0,path,'x'*32)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            store=Store(path);now=time.time()
            packet={'version':1,'kind':'state','run_id':'r','seq':1,'started_at':now,
                    'sent_at':now,'last_event_at':now,'scene1':{},'scene2':{'wafer':'4','ended':False},
                    'reference':{},'columns':[],'series':[]}
            base='http://127.0.0.1:%d/api/temperature?live=1'%server.server_port
            def rejected(url):
                with self.assertRaises(HTTPError) as ctx:urlopen(url)
                code=ctx.exception.code;ctx.exception.close();return code
            try:
                store.ingest(packet)
                with urlopen(base) as response:self.assertEqual(response.status,200)
                self.assertEqual(rejected(base+'&run=r'),400)
                self.assertEqual(rejected(base+'&retain=1&run=r'),400)
                packet.update(seq=2,sent_at=now-100);store.ingest(packet)
                self.assertEqual(rejected(base),503)
                with urlopen(base+'&retain=1') as response:
                    retained=json.load(response)
                    self.assertEqual(retained['stream_status'],'stale')
                    self.assertEqual(retained['run_id'],'r')
                packet.update(seq=3,sent_at=now,last_event_at=now-100);store.ingest(packet)
                self.assertEqual(rejected(base),503)
                with urlopen(base+'&retain=1') as response:self.assertEqual(json.load(response)['stream_status'],'idle')
                packet.update(seq=4,last_event_at=now);packet['scene2']['ended']=True;store.ingest(packet)
                with urlopen(base) as response:self.assertTrue(json.load(response)['scene2']['ended'])
                packet.update(seq=5,last_event_at=now-100,sent_at=now-100);store.ingest(packet)
                with urlopen(base+'&retain=1') as response:self.assertTrue(json.load(response)['scene2']['ended'])
                newer=dict(packet,run_id='new',seq=1,started_at=now+1,sent_at=time.time(),last_event_at=time.time(),scene2={'wafer':'5','ended':False})
                store.ingest(newer)
                with urlopen(base+'&retain=1') as response:
                    current=json.load(response)
                    self.assertEqual(current['run_id'],'new')
                    self.assertEqual(current['stream_status'],'live')
            finally:server.shutdown();server.server_close();thread.join()

    def test_truncated_upload_not_committed_then_large_gzip_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'hc.db';token='x'*32
            server=make_server('127.0.0.1',0,path,token)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with patch.object(server,'handle_error') as error:
                    with socket.create_connection(server.server_address) as client:
                        client.sendall(('POST /api/ingest HTTP/1.0\r\nAuthorization: Bearer '+token+'\r\nContent-Length: 100\r\n\r\n{"kind":').encode())
                        client.shutdown(socket.SHUT_WR)
                        self.assertIn(b'400',client.recv(4096))
                    self.assertIsNone(Store(path).state())
                    packet={'version':1,'kind':'state','run_id':'r','seq':1,'started_at':1,'scene1':{'blob':'x'*20_000_000},'scene2':{},'reference':{},'columns':[],'series':[]}
                    body=gzip.compress(json.dumps(packet).encode())
                    request=Request('http://127.0.0.1:%d/api/ingest'%server.server_port,data=body,headers={'Authorization':'Bearer '+token,'Content-Encoding':'gzip'})
                    with urlopen(request,timeout=10) as response:self.assertEqual(response.status,200)
                    self.assertEqual(len(Store(path).state()['scene1']['blob']),20_000_000)
                    error.assert_not_called()
            finally:server.shutdown();server.server_close();thread.join()

    def test_scene2_original_layout_and_styles_preserved(self):
        original=Path('scene2/web/wafer_map_template.html').read_text(encoding='utf-8')
        deployed=Path('realtime/web/temperature.html').read_text(encoding='utf-8')
        self.assertIn('<script src="/task-nav.js" defer></script>',deployed)
        deployed=re.sub(r'<style id="task-navigation-style">.*?</style><script src="/task-nav.js" defer></script>\n','',deployed,flags=re.S)
        self.assertEqual(original.split('<script id="data"')[0],deployed.split('<script id="data"')[0])
