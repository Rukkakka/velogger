import io
import json
import logging
import re
import sys
import unicodedata
from collections.abc import (
    Iterator,
    Sequence,
)
from contextlib import contextmanager
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path

import typer
from typer._click import (  # Typer 가 내장한 Click. 비공개 경로라 Typer 업그레이드 시 확인 필요.
    Command,
    Context,
    HelpFormatter,
)
from typer._click.exceptions import (
    ClickException,
    NoArgsIsHelpError,
    NoSuchOption,
    UsageError,
)
from typer.core import (
    TyperCommand,
    TyperGroup,
)

from velogger.api.client import VelogClient
from velogger.api.request.cache import Timeframe
from velogger.cli.output import (
    HintedUsageError,
    emit,
    emit_error,
    handle_errors,
)
from velogger.core.errors import VeloggerError
from velogger.core.ratelimit import state_dir
from velogger.core.session import (
    Session,
    SessionError,
    StoredCookie,
    clear_session,
    load_session,
    save_session,
    session_path,
)
from velogger.service.auth import (
    complete_login_with_code,
    parse_cookie_header,
    send_login_mail,
    verify_and_save_session,
    whoami,
)
from velogger.service.common import not_logged_in_error
from velogger.service.post import read_post
from velogger.service.posts import (
    get_recent,
    get_tag_posts,
    get_trending,
    get_user_posts,
    search_posts,
)
from velogger.service.social import (
    get_comments,
    get_feed,
    get_followers,
    get_followings,
    get_reading_list,
    get_series,
)
from velogger.service.users import (
    get_tag_info,
    get_user,
)
from velogger.service.write import (
    add_to_series,
    create_series,
    edit_comment,
    edit_post,
    follow_user,
    get_drafts,
    get_stats,
    like_post,
    publish,
    remove_comment,
    unfollow_user,
    unlike_post,
    upload_image,
    write_comment,
)

from typing import Annotated


logger = logging.getLogger(__name__)

INTERRUPTED_EXIT_CODE: int = 130
INTERRUPTED_HINT: str = '호출한 쪽이 실행을 끊었습니다. 결과가 필요하면 같은 명령을 다시 실행하세요'
SHORT_COMMIT_LENGTH: int = 7
# 설치본에는 pyproject.toml 의 force-include 로 패키지 안에, 편집 가능 설치에는 저장소 docs/ 에만 있다
GUIDE_FILE: str = 'llm.md'
GUIDE_TOPICS: dict[str, str] = {
    'common': 'common.md',
    'velogger': 'velogger.md',
}
HEADING_PATTERN: re.Pattern[str] = re.compile(r'^(#{2,4})\s+(.*)$')
BACKTICK_PATTERN: re.Pattern[str] = re.compile(r'`([^`]+)`')
GUIDE_URL: str = 'https://github.com/Rukkakka/velogger/blob/main/docs/llm.md'
# `--file -` 이면 본문을 stdin 에서 읽는다
STDIN_FILE: str = '-'
# 본문 파일·stdin 인코딩. Windows PowerShell 5(`Set-Content -Encoding UTF8`)·옛 메모장은 UTF-8 앞에 BOM 을 붙여, 'utf-8' 로
# 읽으면 본문 첫 글자가 U+FEFF 가 돼 첫 줄 제목(# ...)이 제목으로 렌더링되지 않는다. utf-8-sig 는 BOM 이 있으면 떼고 없으면
# utf-8 과 같다.
BODY_ENCODING: str = 'utf-8-sig'
# 터미널이 아닐 때 도움말 폭. 옵션 설명이 줄바꿈 없이 한 줄에 들어가게 넉넉히 잡는다
PLAIN_HELP_WIDTH: int = 1000

