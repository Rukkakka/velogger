# velogger 사용법

[설치](../README.md) · [공통 사용 규칙](common.md) · [개발 가이드](../references/providers/velogger.md)

> 출력 형식·에러 대응·요청 제한 같은 공통 규칙은 [공통 사용 규칙](common.md)에 있다. 이 문서는 명령별 세부를 적는다.

## 한눈에 보기

| 명령 | 하는 일 | 로그인 필요 |
| --- | --- | --- |
| `trending` | 트렌딩 글 목록 | — |
| `recent` | 최신 글 목록 | — |
| `search` | 글 검색 | — |
| `posts` | 한 사용자의 글 목록 | — |
| `post` | 글 하나 본문(마크다운)·메타 | — |
| `comments` | 글의 댓글(작성자 포함)·대댓글 | — |
| `user` | 사용자 프로필·태그·시리즈 | — |
| `series` | 시리즈 안 글을 순서대로 | — |
| `tag` | 태그별 글 목록 + 태그 설명 | — |
| `followers` / `followings` | 팔로워 / 팔로잉 목록 | — |
| `feed` | 내가 팔로우한 사람들의 글 | ✅ |
| `liked` | 내가 좋아요한 글 (`--read` 면 읽은 글) | ✅ |
| `publish` | 글 쓰기 (기본 임시저장, `--publish` 로 발행) | ✅ |
| `edit` | 내 글 고치기 | ✅ |
| `drafts` | 내 초안 목록 | ✅ |
| `like` / `unlike` | 글 좋아요 / 취소 | ✅ |
| `comment` | 댓글 달기 | ✅ |
| `comment-edit` / `comment-remove` | 내 댓글 수정 / 삭제(`--yes` 필요) | ✅ |
| `follow` / `unfollow` | 사용자 팔로우 / 끊기 | ✅ |
| `series-create` / `series-add` | 시리즈 만들기 / 글 넣기 | ✅ |
| `upload` | 이미지 올리고 본문용 URL 받기 (`--post <글id>` 필요) | ✅ |
| `stats` | 내 글 조회수 | ✅ |
| `login` | velog 에 로그인 (이메일 링크 또는 쿠키) | — |
| `logout` | 저장된 세션 삭제 | — |
| `whoami` | 로그인한 계정 확인 | — (안 돼 있으면 `logged_in: false`) |
| `limits` | 요청 제한 상태 | — |

조회는 로그인 없이 된다. 로그인돼 있으면 세션 쿠키를 함께 보내, 본인 비공개 글 등도 보인다.

## 글 목록의 공통 모양

`trending`·`recent`·`search`·`posts`·`tag` 는 글 **요약** 목록을 같은 모양으로 돌려준다.

```json
{"returned": 2, "count": 5659,
 "posts": [{"id": "...", "title": "...", "username": "ryu_log", "display_name": "...",
            "url_slug": "...", "url": "https://velog.io/@ryu_log/...", "short_description": "...",
            "thumbnail": null, "tags": ["FastAPI"], "released_at": "...", "updated_at": null,
            "likes": null, "comments_count": 2, "is_private": false, "is_temp": null}]}
```

- `returned` 는 이번에 받은 수다. `count`(전체 수)는 `search`·`tag` 에만, `next_cursor`(다음 페이지, `tag` 의 `--cursor` 로
  넘긴다)는 `tag` 에만 키가 있다. `tag` 의 `next_cursor: null` 은 마지막 페이지다.
- `is_private`·`is_temp` 는 비공개·임시저장(초안) 여부다. 초안은 공개 주소가 없어 `url` 이 편집 주소(`velog.io/write?id=...`)다.
- **본문은 요약에 없다.** 글을 읽으려면 그 글의 `username` 과 `url_slug` 로 `post` 를 부른다.
- 소스마다 빠지는 필드가 있다 (`search` 는 `updated_at`·`likes` 를 안 주고 `null`). `null` 은 모름이다.

## `trending` — 트렌딩 글

| 인자·옵션 | 설명·허용값 | 기본값 |
| --- | --- | --- |
| `--period` | 집계 기간: `day`·`week`·`month`·`year` | `week` |
| `--limit` | 받을 글 수 (최대 100) | 20 |
| `--offset` | 건너뛸 글 수 (페이지) | 0 |

