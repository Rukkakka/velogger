import json
import sys
from collections.abc import Generator
from contextlib import contextmanager

import typer
from httpx import (
    HTTPError,
    HTTPStatusError,
)
from pydantic import (
    BaseModel,
    ValidationError,
)
from typer._click.exceptions import (  # Typer 가 내장한 Click 의 예외. 비공개 경로라 Typer 업그레이드 시 확인 필요.
    ClickException,
    UsageError,
)
from typer._click.globals import get_current_context

from velogger.core.errors import VeloggerError
from velogger.core.schema import is_request_validation_error

from typing import (
    Any,
    TextIO,
)


def _dumps(data: Any, pretty: bool | None, stream: TextIO) -> str:
    """`stream` 에 쓸 JSON. 한글은 그대로 쓰되, `stream` 인코딩이 담지 못하는 글자가 있으면 `\\uXXXX` 로 쓴다.

    Windows 에서 `PYTHONUTF8` 없이 파이프로 받으면 stdout 이 cp949 라 이모지 같은 글자를 쓰다 `UnicodeEncodeError`
    (ValueError)가 나고, `handle_errors` 가 그것을 'velog 응답이 이상하다' 는 PARSE_ERROR 로 냈다. 쓰기는 이미 반영된 뒤라
    에이전트가 실패로 보고 다시 보낼 수 있었다. `\\uXXXX` 는 같은 값을 뜻하는 JSON 이라 읽는 쪽 결과는 같다.
    """
    if pretty is None:
        pretty = stream.isatty()
    indent = 2 if pretty else None
    separators = None if pretty else (',', ':')
    text = json.dumps(data, ensure_ascii=False, indent=indent, separators=separators)
    try:
        text.encode(getattr(stream, 'encoding', None) or 'utf-8')
    except (UnicodeEncodeError, LookupError):
        return json.dumps(data, ensure_ascii=True, indent=indent, separators=separators)
    return text


def emit(
    data: BaseModel | list[BaseModel] | dict[str, Any],
    pretty: bool | None = None,
    notes: list[str] | None = None,
) -> None:
    """결과를 JSON 으로 stdout 에 쓴다.

    값을 모르는 필드는 `null` 로 남기고, 해당 없는 필드는 모델이 키째 뺀다. `notes` 가 있으면 맨 앞에
    붙이고, 없으면 키를 뺀다 (검색 범위·일부 조회·주의 안내 등).
    """
    if isinstance(data, BaseModel):
        payload: Any = data.model_dump(mode='json')
    elif isinstance(data, list):
        payload = [item.model_dump(mode='json') for item in data]
    else:
        payload = data
    if not isinstance(payload, dict) and notes:
        payload = {'items': payload}
    if notes:
        payload = {'notes': notes, **payload}
    typer.echo(_dumps(payload, pretty, sys.stdout))


def emit_error(code: str, message: str, hint: str | None = None, /, **extra: Any) -> None:
    """`{"error": {...}}` 를 stderr 에 쓴다. 터미널이면 들여쓰기, 아니면 한 줄.

    `code`·`message`·`hint` 는 위치 인자로만 받아, `VeloggerError.details` 에 같은 이름의 키가 있어도
    인자가 겹쳐(TypeError) traceback 으로 끝나지 않는다. 겹친 키는 앞의 세 값을 덮어쓰지 않는다.
    """
    error: dict[str, Any] = {'code': code, 'message': message}
    if hint:
        error['hint'] = hint
    error.update({
        key: value for key, value in extra.items()
        if value is not None and key not in ('code', 'message', 'hint')
    })
    # 들여쓰기는 stdout 이 아니라 에러를 쓰는 stderr 가 터미널인지로 정한다 (`velogger ... | jq` 도 에러는 터미널에 보인다)
    typer.echo(_dumps({'error': error}, sys.stderr.isatty(), sys.stderr), err=True)


def _validation_message(error: Any) -> str:
    """요청 모델 검증 오류 문구. 검증 함수가 던진 ValueError 는 pydantic 이 붙이는 'Value error, ' 를 뗀다."""
    if error.get('type') == 'value_error' and 'error' in error.get('ctx', {}):
        return str(error['ctx']['error'])
    return error['msg']


