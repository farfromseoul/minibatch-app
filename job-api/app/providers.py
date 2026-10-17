"""제공자 설정 providers.yaml (아키텍처 D19, 앱 설계 "제공자 설정").

시작할 때 읽고 검사한다. 모르는 kind, 없는 제공자 이름, 선택된 제공자의 키 파일이 없으면 시작하지 않는다.
단계 코드는 ProviderRegistry 만 알고 제공자 이름을 쓰지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.llm.base import LlmEngine
from app.llm.openai_compatible import OpenAiCompatible

LLM_KINDS = {"openai-compatible", "claude-api"}
TTS_KINDS = {"http-worker"}
STOCK_ENGINES = {"none", "pixabay"}  # 스톡 영상 (2026-10-17). 키 파일은 visuals 단계가 쓸 때 읽는다(없으면 그 영상만 도식)
CLIP_ENGINES = {"none", "runway", "higgsfield", "seedance"}  # 생성기 구현은 Phase 2 (기획서 F16~F18)


class ProviderError(Exception):
    pass


class ProviderRegistry:
    def __init__(self, config: dict[str, Any], llms: dict[str, LlmEngine]):
        self.config = config
        self._llms = llms

    def llm(self, step: str) -> LlmEngine:
        steps = self.config["llm"]["steps"]
        # 따로 정하지 않은 LLM 일(주제·시리즈 계획 생성 등)은 script 단계의 제공자를 쓴다
        name = steps.get(step) or steps.get("script")
        if name is None:
            raise ProviderError(f"llm.steps 에 {step} 도 script 도 없다")
        return self._llms[name]

    def tts_settings(self) -> dict[str, Any]:
        tts = self.config["tts"]
        return tts["providers"][tts["provider"]]

    @property
    def chars_per_sec(self) -> float:
        """선택된 TTS 의 초당 글자 수(공백 제외). 대본 목표 글자 수 계산에 쓴다 (앱 설계 "길이 맞추기")"""
        return float(self.tts_settings()["chars_per_sec"])

    @property
    def stock(self) -> dict[str, Any]:
        """스톡 영상 공급원 (video.stock). engine: none | pixabay"""
        return dict(self.config.get("video", {}).get("stock") or {"engine": "none"})

    @property
    def clip_engine(self) -> str:
        return self.config.get("video", {}).get("clip_engine", "none")


def _build_llm(name: str, p: dict[str, Any]) -> LlmEngine:
    kind = p.get("kind")
    if kind == "openai-compatible":
        return OpenAiCompatible(base_url=p["base_url"], model=p["model"],
                                structured_output=p.get("structured_output", "json_schema"),
                                extra_body=p.get("extra_body") or {}, timeout_sec=float(p.get("timeout_sec", 300)),
                                temperature=float(p.get("temperature", 0.3)), prompt_suffix=p.get("prompt_suffix", ""))
    if kind == "claude-api":
        key = Path(p.get("api_key_file", ""))
        if not key.is_file():
            raise ProviderError(f"llm.providers.{name}: 키 파일이 없다 ({key})")
        raise ProviderError(f"llm.providers.{name}: claude-api 구현은 아직 없다 (D16, 전환할 때 추가)")
    raise ProviderError(f"llm.providers.{name}: 모르는 kind {kind}")


def load_providers(path: Path) -> ProviderRegistry:
    if not path.is_file():
        raise ProviderError(f"providers.yaml 이 없다: {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    llm = cfg.get("llm") or {}
    providers, steps = llm.get("providers") or {}, llm.get("steps") or {}
    for name, p in providers.items():
        if p.get("kind") not in LLM_KINDS:
            raise ProviderError(f"llm.providers.{name}: 모르는 kind {p.get('kind')}")
    for step, name in steps.items():
        if name not in providers:
            raise ProviderError(f"llm.steps.{step}: 없는 제공자 {name}")
    # 단계가 고른 제공자만 만든다(키 파일도 그때만 본다)
    llms = {name: _build_llm(name, providers[name]) for name in sorted(set(steps.values()))}
    tts = cfg.get("tts") or {}
    tp = (tts.get("providers") or {}).get(tts.get("provider"))
    if tp is None:
        raise ProviderError(f"tts.provider: 없는 제공자 {tts.get('provider')}")
    if tp.get("kind") not in TTS_KINDS:
        raise ProviderError(f"tts: 모르는 kind {tp.get('kind')}")
    if not isinstance(tp.get("chars_per_sec"), (int, float)) or tp["chars_per_sec"] <= 0:
        raise ProviderError("tts: chars_per_sec(초당 글자 수, 0주 차 실측 Supertonic 5.6) 가 필요하다")
    stock = ((cfg.get("video") or {}).get("stock") or {}).get("engine", "none")
    if stock not in STOCK_ENGINES:
        raise ProviderError(f"video.stock.engine: 모르는 값 {stock}")
    clip = (cfg.get("video") or {}).get("clip_engine", "none")
    if clip not in CLIP_ENGINES:
        raise ProviderError(f"video.clip_engine: 모르는 값 {clip}")
    return ProviderRegistry(cfg, llms)
