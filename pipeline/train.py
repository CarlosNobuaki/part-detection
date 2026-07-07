"""Treino do detector/segmentador YOLO26-seg a partir do dataset gerado.

Modelo final autossuficiente: na inferência roda SÓ o YOLO26-seg (sem SAM),
devolvendo caixa + máscara da peça.
"""
from __future__ import annotations
from ultralytics import YOLO


def train(data_yaml: str, model: str = "yolo26n-seg.pt", epochs: int = 100,
          imgsz: int = 640, device: str | None = None, name: str = "pecas",
          **kwargs):
    """Treina YOLO26-seg. device=None deixa o ultralytics escolher (MPS no M3)."""
    yolo = YOLO(model)
    return yolo.train(data=data_yaml, epochs=epochs, imgsz=imgsz,
                      device=device, name=name, **kwargs)


def predict(weights: str, source, conf: float = 0.25, **kwargs):
    """Inferência com o modelo treinado (sem SAM). Retorna results do ultralytics."""
    return YOLO(weights)(source, conf=conf, **kwargs)
