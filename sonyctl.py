#!/usr/bin/env python3
"""Private per-user Unix IPC, persistent single-owner Bluetooth worker, CLI."""
import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import queue
import signal
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import time
from controller import Controller, initial_state

CONFIG = Path.home()/'.config/sony-xm3.json'
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))/'sony-xm3'
SOCKET = RUNTIME/'control.sock'
HERE = Path(__file__).resolve().parent


class Backend:
    def __init__(self):
        self.config = json.loads(CONFIG.read_text())
        self.enabled = self.config.get('autoConnect', True)
        self.state = initial_state()
        self.lock = threading.RLock()
        self.jobs = queue.Queue(maxsize=8)
        self.stop = threading.Event()
        self.controller = None
        self.busy = False
        self.thread = threading.Thread(target=self.worker,daemon=True)

    def publish(self, state):
        with self.lock:
            self.state.update(state)

    def snapshot(self):
        with self.lock:
            result = copy.deepcopy(self.state)
            result.update(enabled=self.enabled,busy=self.busy)
            return result

    def persist(self):
        self.config['autoConnect'] = self.enabled
        CONFIG.parent.mkdir(parents=True,exist_ok=True)
        temp = CONFIG.with_suffix('.tmp')
        temp.write_text(json.dumps(self.config,ensure_ascii=False,indent=2)+'\n')
        temp.chmod(0o600)
        temp.replace(CONFIG)

    def disconnect(self, message=''):
        if self.controller:
            self.controller.session.close()
            self.controller = None
        with self.lock:
            self.state.update(connected=False,message=message)

    def connect(self):
        address = self.config['address']
        result = subprocess.run(['bluetoothctl','info',address],capture_output=True,text=True,timeout=3)
        if 'Connected: yes' not in result.stdout:
            raise ConnectionError('Connect WH-1000XM3 in your system Bluetooth settings first')
        result = subprocess.run([str(HERE/'sdp-channel'),address],capture_output=True,text=True,timeout=7,check=True)
        c = Controller(address,int(result.stdout.strip()),self.publish)
        try:
            c.start()
        except BaseException:
            c.session.close()
            raise
        self.controller = c

    def execute(self, command, value=None):
        if command == 'status':
            return dict(ok=True,state=self.snapshot())
        event, result = threading.Event(), {}
        try:
            self.jobs.put_nowait((command,value,event,result))
        except queue.Full:
            return dict(ok=False,error='The command queue is full. Please try again shortly',state=self.snapshot())
        if not event.wait(40):
            return dict(ok=False,error='The request is still being processed. Refresh the status before trying again',state=self.snapshot())
        return dict(result,state=self.snapshot())

    def set_codec(self,value):
        profiles = {'SBC':'a2dp-sink-sbc','LDAC':'a2dp-sink'}
        if value not in profiles:
            raise ValueError('Only SBC and LDAC are supported')
        card = 'bluez_card.'+self.config['address'].upper().replace(':','_')
        # Change only the user's XM3 card, never the default sink or volume.
        subprocess.run(['pactl','set-card-profile',card,profiles[value]],capture_output=True,text=True,timeout=8,check=True)
        deadline = time.monotonic()+6
        while time.monotonic()<deadline:
            self.controller.get(0x18,0)
            if self.controller.state['codec']==value:
                self.controller.refresh()
                return
            self.controller.session.pump(.2)
        raise ValueError('The codec change was requested but not confirmed by the headset. Refresh to check')

    def worker(self):
        next_connect, next_refresh = 0, 0
        while not self.stop.is_set():
            job = None
            try:
                job = self.jobs.get(timeout=.15)
            except queue.Empty:
                pass
            if job:
                command,value,event,result = job
                self.busy = True
                try:
                    if command == 'release':
                        self.enabled = False
                        self.persist()
                        self.disconnect('Control released. You can now use the phone app')
                    elif command == 'connect':
                        self.enabled = True
                        self.persist()
                        if not self.controller:
                            self.connect()
                    elif command == 'refresh':
                        if not self.controller:
                            raise ConnectionError('Control channel disconnected')
                        self.controller.refresh()
                    elif command == 'codec':
                        if not self.controller:
                            raise ConnectionError('Control channel disconnected')
                        self.set_codec(value)
                    else:
                        if not self.controller:
                            raise ConnectionError('Control channel disconnected')
                        self.controller.set(command,value)
                    with self.lock:
                        self.state.update(error='',message='Verified by the headset' if command not in ('release','connect','refresh') else self.state.get('message',''))
                    result.update(ok=True)
                except Exception as exc:
                    result.update(ok=False,error=str(exc))
                    with self.lock:
                        self.state.update(error=str(exc),message='')
                    if isinstance(exc,(OSError,TimeoutError)):
                        self.disconnect()
                        next_connect = time.monotonic()+10
                finally:
                    self.busy = False
                    event.set()
                continue
            try:
                if self.enabled and not self.controller and time.monotonic() >= next_connect:
                    self.busy = True
                    try:
                        self.connect()
                        self.publish(dict(error='',message='Control channel connected'))
                        next_refresh = time.monotonic()+30
                    finally:
                        next_connect = time.monotonic()+15
                        self.busy = False
                if self.controller:
                    self.controller.session.pump(.1)
                    self.controller.flush_alerts()
                    if time.monotonic() >= next_refresh:
                        self.controller.refresh()
                        next_refresh = time.monotonic()+30
            except Exception as exc:
                self.disconnect()
                self.publish(dict(error=str(exc),message=''))
                next_connect = time.monotonic()+15
        self.disconnect()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            self.request.settimeout(45)
            _,uid,_ = struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid != os.getuid():
                return
            raw = self.rfile.readline(8193)
            if len(raw)>8192:
                raise ValueError('Request too large')
            request = json.loads(raw)
            command = request.get('command','status')
            if command not in ('status','refresh','connect','release','noise','eq','eq_custom','dsee','touch','guidance','auto_off','vpt','position','button','codec'):
                raise ValueError('Unsupported command')
            result = self.server.backend.execute(command,request.get('value'))
        except Exception as exc:
            result = dict(ok=False,error=str(exc))
        try:
            self.wfile.write((json.dumps(result,ensure_ascii=False)+'\n').encode())
        except (BrokenPipeError,ConnectionResetError):
            pass


