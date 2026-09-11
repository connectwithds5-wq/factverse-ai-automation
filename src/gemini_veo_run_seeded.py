import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)
seed = ROOT / 'data' / 'documentary_pixazo_test.json'
metadata = json.loads(seed.read_text(encoding='utf-8'))
(OUT / 'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
subprocess.run([sys.executable, str(ROOT / 'src' / 'generate_test_audio.py')], check=True)

import gemini_veo_documentary_test as runner
runner.make_plan = lambda: metadata
runner.main()
