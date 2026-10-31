#!/usr/bin/env python3
"""Real authenticated Piper -> photo uploads -> FFmpeg preview and Full-HD."""
from __future__ import annotations
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import zlib
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from studio_web import Handler, Studio
from narrated_short import inspect_narration, DISCLOSURE, layout_title

def png(rgb, w=320, h=400):
    raw = b"".join(b"\0" + bytes(rgb)*w for _ in range(h))
    def ch(t, payload):
        return struct.pack(">I", len(payload))+t+payload+struct.pack(">I", zlib.crc32(t+payload))
    return b"\x89PNG\r\n\x1a\n"+ch(b"IHDR", struct.pack(">IIBBBBB",w,h,8,2,0,0,0))+ch(b"IDAT",zlib.compress(raw,9))+ch(b"IEND",b"")

@unittest.skipUnless(os.getenv("UGC_TEST_PIPER_MODEL_EN"), "Requires installed English Piper ONNX model")
class V14RealEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ugc-v14-http-")
        cls.root=Path(cls.tmp.name)
        cls.server=Studio(("127.0.0.1",0),Handler,cls.root,"ugc-v14-ci-"+"X"*40,
            voice_model_en=Path(os.environ["UGC_TEST_PIPER_MODEL_EN"]),
            voice_license_ref_en="https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD")
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=8)
        cls.tmp.cleanup()

    def call(self,path,method="GET",data=None,auth=True,headers=None):
        h=dict(headers or {})
        if auth:h["Authorization"]="Bearer "+self.server.token
        if isinstance(data,dict):
            data=json.dumps(data,ensure_ascii=False).encode()
            h["Content-Type"]="application/json"
        req=Request(self.base+path,method=method,data=data,headers=h)
        try:
            with urlopen(req,timeout=60) as response:
                raw=response.read()
                return response.status,json.loads(raw) if "application/json" in response.headers.get("Content-Type","") else raw
        except HTTPError as error:
            raw=error.read()
            try:raw=json.loads(raw)
            except (ValueError,UnicodeError):pass
            return error.code,raw

    def wait(self,kind,timeout=500):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            code,p=self.call("/api/projects/"+self.pid)
            self.assertEqual(code,200,p)
            if p["job"]["status"] in {"completed","failed"}:
                self.assertEqual(p["job"].get("kind"),kind,p["job"])
                self.assertEqual(p["job"]["status"],"completed",p["job"])
                return p
            time.sleep(.4)
        self.fail("Timeout while creating real "+kind)

    def test_01_setup_and_real_english_voice(self):
        self.assertEqual(self.call("/api/projects",auth=False)[0],401)
        status,res=self.call("/api/projects","POST",{"name":"Real V14 test"})
        self.assertEqual(status,201,res)
        self.__class__.pid=res["id"]
        for name,color in (("red.png",(244,48,42)),("blue.png",(36,87,235))):
            code,res=self.call(f"/api/projects/{self.pid}/media?filename={name}",
                "POST",png(color),headers={"Content-Type":"image/png"})
            self.assertEqual(code,201,res)
            self.assertEqual(res["media"]["type"],"image")
        code,job=self.call("/api/projects/"+self.pid+"/voice","POST",
            {"language":"en","text":"This story uses two real product photographs. The soundtrack is generated entirely offline, with no paid API.","confirm_voice_rights":True})
        self.assertEqual(code,202,job)
        project=self.wait("voice")
        voices=[m for m in project["media"] if m.get("generated_by")=="piper_local"]
        self.assertEqual(len(voices),1)
        self.__class__.voice=voices[0]["file"]
        self.assertGreater(voices[0]["duration"],2)
        self.assertEqual(inspect_narration(self.root/self.pid/self.voice,voices[0]["voice_sha256"])["language"],"en_US")

    def payload(self,**kwargs):
        result={"audio":self.voice,"images":["media/red.png","media/blue.png"],
            "title":"Genuine product","preview":True,
            "confirm_image_rights":True,"claims_verified":True}
        result.update(kwargs)
        return result

    def test_02_reject_unauthorized_and_unlicensed_inputs(self):
        path="/api/projects/"+self.pid+"/narrated"
        self.assertEqual(self.call(path,"POST",self.payload(),auth=False)[0],401)
        for invalid in (
            self.payload(confirm_image_rights=False),
            self.payload(claims_verified=False),
            self.payload(images=[]),
            self.payload(images=["media/red.png"]*2),
            self.payload(images=["../escape.png"]),
            self.payload(images=["media/missing.png"]),
            self.payload(audio="media/red.png"),
            self.payload(audio="media/unknown.wav"),
            self.payload(title="<b>FAKE</b>"),
            self.payload(preview="false")
        ):
            code,res=self.call(path,"POST",invalid)
            self.assertEqual(code,400,(invalid,res))

    def verify_result(self,name,width,height):
        file=self.root/self.pid/"renders"/name
        self.assertTrue(file.is_file(),name)
        report=json.loads(file.with_suffix(".report.json").read_text())
        self.assertEqual(report["status"],"REQUIRES_HUMAN_REVIEW")
        self.assertEqual(report["disclosure"],DISCLOSURE)
        self.assertEqual(report["photo_count"],2)
        self.assertEqual(report["visual_text_layout"],"editorial_product_card_v16")
        self.assertTrue(report["scene_counter"])
        self.assertIn(report["title_line_count"],range(1,5))
        self.assertEqual(report["language"],"en_US")
        self.assertFalse(report["lip_sync_generated"])
        self.assertTrue(report["full_ffmpeg_decode_passed"])
        self.assertTrue(report["human_review_required"])
        inspected=subprocess.run(["ffprobe","-v","error","-of","json",
            "-show_format","-show_streams",str(file)],capture_output=True,text=True,check=True)
        meta=json.loads(inspected.stdout)
        tracks=meta["streams"]
        video=next(x for x in tracks if x["codec_type"]=="video")
        audio=next(x for x in tracks if x["codec_type"]=="audio")
        self.assertEqual((video["width"],video["height"]),(width,height))
        self.assertEqual(video["codec_name"],"h264")
        self.assertEqual(audio["codec_name"],"aac")
        self.assertGreater(float(meta["format"]["duration"]),2)
        outputs=self.call("/api/projects/"+self.pid)[1]["outputs"]
        url=next(x["url"] for x in outputs if x["name"]==name)
        code,data=self.call(url,auth=False,headers={"Range":"bytes=0-31"})
        self.assertEqual((code,len(data)),(206,32))
        self.assertIn(b"ftyp",data)
        sample_dir=os.getenv("UGC_V16_ARTIFACTS_DIR")
        if sample_dir:
            folder=Path(sample_dir)
            folder.mkdir(parents=True,exist_ok=True)
            subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
                "-ss","0.75","-i",str(file),"-frames:v","1",
                str(folder/(file.stem+".png"))],check=True,timeout=75)
        return file

    def test_03_real_preview_and_two_distinct_scenes(self):
        endpoint="/api/projects/"+self.pid+"/narrated"
        code,result=self.call(endpoint,"POST",self.payload(title="A premium everyday product with lasting quality"))
        self.assertEqual(code,202,result)
        self.assertEqual(self.call(endpoint,"POST",self.payload(title="A premium everyday product with lasting quality"))[0],409)
        project=self.wait("narrated")
        self.assertTrue(project["job"]["preview"])
        file=self.verify_result("narrated_preview.mp4",360,640)
        report=json.loads(file.with_suffix(".report.json").read_text())
        self.assertGreaterEqual(report["title_line_count"],2)
        def center(when):
            r=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-ss",str(when),
                "-i",str(file),"-frames:v","1","-vf","crop=1:1:180:320,format=rgb24",
                "-f","rawvideo","-"],capture_output=True,check=True,timeout=40)
            return tuple(r.stdout[:3])
        early=center(.6)
        late=center(float(project["job"]["duration"])-.6)
        self.assertGreater(early[0],early[2]+35,(early,late))
        self.assertGreater(late[2],late[0]+35,(early,late))

    def test_04_real_full_hd_export(self):
        code,response=self.call("/api/projects/"+self.pid+"/narrated","POST",self.payload(preview=False))
        self.assertEqual(code,202,response)
        p=self.wait("narrated")
        self.assertFalse(p["job"]["preview"])
        full=self.verify_result("narrated.mp4",1080,1920)
        self.assertNotEqual(full.stat().st_size,(self.root/self.pid/"renders/narrated_preview.mp4").stat().st_size)

    def test_05_real_timeline_progresses_inside_encoded_preview(self):
        """Inspect real encoded pixels at start and end: progress must move."""
        video = self.root/self.pid/"renders"/"narrated_preview.mp4"
        report = json.loads(video.with_suffix(".report.json").read_text())
        self.assertEqual(report["animated_progress_segments"], 20)
        self.assertEqual(report["animated_headline"], "slide_fade_500ms")
        # Track begins at x=23 and ends at x=336 in a 360px preview.
        # Sample the centre of segment 15, away from its one-pixel gap.
        x = 23 + round(14.5 * int(360*.87) / 20)
        y = int(640 * .883) + 1
        def sample(at):
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error",
                 "-ss", f"{at:.3f}", "-i", str(video), "-frames:v", "1",
                 "-vf", f"crop=1:1:{x}:{y},format=rgb24",
                 "-f", "rawvideo", "-"],
                capture_output=True, check=True, timeout=45)
            self.assertEqual(len(result.stdout), 3)
            return tuple(result.stdout)
        early = sample(.12)
        late = sample(report["duration"]-.18)
        self.assertGreater(late[0], early[0]+45, (early, late))
        self.assertGreater(late[1], early[1]+35, (early, late))

    def test_05_title_wrapping_boundaries(self):
        for original in ("Simple", "Premium everyday skincare for your routine",
                         "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW"):
            for preview in (True, False):
                rendered, size, count = layout_title(original, preview)
                self.assertEqual(rendered.replace("\n","").replace(" ",""),
                                 original.replace(" ",""))
                self.assertTrue(1 <= count <= 4)
                self.assertTrue(all(len(line) <= 16 for line in rendered.split("\n")))
                self.assertGreater(size, 0)

    def test_06_legacy_ui_and_private_status_unchanged(self):
        code,page=self.call("/",auth=False)
        self.assertEqual(code,200)
        self.assertIn(b'id="narratedPanel"',page)
        code,js=self.call("/studio.js",auth=False)
        self.assertEqual(code,200)
        self.assertIn(b"runNarrated",js)
        self.assertIn(b"runExport",js)
        self.assertEqual(self.call("/api/projects/"+self.pid+"/check","POST",{})[0],409)

if __name__=="__main__":
    unittest.main(verbosity=2)