```bash
velogger trending --period month --limit 10
```

## `recent` — 최신 글

`--limit` 만 받는다. 상단에 스팸 글이 끼기도 한다 — velog 서버 결과를 그대로 전하므로, 거를지는 호출하는 쪽이 판단한다.

## `search` — 글 검색

| 인자·옵션 | 설명 | 기본값 |
| --- | --- | --- |
| `KEYWORD` | 검색어 | 필수 |
| `--user` | 이 사용자(@username)의 글만 검색 | 전체 |
| `--limit` | 받을 글 수 (최대 100) | 20 |
| `--offset` | 건너뛸 글 수 (페이지) | 0 |

`count` 로 전체 결과 수를 알 수 있다. 더 보려면 `--offset` 을 `--limit` 만큼 늘린다.

## `posts` — 한 사용자의 글

| 인자·옵션 | 설명 | 기본값 |
| --- | --- | --- |
| `USERNAME` | 글쓴이 아이디 (@ 없이) | 필수 |
| `--tag` | 이 사용자 글 중 태그로 거르기 | 전체 |
| `--limit` | 받을 글 수 (최대 100) | 20 |

`--tag` 는 그 사용자의 글 안에서만 거른다. 태그로 **전역** 글을 찾으려면 `tag` 를 쓴다.

## `post` — 글 본문

| 인자 | 설명 |
| --- | --- |
| `USERNAME` | 글쓴이 아이디 (@ 없이) |
| `URL_SLUG` | 글 slug (목록의 `url_slug` 그대로. 한글이 들어가기도 한다) |

```bash
velogger post teo ai-native-fe
velogger post someone -- -회고      # slug 가 '-' 로 시작하면 앞에 -- 를 둔다 (없으면 옵션으로 읽혀 INVALID_ARGUMENT)
```

**반환값**: `body`(본문. `is_markdown: true` 면 마크다운), `title`·`tags`·`likes`·`comments_count`·`released_at`, `is_private`·`is_temp`, 속한 `series`(이름·url·시리즈 안 글), 같은 시리즈의 `previous_post`·`next_post`. 없는 글은 `NOT_FOUND`.

## `user` — 사용자

| 인자 | 설명 |
| --- | --- |
| `USERNAME` | 사용자 아이디 (@ 없이) |

**반환값**: `display_name`·`short_bio`·`thumbnail`·`url`(블로그 주소), `links`(github·url·email 등 공개 링크), `posts_count`(전체 글 수), 많이 쓴 `tags`, `series` 목록. 시리즈·태그·링크가 없으면 `[]`·`{}` 다 (`null` 은 velog 가 알려 주지 않은 경우). 글 목록 자체는 `velogger posts <username>` 로 받는다.

## `tag` — 태그별 글

| 인자·옵션 | 설명 | 기본값 |
| --- | --- | --- |
| `NAME` | 태그 이름 | 필수 |
| `--limit` | 받을 글 수 (최대 100) | 20 |
| `--cursor` | 다음 페이지 커서 (이전 결과의 `next_cursor`) | 첫 페이지 |

태그별 글 목록(공통 모양)에 더해, 첫 페이지에는 맨 앞에 `tag`(이름·설명)를 붙인다 (`--cursor` 로 받은 다음 페이지에는 붙이지 않는다). 태그 전체 글 수는 `count` 다 (velog 의 태그 정보는 글 수를 늘 0 으로 줘 내지 않는다). 다음 페이지는 결과의 `next_cursor` 를 그대로 `--cursor` 로 넘긴다. (velog 의 GraphQL 로는 태그별 글이 빈 배열로 와서 CDN 캐시를 쓴다.)

```bash
velogger tag react --limit 20
velogger tag react --limit 20 --cursor <이전 결과의 next_cursor>
```

## `comments` — 댓글 읽기

`velogger comments <글 id> [--replies]`. `id` 는 목록·`post` 결과의 `id`. **`post` 는 댓글 수만 주므로 내용은 이
명령으로 받는다** (작성자가 채워지는 v2 경로를 쓴다).

`--replies` 를 주면 대댓글이 있는 댓글마다 요청을 한 번씩 더 보내 `replies` 를 채운다 (댓글이 많으면 요청이
그만큼 늘어난다). 삭제된 댓글은 velog 가 내용을 주지 않아 `deleted: true` 로만 온다.

