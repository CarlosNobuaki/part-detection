# Identificador de Peças — SAM → YOLO26-seg

Ferramenta interna de **visão computacional** que identifica a **peça principal** de uma
foto (caixa delimitadora + máscara de segmentação). O fluxo usa o **SAM** apenas para
rotular as imagens automaticamente (offline) e treina um **YOLO26-seg** que, na
inferência, reconhece a peça sozinho — **sem depender do SAM** em produção.

Tudo é operado por um painel **Streamlit**: segmentar → revisar → exportar dataset → treinar.

---

## Como funciona (pipeline)

O projeto segue a chamada **"rota C"**: o SAM é caro/pesado, então só é usado uma vez,
na rotulagem. O modelo que roda em produção é leve e autossuficiente.

```
Fotos brutas ──▶ (1) SAM rotula ──▶ (2) Revisão humana ──▶ (3) Dataset YOLO-seg ──▶ (4) Treino YOLO26-seg
   images/          máscara+caixa       painel Streamlit       polígonos + split         modelo final
                                                                                          (roda sem SAM)
```

1. **SAM rotula (offline).** [pipeline/segment.py](pipeline/segment.py) usa `SAM2Predictor`
   com 1 ponto (o centro da imagem por padrão, ou o clique do usuário) e `multimask_output=True`,
   escolhendo o **maior escopo** (a peça inteira, não um pedaço). Agnóstico de peso:
   `sam2.1_b.pt` (~160 MB, padrão, auto-baixa) ou `sam3.pt` (3.45 GB, requer acesso no
   HuggingFace) — troca por 1 parâmetro.
2. **Revisão humana.** No painel, você navega imagem a imagem, corrige o ponto de
   segmentação com um clique, ajusta o nome da classe e aceita/rejeita cada máscara. As
   revisões persistem em `data/records/<pasta>.json`.
3. **Exportação do dataset.** [pipeline/export.py](pipeline/export.py) gera um dataset
   YOLO-seg (polígonos normalizados, imagens por **symlink** para não duplicar os GBs de
   fotos, split train/val). A imagem **completa** é usada no treino — a máscara do SAM é
   só o rótulo, o fundo é mantido.
4. **Treino.** [pipeline/train.py](pipeline/train.py) treina o `yolo26n-seg.pt`. Na
   inferência, roda **só o YOLO26-seg**, devolvendo caixa + máscara.

---

## Estrutura do projeto

```
INOVASKILL_PORTATEIS/
├── app.py                  # painel Streamlit (segmentar, revisar, exportar, treinar)
├── pipeline/
│   ├── segment.py          # SAM: segmenta a peça principal (rotulagem offline)
│   ├── export.py           # gera o dataset YOLO-seg (polígonos + split train/val)
│   └── train.py            # treino e inferência do YOLO26-seg
├── images/<CLASSE>/        # fotos brutas (nome da pasta = classe). NÃO versionado
├── data/                   # gerado: records/ (revisões), previews/, dataset/. NÃO versionado
├── runs/                   # gerado: pesos e métricas do treino. NÃO versionado
├── requirements.txt
├── sam2.1_b.pt             # peso do SAM (auto-baixa). NÃO versionado
└── yolo26n-seg.pt          # peso base do YOLO. NÃO versionado
```

As pastas de dados/pesos ficam fora do Git (ver [.gitignore](.gitignore)) por serem grandes.

---

## Pré-requisitos

- **Python 3.11**
- **macOS com Apple Silicon** (M3/16 GB é o alvo, usa aceleração **MPS**). Funciona também
  em CPU/CUDA, mas pesos muito grandes (SAM3) são inviáveis em hardware modesto.
- As fotos organizadas em `images/<NOME_DA_CLASSE>/*.jpg` (o nome da pasta vira a classe).

---

## Instalação

```bash
# 1. Entre na pasta do projeto
cd INOVASKILL_PORTATEIS

# 2. Crie o ambiente virtual com Python 3.11
python3.11 -m venv .venv

# 3. Ative o ambiente (opcional — os comandos abaixo usam .venv/bin diretamente)
source .venv/bin/activate

# 4. Instale as dependências
.venv/bin/pip install -r requirements.txt
```

