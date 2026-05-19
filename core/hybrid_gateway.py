from __future__ import annotations
import os
import asyncio
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Callable

from sqlalchemy import select, func

from core.database_async import AsyncSessionLocal, HybridInferenceLog
from core.schemas import (HybridInferenceRequest, HybridInferenceResponse,
                            HybridRoute)


log = logging.getLogger("hybrid_gateway")


LOCAL_MODEL_PATH = os.environ.get("LOCAL_SLM_PATH", "").strip()
LOCAL_CTX_SIZE   = int(os.environ.get("LOCAL_SLM_CTX", "4096"))
LOCAL_THREADS    = int(os.environ.get("LOCAL_SLM_THREADS", "4"))
LOCAL_GPU_LAYERS = int(os.environ.get("LOCAL_SLM_GPU_LAYERS", "0"))

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

GEMINI_IN_COST_PER_1K  = 0.000075
GEMINI_OUT_COST_PER_1K = 0.0003
LOCAL_COST_PER_1K      = 0.0

CLOUD_ONLY_KINDS = frozenset({
    "VISION", "SQL_GEN", "LONG_REASONING", "MULTILINGUAL_TRANSLATE",
    "MARKET_RESEARCH", "FINANCIAL_AUDIT",
})
LOCAL_PREFERRED_KINDS = frozenset({
    "CLASSIFY", "EXTRACT_JSON", "INTENT_DETECT", "SHORT_SUMMARY",
    "TAG_GENERATE", "PRODUCT_DESC_SHORT", "KEYWORD_EXPAND",
})
HYBRID_KINDS = frozenset({
    "PRODUCT_DESC", "REVIEW_REPLY", "MARKETPLACE_FEASIBILITY",
    "MRP_NARRATIVE", "INVENTORY_INSIGHT",
})

NEGATIVE_CONFIDENCE_MARKERS = (
    "bilmiyorum", "emin değilim", "emin degilim",
    "i don't know", "i do not know", "uncertain",
    "yetersiz veri", "veri yok", "no data",
)


def _approx_tokens(text: str) -> int:
    if not text:
        return 1
    return max(1, int(len(text) / 4))


def _heuristic_confidence(prompt: str, response: str,
                            request_kind: str = "") -> float:
    if not response or not response.strip():
        return 0.0
    text = response.strip()
    lower = text.lower()
    score = 0.55
    n = len(text)
    if n >= 80:
        score += 0.12
    if n >= 240:
        score += 0.08
    if text.count("\n") >= 2:
        score += 0.04
    if any(m in lower for m in NEGATIVE_CONFIDENCE_MARKERS):
        score -= 0.35
    if "{" in text and "}" in text:
        try:
            start = text.find("{")
            end = text.rfind("}")
            json.loads(text[start:end + 1])
            score += 0.18
        except Exception:
            score -= 0.06
    if request_kind.upper() in ("EXTRACT_JSON", "SQL_GEN") and "```" in text:
        score += 0.04
    return max(0.0, min(1.0, score))


