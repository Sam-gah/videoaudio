"""Isolated safety, import, matching, preparation and HTTP tests."""
from pathlib import Path
import contextlib
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import app


class DeskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='editor-desk-test-')
        cls.original=(app.ROOT,app.PROJECTS,os.getcwd())
        cls.engine=app.ffmpeg()
        cls.original_lut=app.ROOT/'assets/approved_trudent.cube'
        app.ROOT=(Path(cls.temp.name)/'desk').resolve();app.ROOT.mkdir()
        app.PROJECTS=app.ROOT/'projects';app.PROJECTS.mkdir()
        (app.ROOT/'assets').mkdir();shutil.copy2(cls.original_lut,app.ROOT/'assets/approved_trudent.cube')
        app.write_json(app.ROOT/'settings.json',{'ffmpeg':cls.engine})
        os.chdir(app.ROOT)
        app.create_client('Test client','test')
        cls.p=app.PROJECTS/'test'
        # Short deterministic fixture, camera audio appears one second later in recording.
        app.run_ff(['-v','error','-f','lavfi','-i','testsrc2=s=192x108:r=25:d=2',
                    '-f','lavfi','-i','aevalsrc=0.08*sin(2*PI*(400+100*t)*t):s=48000:d=2',
                    '-c:v','libx264','-pix_fmt','yuv420p','-c:a','pcm_s16le','-n',cls.p/'video/test.mov'])
        app.run_ff(['-v','error','-i',cls.p/'video/test.mov','-map','0:a:0','-af','adelay=1000:all=1',
                    '-c:a','pcm_s16le','-n',cls.p/'audio/recording.wav'])

    @classmethod
    def tearDownClass(cls):
        app.ROOT,app.PROJECTS,cwd=cls.original;os.chdir(cwd);cls.temp.cleanup()

    def test_01_catalog_and_safety(self):
        data=app.catalog();self.assertEqual(data['clients'][0]['media']['video'][0]['name'],'test.mov')
        self.assertRaises(ValueError,app.within,self.p,'../../outside')
        self.assertRaises(ValueError,app.client_dir,'../x')
        self.assertRaises(ValueError,app.create_client,'')

    def test_02_copy_import_and_no_overwrite(self):
        source=Path(self.temp.name)/'incoming';source.mkdir();(source/'speech.wav').write_bytes(b'fixture')
        result=app.import_media({},'test',{'audio':str(source)})
        self.assertEqual(result['files'],1);self.assertTrue((source/'speech.wav').exists())
        self.assertRaises(ValueError,app.import_media,{},'test',{'audio':str(source)})
        self.assertRaises(ValueError,app.import_media,{},'test',{'audio':str(app.ROOT)})
        # Keep an intentionally invalid audio source: matching must skip, not fail the whole job.

    def test_03_match_offset(self):
        report=app.find_audio({},'test','video/test.mov')
        self.assertTrue(report['candidates'])
        best=report['candidates'][0];self.assertEqual(best['name'],'recording.wav')
        self.assertAlmostEqual(best['offset'],1,delta=.04)
        self.assertTrue(report['skipped'])

    def test_04_profile_coverage_preview_and_render(self):
        self.assertRaises(ValueError,app.clip_settings,'test','video/test.mov')
        app.save_clip('test','video/test.mov',{'audio':'audio/recording.wav','offset':1,'start':0,'end':2,'profile':'trudent-slog3','rotation':'clock','note':'Test only'})
        result=app.prepare({},'test','video/test.mov',True)
        self.assertTrue((self.p/result['preview']).exists())
        output=app.prepare({},'test','video/test.mov')
        self.assertTrue((self.p/output['output']).exists())
        info=app.probe(self.p/output['output']);self.assertTrue(info['audio']);self.assertAlmostEqual(info['duration'],2,delta=.03)
        app.save_clip('test','video/test.mov',{'offset':2})
        self.assertRaises(ValueError,app.prepare,{},'test','video/test.mov')
        app.save_clip('test','video/test.mov',{'offset':1})

    def test_05_http_range_auth_and_traversal(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base+'/api/catalog') as response:
                self.assertIn('clients',json.load(response))
            req=urllib.request.Request(base+'/projects/test/video/test.mov',headers={'Range':'bytes=0-99'})
            with urllib.request.urlopen(req) as response:
                self.assertEqual(response.status,206);self.assertEqual(len(response.read()),100)
            req=urllib.request.Request(base+'/projects/test/video/test.mov',headers={'Range':'bytes=999999999-'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
            self.assertEqual(error.exception.code,416)
            req=urllib.request.Request(base+'/api/client',data=b'{"name":"Unauthorized"}',headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
            self.assertEqual(error.exception.code,403)
            req=urllib.request.Request(base+'/api/client',data=b'{"name":"Authorized"}',headers={'Content-Type':'application/json','X-Editor-Token':app.TOKEN,'Origin':base})
            with urllib.request.urlopen(req) as response:self.assertIn('id',json.load(response))
            req=urllib.request.Request(base+'/api/client',data=b'{"name":"Evil origin"}',headers={'X-Editor-Token':app.TOKEN,'Origin':'https://example.com'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
            self.assertEqual(error.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'/projects/%2e%2e/app.py')
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_06_queue_deduplication(self):
        released=threading.Event()
        def wait_job(job,key,path):
            released.wait(3)
            return {'ok':True}
        try:
            first=app.enqueue('Test duplicate',wait_job,'test','video/test.mov')
            second=app.enqueue('Test duplicate',wait_job,'test','video/test.mov')
            self.assertEqual(first['id'],second['id'])
        finally:
            released.set()
        # Join queued work before the temporary project is removed.
        app.POOL.submit(lambda:None).result(timeout=5)

    def test_07_queued_settings_are_frozen(self):
        frozen={'start':0,'end':2,'offset':1,'profile':'trudent-slog3','rotation':'clock'}
        app.save_clip('test','video/test.mov',{'profile':'rec709'})
        self.assertEqual(app.clip_settings('test','video/test.mov',frozen)[2]['profile'],'trudent-slog3')
        self.assertEqual(app.clip_settings('test','video/test.mov')[2]['profile'],'rec709')


if __name__=='__main__':unittest.main(verbosity=2)
