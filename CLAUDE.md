# CLAUDE.md — Identificador de peças

Ferramenta interna de visão computacional: segmenta a **peça principal** de fotos com
SAM, gera um dataset e treina um **YOLO26-seg** que, na inferência, identifica a peça
(caixa + máscara) **sem depender do SAM**.

## Como rodar
```bash
.venv/bin/streamlit run app.py      # painel: segmentar -> revisar -> exportar -> treinar
```
- venv em `.venv` (Python 3.11). Deps em `requirements.txt` (`ultralytics`, `streamlit`,
  `streamlit-image-coordinates`).
- Hardware alvo: Apple M3, 16 GB, MPS. Modelos pesados (SAM3) são inviáveis aqui.

## Arquitetura do pipeline (decisão "rota C" — não mudar sem discutir)
1. **SAM só rotula, offline.** [pipeline/segment.py](pipeline/segment.py) usa `SAM2Predictor`
   com 1 ponto (centro por padrão, ou clique do usuário), `multimask_output=True`, e pega o
   **maior escopo** (a peça inteira, não um sub-pedaço). Agnóstico de peso: `sam2.1_b.pt`
   (padrão, ~160 MB, auto-baixa) ou `sam3.pt` (3.45 GB, gated no HF) — troca por 1 parâmetro.
2. **Treino em imagem completa** (fundo mantido), a máscara do SAM é só o **rótulo**.
   [pipeline/export.py](pipeline/export.py) → dataset YOLO-seg (polígonos normalizados,
   symlink das imagens, split train/val limpando dirs antigos).
3. **Inferência roda só o YOLO26-seg** ([pipeline/train.py](pipeline/train.py),
   `yolo26n-seg.pt`) → caixa + máscara. **Nunca** apagar o fundo da entrada; **nunca** rodar
   SAM na inferência (rejeitado por domain-gap + custo em runtime).

## Estrutura
- `images/<CLASSE>/<CLASSE>_<n>.jpg` — dados brutos (7 classes; nome da pasta = classe).
  **Não versionado** (grande) — ver `.gitignore`.
- `app.py` — painel Streamlit (seleção de pasta, segmentação, revisão, export, treino).
- `pipeline/{segment,export,train}.py` — núcleo reutilizável, testável sem UI.
- `data/{records,previews,dataset}/`, `runs/` — gerados; não versionados.

## Convenções
- Estado do Streamlit em `st.session_state`; revisões persistem em `data/records/<pasta>.json`
  (o script re-executa a cada interação — nunca guardar máscara de 16 MP em memória).
- O **nome digitado na revisão vira a classe** no `data.yaml` (dedup por nome) — cuidado com
  typos: viram classes espúrias.
- Verificar mudanças no pipeline de forma headless (segmentar → exportar → treinar 1 época)
  antes de confiar na UI.

## Personas (lentes do wizard v2, em `.claude/agents/`)
`rotulador-lens` (opera o painel/revisão) e `ml-engenheiro-lens` (dataset/treino). O seam
crítico entre elas: nome/`accepted`/`polygon` da revisão → `class_id`/labels do treino.
