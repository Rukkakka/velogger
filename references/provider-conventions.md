# Provider Conventions

`src/velogger/api`·`src/velogger/service` 모듈을 쓰는 규칙. 형식 규칙은 [code-style.md](code-style.md),
계층 구조와 요청 제한은 [architecture.md](architecture.md) 를 본다.

velogger 는 소스가 velog 하나뿐이라 jibsa·baenggipyo 의 `providers/<source>/` 한 겹을 두지 않고, API 층과
service 층을 `src/velogger/` 바로 아래(`api/`·`service/`)에 둔다. 두 층의 역할·규약은 jibsa 를 그대로 따르고,
velog 고유의 구현·예외는 [velogger 개발 가이드](providers/velogger.md)에 적는다.

## 모듈 구성

```
src/velogger/
├── api/              # 아래층: velog API 를 그대로 옮긴 것. service 를 가져다 쓰지 않는다
│   ├── __init__.py   # 안내 docstring 만
│   ├── client.py     # VelogClient(BaseHTTPClient) + run_request_*
│   ├── request/      # 요청 파라미터·본문 모델 (service 와 같은 모듈 이름)
│   └── response/     # 응답 모델 (최상위 + 중첩, service 와 같은 모듈 이름, 공통은 common.py)
└── service/          # 윗층: api 를 조합해 CLI 출력 모델로 정규화
    ├── __init__.py   # 모듈 안내 docstring 만
    ├── common.py     # 두 모듈 이상이 쓰는 결과 모델·상수·안내 문구
    └── <기능>.py      # CLI 명령 묶음 하나 (auth, posts, post, users, write …)
```

- 중첩·공통 응답 모델도 `response/` 에 둔다 (여러 기능이 쓰면 `response/common.py`). 공통 베이스는 최상위
  모델보다 위에 둔다.
- service 결과 모델(`VelogWhoami`, `VelogPostSummary` 등)은 CLI 출력용이므로 그 기능의 service 모듈에 두고
  `BaseModel` + `extra='forbid'` 로 만든다.
- import 는 `service` → `api` 한 방향이다. `api/` 는 velog API 를 그대로 옮긴 아래층이라 service·CLI 를 모른다.

### service 모듈을 나누는 기준

