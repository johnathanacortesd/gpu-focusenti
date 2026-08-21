# 🔍 Sentimiento por marca — noticias (español)

App en [Streamlit](https://streamlit.io) que toma un archivo `.xlsx` de noticias,
detecta las menciones de una **marca (y sus alias)** y clasifica el **tono** de
cada mención en **Positivo / Neutro / Negativo**.

## Qué hace

1. **Subes un `.xlsx`** y eliges las columnas de texto (por defecto detecta `Título` y `Cuerpo`).
2. Escribes la **marca** y sus **alias** (separados por coma).
3. Analiza **solo el contexto de la mención** (no toda la noticia). Así, una noticia
   negativa sobre otro tema queda *Neutro* o *Positivo* si la mención a la marca lo es.
4. **Agrupa noticias iguales/similares** (FAISS + embeddings) y les aplica el mismo tono
   (voto por mayoría; en empate gana el más severo).
5. Devuelve el archivo con dos columnas nuevas al final: `Confianza` y `Tono`.

### Reglas de clasificación

| Tono | Cuándo |
|---|---|
| 🟢 Positivo | Elogios, buenas prácticas, voceros, acciones, gestiones favorables |
| ⚪ Neutro | Sin mención de la marca, o mención sin ataque ni elogio |
| 🔴 Negativo | Críticas, ataques, denuncias |

## Archivos

| Archivo | Propósito |
|---|---|
| `app.py` | Aplicación completa (autocontenida) |
| `requirements.txt` | Dependencias para Streamlit Cloud |

## Desplegar en Streamlit Cloud

1. Sube estos archivos a un repositorio (GitHub, por ejemplo):
   ```
   tu-repo/
   ├── app.py
   └── requirements.txt
   ```
2. Entra a [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Conecta el repo y **deja `app.py` como archivo principal** (Streamlit Cloud lo detecta solo).
4. Deploy. La **primera ejecución** es más lenta: descarga los modelos (~500 MB) desde
   Hugging Face. Las siguientes son normales.

## Modelos (gratuitos, de uso comercial)

| Componente | Modelo | Licencia |
|---|---|---|
| Sentimiento (español nativo) | `pysentimiento/robertuito-sentiment-analysis` | base **MIT** ✅ |
| Sentimiento (multilingüe) | `cardiffnlp/twitter-xlm-roberta-base-sentiment` | base MIT ✅ |
| Embeddings (agrupar) | `paraphrase-multilingual-MiniLM-L12-v2` | Apache-2.0 ✅ |

> Nota de licencia (honesta): RoBERTuito **base** es MIT (uso comercial claro). El
> clasificador de sentimiento es un fine-tune sobre esa base, del proyecto open-source
> pysentimiento, entrenado con el corpus académico TASS. En la práctica es de uso
> comercial; si necesitas un papel comercial *impoluto*, el multilingüe (base MIT) es
> la opción más conservadora.

## Limitaciones (importantes y honestas)

- **Memoria en Streamlit Cloud free tier (~1 GB).** Cargar el modelo de sentimiento
  (~500 MB) **más** el de embeddings (~470 MB) puede quedar justo y, en algunos casos,
  provocar `Killed` (OOM). Si te pasa:
  - **Desmarca** "🔗 Agrupar noticias similares" → así solo carga el modelo de sentimiento.
  - O, en `requirements.txt`, quita `sentence-transformers` y `faiss-cpu` si no usas el agrupado.
- El modelo de sentimiento fue entrenado en tweets: rinde muy bien en noticias cortas y
  redes; en textos muy largos/abstractos puede bajar la precisión.
- El agrupado busca vecinos exactos por similitud de coseno (FAISS `IndexFlatIP`, exacto).
