#!/usr/bin/env python3
"""V10: real FFmpeg portrait product cards, editorial QA and Android form contract.

Entirely local synthetic media; no model downloads or paid API calls.
"""
from __future__ import annotations
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

from make_synthetic_demo import create
from overlay_layout import card_geometry, framed_card_filters
from ugc import load_project, verify, build
from editorial_quality import analyze
from auto_edit import propose

ROOT=Path(__file__).resolve().parent


def rgb_frame(path:Path, seconds:float) -> bytes:
    # Read one exact preview-sized RGB frame for a visual-composition regression.
    result=subprocess.run(
        ["ffmpeg","-hide_banner","-loglevel","error","-nostdin",
         "-ss",str(seconds),"-i",str(path),"-frames:v","1",
         "-vf","scale=360:640","-pix_fmt","rgb24","-f","rawvideo","-"],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=90)
    if len(result.stdout)!=360*640*3:
        raise AssertionError("Trame vidéo non décodable (360 × 640)")
    return result.stdout


def rgb_at(frame:bytes,x:int,y:int):
    pos=(y*360+x)*3
    return tuple(frame[pos:pos+3])


def color_distance(one,other):
    return sum(abs(a-b) for a,b in zip(one,other))


class ProductPictureInPictureV10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        create()
        cls.config, cls.root=load_project(ROOT/"examples"/"synthetic_demo.json")
        cls.checked=verify(cls.config,cls.root)

    def test_01_geometry_safe_at_preview_and_export(self):
        for w,h in ((360,640),(1080,1920)):
            left=card_geometry("pip_left",w,h)
            right=card_geometry("pip_right",w,h)
            self.assertEqual(left["total_width"],right["total_width"])
            self.assertLess(left["x"]+left["total_width"],right["x"])
            for g in (left,right):
                self.assertGreater(g["y"],h*.20)
                self.assertLessEqual(g["y"]+g["total_height"],h*.68)
                self.assertLessEqual(g["x"]+g["total_width"],w)
                self.assertIn("pad=",framed_card_filters(g["border"],g["shadow"]))
            self.assertEqual(card_geometry("full",w,h)["inner_width"],w)
        with self.assertRaises(ValueError): card_geometry("pip_center",360,640)

    def test_02_validation_and_backward_compatibility(self):
        self.assertEqual(len(verify(self.config,self.root)["talking"]),1)
        changed=copy.deepcopy(self.config)
        changed["overlays"][0]["layout"]="pip_left"
        self.assertEqual(len(verify(changed,self.root)["talking"]),1)
        changed["overlays"][0]["layout"]="dangerous"
        with self.assertRaises(ValueError): verify(changed,self.root)

    def test_03_editorial_facts_not_invented(self):
        pip=copy.deepcopy(self.config["overlays"])
        for i,l in enumerate(pip):
            l["layout"]="pip_left" if i==0 else "pip_right"
        whole=analyze(self.checked,self.config["overlays"])
        cards=analyze(self.checked,pip)
        self.assertGreater(whole["speech_covered_ratio"],0)
        self.assertEqual(cards["speech_covered_ratio"],0)
        self.assertEqual(cards["picture_in_picture_count"],2)
        self.assertTrue(cards["picture_in_picture_may_cover_speaker"])
        self.assertTrue(cards["does_not_estimate_phoneme_lipsync"])

    def test_04_autoplanner_preserves_product_cards(self):
        changed=copy.deepcopy(self.config)
        changed["overlays"][0]["layout"]="pip_right"
        proposed,report=propose(changed,self.checked)
        self.assertIn(changed["overlays"][0],proposed["overlays"])
        self.assertTrue(report["human_review_required"])

    def test_05_ffmpeg_actual_card_and_native_audio(self):
        with tempfile.TemporaryDirectory(prefix="ugc-v10-render-") as scratch:
            workspace=Path(scratch)
            original=copy.deepcopy(self.config)
            original["overlays"]=[]
            original["face_policy"]="off"
            original["music"]=None
            base=workspace/"base.mp4"
            base_report=build(original,self.root,base,preview=True,
                              full_decode=True,strict_sync=True,face_policy_override="off")
            self.assertTrue(base_report["sync_audio_gate"]["native_audio_preserved"])
            pip=copy.deepcopy(original)
            pip["overlays"]=[copy.deepcopy(self.config["overlays"][0])]
            pip["overlays"][0]["layout"]="pip_left"
            pip["overlays"][0]["start"]=1.
            pip["overlays"][0]["duration"]=1.4
            pip["overlays"][0]["fade"]=.0
            pip["editorial_policy"]="required"
            video=workspace/"pip_photo.mp4"
            report=build(pip,self.root,video,preview=True,
                         full_decode=True,strict_sync=True,face_policy_override="off")
            self.assertEqual((report["width"],report["height"]),(360,640))
            self.assertTrue(report["sync_audio_gate"]["native_audio_preserved"])
            self.assertEqual(report["editorial_quality"]["speech_covered_ratio"],0)
            self.assertEqual(report["overlay_layouts"][0]["layout"],"pip_left")
            baseline=rgb_frame(base,1.65)
            composited=rgb_frame(video,1.65)
            self.assertLess(color_distance(rgb_at(baseline,190,285),rgb_at(composited,190,285)),18,
                            "Le centre doit rester visible: la carte n'est pas plein écran")
            self.assertGreater(color_distance(rgb_at(baseline,55,300),rgb_at(composited,55,300)),30,
                               "La carte produit doit réellement apparaître à gauche")
            self.assertTrue(video.with_suffix(".report.json").exists())
            self.assertTrue(video.with_suffix(".srt").exists())
            # Video inserts (not only photos) must follow the same compositing path.
            moving=copy.deepcopy(original)
            moving["overlays"]=[{"file":"demo_media/presentation_demo.mp4",
                                 "rights":"owned","source_in":0,"start":1.0,
                                 "duration":.8,"fade":0,"motion":"static","layout":"pip_right"}]
            moving_output=workspace/"pip_video.mp4"
            video_report=build(moving,self.root,moving_output,preview=True,
                               full_decode=True,strict_sync=True,face_policy_override="off")
            self.assertEqual(video_report["overlay_layouts"][0]["layout"],"pip_right")
            self.assertTrue(video_report["sync_audio_gate"]["native_audio_preserved"])
            self.assertTrue(moving_output.exists())


if __name__=="__main__":
    unittest.main(verbosity=2)
