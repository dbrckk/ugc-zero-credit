#!/usr/bin/env python3
"""Acceptance checks against a REAL running Docker-backed bilingual studio.

No fake TTS: calls authenticated HTTP endpoints and waits for Piper WAV artifacts.
Can be run a second time after a container restart to prove volume persistence.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
from urllib.error import HTTPError
import wave
import io

TOKEN = os.environ["UGC_STUDIO_TOKEN"]
BASE = "http://127.0.0.1:" + os.environ.get("UGC_STUDIO_PORT","8787")
STATE = Path(os.environ.get("UGC_V13_STATE_FILE","/tmp/ugc_v13_ci_state.json"))
AUTH = {"Authorization":"Bearer "+TOKEN}


def call(path, method="GET", payload=None, token=True, headers=None):
    given=dict(headers or {})
    if token:
        given.update(AUTH)
    raw=json.dumps(payload).encode() if payload is not None else None
    if raw is not None:
        given["Content-Type"]="application/json"
    req=urllib.request.Request(BASE+path,method=method,data=raw,headers=given)
    try:
        with urllib.request.urlopen(req,timeout=40) as response:
            data=response.read()
            return response.status, json.loads(data) if "application/json" in response.headers.get("Content-Type","") else data
    except HTTPError as err:
        data=err.read()
        try: data=json.loads(data)
        except ValueError: pass
        return err.code,data


def poll_ready(timeout=120):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        try:
            code,res=call("/api/health")
            if code==200:
                return res
        except Exception:
            pass
        time.sleep(2)
    raise AssertionError("Studio non prêt / authentification impossible")


def wait_job(pid, expected, timeout=140):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        code,data=call("/api/projects/"+pid)
        assert code==200,(code,data)
        job=data["job"]
        if job["status"]=="completed":
            assert job.get("language")==expected,(job,expected)
            return data
        if job["status"]=="failed":
            raise AssertionError("Échec du vrai rendu Piper: "+str(job))
        time.sleep(.4)
    raise AssertionError("Temps limite dépassé")


def verify_tracks(data):
    files={x.get("language"):x for x in data["media"] if x.get("generated_by")=="piper_local"}
    assert set(files)=={"fr","en"},files
    assert files["fr"]["voice_locale"]=="fr_FR"
    assert files["en"]["voice_locale"]=="en_US"
    assert files["fr"]["voice_sha256"] != files["en"]["voice_sha256"]
    for lang,item in files.items():
        code,wav=call(item["url"],token=False)
        assert code==200,(lang,code)
        with wave.open(io.BytesIO(wav),"rb") as audio:
            assert audio.getframerate()>=16000
            assert audio.getnframes() > audio.getframerate()//2
        code,ranged=call(item["url"],token=False,headers={"Range":"bytes=0-63"})
        assert code==206 and ranged[:4]==b"RIFF",(code,ranged[:4])
        print("Verified real",lang,"WAV:",len(wav),"bytes")
    return files


def main():
    health=poll_ready()
    assert health["voice_languages"]==["fr","en"],health
    assert health["voice_generation_enabled"] is True
    assert health["paid_generators"] is False
    assert call("/api/health",token=False)[0]==401
    if "--after-restart" in sys.argv:
        pid=STATE.read_text().strip()
        code,project=call("/api/projects/"+pid)
        assert code==200,(code,project)
        verify_tracks(project)
        print("V13 persistent Docker volume verified after restart.")
        return
    code,project=call("/api/projects",method="POST",payload={"name":"V13 Docker acceptance bilingual"})
    assert code==201,(code,project)
    pid=project["id"]
    STATE.write_text(pid)
    for language,text in (
        ("fr","Bonjour, cette voix française est générée réellement sur le serveur."),
        ("en","Hello, this English voice is generated locally on the server."),
    ):
        url="/api/projects/"+pid+"/voice"
        data={"language":language,"text":text,"confirm_voice_rights":True}
        code,res=call(url,method="POST",payload=data)
        assert code==202,(language,code,res)
        verify=wait_job(pid,language)
        print("Completed Piper",language,verify["job"]["status"])
    verify_tracks(verify)
    print("V13 complete: secure API, bilingual real CPU synthesis, signed streaming.")


if __name__=="__main__":
    main()
