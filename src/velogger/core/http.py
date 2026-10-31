import json
import logging
import re
from abc import (
    ABC,
    abstractmethod,
)
from collections.abc import (
    Awaitable,
    Callable,
)
from datetime import (
    datetime,
    timezone,
)
from email.utils import parsedate_to_datetime
from functools import cached_property
from math import isfinite
from types import TracebackType
from urllib.parse import (
    urlsplit,
    urlunsplit,
)

from httpx import (
    AsyncClient,
    Client,
    HTTPStatusError,
    NetworkError,
    RemoteProtocolError,
    Response,
    TimeoutException,
    TransportError,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from tenacity import RetryCallState

from velogger.core.ratelimit import (
    RateLimiter,
    RateLimitPolicy,
)

from typing import (
    Annotated,
    ClassVar,
    Literal,
    TypeVar,
)


logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT: str = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36'
)

# 다시 보내면 나을 수 있는 전송 오류: 시간 초과, 연결·읽기·쓰기 실패, 서버가 응답 중 끊음. 프록시 거절(ProxyError)·
# 지원하지 않는 URL(UnsupportedProtocol)·요청 형식 오류(LocalProtocolError)처럼 다시 보내도 같은 TransportError 는 빼서
# 재시도 대기와 요청 제한 슬롯을 쓰지 않는다 (2026-10-14 확인: CONNECT 를 403 으로 거절하는 프록시에 3번 시도)
RETRYABLE_TRANSPORT_ERRORS: tuple[type[TransportError], ...] = (TimeoutException, NetworkError, RemoteProtocolError)

BODY_PREVIEW_LIMIT: int = 2048
RETRY_BODY_PREVIEW_LIMIT: int = 200
SENSITIVE_KEY_PATTERN: re.Pattern[str] = re.compile(
    r'(token|secret|password|passwd|api[-_]?key|access[-_]?key|'
    r'private[-_]?key|service[-_]?key|authorization|cookie|credential)',
    re.IGNORECASE,
)
SENSITIVE_TEXT_PATTERN: re.Pattern[str] = re.compile(
    r'([\w-]*(?:token|secret|password|passwd|api[-_]?key|access[-_]?key|'
    r'private[-_]?key|service[-_]?key|authorization|cookie|credential)'
    r'[\w-]*\s*[=:]\s*)'
    r'([^,\s&}\n]+)',
    re.IGNORECASE,
)
# 경로에 자격증명이 들어가는 엔드포인트. velog 로그인 code 는 `/api/v2/auth/code/{code}` 처럼 경로에 실려, 쿼리만
# 지워서는 에러 메시지·재시도 로그에 그대로 남는다 (2026-10-20 확인: 404 에러 JSON 에 code 가 찍혔다).
# 로그 한 줄(`GET https://.../auth/code/abc "HTTP/1.1 404"`)에도 쓰므로 공백·따옴표·쿼리 앞에서 멈춘다.
SENSITIVE_PATH_PATTERN: re.Pattern[str] = re.compile(r'(/auth/code/)[^/?#\s"]+')

_T = TypeVar('_T', bound='BaseHTTPClient')


def create_base_url(schema: Literal['https', 'http'], host: str) -> str:
    return f'{schema}://{host}'


