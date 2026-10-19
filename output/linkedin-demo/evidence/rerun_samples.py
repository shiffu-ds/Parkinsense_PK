from pathlib import Path
import sys,json,time,hashlib
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from ml.vision.pipeline import analyze_video
from ml.audio import analyze_audio
from app.components.public_demo import load_demo_clips
out=Path(__file__).parent
clips=load_demo_clips();rows=[]
for clip in [clips[1],clips[2]]:
 t=time.perf_counter();r=analyze_video(clip['path'],clip['task']);(out/(clip['id']+'.json')).write_text(json.dumps(r,indent=2,allow_nan=False));rows.append({'id':clip['id'],'accepted':r['quality']['accepted'],'elapsed_s':round(time.perf_counter()-t,2),'sha256':clip['sha256']});print(rows[-1],flush=True)
p=ROOT/'artifacts/project-audit-2026-10-18/real-media/pd-reading-30-60s.wav'
r=analyze_audio(p,'English','sentence');(out/'voice.json').write_text(json.dumps(r,indent=2,allow_nan=False));rows.append({'id':'mdvr-pd-reading-30-60s','accepted':r['quality']['accepted'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()});(out/'rerun-summary.json').write_text(json.dumps(rows,indent=2));print(rows[-1],flush=True)
