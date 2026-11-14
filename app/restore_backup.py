#!/usr/bin/env python3
"""Restore only user-selected Math backups, preserving existing data first."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import zipfile

DEFAULT = Path(__file__).resolve().parents[1]/'.local/math'

def restore(archive_path, data_dir):
    data=Path(data_dir);data.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.TemporaryDirectory(dir=data) as folder:
        stage=Path(folder)
        with zipfile.ZipFile(archive_path) as archive:
            entries=archive.infolist()
            if sum(i.file_size for i in entries)>1024*1024*1024: raise ValueError('备份展开超过1GB，请核对文件')
            names=[i.filename for i in entries]
            if len(names)!=len(set(names)) or 'math.sqlite3' not in names or 'backup.json' not in names: raise ValueError('不是完整的 Math 备份')
            if json.loads(archive.read('backup.json')).get('format')!='math-backup-v1': raise ValueError('备份版本不支持')
            for entry in entries:
                path=Path(entry.filename)
                if path.is_absolute() or '..' in path.parts or entry.external_attr>>16 & 0o170000 == 0o120000: raise ValueError('备份含不安全路径')
                if not (entry.filename in {'math.sqlite3','backup.json'} or entry.filename.startswith(('photos/',))): raise ValueError('备份含不支持的文件')
            archive.extractall(stage)
        with sqlite3.connect(str(stage/'math.sqlite3')) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('备份数据库损坏')
            photos=conn.execute('SELECT photo FROM questions').fetchall()
            for (name,) in photos:
                if Path(name).name!=name or not (stage/'photos'/name).is_file(): raise ValueError('备份缺少题目照片')
            conn.execute('DELETE FROM sessions');conn.commit()
        # Move original files into a recovery folder; rollback if an operation fails.
        recovery=data/'before-restore'/str(time.time_ns());recovery.mkdir(parents=True,mode=0o700)
        moved=[];installed=[]
        try:
            for name in ['math.sqlite3','math.sqlite3-wal','math.sqlite3-shm','photos']:
                old=data/name
                if old.exists(): shutil.move(str(old),str(recovery/name));moved.append(name)
            for name in ['math.sqlite3','photos']:
                if (stage/name).exists(): shutil.move(str(stage/name),str(data/name));installed.append(name)
            (data/'photos').mkdir(exist_ok=True,mode=0o700)
        except Exception:
            for name in installed:
                path=data/name
                if path.is_dir():shutil.rmtree(path)
                else:path.unlink(missing_ok=True)
            for name in moved:shutil.move(str(recovery/name),str(data/name))
            raise
        for path in data.rglob('*'):
            if path.is_file() and not path.is_symlink():os.chmod(path,0o600)
            elif path.is_dir():os.chmod(path,0o700)
        return recovery

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='先停止 Math 后台，再恢复备份。原数据会保留。')
    parser.add_argument('backup',type=Path);parser.add_argument('--data-dir',type=Path,default=DEFAULT)
    args=parser.parse_args()
    # Prevent restoring a live database (both managed service and manual launcher).
    import subprocess
    check=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:8921','-sTCP:LISTEN'],capture_output=True)
    if check.returncode==0:raise SystemExit('请先运行「停止后台.command」，再恢复；恢复后运行「启动原型.command」。')
    try:previous=restore(args.backup,args.data_dir);print('恢复完成。之前的数据仍保存在：'+str(previous))
    except Exception as error:raise SystemExit('恢复未完成：'+str(error))