def _redact_json(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: '<redacted>'
            if SENSITIVE_KEY_PATTERN.search(str(key))
            else _redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    return SENSITIVE_TEXT_PATTERN.sub(r'\1<redacted>', value)


def _safe_request_url(url: object) -> str:
    parts = urlsplit(str(url))
    netloc = parts.netloc.rsplit('@', 1)[-1]
    path = SENSITIVE_PATH_PATTERN.sub(r'\1<redacted>', parts.path)
    return urlunsplit((parts.scheme, netloc, path, '', ''))


class SensitivePathLogFilter(logging.Filter):
    """httpx 요청 로그(`HTTP Request: GET <url> ...`)에서 경로에 실린 자격증명을 가린다.

    `--verbose` 는 httpx 의 INFO 로그로 요청 URL 을 통째로 찍어, 로그인 code 가 `/auth/code/<code>` 로 그대로 남았다
    (2026-10-20 실측: 502 재시도 때마다 한 줄씩). 요청 로그는 API 감시 기록에 쓰여 끄지 않고 경로만 가린다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = SENSITIVE_PATH_PATTERN.sub(r'\1<redacted>', message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


# 로거 필터는 그 로거에 직접 남긴 기록에만 걸린다. httpx 는 요청 로그를 'httpx' 로거에 남긴다.
logging.getLogger('httpx').addFilter(SensitivePathLogFilter())


class ResponseStatusError(HTTPStatusError):
    """`HTTPStatusError` whose message carries a truncated response body."""


def _request_origin(exc: HTTPStatusError) -> str:
    """Name the request behind a status error without assuming one was attached.

    `HTTPStatusError.request` raises rather than returning None when the error
    was built without one, so the attribute is never read unguarded.
    """
    try:
        request = exc.request
    except RuntimeError:
        return '<unknown request>'
    return f'{request.method} {_safe_request_url(request.url)}'


def _body_preview(response: Response, limit: int = BODY_PREVIEW_LIMIT) -> str:
    """Render a response body short enough to sit inside an exception message.

    A body that was never read raises rather than returning text, so every
    failure here resolves to a marker instead of propagating.
    """
    try:
        body = response.text
    except Exception:
        return '<unread>'

    body = body.strip()
    if not body:
        return '<empty>'

    try:
        body = json.dumps(
            _redact_json(json.loads(body)),
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError):
        body = _redact_text(body)

    if len(body) > limit:
        return f'{body[:limit]}... (truncated, {len(body)} chars)'
    return body


def raise_for_status(response: Response, limit: int = BODY_PREVIEW_LIMIT) -> None:
    """`Response.raise_for_status` that keeps the error body in the message.

    비공식 API 는 거절 사유를 본문에만 담아 보내므로 본문을 잘라 예외 메시지에
    붙인다. 헤더는 인증정보(쿠키)가 있으므로 넣지 않는다.

    Raises:
        ResponseStatusError: If the response carries a `4xx` or `5xx` status.
            It subclasses `HTTPStatusError`, so retry predicates that match on
            that type are unaffected.
    """
    try:
        response.raise_for_status()
    except HTTPStatusError as exc:
        raise ResponseStatusError(
            f'{_request_origin(exc)} -> '
            f'{response.status_code} {response.reason_phrase}\n'
            f'Response body: {_body_preview(response, limit)}',
            request=exc.request,
            response=exc.response,
        ) from None


def describe_failed_attempt(
    exc: BaseException | None,
    limit: int = RETRY_BODY_PREVIEW_LIMIT,
) -> str:
    """Render a failed attempt as one line for the retry log."""
    if exc is None:
        return '<no exception recorded>'
    if not isinstance(exc, HTTPStatusError):
        return f'{type(exc).__name__}: {exc}'

    body = ' '.join(_body_preview(exc.response, limit).split())
    return (
        f'{_request_origin(exc)} -> '
        f'{exc.response.status_code} {exc.response.reason_phrase} '
        f'| body: {body}'
    )


def should_retry_idempotent(exc: BaseException) -> bool:
    if isinstance(exc, HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code == 429
    return isinstance(exc, RETRYABLE_TRANSPORT_ERRORS)


def should_retry_non_idempotent(exc: BaseException) -> bool:
    """상태를 바꾸는 호출(글·댓글 작성, 메일 발송 등)용 재시도 술어. 서버가 처리하지 않았다고 볼 수 있는 실패만 다시 보낸다.

    재시도 규약(docs/development/provider-conventions.md '재시도')이 상태를 바꾸는 호출에 이 술어를 쓰라고 정해 두었다.

    - 429·503 만 재시도한다. 둘 다 서버가 요청을 받지 않고 돌려보낸 응답이다.
    - 502·504(게이트웨이)·500 은 원 서버가 이미 처리한 뒤 응답만 잃었을 수 있어 다시 보내지 않는다. 다시 보내면
      글·댓글·시리즈가 두 번 생긴다. velog v2 는 내부 에러를 HTTP 200 + null 로 삼키므로, 쓰기에서 5xx 는 대개 앞단
      게이트웨이가 낸 것이다.
    - timeout·transport 오류도 서버에 이미 닿았을 수 있어 다시 보내지 않는다.
    """
    if isinstance(exc, HTTPStatusError):
        return exc.response.status_code in (429, 503)
    return False


def retry_after_seconds(header: str) -> float | None:
    """Read a `Retry-After` value in either form RFC 9110 allows.

    Args:
        header (str): Raw header value, as delay-seconds or an HTTP-date.

    Returns:
        float | None: Seconds to wait, or None when the value parses as
            neither form.
    """
    try:
        seconds = float(header)
    except ValueError:
        pass
    else:
        return seconds if isfinite(seconds) else None

    try:
        deadline = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if deadline is None:
        return None
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (deadline - datetime.now(timezone.utc)).total_seconds()


def wait_retry_after(
    retry_state: RetryCallState,
    default: float = 1.0,
    maximum: float = 60.0,
) -> float:
    """Honour a rate-limit `Retry-After` header, capped at `maximum` seconds.

    Waits `default` seconds when the failure carries no usable header.
    """
    outcome = retry_state.outcome
    if outcome is None:
        return default

    exc = outcome.exception()
    if not isinstance(exc, HTTPStatusError):
        return default

    header = exc.response.headers.get('Retry-After')
    if not header:
        return default

    seconds = retry_after_seconds(header)
    if seconds is None:
        return default

    return min(max(seconds, 0.0), maximum)


def log_retry_before_sleep(retry_state: RetryCallState) -> None:
    outcome = retry_state.outcome
    next_action = retry_state.next_action
    if outcome is None or next_action is None:
        return

    logger.warning(
        'Attempt %s failed: %s | Retrying in %ss...',
        retry_state.attempt_number,
        describe_failed_attempt(outcome.exception()),
        next_action.sleep,
    )


class BaseHTTPClient(BaseModel, ABC):
    """Shared base model for the httpx-based provider clients.

    Defines the connection options every provider shares and a unified
    lifecycle for the sync/async httpx clients. Subclasses declare their own
    `host` and build `_client` / `_async_client` with ``@cached_property``.

    Args:
        url_schema: URL scheme used to build `base_url`. Defaults to 'https'.
        verify: TLS certificate verification flag. Defaults to True.
        proxy: Optional proxy URL. Defaults to None.
        timeout: Request timeout in seconds. Defaults to 20.
        user_agent: `User-Agent` header value. Defaults to a desktop Chrome UA.
        rate_limit: 프로세스 간 공유 요청 제한 정책. None 이면 클래스의
            `default_rate_limit` 을 쓴다. Defaults to None.

    Attributes:
        source_name: 요청 제한 상태 파일 이름 (서브클래스가 지정).
        default_rate_limit: 서브클래스 기본 제한 정책.
        rate_limiter: `source_name` 과 정책으로 만든 `RateLimiter`. 서브클래스는
            `rate_limit_hooks()` / `async_rate_limit_hooks()` 를 httpx 클라이언트의
            `event_hooks` 로 넘긴다.
    """

    source_name: ClassVar[str] = 'default'
    default_rate_limit: ClassVar[dict[str, object]] = {}

    model_config = ConfigDict(
        extra='forbid',
    )

    url_schema: Literal['http', 'https'] = 'https'

    verify: bool = True

    proxy: str | None = None

    timeout: Annotated[
        int,
        Field(gt=0)
    ] = 20

    user_agent: str = DEFAULT_USER_AGENT

    rate_limit: RateLimitPolicy | None = None

    @cached_property
    def rate_limiter(self) -> RateLimiter:
        policy = self.rate_limit or RateLimitPolicy(**self.default_rate_limit)
        return RateLimiter(self.source_name, policy)

    def rate_limit_hooks(self) -> dict[str, list[Callable[..., None]]]:
        return self.rate_limiter.event_hooks()

    def async_rate_limit_hooks(self) -> dict[str, list[Callable[..., Awaitable[None]]]]:
        # async 쪽(이 훅, `_async_client`)은 CLI 가 부르지 않지만, async 로 부르고 싶은 엔드포인트가 생기면 `arun_request_*` 를
        # 짝으로 더할 기반이라 일부러 둔다. velogger 에는 아직 `arun_request_*` 가 하나도 없다 (provider-conventions.md '요청
        # 메서드'). 호출부 0건은 죽은 코드가 아니다
        return self.rate_limiter.async_event_hooks()

    @property
    @abstractmethod
    def _client(self) -> Client:
        """
        Synchronous HTTP client. Subclasses must override this with
        ``@cached_property`` so `close()` can locate it via
        ``__dict__.pop('_client', None)``. ``@cached_property`` cannot be
        combined with ``@abstractmethod``, so the abstract declaration stays a
        plain property.
        """
        ...

    @property
    @abstractmethod
    def _async_client(self) -> AsyncClient:
        """
        Asynchronous HTTP client. Subclasses must override this with
        ``@cached_property``; see ``_client``.
        """
        ...

    def close(self) -> None:
        """
        Close the sync client only: an async client cannot be closed from
        sync code. If ``_async_client`` was used (e.g. by an ``arun_request_*``
        method a subclass adds), close with ``aclose()`` or ``async with``
        instead (a plain ``with`` leaves the async pool open).
        """
        client: Client | None = self.__dict__.pop('_client', None)
        if client is not None:
            client.close()

    async def aclose(self) -> None:
        """
        Close the async client and, since a sync close is safe to call from
        async code, the sync client too.
        """
        async_client: AsyncClient | None = self.__dict__.pop('_async_client', None)
        if async_client is not None:
            await async_client.aclose()
        self.close()

    def __enter__(self: _T) -> _T:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None
    ) -> None:
        self.close()

    async def __aenter__(self: _T) -> _T:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None
    ) -> None:
        await self.aclose()

