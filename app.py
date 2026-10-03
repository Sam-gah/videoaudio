"""Private offline editor handoff. Python 3.10+, no web framework required."""
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
import argparse
import concurrent.futures
import hashlib
import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import site

site.addsitedir(str(Path(__file__).resolve().parent / 'vendor'))

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / 'projects'
VIDEO = {'.mp4', '.mov', '.mxf', '.mkv', '.avi', '.m4v'}
AUDIO = {'.wav', '.m4a', '.mp3', '.aac', '.flac', '.aiff', '.aif', '.ogg'}
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.RLock()
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)
JOBS = []


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def client_dir(key):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,70}', key):
        raise ValueError('Invalid client identifier')
    p = PROJECTS / key
    if not (p / 'project.json').exists():
        raise ValueError('Client not found')
    return p.resolve()


def within(base, relative):
    p = (base / relative).resolve()
    if not p.is_relative_to(base.resolve()):
        raise ValueError('Path outside project')
    return p


def create_client(name, key=None):
    name = str(name).strip()[:100]
    if not name:
        raise ValueError('Enter a client name')
    key = key or (re.sub('[^a-z0-9]+', '-', name.lower()).strip('-')[:50] or 'client') + '-' + uuid.uuid4().hex[:6]
    p = PROJECTS / key
    if p.exists():
        raise ValueError('Client already exists')
    for kind in ('video', 'audio', 'final', 'reports'):
        (p / kind).mkdir(parents=True)
    write_json(p / 'project.json', {'id': key, 'name': name, 'clips': {}, 'note': ''})
    return key


def ffmpeg():
    configured = read_json(ROOT / 'settings.json', {}).get('ffmpeg', '')
    options = [configured, str(ROOT / 'tools/ffmpeg.exe'), str(ROOT / 'tools/ffmpeg')]
    if sys.platform == 'darwin' and os.uname().machine == 'arm64':
        options.append(str(ROOT / 'tools/ffmpeg-mac-arm64'))
    options.append(shutil.which('ffmpeg') or '')
    try:
        import imageio_ffmpeg
        options.append(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError,RuntimeError):
        pass
    for path in options:
        if path and Path(path).is_file():
            return str(Path(path).resolve())
    raise ValueError('FFmpeg is missing. Set its executable path in Settings.')


def run_ff(args, timeout=3600):
    result = subprocess.run([ffmpeg(), '-hide_banner', '-nostdin', *map(str, args)],
                            capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-2400:])
    return result


def probe(path):
    # FFmpeg is bundled; no separate ffprobe installation needed.
    p = subprocess.run([ffmpeg(), '-hide_banner', '-nostdin', '-i', str(path)],
                       capture_output=True, timeout=45)
    log = p.stderr.decode(errors='replace')
    m = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', log)
    if not m:
        raise ValueError('Cannot read duration: ' + path.name)
    duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    return {'duration': duration, 'audio': bool(re.search(r'Stream .*Audio:', log)),
            'video': bool(re.search(r'Stream .*Video:', log))}


def media_list(p, kind):
    extensions = AUDIO if kind == 'audio' else VIDEO
    items = []
    for f in sorted((p / kind).rglob('*')):
        if f.is_file() and not f.name.startswith('.') and f.suffix.lower() in extensions:
            items.append({'name': f.name, 'path': f.relative_to(p).as_posix(), 'bytes': f.stat().st_size})
    return items


def catalog():
    clients = []
    for p in sorted(PROJECTS.glob('*')):
        if not (p / 'project.json').is_file():
            continue
        data = read_json(p / 'project.json')
        data['media'] = {kind: media_list(p, kind) for kind in ('video', 'audio', 'final')}
        clients.append(data)
    try:
        executable = ffmpeg()
    except ValueError:
        executable = ''
    return {'clients': clients, 'ffmpeg': executable, 'free_bytes': shutil.disk_usage(ROOT).free,
            'jobs': list(JOBS), 'token': TOKEN, 'root': str(ROOT)}