반환: `post_id`, `comments_count`(대댓글 포함 전체), `returned`(최상위 댓글 수), `comments[]`
(`id`·`username`·`text`·`created_at`·`replies_count`·`deleted`, `--replies` 일 때만 `replies`). `replies` 는 대댓글이
없으면 `[]` 이고, `--replies` 없이 부르면 키 자체가 없다.

## `series` — 시리즈 글 순서대로

`velogger series <username> <series_slug>`. slug 는 `user` 결과 `series[].url` 끝부분. 글을 시리즈 순서(`index`)대로
정렬해 돌려준다. 반환에 시리즈 `id` 가 있어 `series-add` 에 바로 쓸 수 있다.

## `followers` / `followings`

`velogger followers <username>` · `velogger followings <username>` (`--limit`). 각 사람의 `user_id`·`username`·
`display_name`·`short_bio`·`url` 과, 로그인했다면 `is_followed`(내가 팔로우 중인지)를 준다.

## `feed` / `liked` (로그인 필요)

- `velogger feed` — 내가 팔로우한 사람들의 최신 글
- `velogger liked` — 내가 좋아요한 글. `--read` 를 주면 읽은 글 목록

둘 다 [글 목록 공통 모양](#글-목록의-공통-모양)으로 돌려준다.

## 쓰기 명령 (로그인 필요)

`publish`·`edit`·`drafts`·`like`·`unlike`·`comment`·`stats` 는 저장된 로그인 세션이 있어야 한다. 없으면
네트워크 없이 바로 `NOT_LOGGED_IN` 으로 막고, 사용자가 `velogger login` 을 직접 실행하라고 안내한다. 글 삭제
명령은 두지 않는다.

### `publish` — 글 쓰기

| 인자·옵션 | 설명 | 기본값 |
| --- | --- | --- |
| `TITLE` | 글 제목 | 필수 |
| `--body` / `--file` | 본문 (마크다운). 둘 중 하나. `--file -` 면 stdin(파이프)에서 읽는다 | 필수 |
| `--tag` | 태그 (반복 또는 쉼표) | 없음 |
| `--series-id` | 넣을 시리즈 ID (`user` 결과의 series) | 없음 |
| `--slug` | url_slug | 제목에서 생성 |
| `--thumbnail` | 썸네일 이미지 URL | 없음 |
| `--private` | 비공개로 저장 | 공개 |
| `--publish` | **실제로 발행** (없으면 임시저장/초안) | 임시저장 |
| `--markdown / --no-markdown` | 본문이 마크다운인지 | 마크다운 |

```bash
velogger publish "제목" --file post.md --tag python,velog          # 초안
velogger publish "제목" --file post.md --tag python --publish       # 발행
cat post.md | velogger publish "제목" --file - --publish            # 파이프 (--file - 를 꼭 준다)
```

**발행은 신뢰 계정만 된다.** `whoami` 의 `is_trusted` 가 `false` 면 발행에 캡차(Cloudflare Turnstile)가 붙어
`FORBIDDEN` 으로 막힌다. CLI 는 캡차를 풀지 않으니 그 글은 velog.io 웹에서 발행한다. 임시저장은 캡차가 없어
누구나 된다. 반환값은 `id`·`url_slug`·`url`(발행 시)·`status`(`published`/`draft`)·`is_private`.

stdin 은 `--file -` 를 줬을 때만 읽는다. 본문 옵션 없이 파이프만 연결하면 `INVALID_ARGUMENT` 다 (닫히지 않는 stdin 을
물려받은 셸에서 멈추지 않게). 본문 파일·stdin 은 UTF-8 이어야 하고(아니면 `INVALID_ARGUMENT`), 맨 앞의 BOM(Windows
PowerShell 5·옛 메모장이 붙인다)은 떼고 읽는다.

**쓰기 결과가 `UPSTREAM_ERROR` 면 바로 다시 보내지 않는다.** velog 는 반영하지 못한 쓰기도 에러 없이 빈 결과만 주기도
해서, CLI 는 그때 `UPSTREAM_ERROR` 를 낸다. 반영됐는지 모르므로 `drafts`·`posts`·`comments` 로 먼저 확인한 뒤 다시
보낸다 (글·댓글이 두 번 생기지 않게).

### `edit` — 내 글 고치기

`velogger edit <id> [옵션]`. `id` 는 `posts`·`drafts` 결과의 `id`. **안 준 필드는 현재 값을 그대로 둔다** (본문을
안 주면 본문이 유지되고, 속한 시리즈·요약(short_description)도 그대로다). `--title`·`--body`/`--file`·`--tag`·`--slug`·`--private`/`--public`·`--publish`(초안을
발행 상태로, 신뢰 계정만)를 받는다. 신뢰 계정이 아니면 **이미 발행된 글은 `--publish` 없이도 고칠 수 없다** (velog 웹도
발행된 글을 고칠 때 캡차를 띄운다). 그때는 `FORBIDDEN` 이니 velog.io 웹에서 고친다. 남의 글 id 를 주면 고치지 않고
`FORBIDDEN`('본인 글이 아니라') 이다. velog 가 글의 발행·공개 상태를 주지 않으면 추측해 덮어쓰지 않고 `PARSE_ERROR` 로 멈춘다
(모르는 채 보내면 발행된 글이 초안이 되거나 비공개 글이 공개될 수 있다).

### `drafts` — 내 초안

내 임시저장 글을 [글 목록 공통 모양](#글-목록의-공통-모양)으로 돌려준다. `--limit` 만 받는다.

### `like` / `unlike` — 좋아요

`velogger like <id>` / `velogger unlike <id>`. `id` 는 목록·`post` 결과의 `id`. 반환값은 `id`·`likes`(현재 수)·
`liked`(내 상태).

### `comment` — 댓글

`velogger comment <id> "<내용>" [--reply-to <comment_id>]`. 글에 댓글을, `--reply-to` 로 대댓글을 단다.

### `comment-edit` / `comment-remove` — 내 댓글 수정·삭제

```bash
velogger comment-edit <댓글 id> "고친 내용"
velogger comment-remove <댓글 id> --yes
```

댓글 id 는 `comments` 결과의 `id`. **삭제는 되돌릴 수 없어 `--yes` 가 없으면 거부**한다. 빈 내용으로는 고치지 않는다
(`INVALID_ARGUMENT`. velog 는 빈 댓글로 저장한다).

### `follow` / `unfollow` — 팔로우

`velogger follow <username>` · `velogger unfollow <username>`. velog API 는 사용자 ID 를 받으므로 CLI 가 username 을
ID 로 바꿔서 보낸다 (요청이 한 번 더 간다). 반환은 `username`·`user_id`·`is_followed`.

### `series-create` / `series-add` — 시리즈

```bash
velogger series-create "내 시리즈"            # id 를 돌려준다
velogger series-add <시리즈 id> <글 id>        # 시리즈 맨 뒤에 넣는다
```

`publish --series-id <id>` 로 글을 쓸 때 바로 넣을 수도 있다. slug 를 안 주면 이름에서 만든다. 반환은 `series-create` 가
`id`·`name`·`url_slug`, `series-add` 가 `series_id`·`post_id`·`added`.

같은 slug 의 시리즈가 이미 있거나(`series-create`), 이미 그 시리즈에 든 글이면(`series-add`) `ALREADY_EXISTS` 다. 다시
보내도 결과가 같으니 다른 `--slug` 를 주거나 이미 있는 것을 쓴다. 이름이 비면 `INVALID_ARGUMENT` 다.

### `upload` — 이미지 올리기

`velogger upload <파일 경로> --post <글 id>`. velog 에 이미지를 올리고 `url` 과, 본문에 그대로 붙여 넣을 수 있는
마크다운 이미지 문법 문자열(`markdown` 필드)을 준다.

**`--post` 는 필수다.** velog 는 어느 글에 들어갈 이미지인지(`ref_id`) 모르거나 그 글이 내 글이 아니면 업로드를 403
으로 막는다 (CLI 는 `FORBIDDEN`). 웹 에디터도 글을 초안으로 먼저 저장해 id 를 받은 뒤에 이미지를 올린다. 그래서 순서는 이렇다.

```bash
velogger publish "제목" --body "임시"                 # ① 초안을 만들고 id 를 받는다
velogger upload a.png --post <id>                     # ② 그 id 로 이미지를 올린다 → markdown
velogger edit <id> --file post.md                     # ③ markdown 을 넣은 본문으로 고친다
velogger edit <id> --publish                          # ④ (원하면) 발행
```

본문에 로컬 경로를 쓰면 이미지가 안 보인다.

**이미지(PNG·JPEG·GIF·WebP·AVIF·SVG)만 올린다.** velog 는 받은 파일의 형식을 보지 않고 누구나 받을 수 있는 주소로 올리므로,
CLI 가 확장자가 아니라 파일 내용으로 이미지인지 보고 아니면 네트워크 요청 없이 `INVALID_ARGUMENT` 로 막는다 (SVG 는 맨 앞이
`<svg` 요소인지 본다).

### `stats` — 내 글 조회수

`velogger stats <id>`. 본인 글의 `total`(전체 조회수)을 돌려준다. 본인 글만 되고, 남의 글이면 `FORBIDDEN` 이다.

> `count_by_day`(일별 조회수)는 **velog 서버가 현재 빈 배열로 돌려준다** (서버 쪽이 그렇게 되어 있다). CLI 가
> 빠뜨리는 게 아니라 받을 수 없는 값이다.

## `login`

velog 는 **비밀번호가 없다.** 가입을 이메일로 했든 깃허브·구글로 했든, 로그인 수단은 (1) 계정 이메일로 오는 매직 링크, (2) 소셜 로그인이다. CLI 는 이메일 링크로 로그인하거나, 브라우저에서 복사한 쿠키를 받는다.

로그인 code 와 쿠키는 계정의 열쇠다. CLI 는 이 값을 화면에 출력하지 않고, 세션 파일에만 사용자 전용 권한으로 저장한다.

### 이메일 로그인 (기본)

```bash
velogger login you@example.com          # 1) velog 가 그 주소로 로그인 링크를 보낸다
# 2) 메일 속 링크를 복사한다 (브라우저로 열지 말 것). 예: https://velog.io/email-login?code=abcd1234
velogger login --code 'https://velog.io/email-login?code=abcd1234'   # 3) 세션 저장
```

- `--code` 에는 링크 전체를 붙여넣어도 되고 `code` 값만 줘도 된다.
- 깃허브 등 소셜로 가입한 계정도, 그 계정 이메일로 로그인 링크가 온다.
- 링크(code)는 일회용이고 금방 만료된다. 실패하면 `velogger login <이메일>` 로 새로 받는다.

### 쿠키 붙여넣기 (대체)

브라우저에서 velog 에 로그인한 상태라면, 개발자도구 → Application → Cookies → `https://velog.io` 의 쿠키를 복사해 넘긴다.

```bash
velogger login --cookie 'access_token=...; refresh_token=...'
```

### 반환값

로그인에 성공하면 `whoami` 와 같은 형식(`logged_in`, `username`, `is_trusted`)을 돌려준다. 이메일만 보낸 단계(`velogger login <이메일>`)에서는 `email`, `registered`, 다음에 할 일 `message` 를 돌려준다.

### 오류와 대응

| code | 뜻 |
| --- | --- |
| `LOGIN_FAILED` | code 가 없거나(404) 이미 쓰였거나(403) 24시간이 지났거나(410), 쿠키가 잘못됨. 새 링크를 받는다 |
| `INVALID_ARGUMENT` | `--code`/`--cookie` 형식이 맞지 않음 |

## `logout`

세션 파일을 지운다 (로컬에서만. velog 서버의 로그인은 그대로다). `logged_out`(지웠는지)과 `session_path` 를 돌려준다.

## `whoami`

지금 로그인한 계정을 보여 준다. 로그인 안 했으면 `logged_in: false`.

| 필드 | 의미 |
| --- | --- |
| `logged_in` | 로그인 여부 |
| `username` | velog 아이디 (@username) |
| `is_trusted` | 신뢰 계정 여부. `false` 면 글 발행에 캡차가 붙어 CLI 로는 발행할 수 없다 |

계정 이메일·사용자 ID 는 velog 가 알려 줘도 내보내지 않는다 (로그인 정보는 로그인 여부·`username`·`is_trusted` 만).

## `limits`

요청 제한 상태를 본다 (네트워크 요청 없음). `--reset` 으로 로컬 쿨다운·요청 기록을 초기화한다. 자세한 정책은 [공통 사용 규칙](common.md#요청-제한과-limits)에 있다.
