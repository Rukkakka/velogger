"""velogger 의 로그인 없는 조회 명령을 실제로 불러 비공식 API 가 깨졌는지 본다 (매일 새벽 `.github/workflows/api-monitor.yml`).

로그인·쓰기는 부작용이 있고 CI 에 세션도 없어 넣지 않는다 (`NOT_MONITORED`). 명령마다 셋으로 나눈다
(references/development.md '매일 API 감시').

- 정상: exit 0 이고 정한 칸(`Step.expect`)에 값이 있음
- 고장: 응답 형식 오류·서버 거절·내부 오류 같은 에러, 정한 칸이 비어 있음, JSON 이 아닌 출력. 결과가 0건일 리 없는
  곳(트렌딩·`python` 검색·`react` 태그·velopert)만 부르므로, 비어 있으면 velog 가 바뀐 것으로 본다
- 확인 못 함: 요청 제한·네트워크 오류·서버 5xx·시간 초과, 앞 명령이 넘길 값을 주지 않아 건너뛴 명령. velog 가 바뀐 것인지
  알 수 없다

    python scripts/monitor/api_check.py run --out result.json
    python scripts/monitor/api_check.py report result.json [--issues] [--dry-run]

새 CLI 명령을 만들면 STEPS 에 넣거나 NOT_MONITORED 에 이유를 적는다. tests/test_monitor.py 가 CLI 명령 목록과 대조한다.
jibsa(scripts/monitor/api_check.py)의 감시를 velogger 에 맞게 옮겼다 (소스가 하나라 러너를 나누지 않는다).
"""

import argparse
import datetime
import json
import os
import string
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from typing import Any


@dataclass(frozen=True)
class Capture:
    """결과에서 뒤 명령에 넘길 값 하나.

    Args:
        name: 뒤 명령 인자의 `{name}` 에 채울 이름. 이미 담긴 이름이면 덮어쓰지 않는다.
        field: 꺼낼 칸 (예: `id`).
        items: 목록 칸 (예: `posts`). 주면 그 목록에서 꺼내고, 비우면 결과 맨 위 칸에서 꺼낸다. 한 명령에서 같은 목록을
            쓰는 값은 모두 한 항목(그 값이 다 있는 첫 항목)에서 꺼낸다 (`_captures`).
        after: 주면 값에서 이 글자 뒤만 쓴다 (시리즈 주소 `.../series/<slug>` 에서 slug).
    """

    name: str
    field: str
    items: str = ''
    after: str = ''


@dataclass(frozen=True)
class Step:
    """감시할 명령 하나.

    Args:
        label: 결과 표에 쓰는 이름.
        command: CLI 명령 경로 (예: `('trending',)`).
        args: 인자. `{name}` 은 앞 명령의 `Capture` 값으로 채운다.
        expect: 값이 있어야 정상인 칸. 점으로 이어 안쪽 칸을 가리킨다.
        captures: 이 결과에서 뒤 명령에 넘길 값.
    """

    label: str
    command: tuple[str, ...]
    args: tuple[str, ...]
    expect: str
    captures: tuple[Capture, ...] = ()


# 명령 하나가 요청 제한 대기(최대 60초)를 몇 번 거쳐도 끝날 시간
COMMAND_TIMEOUT_SECONDS: int = 300
# 결과·표·이슈에 쓰는 날짜의 시간대. 러너는 UTC 라 한국 04:17 실행이 전날 날짜로 찍힌다 (jibsa 2026-10-18 확인)
KST: datetime.timezone = datetime.timezone(datetime.timedelta(hours=9), 'KST')
GROUP: str = 'velog'

