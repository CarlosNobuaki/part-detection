"""Painel de rotulagem: SAM segmenta a peça principal -> revisão -> dataset -> treino.

Rodar:  .venv/bin/streamlit run app.py
"""
from __future__ import annotations
import json
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from streamlit_image_coordinates import streamlit_image_coordinates

from pipeline.segment import segment_main_part, overlay
from pipeline.export import build_dataset
from pipeline import train as trainer

ROOT = Path(__file__).parent
IMAGES = ROOT / "images"
PREVIEWS = ROOT / "data" / "previews"
RECORDS = ROOT / "data" / "records"
DATASET = ROOT / "data" / "dataset"
for d in (PREVIEWS, RECORDS, DATASET):
    d.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Identificador de peças", layout="wide")
ss = st.session_state
ss.setdefault("records", {})   # folder -> [record]
ss.setdefault("idx", 0)


def list_folders() -> list[str]:
    return sorted(p.name for p in IMAGES.iterdir() if p.is_dir())


def list_images(folder: str) -> list[Path]:
    return sorted((IMAGES / folder).glob("*.jpg"))


PREVIEW_MAX = 720   # lado máx. do preview; usado p/ mapear clique -> pixels originais


def preview_scale(w: int, h: int) -> float:
    return min(PREVIEW_MAX / max(w, h), 1.0)


def save_preview(folder: str, image_path: str, mask: np.ndarray | None) -> str:
    """Salva preview ≤720px. Com máscara -> overlay; sem -> imagem reduzida (p/ clique)."""
    ov = overlay(image_path, mask) if mask is not None else \
        cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
    h, w = ov.shape[:2]
    s = preview_scale(w, h)
    if s < 1:
        ov = cv2.resize(ov, (int(w * s), int(h * s)))
    outdir = PREVIEWS / folder
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / (Path(image_path).stem + ".jpg")
    cv2.imwrite(str(out), cv2.cvtColor(ov, cv2.COLOR_RGB2BGR))
    return str(out)


def records_path(folder: str) -> Path:
    return RECORDS / f"{folder}.json"


def persist(folder: str):
    records_path(folder).write_text(json.dumps(ss.records[folder], ensure_ascii=False))


def load_records(folder: str):
    p = records_path(folder)
    if p.exists():
        ss.records[folder] = json.loads(p.read_text())


def segment_one(folder: str, image_path: str, name: str, point=None) -> dict:
    r = segment_main_part(image_path, weights=ss.weights, point=point)
    img = cv2.imread(image_path); h, w = img.shape[:2]
    if r is None:
        return {"image_path": image_path, "name": name, "polygon": None,
                "bbox": None, "w": w, "h": h, "area_frac": 0.0,
                "accepted": False, "preview": save_preview(folder, image_path, None)}
    return {"image_path": image_path, "name": name,
            "polygon": r["polygon"].tolist(), "bbox": r["bbox"], "w": w, "h": h,
            "area_frac": r["area_frac"], "accepted": True,
            "preview": save_preview(folder, image_path, r["mask"])}


# ------------------------------------------------------------------ sidebar
st.sidebar.header("1 · Configuração")
folders = list_folders()
folder = st.sidebar.selectbox("Pasta da peça", folders)
default_name = folder
part_name = st.sidebar.text_input("Nome da peça (classe)", value=default_name)
ss.weights = st.sidebar.text_input("Peso SAM", value="sam2.1_b.pt",
                                    help="Troque p/ sam3.pt quando tiver o peso.")
limit = st.sidebar.number_input("Limitar nº de imagens (0 = todas)", 0, 5000, 0)

if st.sidebar.button("▶ Segmentar pasta", type="primary"):
    imgs = list_images(folder)
    if limit:
        imgs = imgs[:limit]
    prog = st.sidebar.progress(0.0, "Segmentando…")
    recs = []
    for i, p in enumerate(imgs, 1):
        recs.append(segment_one(folder, str(p), part_name))
        prog.progress(i / len(imgs), f"Segmentando {i}/{len(imgs)}")
    ss.records[folder] = recs
    persist(folder)
    ss.idx = 0
    prog.empty()
    st.sidebar.success(f"{len(recs)} imagens segmentadas.")

if folder not in ss.records:
    load_records(folder)

# ------------------------------------------------------------------ review
st.title("Identificador de peças — revisão")
recs = ss.records.get(folder)
if not recs:
    st.info("Selecione uma pasta e clique **Segmentar pasta** na barra lateral.")
    st.stop()

