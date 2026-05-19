from __future__ import annotations
import math
import re
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from typing import Optional, Sequence

import numpy as np
from PIL import Image
from sqlalchemy import select

from core.database_async import AsyncSessionLocal, IPInfringement
from core.schemas import (IPInfringementCheck, IPInfringementOut,
                            IPDecision, RiskLevel)


_TOKEN_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", re.UNICODE)
_PHASH_HEX_LEN = 16
_PHASH_BIT_LEN = 64


def _dct_1d_matrix(N: int) -> np.ndarray:
    n = np.arange(N, dtype=np.float64)
    k = n.reshape(-1, 1)
    return np.cos(np.pi * (2.0 * n + 1.0) * k / (2.0 * N))


def _dct_2d(matrix: np.ndarray) -> np.ndarray:
    N = matrix.shape[0]
    M = _dct_1d_matrix(N)
    return M @ matrix @ M.T


def phash_64bit(image_bytes: bytes, resize: int = 32, hash_size: int = 8) -> str:
    img = Image.open(BytesIO(image_bytes)).convert("L").resize(
        (resize, resize), Image.LANCZOS)
    arr = np.asarray(img, dtype=np.float64)
    dct = _dct_2d(arr)
    low = dct[:hash_size, :hash_size]
    flat = low.flatten()
    median = float(np.median(flat[1:]))
    bits = (flat > median).astype(np.uint8)
    bit_int = 0
    for b in bits:
        bit_int = (bit_int << 1) | int(b)
    return f"{bit_int:0{_PHASH_HEX_LEN}x}"


def phash_from_path(path: str, resize: int = 32, hash_size: int = 8) -> str:
    with open(path, "rb") as fh:
        return phash_64bit(fh.read(), resize=resize, hash_size=hash_size)


def hamming_distance(hash_a: str, hash_b: str) -> int:
    if len(hash_a) != len(hash_b):
        raise ValueError("Hash uzunlukları eşleşmiyor")
    a_int = int(hash_a, 16)
    b_int = int(hash_b, 16)
    return int(bin(a_int ^ b_int).count("1"))


def phash_similarity_pct(hash_a: str, hash_b: str,
                            bit_len: int = _PHASH_BIT_LEN) -> float:
    return max(0.0, 1.0 - hamming_distance(hash_a, hash_b) / bit_len)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)
            if len(m.group(0)) >= 2]


def _term_frequency(tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = float(len(tokens))
    return {t: c / total for t, c in counts.items()}


def _inverse_doc_frequency(corpus_tokens: list[list[str]]) -> dict[str, float]:
    N = len(corpus_tokens)
    if N == 0:
        return {}
    df: dict[str, int] = {}
    for tokens in corpus_tokens:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    return {t: math.log((1.0 + N) / (1.0 + d)) + 1.0 for t, d in df.items()}


def tfidf_cosine_similarity(text_a: str, text_b: str,
                              corpus: Optional[Sequence[str]] = None) -> float:
    a_tok = _tokenize(text_a)
    b_tok = _tokenize(text_b)
    if not a_tok or not b_tok:
        return 0.0
    corpus_tokens = [a_tok, b_tok]
    if corpus:
        for c in corpus:
            corpus_tokens.append(_tokenize(c))
    idf = _inverse_doc_frequency(corpus_tokens)
    tf_a = _term_frequency(a_tok)
    tf_b = _term_frequency(b_tok)
    vocab = set(tf_a.keys()) | set(tf_b.keys())
    dot = 0.0
    norm_a_sq = 0.0
    norm_b_sq = 0.0
    for t in vocab:
        idf_t = idf.get(t, 1.0)
        va = tf_a.get(t, 0.0) * idf_t
        vb = tf_b.get(t, 0.0) * idf_t
        dot += va * vb
        norm_a_sq += va * va
        norm_b_sq += vb * vb
    if norm_a_sq <= 0 or norm_b_sq <= 0:
        return 0.0
    return float(dot / (math.sqrt(norm_a_sq) * math.sqrt(norm_b_sq)))


def damerau_levenshtein(a: str, b: str) -> int:
    a = a.lower()
    b = b.lower()
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,
                d[i][j - 1] + 1,
                d[i - 1][j - 1] + cost,
            )
            if (i > 1 and j > 1
                    and a[i - 1] == b[j - 2]
                    and a[i - 2] == b[j - 1]):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + cost)
    return d[la][lb]


def damerau_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    return max(0.0, 1.0 - damerau_levenshtein(a, b) / max_len)


def brand_fuzzy_score(text: str, brand: str,
                        exact_bonus: float = 1.0,
                        per_token_threshold: float = 0.80) -> float:
    if not text or not brand:
        return 0.0
    text_lower = text.lower()
    brand_lower = brand.lower()
    if brand_lower in text_lower:
        return exact_bonus
    text_tokens = _tokenize(text)
    brand_tokens = _tokenize(brand)
    if not text_tokens or not brand_tokens:
        return 0.0
    matched = 0.0
    for bt in brand_tokens:
        best_for_bt = 0.0
        for tt in text_tokens:
            sim = damerau_similarity(tt, bt)
            if sim > best_for_bt:
                best_for_bt = sim
        if best_for_bt >= per_token_threshold:
            matched += best_for_bt
    score = matched / len(brand_tokens)
    return float(score)


