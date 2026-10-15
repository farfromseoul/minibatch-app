"""0주 차 TTS 비교 실행.

엔진마다 같은 문장을 합성해 out/tts/<엔진>/ 에 WAV 를 남기고, 합성 시간·음성 길이·RTF 를 표로 만든다.
RTF(실시간 계수) = 합성 시간 ÷ 음성 길이. 1보다 작으면 실시간보다 빠르다.

엔진은 각자 일회용 컨테이너 안에서 돌린다(설치가 무겁고 서로 의존성이 다르다). 실행 명령은 poc/README.md.

사용 예:
    python -m tts_compare.run --engine melotts
    python -m tts_compare.run --engine supertonic --supertonic-dir /opt/supertonic
"""
from __future__ import annotations

import argparse
import contextlib
import pathlib
import shutil
import subprocess
import time
import wave
from typing import Callable, List, Optional

# 짧은 문장, 영어 기술 용어가 섞인 문장, 숫자가 섞인 문장 (실행계획 5단계)
SAMPLE_SENTENCES = [
    "LLM이 모르는 걸 물어보면 어떻게 될까요?",
    "RAG는 먼저 관련 문서를 찾고, 그 내용을 API로 LLM에 넘깁니다.",
    "쿠버네티스는 2014년에 공개됐고, 지금은 컨테이너 3개든 300개든 똑같이 다룹니다.",
]


def wav_seconds(path: pathlib.Path) -> float:
    with contextlib.closing(wave.open(str(path), "rb")) as w:
        return w.getnframes() / float(w.getframerate())


def run_engine(name: str, synth: Callable[[str, pathlib.Path], None], sentences: List[str],
               out_dir: pathlib.Path) -> List[dict]:
    """synth(문장, 출력 경로)를 문장마다 부르고 기록을 돌려준다. 실패해도 다음 문장으로 간다."""
    target = out_dir / name
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for i, text in enumerate(sentences, start=1):
        path = target / f"s{i:02d}.wav"
        record = {"engine": name, "text": text, "file": str(path),
                  "synth_sec": None, "audio_sec": None, "rtf": None, "error": None}
        started = time.monotonic()
        try:
            synth(text, path)
            record["synth_sec"] = time.monotonic() - started
            record["audio_sec"] = wav_seconds(path)
            record["rtf"] = record["synth_sec"] / record["audio_sec"] if record["audio_sec"] else None
        except Exception as e:
            record["synth_sec"] = time.monotonic() - started
            record["error"] = f"{type(e).__name__}: {e}"
        records.append(record)
        if record["error"]:
            status = record["error"]
        else:
            status = "{:.2f}초 음성, RTF {:.2f}".format(record["audio_sec"], record["rtf"])
        print(f"{name} | s{i:02d} | {status}")
    return records


def render_markdown(records: List[dict]) -> str:
    order: List[str] = []
    for r in records:
        if r["engine"] not in order:
            order.append(r["engine"])
    lines = ["| 엔진 | 성공 | 평균 RTF (1 미만이면 실시간보다 빠름) | 음성 길이 합(초) | 합성 시간 합(초) |",
             "| --- | --- | --- | --- | --- |"]
    for name in order:
        items = [r for r in records if r["engine"] == name]
        ok = [r for r in items if not r["error"]]
        rtfs = [r["rtf"] for r in ok if r["rtf"] is not None]
        audio = sum(r["audio_sec"] or 0 for r in ok)
        synth = sum(r["synth_sec"] or 0 for r in items)
        avg = f"{sum(rtfs) / len(rtfs):.2f}" if rtfs else "-"
        lines.append(f"| {name} | {len(ok)}/{len(items)} | {avg} | {audio:.1f} | {synth:.1f} |")
    return "\n".join(lines) + "\n"


def melotts_synth_factory(device: str = "cpu") -> Callable[[str, pathlib.Path], None]:
    """MeloTTS 공식 문서의 한국어 예시를 따른다: TTS(language='KR'), speaker_ids['KR'], tts_to_file."""
    from melo.api import TTS  # 컨테이너 안에서만 설치돼 있다

    model = TTS(language="KR", device=device)
    speaker = model.hps.data.spk2id["KR"]

    def synth(text: str, out_path: pathlib.Path) -> None:
        model.tts_to_file(text, speaker, str(out_path), speed=1.0)

    return synth


def supertonic_synth_factory(repo_dir: pathlib.Path) -> Callable[[str, pathlib.Path], None]:
    """Supertonic 저장소의 예제 스크립트(py/example_onnx.py --text --lang ko)를 문장마다 부른다.

    결과는 py/results/ 에 WAV 로 생긴다(저장소 README). 파일 이름 규칙은 확인하지 못해,
    실행 직후 새로 생긴 WAV 를 가져온다. 목소리(스타일) 선택 인자는 미확인이라 기본값을 쓴다.
    """
    py_dir = repo_dir / "py"
    results = py_dir / "results"

    def synth(text: str, out_path: pathlib.Path) -> None:
        before = set(results.glob("*.wav")) if results.exists() else set()
        subprocess.run(["python", "example_onnx.py", "--n-test", "1", "--text", text, "--lang", "ko"],
                       cwd=py_dir, check=True, capture_output=True, text=True)
        new = sorted(set(results.glob("*.wav")) - before, key=lambda p: p.stat().st_mtime)
        if not new:
            raise RuntimeError("example_onnx.py 가 WAV 를 만들지 않았다")
        shutil.move(str(new[-1]), out_path)

    return synth


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="0주 차 TTS 비교")
    parser.add_argument("--engine", required=True, choices=["melotts", "supertonic"])
    parser.add_argument("--supertonic-dir", default="/opt/supertonic", help="Supertonic 저장소 위치 (모델은 assets/ 에)")
    parser.add_argument("--out", default="out/tts")
    args = parser.parse_args(argv)

    if args.engine == "melotts":
        synth = melotts_synth_factory()
    else:
        synth = supertonic_synth_factory(pathlib.Path(args.supertonic_dir))
    out_dir = pathlib.Path(args.out)
    records = run_engine(args.engine, synth, SAMPLE_SENTENCES, out_dir)
    table = render_markdown(records)
    (out_dir / f"summary-{args.engine}.md").write_text(table)
    print("\n" + table)
    print(f"음성 파일: {out_dir}/{args.engine}/s01.wav … (직접 들어 보고 점수를 매긴다)")


if __name__ == "__main__":
    main()