n = len(recs)
ok = sum(r["accepted"] for r in recs)
st.caption(f"Pasta **{folder}** · {n} imagens · {ok} aceitas · {n - ok} rejeitadas/falhas")

ss.idx = int(st.slider("Imagem", 0, n - 1, min(ss.idx, n - 1)))
rec = recs[ss.idx]

col1, col2 = st.columns([3, 2])
with col1:
    st.caption("👆 Clique sobre a peça para re-segmentar naquele ponto (ou use ↻).")
    if rec["preview"] and Path(rec["preview"]).exists():
        if not rec["accepted"] and rec["polygon"] is None:
            st.warning("Sem máscara (falhou). Clique na peça para apontar ou rejeite.")
        clk = streamlit_image_coordinates(rec["preview"], key=f"clk_{folder}_{ss.idx}")
        if clk:
            sig = (folder, ss.idx, int(clk["x"]), int(clk["y"]))
            if ss.get("last_click") != sig:
                ss["last_click"] = sig
                s = preview_scale(rec["w"], rec["h"])            # clique(preview) -> original
                pt = (int(clk["x"] / s), int(clk["y"] / s))
                recs[ss.idx] = segment_one(folder, rec["image_path"], rec["name"], point=pt)
                persist(folder); st.rerun()
    else:
        st.image(rec["image_path"], use_container_width=True)

with col2:
    st.metric("Área da máscara", f"{rec['area_frac']:.1%}")
    _old = (rec["name"], rec["accepted"])
    rec["name"] = st.text_input("Nome da peça principal", value=rec["name"],
                                key=f"name_{folder}_{ss.idx}")
    rec["accepted"] = st.checkbox("Aceitar esta segmentação", value=rec["accepted"],
                                  key=f"acc_{folder}_{ss.idx}")
    if (rec["name"], rec["accepted"]) != _old:
        persist(folder)                       # auto-salva edições de nome/aceite
    c1, c2, c3 = st.columns(3)
    if c1.button("◀ Anterior") and ss.idx > 0:
        ss.idx -= 1; st.rerun()
    if c2.button("Próxima ▶") and ss.idx < n - 1:
        ss.idx += 1; st.rerun()
    if c3.button("↻ Re-segmentar"):
        recs[ss.idx] = segment_one(folder, rec["image_path"], rec["name"])
        persist(folder); st.rerun()
    if st.button("💾 Salvar revisão desta pasta"):
        persist(folder); st.success("Revisão salva.")

# ------------------------------------------------------------------ export + treino
st.divider()
st.header("2 · Exportar dataset + treinar")
st.write("Gera dataset YOLO-seg com **todas as pastas já revisadas** e treina o modelo.")

if st.button("📦 Exportar dataset YOLO-seg"):
    for f in list_folders():
        if f not in ss.records:           # não sobrescrever edições da sessão atual
            load_records(f)
    all_names, name_to_id = [], {}
    records_out = []
    for f, rs in ss.records.items():
        for r in rs:
            if not r["accepted"] or r["polygon"] is None:
                continue
            if r["name"] not in name_to_id:
                name_to_id[r["name"]] = len(all_names); all_names.append(r["name"])
            records_out.append({"image_path": r["image_path"],
                                "class_id": name_to_id[r["name"]],
                                "polygon": r["polygon"], "w": r["w"], "h": r["h"]})
    summary = build_dataset(records_out, str(DATASET), all_names)
    ss["data_yaml"] = summary["data_yaml"]
    st.success(f"Dataset: {summary['train']} treino / {summary['val']} val · "
               f"classes={all_names}")
    st.code(summary["data_yaml"])

epochs = st.number_input("Épocas", 1, 500, 100)
model_name = st.selectbox("Modelo", ["yolo26n-seg.pt", "yolo26s-seg.pt"])
if st.button("🚀 Treinar YOLO26-seg"):
    data_yaml = ss.get("data_yaml") or str(DATASET / "data.yaml")
    if not Path(data_yaml).exists():
        st.error("Exporte o dataset primeiro.")
    else:
        with st.spinner(f"Treinando {model_name} por {epochs} épocas…"):
            res = trainer.train(data_yaml, model=model_name, epochs=int(epochs))
        st.success(f"Treino concluído. Pesos em: {res.save_dir}")
