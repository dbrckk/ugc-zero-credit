# UGC Zero Credit

**UGC / TikTok / Reels post-production pipeline — V6.** A self-hosted, offline tool for assembling authorized AI-presenter footage, product inserts, original music, subtitles and quality evidence. No paid video/voice generation API or token is called.

## Capabilities

- Preserve each talking clip's **native speech/video timing** (no artificial redubbing).
- Produce vertical **1080 × 1920, 30 FPS, H.264/AAC** MP4 with FFmpeg.
- Compose product footage with non-destructive editorial proposals and stable subtitle timings.
- Validate rights metadata, audio sync, audio loudness, frame freezes, black frames, optional face/mouth motion, and mobile-safe text placement.
- Generate offline preview, audit reports, contact sheets and a browser-based review page.
- Prevent publication of synthetic test footage and block unapproved media.

**Limits:** does not itself generate photorealistic AI influencers, generate a natural voice, guarantee phoneme-accurate lip-sync, verify product authenticity, or publish to TikTok. Requires a legally usable speaking AI-presenter video and other authorized media. Reports are diagnostic, not a substitute for human editorial review.

## Install and run (Linux / remote server)

Requirements: Python 3.10+, `ffmpeg`, `ffprobe`; OpenCV/NumPy are **optional**, for local face QA and certain integration tests. No model weights are downloaded automatically.

```bash
git clone https://github.com/dbrckk/ugc-zero-credit.git
cd ugc-zero-credit
python3 make_synthetic_demo.py
python3 ugc.py doctor
python3 ugc.py check examples/synthetic_demo.json
python3 ugc.py render examples/synthetic_demo.json --output demo_1080x1920.mp4
python3 ugc.py audit demo_1080x1920.mp4 --full-decode
```

For a commercial project: copy `project_template.json`, fill in your local source paths, verified claims and permissions, then:

```bash
python3 ugc.py check my_project.json --strict-editorial
python3 ugc.py render my_project.json --require-speaking-face --output final.mp4
```

Read `PROCESS_V6.md` and `RELEASE_NOTES_V6.md` for the strict review and publication gates.

## Run local checks

```bash
python3 functional_checks_v3.py
python3 functional_checks_v4.py
python3 functional_checks_v5.py
python3 functional_checks_v6.py
```

The synthetic example is **not publishable**. The example captions are illustrative, not a real voice transcript. A passed audio-waveform check alone does **not** verify lip/phoneme synchrony.

## Free-by-default policy

No external generation API, no paid provider credits, no remote Actions run by default. Local rendering consumes CPU, disk, and electricity. Optional vision dependencies may require a one-time package download; optional local speech transcription requires a previously downloaded licensed model.

Developed separately from [monteur-video](https://github.com/dbrckk/monteur-video) and transferred from the isolated V6 development branch. No examples containing real influencers, commercial products or unapproved media are included.
