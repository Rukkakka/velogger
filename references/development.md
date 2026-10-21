# 공통 개발 환경

[개발 규약](../AGENTS.md) · [코드 형식](code-style.md) · [작업 절차](workflow.md)

## 설치

코드를 고치려면 저장소를 받아 편집 가능 모드로 설치한다. 고친 코드가 바로 반영된다. Python 3.11 이상과 git 이 필요하다 ([README 의 설치](../README.md#설치)).

```bash
# macOS·Linux
git clone https://github.com/Rukkakka/velogger && cd velogger

python3.11 -m venv .venv          # 또는 uv venv --python 3.11
.venv/bin/pip install -e ".[dev]" # 또는 uv pip install -e ".[dev]"

.venv/bin/velogger --help            # source .venv/bin/activate 후에는 velogger 만 쳐도 된다
```

```powershell
# Windows (PowerShell) — bin 대신 Scripts 폴더를 쓴다
git clone https://github.com/Rukkakka/velogger; cd velogger

py -m venv .venv                       # 또는 uv venv --python 3.11
.venv\Scripts\pip install -e ".[dev]"  # 또는 uv pip install -e ".[dev]"

.venv\Scripts\velogger --help             # .venv\Scripts\Activate.ps1 후에는 velogger 만 쳐도 된다
```

Windows 는 [README 의 Windows 에서 쓸 때](../README.md#windows-에서-쓸-때)(UTF-8 출력 설정)도 그대로 적용된다. `Activate.ps1` 이 실행 정책 때문에 막히면 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 를 한 번 실행한다.

## 코드 검사

[코드 형식](code-style.md) 규칙 중 도구로 잡을 수 있는 것은 ruff 와 mypy 가 검사한다. 설정은 `pyproject.toml` 에 있다. 코드를 고쳤으면 둘 다 0건이어야 한다.

```bash
.venv/bin/ruff check          # 따옴표, import 순서, 안 쓰는 import, 타입 힌트 누락
.venv/bin/ruff check --fix    # import 정렬·따옴표처럼 자동으로 고칠 수 있는 것은 고친다
.venv/bin/mypy                # src 전체 타입 검사
```

Windows 는 `.venv\Scripts\ruff`, `.venv\Scripts\mypy` 로 부른다.

- `ruff format` 은 쓰지 않는다. 여러 줄로 쓰는 필드 선언([코드 형식 §4](code-style.md#4-pydantic-선언))을 한 줄로 합친다.
- import 바로 위에 주석을 달면 ruff 가 그 앞에 빈 줄을 넣어 같은 그룹이 갈라진 것처럼 보인다. import 에 다는 주석은 줄 끝에 쓴다.
- mypy 오류를 `# type: ignore` 로 덮지 않는다. 앞에서 이미 확인해 None 일 수 없는 값이면 `assert` 로 좁히고 왜 그런지 주석을 단다. 정말 필요할 때만 오류 코드를 붙여 쓴다 (`# type: ignore[assignment]`).

## 검증과 테스트

### 검증은 실제 API 로

- 코드를 바꾸면 CLI 직접 조회나 원본 응답 확인처럼 실제 API 호출로 동작을 확인하는 것이 기본이다. 가짜 응답(픽스처·`MockTransport`)으로만 확인했다고 하지 않는다. 실제 API 를 부르는 테스트(live 테스트)는 두지 않고 CLI 직접 조회로 확인한다. 매일 새벽 도는 [API 감시](#매일-api-감시)만 예외다 (pytest 가 아니라 따로 도는 워크플로다).
- 실제 API 로 재현할 수 없는 상태(커서가 멈춘 응답 등)만 가짜 응답으로 확인하고 그 이유를 적는다.
- 요청 수는 최소로 하고 요청 제한 훅을 거친다. 로그인·발행·삭제처럼 부작용이 있는 동작은 함부로 실행하지 않는다 (실제 메일 발송·글 생성).
- 문서·문구만 바꿨으면 링크·코드 선언·출력 필드 대응만 검토하고 pytest·실제 호출은 하지 않는다.

### 테스트 추가는 두 경우만

1. 실제 API 로 재현하기 어려운 아주 드문 엣지케이스
2. 틀어지면 안 되는 핵심 동작 (출력 계약·토큰 비노출·비공개/내려간 글 처리 같은 공통 규칙)

기존 테스트를 넓히는 것도 같은 기준이다. 추가할 때는 둘 중 무엇인지 PR·보고에 적는다. 그 밖의 경우(일반 분기, 요청 파라미터 모양, 문구, 구현을 그대로 따라 쓰는 검증, 다른 테스트와 겹치는 검증)에는 추가하지 않는다.

### pytest 실행 범위

```bash
.venv/bin/pytest tests/test_velog.py::test_name   # 평소: 바꾼 부분 테스트 몇 개만 이름으로
.venv/bin/pytest                                  # 전체 (네트워크 없음) — 실행 전에 사용자에게 묻는다
```

Windows 는 `.venv/bin/pytest` 대신 `.venv\Scripts\pytest` 로 부른다.

- **전체 `pytest` 는 실행 전에 사용자에게 묻는다.** PR 에서는 [CI](../.github/workflows/ci.yml) 가 전체를 돌린다.
- 평소에는 바꾼 함수를 직접 검사하는 테스트 몇 개만 `tests/test_x.py::test_name` 으로 골라 한 번 실행한다. 파일 전체, 넓은 `-k` 키워드, 바꾼 함수를 부르는 테스트를 모두 모아 돌리는 것도 하지 않는다. 실패하면 그 테스트만 다시 돌린다.
- 문구·문서·이름 변경처럼 깨질 위험이 없으면 바꾼 부분의 테스트도 돌리지 않는다.

### 픽스처와 테스트 환경

- 픽스처는 `tests/fixtures/velog/<action_id>.json`. 실제 응답 구조를 본뜬 **가상 데이터**다. 실제 사용자·글·토큰·쿠키는 커밋하지 않는다. 만드는 법은 [새 엔드포인트 추가 순서](provider-conventions.md#새-엔드포인트-추가-순서)에 있다.
- 픽스처는 테스트가 읽는 것만 둔다. 응답 형태를 보여 주는 참고 자료로 두지 않고, 테스트를 지워 아무도 읽지 않게 된 픽스처는 함께 지운다.
- `conftest.py` 가 `VELOGGER_STATE_DIR` 을 임시 디렉터리로 돌려 `~/.cache/velogger` 를 건드리지 않는다.
- 테스트 코드 형식(파일·함수 이름, `MockTransport` 끼우는 법)은 [코드 형식](code-style.md#8-테스트-코드)에 있다.

## 매일 API 감시

비공식 API 는 velog 가 응답을 바꾸면 조용히 깨진다 (2026-10-19 의 `writePost` 처럼 에러도 없이 null 만 오기도
한다). 사용자보다 먼저 알려고 [API 감시 워크플로](../.github/workflows/api-monitor.yml)가 한국 시간 매일
04:17 에 조회 명령을 실제로 부른다 ([scripts/monitor/api_check.py](../scripts/monitor/api_check.py)). jibsa 의 감시를 옮긴 것이고,
소스가 하나라 러너를 나누지 않는다. CI 는 여전히 실제 API 를 부르지 않는다.

- **무엇을 부르나:** 로그인 없이 되는 조회만 (`trending`·`recent`·`search`·`tag`(첫 페이지·`--cursor` 다음 페이지)·`posts`·`user`·
  `followers`·`followings`·`post`·`comments --replies`·`series`). `comments` 는 `--replies` 로 대댓글 조회(`ReloadReplies`)까지 본다
  (그 글에 대댓글이 있는 댓글이 없으면 그날은 대댓글 요청이 나가지 않는다). `post`·`comments` 는 `trending` 에서 셋이 모두 있는 첫 글의 `username`·`url_slug`·`id` 를 (값마다 다른 글에서 꺼내면 없는 글을 불러 거짓 고장이 난다),
  `series` 는 `user velopert` 의 첫 시리즈를, 태그 다음 페이지는 첫 페이지의 `next_cursor` 를 이어 받는다 (`Step.captures`, slug 를
  박아 두면 이름이 바뀔 때 거짓 고장이 난다). 결과가 0건일 리 없는 곳(트렌딩·`python`·`react`·velopert)만 부르고 `--limit` 은 작게 준다.
  **로그인·쓰기(`publish`·`like`·`comment` 등)와 로그인이 필요한 조회(`feed`·`liked` 등)는 넣지 않는다** — 실제
  부작용이 있거나 CI 에 세션이 없다. 넣지 않는 명령은 `api_check.py` 의 `NOT_MONITORED` 에 이유와 함께 적는다.
- **판정:**

  | 판정 | 기준 |
  | --- | --- |
  | 정상 | exit 0, 그 명령에 정한 칸(`Step.expect`)에 값이 있음 |
  | 고장 | `PARSE_ERROR`·`INTERNAL_ERROR`·`NOT_FOUND`·`INVALID_ARGUMENT`·`FORBIDDEN`·`CLI_ERROR`·`NOT_LOGGED_IN`(로그인 없는 조회에 로그인을 요구하게 바뀜)·4xx 이거나 상태 없는 `UPSTREAM_ERROR`(GraphQL 이 쿼리를 거절함), 정한 칸이 비어 있음, JSON 이 아닌 출력, 결과 파일 없음(조회 잡 실패) |
  | 확인 못 함 | `RATE_LIMITED`, `NETWORK_ERROR`, 5xx `UPSTREAM_ERROR`, 5분 안에 안 끝남, 앞 명령이 값을 주지 않아 건너뛴 명령 |

- **알림:** 고장이면 `api-broken` 이슈를 열고(열려 있으면 댓글) 실행이 실패로 끝나 GitHub 이 메일로 알린다. 모두 정상이면 그 이슈를
  닫는다. 사흘 연속 확인 못 함이면 `api-blocked` 이슈를 열고, 확인 못 함이 없어지면 닫는다. 결과 표는 실행 요약
  (`GITHUB_STEP_SUMMARY`)과 아티팩트(`result`·`report`, 7일)로 남는다.
- **명령을 추가·삭제하면** `api_check.py` 의 `STEPS` 에 넣거나(로그인 없는 조회), `NOT_MONITORED` 에 이유와 함께
  적는다. 둘 다 아니면 `tests/test_monitor.py::test_every_command_is_monitored_or_excluded_with_reason` 이 실패한다
  (감시에서 말없이 빠지는 명령이 없게).
- **수동 실행:** Actions 의 "API 감시" → Run workflow, 또는 `gh workflow run api-monitor.yml`. 로컬에서는
  `.venv/bin/python scripts/monitor/api_check.py run --out result.json` (요청이 13번쯤 나가니 필요할 때만). 세션 쿠키를 싣지 않으려면
  `VELOGGER_CONFIG_DIR` 를 빈 폴더로 준다 (CI 와 같은 비로그인 상태). 이슈 처리는 `report result.json --issues --dry-run` 으로 보낼
  `gh` 명령만 본다.
- 감시 파일(`scripts/monitor/`, 워크플로)을 고친 PR 에서도 한 번 돌고, 이슈는 건드리지 않는다. 고장이면 그 PR 의 검사가 실패한다 (필수
  검사는 아니다).
- 공개 저장소라 실행 기록에는 요청 로그(`--verbose`)만 남기고, 결과 본문(글 제목·본문)은 정상이 아닐 때만 앞부분을 남긴다.
- **알아 둘 것:** 워크플로는 GitHub 에 push 된 뒤부터 돈다. 로컬에서만 작업 중이면 감시는 아직 꺼져 있다. 공개 저장소에 60일 동안
  활동이 없으면 GitHub 이 예약 실행을 끈다. 꺼졌으면 Actions 의 "API 감시" 에서 다시 켠다.

## README 데모

`scripts/demo/demo.tape` 가 [VHS](https://github.com/charmbracelet/vhs) 녹화 대본이다
(`vhs scripts/demo/demo.tape` → `docs/demo/demo.gif`). **조회만 녹화한다** — 로그인·쓰기는 실제 글이 올라가고
화면에 계정 정보가 남는다. 녹화 전에 `velogger logout` 으로 세션이 없는 상태인지 확인한다.
