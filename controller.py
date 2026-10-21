"""XM3 state, supported settings, and strict device readback checks."""
import copy
import time
from mdr import Session

PRESETS = {0:'Off',16:'Bright',17:'Excited',18:'Mellow',19:'Relaxed',20:'Vocal',21:'Treble Boost',
           22:'Bass Boost',23:'Speech',160:'Manual',161:'Custom 1',162:'Custom 2'}
CODECS = {0:'Negotiating',1:'SBC',2:'AAC',16:'LDAC',32:'aptX',33:'aptX HD'}


def initial_state():
    return dict(connected=False, busy=False, model='WH-1000XM3', error='', message='',
                updated_at=0, firmware='', codec='', battery=None, mode='', ambient=0,
                focus=False, eq_preset=0, eq_bands=[0]*6, presets=[], dsee=None,
                touch=None, guidance=None, auto_off=None, quality=None,
                vpt=None, position=None, button=None, button_choices=[], functions=[])


class Controller:
    def __init__(self, address, channel, publish):
        self.state = initial_state()
        self.publish = publish
        self.alerts = []
        self.session = Session(address, channel, self.receive)

    def emit(self):
        self.publish(copy.deepcopy(self.state))

    def receive(self, kind, p):
        if len(p) < 2:
            return
        s = self.state
        cmd, selector = p[:2]
        if kind == 14:
            if cmd in (0x47,0x49) and p[1:3] == b'\x01\x01' and len(p) == 4:
                s['guidance'] = bool(p[3])
        elif kind == 12:
            if cmd == 5 and selector in (1,2) and len(p) >= 3+p[2]:
                s['model' if selector == 1 else 'firmware'] = p[3:3+p[2]].decode('utf8',errors='replace')
            elif cmd == 7 and len(p) >= 3:
                s['functions'] = list(p[3:3+p[2]])
            elif cmd in (0x11,0x13) and selector == 0 and len(p) == 4:
                s['battery'], s['charging'] = p[2], bool(p[3])
            elif cmd in (0x19,0x1b) and len(p) >= 3:
                s['codec'] = CODECS.get(p[2], f'Unknown ({p[2]})')
            elif cmd in (0x67,0x69) and selector == 2 and len(p) == 8:
                s['mode'] = 'off' if p[2] == 0 else ('anc' if p[4]==2 else 'wind' if p[4]==1 else 'ambient')
                s['ambient'], s['focus'] = p[7], bool(p[6])
            elif cmd in (0x57,0x59) and selector == 1 and len(p) >= 4+p[3]:
                s['eq_preset'], s['eq_bands'] = p[2], [b-10 for b in p[4:4+p[3]]]
            elif cmd == 0x51 and selector == 1 and len(p) >= 5:
                if p[2:4] != b'\x06\x15':
                    raise ValueError('Expected the XM3 6-channel, 21-step equalizer')
                presets, offset = [], 5
                for _ in range(p[4]):
                    preset, length = p[offset:offset+2]
                    offset += 2
                    name = p[offset:offset+length].decode('utf8',errors='replace')
                    offset += length
                    presets.append({'value':preset,'text':PRESETS.get(preset,name or str(preset))})
                s['presets'] = presets
            elif cmd in (0xe7,0xe9) and len(p) == 4:
                if selector == 2:
                    s['dsee'] = bool(p[3])
                elif selector == 1:
                    s['quality'] = p[3]
            elif cmd in (0x47,0x49) and len(p) == 3:
                if selector in (1,2):
                    s['vpt' if selector == 1 else 'position'] = p[2]
            elif cmd in (0xd7,0xd9) and len(p) == 4:
                if selector == 0xd2 and p[2] == 1:
                    s['touch'] = bool(p[3])
                elif selector == 0xd1 and p[2] == 2:
                    s['button'] = p[3]
            elif cmd == 0xd1 and selector == 0xd1:
                # XM3 list capability: title type+length+name, summary, setting type,
                # element count, then length-prefixed element strings.
                offset = 4+p[3]
                offset += 1+p[offset]
                setting, count = p[offset:offset+2]
                offset += 2
                choices = []
                if setting == 2:
                    for i in range(count):
                        fmt, n = p[offset:offset+2]
                        offset += 2
                        name = p[offset:offset+n].decode('utf8',errors='replace')
                        offset += n
                        n = p[offset]
                        offset += 1+n
                        text = ('ANC / Ambient' if 'NCASM' in name else
                                'Tencent Xiaowei' if 'TENCENT' in name else
                                'Google Assistant' if 'GOOGLE' in name else
                                'Amazon Alexa' if 'ALEXA' in name else name)
                        choices.append({'value':i,'text':text})
                s['button_choices'] = choices
            elif cmd in (0xf7,0xf9) and selector == 4 and len(p) == 5:
                s['auto_off'] = p[3]
                s['auto_off_selected'] = p[4]
            elif cmd == 0x99 and selector == 1 and len(p) >= 4:
                self.alerts.append(p[2])
        s['updated_at'] = time.time()
        self.emit()

    def get(self, cmd, selector, kind=12, extra=b''):
        return self.session.request(bytes([cmd,selector])+extra, bytes([cmd+1,selector])+extra if kind == 14 else bytes([cmd+1,selector]),kind)

    def start(self):
        p = self.get(0,0)
        if p != bytes.fromhex('01004010'):
            raise ValueError(f'Only XM3 MDR 0x4010 is supported; received {p.hex()}')
        self.get(4,1)
        if self.state['model'] != 'WH-1000XM3':
            raise ValueError('Only WH-1000XM3 is supported')
        self.get(4,2)
        self.get(6,0)
        self.get(0x50,1,extra=b'\x01')
        self.get(0xd0,0xd1,extra=b'\x01')
        self.refresh()
        self.state['connected'] = True
        self.emit()

    def refresh(self):
        for cmd,selector in [(0x10,0),(0x18,0),(0x66,2),(0x56,1),
                             (0xe6,2),(0xe6,1),(0xd6,0xd2),(0xd6,0xd1),
                             (0xf6,4),(0x46,1),(0x46,2)]:
            self.get(cmd,selector)
        if 0x39 in self.state['functions']:
            self.get(0x46,1,kind=14,extra=b'\x01')

    def flush_alerts(self):
        # Do not accept a codec-disconnection prompt implicitly. XM3 can still
        # apply EQ while retaining the current connection; readback decides.
        while self.alerts:
            message = self.alerts.pop(0)
            self.session.request(bytes([0x9a,1,message,0]))

    def set(self, command, value):
        s = self.state
        kind = 12
        if command == 'noise':
            if not isinstance(value,dict) or value.get('mode') not in ('anc','wind','ambient','off'):
                raise ValueError('Invalid noise-control mode')
            mode = value['mode']
            level = value.get('level', max(1,s['ambient']))
            focus = value.get('focus',s['focus'])
            if type(level) is not int or not 1 <= level <= 20 or type(focus) is not bool:
                raise ValueError('Ambient sound level must be between 1 and 20')
            # GET reports ON (1), SET must use ADJUSTMENT_COMPLETION (17).
            # The XM3 sender uses LEVEL_ADJUSTMENT (1), even though GET reports
            # the device's DUAL_SINGLE_OFF capability (2).
            raw = bytes([0x68,2,17 if mode!='off' else 0,1,2 if mode=='anc' else 1 if mode=='wind' else 0,1,int(focus),level if mode=='ambient' else 0])
            getter = (0x66,2)
            verify = lambda: s['mode']==mode and (mode!='ambient' or (s['ambient']==level and s['focus']==focus))
        elif command in ('eq','eq_custom'):
            allowed = [p['value'] for p in s['presets']]
            if command == 'eq':
                if type(value) is not int or value not in allowed:
                    raise ValueError('This EQ preset is not supported by the headset')
                raw = bytes([0x58,1,value,0])
                verify = lambda: s['eq_preset']==value
            else:
                if not isinstance(value,list) or len(value)!=6 or any(type(v) is not int or not -10<=v<=10 for v in value):
                    raise ValueError('EQ requires Clear Bass and 5 bands, each from -10 to +10')
                self.session.request(bytes([0x58,1,160,0]))
                self.flush_alerts()
                raw = bytes([0x58,1,255,6]+[v+10 for v in value])
                verify = lambda: s['eq_preset']==160 and s['eq_bands']==value
            getter = (0x56,1)
        elif command in ('dsee','touch','guidance'):
            if type(value) is not bool:
                raise ValueError('Expected a boolean value')
            raw = bytes({'dsee':[0xe8,2,0,int(value)],'touch':[0xd8,0xd2,1,int(value)],
                         'guidance':[0x48,1,1,int(value)]}[command])
            getter = {'dsee':(0xe6,2),'touch':(0xd6,0xd2),'guidance':(0x46,1)}[command]
            kind = 14 if command=='guidance' else 12
            verify = lambda: s[command]==value
        elif command == 'auto_off':
            if type(value) is not int or value not in (0,1,2,3,17):
                raise ValueError('Invalid auto power-off time')
            selected = value if value !=17 else s.get('auto_off_selected',0)
            # Sound Connect 13.3.0 q00/b -> tm0/r3 uses SYSTEM_SET_PARAM,
            # not SET_EXTENDED_PARAM used by the upstream library.
            raw = bytes([0xf8,4,1,value,selected])
            getter = (0xf6,4)
            verify = lambda: s['auto_off']==value
        elif command in ('vpt','position','button'):
            allowed = {'vpt':(0,1,2,3,4),'position':(0,1,2,3,17,18),
                       'button':tuple(p['value'] for p in s['button_choices'])}[command]
            if type(value) is not int or value not in allowed:
                raise ValueError('Invalid setting value')
            raw = bytes({'vpt':[0x48,1,value],'position':[0x48,2,value],
                         'button':[0xd8,0xd1,2,value]}[command])
            getter = {'vpt':(0x46,1),'position':(0x46,2),'button':(0xd6,0xd1)}[command]
            verify = lambda: s[command]==value
        else:
            raise ValueError('Unsupported command')
        self.session.request(raw,kind=kind)
        self.flush_alerts()
        self.get(*getter,kind=kind,extra=b'\x01' if kind==14 else b'')
        # Drain other settings changed as a consequence (VPT/EQ can be exclusive).
        self.refresh()
        self.flush_alerts()
        if not verify():
            raise ValueError('The headset did not apply the requested setting. The actual value is shown. EQ/VPT may be restricted by LDAC or other effects.')
        return 'Verified by the headset'
