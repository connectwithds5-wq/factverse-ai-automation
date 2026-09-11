import json, os, re, subprocess, time
from pathlib import Path
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
CLIPS = OUT / 'gemini_veo_clips'
FINAL = OUT / 'factverse_gemini_veo.mp4'
MODEL = os.getenv('VEO_MODEL', 'veo-3.1-generate-preview')
TEXT_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.6-flash')
TARGET = 15
for p in (OUT, CLIPS): p.mkdir(parents=True, exist_ok=True)

key = os.getenv('GEMINI_API_KEY')
if not key: raise RuntimeError('GEMINI_API_KEY GitHub Secret is missing.')
client = genai.Client(api_key=key)

def parse_json(text):
    text = re.sub(r'^```(?:json)?\\s*|\\s*```$', '', (text or '').strip(), flags=re.I)
    a, b = text.find('{'), text.rfind('}')
    if a < 0 or b < 0: return None
    try: return json.loads(text[a:b+1])
    except Exception: return None

def make_plan():
    prompt = '''Create ONE factual, highly engaging 15-second FACTVERSE YouTube Short in English. Use a surprising but well-established science, history, space, animal, psychology or technology fact. Never invent facts or statistics. Return ONLY JSON: {"hook":"max 10 words","fact":"max 42 spoken words","twist":"max 12 words","title":"...","description":"...","keywords":["facts","did you know","shorts"],"hashtags":["#facts","#shorts","#factverse"],"shots":[{"duration":4,"narration":"exact lines for this beat","visual_prompt":"specific cinematic visual matching those lines"},{"duration":4,"narration":"exact lines","visual_prompt":"specific cinematic visual"},{"duration":4,"narration":"exact lines","visual_prompt":"specific cinematic visual"},{"duration":3,"narration":"exact lines","visual_prompt":"specific cinematic visual"}]}. Shot durations must total 15 seconds. Every visual prompt must be premium photorealistic documentary footage, vertical 9:16, deliberate camera movement, realistic lighting, no text, captions, logos, watermarks, UI or split screens. Prefer objects, environments, scientific visualizations, macro, aerial or natural phenomena over generic talking heads.'''
    r = client.models.generate_content(model=TEXT_MODEL, contents=prompt, config=types.GenerateContentConfig(response_mime_type='application/json', temperature=0.7))
    d = parse_json(r.text)
    if not d or len(d.get('shots', [])) != 4 or sum(int(x.get('duration', 0)) for x in d['shots']) != TARGET:
        raise RuntimeError('Invalid Gemini documentary plan.')
    return d

def veo(index, shot):
    prompt = f'''Premium factual documentary footage for a YouTube Short. Vertical 9:16, photorealistic, cinematic, physically plausible motion, realistic lighting, high detail. SUBJECT: {shot['visual_prompt']}. Shot {index+1} of 4. Keep the subject clearly visible and avoid abrupt internal cuts. STRICTLY NO text, subtitles, captions, logos, watermarks, UI, fake labels, readable signs, split screens, duplicated subjects, distorted anatomy or AI artifacts. Generate visual scene plus natural ambient sound only; do not speak narration.'''
    duration = 4 if int(shot['duration']) == 3 else int(shot['duration'])
    op = client.models.generate_videos(model=MODEL, prompt=prompt, config=types.GenerateVideosConfig(aspect_ratio='9:16', resolution='720p', duration_seconds=duration, number_of_videos=1))
    start = time.time()
    while not op.done:
        if time.time() - start > 900: raise TimeoutError(f'Veo shot {index+1} timed out')
        time.sleep(10); op = client.operations.get(op)
    if not op.response or not op.response.generated_videos: raise RuntimeError(f'No video returned for shot {index+1}')
    path = CLIPS / f'shot_{index+1:02d}.mp4'
    client.files.download(file=op.response.generated_videos[0].video, destination=str(path))
    return path, prompt

def caption(src, text, index, duration):
    dst = OUT / f'gemini_caption_{index:02d}.mp4'
    words, lines, cur = text.split(), [], ''
    for w in words:
        test = (cur + ' ' + w).strip()
        if len(test) <= 25: cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    cap = '\\n'.join(lines[:3]).replace(':', '\\:').replace("'", "\\\\'")
    vf = f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='{cap}':fontcolor=white:fontsize=58:line_spacing=10:borderw=4:bordercolor=black:box=1:boxcolor=black@0.58:boxborderw=22:x=(w-text_w)/2:y=1160"
    subprocess.run(['ffmpeg','-y','-i',str(src),'-t',str(duration),'-vf',vf,'-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(dst)], check=True)
    return dst

def main():
    data = make_plan()
    (OUT/'metadata.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'gemini_veo_plan.json').write_text(json.dumps({'model':MODEL,'text_model':TEXT_MODEL,'shots':data['shots']}, ensure_ascii=False, indent=2), encoding='utf-8')
    voice = OUT / 'voice.wav'
    if not voice.exists(): raise RuntimeError('voice.wav missing; run generate_test_audio.py first')
    clips, requests = [], []
    for i, shot in enumerate(data['shots']):
        src, prompt = veo(i, shot)
        clips.append(caption(src, shot['narration'], i+1, int(shot['duration'])))
        requests.append({'shot':i+1,'duration':shot['duration'],'narration':shot['narration'],'visual_prompt':shot['visual_prompt'],'veo_prompt':prompt})
    (OUT/'gemini_veo_requests.json').write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'gemini_veo_timing.json').write_text(json.dumps({'durations':[x['duration'] for x in data['shots']], 'total':TARGET}, indent=2), encoding='utf-8')
    concat = OUT/'gemini_veo_concat.txt'
    concat.write_text('\\n'.join(f"file '{p.resolve()}'" for p in clips)+'\\n', encoding='utf-8')
    visuals = OUT/'gemini_veo_visuals.mp4'
    subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-t',str(TARGET),'-an','-r','30','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(visuals)], check=True)
    subprocess.run(['ffmpeg','-y','-i',str(visuals),'-i',str(voice),'-filter_complex','[1:a]apad,atrim=0:15,volume=1.0[voice]','-map','0:v:0','-map','[voice]','-t','15','-c:v','copy','-c:a','aac','-b:a','160k','-movflags','+faststart',str(FINAL)], check=True)
    print('FINAL:', FINAL)
    print('TITLE:', data['title'])

if __name__ == '__main__': main()
