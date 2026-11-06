"""Verify an extracted, unmodified source release without importing AI dependencies."""
from pathlib import Path
import hashlib
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP_LOCAL = {'.local', '.venv', 'engine', 'models', 'artifacts', '__pycache__', '.pytest_cache', '.git'}


def main():
    manifest_path = ROOT / 'SHA256SUMS.json'
    if not manifest_path.is_file():
        raise SystemExit('No release manifest. Run this tool on the distributed ZIP.')
    expected = json.loads(manifest_path.read_text(encoding='utf-8'))
    failures = []
    for name, digest in expected.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            failures.append(f'Missing or linked release file: {name}')
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            failures.append(f'Changed release file: {name}')
    unexpected = []
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if any(part in SKIP_LOCAL for part in relative.parts) or not path.is_file():
            continue
        if relative.as_posix() not in expected and relative.as_posix() != 'SHA256SUMS.json':
            unexpected.append(relative.as_posix())
    failures.extend('Unexpected file: '+name for name in unexpected)
    for name in expected:
        if Path(name).suffix in {'.py', '.js', '.html', '.css', '.md', '.json', '.txt', '.toml', '.ps1'}:
            text = (ROOT / name).read_text(encoding='utf-8')
            if re.search(r'\bhf_[A-Za-z0-9]{24,}\b', text):
                failures.append('Potential credential in '+name)
    if failures:
        print('\n'.join(failures))
        return 1
    print(f'Verified {len(expected)} release files. Runtime directories are excluded.')
    print('Manifest integrity is not a publisher signature or a model/hardware certification.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
