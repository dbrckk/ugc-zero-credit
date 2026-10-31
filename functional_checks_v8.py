#!/usr/bin/env python3
"""Functional HTTP/Android workflow smoke test (offline; no credentials/paid services)."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unittest

from studio_web import Handler, Studio

ROOT=Path(__file__).resolve().parent


class WebStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix='ugc-v8-tests-')
        cls.server = Studio(('127.0.0.1',0), Handler, Path(cls.workspace.name), 'v8-local-secret-'+'x'*40)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_address[1])
        cls.pid=None

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=8)
        cls.workspace.cleanup()

    def request(self,path,method='GET',data=None,auth=True,headers=None):
        hdr=dict(headers or {})
        if auth:hdr['Authorization']='Bearer '+self.server.token
        if data is not None and isinstance(data,(dict,list)):
            data=json.dumps(data,ensure_ascii=False).encode('utf-8');hdr['Content-Type']='application/json'
        req=Request(self.base+path,data=data,headers=hdr,method=method)
        try:
            with urlopen(req,timeout=45) as res:
                body=res.read()
                return res.status,json.loads(body) if 'application/json' in res.headers.get('Content-Type','') else body
        except HTTPError as e:
            body=e.read()
            try:body=json.loads(body)
            except:pass
            return e.code,body

    def test_01_auth_and_bad_origin(self):
        self.assertEqual(self.request('/api/health',auth=False)[0],401)
        self.assertEqual(self.request('/api/health')[0],200)
        self.assertEqual(self.request('/api/health',headers={'Origin':'https://malicious.example'})[0],403)
        self.assertEqual(self.request('/studio.js',auth=False)[0],200)

    def test_02_create_and_upload(self):
        code,data=self.request('/api/projects',method='POST',data={'name':'UGC V8 test local'})
        self.assertEqual(code,201,data);self.__class__.pid=data['id']
        self.assertRegex(self.pid,r'^[a-f0-9]{16}$')
        self.assertEqual(self.request('/api/projects/'+self.pid)[0],200)
        self.assertEqual(self.request('/api/projects/'+self.pid+'/media?filename=..%2Foutside.mp4',method='POST',data=b'evil')[0],400)
        samples=[('presentation_demo.mp4','video'),('produit.png','image'),('music_original.wav','audio')]
        for name,kind in samples:
            p=ROOT/'examples'/'demo_media'/name
            self.assertTrue(p.is_file(),p)
            code,data=self.request('/api/projects/'+self.pid+'/media?'+urlencode({'filename':name}),method='POST',data=p.read_bytes(),headers={'Content-Type':'application/octet-stream'})
            self.assertEqual(code,201,data);self.assertEqual(data['media']['type'],kind)
        srt=b'1\n00:00:00,120 --> 00:00:01,000\nBonjour tout le monde !\n\n2\n00:00:01,200 --> 00:00:03,400\nUn produit fictif de demonstration.\n'
        code,data=self.request('/api/projects/'+self.pid+'/media?filename=voix.srt',method='POST',data=srt,headers={'Content-Type':'text/plain'})
        self.assertEqual(code,201,data)
        code,data=self.request('/api/projects/'+self.pid+'/media?filename=voix.srt',method='POST',data=srt,headers={'Content-Type':'text/plain'})
        self.assertEqual(code,201,data);self.assertNotEqual(data['media']['file'],'media/voix.srt')
        self.assertEqual(self.request('/api/projects/'+self.pid+'/media?filename=corrupt.srt',method='POST',data=b'fake srt')[0],400)

    def payload(self,valid=True):
        return {'product':{'name':'PRODUIT FICTIF TEST', 'claims_verified':valid,'product_reference':'media/produit.png','evidence_urls':[]},
                'talking_clips':[{'file':'media/presentation_demo.mp4','source_in':0,'duration':4,'rights':'owned','smart_crop':'off'}],
                'overlays':[{'file':'media/produit.png','start':1.2,'duration':.7,'rights':'owned','motion':'push_in','fade':.08}],
                'music':{'file':'media/music_original.wav','rights':'owned','volume':.06},
                'srt_assignments':[{'clip':0,'file':'media/voix.srt','timebase':'clip'}]}

    def test_03_validation_and_srt(self):
        pid=self.pid
        self.assertEqual(self.request('/api/projects/'+pid+'/configure',method='POST',data=self.payload(valid=False))[0],400)
        code,data=self.request('/api/projects/'+pid+'/configure',method='POST',data=self.payload(valid=True))
        self.assertEqual(code,200,data);self.assertEqual(data['captions'],2)
        self.assertEqual(data['config']['caption_mode'],'segments')
        self.assertFalse(data['config']['caption_origins'][0]['word_level_alignment'])
        self.assertEqual(self.request('/api/projects/'+pid+'/check',method='POST',data={})[0],200)
        code,details=self.request('/api/projects/'+pid)
        self.assertEqual(code,200);self.assertEqual(details['draft']['srt_assignments'][0]['file'],'media/voix.srt')
        signed=next(m for m in details['media'] if m['type']=='image')['url']
        self.assertEqual(self.request(signed,auth=False)[0],200)
        self.assertEqual(self.request(signed.split('?')[0]+'?expires=1&sig='+'a'*64,auth=False)[0],401)
        self.assertEqual(self.request('/api/projects/'+pid+'/media/%2e%2e',auth=False)[0],401)

    def test_04_real_render_and_range(self):
        pid=self.pid
        code,data=self.request('/api/projects/'+pid+'/render',method='POST',data={'preview':True})
        self.assertEqual(code,202,data)
        self.assertEqual(self.request('/api/projects/'+pid+'/render',method='POST',data={'preview':True})[0],409)
        for _ in range(110):
            _,details=self.request('/api/projects/'+pid)
            if details['job']['status'] in {'completed','failed'}:break
            time.sleep(.5)
        self.assertEqual(details['job']['status'],'completed',details['job'])
        output=next(x for x in details['outputs'] if x['name']=='preview.mp4')
        self.assertEqual(self.request(output['url'],auth=False)[0],200)
        url=output['url']
        status,payload=self.request(url,auth=False,headers={'Range':'bytes=0-127'})
        self.assertEqual(status,206);self.assertEqual(len(payload),128)
        status,payload=self.request(url,auth=False,headers={'Range':'bytes=999999999-'})
        self.assertEqual(status,416)
        status,report=self.request(next(x['url'] for x in details['outputs'] if x['name']=='preview.report.json'),auth=False)
        self.assertEqual(status,200);self.assertEqual(report['caption_mode'],'segments')
        self.assertTrue(report['sync_audio_gate']['native_audio_preserved'])
        info=subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(Path(self.workspace.name)/pid/'renders/preview.mp4')])
        streams=json.loads(info)['streams']
        self.assertEqual((next(x['width'] for x in streams if x['codec_type']=='video'),next(x['height'] for x in streams if x['codec_type']=='video')),(360,640))
        self.assertTrue(any(x['codec_type']=='audio' for x in streams))


if __name__=='__main__':
    unittest.main(verbosity=2)
