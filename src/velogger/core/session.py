"""로그인 세션(velog 가 발급한 쿠키)을 로컬 파일에 저장하고 읽는다.

velog 는 비밀번호가 없다. 이메일 매직 링크나 소셜 로그인으로 받은 **세션 쿠키**(access_token·
refresh_token 등)가 곧 인증 수단이다. 그 쿠키를 `<config_dir>/session.json` 에 사용자만 읽을 수
있는 권한(0600)으로 저장한다. 토큰 값은 비밀이라 로그·출력에 내보내지 않는다 (CLI 는 쿠키 값을
emit 하지 않고, 로그인 여부·사용자 이름만 보여 준다).

쿠키 이름을 코드에 박지 않는다. velog 가 응답으로 주는 Set-Cookie 를 이름 그대로 통째로 담아,
velog 가 쿠키 구성을 바꿔도(이름 추가·변경) 그대로 따라간다.
"""

import contextlib
import json
import os
import stat
import tempfile
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from velogger.core.errors import VeloggerError

from typing import (
    Annotated,
    Any,
)


class SessionError(VeloggerError):
    """세션 파일을 읽거나 쓰지 못했을 때 (권한·샌드박스·디스크), 또는 로그인이 필요한데 세션이 없을 때."""


class StoredCookie(BaseModel):
    """저장하는 쿠키 하나. velog 응답의 Set-Cookie 를 이름·값·도메인·경로 그대로 담는다."""

    model_config = ConfigDict(extra='forbid')

    name: Annotated[str, Field(description='쿠키 이름 (예: access_token)')]
    value: Annotated[str, Field(repr=False, description='쿠키 값 (비밀). 출력하지 않는다')]
    domain: Annotated[str, Field(description='쿠키 도메인 (예: .velog.io)')] = '.velog.io'
    path: Annotated[str, Field(description='쿠키 경로')] = '/'


class Session(BaseModel):
    """로그인 세션. velog 가 준 쿠키 묶음과, 참고용 사용자 이름.

    Args:
        cookies: velog 가 발급한 쿠키들. 인증이 필요한 요청에 그대로 실어 보낸다.
        username: 로그인한 계정의 username. 표시용이며 인증에는 쓰지 않는다 (쿠키가 인증한다).
    """

    model_config = ConfigDict(extra='forbid')

    cookies: list[StoredCookie] = Field(default_factory=list)
    username: str | None = None

    def is_empty(self) -> bool:
        return not self.cookies


def config_dir() -> Path:
    """세션 파일 디렉터리. `VELOGGER_CONFIG_DIR` > `$XDG_CONFIG_HOME/velogger` > `~/.config/velogger`.

    요청 제한 상태(`~/.cache/velogger`)와 달리 로그인 자격이라 cache 가 아니라 config 에 둔다.
    """
    override = os.environ.get('VELOGGER_CONFIG_DIR')
    if override:
        return Path(override)
    config_home = os.environ.get('XDG_CONFIG_HOME')
    base = Path(config_home) if config_home else Path.home() / '.config'
    return base / 'velogger'


def session_path() -> Path:
    return config_dir() / 'session.json'


def load_session() -> Session:
    """저장된 세션을 읽는다. 없으면 빈 세션. 깨졌으면(JSON 해석 실패) 빈 세션으로 본다.

    Raises:
        SessionError: 파일은 있는데 권한·디스크 문제로 읽지 못할 때.
    """
    path = session_path()
    try:
        raw = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return Session()
    except OSError as exc:
        raise SessionError(
            code='INTERNAL_ERROR',
            message=f'세션 파일({path})을 읽을 수 없습니다 ({type(exc).__name__})',
            hint='VELOGGER_CONFIG_DIR 로 읽을 수 있는 폴더를 지정하거나 파일 권한을 확인하세요',
        ) from exc
    try:
        data: Any = json.loads(raw)
        return Session.model_validate(data)
    except ValueError:
        # 손상된 세션은 로그인하지 않은 것으로 본다. 다음 로그인이 덮어쓴다.
        return Session()


def save_session(session: Session) -> None:
    """세션을 사용자만 읽을 수 있는 권한(0600)으로 저장한다.

    먼저 0600 으로 임시 파일에 쓰고 바꿔치기해, 다른 사용자가 중간 상태의 토큰을 보지 못하게 한다.

    Raises:
        SessionError: 디렉터리·파일을 쓰지 못할 때.
    """
    path = session_path()
    directory = path.parent
    tmp: str | None = None
    try:
        created = not directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        if created:
            # 새로 만든 폴더만 사용자 전용으로 둔다 (토큰이 든 파일이 있는 곳이라). VELOGGER_CONFIG_DIR 로 고른 기존 폴더의
            # 권한은 건드리지 않는다 (2026-10-20 재현: 755 폴더가 700 으로 바뀌어 그 폴더를 같이 쓰던 쪽이 깨질 수 있었다)
            os.chmod(directory, stat.S_IRWXU)
        # mkstemp 는 늘 새 이름으로 0600 파일을 만든다. 고정 이름(session.tmp)을 O_CREAT 로 열면 남아 있던 파일의 권한을
        # 그대로 물려받아, 0644 로 남은 tmp 가 있으면 session.json 이 누구나 읽을 수 있게 됐다 (2026-10-20 재현)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix='.session-', suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(session.model_dump(), file, ensure_ascii=False)
        os.replace(tmp, path)
        tmp = None
    except OSError as exc:
        raise SessionError(
            code='INTERNAL_ERROR',
            message=f'세션 파일({path})을 쓸 수 없습니다 ({type(exc).__name__})',
            hint='VELOGGER_CONFIG_DIR 로 쓸 수 있는 폴더를 지정하거나, 샌드박스면 그 폴더 쓰기를 허용하세요',
        ) from exc
    finally:
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)


def clear_session() -> bool:
    """세션 파일을 지운다 (로그아웃). 지웠으면 True, 원래 없었으면 False.

    Raises:
        SessionError: 파일을 지우지 못할 때.
    """
    path = session_path()
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise SessionError(
            code='INTERNAL_ERROR',
            message=f'세션 파일({path})을 지울 수 없습니다 ({type(exc).__name__})',
            hint='파일 권한을 확인하세요',
        ) from exc
