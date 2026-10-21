# Sony XM3 Plasmoid

An English-language KDE Plasma 6 widget for controlling **Sony WH-1000XM3** headphones on Linux. It includes a compact panel icon, a three-tab control panel, and a small per-user Bluetooth backend.

The implementation talks directly to the headset over BlueZ RFCOMM. No Android runtime, Sony account, or cloud service is needed. This project is not affiliated with Sony.

## Features

- Battery, firmware, codec and device settings read directly from the headset.
- ANC, wind noise reduction, ambient sound (levels 1–20), off, and focus on voice.
- EQ presets, five-band equalizer and Clear Bass (−10 to +10).
- DSEE HX auto/off, VPT surround and sound position.
- LDAC/SBC switching for the selected headset's PipeWire/PulseAudio card.
- Touch panel, voice guidance and automatic power-off settings.
- Device-reported NC/AMBIENT button assignments.
- **Use phone app** releases the private control connection; **Take control** reconnects it. Neither action intentionally disconnects the audio connection.
- Device readback after setting changes; failures display the actual reported state.
- Hidden scrollbars with mouse-wheel and touchpad scrolling.

### Headset limitations

**EQ, VPT and sound position were rejected under LDAC on the tested headset. Switching to SBC made these controls work.** Select SBC in the Sound tab before using these effects. Codec changes briefly interrupt audio; the widget never changes codecs implicitly to enable an effect.

Connection priority is currently read-only. NC optimizer, adaptive scenes, playback/volume control, firmware updates, voice-language packages and 360 Reality Audio setup are not implemented.

## Compatibility and verification

The only supported model is **WH-1000XM3**, tested with firmware **4.5.2** and MDR V1 protocol **0x4010**, on Debian 13 / Plasma 6.3.6 / BlueZ / PipeWire.

Hardware write/readback tests covered ANC, wind reduction, ambient level, voice focus, EQ presets/custom bands, DSEE, LDAC/SBC switching, VPT, sound position, touch panel, voice guidance and automatic power-off. Widget clicks were also tested through to device readback. Test changes were restored afterward.

Button-assignment options are read from the headset, and a write path is provided, but changing to a non-default assignment has **not** been hardware-tested. Long-term operation, suspend/resume and recovery after the headset powers down are also not yet verified. Readback confirms device settings, not the listener's subjective audio experience.

## Install

Requirements:

- KDE Plasma 6, including `org.kde.plasma.plasma5support` and its executable data engine.
- Python 3.10+, BlueZ, systemd user services and `kpackagetool6`.
- A C compiler and BlueZ development headers.
- `pactl` for codec switching (PipeWire's PulseAudio compatibility server works).

On Debian/Ubuntu, install the additional build/runtime tools if needed:

```bash
sudo apt install gcc libbluetooth-dev bluez pulseaudio-utils
```

Pair and connect your XM3 in the system Bluetooth settings, then run:

```bash
git clone https://github.com/TYBLHQY/sony-xm3-plasmoid.git
cd sony-xm3-plasmoid
python3 install.py --address AA:BB:CC:DD:EE:FF
```

Replace the example address with your headset's address, listed by `bluetoothctl devices`. The installer builds the widget, installs it for the current user, and enables `sony-xm3.service`. No Python packages need to be installed with pip.

Add **Sony WH-1000XM3** using Plasma's **Add Widgets** menu. The interface, preset names and backend messages are in English.

To build without installing or starting a service:

```bash
python3 install.py --build-only
```

This creates `sony-wh1000xm3-0.1.1.plasmoid` for the build machine's architecture. Installing this archive alone installs the widget files; the installer is still needed to configure the backend and device address.

### Installed files

- `~/.local/share/plasma/plasmoids/io.github.tyblhqy.sonyxm3/`
- `~/.config/systemd/user/sony-xm3.service`
- `~/.config/sony-xm3.json`
- `$XDG_RUNTIME_DIR/sony-xm3/control.sock`

The Unix socket is private to the current user. The Bluetooth address stays in the local configuration. Existing installation targets are backed up to `private/backups/` before replacement.

## Command line

Run these from the checkout after installation:

```bash
python3 sonyctl.py status
python3 sonyctl.py noise '{"mode":"anc","level":1,"focus":false}'
python3 sonyctl.py codec '"SBC"'
python3 sonyctl.py eq '16'
python3 sonyctl.py eq_custom '[0,1,0,0,0,0]'
python3 sonyctl.py release
python3 sonyctl.py connect
systemctl --user status sony-xm3.service
journalctl --user -u sony-xm3.service
```

The daemon only takes the control connection when the headset is already connected in BlueZ; it does not pair devices. Releasing control also disables automatic control-channel reconnection until you take control again.

## Development

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
python3 install.py --build-only
```

Tests cover fragmented/escaped frames, checksums, corrupt-frame rejection, replies arriving before ACK, duplicate packets and invalid setting values. An additional replay test uses the upstream XM3 capture corpus when it is present under `references/SonyHeadphonesClient/`; otherwise that test is skipped.

Source layout:

- `package/contents/ui/main.qml`: Plasma interface.
- `controller.py`: XM3 settings and device readback validation.
- `mdr.py`: framed MDR V1 transport and alternating-bit acknowledgements.
- `sonyctl.py`: persistent Bluetooth worker, private Unix IPC and CLI.
- `sdp_channel.c`: discover the MDR V1 RFCOMM service channel.
- `install.py`: build and user-level installation.

## Protocol research and credits

Protocol definitions and test captures were cross-checked against the MIT-licensed [mos9527/SonyHeadphonesClient](https://github.com/mos9527/SonyHeadphonesClient), inspected at commit `8f4808cb635f5a176df0b7b5aea959818be5129e`, its [XM3 hardware notes](https://github.com/mos9527/SonyHeadphonesClient/blob/v1-compat/docs/device-support/WH-1000XM3.md), and [Plutoberth's original client](https://github.com/Plutoberth/SonyHeadphonesClient), inspected at `5620e8ed5deccb957338b54e371b215146080819`.

Local static analysis of Sound Connect 13.3.0 also confirmed the RFCOMM UUID, commands and serialization. Two important XM3 details:

- Noise-control GET reports `ON=0x01`, while a completed SET uses `ADJUSTMENT_COMPLETION=0x11` and the sender's level-adjustment parameter type.
- Automatic power-off uses `SYSTEM_SET_PARAM=0xF8`. The `0xFC` command used by the inspected upstream implementation was acknowledged but did not change the tested device; `0xF8` was verified by readback.

This is an independent Python/QML implementation. No Sony APK, decompiled source, artwork, firmware, native library, personal device address or private capture is included in the repository or widget archive.

## Uninstall

Remove the widget from your panel, then run:

```bash
systemctl --user disable --now sony-xm3.service
kpackagetool6 --type Plasma/Applet --remove io.github.tyblhqy.sonyxm3
rm ~/.config/systemd/user/sony-xm3.service
systemctl --user daemon-reload
```

Optionally remove `~/.config/sony-xm3.json` to delete the saved device address. Bluetooth pairing and the system audio configuration are not removed.

## License

[MIT](LICENSE).