As dependências ([requirements.txt](requirements.txt)) são:

- **ultralytics** — traz `torch`, `torchvision`, `opencv`, `numpy` e inclui SAM + YOLO26.
- **streamlit** — o painel de segmentação e revisão.
- **streamlit-image-coordinates** — captura do clique-para-apontar na revisão.

> Os pesos dos modelos (`sam2.1_b.pt`, `yolo26n-seg.pt`) são **baixados automaticamente**
> na primeira execução, se ainda não existirem na pasta.

---

## Execução

Inicie o painel:

```bash
.venv/bin/streamlit run app.py
```

O Streamlit abre no navegador (por padrão em `http://localhost:8501`).

### Passo a passo no painel

1. **Configuração (barra lateral)**
   - Selecione a **pasta da peça** (cada pasta em `images/` é uma classe).
   - Confira/edite o **nome da peça (classe)**.
   - Escolha o **peso do SAM** (`sam2.1_b.pt` por padrão).
   - Opcional: limite o número de imagens para um teste rápido.
   - Clique em **▶ Segmentar pasta**.

2. **Revisão**
   - Navegue pelas imagens com o slider ou os botões **◀ Anterior / Próxima ▶**.
   - **Clique sobre a peça** na imagem para re-segmentar naquele ponto, ou use **↻ Re-segmentar**.
   - Ajuste o **nome** e marque **Aceitar esta segmentação** (edições são salvas automaticamente).
   - Repita para as demais pastas/classes.

3. **Exportar dataset + treinar**
   - Clique em **Exportar dataset YOLO-seg** — junta **todas as pastas já revisadas**,
     dedup por nome de classe, e gera `data/dataset/` com `data.yaml`.
   - Escolha o número de **épocas** e o **modelo** (`yolo26n-seg.pt` ou `yolo26s-seg.pt`).
   - Clique em **Treinar YOLO26-seg**. Os pesos treinados ficam em `runs/`.

### Inferência (usar o modelo treinado)

Após o treino, o modelo roda sozinho (sem SAM). Exemplo em Python:

```python
from pipeline.train import predict

results = predict("runs/segment/pecas/weights/best.pt", "caminho/para/foto.jpg")
results[0].show()   # exibe caixa + máscara da peça identificada
```

---

## Verificação headless (sem UI)

Antes de confiar na interface, dá para validar o pipeline direto no Python — segmentar,
exportar e treinar 1 época:

```bash
.venv/bin/python -c "
from pipeline.segment import segment_main_part
from pipeline.export import build_dataset
from pipeline import train

r = segment_main_part('images/COADOR-1220919/COADOR-1220919_1.jpg')
print('area_frac:', r['area_frac'])

recs = [{'image_path': 'images/COADOR-1220919/COADOR-1220919_1.jpg',
         'class_id': 0, 'polygon': r['polygon'].tolist(), 'w': r['mask'].shape[1], 'h': r['mask'].shape[0]}]
summary = build_dataset(recs, 'data/dataset', ['COADOR'])
print(summary)

train.train('data/dataset/data.yaml', epochs=1)
"
```

---

## Notas e convenções

- **O nome digitado na revisão vira a classe** no `data.yaml` (dedup por nome) — cuidado com
  typos, que viram classes espúrias.
- O Streamlit re-executa o script a cada interação; por isso as revisões persistem em disco
  (`data/records/`) em vez de ficar em memória — máscaras de 16 MP não são guardadas na sessão.
- Classes atuais em `images/`: BASE-PULVERIZADOR-ELETRICOS, BATERIA-LHON, COADOR,
  FILTRO-SUCCAO-DA-BOMBA, PAINEL-COM-POTENCIOMETRO, REGISTRO-COMPLETO, TAMPA-COM-DIAFRAGMA.

Para detalhes de arquitetura e decisões de design, veja [CLAUDE.md](CLAUDE.md).
