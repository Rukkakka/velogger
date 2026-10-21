# Output Contract

velogger 는 LLM 에이전트가 셸로 호출하는 도구라, CLI 의 출력 형식이 곧 공개 API 다. 여기 적힌 규칙을
바꾸는 변경은 `docs/common.md` 와 `docs/velogger.md` 의 출력 규칙·사용 지침도 함께 고친다.
구현은 `cli/output.py`, `cli/app.py` 의 `run()`.

## stdout / stderr

아래 JSON 계약은 조회 결과와 에러에 적용한다. `--help`·자동완성·`guide`·`--version` 은 CLI 텍스트를
출력하고, `--verbose` 는 stderr 에 진행 로그를 추가한다.

`--help` 는 stdout 이 터미널이면 Rich 표로, 아니면(파이프·LLM 셸) 줄글로 쓴다 (`use_plain_help`). 셸로 부르는
에이전트에게는 줄바꿈만 있는 텍스트가 맞으므로, 예시 명령은 docstring 에서 한 줄에 하나씩 쓴다.

- **결과는 stdout 에 JSON 하나.** `emit()` 으로만 쓴다. `print` 나 로그를 stdout 에 쓰지 않는다.
- **에러는 stderr 에 `{"error": {...}}` JSON 하나.** `emit_error()` 로만 쓴다. 사용법 오류(없는 옵션, 잘못된
  값, 인자 누락)도 마찬가지다. `run()` 이 Typer 를 `standalone_mode=False` 로 돌려 Click 예외를 직접 잡는다.
- 로그(`--verbose`)는 `logging` 으로 stderr 에 나간다. 기본 레벨은 ERROR.
- JSON 은 터미널이면 들여쓰기, 파이프면 한 줄. `--pretty/--compact` 로 강제한다. `ensure_ascii=False` 로
  한글을 그대로 쓰되, 쓸 스트림의 인코딩이 담지 못하는 글자가 있으면 그 출력만 `ensure_ascii=True`(`\uXXXX`)로 쓴다
  (`cli/output.py` 의 `_dumps`). Windows 에서 `PYTHONUTF8` 없이 파이프로 받으면 stdout 이 cp949 라, 이모지가 든 결과가
  `UnicodeEncodeError`(ValueError) → 'velog 응답이 이상하다' 는 `PARSE_ERROR` 로 나갔다 (쓰기는 이미 반영된 뒤였다).

## 에러

```json
{"error": {"code": "NOT_LOGGED_IN", "message": "...", "hint": "...", "status": 401}}
```

- `code` 는 기계가 읽는 값, `message` 는 사람이 읽는 설명, `hint` 는 **다음에 할 행동**이다. LLM 이 hint 를 보고
  재로그인·옵션 수정·재시도를 고르므로, 새 에러에는 구체적인 hint 를 단다.
- 애플리케이션 에러는 `core.errors.VeloggerError` 로 던진다. 추가 필드는 `details` 에 넣으면 에러 JSON 에
  평탄하게 실린다.
- CLI 명령 본문은 `with handle_errors():` 로 감싼다. 예외 → 코드 매핑:

| 예외 | code | exit |
| --- | --- | --- |
| `VeloggerError` | 예외의 `code` | 1 (`INVALID_ARGUMENT` 는 2) |
| pydantic `ValidationError` — 요청 모델(`RequestModel`) | `INVALID_ARGUMENT` | 2 |
| pydantic `ValidationError` — 응답 모델·결과 모델 (응답 형식 변경) | `PARSE_ERROR` | 1 |
| `HTTPStatusError` 401 / 403 / 404 / 429 / 그 밖 | `NOT_LOGGED_IN` / `FORBIDDEN` / `NOT_FOUND` / `RATE_LIMITED` / `UPSTREAM_ERROR` | 1 |
| 그 밖의 `HTTPError` | `NETWORK_ERROR` | 1 |
| `ValueError` (JSON 아닌 응답의 `JSONDecodeError`) | `PARSE_ERROR` | 1 |
| 그 밖의 모든 예외 | `INTERNAL_ERROR` | 1 |
| Click `UsageError` (`run()` 에서) | `INVALID_ARGUMENT` | 2 |
| `KeyboardInterrupt` / Click `Abort` | `INTERRUPTED` | 130 / 1 |

- 쓰이는 코드: `INVALID_ARGUMENT`, `NOT_LOGGED_IN`, `LOGIN_FAILED`, `FORBIDDEN`, `NOT_FOUND`, `ALREADY_EXISTS`,
  `RATE_LIMITED`, `UPSTREAM_ERROR`, `NETWORK_ERROR`, `PARSE_ERROR`, `INTERNAL_ERROR`, `INTERRUPTED`, `CLI_ERROR`.
  새 코드를 만들면 공통 사용 문서의 exit code 표와 오류 대응에도 추가한다.
