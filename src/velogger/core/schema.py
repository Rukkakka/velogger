from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    ValidationError,
)

from typing import Annotated


def _require_text(value: str) -> str:
    """빈 값과 공백만 있는 값을 막는다. 값은 바꾸지 않는다 (앞뒤 공백도 사용자가 쓴 그대로 보낸다)."""
    if not value.strip():
        raise ValueError('빈 값이나 공백만 있는 값은 보낼 수 없습니다')
    return value


# 공백만 있으면 안 되는 문자열. `min_length=1` 은 '   ' 을 통과시킨다. 에러 문구는 `ValueError` 메시지가 그대로
# INVALID_ARGUMENT 로 나간다 (cli/output.py `_validation_message`).
NonBlankStr = Annotated[str, AfterValidator(_require_text)]


class RequestModel(BaseModel):
    """Base request model with strict field validation."""
    model_config = ConfigDict(
        validate_by_name=True,
        extra='forbid',
    )


class ResponseModel(BaseModel):
    """Base response model allowing additional fields from APIs.

    비공식 API 는 예고 없이 필드를 추가하므로 모르는 필드는 버리지 않고 보존한다.
    """
    model_config = ConfigDict(
        validate_by_name=True,
        extra='allow',
    )


def is_request_validation_error(exc: ValidationError) -> bool:
    """요청 모델(`RequestModel`)을 만들다 난 검증 오류인지. 즉 사용자 입력이 잘못된 경우.

    응답 모델이나 service 결과 모델의 검증 오류는 velog 응답이 예상과 달라진 것이라 입력 오류가 아니다.
    `ValidationError.title` 은 검증한 모델 클래스 이름이다.

    응답 값(다음 페이지 커서 등)으로 요청 모델을 만들다 난 오류도 여기서는 입력 오류로 보인다. 그 값이 실제로 형식에서
    벗어날 수 있는 곳만 그 자리에서 다른 에러로 바꾼다 (jibsa 에서 옮긴 규칙).
    새 엔드포인트의 규칙은 docs/development/provider-conventions.md '요청·응답 모델' 에 있다.
    """
    stack: list[type[BaseModel]] = [RequestModel]
    while stack:
        model = stack.pop()
        if model.__name__ == exc.title:
            return True
        stack.extend(model.__subclasses__())
    return False
