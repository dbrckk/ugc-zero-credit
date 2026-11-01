#!/usr/bin/env python3
"""Real authenticated Piper -> photo uploads -> FFmpeg preview and Full-HD."""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import wave
import zlib
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from studio_web import Handler, Studio
from narrated_short import inspect_narration, DISCLOSURE, layout_title
from offline_presenter import inspect_video, audible_audio_peak, prepare_presenter_video
from speech_scene_timing import plan_scenes

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

    def test_00_actual_silence_guides_cuts_without_paid_inference(self):
        """Create a WAV with two pauses and verify fade overlap mathematics."""
        with tempfile.TemporaryDirectory(prefix="ugc-v20-pacing-") as temp:
            path = Path(temp) / "narration.wav"
            rate = 16000
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(rate)
                sound = bytearray()
                for sample in range(rate * 6):
                    time_s = sample / rate
                    silent = 1.7 <= time_s < 2.1 or 3.7 <= time_s < 4.1
                    amplitude = 0 if silent else round(11000 * math.sin(2 * math.pi * 220 * time_s))
                    sound.extend(struct.pack("<h", amplitude))
                audio.writeframes(sound)
            plan = plan_scenes(path, 6.0, 3, .3)
            self.assertEqual(plan["pause_matches"], 2, plan)
            self.assertAlmostEqual(plan["cut_times"][0], 1.9, delta=.04)
            self.assertAlmostEqual(plan["cut_times"][1], 3.9, delta=.04)
            self.assertAlmostEqual(sum(plan["scene_durations"]) - .6, 6, delta=.0001)
            self.assertEqual(len(plan["transition_offsets"]), 2)
            self.assertLess(plan["transition_offsets"][0], plan["transition_offsets"][1])
            single = plan_scenes(path, 6, 1, 0)
            self.assertEqual(single["scene_durations"], [6])

    def test_00_real_av_quality_checks_reject_silent_voice(self):
        """No fake GPU: encode and inspect real H264/AAC files through FFmpeg."""
        with tempfile.TemporaryDirectory(prefix="ugc-v22-audio-") as temp:
            for silent in (False, True):
                output = Path(temp) / ("silent.mp4" if silent else "audible.mp4")
                audio = "anullsrc=r=16000:cl=mono" if silent else "sine=frequency=440:sample_rate=16000"
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                     "-f", "lavfi", "-i", "color=c=blue:s=320x400:r=25",
                     "-f", "lavfi", "-i", audio,
                     "-t", "1.25", "-c:v", "libx264", "-preset", "ultrafast",
                     "-c:a", "aac", "-shortest", str(output)],
                    check=True, capture_output=True, timeout=75)
                checked = inspect_video(output)
                self.assertEqual((checked["width"], checked["height"]), (320, 400))
                self.assertLessEqual(checked["av_track_gap_ms"], 450)
                if silent:
                    with self.assertRaisesRegex(RuntimeError, "muette|faible"):
                        audible_audio_peak(output)
                else:
                    self.assertGreater(audible_audio_peak(output), -55)

    def test_00_real_moving_presenter_footage_keeps_motion(self):
        """Use real decoded FFmpeg frames: the GPU source must NOT be a photo slide."""
        with tempfile.TemporaryDirectory(prefix="ugc-v23-motion-") as temp:
            root = Path(temp)
            original = root / "presenter.mp4"
            normalized = root / "avatar.mp4"
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "testsrc2=s=360x640:r=12",
                 "-t", "2.5", "-c:v", "libx264", "-preset", "ultrafast",
                 "-pix_fmt", "yuv420p", str(original)],
                capture_output=True, check=True, timeout=75)
            report = prepare_presenter_video(original, normalized, voice_seconds=2.0)
            self.assertEqual(report["source_type"], "moving_video")
            self.assertEqual(report["source_fps"], 12.)
            self.assertEqual(report["prepared_fps"], 25)
            self.assertEqual((report["prepared_width"], report["prepared_height"]), (360, 640))
            self.assertTrue(report["source_audio_replaced_with_piper"])
            self.assertGreater(report["prepared_frame_count"], 35)
            def frame(at):
                result = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error",
                     "-ss", str(at), "-i", str(normalized), "-frames:v", "1",
                     "-vf", "scale=48:80,format=rgb24", "-f", "rawvideo", "-"],
                    capture_output=True, check=True, timeout=50)
                self.assertEqual(len(result.stdout), 48*80*3)
                return result.stdout
            self.assertNotEqual(frame(.2), frame(1.2))
            with self.assertRaisesRegex(ValueError, "MP4, MOV ou MKV"):
                prepare_presenter_video(root / "avatar.webm", root / "no.mp4", voice_seconds=2.0)
            with self.assertRaisesRegex(ValueError, "0,5"):
                prepare_presenter_video(original, root / "no.mp4", voice_seconds=65.0)
            (root / "danger.mp4").symlink_to(original)
            with self.assertRaisesRegex(ValueError, "symbolique"):
                prepare_presenter_video(root / "danger.mp4", root / "no.mp4", voice_seconds=2.0)

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
        self.assertEqual(report["visual_text_layout"],"cinematic_parallax_product_stage_v19")
        self.assertEqual(report["photo_motion"],"independent_foreground_entry_and_background_zoom")
        self.assertEqual(report["transition_styles"],["smoothright"])
        self.assertEqual(report["scene_cut_method"],"ffmpeg_silence_pauses_with_even_fallback_v20")
        self.assertEqual(len(report["scene_cut_times"]),1)
        self.assertEqual(len(report["scene_durations"]),2)
        self.assertGreater(report["scene_cut_times"][0],.5)
        self.assertLess(report["scene_cut_times"][0],report["duration"]-.5)
        self.assertAlmostEqual(sum(report["scene_durations"])-.3,report["duration"],delta=.4)
        self.assertLessEqual(report["scene_cuts_near_pauses"],1)
        self.assertGreaterEqual(report["photo_frame_px"],8)
        self.assertGreaterEqual(report["photo_entrance_ms"],320)
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
            for stamp,label in ((.10,"entry"),(.85,"settled")):
                subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y",
                    "-ss",str(stamp),"-i",str(file),"-frames:v","1",
                    str(folder/(file.stem+"_"+label+".png"))],
                    check=True,timeout=75)
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

    def test_05_product_photo_really_enters_from_right(self):
        """Pixel comparison proves the actual image card moves into the frame."""
        video = self.root/self.pid/"renders"/"narrated_preview.mp4"
        # First CI photo is flat red. At 0.10s its card has not yet reached
        # x=70; at 0.85s it occupies this point, brighter than the blur layer.
        def pixel(at):
            r = subprocess.run(
                ["ffmpeg","-hide_banner","-loglevel","error",
                 "-ss",str(at),"-i",str(video),"-frames:v","1",
                 "-vf","crop=1:1:70:210,format=rgb24",
                 "-f","rawvideo","-"],
                capture_output=True,check=True,timeout=45)
            self.assertEqual(len(r.stdout),3)
            return tuple(r.stdout)
        before, after = pixel(.10), pixel(.85)
        self.assertGreater(after[0], before[0]+32, (before,after))
        self.assertGreater(after[1], before[1]+18, (before,after))

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

    def test_05_gpu_presenter_is_explicitly_disabled_on_cpu_server(self):
        status, health = self.call("/api/health")
        self.assertEqual(status, 200)
        self.assertFalse(health["presenter_gpu_configured"])
        self.assertFalse(health["presenter_gpu_verified"])
        self.assertEqual(self.call("/api/presenter/readiness", auth=False)[0], 401)
        diagnostic_code, diagnostic = self.call("/api/presenter/readiness")
        self.assertEqual(diagnostic_code, 200)
        self.assertFalse(diagnostic["configured"])
        self.assertFalse(diagnostic["ready"])
        self.assertEqual(diagnostic["code"], "not_configured")
        path = "/api/projects/" + self.pid + "/presenter"
        payload = {"audio": self.voice, "portrait": "media/red.png",
                   "portrait_rights_ref": "portrait rights documented",
                   "confirm_voice_rights": True,
                   "confirm_portrait_rights": True,
                   "confirm_subject_consent": True}
        self.assertEqual(self.call(path, "POST", payload, auth=False)[0], 401)
        status, response = self.call(path, "POST", payload)
        self.assertEqual(status, 503, response)
        self.assertIn("MuseTalk", response["error"])
        status, project = self.call("/api/projects/" + self.pid)
        self.assertEqual(status, 200)
        self.assertNotEqual(project["job"].get("kind"), "presenter")
        status, page = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(b'id="presenterPanel"', page)
        status, js = self.call("/studio.js")
        self.assertEqual(status, 200)
        self.assertIn(b"generatePresenter", js)
        self.assertIn(b"refreshPresenterReadiness", js)

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
