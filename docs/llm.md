# velogger LLM 사용 가이드

셸로 `velogger` 를 불러 velog.io 를 다루는 LLM 에이전트용 요약이다. `velogger guide` 가 이 문서를 그대로 출력한다. 옵션 세부는 `velogger <명령> --help`, 더 깊은 설명은 `velogger guide velogger <명령>` 으로 읽는다.

> **조회**(`trending`·`recent`·`search`·`posts`·`post`·`comments`·`user`·`tag`·`series`·`followers`·`followings`), **작성·반응**(`publish`·`edit`·`drafts`·`like`·`unlike`·`comment`·`comment-edit`·`comment-remove`·`follow`·`unfollow`·`series-create`·`series-add`·`upload`·`stats`·`feed`·`liked`), **로그인**(`login`·`logout`·`whoami`), 요청 제한(`limits`).

## 꼭 지킬 규칙

- 결과는 stdout 에 JSON 하나, 에러는 stderr 에 `{"error": {"code", "message", "hint", ...}}`. exit 0 성공, 1 실행 에러, 2 입력 오류, 130 중단.
- 값이 없을 때: **키 없음** = 해당 없음, **`null`** = 모름, **`[]`** = 비어 있음.
- `--verbose` 는 쓰지 않는다 (stderr 에 로그가 섞인다).
- 명령은 하나씩 차례로 부른다. 요청 간격은 모든 velogger 프로세스가 함께 지킨다.

## 로그인

velog 는 **비밀번호가 없다.** 이메일 매직 링크나 소셜 로그인으로 받은 세션 쿠키가 인증 수단이다. 그래서 "id/pw 를 줄 테니 로그인해" 는 velog 에 로그인 수단이 없어 불가능하다. 로그인은 **사용자가 직접** 한다 (에이전트가 사용자의 code·쿠키를 대신 다루지 않는다).

- 로그인이 필요한 명령에서 로그인이 안 돼 있으면 `NOT_LOGGED_IN` 에러가 난다. 그러면 **사용자에게 터미널에서 `velogger login` 을 직접 실행하라고 안내**한다.
- 로그인 흐름(사용자가 함):
  1. `velogger login <이메일>` → velog 가 그 주소로 로그인 링크를 보낸다
  2. 메일 속 링크(`velog.io/email-login?code=...`)를 복사 (브라우저로 열지 말 것)
  3. `velogger login --code <링크>` → 세션 저장
- 소셜(깃허브 등) 가입자 대체 방법: 브라우저에서 복사한 velog.io 쿠키로 `velogger login --cookie 'name=value; ...'`.
- `velogger whoami` 로 로그인 상태를 본다. `is_trusted` 가 `false` 면 글 발행에 캡차(Cloudflare Turnstile)가 붙어 CLI 로는 발행할 수 없다 — 그런 글은 웹에서 발행하라고 사용자에게 안내한다.

## 무엇을 하려면

