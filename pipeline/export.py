"""Exporta as segmentações revisadas para um dataset YOLO-seg.

Cada 'record' = uma imagem aceita com sua classe e polígono (em pixels).
Imagens entram por SYMLINK (não duplica os ~5GB de fotos). Split train/val.
"""
from __future__ import annotations
import os, random, yaml
from pathlib import Path


def _poly_line(class_id: int, polygon_px, w: int, h: int) -> str | None:
    """Linha YOLO-seg: 'cls x1 y1 x2 y2 ...' normalizado [0,1]. None se degenerado."""
    if polygon_px is None or len(polygon_px) < 3:
        return None
    coords = []
    for x, y in polygon_px:
        coords.append(f"{min(max(x / w, 0.0), 1.0):.6f}")
        coords.append(f"{min(max(y / h, 0.0), 1.0):.6f}")
    return f"{class_id} " + " ".join(coords)


def build_dataset(records: list[dict], out_dir: str, class_names: list[str],
                  val_frac: float = 0.2, seed: int = 42) -> dict:
    """records: [{image_path, class_id, polygon, w, h}]. Gera dataset YOLO-seg.

    Estrutura: out_dir/images/{train,val}/ (symlinks) + labels/{train,val}/ + data.yaml
    Retorna resumo {train, val, skipped, data_yaml}.
    """
    out = Path(out_dir)
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        d = out / sub
        if d.exists():                       # limpa split antigo (evita mistura train/val)
            for f in d.iterdir():
                f.unlink()
        d.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    recs = [r for r in records if r.get("polygon") is not None and len(r["polygon"]) >= 3]
    rng.shuffle(recs)
    n_val = int(len(recs) * val_frac)
    counts = {"train": 0, "val": 0, "skipped": len(records) - len(recs)}

    for i, r in enumerate(recs):
        split = "val" if i < n_val else "train"
        src = Path(r["image_path"]).resolve()
        stem = src.stem
        link = out / f"images/{split}/{src.name}"
        if not link.exists():
            os.symlink(src, link)
        line = _poly_line(r["class_id"], r["polygon"], r["w"], r["h"])
        label = out / f"labels/{split}/{stem}.txt"
        label.write_text((line + "\n") if line else "")
        counts[split] += 1

    data_yaml = out / "data.yaml"
    data_yaml.write_text(yaml.safe_dump({
        "path": str(out.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {i: n for i, n in enumerate(class_names)},
    }, sort_keys=False, allow_unicode=True))
    counts["data_yaml"] = str(data_yaml)
    return counts