class LocalSLMProvider:
    def __init__(self, model_path: str = LOCAL_MODEL_PATH,
                 n_ctx: int = LOCAL_CTX_SIZE,
                 n_threads: int = LOCAL_THREADS,
                 n_gpu_layers: int = LOCAL_GPU_LAYERS):
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._n_gpu_layers = n_gpu_layers
        self._llm: Any = None
        self._loaded = False
        self._available = False
        self._load_error: Optional[str] = None

    def _try_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._model_path:
            self._available = False
            self._load_error = "LOCAL_SLM_PATH ayarlı değil"
            return
        p = Path(self._model_path)
        if not p.exists():
            self._available = False
            self._load_error = f"Model dosyası bulunamadı: {p}"
            return
        try:
            from llama_cpp import Llama
            self._llm = Llama(
                model_path=str(p),
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                n_gpu_layers=self._n_gpu_layers,
                verbose=False,
            )
            self._available = True
            self._load_error = None
        except ImportError:
            self._available = False
            self._load_error = "llama-cpp-python kurulu değil"
        except Exception as exc:
            self._available = False
            self._load_error = f"Yükleme hatası: {exc}"

    @property
    def available(self) -> bool:
        self._try_load()
        return self._available

    @property
    def load_error(self) -> Optional[str]:
        self._try_load()
        return self._load_error

    async def generate(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.4,
                        request_kind: str = "") -> dict:
        self._try_load()
        if not self._available:
            raise RuntimeError(self._load_error or "Local SLM kullanılamıyor")
        loop = asyncio.get_event_loop()
        t0 = time.perf_counter()

        def _call():
            return self._llm(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                echo=False,
                stop=["</s>"],
            )
        try:
            res = await loop.run_in_executor(None, _call)
        except Exception as exc:
            raise RuntimeError(f"Local SLM çıkarım hatası: {exc}")
        latency_ms = int((time.perf_counter() - t0) * 1000)

        choices = res.get("choices") if isinstance(res, dict) else None
        text = ""
        if choices:
            text = (choices[0].get("text") or "").strip()
        usage = (res.get("usage") if isinstance(res, dict) else None) or {}
        ptok = int(usage.get("prompt_tokens") or _approx_tokens(prompt))
        ctok = int(usage.get("completion_tokens") or _approx_tokens(text))
        return {
            "text":              text,
            "prompt_tokens":     ptok,
            "completion_tokens": ctok,
            "latency_ms":        latency_ms,
            "cost_usd":          LOCAL_COST_PER_1K * (ptok + ctok) / 1000,
            "confidence":        _heuristic_confidence(prompt, text, request_kind),
        }


class CloudProvider:
    def __init__(self, api_key: str = GEMINI_API_KEY,
                 model_name: str = GEMINI_MODEL):
        self._api_key = api_key
        self._model_name = model_name
        self._configured = False
        self._config_error: Optional[str] = None

    def _ensure(self) -> None:
        if self._configured:
            return
        if not self._api_key or self._api_key == "YOUR_API_KEY_HERE":
            self._config_error = "Gemini API anahtarı yok"
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=self._api_key)
            self._configured = True
        except ImportError:
            self._config_error = "google-generativeai paketi yok"
        except Exception as exc:
            self._config_error = f"Yapılandırma hatası: {exc}"

    @property
    def available(self) -> bool:
        self._ensure()
        return self._configured

    @property
    def config_error(self) -> Optional[str]:
        self._ensure()
        return self._config_error

    async def generate(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.4,
                        request_kind: str = "") -> dict:
        self._ensure()
        if not self._configured:
            raise RuntimeError(self._config_error or "Cloud kullanılamıyor")
        loop = asyncio.get_event_loop()
        t0 = time.perf_counter()

        def _call():
            import google.generativeai as genai
            model = genai.GenerativeModel(self._model_name)
            return model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": max_tokens,
                    "temperature": temperature,
                })
        try:
            resp = await loop.run_in_executor(None, _call)
        except Exception as exc:
            raise RuntimeError(f"Cloud çıkarım hatası: {exc}")
        latency_ms = int((time.perf_counter() - t0) * 1000)

        text = getattr(resp, "text", None) or ""
        usage_meta = getattr(resp, "usage_metadata", None)
        if usage_meta is not None:
            ptok = int(getattr(usage_meta, "prompt_token_count", 0)
                        or _approx_tokens(prompt))
            ctok = int(getattr(usage_meta, "candidates_token_count", 0)
                        or _approx_tokens(text))
        else:
            ptok = _approx_tokens(prompt)
            ctok = _approx_tokens(text)
        cost = (ptok / 1000) * GEMINI_IN_COST_PER_1K + (ctok / 1000) * GEMINI_OUT_COST_PER_1K
        return {
            "text":              text.strip(),
            "prompt_tokens":     ptok,
            "completion_tokens": ctok,
            "latency_ms":        latency_ms,
            "cost_usd":          float(cost),
            "confidence":        _heuristic_confidence(prompt, text, request_kind),
        }