def snapshot_file():
    data = catalog()
    for key in ('token', 'ffmpeg', 'root', 'jobs'):
        data.pop(key, None)
    # External JS allows a useful read-only file:// version without fetch restrictions.
    (ROOT / 'catalog.js').write_text('window.OFFLINE_CATALOG = ' + json.dumps(data, ensure_ascii=True) + ';\n', encoding='utf-8')


def update(job, stage, progress=None):
    with LOCK:
        job['stage'] = stage
        if progress is not None:
            job['progress'] = progress


def enqueue(label, function, *args):
    signature=hashlib.sha256((label+json.dumps(args,sort_keys=True)).encode()).hexdigest()
    with LOCK:
        for previous in JOBS:
            if previous.get('signature')==signature and previous['status'] in ('queued','running'):
                return previous
        job = {'id': uuid.uuid4().hex[:12], 'label': label, 'status': 'queued', 'stage': 'Waiting', 'progress': 0,
               'signature':signature,'client':args[0] if args else '', 'video':args[1] if len(args)>1 and isinstance(args[1],str) else ''}
        JOBS.append(job)
    def task():
        try:
            job['status'] = 'running'
            job['result'] = function(job, *args)
            job.update(status='done', stage='Complete', progress=100)
            with LOCK:
                snapshot_file()
        except Exception as exc:
            job.update(status='error', stage=str(exc), progress=0)
    POOL.submit(task)
    return job


def clone_copy(source, dest):
    if dest.exists():
        raise ValueError('Destination already exists: ' + str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'darwin':
        p = subprocess.run(['/bin/cp', '-c', str(source), str(dest)], capture_output=True)
        if p.returncode == 0:
            return
    shutil.copy2(source, dest)


def import_media(job, key, folders):
    p = client_dir(key)
    plan = []
    for kind in ('video', 'audio'):
        value = str(folders.get(kind, '')).strip()
        if not value:
            continue
        source = Path(value).expanduser().resolve()
        if not source.is_dir():
            raise ValueError('Folder not found: ' + str(source))
        if source == Path(source.anchor) or source == Path.home().resolve() or source == ROOT.resolve() or source.is_relative_to(ROOT.resolve()):
            raise ValueError('Choose a source-media folder outside Editor_Desk, not a whole drive or home folder.')
        allowed = VIDEO | {'.xml'} if kind == 'video' else AUDIO
        for f in sorted(source.rglob('*')):
            if f.is_file() and not any(part.startswith('.') for part in f.relative_to(source).parts) and f.suffix.lower() in allowed:
                target = p / kind / f.relative_to(source)
                if target.exists():
                    raise ValueError('Import would overwrite ' + target.name + '. Use a different client or remove it from the import selection.')
                plan.append((f, target))
    if not plan:
        raise ValueError('No supported media found in those folders')
    total = sum(f.stat().st_size for f, _ in plan)
    if total + 512 * 1024**2 > shutil.disk_usage(ROOT).free:
        raise ValueError('Not enough free space for a complete import. Put Editor_Desk on a larger drive first.')
    for i, (source, dest) in enumerate(plan):
        update(job, 'Copying ' + source.name, round(i * 100 / len(plan)))
        clone_copy(source, dest)
    return {'files': len(plan), 'bytes': total}


def save_clip(key, relative, settings):
    p = client_dir(key)
    source = within(p, relative)
    if not source.is_file() or not relative.startswith('video/'):
        raise ValueError('Select a camera video')
    fields = {'profile', 'rotation', 'audio', 'offset', 'start', 'end', 'status', 'note', 'camera_fallback'}
    clean = {k: v for k, v in settings.items() if k in fields}
    for field in ('start', 'end', 'offset'):
        if field in clean:
            clean[field] = float(clean[field])
            if not math.isfinite(clean[field]):
                raise ValueError('Time values must be finite numbers')
    with LOCK:
        data = read_json(p / 'project.json')
        data['clips'].setdefault(relative, {}).update(clean)
        write_json(p / 'project.json', data)
        snapshot_file()


def clip_settings(key, relative, frozen=None):
    p = client_dir(key)
    source = within(p, relative)
    if not source.is_file() or not relative.startswith('video/'):
        raise ValueError('Select a camera video')
    data = frozen if frozen is not None else read_json(p / 'project.json')['clips'].get(relative, {})
    info = probe(source)
    start = float(data.get('start', 0))
    end = float(data.get('end') or info['duration'])
    offset = float(data.get('offset', 0))
    if not all(math.isfinite(x) for x in (start, end, offset)) or not 0 <= start < end <= info['duration'] + .03:
        raise ValueError('Camera in/out times are outside the clip')
    profile = data.get('profile', 'unconfirmed')
    if profile not in ('trudent-slog3', 'rec709'):
        raise ValueError('Confirm the input profile before preparing a clip')
    if data.get('rotation', 'none') not in ('none', 'clock', 'cclock', '180'):
        raise ValueError('Invalid rotation')
    return p, source, data, start, end, offset


def picture_filters(data, preview=False):
    result = []
    if data.get('profile') == 'trudent-slog3':
        # Work relative to ROOT so spaces in the application path do not break LUT syntax.
        result += ['scale=in_range=full:in_color_matrix=bt709:out_range=full', 'format=gbrp16le',
                   "lut3d=file='assets/approved_trudent.cube':interp=tetrahedral"]
    rotation = data.get('rotation', 'none')
    if rotation in ('clock', 'cclock'):
        result.append('transpose=' + rotation)
    elif rotation == '180':
        result += ['hflip', 'vflip']
    size = 960 if preview else 1920
    result.append(f"scale=w='if(gte(iw,ih),min(iw,{size}),-2)':h='if(gte(iw,ih),-2,min(ih,{size}))':flags=lanczos")
    if data.get('profile') == 'trudent-slog3':
        result.append('scale=in_range=full:out_range=tv:out_color_matrix=bt709')
    result += ['format=yuv420p', 'setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709']
    return ','.join(result)


def new_output(p, source):
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', source.stem)[:70]
    out = p / 'final' / (name + '_' + time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:4])
    out.mkdir(parents=True)
    return out


