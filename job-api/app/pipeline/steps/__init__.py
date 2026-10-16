"""구현된 단계 목록. 나머지 단계(script ~ upload)는 작업 순서 20-d 에서 더한다."""
from .topic import TopicStep


def default_steps() -> dict:
    return {"topic": TopicStep()}
