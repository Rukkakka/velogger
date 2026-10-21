# Architecture

velogger 의 계층 구조와, 명령 하나가 실행될 때 요청이 흐르는 경로. 형식 규칙은
[code-style.md](code-style.md), provider 모듈 작성 규칙은
[provider-conventions.md](provider-conventions.md), 출력 형식은
[output-contract.md](output-contract.md), velog 고유 구현은 [velogger 개발 가이드](providers/velogger.md)를 본다.

## 계층

```
cli/                 Typer 명령. 인자 검증 → service 호출 → emit / handle_errors
 └─ service/                      여러 엔드포인트를 묶어 CLI 출력 모델로 정규화 (기능별 모듈)
     └─ api/                         velog API 그대로: client.py (엔드포인트 하나 = 메서드 하나, run_request_*),
                                       request/·response/ 모델
         └─ core/http.py BaseHTTPClient   httpx 클라이언트 + 요청 제한 훅 (+ 세션 쿠키)
```

각 계층은 아래 계층만 안다.

- **client** 는 HTTP 호출과 응답 검증만 한다. 응답을 `Velog{Action}ResponseModel` 로 검증해 돌려줄 뿐,
  날짜 변환이나 비공개 판정 같은 해석은 하지 않는다. GraphQL 의 `errors`(HTTP 200 안의 실패)도 여기서
  판정하지 않고 모델에 담아 돌려준다.
- **service** 는 client 메서드를 조합해 조회·쓰기 흐름을 만들고, velog 응답을 CLI 출력 모델로 바꾼다.
  GraphQL `errors` 판정(UNAUTHENTICATED → `NOT_LOGGED_IN` 등), 로그인 세션 저장, `VeloggerError` 변환이
  여기서 일어난다. 함수는 첫 인자로 client 를 받는다 (`search_posts(client, keyword, ...)`).
- **cli** 는 옵션 파싱, client 생성(`with VelogClient(...) as client`), 출력(`emit`)만 한다. 비즈니스 로직을
  넣지 않는다. 인증이 필요한 명령은 `load_session()` 으로 세션을 읽어 `VelogClient(cookies=...)` 를 만든다.

## BaseHTTPClient

`core/http.py` 의 `BaseHTTPClient(BaseModel, ABC)` 가 provider client 의 기반이다. pydantic 모델이
**검증된 설정 객체**이자 **httpx 클라이언트 팩토리** 역할을 함께 한다.

- 공통 필드: `url_schema`, `verify`, `proxy`, `timeout`, `user_agent`, `rate_limit`. `extra='forbid'` 라
  오타 난 설정은 생성 시점에 실패한다.
- `VelogClient` 는 여기에 `host`(v2)·`graphql_v3_host`·`cookies` 를 더한다. `cookies` 로 받은 세션 쿠키를
  httpx 쿠키 자에 실어 보내고, 응답의 Set-Cookie(토큰 갱신)가 자에 반영되면 service 가
  `current_cookies()` 로 다시 저장한다.
- 서브클래스는 `_client` / `_async_client` 를 `@cached_property` 로 만든다. `close()` 가
  `self.__dict__.pop('_client', None)` 으로 꺼내 닫으므로 이름이 정확히 같아야 한다.
- `with` / `async with` 를 지원한다. CLI 와 service 호출부는 항상 컨텍스트 매니저로 쓴다.

## 두 서버와 GraphQL

velog 는 서버가 둘이다. 로그인·글쓰기 같은 인증 동작과 `is_trusted` 가 붙는 `auth` 조회는 구(舊)
**v2 서버**(`v2.velog.io`, REST + GraphQL)가, 공개 조회는 주로 **v3 서버**(`v3.velog.io`, GraphQL)가 맡는다.
일부 조회는 CDN 캐시(`cache.velcdn.com`)에 REST 로 있다. 어느 엔드포인트가 어느 서버인지는
[velogger 개발 가이드](providers/velogger.md)에 적는다.

- GraphQL 응답은 HTTP 200 이어도 본문에 `errors` 가 올 수 있다 (인증 실패·잘못된 입력). client 는 응답 모델에
  `data` 와 `errors` 를 함께 담고, service 가 판정한다 (`UNAUTHENTICATED` → `NOT_LOGGED_IN`).
- 같은 뜻의 조회가 v2·v3·캐시에 나뉘어 있으면, 로그인 없이 되는 쪽과 더 많은 필드를 주는 쪽을 가려 쓴다
  (예: 댓글 작성자는 v3 가 null 이라 v2 로 받는다).

## 로그인 세션

`core/session.py`. velog 는 비밀번호가 없어 세션 쿠키가 인증 수단이다.

- 세션 파일: `<config_dir>/session.json`, 권한 0600. `config_dir` 은
  `VELOGGER_CONFIG_DIR` > `$XDG_CONFIG_HOME/velogger` > `~/.config/velogger`.
- 쿠키 이름을 코드에 박지 않는다. velog 가 주는 Set-Cookie 를 이름 그대로 통째로 담아, velog 가 쿠키
  구성을 바꿔도 따라간다. 토큰 값은 어떤 출력에도 내보내지 않는다.
- 요청 제한 상태(`~/.cache/velogger`)와 달리, 로그인 자격이라 cache 가 아니라 config 에 둔다.

## 요청 제한

`core/ratelimit.py`. 비공식 API 라, **velogger 를 실행하는 모든 프로세스가 하나의 상태 파일을 공유**한다.
LLM 이 명령을 연달아 실행해도 간격이 지켜진다.

- 상태 파일: `<state_dir>/ratelimit/velog.json`. `state_dir` 은
  `VELOGGER_STATE_DIR` > `$XDG_CACHE_HOME/velogger` > `~/.cache/velogger`.
- `RateLimiter.reserve()` 가 `flock` 잠금 안에서 다음 슬롯을 예약하고, 실제 대기는 잠금 밖에서 한다.
  Windows 는 `msvcrt.locking` 으로 같은 잠금을 건다.
- 슬롯까지 `max_wait`(60초)보다 오래 기다려야 하면 `RateLimitedError(reason='budget')`.
- 429 를 받으면 쿨다운을 걸고 곧바로 `RateLimitedError(reason='cooldown')`. `RateLimitedError` 는
  `HTTPStatusError` 가 아니라 재시도 대상이 아니다.
- 연결: `BaseHTTPClient.rate_limit_hooks()` 를 httpx `event_hooks` 로 넘긴다.

기본 정책 값은 `VelogClient.default_rate_limit` 에 있다. 사용자에게 보여 주는 정책 표는
[공통 사용 규칙](../docs/common.md#요청-제한과-limits)에 있으니, 정책을 바꾸면 그 표도 함께 고친다.
