import pathlib
import socket
import threading
import unittest
from mdr import Decoder, Session, encode
from controller import Controller


class ProtocolTests(unittest.TestCase):
    def test_all_bytes_fragmented(self):
        payload=bytes(range(256))*3
        wire=encode(12,0,payload)
        decoder=Decoder()
        result=[]
        for b in wire: result+=decoder.feed(bytes([b]))
        self.assertEqual(result,[(12,0,payload)])

    def test_corruption_rejected(self):
        raw=bytearray(encode(12,0,b'\x00\x00'))
        raw[-2]^=1
        with self.assertRaises(ValueError): Decoder().feed(raw)

    def test_capture_corpus(self):
        corpus=pathlib.Path(__file__).parent/'references/SonyHeadphonesClient/tests/WH-1000XM3-4.5.2'
        files=list(corpus.glob('*.bin'))
        if not files: self.skipTest('Optional upstream capture corpus absent')
        for file in files:
            self.assertEqual(len(Decoder().feed(file.read_bytes())),1,file.name)

    def test_reply_before_ack_and_duplicate(self):
        local,remote=socket.socketpair()
        seen=[]
        # Exercise Session without using an actual Bluetooth adapter.
        session=Session.__new__(Session)
        import collections
        session.sock=local; session.decoder=Decoder(); session.tx=0; session.last_rx=None
        session.acks=collections.deque(maxlen=16); session.responses=collections.deque(maxlen=256)
        session.on_payload=lambda k,p:seen.append(p); session.trace=collections.deque(maxlen=500)
        def peer():
            remote.recv(4096)
            reply=encode(12,0,bytes.fromhex('01004010'))
            remote.sendall(reply+reply+encode(1,1))
            remote.recv(4096)
        thread=threading.Thread(target=peer)
        thread.start()
        try:
            self.assertEqual(session.request(b'\x00\x00',b'\x01\x00'),bytes.fromhex('01004010'))
            self.assertEqual(len(seen),1)
            self.assertEqual(session.tx,1)
        finally:
            thread.join(timeout=2); local.close(); remote.close()

    def test_reject_invalid_setting_before_write(self):
        c=Controller.__new__(Controller)
        c.state={'presets':[],'ambient':1,'focus':False,'button_choices':[]}
        for command,value in [('noise',{'mode':'ambient','level':21}),('eq',255),
                              ('eq_custom',[100]*6),('touch','true'),('auto_off',15),('button',1)]:
            with self.assertRaises(ValueError): c.set(command,value)


if __name__=='__main__': unittest.main()