def daemon():
    RUNTIME.mkdir(mode=0o700,parents=True,exist_ok=True)
    RUNTIME.chmod(0o700)
    lock = (RUNTIME/'daemon.lock').open('w')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    SOCKET.unlink(missing_ok=True)
    backend = Backend()
    with socketserver.ThreadingUnixStreamServer(str(SOCKET),Handler) as server:
        server.daemon_threads = True
        server.backend = backend
        SOCKET.chmod(0o600)
        backend.thread.start()
        def stop(signum,frame):
            backend.stop.set()
            threading.Thread(target=server.shutdown,daemon=True).start()
        signal.signal(signal.SIGTERM,stop)
        signal.signal(signal.SIGINT,stop)
        try:
            server.serve_forever(poll_interval=.2)
        finally:
            backend.stop.set()
            backend.thread.join(timeout=10)
            SOCKET.unlink(missing_ok=True)


def client(request):
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(42)
            sock.connect(str(SOCKET))
            sock.sendall((json.dumps(request)+'\n').encode())
            with sock.makefile('rb') as stream:
                return json.loads(stream.readline(131072))
    except Exception as exc:
        return dict(ok=False,error=f'Backend unavailable: {exc}',state=initial_state())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command',nargs='?',default='status')
    parser.add_argument('value',nargs='?')
    args = parser.parse_args()
    if args.command == 'daemon':
        daemon()
    else:
        request = json.loads(args.value) if args.command=='request' else dict(command=args.command,value=json.loads(args.value) if args.value else None)
        result = client(request)
        print(json.dumps(result,ensure_ascii=False))
        sys.exit(0 if result.get('ok') else 1)
