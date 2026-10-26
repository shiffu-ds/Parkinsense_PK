"""Editorial video built from measured outputs, not a recording of app interactions."""
from pathlib import Path
import json, math, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import soundfile as sf
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
E=OUT/'evidence';AUDIT=ROOT/'artifacts/project-audit-2026-10-18'
W,H,FPS=1080,1350,24
BG='#F4F2EC';INK='#123B3B';MUTED='#58716C';TEAL='#0B827A';DARK='#102C32';GRID='#29464A';WHITE='#FFFFFF';MINT='#75D8C4';GOLD='#EAC17B'
fonts={}
def font(sz,bold=False):
 k=(sz,bold)
 if k not in fonts:fonts[k]=ImageFont.truetype('/usr/share/fonts/truetype/lato/Lato-'+('Bold' if bold else 'Regular')+'.ttf',sz)
 return fonts[k]
def text(d,xy,s,size=30,color=INK,bold=False):d.text(xy,s,font=font(size,bold),fill=color)
def lines(d,xy,s,size=30,color=INK,width=900,gap=9,bold=False):
 x,y=xy;line=''
 for word in s.split():
  trial=(line+' '+word).strip()
  if d.textlength(trial,font=font(size,bold))>width and line:text(d,(x,y),line,size,color,bold);y+=size+gap;line=word
  else:line=trial
 if line:text(d,(x,y),line,size,color,bold)
 return y+size+gap
def rr(d,box,fill,r=24,outline=None):d.rounded_rectangle(box,r,fill=fill,outline=outline,width=2)
def pill(d,x,y,s):
 w=d.textlength(s,font=font(21,True))+32;rr(d,(x,y,x+w,y+39),'#DEE9E2',15);text(d,(x+16,y+6),s,21,TEAL,True)
def metric(d,x,y,value,label,w=286):
 rr(d,(x,y,x+w,y+112),WHITE,18);text(d,(x+20,y+14),value,39,TEAL,True);text(d,(x+20,y+68),label,22,MUTED)
def base(n,title,sub):
 im=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(im)
 rr(d,(60,53,105,98),TEAL,12);text(d,(70,56),'P',30,WHITE,True)
 text(d,(121,59),'ParkinSense PK',29,INK,True);text(d,(776,64),'BUILD JOURNAL 01',18,MUTED,True)
 text(d,(60,151),f'{n:02d} / TESTING THE PROTOTYPE',20,TEAL,True)
 lines(d,(60,195),title,58,INK,940,6,True);lines(d,(60,281),sub,28,MUTED,940)
 d.line((60,1243,1020,1243),fill='#CFD9D0',width=2)
 text(d,(60,1270),'Research prototype • Not a diagnostic tool',23,MUTED)
 text(d,(875,1273),'OCT 2026',20,MUTED,True)
 return im
SCENES=[
 (8,'Movement deserves','a closer look.','A testing walkthrough of ParkinSense PK, a functional monitoring prototype.'),
 (10,'Six assessment sections','One place to review movement, voice and daily activities.','The app covers walking, hands, sit-to-stand, reach and grasp, voice, and daily activities.'),
 (14,'Walking, in three dimensions','Replay from a published clinical recording.','These 3D landmarks come from a real walking recording. They are model estimates, not calibrated clinical measurements.'),
 (14,'Small movements. Visible patterns.','Finger tapping from a published research recording.','The hand replay shows measured motion over time. This source does not identify the participant’s diagnosis.'),
 (12,'Voice has a place here, too','Signal features from a real research audio sample.','The voice module measures signal activity, pauses and pitch. It does not diagnose Parkinson’s or automatically transcribe speech.'),
 (10,'Results that can be reviewed','Recording quality, measurements and limitations together.','Reports bring measurements and limitations together, with clinician review still required.'),
 (10,'Show the checks. And the gaps.','Software verification is different from clinical validation.','The archived suite passed 463 tests. Wrong-task checks also exposed an important limitation that still needs work.'),
 (8,'The next step is validation','Independent evaluation with real clinical workflows.','The next phase is independent measurement validation, patient usability testing and supervised clinic evaluation.'),
 (6,'Built with evidence in view','Published sources • Derived visuals • Clear limits','Demo visuals are derived from cited research recordings. No clinical accuracy or treatment claim is made.')]
