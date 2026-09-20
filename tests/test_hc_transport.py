import gzip,json,socket,tempfile,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from unittest.mock import patch
from realtime.hc_server import make_server,Store


class TransportTests(unittest.TestCase):
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
        self.assertEqual(original.split('<script id="data"')[0],deployed.split('<script id="data"')[0])