1. **모듈 하나는 CLI 명령 묶음 하나를 맡는다.** 명령 이름만 알면 고칠 파일을 찾을 수 있게 한다. velogger 의 명령 ↔
   모듈 대응은 [velogger 개발 가이드](providers/velogger.md#명령과-요청-흐름)의 표에 있다.
2. **두 모듈 이상이 쓰는 심볼은 `common` 에 둔다.** 한 모듈만 쓰면 그 모듈에 둔다.
3. **import 는 `common` → 기능 모듈 방향으로만 한다.** 기능 모듈끼리 서로 가져다 쓰지 않는다. 같이 쓰게 되면
   그 심볼을 `common` 으로 옮긴다.
4. **모듈이 1,000줄을 넘으면 기능을 다시 나눈다.**
5. **새 명령은 맞는 모듈에 넣는다.** 맞는 모듈이 없으면 새 모듈을 만들고 velogger 개발 가이드의 표에 한 줄 추가한다.
6. CLI 와 테스트는 하위 모듈에서 바로 가져온다 (`from velogger.service.posts import ...`).
7. **요청·응답 모델(`request/`·`response/`)은 service 와 같은 모듈 이름으로 나눈다.** 두 기능 이상이 쓰는 모델,
   중첩 모델, 기반 모델은 `common` 에 둔다. 모듈이 작아도(모델 하나여도) 같은 이름으로 둔다. `client.py` 는
   클래스 하나라 나누지 않는다.

## Action id 명명

엔드포인트마다 **action id** 를 만들고, 그 엔드포인트의 모든 심볼을 action id 로 짓는다.

- **REST**(v2·캐시): 경로에서 경로 파라미터를 빼고 세그먼트를 snake_case 로 잇고, 버전 세그먼트(`vN`)를 끝으로
  옮긴다. 서비스 공통 접두어는 버린다 (`/api/v2/auth/sendmail` → `sendmail`, `/api/v2/auth/code/{code}` →
  `code`, 캐시 `/api/tag-posts` → `tag_posts`).
- **GraphQL**: 오퍼레이션의 루트 필드 이름을 snake_case 로 쓴다 (`trendingPosts` → `trending_posts`,
  `searchPosts` → `search_posts`, `auth` → `auth`). 루트 필드가 같은 오퍼레이션이 여럿이면 뜻이 드러나는
  이름으로 구분하고 그 근거를 client docstring 에 적는다.

| 심볼 | 패턴 | 예 |
| --- | --- | --- |
| 엔드포인트 ClassVar | `{action}_endpoint` (REST) / `{action}_query` (GraphQL 쿼리 문자열) | `sendmail_endpoint`, `AUTH_QUERY` |
| sync 메서드 | `run_request_{action}` | `run_request_sendmail` |
| async 메서드 | `arun_request_{action}` | `arun_request_sendmail` |
| 요청 파라미터 | `Velog{Action}RequestParameterModel` | `VelogTagPostsRequestParameterModel` |
| 요청 본문 | `Velog{Action}RequestPayloadModel` | `VelogSendmailRequestPayloadModel` |
| 응답 | `Velog{Action}ResponseModel` | `VelogAuthResponseModel` |

- 본문이 있는 엔드포인트(POST REST·GraphQL variables)는 `RequestPayloadModel`, 쿼리·경로만 있으면
  `RequestParameterModel`.
- `{Action}` 은 PascalCase, 접두어는 `Velog`.

## Client 클래스

- `BaseHTTPClient` 를 상속하고 다음을 선언한다.
  - 엔드포인트 ClassVar·GraphQL 쿼리 상수
  - `source_name: ClassVar[str] = 'velog'` — 요청 제한 상태 파일 이름
  - `default_rate_limit: ClassVar[dict[str, object]]`
  - `host`(v2)·`graphql_v3_host` 필드와 절대 URL property
  - `base_header` property — `User-Agent` 는 `self.user_agent`, `Origin: https://velog.io`
  - `cookies: list[StoredCookie] | None` — 세션 쿠키 (`Field(repr=False)`)
- `_client` / `_async_client` 는 `@cached_property` 로 만들고 `event_hooks=self.rate_limit_hooks()`,
  `cookies=self._cookie_jar()`, `verify`, `timeout`, `proxy` 를 넘긴다.
- 세션 쿠키 같은 비밀 값 필드는 `Field(repr=False)`.

## 요청 메서드

엔드포인트마다 `run_request_{action}` 를 만든다. CLI·service 는 sync 만 쓴다. async 클라이언트 기반
(`_async_client`·`async_rate_limit_hooks`)은 `BaseHTTPClient` 에 있어 라이브러리로 확장할 때 쓰지만, 지금은
`arun_request_*` 를 두지 않는다. async 로도 부르고 싶은 엔드포인트가 생기면 그때 sync 와 같은 모양으로 짝을
추가한다.

- **재시도.** 조회 전용(GraphQL 조회·`auth`·`code` 교환)은 `velog_retry`(5xx·429·timeout·transport).
  상태를 바꾸면서 다시 보내면 안 되는 호출(`sendmail` 메일 발송, 글·댓글·시리즈 작성 등 모든 쓰기 mutation, 업로드)은
  `velog_write_retry`(**429·503 만**). 502·504(게이트웨이)·500·timeout·transport 는 원 서버가 이미 처리했을 수 있어
  재시도하지 않는다 — 다시 보내면 글·댓글이 두 번 생긴다. 재시도 데코레이터는 client 모듈에 한 번만 정의한다.
- **`raise_for_status`** 는 `core.http.raise_for_status` 를 쓴다 (본문을 잘라 예외 메시지에, 민감 키는 가림).
- **직렬화.** REST 쿼리는 `model_dump(by_alias=True, exclude_none=True)`, 본문·GraphQL variables 는 `json=`.
- **해석하지 않는다.** 메서드는 검증된 응답 모델을 그대로 돌려준다. GraphQL `errors`(HTTP 200 안의 실패)도
  여기서 판정하지 않고 service 가 처리한다.
- **docstring.** 첫 줄에 HTTP 메서드와 경로(또는 GraphQL 오퍼레이션), 이어서 재시도 동작과 "요청 제한이
  켜져 있으면 429 는 재시도 없이 `RateLimitedError` 로 끝난다"를 적는다. async 변형은
  `Async variant of run_request_...` 한 줄.

## 요청·응답 모델

- 요청 모델은 `core.schema.RequestModel`(`extra='forbid'`), 응답 모델은 `ResponseModel`(`extra='allow'`)을
  상속한다. 둘 다 `validate_by_name=True` 라 코드에서는 필드 이름으로 만든다. 비공식 API 가 예고 없이 필드를
  더하므로 응답 모델은 모르는 필드를 버리지 않는다.
- 응답 필드는 **velog 가 빠뜨릴 수 있으면 `X | None = None`** 으로 둔다. 실제 응답에서 늘 오는 것만 필수로 한다.
- 와이어 이름이 snake_case 면 별칭이 필요 없다 (velog GraphQL 은 대부분 snake_case). camelCase 로 오는 캐시
  REST 등은 `alias='camelCase'` 를 단다. 선언 위치는 [code-style.md](code-style.md#4-pydantic-선언) 를 따른다.
- GraphQL 응답은 `data` 와 `errors` 를 함께 담는 봉투 모델로 받는다. `errors` 항목은 `response/common.py` 의
  `VelogGraphQLErrorModel`(message·extensions)로.

## GraphQL persisted query 주의

일부 v3·캐시 GraphQL 은 쿼리 본문 대신 **persisted query 해시**만 받을 수 있다 (jibsa 당근이 그랬다). velog 는
현재 `auth`·조회 쿼리를 본문으로 보내도 받지만, 새 엔드포인트가 해시만 받으면 웹 번들에서 꺼낸 해시를
client 상수로 두고 근거(번들 파일·쿼리 이름)를 주석으로 남긴다. 봇 차단·캡차는 우회하지 않는다.

## 새 엔드포인트 추가 순서

1. 실제 응답을 확인하고, 엔드포인트 설명과 필드 의미는 `api/client.py` docstring 과 `api/response/` 모델에 적는다.
2. 그 엔드포인트를 부를 기능의 `api/request/<기능>.py` / `api/response/<기능>.py` 에 모델,
   `api/client.py` 에 ClassVar/쿼리 상수 + sync/async 메서드.
3. 필요하면 맞는 service 모듈에서 조합한다. 자주 쓰는 공개 진입점이면 provider `__init__.py` 에 re-export 한다.
4. CLI 직접 조회로 실제 동작을 확인한다. 로그인·발행처럼 부작용 있는 엔드포인트는 사용자에게 확인하고 쓴다.
   테스트는 [추가 기준](development.md#검증과-테스트)에 맞을 때만 픽스처 + `httpx.MockTransport` 로 추가한다.
   픽스처는 실제 응답 구조를 본뜨되 값은 모두 가상으로 바꾸고(사용자·글·토큰·쿠키), 실제 응답은 커밋하지 않는다.
