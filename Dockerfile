# syntax=docker/dockerfile:1
# Reproducible local-first CPU studio. Voice models are downloaded at BUILD
# time only; runtime has no external inference or weights download.
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates ffmpeg espeak-ng libgomp1 tini \
 && rm -rf /var/lib/apt/lists/*

# Pin the independently versioned open-source TTS runtime.
RUN python -m pip install --disable-pip-version-check 'piper-tts==1.8.0'

# Preserve build cache across edits: do not re-download voices for code-only changes.
RUN mkdir -p /opt/ugc-voices \
 && python -m piper.download_voices fr_FR-siwis-medium en_US-lessac-medium --data-dir /opt/ugc-voices \
 && test -s /opt/ugc-voices/fr_FR-siwis-medium.onnx \
 && test -s /opt/ugc-voices/fr_FR-siwis-medium.onnx.json \
 && test -s /opt/ugc-voices/en_US-lessac-medium.onnx \
 && test -s /opt/ugc-voices/en_US-lessac-medium.onnx.json

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin ugc \
 && install -d -m 0700 -o ugc -g ugc /data
WORKDIR /app
COPY --chown=ugc:ugc . /app
USER ugc
EXPOSE 8787
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "studio_web.py", \
     "--host", "0.0.0.0", "--port", "8787", "--data", "/data", \
     "--voice-model-fr", "/opt/ugc-voices/fr_FR-siwis-medium.onnx", \
     "--voice-license-ref-fr", "https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD", \
     "--voice-model-en", "/opt/ugc-voices/en_US-lessac-medium.onnx", \
     "--voice-license-ref-en", "https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/lessac/medium/MODEL_CARD"]
