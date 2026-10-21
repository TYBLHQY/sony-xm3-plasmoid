"""Read-only XM3 inventory. Invoke with ADDRESS, channel from sdp-channel."""
import json
import sys
from mdr import Session

def probe(address, channel):
    session = Session(address, channel)
    result = {}
    try:
        for name, request in [('protocol','0000'), ('model','0401'), ('firmware','0402'),
                              ('functions','0600'), ('battery','1000'), ('codec','1800'),
                              ('noise','6602'), ('eq_capability','500101'), ('eq','5601'),
                              ('dsee','e602'), ('quality','e601'), ('auto_off','fa04'),
                              ('vpt','4601'), ('position','4602'),
                              ('button_capability','d0d101'), ('button','d6d1'),
                              ('touch_capability','d0d201'), ('touch','d6d2')]:
            raw = bytes.fromhex(request)
            try:
                result[name] = session.request(raw, bytes([raw[0] + 1,raw[1]])).hex()
            except TimeoutError as exc:
                result[name] = {'error': str(exc)}
        result['trace'] = list(session.trace)
    finally:
        session.close()
    return result

if __name__ == '__main__':
    print(json.dumps(probe(sys.argv[1], int(sys.argv[2])), ensure_ascii=False, indent=2))
