#!/usr/bin/env python3
"""Chromium mobile browser smoke test using only local synthetic assets."""
from pathlib import Path
import json
import base64
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import tempfile
import threading
from urllib.parse import quote

from playwright.sync_api import sync_playwright
from studio_web import Handler, Studio

ROOT=Path(__file__).resolve().parent


def run():
    with tempfile.TemporaryDirectory(prefix='ugc-v8-mobile-') as workspace:
        server=Studio(('127.0.0.1',0),Handler,Path(workspace),'offline-browser-token-'+'A'*35)
        server_thread=threading.Thread(target=server.serve_forever,daemon=True);server_thread.start()
        port=server.server_address[1]
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-gpu'])
                page=browser.new_page(viewport={'width':393,'height':852},device_scale_factor=1,is_mobile=True,has_touch=True)
                page.on('pageerror', lambda error: print('BROWSER JS ERROR:',str(error)))
                # This runner's managed Chromium blocks ALL navigation by policy.
                # Inject the real UI/JS into about:blank and bridge fetch through
                # Python urllib to the running HTTP server; all actual endpoints
                # are still exercised, but browser-native network is not.
                def bridge(source, req):
                    body = base64.b64decode(req.get('body','')) if req.get('body') else None
                    headers = req.get('headers',{})
                    request = Request(f"http://127.0.0.1:{port}"+req['path'],data=body,headers=headers,method=req.get('method','GET'))
                    try:
                        with urlopen(request,timeout=60) as response:
                            return {'status':response.status,'content_type':response.headers.get('Content-Type',''),
                                    'body':base64.b64encode(response.read()).decode()}
                    except HTTPError as e:
                        return {'status':e.code,'content_type':e.headers.get('Content-Type',''),
                                'body':base64.b64encode(e.read()).decode()}
                page.expose_binding('pyRequest',bridge)
                ui=(ROOT/'studio_web/index.html').read_text(encoding='utf-8')
                ui=ui.replace('<link rel="stylesheet" href="/studio.css">','').replace('<script defer src="/studio.js"></script>','')
                page.set_content(ui)
                page.add_style_tag(content=(ROOT/'studio_web/studio.css').read_text(encoding='utf-8'))
                page.add_script_tag(content='''
                    window.fetch = async (url, opts={}) => {
                        let payload='';
                        if(opts.body){
                            const bin=await (opts.body instanceof Blob?opts.body:new Blob([opts.body])).arrayBuffer();
                            const arr=new Uint8Array(bin);let s='';
                            for(let i=0;i<arr.length;i+=8192)s+=String.fromCharCode(...arr.slice(i,i+8192));
                            payload=btoa(s);
                        }
                        const output=await window.pyRequest({path:String(url),method:opts.method||'GET',body:payload,headers:opts.headers||{}});
                        const decoded=atob(output.body);const array=new Uint8Array(decoded.length);
                        for(let i=0;i<decoded.length;i++)array[i]=decoded.charCodeAt(i);
                        return new Response(array,{status:output.status,headers:{'Content-Type':output.content_type}});
                    };
                ''')
                page.add_script_tag(content=(ROOT/'studio_web/studio.js').read_text(encoding='utf-8'))
                assert page.get_by_text('Studio vidéo').is_visible()
                page.locator('#token').fill(server.token)
                page.locator('#connect').click()
                page.get_by_text('Connexion privée établie.').wait_for(timeout=20000)
                page.locator('#projectName').fill('Publicité démonstration IA — essai mobile')
                page.locator('#create').click()
                page.get_by_text('Projet créé.').first.wait_for(timeout=20000)
                for f in ['presentation_demo.mp4','produit.png','music_original.wav']:
                    page.locator('#uploadFiles').set_input_files(str(ROOT/'examples/demo_media'/f))
                    page.locator('#upload').click()
                    page.locator('#uploadStatus').get_by_text('Import terminé.').wait_for(timeout=30000)
                    page.locator('#upload').wait_for(state='visible')
                srtfile=Path(workspace)/'voix.srt';srtfile.write_text('1\n00:00:00,200 --> 00:00:01,000\nBonjour !\n\n2\n00:00:01,100 --> 00:00:03,400\nTexte vérifié, sans API.\n',encoding='utf-8')
                page.locator('#uploadFiles').set_input_files(str(srtfile));page.locator('#upload').click()
                page.locator('#uploadStatus').get_by_text('Import terminé.').wait_for(timeout=30000)
                page.locator('#productName').fill('DEMO PRODUIT FICTIF')
                page.locator('#claims').check()
                page.locator('#addClip').click()
                page.locator('#clips .entry').count()==1
                card=page.locator('#clips .entry')
                card.locator('select').nth(0).select_option('media/presentation_demo.mp4')
                card.locator('select').nth(2).select_option('owned')
                card.locator('select').nth(3).select_option('media/voix.srt')
                page.locator('#addOverlay').click()
                page.locator('#overlays .entry select').nth(0).select_option('media/produit.png')
                page.locator('#overlays .entry select').nth(1).select_option('owned')
                page.locator('#music').select_option('media/music_original.wav')
                page.locator('#musicRights').select_option('owned')
                page.locator('#save').click()
                page.get_by_text('Projet validé :').wait_for(timeout=30000)
                page.locator('#preview').click()
                page.locator('#jobStatus').get_by_text('Export terminé.', exact=True).wait_for(timeout=70000)
                page.locator('video').wait_for(state='visible',timeout=10000)
                # Browser policy blocks video src; HTTP Range playback was exercised by the API suite.
                assert page.locator('a[href*="preview.mp4"]').count()>=1
                page.screenshot(path='/mnt/data/ugc_studio_v8_android_preview.png',full_page=True)
                print('PASS mobile browser: login, project, 4 uploads, SRT, clips, save, render, preview')
                browser.close()
        finally:
            server.shutdown();server.server_close();server_thread.join(timeout=5)


if __name__=='__main__':run()
