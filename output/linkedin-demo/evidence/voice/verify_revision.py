from pathlib import Path
import json,subprocess,hashlib
import cv2,numpy as np
from PIL import Image
OUT=Path(__file__).resolve().parents[2];video=OUT/'ParkinSense-PK-Voice-Captions.mp4'
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(video)]))
v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
assert v['codec_name']=='h264' and a['codec_name']=='aac'
assert (v['width'],v['height'])==(1080,1350) and int(v['nb_frames'])==2208
assert abs(float(v['duration'])-92)<.05 and abs(float(a['duration'])-92)<.05
subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],check=True)
audio=np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(video),'-vn','-ac','1','-ar','16000','-f','f32le','-']),dtype='<f4')
scenes=json.loads((OUT/'storyboard.json').read_text());sound=[]
for s in scenes:
 clip=audio[int(s['start_s']*16000):int(s['end_s']*16000)]
 rms=float(np.sqrt(np.mean(clip**2)));assert rms>.01
 sound.append({'scene':s['title'],'rms_dbfs':round(float(20*np.log10(rms)),2),'active_sample_fraction':round(float(np.mean(np.abs(clip)>.005)),3)})
cap=cv2.VideoCapture(str(video));shots=[]
for i,t in enumerate([2,11,23,37,51,62,72,81,88]):
 cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read();assert ok
 crop=frame[1080:1200,85:995];white=np.all(crop>210,axis=2);assert int(white.sum())>600
 im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));im.save(OUT/f'evidence/voice/final-scene-{i+1:02d}.jpg',quality=94);shots.append(im.resize((360,450)))
cap.release();sheet=Image.new('RGB',(1080,1350),'white')
for i,im in enumerate(shots):sheet.paste(im,((i%3)*360,(i//3)*450))
sheet.save(OUT/'evidence/voice/final-contact-sheet.jpg',quality=95)
r={'file':video.name,'duration_seconds':float(v['duration']),'audio_codec':a['codec_name'],'sample_rate':int(a['sample_rate']),'audio_duration_seconds':float(a['duration']),'video_codec':v['codec_name'],'frames':int(v['nb_frames']),'full_decode_passed':True,'speech_signal_present_in_all_nine_scenes':True,'burned_caption_pixels_present_in_all_nine_samples':True,'audio_per_scene':sound,'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'bytes':video.stat().st_size}
(OUT/'evidence/voice/revision-verification.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
