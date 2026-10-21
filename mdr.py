"""Sony WH-1000XM3 MDR V1 transport; independent Python implementation.

Wire layout checked against Sound Connect 13.3.0 and the MIT-licensed
mos9527/SonyHeadphonesClient protocol definitions and XM3 capture corpus.
"""
import collections
import socket
import struct
import time


def encode(kind, seq, payload=b''):
    body = bytes([kind, seq]) + struct.pack('>I', len(payload)) + payload
    body += bytes([sum(body) & 255])
    return b'>' + bytes(v for b in body for v in ([61, b - 16] if b in (60, 61, 62) else [b])) + b'<'


class Decoder:
    def __init__(self):
        self.body = None
        self.escaped = False

    def feed(self, data):
        result = []
        for b in data:
            if b == 62:
                self.body, self.escaped = bytearray(), False
            elif self.body is None:
                continue
            elif b == 60:
                body, self.body = self.body, None
                if self.escaped or len(body) < 7:
                    raise ValueError('Malformed MDR frame')
                if len(body) != struct.unpack('>I', body[2:6])[0] + 7 or sum(body[:-1]) & 255 != body[-1]:
                    raise ValueError('MDR length/checksum mismatch')
                result.append((body[0], body[1], bytes(body[6:-1])))
            elif self.escaped:
                if b not in (44, 45, 46):
                    raise ValueError('Invalid MDR escape')
                self.body.append(b + 16)
                self.escaped = False
            elif b == 61:
                self.escaped = True
            else:
                self.body.append(b)
            if self.body is not None and len(self.body) > 65536:
                raise ValueError('Oversized MDR frame')
        return result


class Session:
    def __init__(self, address, channel, on_payload=None):
        self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        self.sock.settimeout(5)
        try:
            self.sock.connect((address, channel))
        except BaseException:
            self.sock.close()
            raise
        self.decoder = Decoder()
        self.tx = 0
        self.last_rx = None
        self.acks = collections.deque(maxlen=16)
        self.responses = collections.deque(maxlen=256)
        self.on_payload = on_payload or (lambda kind, payload: None)
        self.trace = collections.deque(maxlen=500)

    def close(self):
        self.sock.close()

    def pump(self, timeout):
        self.sock.settimeout(max(.01, timeout))
        try:
            data = self.sock.recv(4096)
        except socket.timeout:
            return
        if not data:
            raise ConnectionError('The headphone control connection was closed')
        for kind, seq, payload in self.decoder.feed(data):
            self.trace.append({'direction': 'rx', 'kind': kind, 'seq': seq, 'payload': payload.hex()})
            if kind == 1:
                self.acks.append(seq)
                continue
            if kind not in (12, 14):
                continue
            self.sock.sendall(encode(1, seq ^ 1))
            if seq == self.last_rx:
                continue
            self.last_rx = seq
            self.responses.append((kind, payload))
            self.on_payload(kind, payload)

    def request(self, payload, response=None, kind=12, timeout=3):
        """Preserve replies arriving before ACK; never retry an uncertain SET."""
        self.responses.clear()
        self.acks.clear()
        self.trace.append({'direction': 'tx', 'kind': kind, 'seq': self.tx, 'payload': payload.hex()})
        self.sock.sendall(encode(kind, self.tx, payload))
        deadline = time.monotonic() + timeout
        acknowledged, answer = False, None
        while time.monotonic() < deadline:
            self.pump(min(.25, deadline - time.monotonic()))
            if (self.tx ^ 1) in self.acks:
                acknowledged = True
            if response is not None:
                for k, p in self.responses:
                    if k == kind and p.startswith(response):
                        answer = p
            if acknowledged and (response is None or answer is not None):
                self.tx ^= 1
                return answer
        if acknowledged:
            self.tx ^= 1
        raise TimeoutError(f'The headset did not fully confirm request {payload.hex()} (ACK={acknowledged})')
