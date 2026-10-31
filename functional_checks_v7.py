#!/usr/bin/env python3
"""Regression tests for genuine phrase-level SRT integration; offline, no APIs."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from subtitle_import import import_srt, parse_srt
from ugc import load_project, verify, write_captions, write_srt, build, probe

ROOT = Path(__file__).resolve().parent


class SrtTests(unittest.TestCase):
    def test_parse_numbered_crlf_bom_and_multiline(self):
        text = '\ufeff1\r\n00:00:00,230 --> 00:00:00,990\r\nUn excellent\r\nproduit !\r\n\r\n2\r\n00:00:01,200 --> 00:00:01,980\r\nCoucou.\r\n'
        self.assertEqual(parse_srt(text), [
            {"start": .230, "end": .990, "text": "Un excellent produit !"},
            {"start": 1.2, "end": 1.98, "text": "Coucou."}])

    def test_unumbered_srt_supported(self):
        cues = parse_srt('00:00:00.125 --> 00:00:01.000\nUne phrase.\n')
        self.assertEqual(cues[0]['start'], .125)

    def test_invalid_srt_is_not_silently_repaired(self):
        cases = ['', '1\n00:00:00,500 --> 00:00:00,400\nImpossible',
                 '1\n00:00:00,100 --> 00:00:01,000\nBien\n\n2\n00:00:00,900 --> 00:00:02,000\nChevauchement',
                 '1\n00:00:00,100 --> 00:00:01,000\n<i>HTML interdit</i>',
                 '1\n00:00:60,000 --> 00:00:61,000\nMauvais',
                 '1\n00:00:00,100 --> 00:00:01,000\n' + 'A'*93]
        for case in cases:
            with self.subTest(case=case[:30]), self.assertRaises(ValueError):
                parse_srt(case)


class ImportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from make_synthetic_demo import create
        create()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ugc-v7-subtitles-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        shutil.copytree(ROOT/'examples'/'demo_media', self.folder/'demo_media')
        self.config = json.loads((ROOT/'examples'/'synthetic_demo.json').read_text(encoding='utf-8'))
        self.project = self.folder/'source.json'
        self.project.write_text(json.dumps(self.config,ensure_ascii=False),encoding='utf-8')
        self.srt = self.folder/'voice.srt'
        self.srt.write_text('1\n00:00:00,250 --> 00:00:01,000\nLe produit est joli.\n\n2\n00:00:01,100 --> 00:00:02,450\nSa texture est nacrée.\n',encoding='utf-8')
        self.output = self.folder/'aligned.json'

    def test_requires_explicit_replacement(self):
        with self.assertRaisesRegex(ValueError,'--replace-existing'):
            import_srt(self.project,self.srt,self.output,clip_index=0)
        self.assertFalse(self.output.exists())

    def test_successful_import_maps_clip_time_and_keeps_original(self):
        original_sha = hashlib.sha256(self.project.read_bytes()).hexdigest()
        result = import_srt(self.project,self.srt,self.output,clip_index=0,replace_existing=True)
        conf,root = load_project(self.output)
        verified = verify(conf,root)
        self.assertEqual(result['phrases_imported'],2)
        self.assertEqual(conf['words'],[])
        self.assertEqual(conf['caption_mode'],'segments')
        self.assertEqual(len(verified['segments']),2)
        self.assertAlmostEqual(verified['segments'][0]['start'],.25)
        self.assertEqual(conf['caption_origins'][0]['word_level_alignment'],False)
        self.assertTrue(conf['caption_origins'][0]['manual_review_required'])
        self.assertEqual(hashlib.sha256(self.project.read_bytes()).hexdigest(),original_sha)
        with self.assertRaises(FileExistsError):
            import_srt(self.project,self.srt,self.output,clip_index=0,replace_existing=True)

    def test_source_in_offset_is_applied(self):
        conf=copy.deepcopy(self.config)
        conf['talking_clips'][0]['source_in']=1
        conf['talking_clips'][0]['duration']=3
        conf['overlays']=[]
        conf['words']=[]
        conf['caption_mode']='none'
        self.project.write_text(json.dumps(conf),encoding='utf-8')
        out=import_srt(self.project,self.srt,self.output,clip_index=0)
        project,_=load_project(self.output)
        self.assertAlmostEqual(project['segments'][0]['start'],1.25)
        self.assertAlmostEqual(project['segments'][1]['end'],3.45)
        self.assertAlmostEqual(verify(project,self.folder)['segments'][0]['start'],.25)
        self.assertEqual(out['timebase'],'clip')

    def test_source_timebase_and_out_of_range_are_checked(self):
        conf=copy.deepcopy(self.config)
        conf['talking_clips'][0]['source_in']=1
        conf['talking_clips'][0]['duration']=2.6
        conf['overlays']=[]
        conf['words']=[]
        conf['caption_mode']='none'
        self.project.write_text(json.dumps(conf),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'hors de la portion'):
            import_srt(self.project,self.srt,self.output,clip_index=0,timebase='source')
        self.assertFalse(self.output.exists())
        self.srt.write_text('1\n00:00:01,100 --> 00:00:02,450\nUne phrase réelle.\n',encoding='utf-8')
        r=import_srt(self.project,self.srt,self.output,clip_index=0,timebase='source')
        self.assertEqual(r['phrases_imported'],1)
        self.assertAlmostEqual(verify(load_project(self.output)[0],self.folder)['segments'][0]['start'],.1)

    def test_import_does_not_erase_other_clips(self):
        conf=copy.deepcopy(self.config)
        conf['talking_clips'].append({**conf['talking_clips'][0]})
        conf['overlays']=[]
        conf['words']=[]
        conf['caption_mode']='segments'
        conf['segments']=[{"clip":1,"start":.4,"end":1.2,"text":"Autre clip conservé."}]
        self.project.write_text(json.dumps(conf),encoding='utf-8')
        import_srt(self.project,self.srt,self.output,clip_index=0)
        updated,_=load_project(self.output)
        verified=verify(updated,self.folder)
        self.assertEqual(len(verified['segments']),3)
        self.assertAlmostEqual(verified['segments'][-1]['start'],4.4)

    def test_rendered_mp4_contains_phrases_and_native_audio(self):
        import_srt(self.project,self.srt,self.output,clip_index=0,replace_existing=True)
        config,root=load_project(self.output)
        ass=self.folder/'phrases.ass';srt=self.folder/'phrases.srt'
        checked=verify(config,root)
        write_captions(ass,checked['words'],checked['total_duration'],360,640,config['product']['disclosure'],segments=checked['segments'])
        write_srt(srt,checked['words'],segments=checked['segments'])
        self.assertIn('Le produit est joli.',ass.read_text(encoding='utf-8'))
        self.assertIn('00:00:00,250 --> 00:00:01,000',srt.read_text(encoding='utf-8'))
        self.assertNotIn('\\c&H00D5AEFF&',ass.read_text(encoding='utf-8'))
        output=self.folder/'final.mp4'
        report=build(config,root,output,preview=True,face_policy_override='off')
        self.assertEqual(report['caption_mode'],'segments')
        self.assertEqual(report['subtitle_words'],0)
        self.assertEqual(report['subtitle_phrases'],2)
        self.assertTrue(report['sync_audio_gate']['native_audio_preserved'])
        self.assertEqual(int(probe(output)['streams'][0]['width']),360)
        self.assertTrue(output.with_suffix('.srt').exists())
        self.assertTrue(output.with_suffix('.jpg').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