def prepare(job, key, relative, preview=False, frozen=None):
    p, source, data, start, end, offset = clip_settings(key, relative, frozen)
    if shutil.disk_usage(ROOT).free < (end - start) * 5_000_000 + 512 * 1024**2:
        raise ValueError('Not enough free space for this export')
    out = new_output(p, source)
    if preview:
        update(job, 'Rendering grade preview', 30)
        image = out / 'grade_preview.jpg'
        run_ff(['-v', 'error', '-ss', start + min(1, (end-start)/2), '-i', source,
                '-vf', picture_filters(data, True), '-frames:v', 1, '-q:v', 2, '-n', image])
        return {'preview': image.relative_to(p).as_posix(), 'client': key}
    fallback = bool(data.get('camera_fallback', False))
    audio_relative = data.get('audio', '')
    if fallback:
        audio_source, audio_start = source, start
    elif audio_relative and audio_relative.startswith('audio/'):
        audio_source, audio_start = within(p, audio_relative), start + offset
    else:
        raise ValueError('Select a separate recording, or explicitly choose camera-audio fallback')
    ai = probe(audio_source)
    duration = end - start
    if not ai['audio']:
        raise ValueError('Selected source has no audio track')
    if audio_start < -.001 or audio_start + duration > ai['duration'] + .03:
        raise ValueError('The chosen recording does not cover this camera in/out interval. Trim to its overlap or choose another recording.')
    name = source.stem
    clean = p / 'audio' / (out.name + '_clean_dialogue.wav')
    update(job, 'Measuring dialogue loudness', 12)
    trim = f'atrim=start={max(0,audio_start)}:duration={duration},asetpts=PTS-STARTPTS,aresample=48000'
    # Downmix to mono explicitly. Gentle default, not aggressive speech reconstruction.
    cleanup = 'highpass=f=70,afftdn=nr=5:nf=-55:tn=0:gs=6,acompressor=threshold=0.20:ratio=2:attack=10:release=180:knee=2.828:makeup=1'
    base = trim + ',' + cleanup
    measured_log = run_ff(['-i', audio_source, '-ac', 1, '-af', base + ',loudnorm=I=-16:TP=-1.7:LRA=11:print_format=json', '-f', 'null', '-']).stderr.decode(errors='replace')
    measurements = re.findall(r'\{\s*"input_i".*?\}', measured_log, re.S)
    if not measurements:
        raise ValueError('Loudness analysis failed')
    measured = json.loads(measurements[-1])
    if any(not math.isfinite(float(measured[k])) for k in ('input_i','input_tp','input_lra','input_thresh')):
        raise ValueError('Recording is silent or loudness cannot be measured')
    dynamic = float(measured['input_lra']) > 11 or float(measured['input_tp']) - 16 - float(measured['input_i']) > -1.7
    correction = measured['target_offset'] if dynamic else '0'
    loudnorm = f"loudnorm=I=-16:TP=-1.7:LRA=11:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:offset={correction}:linear=true"
    filters = base + ',' + loudnorm + f',atrim=start=0.025,asetpts=PTS-STARTPTS,apad=pad_dur=0.025,atrim=duration={duration},afade=t=in:d=0.015,afade=t=out:st={max(0,duration-.12)}:d=0.12'
    update(job, 'Cleaning and aligning audio', 35)
    run_ff(['-v','error','-i',audio_source,'-map','0:a:0','-ac',1,'-af',filters,'-ar',48000,'-c:a','pcm_s24le','-n',clean])
    update(job, 'Encoding 1080p prepared video', 55)
    target = out / (name + '_prepared_1080p.mp4')
    run_ff(['-v','error','-ss',start,'-i',source,'-i',clean,'-map','0:v:0','-map','1:a:0','-t',duration,
            '-vf',picture_filters(data),'-c:v','libx264','-crf',17,'-preset','fast',
            '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
            '-c:a','aac','-b:a','320k','-ar',48000,'-map_metadata','-1','-movflags','+faststart','-n',target])
    update(job, 'Checking exported streams', 92)
    run_ff(['-v','error','-i',target,'-map','0:v:0','-map','0:a:0','-f','null','-'])
    metadata = {'source': relative, 'settings': data, 'camera_range':[start,end], 'audio_start':audio_start,
                'camera_audio_fallback':fallback, 'loudness_input':measured,
                'clean_audio':clean.relative_to(p).as_posix(), 'output':target.relative_to(p).as_posix(),
                'verification':'Full stream decode passed. Human lip-sync, grade and dialogue approval still required.'}
    write_json(out / 'PREPARATION.json', metadata)
    with LOCK:
        project = read_json(p / 'project.json')
        project['clips'].setdefault(relative, {}).update(final=metadata['output'], clean_audio=metadata['clean_audio'],
            qa=(out/'PREPARATION.json').relative_to(p).as_posix(), status='review', camera_fallback=fallback)
        write_json(p / 'project.json', project)
    return {'output':metadata['output'], 'client':key}