def _initial_route(req: HybridInferenceRequest,
                     local_avail: bool, cloud_avail: bool) -> HybridRoute:
    kind = (req.request_kind or "").upper()
    if not local_avail and not cloud_avail:
        return HybridRoute.CLOUD
    if not local_avail:
        return HybridRoute.CLOUD
    if not cloud_avail:
        return HybridRoute.LOCAL_SLM
    if kind in CLOUD_ONLY_KINDS:
        return HybridRoute.CLOUD
    if kind in LOCAL_PREFERRED_KINDS:
        return HybridRoute.LOCAL_SLM
    if req.require_local_first:
        return HybridRoute.LOCAL_SLM
    if kind in HYBRID_KINDS:
        return HybridRoute.HYBRID
    return HybridRoute.CLOUD


class HybridGateway:
    def __init__(self,
                 local: Optional[LocalSLMProvider] = None,
                 cloud: Optional[CloudProvider] = None):
        self._local = local or LocalSLMProvider()
        self._cloud = cloud or CloudProvider()

    @property
    def local_available(self) -> bool:
        return self._local.available

    @property
    def cloud_available(self) -> bool:
        return self._cloud.available

    @property
    def status(self) -> dict:
        return {
            "local": {
                "available": self._local.available,
                "error":     self._local.load_error,
                "model":     LOCAL_MODEL_PATH or None,
            },
            "cloud": {
                "available": self._cloud.available,
                "error":     self._cloud.config_error,
                "model":     GEMINI_MODEL,
            },
        }

    async def infer(self, req: HybridInferenceRequest) -> HybridInferenceResponse:
        primary = _initial_route(req, self._local.available, self._cloud.available)
        fallback_triggered = False
        routed_to = primary
        result: Optional[dict] = None
        error_msg: Optional[str] = None

        if primary in (HybridRoute.LOCAL_SLM, HybridRoute.HYBRID):
            try:
                routed_to = HybridRoute.LOCAL_SLM
                result = await self._local.generate(
                    req.prompt, max_tokens=512, temperature=0.4,
                    request_kind=req.request_kind)
                if result["confidence"] < req.min_confidence \
                        and self._cloud.available:
                    fallback_triggered = True
                    routed_to = HybridRoute.CLOUD
                    result = await self._cloud.generate(
                        req.prompt, max_tokens=512, temperature=0.4,
                        request_kind=req.request_kind)
                elif result["latency_ms"] > req.max_latency_ms \
                        and self._cloud.available \
                        and primary != HybridRoute.LOCAL_SLM:
                    fallback_triggered = True
                    routed_to = HybridRoute.CLOUD
                    result = await self._cloud.generate(
                        req.prompt, max_tokens=512, temperature=0.4,
                        request_kind=req.request_kind)
            except Exception as exc:
                error_msg = f"local: {exc}"
                if self._cloud.available:
                    fallback_triggered = True
                    routed_to = HybridRoute.CLOUD
                    try:
                        result = await self._cloud.generate(
                            req.prompt, max_tokens=512, temperature=0.4,
                            request_kind=req.request_kind)
                        error_msg = None
                    except Exception as exc2:
                        error_msg = f"local: {exc} | cloud: {exc2}"
        else:
            try:
                routed_to = HybridRoute.CLOUD
                result = await self._cloud.generate(
                    req.prompt, max_tokens=512, temperature=0.4,
                    request_kind=req.request_kind)
            except Exception as exc:
                error_msg = f"cloud: {exc}"
                if self._local.available:
                    fallback_triggered = True
                    routed_to = HybridRoute.LOCAL_SLM
                    try:
                        result = await self._local.generate(
                            req.prompt, max_tokens=512, temperature=0.4,
                            request_kind=req.request_kind)
                        error_msg = None
                    except Exception as exc2:
                        error_msg = f"cloud: {exc} | local: {exc2}"

        if result is None:
            result = {
                "text":              None,
                "prompt_tokens":     _approx_tokens(req.prompt),
                "completion_tokens": 0,
                "latency_ms":        0,
                "cost_usd":          0.0,
                "confidence":        0.0,
            }

        log_id = await self._log(
            req=req, routed_to=routed_to, result=result,
            fallback=fallback_triggered, error_msg=error_msg)

        return HybridInferenceResponse(
            id=log_id,
            request_kind=req.request_kind,
            routed_to=routed_to,
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            latency_ms=result["latency_ms"],
            cost_usd=result["cost_usd"],
            confidence=result["confidence"],
            fallback_triggered=fallback_triggered,
            response_text=result.get("text"),
            error_message=error_msg,
            created_at=datetime.utcnow(),
        )

    async def _log(self, *, req: HybridInferenceRequest,
                    routed_to: HybridRoute, result: dict,
                    fallback: bool, error_msg: Optional[str]) -> int:
        async with AsyncSessionLocal() as session:
            entry = HybridInferenceLog(
                request_kind=req.request_kind,
                routed_to=routed_to.value,
                prompt_tokens=int(result["prompt_tokens"]),
                completion_tokens=int(result["completion_tokens"]),
                latency_ms=int(result["latency_ms"]),
                cost_usd=float(result["cost_usd"]),
                confidence=float(result["confidence"]),
                fallback_triggered=bool(fallback),
                error_message=(error_msg[:512] if error_msg else None),
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return int(entry.id)

    async def telemetry(self, last_n: int = 100) -> dict:
        async with AsyncSessionLocal() as session:
            total = (await session.execute(
                select(func.count(HybridInferenceLog.id)))).scalar_one()
            recent = (await session.execute(
                select(HybridInferenceLog)
                .order_by(HybridInferenceLog.id.desc())
                .limit(last_n))).scalars().all()
        if not recent:
            return {"total_logs": int(total or 0),
                     "sampled": 0,
                     "avg_latency_ms": 0.0,
                     "avg_cost_usd": 0.0,
                     "avg_confidence": 0.0,
                     "fallback_rate": 0.0,
                     "by_route": {},
                     "by_kind": {}}
        n = len(recent)
        avg_latency = sum(r.latency_ms for r in recent) / n
        avg_cost = sum(float(r.cost_usd) for r in recent) / n
        avg_conf = sum(float(r.confidence) for r in recent) / n
        fb_rate = sum(1 for r in recent if r.fallback_triggered) / n
        by_route: dict = {}
        by_kind: dict = {}
        for r in recent:
            by_route[r.routed_to] = by_route.get(r.routed_to, 0) + 1
            by_kind[r.request_kind] = by_kind.get(r.request_kind, 0) + 1
        return {
            "total_logs":     int(total or 0),
            "sampled":        n,
            "avg_latency_ms": float(avg_latency),
            "avg_cost_usd":   float(avg_cost),
            "avg_confidence": float(avg_conf),
            "fallback_rate":  float(fb_rate),
            "by_route":       by_route,
            "by_kind":        by_kind,
        }


_default_gateway: Optional[HybridGateway] = None
_gateway_lock = asyncio.Lock()


def get_gateway() -> HybridGateway:
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = HybridGateway()
    return _default_gateway


async def infer(request_kind: str, prompt: str,
                  require_local_first: bool = True,
                  max_latency_ms: int = 6000,
                  min_confidence: float = 0.55,
                  context_hints: Optional[dict] = None
                  ) -> HybridInferenceResponse:
    req = HybridInferenceRequest(
        request_kind=request_kind,
        prompt=prompt,
        require_local_first=require_local_first,
        max_latency_ms=max_latency_ms,
        min_confidence=min_confidence,
        context_hints=context_hints,
    )
    return await get_gateway().infer(req)


def infer_sync(request_kind: str, prompt: str, **kwargs
                  ) -> HybridInferenceResponse:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError(
                "infer_sync, çalışan async event loop içinden çağrılamaz; "
                "doğrudan await infer(...) kullanın.")
    except RuntimeError as exc:
        if "no current event loop" not in str(exc).lower():
            if "asyncio" in str(exc).lower() or "running" in str(exc).lower():
                raise
    return asyncio.run(infer(request_kind, prompt, **kwargs))


__all__ = [
    "HybridGateway", "LocalSLMProvider", "CloudProvider",
    "get_gateway", "infer", "infer_sync",
    "LOCAL_MODEL_PATH", "GEMINI_MODEL",
    "CLOUD_ONLY_KINDS", "LOCAL_PREFERRED_KINDS", "HYBRID_KINDS",
]