def _usage_hint() -> str:
    """사용법 오류와 같은 '<명령> --help' 힌트. 명령 밖이면 일반 문구."""
    context = get_current_context(silent=True)
    if context is None:
        return '옵션 값을 확인하세요'
    return f"'{context.command_path} --help' 로 사용법을 확인하세요"


@contextmanager
def handle_errors() -> Generator[None, None, None]:
    """예외를 `{"error": {...}}` JSON 으로 stderr 에 쓰고 exit code 1 (입력 검증 실패는 2) 로 끝낸다.

    LLM 이 실패 원인을 읽고 다음 행동(재로그인·옵션 수정·재시도)을 고를 수 있도록 코드와 힌트를
    함께 남긴다. 예상하지 못한 예외도 traceback 대신 INTERNAL_ERROR 로 쓴다.
    """
    try:
        yield
    except VeloggerError as exc:
        emit_error(exc.code, exc.message, exc.hint, **exc.details)
        # 입력 오류(INVALID_ARGUMENT)는 사용법 오류와 같은 exit code 2 로 맞춘다
        raise typer.Exit(code=2 if exc.code == 'INVALID_ARGUMENT' else 1)
    except ValidationError as exc:
        if not is_request_validation_error(exc):
            # 응답 모델 검증 실패는 velog 응답이 바뀐 것이다. 입력을 고쳐도 소용없다.
            emit_error(
                'PARSE_ERROR',
                f'{exc.title} 검증 실패: ' + '; '.join(error['msg'] for error in exc.errors()),
                '비공식 API 응답 형식이 바뀌었을 수 있습니다. velogger 를 업데이트하거나 잠시 뒤 다시 시도하세요',
            )
            raise typer.Exit(code=1)
        emit_error(
            'INVALID_ARGUMENT',
            '; '.join(_validation_message(error) for error in exc.errors()),
            _usage_hint(),
        )
        raise typer.Exit(code=2)
    except HTTPStatusError as exc:
        status = exc.response.status_code
        code = {
            401: 'NOT_LOGGED_IN',
            403: 'FORBIDDEN',
            404: 'NOT_FOUND',
            429: 'RATE_LIMITED',
        }.get(status, 'UPSTREAM_ERROR')
        hint = {
            401: '로그인이 필요하거나 세션이 만료됐습니다. velogger login 으로 다시 로그인하세요',
            403: '권한이 없거나 차단된 요청입니다',
            404: '대상이 없는지(내려간 글·없는 사용자), ID·주소가 맞는지 확인하세요',
            429: '요청이 너무 잦습니다. 잠시 후 다시 시도하세요',
        }.get(status, '비공식 API 라 스펙이 바뀌었을 수 있습니다')
        emit_error(code, str(exc), hint, status=status)
        raise typer.Exit(code=1)
    except HTTPError as exc:
        emit_error(
            'NETWORK_ERROR',
            f'{type(exc).__name__}: {exc}',
            '네트워크 상태를 확인하고 다시 시도하세요',
        )
        raise typer.Exit(code=1)
    except ValueError as exc:
        # JSON 이 아닌 응답(차단 페이지 등)의 JSONDecodeError 포함
        emit_error(
            'PARSE_ERROR',
            f'{type(exc).__name__}: {exc}',
            '응답이 예상한 형식이 아닙니다. 차단 페이지이거나 구조가 바뀌었을 수 있습니다',
        )
        raise typer.Exit(code=1)
    except (ClickException, typer.Exit):
        # 사용법 오류와 정상 종료는 cli.app.run 이 처리한다
        raise
    except BrokenPipeError:
        # 출력을 받는 쪽(`| head` 등)이 먼저 닫았다. velogger 오류가 아니라 INTERNAL_ERROR 로 내지 않는다.
        raise
    except Exception as exc:
        emit_error(
            'INTERNAL_ERROR',
            f'{type(exc).__name__}: {exc}',
            'velogger 내부 오류입니다. velogger --verbose <명령> 으로 다시 실행해 로그를 확인하세요',
        )
        raise typer.Exit(code=1)


class HintedUsageError(UsageError):
    """기본 힌트('--help 로 확인') 대신 정해 둔 힌트를 싣는 사용법 오류."""

    def __init__(self, message: str, hint: str) -> None:
        super().__init__(message)
        self.hint = hint
