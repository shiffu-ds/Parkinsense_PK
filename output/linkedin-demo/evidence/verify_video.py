from pathlib import Path
import subprocess,json,hashlib
import cv2
from PIL import Image
p=Path(__file__).resolve().parents[1];video=p/'ParkinSense-PK-Testing-Demo.mp4'
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
s=next(x for x in probe['streams'] if x['codec_type']=='video')
assert (s['width'],s['height'],s['pix_fmt'],s['codec_name'])==(1080,1350,'yuv420p','h264')
assert abs(float(probe['format']['duration'])-92)<.1
assert int(s['nb_frames'])==2208
subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True)
cap=cv2.VideoCapture(str(video));shots=[]
for i,t in enumerate([3,12,25,39,52,63,73,82,89]):
 cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read();assert ok
 im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));im.save(p/f'evidence/decoded-{i+1:02d}.jpg',quality=90);shots.append(im.resize((270,338)))
cap.release();sheet=Image.new('RGB',(810,1014),'white')
for i,im in enumerate(shots):sheet.paste(im,((i%3)*270,(i//3)*338))
sheet.save(p/'evidence/decoded-contact-sheet.jpg',quality=94)
r={'file':video.name,'duration_seconds':float(probe['format']['duration']),'width':s['width'],'height':s['height'],'fps':s['r_frame_rate'],'frames':int(s['nb_frames']),'codec':s['codec_name'],'pixel_format':s['pix_fmt'],'bytes':video.stat().st_size,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'full_decode_passed':True,'sampled_scene_frames':len(shots),'silent':not any(x['codec_type']=='audio' for x in probe['streams']),'note':'Edited output visualization; not a live screen recording. Full suite figure is historical; three media examples were rerun.'}
(p/'evidence/video-verification.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
