#!/usr/bin/env python3
"""Authenticated mobile HTTP -> real local Piper WAV with signed playback."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

from studio_web import Handler, Studio


@unittest.skipUnless(os.environ.get("UGC_TEST_PIPER_MODEL"),"Real Piper model not installed")
class RealMobileVoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace=tempfile.TemporaryDirectory(prefix="ugc-v11-android-")
        cls.server=Studio(("127.0.0.1",0),Handler,Path(cls.workspace.name),
                          "local-test-token-"+"X"*40,
                          voice_model=Path(os.environ["UGC_TEST_PIPER_MODEL"]),
                          voice_license_ref="https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD")
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.pid=None

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.workspace.cleanup()

    def call(self,path,method="GET",payload=None,auth=True,extra_headers=None):
        headers=dict(extra_headers or {})
        if auth:
            headers["Authorization"]="Bearer "+self.server.token
        if isinstance(payload,dict):
            payload=json.dumps(payload,ensure_ascii=False).encode()
            headers["Content-Type"]="application/json"
        request=Request(self.url+path,data=payload,method=method,headers=headers)
        try:
            with urlopen(request,timeout=30) as response:
                raw=response.read()
                return response.status,json.loads(raw) if "application/json" in response.headers.get("Content-Type","") else raw
        except HTTPError as exc:
            raw=exc.read()
            try:raw=json.loads(raw)
            except (ValueError,UnicodeDecodeError):pass
            return exc.code,raw

    def test_01_auth_and_enabled(self):
        self.assertEqual(self.call("/api/health",auth=False)[0],401)
        code,health=self.call("/api/health")
        self.assertEqual(code,200)
        self.assertTrue(health["voice_generation_enabled"])
        self.assertEqual(health["voice_language"],"fr_FR")
        code,res=self.call("/api/projects",method="POST",payload={"name":"V11 vraie voix locale"})
        self.assertEqual(code,201,res)
        self.__class__.pid=res["id"]

    def test_02_required_voice_rights_and_input(self):
        endpoint=f"/api/projects/{self.pid}/voice"
        self.assertEqual(self.call(endpoint,method="POST",payload={"text":"Bonjour","confirm_voice_rights":False})[0],400)
        self.assertEqual(self.call(endpoint,method="POST",payload={"text":"<script>x</script>","confirm_voice_rights":True})[0],400)
        self.assertEqual(self.call(endpoint,method="POST",payload={"text":"Bonjour","confirm_voice_rights":True},auth=False)[0],401)

    def test_03_real_generate_signed_wav_and_recovery(self):
        endpoint=f"/api/projects/{self.pid}/voice"
        payload={"text":"Bonjour, ceci est un test français depuis mon téléphone.","confirm_voice_rights":True}
        code,data=self.call(endpoint,method="POST",payload=payload)
        self.assertEqual(code,202,data)
        self.assertEqual(data["kind"],"voice")
        self.assertEqual(self.call(endpoint,method="POST",payload=payload)[0],409)
        until=time.monotonic()+75
        current={}
        while time.monotonic()<until:
            status,current=self.call(f"/api/projects/{self.pid}")
            self.assertEqual(status,200,current)
            if current["job"]["status"] in {"completed","failed"}:
                break
            time.sleep(.25)
        self.assertEqual(current["job"]["status"],"completed",current["job"])
        clips=[item for item in current["media"] if item.get("generated_by")=="piper_local"]
        self.assertEqual(len(clips),1)
        self.assertEqual(clips[0]["type"],"audio")
        self.assertTrue(clips[0]["file"].endswith(".wav"))
        self.assertGreater(clips[0]["bytes"],1000)
        self.assertEqual(self.call(clips[0]["url"],auth=False)[0],200)
        code,audio=self.call(clips[0]["url"],auth=False,extra_headers={"Range":"bytes=0-63"})
        self.assertEqual((code,len(audio)),(206,64))
        self.assertEqual(audio[:4],b"RIFF")
        wav=Path(self.workspace.name)/self.pid/clips[0]["file"]
        report=wav.with_suffix(".voice.json")
        self.assertTrue(report.is_file())
        meta=json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(meta["status"],"VOICE_GENERATED_NOT_LIPSYNCED")
        self.assertFalse(meta["human_lip_sync_proven"])
        # A completed voice job frees the render queue slot.
        self.assertEqual(self.call(endpoint,method="POST",payload=payload)[0],202)


if __name__=="__main__":
    unittest.main(verbosity=2)
