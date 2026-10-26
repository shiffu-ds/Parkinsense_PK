from pathlib import Path
import asyncio,json,subprocess
import edge_tts
OUT=Path(__file__).resolve().parent;E=OUT/'evidence/voice'
texts=[
'This is ParkinSense P K: a research prototype for reviewing everyday movement and speech.',
'Six sections bring together walking, hands, sit-to-stand, reach and grasp, voice, and daily activities.',
'This walking replay comes from a published clinical recording. The model tracks body landmarks in three dimensions. These estimates are not calibrated clinical measurements.',
'Here, a published finger-tapping recording becomes a three-dimensional hand replay and movement curve. The source does not specify the participant’s diagnosis.',
'The voice module measures signal activity, pauses, and estimated pitch from real audio. These are acoustic measurements, not a Parkinson’s diagnosis.',
'The report brings recording quality, measurements, and limitations into one view. A clinician still needs to review the findings.',
'The archived suite passed four hundred and sixty-three tests. Wrong-task checks exposed a limitation: human task confirmation is still needed.',
'Next come independent measurement validation, patient usability testing, and supervised clinic evaluation.',
'Built from research recordings. Clinical validation is still ahead.'
]
async def main():
 rows=[]
 for i,txt in enumerate(texts):
  path=E/f'scene-{i+1:02d}.mp3';meta=E/f'scene-{i+1:02d}-words.json'
  if not path.exists() or not meta.exists():
   words=[]
   c=edge_tts.Communicate(txt,voice='en-US-AriaNeural',rate='+0%',boundary='WordBoundary',receive_timeout=30)
   with path.open('wb') as f:
    async for chunk in c.stream():
     if chunk['type']=='audio':f.write(chunk['data'])
     elif chunk['type']=='WordBoundary':words.append({'text':chunk['text'],'start':chunk['offset']/1e7,'duration':chunk['duration']/1e7})
   assert words;meta.write_text(json.dumps(words,indent=2))
  dur=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]))
  rows.append({'scene':i+1,'text':txt,'duration':dur,'voice':'en-US-AriaNeural'});print('Narration',i+1,round(dur,2),'seconds',flush=True)
 (E/'narration.json').write_text(json.dumps(rows,indent=2))
asyncio.run(main())
