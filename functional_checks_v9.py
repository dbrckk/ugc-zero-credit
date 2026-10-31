#!/usr/bin/env python3
"""Offline regression tests for bounded render queue (no network, no FFmpeg)."""
import unittest
from studio_scheduling import admission, is_active, MAX_ACTIVE_RENDERS

class RenderAdmissionTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(admission({}, "p"), "ok")
    def test_duplicate(self):
        self.assertEqual(admission({"p":{"status":"queued"}}, "p"), "already_running")
        self.assertEqual(admission({"p":{"status":"running"}}, "p"), "already_running")
    def test_queue_limit(self):
        jobs={"a":{"status":"running"},"b":{"status":"queued"}}
        self.assertEqual(admission(jobs,"c"),"server_busy")
        self.assertEqual(MAX_ACTIVE_RENDERS,2)
    def test_terminal_frees_capacity(self):
        jobs={"a":{"status":"completed"},"b":{"status":"failed"}}
        self.assertEqual(admission(jobs,"c"),"ok")
        self.assertFalse(is_active(jobs["a"]))
        self.assertFalse(is_active(jobs["b"]))
    def test_one_slot(self):
        self.assertEqual(admission({"a":{"status":"running"}},"b"),"ok")

if __name__ == "__main__":
    unittest.main(verbosity=2)
