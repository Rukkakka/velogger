from typing import Any


class VeloggerError(Exception):
    """CLI 가 구조화된 에러로 보고하는 애플리케이션 에러.

    Args:
        code: 기계가 읽는 에러 코드 (예: NOT_LOGGED_IN).
        message: 사람이 읽는 설명.
        hint: 다음에 시도할 행동. Defaults to None.
        details: 에러 JSON 에 함께 실을 추가 필드. Defaults to None.
    """

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details or {}
