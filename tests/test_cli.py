"""CLI 출력 계약과 자격증명 취급. 바뀌면 에이전트가 깨지는 것들만 지킨다."""

import io
import json
import logging
import stat
import sys

import httpx
import pytest

from velogger.api.client import VelogClient
from velogger.cli.app import run
from velogger.cli.output import (
    emit,
    handle_errors,
)
from velogger.core.http import (
    describe_failed_attempt,
    raise_for_status,
)
from velogger.core.session import (
    Session,
    StoredCookie,
    load_session,
    save_session,
    session_path,
)


def _stderr_json(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().err)


# --- 출력 계약 ---

def test_usage_error_is_json_on_stderr_with_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    code = run(['publish'])  # 본문·제목 없이
    assert code == 2
    error = _stderr_json(capsys)['error']
    assert error['code'] == 'INVALID_ARGUMENT'
    assert error['hint']


def test_unknown_option_is_json_not_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    code = run(['trending', '--nope'])
    assert code == 2
    assert _stderr_json(capsys)['error']['code'] == 'INVALID_ARGUMENT'


def test_output_the_stdout_encoding_cannot_hold_is_escaped_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """stdout 이 cp949 같은 인코딩이면 담지 못하는 글자(이모지)를 `\\uXXXX` 로 쓴다.

    Windows 에서 PYTHONUTF8 없이 파이프로 받으면 결과를 쓰다 UnicodeEncodeError 가 나, 이미 반영된 쓰기가 'velog 응답이
    이상하다' 는 PARSE_ERROR 로 보고됐다. 이 Mac 에서는 stdout 인코딩을 바꿔야 재현돼 가짜 stdout 으로 본다.
    """
    buffer = io.BytesIO()
    stdout = io.TextIOWrapper(buffer, encoding='cp949')
    monkeypatch.setattr(sys, 'stdout', stdout)
    with handle_errors():
        emit({'text': '좋아요 👍'}, pretty=False)
    stdout.flush()

    assert json.loads(buffer.getvalue().decode('cp949')) == {'text': '좋아요 👍'}


def test_value_starting_with_dash_gets_a_hint_to_use_double_dash(capsys: pytest.CaptureFixture[str]) -> None:
    """velog 는 제목 '- 회고' 의 slug 를 '-회고' 로 만든다. 그대로 넘기면 옵션으로 읽히니 `--` 를 쓰라고 알린다."""
    code = run(['post', 'someone', '-회고'])
    assert code == 2
    assert '-- <url_slug>' in _stderr_json(capsys)['error']['hint']


def test_write_without_session_is_not_logged_in_without_network(capsys: pytest.CaptureFixture[str]) -> None:
    """세션이 없으면 네트워크를 쓰지 않고 바로 막는다 (에이전트가 사용자에게 로그인을 안내하도록)."""
    code = run(['like', 'some-post-id'])
    assert code == 1
    error = _stderr_json(capsys)['error']
    assert error['code'] == 'NOT_LOGGED_IN'
    assert 'velogger login' in error['hint']


# --- 자격증명 취급 ---

def test_session_file_is_user_only_and_token_never_printed(capsys: pytest.CaptureFixture[str]) -> None:
    """세션 파일은 0600 이고, 어떤 출력에도 토큰 값이 나오지 않는다."""
    secret = 'super-secret-token-value'
    save_session(Session(cookies=[StoredCookie(name='access_token', value=secret)], username='me'))

    # Windows 의 st_mode 는 읽기 전용 플래그만 반영해 쓸 수 있는 파일은 늘 0o666 으로 보인다 (POSIX 권한이 없다)
    if sys.platform != 'win32':
        mode = stat.S_IMODE(session_path().stat().st_mode)
        assert mode == 0o600, f'세션 파일 권한이 0600 이 아니다: {oct(mode)}'

    assert load_session().cookies[0].value == secret

    code = run(['logout'])
    assert code == 0
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
    assert json.loads(captured.out)['logged_out'] is True


def test_login_code_in_url_path_is_not_printed_in_errors() -> None:
    """로그인 code 는 URL 경로(`/api/v2/auth/code/{code}`)에 실린다. 에러 메시지·재시도 로그에 나오면 안 된다.

    5xx·429 로 끝난 code 는 아직 쓸 수 있는 자격증명이다 (2026-10-20 확인: 에러 JSON 에 code 가 그대로 찍혔다).
    """
    code = 'still-valid-login-code'
    request = httpx.Request('GET', f'https://v2.velog.io/api/v2/auth/code/{code}')
    with pytest.raises(httpx.HTTPStatusError) as caught:
        raise_for_status(httpx.Response(502, request=request, text='Bad Gateway'))

    assert code not in str(caught.value)
    assert code not in describe_failed_attempt(caught.value)


def test_login_code_in_url_path_is_not_printed_in_request_log(caplog: pytest.LogCaptureFixture) -> None:
    """`--verbose` 가 켜는 httpx 요청 로그에도 로그인 code 가 나오면 안 된다.

    2026-10-20 재현: `velogger --verbose login --code <링크>` 가 `GET .../auth/code/<code>` 를 그대로 찍었다 (502 면 재시도마다).
    """
    code = 'still-valid-login-code'
    client = VelogClient()
    client.__dict__['_client'] = httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(lambda request: httpx.Response(404, request=request)),
    )
    caplog.set_level(logging.INFO, logger='httpx')
    with pytest.raises(httpx.HTTPStatusError):
        client.run_request_code(code)

    assert '/auth/code/<redacted>' in caplog.text
    assert code not in caplog.text


def test_logout_removes_session(capsys: pytest.CaptureFixture[str]) -> None:
    save_session(Session(cookies=[StoredCookie(name='access_token', value='x')], username='me'))
    run(['logout'])
    capsys.readouterr()
    assert load_session().is_empty()


# --- 가이드 (네트워크 없음) ---

def test_guide_prints_markdown_not_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = run(['guide'])
    assert code == 0
    assert capsys.readouterr().out.startswith('# velogger LLM 사용 가이드')
