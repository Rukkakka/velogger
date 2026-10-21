import pytest


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """요청 제한 상태와 로그인 세션을 테스트마다 임시 디렉터리로 돌린다.

    실제 `~/.cache/velogger`·`~/.config/velogger` (진짜 로그인 세션!)를 건드리지 않게 한다.
    """
    monkeypatch.setenv('VELOGGER_STATE_DIR', str(tmp_path / 'state'))
    monkeypatch.setenv('VELOGGER_CONFIG_DIR', str(tmp_path / 'config'))