# 로그인 없이 되는 조회만 넣는다. 상세 명령은 앞 결과의 값(글 username·url_slug·id, 시리즈 slug, 다음 페이지 커서)을
# 이어 받는다 (slug 를 박아 두면 글·시리즈 이름이 바뀔 때 거짓 고장이 난다). --limit 은 작게 준다 (결과가 있는지만 본다).
# 받은 slug 를 위치 인자로 넘기는 명령은 앞에 `--` 를 둔다. velog 는 제목 '- 회고' 의 slug 를 '-회고' 로 만들어(velog-server
# escapeForUrl), `--` 가 없으면 Click 이 옵션으로 읽어 INVALID_ARGUMENT 가 나고 거짓 고장 이슈가 열린다
STEPS: tuple[Step, ...] = (
    Step(
        '트렌딩', ('trending',), ('--limit', '3'), 'posts',
        (Capture('username', 'username', 'posts'), Capture('url_slug', 'url_slug', 'posts'), Capture('post_id', 'id', 'posts')),
    ),
    Step('최신 글', ('recent',), ('--limit', '3'), 'posts'),
    Step('검색 python', ('search',), ('python', '--limit', '3'), 'posts'),
    # 태그 글은 GraphQL 이 아니라 CDN 캐시 REST 다. 다음 페이지(--cursor)도 같은 캐시에 커서를 넘기는 경로라 함께 본다
    Step('태그 react', ('tag',), ('react', '--limit', '3'), 'posts', (Capture('tag_cursor', 'next_cursor'),)),
    Step('태그 react 다음 페이지', ('tag',), ('react', '--limit', '3', '--cursor', '{tag_cursor}'), 'posts'),
    Step('사용자 글 velopert', ('posts',), ('velopert', '--limit', '3'), 'posts'),
    Step('사용자 velopert', ('user',), ('velopert',), 'username', (Capture('series_slug', 'url', 'series', after='/series/'),)),
    Step('팔로워 velopert', ('followers',), ('velopert', '--limit', '3'), 'users'),
    Step('팔로잉 velopert', ('followings',), ('velopert', '--limit', '3'), 'users'),
    Step('글 본문', ('post',), ('--', '{username}', '{url_slug}'), 'body'),
    # 트렌딩 글에 댓글이 없을 수 있어 목록이 아니라 post_id 로 본다 (v2 경로가 응답하는지). --replies 로 대댓글 조회
    # (`ReloadReplies`, 대댓글의 대댓글까지 중첩)도 함께 본다. 대댓글이 있는 댓글이 없으면 그날은 그 요청을 보내지 않는다
    # (2026-10-21 확인: 트렌딩 10개 중 6개, 감시가 쓰는 첫 글에도 대댓글이 있었다)
    Step('댓글·대댓글', ('comments',), ('{post_id}', '--replies'), 'post_id'),
    Step('시리즈', ('series',), ('--', 'velopert', '{series_slug}'), 'posts'),
)

# 감시하지 않는 명령과 이유. 명령을 새로 만들면 STEPS 에 넣거나 여기에 이유와 함께 적는다
# (tests/test_monitor.py 가 둘 다 아니면 실패한다 — 감시에서 조용히 빠지는 명령이 없게).
NOT_MONITORED: dict[str, str] = {
    'guide': '네트워크를 쓰지 않는다',
    'limits': '네트워크를 쓰지 않는다',
    'login': '실제 로그인 메일을 보낸다',
    'logout': '로컬 세션만 지운다',
    'whoami': '로그인 세션이 있어야 의미가 있다 (CI 에는 세션이 없다)',
    'feed': '로그인 세션이 필요하다',
    'liked': '로그인 세션이 필요하다',
    'drafts': '로그인 세션이 필요하다',
    'stats': '로그인 세션이 필요하다',
    'publish': '실제 글이 올라간다',
    'edit': '실제 글을 고친다',
    'like': '실제 좋아요가 눌린다',
    'unlike': '실제 좋아요를 취소한다',
    'comment': '실제 댓글이 달린다',
    'comment-edit': '실제 댓글을 고친다',
    'comment-remove': '실제 댓글을 지운다',
    'follow': '실제 팔로우한다',
    'unfollow': '실제 팔로우를 끊는다',
    'series-create': '실제 시리즈가 생긴다',
    'series-add': '실제 시리즈에 글을 넣는다',
    'upload': '실제 이미지가 올라간다',
}

OK: str = 'ok'
BROKEN: str = 'broken'
UNKNOWN: str = 'unknown'
STATUS_LABELS: dict[str, str] = {OK: '✅ 정상', BROKEN: '❌ 고장', UNKNOWN: '⚠️ 확인 못 함'}
# velog 가 바뀐 것인지 알 수 없는 에러. 그 밖의 에러 코드(PARSE_ERROR, INTERNAL_ERROR, NOT_FOUND, NOT_LOGGED_IN 등)는 고장이다.
# NOT_LOGGED_IN 도 고장이다: 감시는 로그인 없이 되는 조회만 부르므로, 그 조회에 velog 가 로그인을 요구하게 바뀐 것이다
UNKNOWN_CODES: frozenset[str] = frozenset({'RATE_LIMITED', 'NETWORK_ERROR'})

