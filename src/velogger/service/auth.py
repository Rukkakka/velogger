"""로그인·세션 관련 흐름 (`velogger login`·`logout`·`whoami`).

velog 는 비밀번호가 없어, 이메일 매직 링크나 소셜 로그인으로 받은 세션 쿠키가 인증 수단이다.
여기서는 메일 보내기, code → 쿠키 교환, 붙여넣은 쿠키 검증, 로그인한 사용자 조회를 맡는다. 토큰 값은
출력 모델에 넣지 않는다 (로그인 여부·username·is_trusted 만 보여 준다).
"""

import logging
import re
from urllib.parse import unquote

from httpx import (
    HTTPError,
    HTTPStatusError,
    Response,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from velogger.api.client import VelogClient
from velogger.api.request.auth import VelogSendmailRequestPayloadModel
from velogger.api.response.auth import (
    VelogAuthUserModel,
    VelogCodeLoginResponseModel,
)
from velogger.core.errors import VeloggerError
from velogger.core.session import (
    Session,
    StoredCookie,
    save_session,
)
from velogger.service.common import fetch_auth

from typing import Annotated


logger = logging.getLogger(__name__)

# 링크·쿼리 문자열·`code=값` 어디에 있든 code 파라미터 값을 꺼낸다 (`velog.io/email-login?code=abc`, `code=abc`)
CODE_PARAM_PATTERN: re.Pattern[str] = re.compile(r'(?:^|[?&#])code=([^&#\s]+)')
# velog code 는 shortid(`0-9A-Za-z_-`)다 (velog-server `emailAuth.code = shortid.generate()`). 링크에서 꺼낸 값도 이
# 모양만 받는다: URL 디코드한 `../../posts?x=1` 같은 값이 경로에 들어가면 요청이 다른 엔드포인트로 갔다 (2026-10-20 재현).
# `.` 은 예전부터 받아 두고, `.`·`..` 처럼 점만 있는 값(경로의 상위 폴더)은 뺀다.
LOGIN_CODE_PATTERN: re.Pattern[str] = re.compile(r'(?!\.+$)[A-Za-z0-9._-]+')
# code 교환이 실패한 이유 (velog-server `GET /api/v2/auth/code/:code`): 없음 404, 이미 씀 403 + TOKEN_ALREADY_USED,
# 24시간 지남 410 + EXPIRED_CODE. 2026-10-20 실측: 없는 code 404, 이미 쓴 code 403. 410 은 소스 기준이다.
CODE_ALREADY_USED_NAME: str = 'TOKEN_ALREADY_USED'
LOGIN_CODE_FAILURES: dict[int, str] = {
    404: '로그인 code 를 찾지 못했습니다 (잘못 복사했거나 velog 가 지운 code 입니다)',
    403: '이미 쓴 로그인 code 입니다 (링크는 한 번만 쓸 수 있고, 브라우저로 열어도 쓰입니다)',
    410: '만료된 로그인 code 입니다 (링크는 24시간 안에 써야 합니다)',
}


class VelogLoginMailResult(BaseModel):
    """`velogger login` 으로 로그인 메일을 보낸 결과."""

    model_config = ConfigDict(extra='forbid')

    email: Annotated[str, Field(description='로그인 링크를 보낸 이메일')]
    registered: Annotated[
        bool | None,
        Field(description='이미 가입된 이메일인지. True 면 로그인 메일, False 면 가입 메일')
    ] = None
    message: Annotated[str, Field(description='다음에 할 일 안내')]


class VelogWhoami(BaseModel):
    """로그인 상태. 토큰·쿠키 값은 담지 않는다.

    로그인 정보는 로그인 여부·username·is_trusted 만 보여 준다 (AGENTS.md '꼭 지킬 것'). v2 `auth` 가 주는 계정
    이메일·사용자 ID 는 에이전트 대화 기록·로그에 남으므로 출력 모델로 옮기지 않는다.
    """

    model_config = ConfigDict(extra='forbid')

    logged_in: Annotated[bool, Field(description='로그인 여부')]
    username: Annotated[str | None, Field(description='velog 아이디 (@username)')] = None
    is_trusted: Annotated[
        bool | None,
        Field(description='신뢰 계정 여부. False 면 글 발행에 캡차(Turnstile)가 붙어 CLI 로는 발행할 수 없다')
    ] = None


def parse_login_code(raw: str) -> str:
    """로그인 메일에서 받은 링크나 code 문자열에서 code 만 꺼낸다.

    `velog.io/email-login?code=abc`, `https://velog.io/email-login?code=abc`, 또는 code 그 자체(`abc`)를
    모두 받는다.

    Raises:
        VeloggerError: code 를 찾지 못했을 때 (`INVALID_ARGUMENT`).
    """
    raw = raw.strip()
    # urlsplit 은 스킴 없는 `code=abc` 를 netloc 으로 읽어 query 가 비므로, code 파라미터를 직접 찾는다.
    # 링크가 아니면 code 를 그대로 준 것으로 본다.
    match = CODE_PARAM_PATTERN.search(raw)
    code = unquote(match.group(1)) if match else raw
    if LOGIN_CODE_PATTERN.fullmatch(code):
        return code
    raise VeloggerError(
        code='INVALID_ARGUMENT',
        message='로그인 code 를 찾지 못했습니다',
        hint='메일 속 링크(velog.io/email-login?code=...)를 통째로 붙여넣거나 code 값만 주세요',
    )


def parse_cookie_header(raw: str) -> list[StoredCookie]:
    """브라우저에서 복사한 쿠키 문자열(`name=value; name2=value2`)을 저장용 쿠키 목록으로 바꾼다.

    Raises:
        VeloggerError: `name=value` 쌍을 하나도 찾지 못했을 때 (`INVALID_ARGUMENT`).
    """
    cookies: list[StoredCookie] = []
    for part in raw.strip().split(';'):
        part = part.strip()
        if not part or '=' not in part:
            continue
        name, _, value = part.partition('=')
        name = name.strip()
        value = value.strip()
        if name and value:
            cookies.append(StoredCookie(name=name, value=value))
    if not cookies:
        raise VeloggerError(
            code='INVALID_ARGUMENT',
            message='쿠키를 찾지 못했습니다',
            hint="브라우저 개발자도구의 velog.io 쿠키를 'name=value; name2=value2' 형식으로 붙여넣으세요",
        )
    return cookies


def whoami(client: VelogClient) -> VelogWhoami:
    """현재 로그인 상태를 돌려준다 (로그인 안 했으면 `logged_in: false`).

    실을 세션 쿠키가 없으면 velog 에 묻지 않는다. 쿠키 없이 보낸 `auth` 는 늘 null 이라, 요청 제한 슬롯만 쓴다.
    """
    if not client.cookies:
        return VelogWhoami(logged_in=False)
    user = fetch_auth(client)
    if user is None:
        return VelogWhoami(logged_in=False)
    return _whoami_of(user)


def send_login_mail(client: VelogClient, email: str) -> VelogLoginMailResult:
    """그 이메일로 로그인(또는 가입) 링크를 보내 달라고 velog 에 요청한다."""
    response = client.run_request_sendmail(VelogSendmailRequestPayloadModel(email=email))
    if response.registered is False:
        message = (
            '이 이메일로 가입 링크를 보냈습니다 (아직 velog 계정이 없는 이메일입니다). '
            'velog 에 쓰는 이메일이 맞는지 확인하세요'
        )
    else:
        message = (
            '로그인 링크를 메일로 보냈습니다. 메일 속 링크(velog.io/email-login?code=...)를 복사해 '
            '`velogger login --code <링크>` 를 실행하세요. 링크는 브라우저로 열지 마세요'
        )
    return VelogLoginMailResult(email=email, registered=response.registered, message=message)


def complete_login_with_code(client: VelogClient, raw_code: str) -> VelogWhoami:
    """메일에서 받은 code 를 세션 쿠키로 바꾸고 세션을 저장한다.

    쿠키를 받자마자 저장한 뒤 `auth` 로 확인한다. 확인 요청만 실패하면 로그인 응답 본문의 사용자로 결과를 낸다.

    Raises:
        VeloggerError: code 가 다 쓰였거나 잘못됐을 때, 계정이 없는 이메일의 가입 링크일 때, velog 가 쿠키를 주지
            않았을 때, 받은 쿠키로 로그인되지 않을 때 (`LOGIN_FAILED`).
    """
    code = parse_login_code(raw_code)
    try:
        response = client.run_request_code(code)
    except HTTPStatusError as exc:
        # 그대로 두면 404 는 '내려간 글' 힌트의 NOT_FOUND, 403 은 '차단된 요청' 힌트의 FORBIDDEN, 410 은 '스펙이 바뀌었을
        # 수 있다' 는 UPSTREAM_ERROR 가 돼, 에이전트가 새 링크를 받는 대신 엉뚱한 원인을 찾는다
        status = exc.response.status_code
        if status not in LOGIN_CODE_FAILURES or (status == 403 and not _is_code_already_used(exc)):
            raise
        raise VeloggerError(
            code='LOGIN_FAILED',
            message=LOGIN_CODE_FAILURES[status],
            hint='`velogger login <이메일>` 로 새 링크를 받으세요. 링크는 브라우저로 열지 말고 복사만 하세요',
            details={'status': status},
        ) from None
    body = _code_login_body(response)
    cookies = client.current_cookies()
    if not cookies:
        if body.register_token:
            # 계정이 없는 이메일로 받은 가입 링크다. '만료됐을 수 있다' 고 하면 새 링크를 받아도 또 가입 링크가 와 되풀이된다
            raise VeloggerError(
                code='LOGIN_FAILED',
                message='velog 계정이 없는 이메일로 받은 가입 링크입니다 (로그인 code 가 아닙니다)',
                hint=(
                    'velog 에 가입된 이메일로 `velogger login <이메일>` 을 다시 실행하세요. 새로 가입하려면 그 메일의 링크를 '
                    '브라우저로 열어 velog.io 에서 가입을 마친 뒤 로그인하세요 (CLI 는 가입하지 않습니다)'
                ),
                details={'registered': False},
            )
        raise VeloggerError(
            code='LOGIN_FAILED',
            message='velog 가 세션 쿠키를 발급하지 않았습니다',
            hint='code 가 만료됐거나 이미 쓰였을 수 있습니다. `velogger login` 으로 새 링크를 받으세요',
        )
    # code 는 이 응답으로 다 썼다 (velog-server 가 `logged` 로 표시해 다시 보내면 403 TOKEN_ALREADY_USED). 아래 확인 요청이
    # 실패했다고 쿠키를 버리면 같은 링크로는 다시 로그인할 수 없어 메일을 새로 받아야 하므로, 쿠키부터 저장한다.
    save_session(Session(cookies=cookies, username=body.username))
    try:
        user = fetch_auth(client)
    except (VeloggerError, HTTPError, ValueError) as exc:
        # 확인 요청만 실패했다 (5xx·네트워크·요청 제한 등). 세션은 저장했고 쿠키는 velog 가 방금 이 code 로 발급한 것이라,
        # 실패로 내면 에이전트가 같은 code 로 다시 보내 'TOKEN_ALREADY_USED' 를 보고 새 링크를 받게 한다. 로그인 응답의
        # 사용자로 낸다 (모르는 is_trusted 는 null).
        logger.warning('로그인 확인 요청이 실패해 velog 로그인 응답의 사용자로 결과를 냅니다 (세션은 저장됨): %s', type(exc).__name__)
        return VelogWhoami(logged_in=True, username=body.username, is_trusted=body.is_trusted)
    return _save_verified(client, user)


def _code_login_body(response: Response) -> VelogCodeLoginResponseModel:
    """code 교환 응답 본문. JSON 이 아니거나 모양이 달라도 빈 모델로 본다 (쿠키는 이미 받았을 수 있어 여기서 실패하지 않는다)."""
    try:
        return VelogCodeLoginResponseModel.model_validate(response.json())
    except ValueError:
        return VelogCodeLoginResponseModel()


def _is_code_already_used(exc: HTTPStatusError) -> bool:
    """403 이 velog 의 '이미 쓴 code' 인지. 앞단(Cloudflare 등)의 403 차단 페이지는 그대로 FORBIDDEN 으로 둔다."""
    try:
        body = exc.response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get('name') == CODE_ALREADY_USED_NAME


def verify_and_save_session(client: VelogClient) -> VelogWhoami:
    """클라이언트에 실린 쿠키가 실제로 로그인되는지 확인하고 세션으로 저장한다 (쿠키 붙여넣기용).

    Raises:
        VeloggerError: 그 쿠키로 로그인되지 않을 때 (`LOGIN_FAILED`).
    """
    return _save_verified(client, fetch_auth(client))


def _save_verified(client: VelogClient, user: VelogAuthUserModel | None) -> VelogWhoami:
    """`auth` 로 확인한 사용자로 세션을 저장한다. `user` 가 None(그 쿠키로 로그인되지 않음)이면 `LOGIN_FAILED`."""
    if user is None:
        raise VeloggerError(
            code='LOGIN_FAILED',
            message='쿠키가 로그인 상태로 이어지지 않았습니다',
            hint='만료됐거나 잘못된 쿠키입니다. `velogger login` 으로 이메일 로그인하거나 쿠키를 다시 복사하세요',
        )
    # 쿠키는 auth 응답을 받은 뒤에 읽는다. 붙여넣은 access_token 이 만료됐으면 v2 가 이 응답의 Set-Cookie 로 새 토큰을
    # 주는데, 먼저 읽어 두면 만료된 토큰이 저장된다 (2026-10-20 재현: 13시간 전 만료된 토큰이 그대로 저장됐다)
    save_session(Session(cookies=client.current_cookies(), username=user.username))
    return _whoami_of(user)


def _whoami_of(user: VelogAuthUserModel) -> VelogWhoami:
    return VelogWhoami(
        logged_in=True,
        username=user.username,
        is_trusted=user.is_trusted,
    )
