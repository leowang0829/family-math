#!/usr/bin/env python3
"""Start Family Math with an explicit private data directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def write_private(path, value):
    temporary = path.with_suffix('.tmp')
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description='爱数学 · Family Math')
    parser.add_argument('--bind', default=os.getenv('MATH_BIND', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.getenv('MATH_PORT', '8921')))
    parser.add_argument('--data-dir', default=os.getenv('MATH_DATA_DIR'))
    parser.add_argument('--public-origin', default=os.getenv('MATH_PUBLIC_ORIGIN'))
    args = parser.parse_args()
    os.umask(0o077)
    data = Path(args.data_dir).expanduser().resolve() if args.data_dir else ROOT / '.local' / 'math'
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    configuration = data / 'ai-config.json'
    key = os.getenv('DASHSCOPE_API_KEY')
    if key:
        write_private(configuration, {'provider': 'qwen', 'key': key, 'model': 'qwen3.8-max',
                                      'workspace': os.getenv('DASHSCOPE_WORKSPACE', ''), 'routing': 'hybrid-v1'})
    elif not configuration.exists():
        write_private(configuration, {'provider': 'qwen', 'key': '', 'model': 'qwen3.8-max',
                                      'workspace': '', 'routing': 'hybrid-v1'})
    command = [sys.executable, str(ROOT / 'app' / 'server.py'),
               '--bind', args.bind, '--port', str(args.port), '--data-dir', str(data)]
    if args.public_origin:
        password = os.getenv('MATH_FAMILY_PASSWORD', '')
        access = data / 'access-config.json'
        if password:
            if not 12 <= len(password) <= 128:
                parser.error('MATH_FAMILY_PASSWORD must contain 12–128 characters')
            salt = secrets.token_hex(16)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
            write_private(access, {'algorithm': 'pbkdf2-sha256', 'iterations': 600000, 'salt': salt, 'hash': digest})
        if not access.exists():
            parser.error('Set MATH_FAMILY_PASSWORD for the first public deployment')
        command += ['--public-origin', args.public_origin, '--public-access']
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