BROKEN_LABEL: str = 'api-broken'
BLOCKED_LABEL: str = 'api-blocked'
# 이만큼 연속으로 확인 못 함이면 알린다 (오늘 포함)
BLOCKED_STREAK: int = 3
WORKFLOW_FILE: str = 'api-monitor.yml'
REPORT_ARTIFACT: str = 'report'


# --- 조회 ---

def _error(stderr: str) -> dict[str, Any] | None:
    """stderr 의 에러 JSON (`--verbose` 로그 뒤 마지막 `{` 줄)."""
    for line in reversed(stderr.splitlines()):
        if line.startswith('{'):
            try:
                body = json.loads(line).get('error')
            except ValueError:
                return None
            return body if isinstance(body, dict) else None
    return None


def _is_unknown(error: dict[str, Any]) -> bool:
    if error.get('code') in UNKNOWN_CODES:
        return True
    # 서버 5xx 는 velog 가 바뀐 것이 아니다. 상태 없는 UPSTREAM_ERROR 는 GraphQL 이 쿼리를 거절한(errors) 것이라 고장이다
    status = error.get('status')
    return error.get('code') == 'UPSTREAM_ERROR' and isinstance(status, int) and status >= 500


def _value(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split('.'):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _present(value: Any) -> bool:
    return value is not None and value != '' and value != [] and value != {}


def _capture_value(candidate: Any, capture: Capture) -> str | None:
    if not _present(candidate):
        return None
    value = str(candidate)
    if capture.after:
        if capture.after not in value:
            return None
        value = value.split(capture.after, 1)[1]
    return value or None


def _captures(data: dict[str, Any], captures: tuple[Capture, ...]) -> dict[str, str]:
    """결과에서 뒤 명령에 넘길 값들. 같은 목록(`items`)에서 꺼내는 값은 모두 한 항목에서 꺼낸다.

    값마다 '그 칸이 있는 첫 항목' 을 따로 고르면, 첫 글에 url_slug 가 없을 때 username 은 첫 글·url_slug 는 둘째 글에서
    와 `post` 가 없는 글을 불러 NOT_FOUND(고장)로 거짓 알림이 난다.
    """
    found: dict[str, str] = {}
    for capture in captures:
        if not capture.items:
            value = _capture_value(data.get(capture.field), capture)
            if value is not None:
                found[capture.name] = value
    for items_key in dict.fromkeys(capture.items for capture in captures if capture.items):
        group = [capture for capture in captures if capture.items == items_key]
        items = data.get(items_key)
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            values = {capture.name: _capture_value(item.get(capture.field), capture) for capture in group}
            if all(value is not None for value in values.values()):
                found.update({name: value for name, value in values.items() if value is not None})
                break
    return found


def _names(step: Step) -> list[str]:
    """인자에 채워야 하는 `{name}` 들."""
    return [name for arg in step.args for _, name, _, _ in string.Formatter().parse(arg) if name]


def _run_step(step: Step, values: dict[str, str]) -> tuple[str, str, dict[str, Any] | None]:
    """(판정, 내용, stdout JSON)."""
    command = [*step.command, *(arg.format(**values) for arg in step.args)]
    print(f"::group::velogger {' '.join(command)}", flush=True)
    try:
        done = subprocess.run(
            [sys.executable, '-m', 'velogger', '--verbose', *command],
            capture_output=True, text=True, encoding='utf-8', timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print('::endgroup::', flush=True)
        return UNKNOWN, f'{COMMAND_TIMEOUT_SECONDS}초 안에 끝나지 않음', None
    # 요청 로그만 남긴다. 결과 본문(글 제목·본문)은 공개 실행 기록에 남기지 않고, 정상이 아닐 때만 앞부분을 남긴다
    print(done.stderr.strip())
    status, detail, data = _judge(step, done)
    if status != OK:
        print(done.stdout.strip()[:1000])
    print('::endgroup::', flush=True)
    return status, detail, data


def _judge(step: Step, done: subprocess.CompletedProcess[str]) -> tuple[str, str, dict[str, Any] | None]:
    if done.returncode == 0:
        try:
            data = json.loads(done.stdout)
        except ValueError:
            return BROKEN, 'stdout 이 JSON 이 아님', None
        if not isinstance(data, dict):
            return BROKEN, 'stdout 이 JSON 객체가 아님', None
        value = _value(data, step.expect)
        if not _present(value):
            return BROKEN, f'{step.expect} 칸이 비어 있음', data
        return OK, f'{len(value)}건' if isinstance(value, list) else f'{step.expect} 있음', data
    error = _error(done.stderr)
    if error is None:
        return BROKEN, f'exit {done.returncode}, 에러 JSON 없음', None
    detail = ' '.join(str(part) for part in (error.get('code'), error.get('status')) if part)
    message = str(error.get('message') or '').replace('\n', ' ')
    return (UNKNOWN if _is_unknown(error) else BROKEN), f'{detail}: {message[:200]}', None


def _today() -> datetime.date:
    """한국 날짜 (`KST`)."""
    return datetime.datetime.now(KST).date()


def run_all() -> dict[str, Any]:
    """명령을 차례로 부른다. 앞 명령이 넘길 값을 주지 않은 명령은 건너뛴다 (확인 못 함)."""
    values: dict[str, str] = {}
    steps: list[dict[str, str]] = []
    for step in STEPS:
        line = ' '.join(step.command)
        missing = [name for name in _names(step) if name not in values]
        if missing:
            steps.append({
                'label': step.label, 'command': line, 'status': UNKNOWN,
                'detail': f"앞 명령 결과에 {', '.join(missing)} 값이 없어 건너뜀",
            })
            continue
        status, detail, data = _run_step(step, values)
        for name, value in (_captures(data, step.captures) if data else {}).items():
            values.setdefault(name, value)
        steps.append({'label': step.label, 'command': line, 'status': status, 'detail': detail})
    return {'group': GROUP, 'date': _today().isoformat(), 'status': _overall([step['status'] for step in steps]), 'steps': steps}


def _overall(statuses: list[str]) -> str:
    if BROKEN in statuses:
        return BROKEN
    return UNKNOWN if UNKNOWN in statuses else OK


# --- 결과 정리 ---

def _table(result: dict[str, Any]) -> str:
    rows = ['| 명령 | 결과 | 내용 |', '| --- | --- | --- |']
    for step in result['steps']:
        detail = step['detail'].replace('|', '\\|')
        rows.append(f"| {step['label']} (`{step['command']}`) | {STATUS_LABELS[step['status']]} | {detail} |")
    return '\n'.join(rows)


def _run_link(text: str = '실행 기록') -> str:
    server, repository, run_id = (os.environ.get(key) for key in ('GITHUB_SERVER_URL', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID'))
    return f' ([{text}]({server}/{repository}/actions/runs/{run_id}))' if server and repository and run_id else ''


def _gh(*args: str, write: bool = False, dry_run: bool = False) -> str:
    """gh CLI. `dry_run` 이면 이슈·라벨을 바꾸는 명령은 보내지 않고 출력만 한다."""
    if write and dry_run:
        print('[dry-run] gh', ' '.join(args))
        return ''
    return subprocess.run(['gh', *args], check=True, capture_output=True, text=True, encoding='utf-8').stdout


def _open_issue(label: str) -> int | None:
    issues = json.loads(_gh('issue', 'list', '--label', label, '--state', 'open', '--json', 'number', '--limit', '1'))
    return issues[0]['number'] if issues else None


def _previous_statuses(count: int) -> list[str]:
    """앞선 예약·수동 실행의 판정 (가까운 것부터). 결과 파일이 없는 실행(만료·실패)을 만나면 거기서 멈춘다."""
    try:
        runs = json.loads(_gh('run', 'list', '--workflow', WORKFLOW_FILE, '--status', 'completed', '--limit', '20', '--json', 'databaseId,event'))
    except subprocess.CalledProcessError:
        # 워크플로가 아직 기본 브랜치에 없으면(첫 실행 전) 실행 목록을 묻지 못한다
        return []
    current = os.environ.get('GITHUB_RUN_ID')
    statuses: list[str] = []
    for run in runs:
        if len(statuses) == count:
            break
        if run['event'] not in ('schedule', 'workflow_dispatch') or str(run['databaseId']) == current:
            continue
        with tempfile.TemporaryDirectory() as folder:
            try:
                _gh('run', 'download', str(run['databaseId']), '--name', REPORT_ARTIFACT, '--dir', folder)
            except subprocess.CalledProcessError:
                break
            try:
                report_data = json.loads((Path(folder) / 'report.json').read_text(encoding='utf-8'))
                statuses.append(report_data['results'][0]['status'])
            except (OSError, ValueError, LookupError, TypeError):
                # 결과 형식을 바꾼 뒤 남아 있는 예전 아티팩트(7일)처럼 모양이 다르면 거기서 끊는다. 그대로 두면 이슈 처리
                # 전체가 죽어, 고장 이슈도 열고 닫지 못한다
                break
    return statuses


def _update_issues(result: dict[str, Any], dry_run: bool) -> None:
    """고장은 api-broken, 사흘 연속 확인 못 함은 api-blocked 이슈로 알린다. 다시 괜찮아지면 닫는다."""
    table, link, status = _table(result), _run_link(), result['status']
    broken = [step['label'] for step in result['steps'] if step['status'] == BROKEN]
    _gh('label', 'create', BROKEN_LABEL, '--color', 'd73a4a', '--description', '매일 API 감시가 찾은 고장', '--force', write=True, dry_run=dry_run)
    _gh('label', 'create', BLOCKED_LABEL, '--color', 'fbca04', '--description', '매일 API 감시가 며칠째 확인하지 못함', '--force', write=True, dry_run=dry_run)

    number = _open_issue(BROKEN_LABEL)
    if status == BROKEN:
        body = f"{_today()} 감시에서 고장: {', '.join(broken)}{link}\n\n{table}"
        if number is None:
            _gh('issue', 'create', '--label', BROKEN_LABEL, '--title', f"API 감시: 고장 ({', '.join(broken)})", '--body', body,
                write=True, dry_run=dry_run)
        else:
            _gh('issue', 'comment', str(number), '--body', body, write=True, dry_run=dry_run)
    elif number is not None and status == OK:
        _gh('issue', 'close', str(number), '--comment', f'{_today()} 감시에서 모두 정상이다{link}', write=True, dry_run=dry_run)

    previous = _previous_statuses(BLOCKED_STREAK - 1)
    streak = status == UNKNOWN and len(previous) == BLOCKED_STREAK - 1 and all(item == UNKNOWN for item in previous)
    number = _open_issue(BLOCKED_LABEL)
    if streak and number is None:
        body = (f"{BLOCKED_STREAK}일 연속 확인 못 함{_run_link('오늘 실행 기록')}. 요청 제한·서버 오류 등으로 고장인지 알 수 없는 "
                f'상태가 이어진다. 막힘이 계속되면 감시를 덜 자주 돌리는 것을 검토한다.\n\n{table}')
        _gh('issue', 'create', '--label', BLOCKED_LABEL, '--title', f'API 감시: {BLOCKED_STREAK}일째 확인 못 함', '--body', body,
            write=True, dry_run=dry_run)
    elif number is not None and status != UNKNOWN:
        _gh('issue', 'close', str(number), '--comment', f'{_today()} 감시에서 확인 못 함이 없다{link}', write=True, dry_run=dry_run)


def report(paths: list[str], *, issues: bool, dry_run: bool) -> int:
    """결과 파일을 읽어 표를 남기고, 고장이 있으면 1 을 돌려준다 (실행이 실패로 끝나 GitHub 이 메일로 알린다)."""
    found = [Path(path) for path in paths if Path(path).is_file()]
    if found:
        result = json.loads(found[0].read_text(encoding='utf-8'))
    else:
        # 결과 파일이 없으면 조회 잡이 감시 코드나 설치에서 실패한 것이다
        result = {
            'group': GROUP, 'date': _today().isoformat(), 'status': BROKEN,
            'steps': [{'label': '조회 잡', 'command': '-', 'status': BROKEN, 'detail': '결과 파일 없음 (조회 잡 실패)'}],
        }
    text = f'## API 감시 {_today()}\n\n{_table(result)}\n'
    print(text)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as file:
            file.write(text)
    Path('report.json').write_text(json.dumps({'results': [result]}, ensure_ascii=False), encoding='utf-8')
    if issues:
        _update_issues(result, dry_run)
    return 1 if result['status'] == BROKEN else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='action', required=True)
    run = commands.add_parser('run', help='조회 명령을 부르고 결과를 JSON 파일로 쓴다')
    run.add_argument('--out', required=True)
    collect = commands.add_parser('report', help='결과 파일을 읽어 표를 남기고 이슈를 고친다')
    collect.add_argument('paths', nargs='*')
    collect.add_argument('--issues', action='store_true', help='고장·연속 확인 못 함을 이슈로 알린다 (예약·수동 실행만)')
    collect.add_argument('--dry-run', action='store_true', help='이슈·라벨을 바꾸지 않고 보낼 gh 명령만 출력한다')
    options = parser.parse_args()
    if options.action == 'run':
        result = run_all()
        Path(options.out).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        print(_table(result))
        return 0
    return report(options.paths, issues=options.issues, dry_run=options.dry_run)


if __name__ == '__main__':
    sys.exit(main())