| 하려는 일 | 명령 |
| --- | --- |
| 트렌딩 글 | `velogger trending [--period day\|week\|month\|year]` |
| 최신 글 | `velogger recent` |
| 글 검색 | `velogger search <검색어> [--user <username>]` |
| 한 사람 글 목록 | `velogger posts <username> [--tag <태그>]` |
| 글 본문 읽기 | `velogger post <username> <url_slug>` |
| 댓글 읽기 | `velogger comments <글 id> [--replies]` |
| 사용자 프로필·태그·시리즈 | `velogger user <username>` |
| 시리즈 글 순서대로 | `velogger series <username> <series_slug>` |
| 태그별 글 | `velogger tag <태그>` |
| 팔로워·팔로잉 | `velogger followers <username>` · `velogger followings <username>` |
| 글 쓰기 (로그인) | `velogger publish "<제목>" --file <본문파일>` (기본 임시저장, `--publish` 로 발행) |
| 글 고치기 (로그인) | `velogger edit <id> [--title ...] [--thumbnail <URL>] [--description "<소개글>"] [--publish]` |
| 내 초안 목록 (로그인) | `velogger drafts` |
| 좋아요 / 취소 (로그인) | `velogger like <id>` / `velogger unlike <id>` |
| 댓글 쓰기·수정·삭제 (로그인) | `velogger comment <id> "<내용>"` · `comment-edit <댓글id> "<내용>"` · `comment-remove <댓글id> --yes` |
| 팔로우 (로그인) | `velogger follow <username>` / `velogger unfollow <username>` |
| 시리즈 만들기·넣기 (로그인) | `velogger series-create "<이름>"` → `velogger series-add <시리즈id> <글id>` |
| 이미지 올리기 (로그인) | `velogger upload <파일> --post <글id>` → 결과의 `markdown` 을 본문에 넣어 `edit` |
| 내 피드·좋아요한 글 (로그인) | `velogger feed` · `velogger liked [--read]` |
| 내 글 조회수 (로그인) | `velogger stats <id>` |
| 로그인 (사용자가 직접) | `velogger login <이메일>` → `velogger login --code <링크>` |
| 로그인 상태 확인 | `velogger whoami` |
| 로그아웃 | `velogger logout` |
| 요청 제한 상태 | `velogger limits` (네트워크 요청 없음) |
| 이 가이드 다시 보기 | `velogger guide` (네트워크 요청 없음) |

## 쓰기 (로그인 필요)

- 쓰기 명령은 **로그인 세션**이 있어야 한다. 없으면 `NOT_LOGGED_IN` → 사용자에게 `velogger login` 을 안내한다. 에이전트가 사용자의 글을 함부로 올리지 않는다.
- **`publish` 는 기본이 임시저장(초안)이다.** `--publish` 를 줘야 실제로 발행된다. 본문은 `--file <경로>`·`--body "..."` 중 하나로 준다. 파이프로 넘기려면 `--file -` 를 꼭 붙인다 (없으면 stdin 을 읽지 않는다). 태그는 `--tag a,b` 또는 `--tag a --tag b`.
- 발행(`--publish`)은 **신뢰 계정(`whoami` 의 `is_trusted: true`)만** 된다. 아니면 `FORBIDDEN` 으로 막히니, 그 글은 velog.io 웹에서 발행하라고 사용자에게 안내한다 (CLI 는 캡차를 풀지 않는다). 임시저장은 누구나 된다.
- `edit`·`like`·`comment`·`comments`·`stats` 는 글 **id**(목록·`post` 결과의 `id`)로 가리킨다. `edit` 은 안 준 필드는 그대로 둔다 (본문을 안 주면 본문 유지).
- 목록의 `short_description` 은 소개글이 없으면 velog 가 본문 앞부분을 잘라 채운 값이다. 소개글은 `publish`·`edit` 의 `--description`(150자까지)으로 쓴다.
- 쓰기 결과가 `UPSTREAM_ERROR` 면 **같은 쓰기를 바로 다시 보내지 않는다.** velog 가 반영 여부를 알려 주지 않은 것이라, `drafts`·`posts`·`comments` 로 반영됐는지 먼저 확인한다 (글·댓글이 두 번 생기지 않게).
- **글 삭제 명령은 없다.** 댓글 삭제(`comment-remove`)는 되돌릴 수 없어 `--yes` 가 있어야 하고, 에이전트는 사용자 확인 없이 붙이지 않는다.
- 본문에 이미지를 넣는 순서: ① `publish` 로 글을 초안으로 먼저 만든다 → ② 그 id 로 `velogger upload <파일> --post <id>` → ③ 결과의 `markdown` 을 본문에 넣어 `edit` (목록 카드의 썸네일로도 쓰려면 결과의 `url` 을 `edit --thumbnail` 로). velog 는 어느 글에 들어갈 이미지인지 모르면 업로드를 403 으로 막는다. 로컬 경로를 본문에 그대로 쓰면 이미지가 안 보인다. 올린 파일은 누구나 볼 수 있는 주소가 되므로 `upload` 는 이미지(PNG·JPEG·GIF·WebP·AVIF·SVG)만 받는다.