def find_audio(job, key, relative):
    try:
        import numpy as np
        from scipy import signal
        from scipy.fft import rfft, irfft, next_fast_len
    except ImportError:
        raise ValueError('Automatic matching needs numpy/scipy. Install requirements.txt, or set a recording and offset manually.')
    p = client_dir(key)
    source = within(p, relative)
    if not relative.startswith('video/') or not source.is_file():
        raise ValueError('Select a camera video')
    recordings = [within(p, a['path']) for a in media_list(p, 'audio') if not a['name'].endswith('_clean_dialogue.wav')]
    if not recordings:
        raise ValueError('No original separate recordings in this client')
    def features(path):
        signature = str(path.relative_to(p)) + str(path.stat().st_size) + str(path.stat().st_mtime_ns)
        cache = p / 'reports' / 'cache' / (hashlib.sha256(signature.encode()).hexdigest() + '.npz')
        if cache.exists():
            with np.load(cache) as z:
                return z['features'], float(z['duration'])
        # Limit single recordings to 30 minutes to bound memory. Split longer takes first.
        raw = run_ff(['-v','error','-i',path,'-t',1800,'-map','0:a:0','-ac',1,'-ar',8000,'-f','f32le','-'], timeout=180).stdout
        samples = np.frombuffer(raw, dtype='<f4')
        if len(samples) < 8000:
            raise ValueError('Not enough usable scratch audio in ' + path.name)
        freq, _, spec = signal.stft(samples, fs=8000, nperseg=512, noverlap=352, boundary=None, padded=False)
        power = abs(spec)**2
        bands=[]
        for lo,hi in zip(np.geomspace(110,3800,33)[:-1],np.geomspace(110,3800,33)[1:]):
            indices=np.flatnonzero((freq>=lo)&(freq<hi))
            if not len(indices): indices=np.array([np.argmin(abs(freq-(lo+hi)/2))])
            bands.append(np.log(1e-10+power[indices].mean(axis=0)))
        x=np.stack(bands,axis=1)
        x-=signal.convolve2d(x,np.ones((51,1))/51,mode='same',boundary='symm')
        x/=np.maximum(x.std(axis=0),.35)
        x=np.clip(x,-3,3)
        x/=np.maximum(np.linalg.norm(x,axis=1,keepdims=True),1e-7)
        x=x.astype(np.float32)
        cache.parent.mkdir(exist_ok=True)
        np.savez_compressed(cache,features=x,duration=len(samples)/8000)
        return x,len(samples)/8000
    update(job,'Reading camera scratch audio',5)
    x,vd=features(source)
    ranked=[]
    errors=[]
    for i,path in enumerate(recordings):
        update(job,'Comparing '+path.name,round(10+80*i/len(recordings)))
        try:
            y,ad=features(path)
            if min(len(x),len(y)) < 50: continue
            size=next_fast_len(len(x)+len(y)-1)
            corr=irfft((rfft(x[::-1],size,axis=0)*rfft(y,size,axis=0)).sum(axis=1),size)[:len(x)+len(y)-1]
            lags=np.arange(-len(x)+1,len(y))
            overlap=np.minimum(len(y),lags+len(x))-np.maximum(0,lags)
            score=corr/np.maximum(overlap,1)
            score[overlap<min(len(x),250)]=-1
            k=int(np.argmax(score));offset=float(lags[k]*.02)
            ranked.append({'audio':path.relative_to(p).as_posix(),'name':path.name,'score':float(score[k]),
                           'offset':offset,'coverage_start':max(0,-offset),'coverage_end':min(vd,ad-offset),
                           'camera_duration':vd,'audio_duration':ad,'approval':'Candidate only. Confirm by listening.'})
        except Exception as exc:
            errors.append({'file':path.name,'error':str(exc)[:250]})
    ranked.sort(key=lambda r:r['score'],reverse=True)
    report={'video':relative,'candidates':ranked[:5],'skipped':errors,'analysis_limit_seconds':1800}
    write_json(p/'reports'/(hashlib.sha256(relative.encode()).hexdigest()[:16]+'_candidates.json'),report)
    return report


