# 공통 CLI 사용 규칙

[설치](../README.md) · [LLM 가이드](llm.md) · [velogger 사용법](velogger.md)

## 출력 규칙

- 결과는 stdout 에 JSON. 터미널이면 들여쓰기, 파이프면 한 줄 (`--pretty` / `--compact` 로 강제). 한글은 그대로 쓰고, stdout 인코딩(Windows 의 cp949 등)이 담지 못하는 글자(이모지 등)가 있으면 그 출력은 `\uXXXX` 로 쓴다 (JSON 으로 읽으면 같은 값이다).
- 값이 없을 때:

  | 상태 | 표현 |
  |---|---|
  | 해당 없음 | **키를 뺀다** |
  | 모름 (해당은 되지만 velog 가 안 알려 줌) | `null` |
  | 알려 줬는데 비어 있음 | `[]` |
- 에러는 **항상** stderr 에 `{"error": {"code", "message", "hint", ...}}` JSON. 사용법 오류(없는 옵션·잘못된 값·인자 누락)도 마찬가지.
- 토큰·쿠키 값은 어떤 출력에도 내보내지 않는다. 로그인 정보는 로그인 여부·`username`·`is_trusted` 만 보여 준다.

| exit code | 뜻 | 출력 |
|---|---|---|
| 0 | 성공 (`--help`, 인자 없이 실행 포함) | stdout 에 결과 JSON (도움말·`velogger guide`·`velogger --version` 은 텍스트) |
| 1 | 실행 중 에러 (`NOT_LOGGED_IN`, `LOGIN_FAILED`, `NOT_FOUND`, `FORBIDDEN`, `ALREADY_EXISTS`, `RATE_LIMITED`, `UPSTREAM_ERROR`, `NETWORK_ERROR`, `PARSE_ERROR`, `INTERNAL_ERROR`) | stderr 에 에러 JSON |
| 2 | 입력 오류 (`INVALID_ARGUMENT`) | stderr 에 에러 JSON |
| 130 | 인터럽트로 중단 (`INTERRUPTED`, Ctrl+C·SIGINT) | stderr 에 에러 JSON |

## 로그인과 세션

velog 는 비밀번호가 없다. 세션 쿠키가 인증 수단이고, 로그인은 사용자가 직접 한다 (자세한 흐름은 [velogger 사용법](velogger.md#login)). 세션은 `~/.config/velogger/session.json` (`VELOGGER_CONFIG_DIR` 로 변경)에 사용자 전용 권한(0600)으로 저장된다. 쿠키 값은 출력에 나오지 않는다.

## 요청 제한과 `limits`

모든 velogger 프로세스가 상태 파일(`~/.cache/velogger/ratelimit/velog.json`, `VELOGGER_STATE_DIR` 로 변경)을 공유해, 명령을 연달아 실행해도 간격이 지켜진다.

| 요청 간격 | 분당 상한 | 429 후 쿨다운 |
|---|---|---|
| 0.3초 | 90 | 2분 |

- 슬롯이 날 때까지 기다리되, 60초 넘게 기다려야 하면 `RATE_LIMITED` (`reason: budget`) 를 낸다.
- 429 를 받으면 쿨다운 동안 요청을 보내지 않고 `RATE_LIMITED` (`reason: cooldown`, `retry_after_seconds`) 를 낸다.
- `velogger limits` 로 상태를 보고 `velogger limits --reset` 으로 초기화한다 (네트워크 요청 없음).
