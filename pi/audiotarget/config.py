"""Configuration (TOML). See config.example.toml for every option."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

# Defaults by board. Smaller boards get a smaller frame so detection keeps up.
PROFILES: dict[str, dict[str, int]] = {
    "zero2w": {"width": 1280, "height": 720, "fps": 30},  # also Pi 3
    "pi4": {"width": 1600, "height": 900, "fps": 40},
    "pi5": {"width": 1920, "height": 1080, "fps": 50},    # also Pi 500
}


def detect_profile(model_path: str = "/proc/device-tree/model") -> str:
    """Pick a profile from the board model string (falls back to the smallest)."""
    try:
        model = Path(model_path).read_bytes().decode("ascii", "replace").strip("\x00 \n")
    except OSError:
        return "zero2w"
    if "Raspberry Pi 5" in model or "Raspberry Pi 500" in model:
        return "pi5"
    if "Raspberry Pi 4" in model or "Raspberry Pi 400" in model or "Compute Module 4" in model:
        return "pi4"
    return "zero2w"


@dataclass
class CameraCfg:
    backend: str = "picamera2"  # "picamera2" (ribbon) or "v4l2" (USB)
    device: str = "0"
    width: int = 0
    height: int = 0
    fps: int = 0
    hfov_deg: float = 0.0
    calibration: str = ""
    exposure_latency_ms: float = 15.0
    rotate_180: bool = False


@dataclass
class DetectorCfg:
    type: str = "card"  # "card" (markers, then rings), "aruco", "bullseye", "onnx"
    card_size_mm: float = 200.0
    marker_size_mm: float = 40.0
    marker_margin_mm: float = 8.0
    marker_id_base: int = 0
    bullseye_outer_mm: float = 120.0
    onnx_model: str = ""
    onnx_input: int = 640
    onnx_class: int = 0
    onnx_conf: float = 0.4
    onnx_target_width_mm: float = 0.0


@dataclass
class LinkCfg:
    mode: str = "both"  # "serial", "ble", "both"
    serial_port: str = "/dev/serial0"
    baud: int = 115200
    ble_name: str = "AudioTarget"
    ble_address: str = ""


@dataclass
class AudioCfg:
    bluetooth_tones: bool = True
    device: str = ""
    sample_rate: int = 48000


@dataclass
class UiCfg:
    enabled: bool = False  # spoken menu (on in the SD-card image)
    voice: str = "en-us"
    speech_rate: int = 175  # words per minute
    long_press_ms: int = 800  # hold Select this long = Back (for 3-button setups)
    announce: bool = True  # speak gun-module / camera status changes


SECTIONS = ("camera", "detector", "link", "audio", "ui")


@dataclass
class Config:
    profile: str = "auto"  # "auto" reads the board model; or zero2w / pi4 / pi5
    camera: CameraCfg = field(default_factory=CameraCfg)
    detector: DetectorCfg = field(default_factory=DetectorCfg)
    link: LinkCfg = field(default_factory=LinkCfg)
    audio: AudioCfg = field(default_factory=AudioCfg)
    ui: UiCfg = field(default_factory=UiCfg)

    def resolved_camera(self) -> CameraCfg:
        """Camera settings with profile defaults filled in."""
        prof = PROFILES[detect_profile() if self.profile == "auto" else self.profile]
        c = self.camera
        return CameraCfg(**{**c.__dict__,
                            "width": c.width or prof["width"],
                            "height": c.height or prof["height"],
                            "fps": c.fps or prof["fps"]})


class ConfigError(ValueError):
    pass


def _fill(cls: type, data: dict[str, Any], section: str) -> Any:
    known = {f.name: f for f in fields(cls)}
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in known:
            raise ConfigError(f"[{section}] unknown option '{key}'")
        default = known[key].default
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, float):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            value = float(value) if ok else value
        elif isinstance(default, int):
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif isinstance(default, str):
            if isinstance(value, int) and not isinstance(value, bool):
                value = str(value)
            ok = isinstance(value, str)
        else:
            ok = True
        if not ok:
            raise ConfigError(f"[{section}] '{key}' has the wrong type")
        kwargs[key] = value
    return cls(**kwargs)


def validate(cfg: Config) -> None:
    if cfg.profile != "auto" and cfg.profile not in PROFILES:
        raise ConfigError(f"profile must be 'auto' or one of {sorted(PROFILES)}")
    if cfg.camera.backend not in ("picamera2", "v4l2"):
        raise ConfigError("camera.backend must be 'picamera2' or 'v4l2'")
    if cfg.camera.hfov_deg <= 0 and not cfg.camera.calibration:
        raise ConfigError("set camera.hfov_deg (lens field of view) or camera.calibration")
    if cfg.detector.type not in ("card", "aruco", "bullseye", "onnx"):
        raise ConfigError("detector.type must be 'card', 'aruco', 'bullseye' or 'onnx'")
    if cfg.detector.type == "onnx" and not cfg.detector.onnx_model:
        raise ConfigError("detector.onnx_model is required for the onnx detector")
    if cfg.link.mode not in ("serial", "ble", "both", "none"):
        raise ConfigError("link.mode must be 'serial', 'ble', 'both' or 'none'")
    d = cfg.detector
    if not (0 < d.marker_size_mm and 2 * (d.marker_size_mm + d.marker_margin_mm) < d.card_size_mm):
        raise ConfigError("markers don't fit on the card: check card_size_mm / marker_size_mm")


def load(path: str | Path | None) -> Config:
    data: dict[str, Any] = {}
    if path:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    top = {k: v for k, v in data.items() if not isinstance(v, dict)}
    unknown = set(data) - {"profile", *SECTIONS}
    if unknown:
        raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown))}")
    cfg = Config(
        profile=str(top.get("profile", "auto")),
        camera=_fill(CameraCfg, data.get("camera", {}), "camera"),
        detector=_fill(DetectorCfg, data.get("detector", {}), "detector"),
        link=_fill(LinkCfg, data.get("link", {}), "link"),
        audio=_fill(AudioCfg, data.get("audio", {}), "audio"),
        ui=_fill(UiCfg, data.get("ui", {}), "ui"),
    )
    validate(cfg)
    return cfg


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    if any(ord(c) < 0x20 for c in s):
        raise ConfigError("control characters are not allowed in settings")
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dumps(cfg: Config) -> str:
    lines = [f"profile = {_toml_value(cfg.profile)}"]
    for name in SECTIONS:
        lines.append(f"\n[{name}]")
        for f in fields(getattr(cfg, name)):
            lines.append(f"{f.name} = {_toml_value(getattr(getattr(cfg, name), f.name))}")
    return "\n".join(lines) + "\n"


def save(cfg: Config, path: str | Path) -> None:
    """Validate, then atomically replace the config file."""
    validate(cfg)
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(dumps(cfg), encoding="utf-8")
    tmp.replace(path)
