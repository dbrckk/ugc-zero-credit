#!/usr/bin/env python3
"""V11 offline constraints + real Piper inference when explicitly configured."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
import wave

from offline_presenter import (clean_text, required_reference, voice_model,
                               synthesize, require_musetalk, audio_info, digest)

class VoiceEngineTests(unittest.TestCase):
    def test_text_restrictions(self):
        self.assertEqual(clean_text("  Bonjour   à tous  "), "Bonjour à tous")
        for text in ("", "x", "a"*1201, "<voice>bonjour</voice>", "a\x01z"):
            with self.subTest(text=text[:15]), self.assertRaises(ValueError):
                clean_text(text)

    def test_rights_validation(self):
        with self.assertRaises(ValueError):
            required_reference("", "licence")
        self.assertEqual(required_reference("https://example.org/card", "licence"),
                         "https://example.org/card")

    def test_incomplete_model_rejected(self):
        with tempfile.TemporaryDirectory() as dirname:
            model=Path(dirname)/"voice.onnx"
            model.write_bytes(b"1"*2048)
            with self.assertRaises(FileNotFoundError): voice_model(model)
            config=model.with_suffix(".onnx.json")
            config.write_text(json.dumps({"phoneme_type":"espeak", "language":{"code":"fr_FR"}}))
            self.assertEqual(voice_model(model)["language"],"fr_FR")
            with self.assertRaises(ValueError):
                synthesize("Bonjour",model,Path(dirname)/"narration.wav",
                           voice_license_ref="https://example.org/licence",confirmed=False)
            self.assertFalse((Path(dirname)/"narration.wav").exists())

    def test_musetalk_missing_gpu_weights_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as dirname:
            root=Path(dirname)
            (root/"scripts").mkdir()
            (root/"scripts"/"inference.py").write_text("")
            with self.assertRaises(FileNotFoundError):
                require_musetalk(root,Path(sys.executable))

    @unittest.skipUnless(__import__("os").environ.get("UGC_TEST_PIPER_MODEL"),"No installed model")
    def test_real_french_voice_cpu_and_atomic_output(self):
        model=Path(__import__("os").environ["UGC_TEST_PIPER_MODEL"])
        with tempfile.TemporaryDirectory() as dirname:
            target=Path(dirname)/"narration.wav"
            result=synthesize("Bonjour, voici une démonstration de notre voix française.",
                              model,target,
                              voice_license_ref="https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD",
                              confirmed=True)
            self.assertTrue(target.is_file())
            self.assertEqual(result["status"],"VOICE_GENERATED_NOT_LIPSYNCED")
            self.assertGreater(result["duration"],.3)
            self.assertEqual(result["wav_sha256"],digest(target))
            with wave.open(str(target),"rb") as wav:
                self.assertGreater(wav.getnframes(), 0)
            self.assertEqual(audio_info(target)["sample_rate"],result["sample_rate"])
            self.assertFalse(result["human_lip_sync_proven"])
            self.assertTrue(target.with_suffix(".voice.json").is_file())
            with self.assertRaises(FileExistsError):
                synthesize("Une autre phrase.",model,target,
                           voice_license_ref="https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD",
                           confirmed=True)
            ff=subprocess.run(["ffprobe","-v","error","-show_entries",
                               "stream=codec_name,sample_rate","-of","json",str(target)],
                              capture_output=True,text=True,check=True)
            decoded=json.loads(ff.stdout)
            self.assertEqual(decoded["streams"][0]["codec_name"],"pcm_s16le")


if __name__=="__main__":
    unittest.main(verbosity=2)
