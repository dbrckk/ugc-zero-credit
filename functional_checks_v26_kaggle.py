#!/usr/bin/env python3
"""Milestone-only control-plane checks; never pretend a Kaggle GPU was used."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import kaggle_automate as ka


class KaggleOrchestrationTests(unittest.TestCase):
    def test_status_strict(self):
        self.assertEqual(ka.status_value('owner/notebook has status "KernelWorkerStatus.COMPLETE"'),
                         "COMPLETE")
        self.assertEqual(ka.status_value('KernelWorkerStatus.QUEUED'), "QUEUED")
        for source in ("", "complete", "KernelWorkerStatus.UNDEFINED",
                       "KernelWorkerStatus.COMPLETE and KernelWorkerStatus.ERROR"):
            with self.subTest(value=source), self.assertRaises(ValueError):
                ka.status_value(source)

    def test_private_kernel_metadata_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "kernel"
            handle = ka.notebook_kernel(folder, user="authorized-user",
                                        slug="ugc-zero-credit-private",
                                        dataset="authorized-user/private-clip")
            self.assertEqual(handle, "authorized-user/ugc-zero-credit-private")
            meta = json.loads((folder / "kernel-metadata.json").read_text())
            self.assertIs(meta["is_private"], True)
            self.assertIs(meta["enable_gpu"], True)
            self.assertIs(meta["enable_internet"], True)
            self.assertEqual(meta["machine_shape"], "NvidiaTeslaT4")
            self.assertEqual(meta["dataset_sources"], ["authorized-user/private-clip"])
        for bad in ("other-user/no", "../bad", "a/xx", "unknown/test/invalid"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ka.ref(bad, "test")

    def test_real_encoded_input_and_private_upload_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private = root / "source"
            private.mkdir()
            original = private / "presenter.mp4"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "testsrc2=s=320x512:r=25", "-t", "1.3",
                            "-c:v", "libx264", "-preset", "ultrafast", str(original)],
                           capture_output=True, check=True, timeout=75)
            (private / "language.txt").write_text("fr")
            (private / "portrait_rights.txt").write_text("Authorized synthetic test scene, no human likeness")
            (private / "script.txt").write_text("Bonjour, voici une publicité test.")
            calls = []
            def fake(args, *, timeout=180):
                calls.append(args)
                return "Dataset creation requested"
            with mock.patch.object(ka, "command", side_effect=fake):
                handle = ka.private_dataset_from_media(private, "authorized-user", root)
            self.assertTrue(handle.startswith("authorized-user/ugc-private-"))
            commands = calls[0]
            self.assertEqual(commands[:2], ["datasets", "create"])
            self.assertNotIn("--public", commands)
            dest = root / "dataset"
            meta = json.loads((dest / "dataset-metadata.json").read_text())
            self.assertEqual(meta["licenses"], [{"name": "other"}])
            self.assertEqual((dest / "presenter.mp4").read_bytes(), original.read_bytes())
            self.assertFalse((dest / "dataset-metadata.json").is_symlink())
            (private / "portrait_rights.txt").write_text("")
            with self.assertRaises(ValueError):
                ka.private_dataset_from_media(private, "authorized-user", root / "unused")

    def test_poll_wait_not_falsely_successful(self):
        values = iter(["KernelWorkerStatus.QUEUED", "KernelWorkerStatus.RUNNING",
                       "KernelWorkerStatus.COMPLETE"])
        with mock.patch.object(ka, "command", side_effect=lambda *a, **kw: next(values)), \
             mock.patch.object(ka.time, "sleep"):
            ka.wait("owner/ugc-zero-credit-private", minutes=5, interval=10)
        with mock.patch.object(ka, "command", return_value="KernelWorkerStatus.ERROR"), \
             self.assertRaisesRegex(RuntimeError, "échec"):
            ka.wait("owner/ugc-zero-credit-private", minutes=5, interval=10)
        with mock.patch.object(ka, "command", return_value="completed"), \
             mock.patch.object(ka.time, "sleep"), \
             self.assertRaisesRegex(RuntimeError, "inaccessible"):
            ka.wait("owner/ugc-zero-credit-private", minutes=5, interval=10)

    def test_checksum_and_gpu_evidence_is_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "ugc-v25-results"
            output.mkdir()
            file = output / "presenter_abc.mp4"
            # Real locally decoded H264/AAC test fixture, NOT MuseTalk inference.
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "testsrc2=s=320x512:r=25",
                            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000",
                            "-t", "1.4", "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac", "-shortest", str(file)],
                           capture_output=True, check=True, timeout=75)
            report = output / "presenter_abc.presenter.json"
            metadata = {"sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                        "gpu_inference_executed": True,
                        "ffmpeg_full_decode": True,
                        "publication_allowed_automatically": False}
            report.write_text(json.dumps(metadata))
            self.assertEqual(ka.check_results(root), [file])
            metadata["sha256"] = "broken"
            report.write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "Preuve"):
                ka.check_results(root)
            report.unlink()
            with self.assertRaisesRegex(RuntimeError, "sans manifeste"):
                ka.check_results(root)

    def test_no_token_or_private_media_leaked_via_failed_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.dict(os.environ, {"KAGGLE_API_TOKEN": "KGAT_sensitive_test_token_123456"}), \
                 mock.patch.object(ka, "check_auth"), \
                 mock.patch.object(ka, "command", side_effect=RuntimeError("Quota Kaggle")) as api:
                with self.assertRaises(RuntimeError):
                    ka.main(["--user", "authorized-user",
                             "--dataset", "authorized-user/private-data",
                             "--kernel-slug", "ugc-zero-credit-private",
                             "--wait-minutes", "5"])
                args = api.call_args[0][0]
                self.assertEqual(args[:2], ["kernels", "push"])
                self.assertNotIn("KGAT_sensitive_test_token_123456", str(args))
            with self.assertRaises(SystemExit):
                ka.main(["--user", "authorized-user", "--dataset", "wrong-owner/data"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
