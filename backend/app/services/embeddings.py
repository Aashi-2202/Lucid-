"""Pinned Sentence Transformer ONNX inference; no remote inference or PyTorch runtime."""
from functools import lru_cache
from pathlib import Path
import os

from app.core.config import settings

MODEL_REPO = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_FILE = "onnx/model_quint8_avx2.onnx"


def model_files(download=False):
    from huggingface_hub import hf_hub_download
    cache = Path(__file__).resolve().parents[2] / ".model-cache"
    return [hf_hub_download(MODEL_REPO, name, revision=MODEL_REVISION, cache_dir=cache,
                           local_files_only=not download) for name in (MODEL_FILE, "tokenizer.json")]


def available():
    try:
        from importlib.util import find_spec
        if settings.embedding_model not in ("all-MiniLM-L6-v2", MODEL_REPO) or any(find_spec(module) is None for module in ("onnxruntime", "tokenizers", "numpy")):
            return False
        model_files()
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def _runtime():
    import onnxruntime as ort
    from tokenizers import Tokenizer
    model, tokenizer_file = model_files()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.log_severity_level = 3
    session = ort.InferenceSession(model, sess_options=options, providers=["CPUExecutionProvider"])
    tokenizer = Tokenizer.from_file(tokenizer_file)
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
    return session, tokenizer


def encode(texts):
    import numpy as np
    if settings.embedding_model not in ("all-MiniLM-L6-v2", MODEL_REPO):
        raise ValueError("Unsupported embedding model")
    session, tokenizer = _runtime()
    vectors = []
    for start in range(0, len(texts), 8):
        batch = tokenizer.encode_batch(texts[start:start + 8])
        values = {
            "input_ids": np.asarray([item.ids for item in batch], dtype=np.int64),
            "attention_mask": np.asarray([item.attention_mask for item in batch], dtype=np.int64),
            "token_type_ids": np.asarray([item.type_ids for item in batch], dtype=np.int64),
        }
        output = session.run(None, {item.name: values[item.name] for item in session.get_inputs()})[0]
        mask = values["attention_mask"][..., None].astype(np.float32)
        pooled = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
        pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9)
        vectors.extend(pooled.tolist())
    return np.asarray(vectors, dtype=np.float32)


if __name__ == "__main__":
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    model_files(download=True)
    vectors = encode(["Build Python backend services", "Developed Python APIs"])
    print({"model": MODEL_REPO, "revision": MODEL_REVISION, "shape": list(vectors.shape),
           "smoke_similarity": round(float(vectors[0] @ vectors[1]), 4)})
