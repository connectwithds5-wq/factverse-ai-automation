import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)
data = json.loads((ROOT / 'data' / 'documentary_pixazo_test.json').read_text(encoding='utf-8'))
data['shots'] = [
  {'duration':4,'narration':data['hook'],'visual_prompt':'premium photorealistic documentary macro shot of a human body from feet upward to head, subtle precision clocks at both levels, elegant scientific mood, slow camera tilt upward'},
  {'duration':4,'narration':data['fact'].split('Because')[0].strip()+'.','visual_prompt':'cinematic Earth from near space with a realistic curved spacetime grid bending around Earth, precision atomic clock near the surface, slow orbital camera'},
  {'duration':4,'narration':'Because your feet are closer to Earth, gravity slows time down for them.','visual_prompt':'photorealistic lower-body documentary shot with a precision clock near the feet and another near the head, subtle visual difference in clock motion, realistic science visualization'},
  {'duration':3,'narration':data['twist'],'visual_prompt':'premium cinematic macro visualization of a realistic human brain inside a translucent head silhouette with subtle clock and time particles, slow forward push, scientific documentary realism'}
]
(OUT / 'metadata.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
subprocess.run([sys.executable, str(ROOT / 'src' / 'generate_test_audio.py')], check=True)
import gemini_veo_documentary_test as runner
runner.make_plan = lambda: data
runner.main()
