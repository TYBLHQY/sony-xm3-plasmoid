#!/usr/bin/env python3
"""Build a self-contained Plasma 6 package and install its per-user service."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
METADATA = json.loads((ROOT/'package/metadata.json').read_text())
ID = METADATA['KPlugin']['Id']


def build_package():
    build = ROOT/'build'
    build.mkdir(exist_ok=True)
    stage = build/'package'
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(ROOT/'package',stage)
    code = stage/'contents/code'
    code.mkdir(parents=True,exist_ok=True)
    for name in ('mdr.py','controller.py','sonyctl.py'):
        shutil.copy2(ROOT/name,code/name)
    subprocess.run(['cc','-O2','-Wall','-Wextra',str(ROOT/'sdp_channel.c'),'-lbluetooth','-o',str(code/'sdp-channel')],check=True)
    shutil.copy2(ROOT/'LICENSE',stage/'LICENSE')
    archive = ROOT/f"sony-wh1000xm3-{METADATA['KPlugin']['Version']}.plasmoid"
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(stage.rglob('*')):
            if file.is_file():
                z.write(file,file.relative_to(stage))
    return archive


def install(address):
    if not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',address):
        raise ValueError('Invalid Bluetooth address')
    config = Path.home()/'.config/sony-xm3.json'
    if config.exists() and json.loads(config.read_text()).get('address','').upper()!=address.upper():
        raise ValueError('The existing configuration uses another Bluetooth address. Update it explicitly before installing.')
    archive = build_package()
    target = Path.home()/'.local/share/plasma/plasmoids'/ID
    service = Path.home()/'.config/systemd/user/sony-xm3.service'
    backup = ROOT/'private/backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    for file in (target,service,config):
        if file.exists():
            backup.mkdir(parents=True,exist_ok=True)
            if file.is_dir(): shutil.copytree(file,backup/file.name)
            else: shutil.copy2(file,backup/file.name)
    env = dict(os.environ,XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    subprocess.run(['systemctl','--user','stop','sony-xm3.service'],env=env,capture_output=True)
    subprocess.run(['kpackagetool6','--type','Plasma/Applet','--upgrade' if target.exists() else '--install',str(archive)],env=env,check=True)
    (target/'contents/code/sdp-channel').chmod(0o755)
    config.parent.mkdir(parents=True,exist_ok=True)
    if not config.exists():
        config.write_text(json.dumps(dict(address=address.upper(),autoConnect=True),indent=2)+'\n')
        config.chmod(0o600)
    service.parent.mkdir(parents=True,exist_ok=True)
    script = target/'contents/code/sonyctl.py'
    service.write_text('[Unit]\nDescription=Sony WH-1000XM3 control backend\n\n[Service]\nType=simple\n'
                       f'ExecStart=/usr/bin/python3 {json.dumps(str(script))} daemon\n'
                       'Restart=on-failure\nRestartSec=5\nUMask=0077\nNoNewPrivileges=yes\n\n'
                       '[Install]\nWantedBy=default.target\n')
    subprocess.run(['systemctl','--user','daemon-reload'],env=env,check=True)
    subprocess.run(['systemctl','--user','enable','--now','sony-xm3.service'],env=env,check=True)
    print(f'Package: {archive}\nInstalled: {target}\nService: {service}')
    if backup.exists(): print(f'Backup: {backup}')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--address')
    parser.add_argument('--build-only',action='store_true',help='Build without installing the widget or starting a service')
    args=parser.parse_args()
    if args.build_only:
        print(build_package())
    elif args.address:
        install(args.address)
    else:
        parser.error('--address is required unless --build-only is used')