class Handler(BaseHTTPRequestHandler):
    def valid_host(self):
        return self.headers.get('Host','') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}

    def send_json(self, data, status=200):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.valid_host():
            self.send_error(403); return
        path=unquote(urlparse(self.path).path)
        try:
            if path=='/api/catalog':
                with LOCK: self.send_json(catalog())
                return
            if path=='/api/refresh':
                with LOCK: snapshot_file(); self.send_json(catalog())
                return
            if path.startswith('/projects/'):
                f=within(PROJECTS,path.removeprefix('/projects/'))
                if f.suffix.lower() not in VIDEO|AUDIO|{'.jpg','.png','.json','.md','.cube'}:
                    self.send_error(403); return
            else:
                if path not in ('/','/index.html','/style.css','/app.js','/catalog.js','/drive_inventory.js','/README.md','/favicon.ico'):
                    self.send_error(404); return
                f=ROOT/('index.html' if path=='/' else path.lstrip('/'))
            if not f.is_file():
                self.send_error(404); return
            size=f.stat().st_size; start=0; end=size-1
            header=self.headers.get('Range','')
            if header:
                m=re.fullmatch(r'bytes=(\d*)-(\d*)',header)
                if not m or not any(m.groups()):
                    self.send_error(416); return
                if m[1]: start=int(m[1]); end=min(end,int(m[2])) if m[2] else end
                else: start=max(0,size-int(m[2]))
                if start>end or start>=size:
                    self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.end_headers(); return
            self.send_response(206 if header else 200)
            self.send_header('Content-Type',mimetypes.guess_type(str(f))[0] or 'application/octet-stream')
            self.send_header('Accept-Ranges','bytes')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(end-start+1))
            if header: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            with f.open('rb') as file:
                file.seek(start); remaining=end-start+1
                while remaining:
                    block=file.read(min(256*1024,remaining))
                    if not block: break
                    self.wfile.write(block); remaining-=len(block)
        except (BrokenPipeError,ConnectionResetError):
            pass
        except (ValueError,OSError) as exc:
            self.send_json({'error':str(exc)},400)

    def do_POST(self):
        origin=self.headers.get('Origin','')
        allowed={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
        if not self.valid_host() or (origin and origin not in allowed) or self.headers.get('X-Editor-Token') != TOKEN:
            self.send_json({'error':'Local session authorization failed. Reload the app.'},403); return
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0 < length <= 65536: raise ValueError('Invalid request size')
            data=json.loads(self.rfile.read(length))
            path=urlparse(self.path).path
            if path=='/api/client':
                key=create_client(data['name']); snapshot_file(); result={'id':key}
            elif path=='/api/rename':
                p=client_dir(data['client']); name=str(data['name']).strip()[:100]
                if not name: raise ValueError('Enter a client name')
                with LOCK:
                    project=read_json(p/'project.json'); project['name']=name; write_json(p/'project.json',project); snapshot_file()
                result={'ok':True}
            elif path=='/api/settings':
                candidate=Path(data['ffmpeg']).expanduser().resolve()
                if not candidate.is_file(): raise ValueError('FFmpeg executable not found')
                subprocess.run([str(candidate),'-version'],capture_output=True,check=True,timeout=10)
                write_json(ROOT/'settings.json',{'ffmpeg':str(candidate)}); result={'ok':True}
            elif path=='/api/browse':
                picked=subprocess.run([sys.executable,str(ROOT/'app.py'),'--pick-folder'],capture_output=True,text=True,timeout=600)
                if picked.returncode: raise ValueError('Folder picker unavailable. Paste the folder path instead. '+picked.stderr[-150:])
                result={'path':picked.stdout.strip()}
            elif path=='/api/save':
                save_clip(data['client'],data['video'],data['settings']); result={'ok':True}
            elif path=='/api/import':
                client_dir(data['client']); result=enqueue('Import media',import_media,data['client'],data)
            elif path in ('/api/prepare','/api/preview'):
                p=client_dir(data['client'])
                frozen=read_json(p/'project.json')['clips'].get(data['video'],{})
                result=enqueue('Grade preview' if path.endswith('preview') else 'Prepare clip',prepare,data['client'],data['video'],path.endswith('preview'),frozen)
            elif path=='/api/match':
                result=enqueue('Find audio candidates',find_audio,data['client'],data['video'])
            else:
                raise ValueError('Unknown action')
            self.send_json(result)
        except (ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:
            self.send_json({'error':str(exc)},400)

    def log_message(self, fmt, *args):
        if '/api/catalog' not in self.path:
            super().log_message(fmt,*args)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--pick-folder',action='store_true')
    args=parser.parse_args()
    if args.pick_folder:
        import tkinter as tk
        from tkinter import filedialog
        picker=tk.Tk(); picker.withdraw(); picker.attributes('-topmost',True)
        chosen=filedialog.askdirectory(title='Choose source media folder')
        picker.destroy(); print(chosen); return
    os.chdir(ROOT)
    PROJECTS.mkdir(exist_ok=True)
    if not list(PROJECTS.glob('*/project.json')):
        create_client('My first client','client-1')
    snapshot_file()
    server=None
    for port in range(args.port,args.port+20):
        try:
            server=ThreadingHTTPServer(('127.0.0.1',port),Handler); break
        except PermissionError:
            raise SystemExit('Local server permission denied. Run this app from your normal terminal.')
        except OSError:
            continue
    if not server: raise SystemExit('No free local port found')
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'Editor Desk: {url}\nKeep this window open. Ctrl+C stops the app.',flush=True)
    if not args.no_browser: webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping. Waiting for any current job to finish.',flush=True)
    finally:
        server.server_close(); POOL.shutdown(wait=True)


if __name__=='__main__':
    main()
