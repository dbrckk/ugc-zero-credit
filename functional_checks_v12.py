#!/usr/bin/env python3
"""V12 acceptance: real French + English Piper synthesis and authenticated HTTP.

Only local ONNX weights are loaded. No paid API and no mock audio generation.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import wave
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from studio_web import Handler, Studio
from voice_catalog import configure_voices, pick_voice, available_languages

FR_LICENSE = "https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD"
EN_LICENSE = "https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD"
FR_MODEL = os.getenv("UGC_TEST_PIPER_MODEL")
EN_MODEL = os.getenv("UGC_TEST_PIPER_MODEL_EN")
ENABLED = bool(FR_MODEL and EN_MODEL)


@unittest.skipUnless(ENABLED, "Install two ONNX Piper models and set UGC_TEST_PIPER_MODEL(_EN)")
class BilingualVoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fr=Path(FR_MODEL)
        cls.en=Path(EN_MODEL)
        cls.tmp=tempfile.TemporaryDirectory(prefix="ugc-v12-bilingual-")
        cls.server=Studio(("127.0.0.1",0),Handler,Path(cls.tmp.name),
                          "bilingual-local-secret-"+"B"*40,
                          voice_model_fr=cls.fr, voice_license_ref_fr=FR_LICENSE,
                          voice_model_en=cls.en, voice_license_ref_en=EN_LICENSE)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.project=None

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=7)
        cls.tmp.cleanup()

    def request(self,path,method="GET",data=None,auth=True,headers=None):
        header=dict(headers or {})
        if auth:
            header["Authorization"]="Bearer "+self.server.token
        if isinstance(data,dict):
            header["Content-Type"]="application/json"
            data=json.dumps(data,ensure_ascii=False).encode()
        req=Request(self.base+path,data=data,headers=header,method=method)
        try:
            with urlopen(req,timeout=60) as res:
                content=res.read()
                return res.status,json.loads(content) if "application/json" in res.headers.get("Content-Type","") else content
        except HTTPError as err:
            content=err.read()
            try:content=json.loads(content)
            except (ValueError,UnicodeDecodeError):pass
            return err.code,content

    def wait_job(self,project_id):
        stop=time.monotonic()+100
        while time.monotonic()<stop:
            code,details=self.request("/api/projects/"+project_id)
            self.assertEqual(code,200,details)
            if details["job"]["status"] in {"completed","failed"}:
                return details
            time.sleep(.2)
        self.fail("Time limit exceeded waiting for real Piper synthesis")

    def test_01_voice_registry_validated_at_startup(self):
        catalog=configure_voices(french_model=self.fr,french_license=FR_LICENSE,
                                 english_model=self.en,english_license=EN_LICENSE)
        self.assertEqual(available_languages(catalog),["fr","en"])
        self.assertEqual(pick_voice(catalog,"fr")[1]["locale"],"fr_FR")
        self.assertEqual(pick_voice(catalog,"en")[1]["locale"],"en_US")
        with self.assertRaises(ValueError):
            configure_voices(french_model=self.en,french_license=FR_LICENSE)
        with self.assertRaises(ValueError):
            configure_voices(english_model=self.fr,english_license=EN_LICENSE)
        with self.assertRaises(ValueError):
            configure_voices(french_model=self.fr,french_license=FR_LICENSE,
                             legacy_model=self.fr,legacy_license=FR_LICENSE)
        with self.assertRaises(ValueError):
            pick_voice(catalog,None)
        with self.assertRaises(ValueError):
            pick_voice(catalog,"de")
        with self.assertRaises(ValueError):
            pick_voice(catalog,{"language":"fr"})

    def test_02_single_voice_remains_backward_compatible(self):
        catalog=configure_voices(legacy_model=self.fr,legacy_license=FR_LICENSE)
        self.assertEqual(available_languages(catalog),["fr"])
        self.assertEqual(pick_voice(catalog,None)[0],"fr")
        with self.assertRaises(LookupError):
            pick_voice(catalog,"en")
        with self.assertRaises(ValueError):
            configure_voices(french_license=FR_LICENSE)
        self.assertEqual(available_languages(configure_voices()),[])

    def test_03_authenticated_health_and_project(self):
        self.assertEqual(self.request("/api/health",auth=False)[0],401)
        status,health=self.request("/api/health")
        self.assertEqual(status,200)
        self.assertEqual(health["voice_languages"],["fr","en"])
        self.assertTrue(health["voice_generation_enabled"])
        self.assertEqual(health["voice_language"],"")
        self.assertFalse(health["paid_generators"])
        status,result=self.request("/api/projects",method="POST",data={"name":"Sélection bilingue"})
        self.assertEqual(status,201,result)
        self.__class__.project=result["id"]

    def test_04_invalid_language_and_unauthorized_rejected_before_render(self):
        url=f"/api/projects/{self.project}/voice"
        payload={"text":"Une narration française.","confirm_voice_rights":True}
        self.assertEqual(self.request(url,method="POST",data=payload)[0],400,
                         "Two voices require an explicit language")
        for code in ("de","FR","en_US","../en",123,{},True,""):
            with self.subTest(code=code):
                self.assertEqual(self.request(url,method="POST",data={**payload,"language":code})[0],400)
        self.assertEqual(self.request(url,method="POST",data={**payload,"language":"fr",
                                                            "confirm_voice_rights":False})[0],400)
        self.assertEqual(self.request(url,method="POST",data={**payload,"language":"fr"},auth=False)[0],401)
        status,detail=self.request("/api/projects/"+self.project)
        self.assertEqual(status,200)
        self.assertEqual(detail["job"]["status"],"idle")
        self.assertEqual(detail["media"],[])

    def _generate(self,language,text):
        url=f"/api/projects/{self.project}/voice"
        data={"language":language,"text":text,"confirm_voice_rights":True}
        code,response=self.request(url,method="POST",data=data)
        self.assertEqual(code,202,response)
        self.assertEqual(response["language"],language)
        self.assertEqual(response["kind"],"voice")
        self.assertEqual(self.request(url,method="POST",data=data)[0],409)
        completed=self.wait_job(self.project)
        self.assertEqual(completed["job"]["status"],"completed",completed["job"])
        self.assertEqual(completed["job"]["language"],language)
        media=[item for item in completed["media"] if item.get("language")==language]
        self.assertEqual(len(media),1)
        item=media[0]
        self.assertEqual(item["type"],"audio")
        self.assertEqual(item["voice_locale"],"fr_FR" if language=="fr" else "en_US")
        self.assertTrue(item["file"].split("/")[-1].startswith("narration_"+language+"_"))
        self.assertGreater(item["bytes"],2000)
        wav=Path(self.tmp.name)/self.project/item["file"]
        manifest=json.loads(wav.with_suffix(".voice.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["language"],item["voice_locale"])
        self.assertEqual(manifest["wav_sha256"],item["voice_sha256"])
        self.assertFalse(manifest["human_lip_sync_proven"])
        self.assertTrue(manifest["no_paid_api"])
        with wave.open(str(wav),"rb") as sound:
            self.assertGreater(sound.getnframes(),8000)
            self.assertEqual(sound.getnchannels(),1)
        self.assertEqual(self.request(item["url"],auth=False)[0],200)
        code,head=self.request(item["url"],auth=False,headers={"Range":"bytes=0-63"})
        self.assertEqual((code,len(head)),(206,64))
        self.assertEqual(head[:4],b"RIFF")
        return item

    def test_05_real_french_speech_and_signed_audio(self):
        self.__class__.fr_item=self._generate("fr",
            "Bonjour, cette narration française est produite localement sans service payant.")

    def test_06_real_english_speech_distinct_model_and_audio(self):
        english=self._generate("en",
            "Hello, this English narration is generated entirely on your own computer.")
        self.assertNotEqual(english["voice_sha256"],self.fr_item["voice_sha256"])
        self.assertNotEqual(english["file"],self.fr_item["file"])
        self.assertEqual(self.request("/api/projects/"+self.project)[1]["media"][0]["language"],"fr")

    def test_07_ui_displays_both_languages_without_external_services(self):
        code,page=self.request("/",auth=False)
        self.assertEqual(code,200)
        text=page.decode("utf-8")
        self.assertIn('id="voiceLanguage"',text)
        self.assertIn('value="fr"',text)
        self.assertIn('value="en"',text)
        code,js=self.request("/studio.js",auth=False)
        self.assertEqual(code,200)
        self.assertIn("voiceLanguages",js.decode())
        self.assertIn("confirm_voice_rights",js.decode())


if __name__=="__main__":
    unittest.main(verbosity=2)
