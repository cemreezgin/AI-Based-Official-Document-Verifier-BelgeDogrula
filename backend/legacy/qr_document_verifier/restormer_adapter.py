"""Resmî Restormer ağırlıklarını yerel olarak çalıştıran isteğe bağlı katman."""
from __future__ import annotations

import os
import hashlib
from pathlib import Path
from runpy import run_path

import cv2
import numpy as np


class RestormerUnavailable(RuntimeError):
    pass


TASKS = {
    "motion_deblur": (
        "Motion_Deblurring/pretrained_models/motion_deblurring.pth",
        "WithBias",
        "194e38fb5b607c9dc5a5b3e08e65b2e79ee2bf0ef5048e0612f6b2ff2f79da31",
    ),
    "real_denoise": (
        "Denoising/pretrained_models/real_denoising.pth",
        "BiasFree",
        "4cae18bed8a291b9a5deeeab48756bbe6f61fcf7f31a4cca0969b24608601387",
    ),
}

ARCHITECTURE_SHA256 = (
    "3be243fa3c8e2cb2c9459eeac062b04d6084dbcc328292dae1c3e52ba6f7434a"
)
_MODEL_CACHE: dict[tuple[str, str], object] = {}


def restormer_home() -> Path:
    configured = os.environ.get("RESTORMER_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent / "third_party" / "Restormer"


def available_tasks() -> list[str]:
    home = restormer_home()
    architecture = home / "basicsr/models/archs/restormer_arch.py"
    if not architecture.is_file():
        return []
    return [
        name for name, (relative, _, _) in TASKS.items()
        if (home / relative).is_file()
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_hash(path: Path, expected: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise RestormerUnavailable(
            f"Restormer dosya bütünlüğü doğrulanamadı: {path.name}"
        )


def _torch():
    try:
        import torch
    except ImportError as exc:
        raise RestormerUnavailable(
            "Restormer için PyTorch kurulu değil."
        ) from exc
    return torch


def _device(torch):
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _load_model(task: str):
    if task not in TASKS:
        raise ValueError(f"Desteklenmeyen Restormer görevi: {task}")
    torch = _torch()
    device = _device(torch)
    cache_key = (task, str(device))
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key], torch, device

    home = restormer_home()
    architecture = home / "basicsr/models/archs/restormer_arch.py"
    relative_weights, layer_norm, weights_sha256 = TASKS[task]
    weights = home / relative_weights
    if not architecture.is_file() or not weights.is_file():
        raise RestormerUnavailable(
            f"{task} modeli bulunamadı. RESTORMER_HOME={home}"
        )
    _require_hash(architecture, ARCHITECTURE_SHA256)
    _require_hash(weights, weights_sha256)

    parameters = {
        "inp_channels": 3,
        "out_channels": 3,
        "dim": 48,
        "num_blocks": [4, 6, 6, 8],
        "num_refinement_blocks": 4,
        "heads": [1, 2, 4, 8],
        "ffn_expansion_factor": 2.66,
        "bias": False,
        "LayerNorm_type": layer_norm,
        "dual_pixel_task": False,
    }
    model_class = run_path(str(architecture))["Restormer"]
    model = model_class(**parameters)
    try:
        checkpoint = torch.load(
            str(weights), map_location=device, weights_only=True
        )
    except TypeError:
        checkpoint = torch.load(str(weights), map_location=device)
    model.load_state_dict(checkpoint["params"])
    model.to(device).eval()
    _MODEL_CACHE[cache_key] = model
    return model, torch, device


def restore(image: np.ndarray, task: str) -> np.ndarray:
    """Restormer çıktısını üretir; QR içeriği hakkında hiçbir tahmin yapmaz."""
    model, torch, device = _load_model(task)
    source = image
    if source.ndim == 2:
        source = cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
    rgb = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
    tensor = (
        torch.from_numpy(np.ascontiguousarray(rgb))
        .float()
        .div(255.0)
        .permute(2, 0, 1)
        .unsqueeze(0)
        .to(device)
    )
    height, width = tensor.shape[-2:]
    pad_h = (8 - height % 8) % 8
    pad_w = (8 - width % 8) % 8
    if pad_h or pad_w:
        tensor = torch.nn.functional.pad(
            tensor, (0, pad_w, 0, pad_h), mode="reflect"
        )
    with torch.inference_mode():
        restored = torch.clamp(model(tensor), 0, 1)
    restored = restored[..., :height, :width]
    output = (
        restored[0]
        .permute(1, 2, 0)
        .mul(255)
        .round()
        .byte()
        .cpu()
        .numpy()
    )
    return cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
