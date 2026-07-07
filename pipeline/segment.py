"""Segmentação da peça principal com SAM (agnóstico: sam2.1_b.pt ou sam3.pt).

Estratégia validada: prompt de 1 ponto (centro por padrão, ou clique do usuário),
multimask_output=True -> escolhe o MAIOR escopo (a peça inteira, não um sub-pedaço).
Rápido (~0.1-0.7s/img após encode). SAM só é usado aqui (rotulagem offline).
"""
from __future__ import annotations
import cv2
import numpy as np
from ultralytics.models.sam.predict import SAM2Predictor, SAM3Predictor

_CACHE: dict[str, SAM2Predictor] = {}


def get_predictor(weights: str = "sam2.1_b.pt", imgsz: int = 1024) -> SAM2Predictor:
    """Carrega e cacheia o predictor. Troque weights p/ 'sam3.pt' quando tiver o peso."""
    if weights not in _CACHE:
        cls = SAM3Predictor if "sam3" in weights else SAM2Predictor
        overrides = dict(model=weights, task="segment", mode="predict",
                         imgsz=imgsz, save=False, verbose=False)
        pred = cls(overrides=overrides)
        pred.setup_model(model=None)
        _CACHE[weights] = pred
    return _CACHE[weights]


def segment_main_part(image_path: str, weights: str = "sam2.1_b.pt",
                      point: tuple[int, int] | None = None) -> dict | None:
    """Segmenta a peça principal. `point` (x,y) opcional p/ re-segmentar via clique.

    Retorna dict(mask bool HxW, bbox [x1,y1,x2,y2], polygon Nx2, area_frac) ou None.
    """
    img = cv2.imread(image_path)
    if img is None:
        return None
    h, w = img.shape[:2]
    px, py = point or (w // 2, h // 2)
    pred = get_predictor(weights)
    pred.set_image(img)
    res = pred(points=[[int(px), int(py)]], labels=[1], multimask_output=True)
    if not res or res[0].masks is None or len(res[0].masks) == 0:
        return None

    data = res[0].masks.data.cpu().numpy().astype(bool)      # (N, H, W)
    best = int(data.reshape(len(data), -1).sum(axis=1).argmax())  # maior escopo
    mask = data[best]

    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    polygon = _largest_contour(mask)
    return {"mask": mask, "bbox": bbox, "polygon": polygon,
            "area_frac": float(mask.mean())}


def _largest_contour(mask: np.ndarray, eps_frac: float = 0.002) -> np.ndarray:
    """Maior contorno externo da máscara, simplificado. Retorna (N,2) em pixels."""
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return np.empty((0, 2), dtype=int)
    c = max(cnts, key=cv2.contourArea)
    eps = eps_frac * cv2.arcLength(c, True)
    return cv2.approxPolyDP(c, eps, True).reshape(-1, 2)


def overlay(image_path: str, mask: np.ndarray, color=(0, 255, 0), alpha=0.45) -> np.ndarray:
    """Imagem RGB com a máscara sobreposta (preview/revisão)."""
    img = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
    tint = np.zeros_like(img); tint[mask] = color
    return np.where(mask[..., None], (img * (1 - alpha) + tint * alpha).astype(np.uint8), img)
