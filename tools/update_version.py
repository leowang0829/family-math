"""Refresh the browser update marker after editing static application files."""
from pathlib import Path
import hashlib
import re

dist = Path(__file__).resolve().parents[1] / 'app' / 'dist'
digest = hashlib.sha256()
for file in sorted(dist.rglob('*')):
    if file.is_file() and file.name not in {'index.html', 'sw.js', 'app-version.js'}:
        digest.update(file.relative_to(dist).as_posix().encode())
        digest.update(file.read_bytes())
version = digest.hexdigest()
index = dist / 'index.html'
index.write_text(re.sub(r'[a-f0-9]{64}', version, index.read_text()))
(dist / 'app-version.js').write_text('// Math build: ' + version + '\n')
worker = dist / 'sw.js'
source = worker.read_text().replace('zhiyi-prototype-', 'family-math-')
source = re.sub(r"const CACHE = '[^']+';", "const CACHE = 'family-math-" + version[:16] + "';", source)
worker.write_text(source)
print(version)