app = typer.Typer(
    name='velogger',
    help=(
        'velogger: velog(velog.io) 비공식 CLI. 결과는 JSON 으로 stdout 에, 에러는 {"error": {...}} JSON 으로 stderr 에 쓴다. '
        '로그인이 필요한 기능은 `velogger login` 으로 먼저 로그인한다.'
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

PrettyOption = Annotated[
    bool | None,
    typer.Option('--pretty/--compact', help='JSON 들여쓰기. 기본값은 터미널이면 pretty, 파이프면 compact'),
]


def show_version(value: bool) -> None:
    """`--version` 이 주어지면 버전 한 줄을 stdout 에 쓰고 끝낸다."""
    if not value:
        return
    with handle_errors():
        typer.echo(version_text())
    raise typer.Exit()


@app.callback()
def configure_logging(
    verbose: Annotated[bool, typer.Option('--verbose', '-v', help='재시도 등 진행 로그를 stderr 에 출력')] = False,
    version: Annotated[
        bool,
        typer.Option('--version', callback=show_version, is_eager=True, help='설치된 velogger 버전을 출력하고 끝낸다'),
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.ERROR,
        format='%(levelname)s %(name)s: %(message)s',
    )


@app.command('login')
def login_command(
    email: Annotated[
        str | None,
        typer.Argument(help='로그인 링크를 받을 이메일. velog 가 그 주소로 로그인 링크를 보낸다')
    ] = None,
    code: Annotated[
        str | None,
        typer.Option('--code', help='메일 속 링크(velog.io/email-login?code=...) 또는 code 값. 이걸로 로그인을 마친다')
    ] = None,
    cookie: Annotated[
        str | None,
        typer.Option('--cookie', help="브라우저에서 복사한 velog.io 쿠키 ('name=value; ...'). 소셜 가입자용 대체 방법")
    ] = None,
) -> None:
    """velog 에 로그인한다 (velog 는 비밀번호가 없어 이메일 링크나 쿠키로 로그인한다).

    흐름 (이메일, 기본):
      1. velogger login <이메일>            → velog 가 그 주소로 로그인 링크를 보낸다
      2. 메일의 링크를 복사 (브라우저로 열지 말 것)
      3. velogger login --code <링크>       → 세션을 저장한다

    쿠키 붙여넣기 (대체): velogger login --cookie 'name=value; ...'

    로그인 code·쿠키는 네 계정의 열쇠다. 신뢰할 수 없는 곳에 넘기지 마라.
    """
    given = [name for name, value in (('--code', code), ('--cookie', cookie)) if value]
    if len(given) > 1:
        raise HintedUsageError(
            '--code 와 --cookie 는 함께 쓸 수 없습니다',
            '로그인을 마치려면 --code 하나만, 쿠키로 하려면 --cookie 하나만 주세요',
        )
    with handle_errors():
        if code is not None:
            with VelogClient() as client:
                emit(complete_login_with_code(client, code))
        elif cookie is not None:
            client = VelogClient(cookies=parse_cookie_header(cookie))
            with client:
                emit(verify_and_save_session(client))
        elif email is not None:
            with VelogClient() as client:
                emit(send_login_mail(client, email))
        else:
            raise HintedUsageError(
                '이메일이나 --code, --cookie 중 하나가 필요합니다',
                '먼저 `velogger login <이메일>` 로 로그인 링크를 받고, 메일 속 링크로 `velogger login --code <링크>` 를 실행하세요',
            )


@app.command('logout')
def logout_command(pretty: PrettyOption = None) -> None:
    """저장된 세션을 지운다 (로컬에서만. velog 서버 세션은 그대로다)."""
    with handle_errors():
        removed = clear_session()
        emit({'logged_out': removed, 'session_path': str(session_path())}, pretty)


@app.command('whoami')
def whoami_command(pretty: PrettyOption = None) -> None:
    """지금 로그인한 계정을 보여 준다. 로그인 안 했으면 logged_in: false.

    is_trusted 가 false 면 글 발행에 캡차가 붙어 CLI 로는 발행할 수 없다.
    """
    with handle_errors(), _session_client() as client:
        emit(whoami(client), pretty)


@app.command('limits')
def limits_command(
    reset: Annotated[bool, typer.Option('--reset', help='쿨다운·요청 기록을 지운다')] = False,
    pretty: PrettyOption = None,
) -> None:
    """요청 제한 상태 (쿨다운 남은 시간, 최근 1분 요청 수, 정책). 네트워크 요청은 보내지 않는다."""
    with handle_errors():
        limiter = VelogClient().rate_limiter
        if reset:
            limiter.reset()
        emit({'state_dir': str(state_dir()), 'velog': limiter.status()}, pretty)


LimitOption = Annotated[int, typer.Option(min=1, max=100, help='받을 글 수 (최대 100)')]
CursorOption = Annotated[str | None, typer.Option('--cursor', help='다음 페이지 커서 (이전 결과의 next_cursor)')]


@app.command('trending')
def trending_command(
    period: Annotated[Timeframe, typer.Option('--period', help='집계 기간')] = 'week',
    limit: LimitOption = 20,
    offset: Annotated[int, typer.Option(min=0, help='건너뛸 글 수 (페이지)')] = 0,
    pretty: PrettyOption = None,
) -> None:
    """트렌딩 글 목록 (기간: day·week·month·year). 본문은 velogger post <username> <url_slug>."""
    with handle_errors(), _session_client() as client:
        emit(get_trending(client, timeframe=period, limit=limit, offset=offset), pretty)


@app.command('recent')
def recent_command(limit: LimitOption = 20, cursor: CursorOption = None, pretty: PrettyOption = None) -> None:
    """최신 글 목록. 상단에 스팸이 끼기도 한다 (velog 서버 결과를 그대로 전한다). 다음 페이지는 next_cursor 를 --cursor 로."""
    with handle_errors(), _session_client() as client:
        emit(get_recent(client, limit=limit, cursor=cursor), pretty)


@app.command('search')
def search_command(
    keyword: Annotated[str, typer.Argument(help='검색어')],
    user: Annotated[str | None, typer.Option('--user', help='이 사용자(@username)의 글만 검색')] = None,
    limit: LimitOption = 20,
    offset: Annotated[int, typer.Option(min=0, help='건너뛸 글 수 (페이지)')] = 0,
    pretty: PrettyOption = None,
) -> None:
    """글 검색. count 로 전체 결과 수를 알려 준다."""
    with handle_errors(), _session_client() as client:
        emit(search_posts(client, keyword, username=user, offset=offset, limit=limit), pretty)


@app.command('posts')
def posts_command(
    username: Annotated[str, typer.Argument(help='글쓴이 아이디 (@ 없이)')],
    tag: Annotated[str | None, typer.Option('--tag', help='이 사용자 글 중 태그 필터')] = None,
    limit: LimitOption = 20,
    cursor: CursorOption = None,
    pretty: PrettyOption = None,
) -> None:
    """한 사용자의 글 목록. 다음 페이지는 next_cursor 를 --cursor 로. 전역 태그 검색은 velogger tag <name> 을 쓴다."""
    with handle_errors(), _session_client() as client:
        emit(get_user_posts(client, username, tag=tag, limit=limit, cursor=cursor), pretty)


@app.command('post')
def post_command(
    username: Annotated[str, typer.Argument(help='글쓴이 아이디 (@ 없이)')],
    url_slug: Annotated[str, typer.Argument(help='글 url_slug (목록의 url_slug)')],
    pretty: PrettyOption = None,
) -> None:
    """글 하나의 본문(마크다운)과 메타·시리즈·이전/다음 글.

    예: velogger post teo ai-native-fe
    """
    with handle_errors(), _session_client() as client:
        detail = read_post(client, username, url_slug)
        emit(detail, pretty, detail.notes or None)


@app.command('user')
def user_command(
    username: Annotated[str, typer.Argument(help='사용자 아이디 (@ 없이)')],
    pretty: PrettyOption = None,
) -> None:
    """사용자 프로필·많이 쓴 태그·시리즈 목록. 글 목록은 velogger posts <username>."""
    with handle_errors(), _session_client() as client:
        emit(get_user(client, username), pretty)


@app.command('tag')
def tag_command(
    name: Annotated[str, typer.Argument(help='태그 이름')],
    limit: LimitOption = 20,
    cursor: CursorOption = None,
    pretty: PrettyOption = None,
) -> None:
    """태그별 글 목록(+태그 설명). 전체 글 수는 count, 다음 페이지는 결과의 next_cursor 를 --cursor 로 넘긴다."""
    with handle_errors(), _session_client() as client:
        listing = get_tag_posts(client, name, limit=limit, cursor=cursor)
        payload = listing.model_dump()
        # 태그 설명은 페이지마다 같아 첫 페이지에서만 받는다 (요청을 줄인다). 이 조회가 실패하면 받은 목록까지 에러로 끝내는
        # 것은 일부러다: 늘 실패하는 태그는 없고(2026-10-23 실측: c#·c++·.net·공백·%·이모지·300자·없는 태그 모두 에러 없이 응답,
        # 없는 태그는 null) 남는 것은 재시도 3번 뒤의 일시적 실패뿐이다. 조회라 다시 불러도 안전하고, notes 로 넘기면 v3 `tag`
        # 쿼리가 깨져도 exit 0 이라 매일 API 감시가 고장을 못 본다. "부가 정보 실패로 결과를 버린다" 는 지적은 오탐이다
        info = get_tag_info(client, name) if cursor is None else None
        if info is not None:
            payload = {'tag': info.model_dump(), **payload}
        emit(payload, pretty)


@contextmanager
def _session_client(*, login_required: bool = False) -> Iterator[VelogClient]:
    """저장된 세션 쿠키를 실은 클라이언트. 명령이 끝나면 성공·실패와 상관없이 갱신된 쿠키를 저장한다 (`_persist`).

    로그인돼 있으면 조회에도 세션 쿠키를 실어 본인 비공개 글 등도 보이게 한다 (조회는 로그인 없이도 된다).
    `login_required` 면 세션이 없을 때 네트워크 없이 바로 NOT_LOGGED_IN 으로 막는다.

    저장을 명령마다 부르지 않고 여기서 하는 것은, 결과를 낸 뒤 stdout 이 닫혔거나(`| head` 의 BrokenPipeError)
    `require_auth` 가 토큰을 갱신한 뒤 서비스가 에러를 낸 경우에도 받은 토큰을 남기려는 것이다. 결과를 낸 뒤에 저장하는
    순서는 그대로다 (`_persist`).

    세션 파일이 있는데 읽지 못하면(권한·샌드박스) 익명 조회로 넘어가지 않고 `load_session` 의 에러를 그대로 내는 것은
    일부러다. 말없이 익명으로 넘어가면 본인 비공개 글이 `NOT_FOUND`, `posts <내 아이디>` 가 공개 글만 돌려줘 에이전트가
    '없는 글' 로 결론 낸다. 에러 힌트대로 `VELOGGER_CONFIG_DIR` 를 고치면 된다 (2026-10-20 재현·검토).
    """
    session = load_session()
    if login_required and not session.cookies:
        raise not_logged_in_error()
    with VelogClient(cookies=session.cookies or None) as client:
        try:
            yield client
        finally:
            _persist(client, session)


def _cookie_set(cookies: list[StoredCookie] | None) -> set[tuple[str, str, str, str]]:
    return {(cookie.name, cookie.value, cookie.domain, cookie.path) for cookie in cookies or []}


def _persist(client: VelogClient, loaded: Session) -> None:
    """요청 뒤 갱신된 세션 쿠키(토큰 회전)를 다시 저장한다. 실패해도 명령 결과는 그대로 둔다 (로그만 남긴다).

    쓰기만이 아니라 조회 뒤에도 부른다. velog 는 access_token 수명이 30분 아래로 남은 요청이면 조회든 쓰기든 새 토큰을
    Set-Cookie 로 주고, refresh_token 도 23일 아래로 남으면 새로 준다 (velog-server `consumeUser`·`refreshUserToken`.
    2026-10-21 실측: access_token 을 뺀 세션으로 보낸 조회에도 두 쿠키가 왔다). 받은 토큰을 버리면 whoami·조회만 쓰는
    사용자는 로그인 30일 뒤 refresh_token 이 만료돼 NOT_LOGGED_IN 이 된다. 세션 없이 보낸 조회는 저장하지 않는다 (익명
    요청에 붙은 쿠키로 세션 파일을 만들지 않게).

    결과를 낸 뒤에 부른다 (`_session_client` 를 나갈 때). 서버는 이미 요청을 처리했으므로, 저장 실패로 결과를 버리면
    에이전트가 실패로 보고 같은 쓰기를 다시 보내 글·댓글이 두 번 생긴다 (2026-10-20 재현: 쓰기가 막힌 설정 폴더에서
    drafts 가 stdout 없이 INTERNAL_ERROR). 갱신된 토큰을 못 남겨도 다음 실행이 refresh_token 으로 다시 갱신한다.

    쿠키가 처음 실은 그대로면 쓰지 않는다. 늘 다시 쓰면, 동시에 돈 다른 velogger 가 갱신해 저장한 토큰을 이 프로세스가
    가진 옛 토큰으로 덮는다 (2026-10-20 확인: 쿠키가 같아도 매번 session.json 을 새 파일로 바꿔 썼다).

    velog 가 쿠키를 모두 지웠을 때도 쓰지 않는다. v3 는 토큰이 잘못됐다고 보면 빈 Set-Cookie 로 쿠키를 지운다 (2026-10-21
    실측: 가짜 토큰 세션으로 recent 를 부르니 쿠키가 모두 지워졌고, v2 는 지우지 않았다). 그대로 쓰면 일시적인 판정에도
    세션 파일이 비어 다시 로그인해야 한다. 세션은 `logout` 으로만 지운다.

    세션 파일이 이 명령이 읽은 때와 달라졌으면 쓰지 않는다. 그 사이 사용자가 `logout` 했거나 다른 계정으로 `login` 했거나,
    먼저 끝난 다른 velogger 가 갱신한 토큰을 저장한 것이다. 덮으면 로그아웃이 풀리거나 다른 계정 세션이 옛 계정으로 바뀐다
    (2026-10-23 재현: access_token 을 뺀 세션 사본으로 whoami 를 부르는 도중 logout 하니, 명령이 끝날 때 velog 가 준 새 토큰으로
    session.json 이 되살아났다). 다른 velogger 가 저장한 토큰도 유효하다 (옛 refresh_token 도 계속 쓰인다). 읽고 쓰는 사이는
    잠그지 않아 그 틈에 바뀌면 못 막지만, 그 틈은 파일 하나를 읽고 쓰는 동안뿐이다.
    """
    if not client.cookies:
        return
    cookies = client.current_cookies()
    if not cookies or _cookie_set(cookies) == _cookie_set(client.cookies):
        return
    try:
        if load_session() != loaded:
            logger.info('명령이 도는 사이 세션 파일이 바뀌어 갱신된 쿠키를 저장하지 않습니다 (logout·login 등)')
            return
        save_session(Session(cookies=cookies, username=loaded.username))
    except SessionError as exc:
        logger.warning('갱신된 세션을 저장하지 못했습니다 (결과에는 영향 없음): %s', exc.message)


def _split_tags(values: list[str] | None) -> list[str]:
    """`--tag a,b --tag c` 를 하나의 태그 목록으로. 태그는 자유 문자열이라 검증하지 않는다."""
    tags: list[str] = []
    for value in values or []:
        for part in value.split(','):
            part = part.strip()
            if part and part not in tags:
                tags.append(part)
    return tags


def _resolve_body(body: str | None, file: str | None) -> str:
    """본문을 --body, --file <경로>, 또는 --file - (stdin)에서 읽는다.

    stdin 은 `--file -` 로 명시했을 때만 읽는다. 터미널이 아니라는 이유로 읽으면, 닫히지 않는 파이프를 물려준
    하네스에서 EOF 까지 멈추거나 부모의 stdin 스트림(MCP JSON-RPC 등)을 본문으로 먹는다 (2026-10-20 재현: 열린
    파이프에서 닫힐 때까지 대기).
    """
    if body is not None and file is not None:
        raise HintedUsageError('--body 와 --file 은 함께 쓸 수 없습니다', '본문은 한 곳에서만 주세요')
    if file == STDIN_FILE:
        # 파이썬은 locale·UTF-8 모드에 따라 stdin 을 surrogateescape 로 읽어, UTF-8 이 아닌 본문이 에러 없이 깨진 채 velog 로
        # 갔다 (2026-10-20 재현: README 의 Windows 설정 PYTHONUTF8=1 도 그렇다). 파일처럼 엄격한 UTF-8 로 읽는다.
        if isinstance(sys.stdin, io.TextIOWrapper):
            sys.stdin.reconfigure(encoding=BODY_ENCODING, errors='strict')
        try:
            text = sys.stdin.read()
        except UnicodeDecodeError as exc:
            raise HintedUsageError('stdin 으로 받은 본문이 UTF-8 이 아닙니다', '본문을 UTF-8 로 넘기세요') from exc
        if not text.strip():
            raise HintedUsageError('stdin 으로 받은 본문이 비어 있습니다', '파이프로 본문을 넘기세요 (예: cat post.md | velogger publish "제목" --file -)')
        return text
    if file is not None:
        try:
            return _local_path(file).read_text(encoding=BODY_ENCODING)
        except OSError as exc:
            raise HintedUsageError(f'본문 파일을 읽을 수 없습니다: {file} ({type(exc).__name__})', '경로가 맞는지 확인하세요') from exc
        except UnicodeDecodeError as exc:
            # ValueError 라 그대로 두면 handle_errors 가 'velog 응답이 이상하다' 는 PARSE_ERROR 로 낸다 (2026-10-20 재현)
            raise HintedUsageError(f'본문 파일이 UTF-8 이 아닙니다: {file}', '파일을 UTF-8 로 저장해 다시 주세요') from exc
    if body is not None:
        return body
    raise HintedUsageError('본문이 필요합니다', '--body "..." 나 --file <경로> 로 주세요. 파이프로 넘기려면 --file - 를 씁니다')


def _local_path(value: str) -> Path:
    """사용자가 준 파일 경로. 그대로 없으면 NFD 로도 찾는다.

    `run()` 이 인자를 NFC 로 바꾸므로, 파일 이름이 NFD 로 저장된 경우(macOS 에서 만든 한글 이름 파일을 Linux 로
    옮김)에는 그 이름으로 열리지 않는다. macOS(APFS)는 두 형태를 같은 파일로 찾아 이 Mac 에서는 재현되지 않고, ext4 처럼
    이름을 바이트로 비교하는 파일 시스템에서만 생긴다.
    """
    path = Path(value)
    if not path.exists():
        decomposed = Path(unicodedata.normalize('NFD', value))
        if decomposed.exists():
            return decomposed
    return path


TagOption = Annotated[list[str] | None, typer.Option('--tag', help='태그 (반복하거나 쉼표로 구분)')]
BodyOption = Annotated[str | None, typer.Option('--body', help='본문 (마크다운). --file 로도 줄 수 있다')]
FileOption = Annotated[str | None, typer.Option('--file', help="본문을 읽을 파일 경로. '-' 면 stdin(파이프)에서 읽는다")]


@app.command('publish')
def publish_command(
    title: Annotated[str, typer.Argument(help='글 제목')],
    body: BodyOption = None,
    file: FileOption = None,
    tag: TagOption = None,
    series_id: Annotated[str | None, typer.Option('--series-id', help='넣을 시리즈 ID (velogger user 결과의 series)')] = None,
    slug: Annotated[str | None, typer.Option('--slug', help='url_slug (기본은 제목에서 생성)')] = None,
    thumbnail: Annotated[str | None, typer.Option('--thumbnail', help='썸네일 이미지 URL')] = None,
    private: Annotated[bool, typer.Option('--private', help='비공개로 저장')] = False,
    publish_flag: Annotated[bool, typer.Option('--publish', help='실제로 발행 (기본은 임시저장/초안)')] = False,
    markdown: Annotated[bool, typer.Option('--markdown/--no-markdown', help='본문이 마크다운인지')] = True,
    pretty: PrettyOption = None,
) -> None:
    """글을 쓴다. **기본은 임시저장(초안)**이고 --publish 를 줘야 실제로 발행된다.

    본문은 --body "..." / --file <경로> / --file - (stdin 파이프) 중 하나로 준다. 발행은 신뢰 계정(whoami 의
    is_trusted)만 되며, 아니면 FORBIDDEN 으로 막고 웹 발행을 안내한다 (캡차를 풀지 않는다).

    예: velogger publish "제목" --file post.md --tag python,velog --publish
    """
    with handle_errors():
        text = _resolve_body(body, file)
        with _session_client(login_required=True) as client:
            result = publish(
                client, title=title, body=text, tags=_split_tags(tag), publish_now=publish_flag,
                is_private=private, is_markdown=markdown, url_slug=slug, thumbnail=thumbnail, series_id=series_id,
            )
            emit(result, pretty)


@app.command('edit')
def edit_command(
    post_id: Annotated[str, typer.Argument(help='고칠 글 ID (velogger posts·drafts 결과의 id)')],
    title: Annotated[str | None, typer.Option('--title', help='새 제목')] = None,
    body: BodyOption = None,
    file: FileOption = None,
    tag: TagOption = None,
    slug: Annotated[str | None, typer.Option('--slug', help='새 url_slug')] = None,
    private: Annotated[bool | None, typer.Option('--private/--public', help='비공개/공개로 바꾸기')] = None,
    publish_flag: Annotated[bool, typer.Option('--publish', help='초안을 발행 상태로 바꾸기 (신뢰 계정만)')] = False,
    thumbnail: Annotated[str | None, typer.Option('--thumbnail', help='썸네일 이미지 URL (velogger upload 결과의 url)')] = None,
    pretty: PrettyOption = None,
) -> None:
    """내 글을 고친다. 바꾸지 않은 필드는 현재 값을 그대로 둔다 (본문을 안 주면 본문은 유지된다).

    예: velogger edit <id> --title "새 제목" --publish
    """
    with handle_errors():
        new_body = _resolve_body(body, file) if (body is not None or file is not None) else None
        with _session_client(login_required=True) as client:
            result = edit_post(
                client, post_id, title=title, body=new_body,
                tags=_split_tags(tag) if tag else None, is_private=private, publish_now=publish_flag, url_slug=slug,
                thumbnail=thumbnail,
            )
            emit(result, pretty)


@app.command('drafts')
def drafts_command(limit: LimitOption = 20, pretty: PrettyOption = None) -> None:
    """내 임시저장(초안) 글 목록. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = get_drafts(client, limit=limit)
        emit(result, pretty)


@app.command('like')
def like_command(post_id: Annotated[str, typer.Argument(help='글 ID (목록·post 결과의 id)')], pretty: PrettyOption = None) -> None:
    """글에 좋아요. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = like_post(client, post_id)
        emit(result, pretty)


@app.command('unlike')
def unlike_command(post_id: Annotated[str, typer.Argument(help='글 ID')], pretty: PrettyOption = None) -> None:
    """글 좋아요를 취소한다. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = unlike_post(client, post_id)
        emit(result, pretty)


@app.command('comment')
def comment_command(
    post_id: Annotated[str, typer.Argument(help='댓글을 달 글 ID')],
    text: Annotated[str, typer.Argument(help='댓글 내용')],
    reply_to: Annotated[str | None, typer.Option('--reply-to', help='대댓글이면 부모 댓글 ID')] = None,
    pretty: PrettyOption = None,
) -> None:
    """글에 댓글(또는 --reply-to 로 대댓글)을 단다. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = write_comment(client, post_id, text, comment_id=reply_to)
        emit(result, pretty)


@app.command('stats')
def stats_command(post_id: Annotated[str, typer.Argument(help='내 글 ID')], pretty: PrettyOption = None) -> None:
    """내 글의 조회수 통계(전체 + 일별). 본인 글만, 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = get_stats(client, post_id)
        emit(result, pretty)


@app.command('comments')
def comments_command(
    post_id: Annotated[str, typer.Argument(help='글 ID (목록·post 결과의 id)')],
    replies: Annotated[bool, typer.Option('--replies', help='대댓글까지 받기 (댓글마다 요청이 한 번씩 더 간다)')] = False,
    pretty: PrettyOption = None,
) -> None:
    """글의 댓글을 읽는다 (작성자·대댓글 수 포함). 로그인 없이도 된다.

    댓글 내용은 post 가 주지 않으므로 이 명령으로 받는다.
    """
    with handle_errors(), _session_client() as client:
        emit(get_comments(client, post_id, with_replies=replies), pretty)


@app.command('series')
def series_command(
    username: Annotated[str, typer.Argument(help='시리즈 주인 아이디 (@ 없이)')],
    url_slug: Annotated[str, typer.Argument(help='시리즈 slug (user 결과 series url 의 끝부분)')],
    pretty: PrettyOption = None,
) -> None:
    """시리즈 안의 글을 순서대로 보여 준다."""
    with handle_errors(), _session_client() as client:
        series = get_series(client, username, url_slug)
        emit(series, pretty, series.notes or None)


@app.command('followers')
def followers_command(
    username: Annotated[str, typer.Argument(help='사용자 아이디 (@ 없이)')],
    limit: LimitOption = 20,
    cursor: CursorOption = None,
    pretty: PrettyOption = None,
) -> None:
    """그 사용자를 팔로우하는 사람 목록. 다음 페이지는 next_cursor 를 --cursor 로."""
    with handle_errors(), _session_client() as client:
        emit(get_followers(client, username, limit=limit, cursor=cursor), pretty)


@app.command('followings')
def followings_command(
    username: Annotated[str, typer.Argument(help='사용자 아이디 (@ 없이)')],
    limit: LimitOption = 20,
    cursor: CursorOption = None,
    pretty: PrettyOption = None,
) -> None:
    """그 사용자가 팔로우하는 사람 목록. 다음 페이지는 next_cursor 를 --cursor 로."""
    with handle_errors(), _session_client() as client:
        emit(get_followings(client, username, limit=limit, cursor=cursor), pretty)


@app.command('feed')
def feed_command(limit: LimitOption = 20, pretty: PrettyOption = None) -> None:
    """내가 팔로우한 사람들의 최신 글. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = get_feed(client, limit=limit)
        emit(result, pretty)


@app.command('liked')
def liked_command(
    read: Annotated[bool, typer.Option('--read', help='좋아요한 글 대신 읽은 글 목록')] = False,
    limit: LimitOption = 20,
    cursor: CursorOption = None,
    pretty: PrettyOption = None,
) -> None:
    """내가 좋아요한 글 목록 (--read 면 읽은 글). 로그인이 필요하다. 다음 페이지는 next_cursor 를 --cursor 로."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = get_reading_list(client, list_type='READ' if read else 'LIKED', limit=limit, cursor=cursor)
        emit(result, pretty)


@app.command('comment-edit')
def comment_edit_command(
    comment_id: Annotated[str, typer.Argument(help='고칠 댓글 ID (comments 결과의 id)')],
    text: Annotated[str, typer.Argument(help='새 내용')],
    pretty: PrettyOption = None,
) -> None:
    """내 댓글 내용을 고친다. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = edit_comment(client, comment_id, text)
        emit(result, pretty)


@app.command('comment-remove')
def comment_remove_command(
    comment_id: Annotated[str, typer.Argument(help='지울 댓글 ID')],
    yes: Annotated[bool, typer.Option('--yes', help='정말 지운다는 확인 (없으면 거부한다)')] = False,
    pretty: PrettyOption = None,
) -> None:
    """내 댓글을 지운다. 되돌릴 수 없어 --yes 가 있어야 실행한다.

    예: velogger comment-remove <댓글 id> --yes
    """
    if not yes:
        raise HintedUsageError(
            '댓글 삭제는 되돌릴 수 없습니다',
            '정말 지우려면 --yes 를 붙이세요. 에이전트는 사용자 확인 없이 붙이지 않습니다',
        )
    with handle_errors(), _session_client(login_required=True) as client:
        result = remove_comment(client, comment_id)
        emit(result, pretty)


@app.command('follow')
def follow_command(
    username: Annotated[str, typer.Argument(help='팔로우할 사용자 아이디 (@ 없이)')],
    pretty: PrettyOption = None,
) -> None:
    """사용자를 팔로우한다. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = follow_user(client, username)
        emit(result, pretty)


@app.command('unfollow')
def unfollow_command(
    username: Annotated[str, typer.Argument(help='팔로우를 끊을 사용자 아이디 (@ 없이)')],
    pretty: PrettyOption = None,
) -> None:
    """사용자 팔로우를 끊는다. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = unfollow_user(client, username)
        emit(result, pretty)


@app.command('series-create')
def series_create_command(
    name: Annotated[str, typer.Argument(help='새 시리즈 이름')],
    slug: Annotated[str | None, typer.Option('--slug', help='시리즈 slug (기본은 이름에서 생성)')] = None,
    pretty: PrettyOption = None,
) -> None:
    """시리즈를 만든다. 돌려받은 id 를 publish --series-id 나 series-add 에 쓴다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = create_series(client, name, url_slug=slug)
        emit(result, pretty)


@app.command('series-add')
def series_add_command(
    series_id: Annotated[str, typer.Argument(help='시리즈 ID (series·series-create 결과의 id)')],
    post_id: Annotated[str, typer.Argument(help='넣을 글 ID')],
    pretty: PrettyOption = None,
) -> None:
    """시리즈 맨 뒤에 글을 넣는다. 로그인이 필요하다."""
    with handle_errors(), _session_client(login_required=True) as client:
        result = add_to_series(client, series_id, post_id)
        emit(result, pretty)


@app.command('upload')
def upload_command(
    file: Annotated[str, typer.Argument(help='올릴 이미지 파일 경로')],
    post: Annotated[str, typer.Option('--post', help='이미지가 들어갈 글 ID (초안이어도 된다). velog 는 글 없이 이미지만 올리는 걸 막는다')],
    pretty: PrettyOption = None,
) -> None:
    """이미지를 velog 에 올리고 본문에 쓸 URL 을 돌려준다. 로그인이 필요하다.

    velog 는 어느 글에 들어갈 이미지인지 알아야 올려 준다. 그래서 글을 먼저 초안으로 만들고 그 id 로 올린 뒤,
    결과의 markdown 을 본문에 넣어 edit 한다.

    예: velogger publish "제목" --body "임시" → (id) → velogger upload a.png --post <id> → velogger edit <id> --file post.md
    """
    with handle_errors(), _session_client(login_required=True) as client:
        result = upload_image(client, _local_path(file), post_id=post)
        emit(result, pretty)


@app.command('guide')
def guide_command(
    topic: Annotated[
        str | None,
        typer.Argument(help=f"사용 문서: {', '.join(GUIDE_TOPICS)}. 없으면 LLM 가이드")
    ] = None,
    section: Annotated[
        str | None,
        typer.Argument(help="절 제목에 든 글자 (예: 'login'). 주면 그 절만 쓴다")
    ] = None,
) -> None:
    """LLM 에이전트용 사용 가이드를 출력한다 (명령 고르기, 출력 읽기, 에러 대응).

    토픽 이름을 주면 그 문서를, 절 이름까지 주면 그 절만 쓴다. `--help` 처럼 JSON 이 아닌 마크다운
    텍스트를 stdout 에 쓴다. 네트워크 요청은 보내지 않는다.

    예: velogger guide
        velogger guide velogger login
    """
    if topic is not None and topic not in GUIDE_TOPICS:
        raise typer.BadParameter(
            f"허용되지 않는 값입니다: '{topic}'. 가능한 값: {', '.join(GUIDE_TOPICS)}", param_hint='TOPIC',
        )
    with handle_errors():
        text = read_guide(GUIDE_TOPICS[topic] if topic else GUIDE_FILE)
        if section:
            text = guide_section(text, section, topic or 'llm')
        typer.echo(text, nl=False)


def read_guide(name: str = GUIDE_FILE) -> str:
    """패키지에 들어 있는 문서를, 없으면(편집 가능 설치) 저장소의 `docs/<name>` 을 읽는다.

    Raises:
        VeloggerError: 둘 다 없을 때 (`INTERNAL_ERROR`, 설치가 깨짐).
    """
    packaged = files('velogger').joinpath(name)
    if packaged.is_file():
        return packaged.read_text(encoding='utf-8')
    # src/velogger/cli/app.py → 저장소 루트
    in_repo = Path(__file__).resolve().parents[3] / 'docs' / name
    if in_repo.is_file():
        return in_repo.read_text(encoding='utf-8')
    raise VeloggerError(
        code='INTERNAL_ERROR',
        message=f'설치된 velogger 에 문서 파일({name})이 없습니다',
        hint=f'velogger 를 다시 설치하세요. 같은 내용은 {GUIDE_URL} 에서도 볼 수 있습니다',
    )


def guide_section(text: str, query: str, topic: str) -> str:
    """문서에서 제목에 `query` 가 든 절(그 아래 하위 절 포함)만 이어 붙인다. 대소문자·백틱은 가리지 않는다.

    Raises:
        VeloggerError: 맞는 절이 없을 때 (`NOT_FOUND`, 힌트에 큰 절 제목).
    """
    def plain(value: str) -> str:
        return value.replace('`', '').casefold().strip()

    lines = text.splitlines(keepends=True)
    headings = [
        (index, len(match.group(1)), match.group(2).strip())
        for index, line in enumerate(lines)
        if (match := HEADING_PATTERN.match(line.rstrip('\n')))
    ]
    exact = {index for index, _, title in headings if plain(query) in (plain(code) for code in BACKTICK_PATTERN.findall(title))}
    picked: list[str] = []
    covered_until = -1
    for position, (index, level, title) in enumerate(headings):
        matched = index in exact if exact else plain(query) in plain(title)
        if index < covered_until or not matched:
            continue
        end = next((later for later, later_level, _ in headings[position + 1:] if later_level <= level), len(lines))
        picked.append(''.join(lines[index:end]).rstrip('\n') + '\n')
        covered_until = end
    if not picked:
        titles = [title.replace('`', '') for _, level, title in headings if level == 2]
        raise VeloggerError(
            code='NOT_FOUND',
            message=f"{topic} 문서에서 찾지 못한 절 제목: '{query}'",
            hint=f"절 제목: {' / '.join(titles)}",
        )
    return '\n'.join(picked)


def version_text() -> str:
    """`velogger --version` 이 쓰는 한 줄 (`velogger 0.1.0 (커밋 a1b2c3d)`)."""
    dist = distribution('velogger')
    text = f'velogger {dist.version}'
    origin = json.loads(dist.read_text('direct_url.json') or '{}')
    commit = origin.get('vcs_info', {}).get('commit_id')
    if commit:
        return f'{text} (커밋 {commit[:SHORT_COMMIT_LENGTH]})'
    if origin.get('dir_info', {}).get('editable'):
        return f'{text} (개발 설치)'
    return text


class PlainHelpFormatter(HelpFormatter):
    """터미널이 아닐 때 쓰는 Click 도움말 형식. 폭을 넓게 잡고 설명은 docstring 의 줄바꿈대로 쓴다."""

    def __init__(self, indent_increment: int = 2, width: int | None = None, max_width: int | None = None) -> None:
        super().__init__(indent_increment, width=PLAIN_HELP_WIDTH, max_width=PLAIN_HELP_WIDTH)

    def write_text(self, text: str) -> None:
        indent = ' ' * self.current_indent
        for line in text.splitlines():
            self.write(f'{indent}{line}\n' if line.strip() else '\n')


class PlainHelpContext(Context):
    formatter_class = PlainHelpFormatter


def use_plain_help(command: Command) -> None:
    """도움말을 Rich 표 대신 Click 줄글로 쓰게 명령 트리 전체를 바꾼다. stdout 이 터미널이 아닐 때 쓴다."""
    if isinstance(command, TyperCommand | TyperGroup):
        command.rich_markup_mode = None
    command.context_class = PlainHelpContext
    if isinstance(command, TyperGroup):
        for subcommand in command.commands.values():
            use_plain_help(subcommand)


def _usage_error_hint(exc: UsageError, command: str) -> str:
    """사용법 오류의 기본 힌트. `-` 하나로 시작하는 모르는 옵션이면 `-` 로 시작하는 값일 수 있다고 알린다.

    velog 는 제목 '- 회고' 의 slug 를 '-회고' 로 만든다 (velog-server escapeForUrl 은 앞의 '-' 를 지우지 않는다). 그런 값을
    인자로 넘기면 Click 이 옵션으로 읽어 'No such option: -회' 가 난다. `--` 뒤의 인자는 옵션으로 읽지 않는다.
    """
    if isinstance(exc, NoSuchOption) and not exc.option_name.startswith('--'):
        return (
            "'-' 로 시작하는 값(url_slug 등)이면 그 앞에 -- 를 두세요 (예: velogger post <username> -- <url_slug>). "
            f"옵션이면 '{command} --help' 로 확인하세요"
        )
    return f"'{command} --help' 로 사용법을 확인하세요"


def _compose_argument(value: str) -> str:
    """인자를 NFC 로 맞추되, 혼자서도 NFC 가 다른 글자로 바꾸는 글자는 그대로 둔다.

    그런 글자는 CJK 호환 한자(樂 U+F914 → U+6A02)·옴 기호(Ω U+2126 → U+03A9)처럼 사용자가 고른 글자다. 인자에는 제목·
    본문·댓글도 있어 바꾸면 velog 에 쓴 것과 다른 글이 저장된다. NFD 로 나뉜 글자에는 이런 글자가 없어(NFD 결과의 글자는
    모두 혼자서 NFC 그대로다) 자모 합치기에는 영향이 없다.
    """
    if unicodedata.is_normalized('NFC', value):
        return value
    pieces: list[str] = []
    start = 0
    for index, char in enumerate(value):
        if unicodedata.normalize('NFC', char) != char:
            pieces.append(unicodedata.normalize('NFC', value[start:index]))
            pieces.append(char)
            start = index + 1
    pieces.append(unicodedata.normalize('NFC', value[start:]))
    return ''.join(pieces)


def run(argv: Sequence[str] | None = None) -> int:
    """CLI 를 실행하고 exit code 를 돌려준다.

    Typer 를 standalone 모드 없이 돌려 사용법 오류도 `{"error": {...}}` JSON 으로 stderr 에 쓴다 (exit 2).
    stdout 이 터미널이 아니면 도움말을 Rich 표 대신 줄글로 쓴다.
    """
    # macOS 에서 복사한 한글은 자모가 나뉜 NFD 로 올 수 있어 NFC 로 맞춘다 (`_compose_argument`). 파일 경로는 `_local_path`
    # 가 NFD 로도 찾는다. url_slug 같은 식별자까지 바꾸는 것은 괜찮다: velog 는 글 slug 에서 NFD 자모(U+1100–11FF)를 지워
    # 저장해 NFD slug 인 글이 없다 (2026-10-21 실측: 비공개 테스트 글의 slug 를 NFD 'nfd-확인용' 으로 고치니 'nfd-' 로
    # 저장됐다. velog-server escapeForUrl 도 'ㄱ-힣' 만 남긴다). 'NFD slug 글을 못 찾는다' 는 지적은 오탐이다.
    args = [_compose_argument(arg) for arg in (sys.argv[1:] if argv is None else argv)]
    cli = typer.main.get_command(app)
    if not sys.stdout.isatty():
        use_plain_help(cli)
    try:
        result = cli.main(args=args, prog_name='velogger', standalone_mode=False)
    except NoArgsIsHelpError as exc:
        typer.echo(exc.format_message())
        return 0
    except UsageError as exc:
        command = exc.ctx.command_path if exc.ctx is not None else 'velogger'
        emit_error(
            'INVALID_ARGUMENT',
            exc.format_message(),
            getattr(exc, 'hint', None) or _usage_error_hint(exc, command),
            command=command,
        )
        return exc.exit_code
    except ClickException as exc:
        emit_error('CLI_ERROR', exc.format_message())
        return exc.exit_code
    except typer.Abort:
        emit_error('INTERRUPTED', '중단되었습니다', INTERRUPTED_HINT)
        return 1
    if result == INTERRUPTED_EXIT_CODE:
        emit_error('INTERRUPTED', '인터럽트(Ctrl+C, SIGINT)로 중단되었습니다', INTERRUPTED_HINT)
        return result
    return result if isinstance(result, int) else 0


def main() -> None:
    sys.exit(run())
