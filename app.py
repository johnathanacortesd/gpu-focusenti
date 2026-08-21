# ============================================================================
#  🔍 Análisis de sentimiento orientado a marca — Streamlit (noticias, español)
#  ---------------------------------------------------------------------------
#  · Porta la lógica del notebook de Colab ya validado.
#  · Modelos gratuitos (base MIT / Apache-2.0):
#      - RoBERTuito (español nativo): pysentimiento/robertuito-sentiment-analysis
#      - Multilingüe: cardiffnlp/twitter-xlm-roberta-base-sentiment
#      - Embeddings (agrupar similares): paraphrase-multilingual-MiniLM-L12-v2
#  · Analiza SOLO el contexto de la mención de la marca (no toda la noticia).
#  · Propaga el mismo tono a noticias iguales/similares.
#  · Salida: columnas "Confianza" y "Tono" (Positivo / Neutro / Negativo).
# ============================================================================

import warnings
warnings.filterwarnings("ignore")

import io
import re
import unicodedata

import numpy as np
import pandas as pd
import streamlit as st

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sentence_transformers import SentenceTransformer
import faiss

st.set_page_config(page_title="Sentimiento por marca", page_icon="🔍", layout="wide")

# ---------------------------- modelos (en caché) ----------------------------
SENT_MODELS = {
    "🇪🇸 RoBERTuito (español nativo) — recomendado": "pysentimiento/robertuito-sentiment-analysis",
    "🌐 Multilingüe (xlm-roberta)": "cardiffnlp/twitter-xlm-roberta-base-sentiment",
}
EMB_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@st.cache_resource(show_spinner=False)
def load_sentiment(model_id):
    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForSequenceClassification.from_pretrained(model_id).eval()
    id2label = {int(k): v for k, v in model.config.id2label.items()}
    labels = [id2label[i] for i in range(len(id2label))]
    return {"tok": tok, "model": model, "labels": labels}


@st.cache_resource(show_spinner=False)
def load_embeddings():
    return SentenceTransformer(EMB_MODEL)


def _norm_label(lbl):
    lbl = lbl.lower()
    if "neg" in lbl:
        return "neg"
    if "pos" in lbl:
        return "pos"
    return "neu"


def _sent_probs(res, text):
    tok = res["tok"](text, return_tensors="pt", truncation=True)
    with torch.no_grad():
        logits = res["model"](**tok).logits[0]
    p = F.softmax(logits, dim=0).cpu().numpy()
    labels = res["labels"]
    return {_norm_label(labels[i]): float(p[i]) for i in range(len(p))}


# ------------------------------- interfaz -----------------------------------
st.title("🔍 Sentimiento por marca")
st.caption(
    "Sube un .xlsx de noticias, indica la marca y sus alias, y obtén la columna "
    "de tono (Positivo / Neutro / Negativo) analizando solo la mención de la marca."
)

uf = st.file_uploader("📂 Sube tu archivo .xlsx", type=["xlsx"])

