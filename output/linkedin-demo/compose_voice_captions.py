from pathlib import Path
import json,subprocess,wave
import numpy as np
from PIL import ImageFont
OUT=Path(__file__).resolve().parent;E=OUT/'evidence/voice';SR=48000
scenes=json.loads((OUT/'storyboard.json').read_text());narration=json.loads((E/'narration.json').read_text())
track=np.zeros(92*SR,dtype=np.int16);captions=[];metrics=[]
font=ImageFont.truetype('/usr/share/fonts/truetype/lato/Lato-Bold.ttf',44)
def wrap(s):
 rows=[];line=''
 for word in s.split():
  trial=(line+' '+word).strip()
  if font.getlength(trial)>870 and line:rows.append(line);line=word
  else:line=trial
 if line:rows.append(line)
 return rows
for i,(s,n) in enumerate(zip(scenes,narration)):
 available=s['end_s']-s['start_s']-.7;speed=max(1,n['duration']/available)
 assert speed<1.2,('Speech too fast',i,speed)
 raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(E/f'scene-{i+1:02d}.mp3'),'-af',f'atempo={speed:.8f}', '-ar',str(SR),'-ac','1','-f','s16le','-'])
 a=np.frombuffer(raw,dtype='<i2');start=int((s['start_s']+.35)*SR);assert start+len(a)<=int(s['end_s']*SR)
 track[start:start+len(a)]=a
 words=json.loads((E/f'scene-{i+1:02d}-words.json').read_text())
 original=n['text'].split();assert len(original)==len(words)
 for w,token in zip(words,original):w['text']=token
 # Human-edited phrase boundaries preserve punctuation and complete ideas.
 cuts=[[5,8,14],[4,7,10,14],[5,9,14,17,24],[5,10,13,18,21],
       [6,10,13,17,21],[5,11,15,19],[4,9,14,20],[5,8,12],[4,9]][i]
 groups=[];previous=0
 for end in cuts:groups.append(words[previous:end]);previous=end
 assert previous==len(words)
 for j,g in enumerate(groups):
  begin=s['start_s'] if j==0 else s['start_s']+.35+g[0]['start']/speed
  end=s['end_s'] if j==len(groups)-1 else s['start_s']+.35+groups[j+1][0]['start']/speed
  txt=' '.join(w['text'] for w in g);rows=wrap(txt);assert len(rows)<=2
  captions.append({'start':begin,'end':end,'text':txt,'lines':rows})
 metrics.append({'scene':i+1,'duration_s':len(a)/SR,'speed':speed,'rms':float(np.sqrt(np.mean(a.astype(float)**2))), 'nonzero_samples':int(np.count_nonzero(a))})
with wave.open(str(E/'narration-aligned.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR);w.writeframes(track.tobytes())
def stamp(t,ass=False):
 h=int(t//3600);m=int(t//60)%60;s=t%60
 return f'{h}:{m:02}:{s:05.2f}' if ass else f'{h:02}:{m:02}:{int(s):02},{round((s%1)*1000):03}'
header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1350
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Lato,44,&H00FFFFFF,&H00FFFFFF,&H00112222,&H00112222,-1,0,0,0,100,100,0,0,1,1,0,5,95,95,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
ass=header
for c in captions:
 body=r'{\an5\pos(540,1140)}'+r'\N'.join(c['lines'])
 ass+=f"Dialogue: 0,{stamp(c['start'],True)},{stamp(c['end'],True)},Caption,,0,0,0,,{body}\n"
(E/'captions.ass').write_text(ass)
(OUT/'ParkinSense-PK-Voice-Captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n"+'\n'.join(c['lines']) for i,c in enumerate(captions))+'\n')
(E/'timing-and-audio.json').write_text(json.dumps({'audio':metrics,'captions':captions},indent=2))
# Burn captions over the previous text panel, retaining the surrounding design.
cmd=['ffmpeg','-hide_banner','-y','-i','ParkinSense-PK-Testing-Demo.mp4','-i','evidence/voice/narration-aligned.wav','-vf','drawbox=x=60:y=1066:w=960:h=150:color=0x123B3B:t=fill,ass=evidence/voice/captions.ass','-af','loudnorm=I=-16:TP=-1.5:LRA=11','-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart','-t','92','ParkinSense-PK-Voice-Captions.mp4']
subprocess.run(cmd,cwd=OUT,check=True)
print('Complete: narrated MP4 with permanent, synchronized captions.',flush=True)
