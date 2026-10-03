"""Read-only manifest of the user's scoped production folder, no media decoding."""
from pathlib import Path
from collections import Counter
import json
import os
import time
import argparse

ROOT=Path(__file__).resolve().parent
SOURCE=Path('/Volumes/Transcend/production bichitras')
VIDEO={'.mp4','.mov','.mxf','.mkv','.avi','.m4v'}
AUDIO={'.wav','.m4a','.mp3','.flac','.aac','.aif','.aiff','.ogg'}
PHOTO={'.jpg','.jpeg','.png','.arw','.cr2','.nef','.dng','.heic'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder',nargs='?',default=str(SOURCE));args=parser.parse_args()
    source=Path(args.folder).expanduser().resolve()
    if not source.is_dir():raise SystemExit('Production source folder not available')
    files=[];groups={};errors=[]
    def fail(error):errors.append(str(error))
    for directory,dirs,names in os.walk(source,onerror=fail):
        dirs[:]=[d for d in dirs if not d.startswith('.')]
        for name in names:
            if name.startswith('.'):continue
            f=Path(directory)/name;suffix=f.suffix.lower()
            kind='video' if suffix in VIDEO else 'audio' if suffix in AUDIO else 'photo' if suffix in PHOTO else 'other'
            try:stat=f.stat()
            except OSError as exc:errors.append(str(exc));continue
            relative=f.relative_to(source).as_posix();group=relative.split('/')[0]
            g=groups.setdefault(group,{'name':group,'video':0,'audio':0,'photo':0,'other':0,'bytes':0})
            g[kind]+=1;g['bytes']+=stat.st_size
            files.append({'path':relative,'name':name,'kind':kind,'bytes':stat.st_size})
    counts=Counter(f['kind'] for f in files)
    repeated=Counter(f['name'].lower() for f in files if f['kind']=='video')
    report={'folder_name':'production bichitras','scanned_at':time.strftime('%Y-%m-%d %H:%M:%S'),
            'source_mount':'Transcend','counts':dict(counts),'total_bytes':sum(f['bytes'] for f in files),
            'groups':sorted(groups.values(),key=lambda g:g['name'].lower()),'files':sorted(files,key=lambda f:f['path'].lower()),
            'duplicate_video_names':{name:n for name,n in repeated.items() if n>1},'errors':errors,
            'status':'Inventory only. Six Trudent clips were prepared previously; remaining files are not color graded, audio matched or approved. Counts are file counts, not content-deduplicated takes.'}
    (ROOT/'drive_inventory.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    summary={k:report[k] for k in ('folder_name','scanned_at','source_mount','counts','total_bytes','groups','status')}
    (ROOT/'drive_inventory.js').write_text('window.DRIVE_INVENTORY = '+json.dumps(summary,ensure_ascii=True)+';\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('counts','total_bytes','groups','errors')},indent=2),flush=True)


if __name__=='__main__':main()