## 조회 읽는 법

- 목록은 글 **요약**(제목·`username`·`url_slug`·`url`·태그·좋아요 등)만 준다. **본문**이 필요하면 그 글의 `username` 과 `url_slug` 로 `velogger post <username> <url_slug>` 를 부른다 (`body` 가 마크다운).
- `url_slug` 는 받은 그대로 쓴다 (한글이 들어가기도 한다). `username` 은 `@` 없이 넣는다. slug 가 `-` 로 시작하면 옵션으로 읽히니 앞에 `--` 를 둔다: `velogger post <username> -- <url_slug>`.
- 목록은 한 번에 50건 이하로 본다 (`--limit`, 최대 100). 글 1건에 설명·메타가 길어 많이 받으면 출력이 커진다.
- `search` 는 `count`(전체 결과 수)를, `tag` 는 `count`·`next_cursor` 를 함께 준다. 다음 페이지는 `tag`·`posts`·`recent`·`liked`·`followers`·`followings` 가 `next_cursor` 를 `--cursor` 로, `search`·`trending` 은 `--offset` 으로 받는다. `next_cursor: null` 은 마지막 페이지다 (키가 없는 목록은 다음 페이지가 없다).
- **태그별 전역 글**은 `velogger tag <태그>` 로만 받는다 (`posts --tag` 는 그 사용자 글 안에서만 거른다).
- `recent` 상단엔 스팸 글이 끼기도 한다. velog 서버가 준 결과를 그대로 전하니, 거를지는 호출하는 쪽이 판단한다.
- `is_private: true` 는 비공개 글(로그인한 본인에게만 보임), `is_temp: true` 는 초안이다 (초안의 `url` 은 편집 주소).

## 에러가 나면

| code | 할 일 |
| --- | --- |
| `NOT_LOGGED_IN` | 사용자에게 `velogger login` 을 직접 실행하라고 안내한다. 에이전트가 대신 로그인하지 않는다 |
| `LOGIN_FAILED` | code 가 만료·소비됐거나 쿠키가 잘못됐다. `velogger login <이메일>` 로 새 링크를 받는다. `details.registered: false` 면 velog 계정이 없는 이메일이다: 가입된 이메일인지 사용자에게 묻는다 |
| `INVALID_ARGUMENT` | `message`·`hint` 를 읽고 `--help` 로 고친다. velog 가 거절한 값(예: 대댓글의 대댓글에 단 `--reply-to`)도 이 코드다. 같은 명령을 그대로 다시 부르지 않는다 |
| `NOT_FOUND` | 없는 글·사용자·태그다. `username`·`url_slug`·`id` 를 이전 결과에서 그대로 복사했는지 확인한다 |
| `FORBIDDEN` | `message` 로 갈린다. 캡차 이야기면 발행에 캡차가 필요한 계정이다 (`is_trusted: false`): 그 글은 웹에서 발행하라고 안내한다 (임시저장은 된다). '본인 것이 아니라'·'본인 글이 아니라' 면 남의 글·댓글·시리즈다: 내 것의 id 인지 확인한다 |
| `ALREADY_EXISTS` | 같은 slug 의 시리즈가 있거나 이미 시리즈에 든 글이다. 같은 명령을 다시 보내지 않는다 (다른 `--slug` 를 주거나 있는 것을 쓴다) |
| `RATE_LIMITED` | `retry_after_seconds` 만큼 기다린다. 바로 다시 부르지 않는다 |
| `NETWORK_ERROR` | 잠시 뒤 한 번만 다시 부른다 |
| `UPSTREAM_ERROR`, `PARSE_ERROR` | velog 가 바뀌었을 수 있다. 사용자에게 velogger 업데이트를 권한다. 쓰기였다면 다시 보내기 전에 반영 여부부터 확인한다 |
| `INTERNAL_ERROR` | 에러 JSON 을 `velogger --version` 과 함께 사용자에게 보여 준다 |
