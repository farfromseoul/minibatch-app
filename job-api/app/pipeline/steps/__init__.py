"""구현된 단계 목록 (PIPELINE 의 모든 단계).

단계 모듈은 함수 안에서 불러온다: 단계들이 app.llm·app.core 를 쓰고, 그쪽이 다시 steps.base 를 쓰므로
패키지를 불러오는 순간 서로를 부르는 순환을 피한다.
"""


def default_steps() -> dict:
    from .media import RenderStep, TimelineStep, TtsStep, VisualsStep
    from .publishing import QcStep, UploadStep
    from .review import ReviewStep
    from .scenes import ScenesStep
    from .script import ScriptStep
    from .topic import TopicStep

    steps = (TopicStep(), ScriptStep(), ReviewStep(), ScenesStep(), TtsStep(), TimelineStep(), VisualsStep(), RenderStep(),
             QcStep(), UploadStep())
    return {s.name: s for s in steps}