@dataclass
class InfringementResult:
    hamming_distance: int
    similarity_pct:   float
    trademark_tfidf:  float
    image_match:      bool
    brand_match:      bool
    decision:         str
    risk_level:       str

    def to_dict(self) -> dict:
        return {
            "hamming_distance": self.hamming_distance,
            "similarity_pct":   self.similarity_pct,
            "trademark_tfidf":  self.trademark_tfidf,
            "image_match":      self.image_match,
            "brand_match":      self.brand_match,
            "decision":         self.decision,
            "risk_level":       self.risk_level,
        }


def detect_infringement(target_phash: str, candidate_phash: str,
                          target_brand_text: Optional[str] = None,
                          candidate_brand_text: Optional[str] = None,
                          hamming_threshold: int = 12,
                          tfidf_threshold: float = 0.78
                          ) -> InfringementResult:
    h_dist = hamming_distance(target_phash, candidate_phash)
    h_sim = 1.0 - h_dist / _PHASH_BIT_LEN

    tfidf_score = 0.0
    if target_brand_text and candidate_brand_text:
        tfidf_score = tfidf_cosine_similarity(
            target_brand_text, candidate_brand_text)

    image_match = h_dist <= hamming_threshold
    brand_match = tfidf_score >= tfidf_threshold

    if image_match and brand_match:
        decision = IPDecision.INFRINGING.value
        risk = RiskLevel.CRITICAL.value
    elif image_match and h_sim >= 0.95:
        decision = IPDecision.SUSPICIOUS.value
        risk = RiskLevel.HIGH.value
    elif brand_match and tfidf_score >= 0.90:
        decision = IPDecision.SUSPICIOUS.value
        risk = RiskLevel.HIGH.value
    elif image_match or brand_match:
        decision = IPDecision.SUSPICIOUS.value
        risk = RiskLevel.MEDIUM.value
    else:
        decision = IPDecision.CLEAN.value
        risk = RiskLevel.LOW.value

    return InfringementResult(
        hamming_distance=h_dist,
        similarity_pct=float(h_sim),
        trademark_tfidf=float(tfidf_score),
        image_match=image_match,
        brand_match=brand_match,
        decision=decision,
        risk_level=risk,
    )


def batch_match(target_phash: str,
                  candidates: Sequence[dict],
                  hamming_threshold: int = 12) -> list[dict]:
    rows = []
    for c in candidates:
        try:
            d = hamming_distance(target_phash, c["phash"])
        except Exception:
            continue
        rows.append({
            "sku":              c.get("sku"),
            "candidate_phash":  c["phash"],
            "hamming_distance": d,
            "similarity_pct":   1.0 - d / _PHASH_BIT_LEN,
            "image_match":      d <= hamming_threshold,
        })
    rows.sort(key=lambda r: r["hamming_distance"])
    return rows


async def persist_check(req: IPInfringementCheck) -> IPInfringementOut:
    result = detect_infringement(
        target_phash=req.target_phash,
        candidate_phash=req.candidate_phash,
        target_brand_text=req.target_brand_text,
        candidate_brand_text=req.candidate_brand_text,
        hamming_threshold=int(req.hamming_threshold),
        tfidf_threshold=float(req.tfidf_threshold),
    )
    async with AsyncSessionLocal() as session:
        row = IPInfringement(
            listing_sku=req.listing_sku,
            candidate_url=req.candidate_url,
            target_phash=req.target_phash,
            candidate_phash=req.candidate_phash,
            hamming_distance=result.hamming_distance,
            similarity_pct=result.similarity_pct,
            trademark_tfidf=result.trademark_tfidf,
            decision=result.decision,
            risk_level=result.risk_level,
            metadata_json={
                "image_match": result.image_match,
                "brand_match": result.brand_match,
                "hamming_threshold": int(req.hamming_threshold),
                "tfidf_threshold":   float(req.tfidf_threshold),
            },
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return IPInfringementOut.model_validate(row)


async def latest_for_sku(sku: str,
                            limit: int = 10) -> list[IPInfringementOut]:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(IPInfringement)
            .where(IPInfringement.listing_sku == sku)
            .order_by(IPInfringement.created_at.desc())
            .limit(limit))).scalars().all()
    return [IPInfringementOut.model_validate(r) for r in rows]


__all__ = [
    "InfringementResult",
    "phash_64bit", "phash_from_path", "hamming_distance",
    "phash_similarity_pct",
    "tfidf_cosine_similarity", "damerau_levenshtein", "damerau_similarity",
    "brand_fuzzy_score",
    "detect_infringement", "batch_match",
    "persist_check", "latest_for_sku",
]
