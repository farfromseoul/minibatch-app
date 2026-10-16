"""구현된 단계 목록. 나머지 단계는 작업 순서 20-d 에서 더한다.

단계 모듈은 함수 안에서 불러온다: 단계들이 app.llm·app.core 를 쓰고, 그쪽이 다시 steps.base 를 쓰므로
패키지를 불러오는 순간 서로를 부르는 순환을 피한다.
"""


def default_steps() -> dict:
    from .review import ReviewStep
    from .scenes import ScenesStep
    from .script import ScriptStep
    from .topic import TopicStep

    return {s.name: s for s in (TopicStep(), ScriptStep(), ReviewStep(), ScenesStep())}
