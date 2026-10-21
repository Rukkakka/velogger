"""매일 API 감시가 명령을 빠뜨리지 않는지."""

import importlib.util
import sys
from pathlib import Path

import pytest
import typer

from velogger.cli.app import app


def _load_monitor(monkeypatch: pytest.MonkeyPatch):
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'monitor' / 'api_check.py'
    spec = importlib.util.spec_from_file_location('api_check', path)
    assert spec is not None and spec.loader is not None
    monitor = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, 'api_check', monitor)  # dataclass 가 자기 모듈을 찾는다
    spec.loader.exec_module(monitor)
    return monitor


def test_every_command_is_monitored_or_excluded_with_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """비공식 API 는 velog 가 바꾸면 조용히 깨진다. 새 명령이 감시에서 말없이 빠지지 않게 한다.

    명령마다 감시 목록(`STEPS`)에 넣거나, 감시하지 않는 이유를 `NOT_MONITORED` 에 적어야 한다.
    """
    monitor = _load_monitor(monkeypatch)
    commands = set(typer.main.get_command(app).commands)  # type: ignore[attr-defined]
    monitored = {step.command[0] for step in monitor.STEPS}
    excluded = set(monitor.NOT_MONITORED)

    unclassified = commands - monitored - excluded
    assert unclassified == set(), f'감시 목록(STEPS)에도 NOT_MONITORED 에도 없는 명령: {sorted(unclassified)}'
    # 없는 명령 이름(오타)이 감시·제외 목록에 남아 있지 않게
    assert (monitored | excluded) - commands == set()
    # 감시하면서 동시에 제외하는 모순이 없게
    assert monitored & excluded == set()


def test_captures_of_one_step_come_from_the_same_item(monkeypatch: pytest.MonkeyPatch) -> None:
    """`post` 는 한 글의 username·url_slug 로 불러야 한다. 첫 글에 칸이 빠졌으면 글마다 섞지 않고 다음 글에서 모두 꺼낸다.

    섞으면 없는 글을 불러 NOT_FOUND 가 나 '고장' 이슈가 거짓으로 열린다. 칸이 빠진 트렌딩 글은 실제 API 로 재현할 수
    없어 가짜 결과로 본다 (2026-10-20 실측: 트렌딩 세 글 모두 칸이 있었다).
    """
    monitor = _load_monitor(monkeypatch)
    trending = next(step for step in monitor.STEPS if step.command == ('trending',))
    data = {'posts': [
        {'id': 'p0', 'username': 'alice', 'url_slug': None},
        {'id': 'p1', 'username': 'bob', 'url_slug': 'bob-post'},
    ]}

    assert monitor._captures(data, trending.captures) == {'username': 'bob', 'url_slug': 'bob-post', 'post_id': 'p1'}
