# AGENTS.md

velog(velog.io)를 조회하고, 로그인한 사용자의 글·반응을 다루는 비공식 CLI (`velogger`).
LLM 에이전트가 셸로 호출하는 도구라, 출력 형식과 에러 형식이 곧 API 다.
CLI 코드는 모두 `src/velogger/` 아래에 있다.
개발 문서(구현 규약)는 `references/`, 사용자 문서(CLI 사용법)는 `docs/`에 있다.

velogger 는 소스가 velog 하나뿐이라, jibsa·baenggipyo 의 `providers/<source>/` 한 겹을 두지 않는다. 대신 그
provider 층을 그대로 펴서 API 층(`src/velogger/api`)과 service 층(`src/velogger/service`)을 `src/velogger/` 바로 아래에
둔다. 두 층의 규약(계층·모델 배치·재시도 등)은 [jibsa](https://github.com/Rukkakka/jibsa)를 그대로 따른다.

## jibsa·baenggipyo 와 다른 점: 로그인

jibsa·baenggipyo 는 "로그인 없는 기능만" 이 첫 규칙이지만, velogger 는 **로그인 기능을 포함한다.** velog 는
비밀번호가 없어(passwordless) 이메일 매직 링크나 소셜 로그인으로 받은 **세션 쿠키**가 인증 수단이다.

- **자격증명을 몰래 다루지 않는다.** 사용자의 로그인 code·쿠키는 사용자가 직접 CLI 에 넣는다. 에이전트가
  대신 로그인하거나, 브라우저 쿠키 저장소를 복호화해 꺼내 오지 않는다 (인포스틸러 기법이라 넣지 않는다).
  소셜 OAuth 는 헤드리스로 가로채지 않는다.
- **토큰·쿠키는 출력하지 않는다.** 로그인 정보는 로그인 여부·`username`·`is_trusted` 만 보여 준다.
  세션은 `<config_dir>/session.json` 에 사용자 전용 권한(0600)으로 저장한다 (`core/session.py`).
- **사용자를 대신해 보내는 기능은 명시적으로.** 글 발행·삭제·댓글·좋아요는 로그인 세션으로 사용자를 대신해
  보내는 일이다. 쓰기는 기본을 안전한 쪽(임시저장)으로 두고, 발행·삭제는 명시적 플래그를 요구한다.

## 구조

| 경로 | 내용 |
| --- | --- |
| `cli/` | Typer 명령 (`login`·`logout`·`whoami`·`limits`·`guide`, 조회·쓰기 명령), JSON·에러 출력 (`output.py`) |
| `core/http.py` | `BaseHTTPClient` — httpx 클라이언트 수명주기, 재시도 술어, `raise_for_status` |
| `core/ratelimit.py` | 프로세스 간 공유 요청 제한 (`RateLimiter`, `RateLimitedError`), 상태 디렉터리(`state_dir`) |
| `core/session.py` | 로그인 세션(쿠키) 저장·로드 (`Session`, `load_session`, `save_session`, 0600) |
| `core/errors.py` | `VeloggerError` — CLI 가 `{"error": {...}}` 로 내보내는 에러 |
| `core/schema.py` | `RequestModel` (`extra='forbid'`) / `ResponseModel` (`extra='allow'`), 요청 검증 오류 판정 |
| `api/` | 아래층: velog API 를 그대로 옮긴 것. `client.py`(`VelogClient` + `run_request_*`) · `request/` · `response/`. request·response 는 service 와 같은 이름의 기능별 모듈 ([모듈 구성](references/provider-conventions.md#모듈-구성)) |
| `service/` | 윗층: `api/` 를 조합해 CLI 출력 모델로 정규화 (기능별 모듈: `auth`·`posts`·`post`·`users`·`social`·`write`, 공통은 `common.py`) |

감시·데모 도구는 `scripts/` 에 있다: 매일 조회 명령을 실제로 불러 보는 [API 감시](references/development.md#매일-api-감시)
(`scripts/monitor/`, `.github/workflows/api-monitor.yml`)와 README 데모 녹화 대본(`scripts/demo/`). 둘 다 **조회만**
다루고 로그인·쓰기는 넣지 않는다 (실제 부작용).
README 로고(`docs/logo-light.svg`·`docs/logo-dark.svg`)는 `scripts/logo/build_logo.py` 로 만든다. 글자를 외곽선으로 바꾼
파일이라 직접 고치지 않고 스크립트를 고쳐 다시 만든다. 비공식 도구라 공식 velog 로고·청록색을 쓰지 않는다.

velog 비공식 API(v2 REST·v2/v3 GraphQL)의 엔드포인트·필드 의미는 provider 의 `api/client.py` docstring 과
`api/response/` 모델 설명에 적는다. 엔드포인트를 추가·수정하기 전에 먼저 읽고, 응답 형태는 CLI 직접
조회나 원본 응답으로 확인한다.

## 꼭 지킬 것

- **토큰·쿠키·추적 ID 는 출력하지 않는다.** 로그인 정보는 로그인 여부·username·is_trusted 만. 원본 응답을 통째로 내보내지 않는다.
- **로그인은 사용자가 한다.** 인증이 필요한 명령은 세션이 없으면 `NOT_LOGGED_IN` 에러로, "사용자가 `velogger login` 을 직접 실행하라" 는 힌트를 준다. 에이전트가 사용자의 code·쿠키를 대신 다루지 않는다.
- **발행에 캡차가 걸리면 넣지 않는다.** `is_trusted` 가 false 인 계정은 글 발행에 Cloudflare Turnstile 이 붙는다. 캡차를 풀지 않고, 그런 계정의 발행은 에러로 "웹에서 발행하라" 고 안내한다. 봇 차단을 우회하지 않는다.
- **조회 결과는 stdout JSON, 에러는 stderr JSON.** 도움말·자동완성·`guide`·`--version` 은 CLI 텍스트이며 `--verbose` 진행 로그는 stderr 로 나간다. 새 에러는 `VeloggerError` 로 코드·힌트를 붙여 던진다.
- **값이 없을 때:** 해당 없음 → 키 삭제, 모름 → `null`, 비어 있음 → `[]`.
- **내려갔거나 비공개·임시인 글은 그대로 드러내지 않는다.** 목록에서 `is_private`·`is_temp` 를 그대로 전하고, 없는 글은 `NOT_FOUND`. 가격처럼 캐시할 값은 없지만 조회는 항상 실시간이다.
- **서버가 거른 결과를 같은 조건으로 다시 거르지 않는다.** velog 의 분류·검색 결과를 다른 기준으로 다시 판정하지 않는다. 직접 거르는 건 서버가 받지 않는 조건뿐이고, 확인할 수 없어 뺀 항목은 사유를 `notes` 로 알린다.
- **모든 HTTP 요청은 요청 제한 훅을 거친다.** 새 클라이언트도 `rate_limit_hooks()` 를 `event_hooks` 로 넘긴다. 폴링으로 다시 묻는 요청도 마찬가지다.
- **검증은 실제 API 로, 테스트는 최소로.** 코드를 바꾸면 CLI 직접 조회 같은 실제 API 호출로 확인한다 (요청은 최소로). 로그인·발행처럼 실제 부작용이 있는 동작은 함부로 자동 실행하지 않는다. 테스트는 아주 드문 엣지케이스나 틀어지면 안 되는 핵심 동작일 때만 추가한다. ([검증과 테스트](references/development.md#검증과-테스트))
- **명령을 추가·삭제하면 매일 API 감시 목록도 고친다.** 로그인 없는 조회면 `scripts/monitor/api_check.py` 의 `STEPS` 에 넣고, 아니면(로그인·쓰기·네트워크 없음) `NOT_MONITORED` 에 이유를 적는다. 둘 다 안 하면 `test_every_command_is_monitored_or_excluded_with_reason` 이 실패한다. ([매일 API 감시](references/development.md#매일-api-감시))
- **velog 가 에러 없이 실패하는 지점을 조심한다.** v2 쓰기 프록시는 내부 에러를 삼켜 HTTP 200 + `null` 만 주고(`writePost` 는 인자 키가 하나라도 빠지면, `likePost` 는 토큰이 만료됐으면), 이미지 업로드는 `ref_id` 가 없으면 평문 403 을 준다. null 결과는 성공으로 내지 않는다(`service/write.py` 의 `_written`). 원인은 `VELOGGER_DEBUG=1` 로 원본 응답을 보고 좁힌다. 어느 요청 앞에 `require_auth` 가 필요한지는 실측 표를 따른다. ([velogger 개발 가이드](references/providers/velogger.md#조용한-실패-null-결과와-not-found))

## 문서 지도

공통 개발 규약 (`references/`)

- [development.md](references/development.md) — 개발 환경 설치, 검증과 테스트 원칙
- [architecture.md](references/architecture.md) — 계층 구조, 요청 흐름, 요청 제한, 세션
- [provider-conventions.md](references/provider-conventions.md) — provider 모듈 작성 규칙 (action id 명명, 재시도, 모델 배치, GraphQL 규약)
- [output-contract.md](references/output-contract.md) — CLI 출력·에러·exit code 규약, 공통 필드 규칙, 내보내지 않는 정보
- [code-style.md](references/code-style.md) — 문자열, import 순서, pydantic 선언, 타입 힌트, docstring, 테스트 코드 형식
- [workflow.md](references/workflow.md) — 이슈 → 브랜치 → 커밋 → PR 절차
- [release.md](references/release.md) — 버전 번호 규칙, CHANGELOG 쓰는 법, 릴리스 절차

소스별 개발 가이드 (`references/providers/`) — velog 에만 있는 구현·예외

- [velogger](references/providers/velogger.md)

## 문서 갱신

README 는 로고·배지·기능 요약(명령 표)·빠른 시작(실제 출력 예시 하나)·설치·로그인 방법·LLM 연결 방법·설정(환경 변수)·제작 목적과
로그인 원칙·문서 링크·기여 안내를 담는다. 명령을 추가·삭제하면 README 기능 표도 맞춘다. README 는 PyPI 프로젝트 페이지로도
쓰여 상대 링크와 heading 앵커가 깨지므로, README 안의 링크는 같은 문서를 가리키는 것까지 GitHub 전체 주소로 적는다.
사용자 문서는 `docs/`, 개발 문서는 `references/`에 둔다. CLI 문서는 LLM 에이전트에게 주는 사용 규칙이기도 하다.

`docs/llm.md` 는 에이전트가 가장 먼저 읽는 요약이고 `velogger guide` 가 그대로 출력한다 (설치본에는 패키지 안으로 복사된다). 짧게 유지하고 (200줄 이하), 링크는 설치본에서도 열리게 GitHub 전체 주소로 쓴다. 옵션 표·실측 근거는 넣지 않고 명령 고르기·출력 읽기·틀리기 쉬운 점·에러 대응만 적은 뒤 자세한 절로 링크한다.

| 바뀐 것 | 고칠 문서 |
| --- | --- |
| 명령·옵션·반환 필드·조회 한도 | `docs/velogger.md` |
| 명령 추가·삭제, 에이전트가 틀리기 쉬운 해석 규칙(누락값·ID·로그인 등)·에러 대응 | `docs/llm.md` |
| 공통 사용법(출력·에러 대응)·요청 제한·로그인 정책 | `docs/common.md` |
| velog 의 구현·예외·API 조사 결과 | `references/providers/velogger.md` |
| 여러 곳에 공통인 개발 규약 | `references/` 바로 아래 문서 |
| 사용자(에이전트 포함)에게 보이는 변경 | `CHANGELOG.md` 의 `Unreleased` ([쓰는 법](references/release.md#changelog-쓰는-법)) |

명령의 인자·기본값·조회 한도·반환값·오류·주의사항은 해당 명령 절에서 설명한다. 공통 규칙은 복사하지 않고 링크로 연결한다. 명령을 실제로 추가하면 해당 문서의 `예정` 표시를 지운다.

## 작업 절차

커밋 전에 **[references/workflow.md](references/workflow.md)** 를 읽는다. 요약:
`main` 에 직접 커밋하지 않고 `<type>/<slug>` 브랜치에서 작업하고, PR 로 머지한다. 커밋 하나에 관심사 하나,
`git add -A` 금지. 사용자에게 보이는 변경은 그 PR 에서 `CHANGELOG.md` 에 적는다. 버전 올리기·릴리스는
[references/release.md](references/release.md) 를 따른다.