starts=np.cumsum([0]+[s[0] for s in SCENES]);DURATION=int(starts[-1])
gait=json.loads((E/'clinical-pd-gait-indoor-2016.json').read_text());hand=json.loads((E/'research-finger-left.json').read_text());voice=json.loads((E/'voice.json').read_text())
assert gait['quality']['accepted'] and hand['quality']['accepted'] and voice['quality']['accepted']
arch=json.loads((AUDIT/'final-checks.json').read_text());assert arch['python_tests']==463 and arch['failures']==0
BODY=[(11,12),(11,13),(13,15),(12,14),(14,16),(11,23),(12,24),(23,24),(23,25),(25,27),(27,29),(29,31),(27,31),(24,26),(26,28),(28,30),(30,32),(28,32)]
HAND=[(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(0,17),(17,18),(18,19),(19,20)]
wave,sr=sf.read(AUDIT/'real-media/pd-reading-30-60s.wav');wave=wave.mean(axis=1) if wave.ndim==2 else wave
bins=np.array([np.max(np.abs(a)) for a in np.array_split(wave,450)]);bins/=max(bins)

def plot(d,arr,box,p,color=MINT):
 x,y,w,h=box;v=np.asarray(arr,float);lo,hi=np.nanmin(v),np.nanmax(v);span=max(hi-lo,.00001)
 for j in range(4):d.line((x,y+j*h/3,x+w,y+j*h/3),fill=GRID,width=1)
 pts=[(int(x+i*w/(len(v)-1)),int(y+h-(a-lo)*h/span)) for i,a in enumerate(v)]
 d.line(pts,fill='#476368',width=2);end=max(2,int(p*len(pts)));d.line(pts[:end],fill=color,width=4)
 cx,cy=pts[min(len(pts)-1,end-1)];d.ellipse((cx-6,cy-6,cx+6,cy+6),fill=WHITE)

def motion(im,res,t,is_hand=False,box=(82,367,998,902)):
 d=ImageDraw.Draw(im);x,y,x2,y2=box;rr(d,box,DARK,26)
 frames=res['landmark_frames'];duration=res['media_metadata']['duration_s'];at=(t%duration)
 times=np.array([f['timestamp_s'] for f in frames]);i=max(0,min(len(frames)-2,np.searchsorted(times,at)-1));f=(at-times[i])/max(times[i+1]-times[i],.001);f=np.clip(f,0,1)
 a=np.asarray(frames[i]['world_landmarks']);b=np.asarray(frames[i+1]['world_landmarks']);v=a[:,:3]*(1-f)+b[:,:3]*f
 if is_hand:v-=v[0]
 theta=.45+.35*math.sin(t*.25);ct,st=math.cos(theta),math.sin(theta)
 scale=1450 if is_hand else 225;cx=(x+x2)/2;cy=y+310 if is_hand else y+205
 def project(pt):
  xx,yy,zz=pt;rx=xx*ct+zz*st;rz=-xx*st+zz*ct;ry=yy*.96+rz*.28;depth=1+rz*.15
  return (int(cx+rx*scale/depth),int(cy+ry*scale/depth)),rz
 extent=.12 if is_hand else .8;floor=.04 if is_hand else .8
 for z in np.linspace(-extent,extent,7):
  aa,_=project((-extent,floor,z));bb,_=project((extent,floor,z));d.line([aa,bb],fill=GRID,width=1)
 for xx in np.linspace(-extent,extent,7):
  aa,_=project((xx,floor,-extent));bb,_=project((xx,floor,extent));d.line([aa,bb],fill=GRID,width=1)
 pts=[project(p) for p in v];edges=HAND if is_hand else BODY
 if is_hand:
  poly=[pts[k][0] for k in [0,5,9,13,17]];d.polygon(poly,fill='#244F51')
 else:d.polygon([pts[k][0] for k in [11,12,24,23]],fill='#244F51')
 for u,w in sorted(edges,key=lambda e:(pts[e[0]][1]+pts[e[1]][1])/2,reverse=True):
  color=GOLD if (is_hand and u<5) else MINT
  d.line([pts[u][0],pts[w][0]],fill='#1C5B5B',width=16);d.line([pts[u][0],pts[w][0]],fill=color,width=7)
 used=set(k for e in edges for k in e)
 for k in used:
  px,py=pts[k][0];d.ellipse((px-6,py-6,px+6,py+6),fill=WHITE)
 text(d,(x+24,y+20),'RECORDED OUTPUT / 3D REPLAY',20,MINT,True)
 text(d,(x+24,y2-69),'Model-local XYZ • estimated scale',23,'#B7CECB')
 text(d,(x+24,y2-36),f'{at:04.1f}s / {duration:04.1f}s • replay loops',20,'#B7CECB')

def make_frame(scene,t):
 dur,title,sub,caption=SCENES[scene]
 if scene==0:
  im=base(1,'Movement, made visible.','Real recordings. Measured outputs. Honest testing.');d=ImageDraw.Draw(im)
  motion(im,gait,t,False,(82,367,998,920));d=ImageDraw.Draw(im);pill(d,83,948,'BODY');pill(d,224,948,'HANDS');pill(d,384,948,'VOICE');pill(d,538,948,'REPORTS')
 elif scene==1:
  im=base(2,title,sub);d=ImageDraw.Draw(im)
  cards=[('01','Walking','Gait + turning'),('02','Hands','Tapping + opening'),('03','Sit-to-stand','Transition measures'),('04','Reach + grasp','Object-transfer tasks'),('05','Voice','Audio + reviewed text'),('06','Daily activities','Patient self-report')]
  for j,(num,name,desc) in enumerate(cards):
   x=60+(j%2)*490;y=380+(j//2)*190;rr(d,(x,y,x+470,y+170),WHITE)
   text(d,(x+24,y+20),num,24,TEAL,True);text(d,(x+24,y+58),name,34,INK,True);text(d,(x+24,y+110),desc,24,MUTED)
  text(d,(60,985),'Real-recording examples in this film: gait, hand and voice.',25,MUTED)
 elif scene in [2,3]:
  res=gait if scene==2 else hand;im=base(scene+1,title,sub);motion(im,res,t,scene==3,(60,365,1020,854));d=ImageDraw.Draw(im)
  p=(t%res['media_metadata']['duration_s'])/res['media_metadata']['duration_s']
  rr(d,(60,872,650,1035),DARK,18)
  key='left_knee_angle_deg_proxy' if scene==2 else 'thumb_index_distance_ratio'
  text(d,(82,887),'Knee angle proxy (degrees)' if scene==2 else 'Thumb–index distance / hand size',21,'#B7CECB')
  plot(d,res['curves'][key],(86,931,540,78),p)
  n=f"{res['quality']['valid_frames']} / {res['quality']['sampled_frames']}"
  metric(d,674,872,n,'sampled frames tracked',346)
  text(d,(686,1001),'Not an accuracy percentage',21,MUTED)
 elif scene==4:
  im=base(5,title,sub);d=ImageDraw.Draw(im);rr(d,(60,375,1020,768),DARK)
  text(d,(87,403),'MDVR-KCL / READING EXCERPT',23,MINT,True)
  text(d,(87,447),'Actual waveform • 30 seconds',29,WHITE)
  for j,v in enumerate(bins):
   x=88+j*2;ht=float(v)*95;color=MINT if j/len(bins)<t/dur else '#3E6263';d.line((x,603-ht,x,603+ht),fill=color,width=1)
  text(d,(87,712),'0s',22,'#B7CECB');text(d,(946,712),'30s',22,'#B7CECB')
  metric(d,60,797,f"{voice['features']['signal_active_fraction']*100:.1f}%",'signal activity',306)
  metric(d,387,797,str(voice['features']['internal_pause_count']),'internal pauses',306)
  metric(d,714,797,f"{voice['features']['f0_autocorrelation_median_hz']:.1f} Hz",'pitch estimate',306)
  lines(d,(60,946),'PD-labelled research sample. Acoustic features are not clinical scores.',27,MUTED,920)
 elif scene==5:
  im=base(6,title,sub);d=ImageDraw.Draw(im);rr(d,(75,375,1005,1025),WHITE,26)
  text(d,(108,405),'ANALYSIS REPORT / OUTPUT EXCERPT',22,TEAL,True)
  text(d,(108,453),'Walking • published recording',35,INK,True)
  d.line((108,519,970,519),fill='#DDE5DF',width=2)
  for y,label,value in [(548,'Recording quality','Accepted'),(618,'Frames tracked','60 / 60 sampled'),(688,'Cadence proxy',f"{gait['features']['cadence_steps_per_min_proxy']:.2f} steps/min")]:
   text(d,(108,y),label,27,MUTED);text(d,(574,y),value,27,INK,True)
  rr(d,(108,767,970,893),'#F4ECD9',16)
  text(d,(131,784),'LIMITATION RETAINED',21,'#806128',True)
  lines(d,(131,820),'Arm-swing measurement withheld: tracking was insufficient.',27,INK,805)
  text(d,(108,934),'Human review required • Monitoring proxies only',25,TEAL,True)
 elif scene==6:
  im=base(7,title,sub);d=ImageDraw.Draw(im)
  rr(d,(60,375,1020,608),DARK);text(d,(88,397),'ARCHIVED VERIFICATION / 19 OCT 2026',22,MINT,True)
  text(d,(88,437),'463',100,WHITE,True);text(d,(333,476),'software tests passed',35,WHITE,True)
  text(d,(90,563),'0 failures • 0 errors • 0 skipped',27,'#B7CECB')
  rr(d,(60,634,1020,796),WHITE);text(d,(89,658),'Three media samples rerun for this demo',31,INK,True)
  text(d,(89,716),'Gait / hand / voice processing completed',28,TEAL)
  rr(d,(60,821,1020,1033),'#F4E6CF');text(d,(89,845),'AN OPEN ISSUE, NOT HIDDEN',22,'#806128',True)
  lines(d,(89,890),'5 of 6 wrong-task videos passed quality checks in the audit. Task confirmation still needs human review.',29,INK,870)
 elif scene==7:
  im=base(8,title,sub);d=ImageDraw.Draw(im)
  for j,(a,b) in enumerate([('01','Validate measurements against expert references'),('02','Check repeatability across cameras and lighting'),('03','Test mobile usability with patients'),('04','Evaluate clinic workflow and production security')]):
   y=384+j*142;rr(d,(60,y,1020,y+119),WHITE,20);text(d,(85,y+33),a,33,TEAL,True);lines(d,(159,y+28),b,30,INK,815)
  text(d,(60,997),'Looking for thoughtful clinical and research feedback.',27,TEAL,True)
 else:
  im=base(9,title,sub);d=ImageDraw.Draw(im)
  credits=[('GAIT / Schaeffer, Linke & Berg (2016)','Frontiers in Neurology • doi:10.3389/fneur.2016.00237'),('HAND / Narongrit Kasemsap (2025)','Figshare • record 28930706 • diagnosis unspecified'),('VOICE / Jaeger, Trivedi & Stadtschnitzer','MDVR-KCL • doi:10.5281/zenodo.2867216')]
  for j,(a,b) in enumerate(credits):
   y=385+j*153;text(d,(60,y),a,27,INK,True);lines(d,(60,y+48),b,25,MUTED,940)
  lines(d,(60,875),'Sources: CC BY 4.0 • creativecommons.org/licenses/by/4.0',24,TEAL,930)
  lines(d,(60,934),'Changes: extracted measurements, animated 3D replay and waveform. No endorsement implied. Full credits accompany this video.',25,MUTED,940)
 d=ImageDraw.Draw(im);rr(d,(60,1066,1020,1216),INK,20);lines(d,(85,1087),caption,28,WHITE,910,8)
 # A quiet time marker, not a simulated analysis progress indicator.
 elapsed=starts[scene]+t;d.rectangle((60,1237,60+int(960*elapsed/DURATION),1241),fill=TEAL)
 return im

def timestamp(sec):
 ms=int(round(sec*1000));return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
(OUT/'ParkinSense-PK-English.srt').write_text('\n\n'.join(f'{i+1}\n{timestamp(starts[i])} --> {timestamp(starts[i+1])}\n{s[3]}' for i,s in enumerate(SCENES))+'\n')
(OUT/'storyboard.json').write_text(json.dumps([{'start_s':int(starts[i]),'end_s':int(starts[i+1]),'title':s[1],'caption':s[3]} for i,s in enumerate(SCENES)],indent=2))
# Preview every scene before encoding.
thumbs=[]
for i,s in enumerate(SCENES):
 im=make_frame(i,s[0]*.45);im.save(OUT/f'evidence/scene-{i+1:02d}.jpg',quality=91);thumbs.append(im.resize((270,338)))
sheet=Image.new('RGB',(810,1014),BG)
for i,im in enumerate(thumbs):sheet.paste(im,((i%3)*270,(i//3)*338))
sheet.save(OUT/'evidence/storyboard-contact-sheet.jpg',quality=94)
make_frame(0,2.0).save(OUT/'ParkinSense-PK-cover.jpg',quality=95)
# Reuse all editorial typography; redraw only animated data panels.
static_frames={i:make_frame(i,0) for i in range(len(SCENES))}
def fast_frame(scene,t):
 im=static_frames[scene].copy();d=ImageDraw.Draw(im)
 if scene==0:motion(im,gait,t,False,(82,367,998,920))
 elif scene in [2,3]:
  res=gait if scene==2 else hand;motion(im,res,t,scene==3,(60,365,1020,854));d=ImageDraw.Draw(im)
  rr(d,(60,872,650,1035),DARK,18)
  key='left_knee_angle_deg_proxy' if scene==2 else 'thumb_index_distance_ratio'
  text(d,(82,887),'Knee angle proxy (degrees)' if scene==2 else 'Thumb–index distance / hand size',21,'#B7CECB')
  plot(d,res['curves'][key],(86,931,540,78),(t%res['media_metadata']['duration_s'])/res['media_metadata']['duration_s'])
 elif scene==4:
  d.rectangle((86,500,990,706),fill=DARK)
  for j,v in enumerate(bins):
   x=88+j*2;ht=float(v)*95;color=MINT if j/len(bins)<t/SCENES[scene][0] else '#3E6263';d.line((x,603-ht,x,603+ht),fill=color,width=1)
 d=ImageDraw.Draw(im);d.rectangle((60,1237,1020,1241),fill=BG)
 d.rectangle((60,1237,60+int(960*(starts[scene]+t)/DURATION),1241),fill=TEAL)
 return im
if '--preview' not in __import__('sys').argv:
 cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'ParkinSense-PK-Testing-Demo.mp4')]
 p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
 for i,s in enumerate(SCENES):
  for frame in range(s[0]*FPS):p.stdin.write(fast_frame(i,frame/FPS).tobytes())
  print(f'Scene {i+1}/{len(SCENES)} encoded',flush=True)
 p.stdin.close();assert p.wait()==0
 print(f'Finished {DURATION}s, {W}x{H}, {FPS} fps',flush=True)