- 입력 검증 실패는 항상 exit 2. 사용자 정의 hint 가 필요한 사용법 오류는 `HintedUsageError` 를 쓴다.
- GraphQL `errors`(HTTP 200 안의 실패)는 service 가 판정한다. `UNAUTHENTICATED` 는 조회 명령에서는
  "로그인 안 됨"(결과)으로, 인증이 필요한 명령에서는 `NOT_LOGGED_IN` 에러로 바꾼다. 대상이 없다는 에러
  (`extensions.code` 가 `NOT_FOUND` 이거나 메시지에 `not found`)는 `NOT_FOUND`, 남의 것이라는 에러(`NO_PERMISSION`
  이거나 메시지에 `no permission`·`not yours`)는 `FORBIDDEN`, 이미 있는 것과 겹친다는 에러(`ALREADY_EXISTS`·`CONFLICT`)는
  `ALREADY_EXISTS`, 그 밖의 GraphQL 에러는 `UPSTREAM_ERROR`. '잠시 뒤 다시 시도' 힌트의 `UPSTREAM_ERROR` 로 두면 에이전트가
  다시 보내도 결과가 같은 요청을 되풀이한다.
- 쓰기 mutation 이 errors 없이 null 을 주면 성공으로 내지 않고 `UPSTREAM_ERROR` 로 바꾼다 (velog v2 가 내부 에러를
  삼킨다, [velogger 개발 가이드](providers/velogger.md#조용한-실패-null-결과와-not-found)). hint 는 "바로 다시 보내지 말고 반영
  여부를 먼저 확인" 이다.

## 결과 출력

- 검색 범위·일부 조회·주의 안내는 `emit(..., notes=...)` 로 맨 앞 `notes` 에 붙이고, 없으면 키를 뺀다. 안내는
  짧게 쓴다 (매번 나오는 안내는 출력 토큰을 늘린다).
- 리스트를 그대로 내보내면 `notes` 를 붙이기 위해 `{"items": [...]}` 로 감싼다.
- service 가 안내를 만들면 결과 모델에 `notes: Annotated[list[str], Field(exclude=True)]` 로 담고 CLI 가
  `emit(result, notes=result.notes or None)` 으로 넘긴다 (예: `series` 가 글 정보 없는 항목을 뺐을 때).

### 값이 없을 때

| 상태 | 표현 | 구현 |
| --- | --- | --- |
| 해당 없음 (그 조회에 원래 없는 항목) | **키를 뺀다** | `@model_serializer` 또는 모델에서 제외 |
| 모름 (해당은 되지만 velog 가 안 알려 줌) | `null` | 필드 기본값 `None` |
| 알려 줬는데 비어 있음 | `[]` | 빈 리스트 |

- service 에서 "모름"과 "없음"을 섞지 않는다.

### 로그인·개인정보 (내보내지 않는 정보)

velogger 는 **조회·작성까지만** 한다. 자격증명과 추적 정보는 모델에 넣지 않는다.

- **토큰·쿠키·세션 ID·추적 ID 를 출력하지 않는다.** 로그인 정보는 로그인 여부·`username`·`is_trusted` 만 보여 준다
  (AGENTS.md '꼭 지킬 것'). 계정 이메일·본인 사용자 ID 는 velog 가 줘도 내보내지 않는다. 세션 파일 경로는 `logout`
  등에서 보여 줘도 된다.
- 로그인 code 는 URL 경로(`/api/v2/auth/code/{code}`)에 실리므로, 에러 메시지·재시도 로그에 URL 을 넣을 때 경로까지
  가린다 (`core/http.py` 의 `SENSITIVE_PATH_PATTERN`).
- 원본 응답을 통째로 내보내지 않는다. 글 본문은 사용자가 요청한 글 조회(`post`)에서 제공하지만, 타인의
  이메일·추적 식별자 같은 값은 거른다.
- 응답 모델(`api/response/`)에는 이런 필드가 있어도 되지만, 출력 모델로 옮기지 않는다.

### 비공개·임시·내려간 글

결과는 항상 실시간 조회다. 가격처럼 캐시할 값은 없다.

- 목록·상세에서 `is_private`·`is_temp` 를 그대로 전한다 (숨기거나 지어내지 않는다). 비공개 글은 로그인한
  본인만 볼 수 있어, 남의 비공개 글은 애초에 응답에 오지 않는다. 소스가 주지 않으면(캐시 trending·tag) `null` 이다.
- 초안(`is_temp: true`)의 공개 주소는 404 라 `url` 은 편집 주소(`https://velog.io/write?id=<id>`)로 낸다.
- 없는 글(삭제·잘못된 slug·없는 사용자)은 `NOT_FOUND`.

## 개수 상한

`--limit` 의 최대값은 CLI 정책이며 서버의 요청당 최대 개수와 구분한다.

- 목록 조회의 `--limit` 은 조회 할당량이다. 실제로 받은 원본 수로 세고, 받은 뒤 뺀 만큼 다시 채우지 않는다.
- 커서(`cursor`) 기반 페이지는 다음 커서가 없거나 진행하지 않거나 요청 횟수 상한에 닿으면 중단한다.
- `returned` 는 실제 반환 수이며 요청한 `limit` 과 같다는 보장이 없다. 집계 범위·제외 사유는 `notes` 로 설명한다.

명령별 기본값·최대값은 `docs/velogger.md` 의 해당 명령 절에, 조회 방식별 예외는 [velogger 개발 가이드](providers/velogger.md)에 적는다.
