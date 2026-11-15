import numpy as np
import pytest

from audiotarget import protocol as p
from audiotarget.config import ConfigError, load
from audiotarget.synth import STALE_S, ToneRenderer, gate_on


def test_parse_tone():
    t = p.parse("T 4400 100 35 3")
    assert t == p.Tone(440.0, 1.0, 0.35, 3)


@pytest.mark.parametrize("line", [
    "", "T", "T 4400 100 35", "T 4400 100 35 3 9", "T 4400 101 35 3", "T 99 10 10 0",
    "T 04400 100 35 3", "T -4400 100 35 3", "A 0", "A 4", "Z 2", "H 1 NRF", "X 1",
    "T 4400  100 35 3", "T 4400 100 35 3\x00", "T " + "9" * 70,
])
def test_parse_rejects(line):
    assert p.parse(line) is None


def test_parse_misc():
    assert p.parse("A 3") == p.Route(3)
    assert p.parse("Z 1") == p.Zeroed(True)
    assert p.parse("H 1 nrf") == p.Hello(1, "nrf")


def test_format_cam_clamps():
    assert p.fmt_cam(5, 1234.4, -99999, 2000.6, 12.2) == b"C 5 1234 -45000 2001 12\n"
    assert p.fmt_cam(2**32 + 1, 0, 0, None, 5000) == b"C 1 0 0 0 2000\n"
    assert p.fmt_notarget(7) == b"N 7\n"
    for line in (p.fmt_cam(1, 1, 1, 1, 1), p.fmt_hello()):
        assert len(line) <= p.MAX_LINE + 1


def test_line_assembler():
    a = p.LineAssembler()
    assert a.feed(b"T 4400 1") == []
    assert a.feed(b"00 100 0\r\nA 1\n") == ["T 4400 100 100 0", "A 1"]
    assert a.feed(b"x" * 200 + b"\nA 2\n") == ["A 2"]
    assert a.feed(b"A\x01 1\nA 3\n") == ["A 3"]


def test_tone_renderer_ramps_and_goes_quiet():
    r = ToneRenderer(48000)
    r.update(p.Tone(440.0, 1.0, 0.25, 0), now=0.0)
    out = r.render(480, now=0.01)
    assert out.shape == (480, 2)
    assert abs(out[0, 0]) < 0.05  # ramped from silence, no click
    out = r.render(4800, now=0.05)
    assert np.max(np.abs(out[:, 0])) == pytest.approx(0.8, abs=0.02)
    assert np.max(np.abs(out[:, 1])) == pytest.approx(0.2, abs=0.02)
    out = r.render(480, now=STALE_S + 0.1)
    out = r.render(480, now=STALE_S + 0.2)
    assert np.max(np.abs(out)) == 0.0


def test_gate_patterns():
    assert gate_on(0, 123)
    assert gate_on(p.TONE_FLAG_CANT, 10) and not gate_on(p.TONE_FLAG_CANT, 70)
    assert gate_on(p.TONE_FLAG_LOST, 100) and not gate_on(p.TONE_FLAG_LOST, 200)


def test_detect_profile(tmp_path):
    from audiotarget.config import detect_profile

    f = tmp_path / "model"
    for model, want in [("Raspberry Pi 5 Model B Rev 1.0", "pi5"),
                        ("Raspberry Pi 4 Model B Rev 1.5", "pi4"),
                        ("Raspberry Pi Zero 2 W Rev 1.0", "zero2w"),
                        ("Raspberry Pi 3 Model B Plus Rev 1.3", "zero2w")]:
        f.write_bytes(model.encode() + b"\x00")
        assert detect_profile(str(f)) == want
    assert detect_profile(str(tmp_path / "missing")) == "zero2w"


def test_config(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('profile = "pi5"\n[camera]\nbackend = "v4l2"\ndevice = 1\nhfov_deg = 30\n')
    cfg = load(f)
    assert cfg.camera.device == "1"
    assert cfg.resolved_camera().width == 1920
    f.write_text('[camera]\nhfov_deg = 30\nbogus = 1\n')
    with pytest.raises(ConfigError):
        load(f)
    f.write_text('[camera]\nhfov_deg = "wide"\n')
    with pytest.raises(ConfigError):
        load(f)
    f.write_text('[camera]\n')
    with pytest.raises(ConfigError):
        load(f)  # no field of view