if uf is not None:

    # al subir un archivo nuevo, limpio los resultados previos
    if st.session_state.get("fname") != uf.name:
        st.session_state["fname"] = uf.name
        st.session_state.pop("result_bytes", None)
        st.session_state.pop("result_df", None)
        st.session_state.pop("result_name", None)

    df = pd.read_excel(uf)
    st.success(f"Archivo cargado: {df.shape[0]:,} filas × {df.shape[1]} columnas")


    def _norm(s):
        return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


    def _find_col(keywords):
        for c in df.columns:
            if _norm(c) in keywords:
                return c
        return None


    tcol = _find_col({"titulo", "title", "headline", "encabezado"})
    bcol = _find_col({"cuerpo", "body", "contenido", "content", "texto", "nota"})
    default_cols = [c for c in (tcol, bcol) if c is not None] or [df.columns[0]]

    cols = st.multiselect("📝 Columnas de texto", list(df.columns), default=default_cols)

    c1, c2 = st.columns(2)
    with c1:
        brand = st.text_input("🏷️ Marca", placeholder="Ej: Hyundai")
        aliases_raw = st.text_input("🏷️ Alias (separados por coma)", placeholder="Hyundai Motor, HMC")
        model_label = st.selectbox("🧠 Modelo de sentimiento", list(SENT_MODELS.keys()))
    with c2:
        do_dedup = st.checkbox("🔗 Agrupar noticias similares (mismo tono)", value=True)
        thr = st.slider("Umbral de similitud", 0.80, 0.99, 0.90, 0.01)

    if st.button("▶ Analizar", type="primary"):
        if not cols:
            st.warning("Selecciona al menos una columna de texto.")
        elif not brand.strip() and not aliases_raw.strip():
            st.warning("Escribe la marca o al menos un alias.")
        else:
            terms = ([brand.strip()] if brand.strip() else []) + [
                a.strip() for a in aliases_raw.split(",") if a.strip()
            ]
            pattern = re.compile(
                r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE
            )
            texts = df[cols].fillna("").agg(" ".join, axis=1).tolist()
            n = len(texts)

            status = st.status("⏳ Preparando análisis...", expanded=True)

            status.write("Cargando modelo de sentimiento...")
            sres = load_sentiment(SENT_MODELS[model_label])

            # --- sentimiento solo sobre la mención de la marca ---
            W = 250
            records = []
            prog = st.progress(0.0, text="Analizando menciones...")
            for i, txt in enumerate(texts):
                wins = []
                for m in pattern.finditer(txt):
                    s = max(0, m.start() - W)
                    e = min(len(txt), m.end() + W)
                    wins.append(txt[s:e])

                if not wins:
                    records.append((i, "Neutro", 1.0))
                else:
                    agg = {"neg": [], "neu": [], "pos": []}
                    for wnd in wins:
                        pr = _sent_probs(sres, wnd)
                        for k in agg:
                            agg[k].append(pr[k])
                    scr = {
                        "neg": float(np.mean(agg["neg"])),
                        "neu": float(np.mean(agg["neu"])),
                        "pos": float(np.mean(agg["pos"])),
                    }
                    lbl = max(scr, key=scr.get)
                    tone = {"neg": "Negativo", "neu": "Neutro", "pos": "Positivo"}[lbl]
                    records.append((i, tone, scr[lbl]))
                prog.progress((i + 1) / n)

            rows_tone = [t for _, t, _ in records]
            rows_conf = [c for _, _, c in records]

            # --- agrupar noticias similares y unificar tono ---
            final_tone = rows_tone
            if do_dedup and n > 1:
                status.write("Calculando embeddings y agrupando similares (FAISS)...")
                emb_model = load_embeddings()
                emb = emb_model.encode(
                    texts, batch_size=32, convert_to_numpy=True,
                    normalize_embeddings=True, show_progress_bar=False,
                )
                emb_f32 = np.ascontiguousarray(emb.astype("float32"))
                d = emb_f32.shape[1]
                index = faiss.IndexFlatIP(d)  # producto interno exacto (coseno)
                index.add(emb_f32)
                k = min(n, 128)
                scores, neighbors = index.search(emb_f32, k)

                parent = np.arange(n)

                def find(x):
                    while parent[x] != x:
                        parent[x] = parent[parent[x]]
                        x = parent[x]
                    return x

                for i in range(n):
                    for j, s in zip(neighbors[i], scores[i]):
                        if j != i and s >= thr:
                            ri, rj = find(i), find(j)
                            if ri != rj:
                                parent[rj] = ri

                root = [find(i) for i in range(n)]

                from collections import defaultdict, Counter
                groups = defaultdict(list)
                for i, r in enumerate(root):
                    groups[r].append(i)

                priority = {"Negativo": 0, "Positivo": 1, "Neutro": 2}
                cluster_tone = {}
                for r, idxs in groups.items():
                    c = Counter(rows_tone[i] for i in idxs)
                    cluster_tone[r] = max(c, key=lambda t: (c[t], -priority[t]))

                final_tone = [cluster_tone[root[i]] for i in range(n)]

            # --- resultado ---
            res = df.copy()
            res["Confianza"] = [round(c, 3) for c in rows_conf]
            res["Tono"] = final_tone

            buf = io.BytesIO()
            res.to_excel(buf, index=False, engine="openpyxl")

            st.session_state["result_df"] = res
            st.session_state["result_bytes"] = buf.getvalue()
            st.session_state["result_name"] = uf.name.rsplit(".", 1)[0] + "_tono.xlsx"

            status.update(label="✅ Análisis terminado", state="complete", expanded=False)

    # --------------------------- mostrar resultados ---------------------------
    if "result_bytes" in st.session_state:
        st.divider()
        res = st.session_state["result_df"]
        vc = res["Tono"].value_counts()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("😀 Positivo", int(vc.get("Positivo", 0)))
        m2.metric("😐 Neutro", int(vc.get("Neutro", 0)))
        m3.metric("😡 Negativo", int(vc.get("Negativo", 0)))
        m4.metric("📄 Total", int(len(res)))

        st.dataframe(res, height=400)
        st.download_button(
            "⬇️ Descargar XLSX",
            data=st.session_state["result_bytes"],
            file_name=st.session_state["result_name"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
