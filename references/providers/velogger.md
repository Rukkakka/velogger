# velogger 개발 가이드

[CLI 사용법](../../docs/velogger.md) · [개발 환경·검증](../development.md) · [공통 아키텍처](../architecture.md) · [provider 작성 규약](../provider-conventions.md) · [출력 계약](../output-contract.md) · [코드 형식](../code-style.md)

공통 규약에 없는, velog 에만 있는 구현과 예외를 적는다. 엔드포인트·해시는 velog 웹 번들에서 꺼냈고,
사이트가 바뀌면 조용히 깨질 수 있으니 바꾸기 전에 실제 응답으로 확인한다.

## 서버

velog 는 프론트가 둘(Next.js 신(新) 클라이언트 + CRA 구(舊) 클라이언트)이고, 백엔드도 여럿이다.

| 호스트 | 종류 | 쓰는 곳 |
| --- | --- | --- |
| `v2.velog.io` | REST + GraphQL | 로그인(`/api/v2/auth/*`), `auth`(is_trusted), 글쓰기·댓글·좋아요·통계, 댓글 작성자·대댓글 |
| `v3.velog.io` | GraphQL | 공개 조회 대부분 (trendingPosts, recentPosts, searchPosts, post, user, userTags 등) |
| `cache.velcdn.com` | REST (CDN 캐시) | `trending-posts`, `tag-posts` (태그별 글은 GraphQL 로는 빈 배열이라 여기서 받는다) |

이미지·프로필 등 정적 파일은 `velog.velcdn.com`. 조회는 로그인 없이 되고, 쓰기·`auth`·`getStats` 는 세션 쿠키가 필요하다.

## 명령과 요청 흐름

| CLI 명령 | 주요 경로 | service 모듈 |
| --- | --- | --- |
| `login`·`logout`·`whoami` | v2 `/api/v2/auth/sendmail`·`/code/{code}` → v2 GraphQL `auth` | `auth` |
| `trending` | 캐시 `/api/trending-posts` | `posts` |
| `recent` | v3 `recentPosts` | `posts` |
| `search` | v3 `searchPosts` | `posts` |
| `posts` | v3 `posts`(username) | `posts` |
| `tag` | 캐시 `/api/tag-posts` + v3 `tag` | `posts`(목록)·`users`(태그 정보) |
| `post` | v3 `readPost` (본문). 댓글 내용은 `comments` 로 따로 | `post` |
| `comments` | v2 `ReloadComments`(+`--replies` 면 `ReloadReplies`) — 작성자가 채워지는 쪽 | `social` |
| `user` | v3 `user` + `userTags` (한 쿼리) | `users` |
| `series` | v2 `Series(username, url_slug)`, `index` 로 정렬 | `social` |
| `followers`·`followings` | v3 `getFollowers`·`getFollowings` | `social` |
| `feed`·`liked` | v3 `feedPosts` · v2 `readingList(LIKED/READ)` (로그인) | `social` |
| `publish`·`edit`·`drafts`·`like`·`unlike`·`comment`·`stats` | v2 `writePost`·`editPost`·`ReadPostForEdit`·`posts(temp_only)`·`likePost`·`unlikePost`·`writeComment`·`getStats` | `write` |
| `comment-edit`·`comment-remove`·`follow`·`unfollow`·`series-create`·`series-add`·`upload` | v2 `editComment`·`removeComment`·`follow`·`unfollow`·`createSeries`·`appendToSeries` · REST `/api/v2/files/upload` | `write` |

## 로그인 (`auth`)

velog 는 비밀번호가 없다. 흐름:

1. `POST v2.velog.io/api/v2/auth/sendmail {email}` → velog 가 그 이메일로 링크를 보낸다. 응답 `{registered}`
   (true 면 기존 계정 → 로그인 링크, false 면 가입 링크). 깃허브 등 소셜 가입 계정도 그 계정 이메일로 로그인
   링크가 온다 (2026-10-18 실측).
2. 메일의 링크는 `velog.io/email-login?code=<code>`. `code` 는 일회용이고 금방 만료된다.
3. `GET v2.velog.io/api/v2/auth/code/{code}` → velog 가 세션 쿠키를 Set-Cookie 로 준다. httpx 가 쿠키 자에
   담고, service 가 `current_cookies()` 로 `session.json` 에 저장한다. 실패는 셋이고 service 가 모두 `LOGIN_FAILED` 로
   바꾼다 (그대로 두면 '내려간 글'·'차단된 요청'·'스펙 변경' 힌트가 된다).

   | 상태 | 뜻 (velog-server `routes/api/v2/auth/index.ts`) |
   | --- | --- |
   | 404 | 없는 code (2026-10-20 실측) |
   | 403 + `{"name": "TOKEN_ALREADY_USED"}` | 이미 쓴 code. 브라우저로 링크를 열어도 쓰인다 (2026-10-20 실측: 로그인에 쓴 링크를 다시 넣음) |
   | 410 + `{"name": "EXPIRED_CODE"}` | 24시간 지난 code (소스 기준. 이미 쓴 code 는 날짜보다 먼저 403 이 된다) |

   본문이 `TOKEN_ALREADY_USED` 가 아닌 403(앞단 차단 페이지 등)은 `FORBIDDEN` 으로 둔다. 예전 문서는 "다 쓴 code 도 404"
   라 했는데 틀렸다 (실측 403). 410 은 쓰지 않은 채 24시간 지난 링크가 있어야 확인할 수 있어 아직 실측하지 않았다.

   성공(200)은 둘이다 (소스 기준, 가입 메일을 실제로 보내야 해 실측하지 않았다). 가입된 이메일이면 쿠키를 Set-Cookie 로
   주고 본문에 사용자(`...user`, `profile`, `tokens`)를 담으며, **이때 code 를 쓴 것으로 표시한다**(`emailAuth.logged`).
   계정이 없는 이메일이면 쿠키 없이 `{email, register_token}` 만 주고 code 는 쓰지 않는다. 그래서 service 는
   - 쿠키를 받자마자 `session.json` 에 저장한 뒤 `auth` 로 확인한다. 확인 요청이 실패했다고 쿠키를 버리면 같은 링크는 403
     이라 메일을 새로 받아야 한다. 확인만 실패하면(5xx·네트워크·요청 제한) 로그인 응답 본문의 `username`·`is_trusted` 로
     결과를 낸다 (`is_trusted` 는 소스의 User 엔티티에 없어 `null` 일 수 있다). 본문의 토큰은 모델에 담지 않는다
     (`VelogCodeLoginResponseModel` 은 `extra='ignore'`).
   - 쿠키 없이 `register_token` 이 오면 '만료됐을 수 있다' 가 아니라 가입 링크라고 `LOGIN_FAILED`(`details.registered:
     false`)로 알린다. 새 링크를 받아도 또 가입 링크가 와 되풀이되기 때문이다.
   - code 는 **URL 경로**에 실려 쿼리를 지워서는 가려지지 않는다. `core/http.py` 의 `SENSITIVE_PATH_PATTERN` 이
     에러 메시지·재시도 로그에서 `/auth/code/<redacted>` 로 가린다 (2026-10-20 확인: 가리기 전에는 에러 JSON 에 찍혔다).
     `--verbose` 가 켜는 httpx 요청 로그도 `SensitivePathLogFilter` 가 가린다 (같은 날 재현: 502 재시도마다 code 가 한 줄씩 찍혔다).
   - code 는 shortid(`0-9A-Za-z_-`, `.` 도 받아 둠)만 받는다. 링크에서 URL 디코드한 `..%2F..%2Fposts` 가 경로에 들어가
     요청이 `/api/v2/posts` 로 갔다 (2026-10-20 재현). client 도 code 를 `quote(safe='')` 로 넣는다.

- **사용자의 code·쿠키를 에이전트가 대신 다루지 않는다.** CLI 로그인은 사용자가 자기 터미널에서 실행한다.
- 소셜 로그인(`/api/v2/auth/social/redirect/github`, v3 `/api/auth/v3/social/redirect/{google,facebook}`)은
  콜백이 velog 로 돌아가 CLI 가 헤드리스로 가로챌 수 없다. 대체로 `--cookie` 붙여넣기를 둔다.
- **토큰 갱신:** access_token 은 1시간, refresh_token 은 30일이다 (2026-10-20 JWT `exp` 확인). 요청 응답의
  Set-Cookie 로 새 토큰이 오면 쿠키 자에 반영되므로, 인증 요청 **뒤** `current_cookies()` 로 세션을 다시 저장한다.
  `login --cookie` 도 `auth` 응답을 받은 뒤에 쿠키를 읽어 저장한다 (먼저 읽으면 붙여넣은 만료 토큰이 저장된다).
  어느 요청이 토큰을 스스로 갱신하는지는 아래 [토큰 갱신과 require_auth](#토큰-갱신과-require_auth).

### whoami 와 is_trusted

로그인 사용자 조회는 **v2 GraphQL `auth`** 를 쓴다 (`{ auth { id username email is_trusted profile {...} } }`).
`is_trusted` 는 v2 `auth` 에만 있고 v3 `currentUser` 에는 없어서 v2 를 쓴다. 로그인 안 했으면 `data.auth` 가
null (또는 `errors` 에 `UNAUTHENTICATED`) — 둘 다 "로그인 안 됨" 으로 본다. 응답의 `id`·`email` 은 받아도
출력하지 않는다 (`whoami`·`login` 결과는 `logged_in`·`username`·`is_trusted` 만, AGENTS.md '꼭 지킬 것').

## 조회

service 는 v3 GraphQL·캐시 응답을 공통 요약 모델(`VelogPostSummary`, `service/common.py`)로 정규화하고, 글
주소를 `https://velog.io/@{username}/{url_slug}` 로 만든다. GraphQL 봉투의 `errors` 는 `graphql_data()` 가
판정한다 (UNAUTHENTICATED → `NOT_LOGGED_IN`, 그 밖 → `UPSTREAM_ERROR`).

- **trendingPosts / recentPosts / searchPosts / posts(username)** 는 v3 GraphQL (`recent`·`search`·`posts`).
  `searchPosts` 는 `{count, posts}`. 트렌딩은 아래 캐시를 쓴다. 목록 필드는 `id, title, short_description,
  thumbnail, user{username, profile}, url_slug, released_at, tags, likes, comments_count, is_private` 정도이고
  소스마다 일부가 빠진다 (실측: `searchPosts` 는 `updated_at`·`likes` 를 안 준다).
- **글 본문**은 v3 `readPost(username, url_slug)` → `body`(마크다운, 실측 수만 자), `series`, `linked_posts`
  (이전/다음). 글이 없으면 `post` 가 null → `NOT_FOUND`. (실측: `series.series_posts` 가 null 로 오기도 한다.)
  ⚠️ **로그인한 본인이 시리즈에 든 자기 글을 읽으면 v3 가 HTTP 500 을 준다** (2026-10-21 실측: 본인 계정의
  공개 시리즈 글을 세션을 실어 부르면 500, 익명이면 200. 남의 시리즈 글은 로그인해도 200). 본문은 `errors` 의 prisma
  `seriesPost.findMany()` `orderBy` 검증 오류(`path: ["post", "series", "series_posts"]`)이고 `data.post` 는
  `series_posts: null` 로 함께 오는 정상 GraphQL 봉투다. velog 쪽 버그라, client 는 이 500 을 에러로 올리지 않고 봉투를
  돌려주고(`run_request_read_post` 의 `keep_partial`, 다시 보내도 같아 재시도하지 않는다), service 는 `errors` 가 모두 그
  경로일 때만 받은 글을 `series.posts: null` + `notes` 로 낸다 (`read_post`). 그 밖의 errors 는 그대로 판정한다. 고치기 전에는
  내 시리즈 글을 로그인한 채로 아예 읽을 수 없었다 (`UPSTREAM_ERROR`). 같은 날 실측으로 익명·남의 글에서도 v3 는
  `series_posts`·`linked_posts` 를 null 로 줘, 결과는 `notes` 한 줄만 다르다.
- **user** 는 v3 `user` + `userTags` 를 **한 쿼리의 두 변수**(`$input: GetUserInput!`, `$tagsInput: UserTagsInput!`)로
  받아 요청을 한 번에 끝낸다. `profile.profile_links` 는 빈 값을 걸러 `links` 로 낸다. `userTags.tags` 는 사용자가
  쓴 태그를 모두 줘 길 수 있다 (teo 실측 약 160개). 글 목록 자체는 `posts` 명령으로 받는다.
- **trending** 은 캐시 REST `cache.velcdn.com/api/trending-posts?timeframe=&limit=&offset=` (응답은 글 카드의
  평탄한 **배열**, camelCase).
- **tag(name)** 은 태그 이름·설명(v3). 단 **태그별 글 목록**은 GraphQL(`posts(tag:...)`)이 v2·v3 모두 빈
  배열이고 `tag.posts_count` 도 0 으로 오므로, 캐시 REST `cache.velcdn.com/api/tag-posts?tag=&limit=&cursor=` 를
  쓴다 (camelCase: `urlSlug`, `shortDescription`, `nextCursor`). `tag` 명령은 이 둘을 합쳐 낸다. 전체 글 수는 캐시의
  `count` 로만 내고 `tag.posts_count` 는 출력하지 않는다 (2026-10-20 실측: react 가 `posts_count: 0` 옆에 `count: 56891`).
- **목록의 `count`·`next_cursor`** 는 그 값을 주는 명령에만 키가 있다 (`count` 는 search·tag, `next_cursor` 는 tag 와 커서로
  이어 받는 posts·recent·liked·followers·followings). 늘 `null` 로 내면 '마지막 페이지(`next_cursor: null`)' 와 구별되지 않았다.
- **한 번에 받는 수의 서버 상한과 커서** (2026-10-23 실측, `limit=100` 을 보내 본 수):

  | 목록 | 상한 | 커서 | CLI |
  | --- | --- | --- | --- |
  | v3 `posts`(한 사용자) | **50** (velog-server `findPostsByUserId` 의 `Math.min(50, size)`). **`tag` 로 거르면 limit 을 무시하고 늘 20** | 마지막 글 `id` | `posts` — 상한보다 큰 `--limit` 은 나눠 받고, 많이 오면 `--limit` 만큼만 남긴다 |
  | v3 `recentPosts` | 100 | 마지막 글 `id` | `recent` |
  | v3 `followers`·`followings` | 100 | 마지막 사람의 **팔로우 관계 `id`** (`userId` 를 주면 404 `Invalid cursor`) | `followers`·`followings` |
  | v2 `readingList` | 100 (넘으면 `BAD_REQUEST` 'Max limit is 100') | 마지막 글 `id` (READ 실측, LIKED 는 소스 기준) | `liked` |
  | v2 `posts(temp_only)` | 100 (소스 기준) | 소스상 커서는 `released_at`, 정렬은 `created_at` | `drafts` — 커서 없음 |
  | v3 `feedPosts` | 확인 못 함 | 확인 못 함 (피드가 빈 계정) | `feed` — 커서 없음 |
  | v3 `searchPosts`·캐시 trending·tag-posts | 99·100·90 (search·tag 는 서버가 거른 듯 100 아래) | offset·offset·`nextCursor` | `search`·`trending`·`tag` |

  예전에는 `posts` 에 커서가 없어 `posts --limit 100` 이 말없이 50개만 줬고 (lcs3947 의 글 64개 중 50개), `--tag` 를 주면
  `--limit 4` 에 20개가 오고 `--limit 100` 은 20개에서 끝났다 (python 글 32개). 커서를 주는 목록의
  `next_cursor` 는 velogger 가 만든다: 요청한 수보다 적게 오면 마지막 페이지(`null`), 꽉 차면 마지막 항목의 커서
  (`service/common.py` 의 `collect_pages`). 그래서 `*_PAGE_SIZE` 는 서버 상한보다 크면 안 된다 — 크면 상한만큼 온 첫 페이지를
  마지막으로 읽는다. `drafts`·`feed` 에 커서가 없는 것은 확인하지 못해서다 (확인하지 않은 커서는 글을 건너뛰거나 되풀이해도
  알 수 없다). "목록이 100개 넘게 못 받는다" 는 지적은 이 둘에만 남은 의도된 한계다.
- **목록의 `is_temp`** 는 v3 `posts`·`recentPosts`·`feedPosts`, v2 `readingList`·`posts(temp_only)` 가 준다 (2026-10-20
  실측. `searchPosts` 는 null 을, 캐시 trending·tag-posts 는 키 자체를 안 준다). 초안의 공개 주소는 404 라
  (`drafts` 가 준 주소로 `post` 를 부르면 `NOT_FOUND`) 초안의 `url` 은 편집 주소 `velog.io/write?id=` 다.
- 조회 클라이언트도 로그인돼 있으면 세션 쿠키를 함께 보낸다 (본인 비공개 글 등). 쿠키가 없으면 공개 조회만 된다.

## 쓰기 (v2 GraphQL, 세션 필요)

`service/write.py`. 모두 세션 쿠키로 보내고, 로그인 안 됨은 200 안의 `errors`(UNAUTHENTICATED)로 와
`graphql_data()` 가 `NOT_LOGGED_IN` 으로 바꾼다. CLI 는 세션이 아예 없으면 네트워크 없이 먼저 막는다
(`_session_client(login_required=True)`). 명령이 끝나면 CLI 가 **결과를 먼저 내보낸 다음** 갱신된 쿠키를 다시 저장한다
(`_session_client` 를 나갈 때 `_persist`, 토큰 회전). 서비스가 에러를 냈거나 결과를 쓰다 stdout 이 닫혀도(`| head`) 저장한다
— `require_auth` 가 이미 토큰을 갱신했을 수 있다. 세션 쿠키를 실은 조회(`whoami`·`post`·`comments` 등)도 같다 — velog 는 access_token 이 30분 아래로
남은 요청이면 조회에도 새 토큰을, refresh_token 이 23일 아래로 남으면 새 refresh_token 도 Set-Cookie 로 준다 (velog-server
`consumeUser`·`refreshUserToken`. 2026-10-21 실측: access_token 을 뺀 세션으로 `comments`·`whoami` 를 부르니 두 쿠키가
와 저장됐다). 예전에는 조회 뒤에 저장하지 않아, 조회만 쓰는 사용자는 로그인 30일 뒤 refresh_token 이 만료됐다. 세션 없이
보낸 조회는 저장하지 않는다. 저장이 실패해도(샌드박스·읽기 전용 폴더) 명령은 성공으로 끝나고 `--verbose` 로그에만 남는다 —
서버는 이미 처리했으므로 결과를 버리면 에이전트가 같은 쓰기를 다시 보내 글이 중복된다 (2026-10-20 재현). 쿠키가 처음 실은
그대로면 다시 쓰지 않는다 — 늘 쓰면 동시에 돈 다른 velogger 가 갱신해 저장한 토큰을 옛 토큰으로 덮는다. velog 가 쿠키를
모두 지웠을 때도 쓰지 않는다 — v3 는 토큰이 잘못됐다고 보면 빈 Set-Cookie 로 쿠키를 지우는데(2026-10-21 실측: 가짜 토큰
세션으로 `recent` 를 부르니 쿠키가 모두 지워졌고 v2 `comments`·`whoami` 는 지우지 않았다), 그대로 쓰면 일시적인 판정에도
세션 파일이 빈다. 세션은 `logout` 으로만 지운다. 명령이 도는 사이 세션 파일이 처음 읽은 때와 달라졌어도 쓰지 않는다 — 다른
터미널의 `logout`·다른 계정 `login`, 먼저 끝난 다른 velogger 의 저장이다. 예전에는 덮어서 로그아웃이 풀렸다 (2026-10-23 재현:
access_token 을 뺀 세션 사본으로 `whoami` 를 부르는 도중 logout 하니, 끝날 때 새 토큰으로 session.json 이 되살아났다). 세션이
없으면 `whoami` 는 velog 에 묻지 않고 `logged_in: false` 다.

- **글쓰기·수정**은 `writePost`/`editPost` (`title, body, tags, is_markdown, is_temp, is_private, url_slug,
  thumbnail, meta, series_id, token`). 임시저장은 `is_temp: true`(기본), 발행은 false. `url_slug` 를 안 주면
  제목에서 만든다 (`slugify`, 한글 slug 허용, 앞뒤 `.` 은 뗀다). **편집은 먼저 `ReadPostForEdit(id)` 로 현재 값을
  읽어 안 바꾼 필드를 채운 뒤** `editPost` 로 보낸다 (본문 등이 지워지지 않게).
- ⚠️ **`editPost` 는 보낸 값으로 글을 통째로 덮는다.** `series_id` 를 null 로 보내면 글이 시리즈에서 빠지고, `meta` 를
  `{}` 로 보내면 사용자가 쓴 요약(`meta.short_description`)이 본문에서 뽑은 요약으로 바뀐다 (2026-10-20 실측: 비공개
  테스트 글의 제목만 고쳤는데 시리즈에서 빠졌다). 그래서 `ReadPostForEdit` 가 `series { id }`·`meta` 까지 읽고 그대로
  돌려보낸다. 편집 전에 `require_auth` 부터 부른다 — 세션이 무효하면 `ReadPostForEdit` 가 익명 조회가 돼 본인 초안이
  null 로 오고, 그러면 `NOT_LOGGED_IN` 대신 `NOT_FOUND` 가 나간다.
- **`ReadPostForEdit`(`post(id)`)는 남의 공개 글도 준다** (2026-10-21 실측. velog-server 리졸버는 초안·비공개만 본인으로
  거른다). 그대로 `editPost` 를 보내면 v2 가 거절을 삼켜 null → '반영됐는지 확인하라' 는 `UPSTREAM_ERROR` 가 나가므로, `user { id }`
  를 같이 읽어 `require_auth` 의 id 와 다르면 보내지 않고 `FORBIDDEN` 이다. 글쓴이를 velog 가 안 주면 막지 않는다 (velog 가
  거절할 뿐 바뀌는 것이 없다).
- **바꾸지 않을 칸의 현재 값을 모르면 `editPost` 를 보내지 않는다** (`PARSE_ERROR`, 메시지에 빠진 칸 이름). 대상은
  `is_temp`·`is_private`·`title`·`body`·`tags`·`url_slug`·`is_markdown`·`meta` 다 (사용자가 옵션으로 준 칸은 빼고). 예전에는
  `is_temp: null` 이면 초안(`true`), `is_private: null` 이면 공개(`false`)로 추측해 발행된 글이 초안이 되거나 비공개 글이
  공개될 수 있었고, 본문·제목은 `''`, 태그는 `[]`, `meta` 는 `{}`, slug 는 제목에서 새로 만들어 보내 본문·태그·요약이 지워지거나
  글 주소가 바뀔 수 있었다. `thumbnail`·시리즈만 null 이 '없음' 이라 그대로 보낸다. velog-server 스키마(`entity/Post.ts`)로는
  모두 NOT NULL 이고 실측으로도 늘 왔다 (2026-10-21 내 글·초안, 2026-10-23 내 공개 글·velopert 의 2018년 글. `meta` 는 `{}` 이거나
  `short_description`·`code_theme` 가 든 객체). 그러니 "null 이 오지 않는데 왜 막느냐" 는 지적은 오탐이다 — 오지 않아야 정상이고,
  왔을 때 되돌릴 수 없어서 막는다.
- ⚠️ **`writePost`·`editPost` 는 값이 없는 인자도 null 로 반드시 보낸다 (`exclude_none` 금지).** v2 의 writePost 는
  껍데기라 받은 인자를 그대로 내부 v3 의 `WritePostInput` 으로 넘기는데(`postService.write`), `thumbnail`·
  `series_id`·`meta`·`token` 키가 **빠지면 내부 v3 가 거절**하고 v2 는 그 에러를 `catch` 로 삼켜 HTTP 200 에
  `{"data":{"writePost":null}}` 만 준다 — 에러 메시지가 전혀 안 보여 원인을 찾기 어렵다.
  (2026-10-19 실측: 네 키를 빼면 계속 null, 웹 CRA 처럼 11개 키를 다 보내니 바로 저장됨. 같은 세션에서
  `likePost`·`getStats` 는 정상이라 인증·프록시 문제가 아니라 **입력 문제**로 좁힐 수 있었다.)
- **발행 캡차(Turnstile).** `writePost` 는 `token`(Turnstile) 인자를 받지만, 웹은 **`auth.is_trusted` 가 false 인
  계정에만** 캡차를 띄운다 (sitekey `0x4AAAAAAARRng9sFKpsJomI`). 신뢰 계정은 token 없이 발행되므로 CLI 는
  token 을 보내지 않는다. 신뢰 계정이 아닌데 발행하려 하면(`is_temp=False`) `_check_can_publish` 가 `require_auth`
  결과의 is_trusted 를 보고 `FORBIDDEN` 으로 막는다 (캡차를 풀지 않는다). 임시저장은 캡차가 없어 통과시킨다.
  - **이미 발행된 글의 `edit` 도 막는 것은 일부러다.** 웹도 발행된 글을 고칠 때 `is_temp: false` + Turnstile token 으로
    `editPost` 를 보내고, 캡차는 `!is_trusted` 면 켜진다 (velog-client `PublishActionButtonsContainer`·`TurnstileProvider`,
    2026-10-20 확인). "신뢰 계정이 아니면 발행된 글을 아예 못 고친다" 는 지적은 웹과 같은 동작이라 오탐이다. 다만 그때는
    `--publish` 를 빼도 같은 에러라, 힌트를 '임시저장은 된다' 가 아니라 '웹에서 고치라' 로 따로 둔다.
- **임시글 목록**은 v2 `posts(username, temp_only: true)` (`drafts`). username 은 `require_auth` 로 얻는다.
- **좋아요** `likePost`/`unlikePost` → `{id, likes, liked}`. **댓글** `writeComment(post_id, text, comment_id?)`.
  대댓글은 **level 2 까지**다: 대댓글(level 1)에 다시 달 수 있고, level 2 에 달면 errors `BAD_REQUEST` 'Maximum comment
  level is 2' (2026-10-21 실측, velog-server `writeComment` 와 같다). `graphql_data()` 는 `BAD_REQUEST` 를 '다시 보내도
  같다' 는 `INVALID_ARGUMENT` 로 바꾼다 (velog-server 의 `BAD_REQUEST` 는 모두 입력 오류다: 'Max limit is 100' 등).
  `comments --replies` 는 `ReloadReplies` 에서 `replies` 를 한 번 더 중첩해 한 요청으로 level 2 까지 받는다. velog 는
  공백만 있는 댓글도 그대로 저장한다 (2026-10-21 실측: `"   "` 이 저장됐다) — 요청 모델이 `NonBlankStr` 로 막는다.
  **통계** `getStats(post_id)` → `{total, count_by_day}` (본인 글만). 글 삭제(`removePost`)는 넣지 않는다. 댓글
  삭제(`comment-remove`)는 되돌릴 수 없어 `--yes` 를 요구한다.
- **이미지 업로드**(`upload`)는 `POST v2.velog.io/api/v2/files/upload` (multipart: `image`·`type`·`ref_id`).
  ⚠️ **`ref_id`(이미지가 들어갈 글 ID)가 없으면 앞단이 403 `Forbidden`(평문, velog JSON 아님)으로 막는다**
  (2026-10-20 실측). 웹 에디터(CRA)도 글을 초안으로 먼저 저장해 `/write?id=…` 로 id 를 받은 뒤에야
  `{type: "post", refId: <id>}` 로 올린다. 그래서 CLI 는 `--post <id>` 를 필수로 받는다. 새 클라이언트(Next)의
  프로필 이미지 업로드는 `v3.velog.io/api/files/v3/upload` 를 쓰지만 글 이미지는 쓰지 않는다. 응답은
  `{"path": "https://velog.velcdn.com/images/<username>/post/<uuid>/image.png"}` 이다 (2026-10-20 실측). service 는 혹시
  모를 변경에 대비해 `path`·`url`·`src`·`image` 중 `http` 로 시작하는 값을 URL 로 고른다. 썸네일은 `--thumbnail` URL 로 받는다.
  - 403 은 앞단 차단이 아니라 라우트가 `ref_id` 글의 주인이 나인지 보고 낸다 (velog-server `files/upload`: `post?.fk_user_id
    !== userId` 면 403). 그래서 없는 글·남의 글도 403 이고, service 는 `FORBIDDEN`('--post 에 내 글 id') 으로 바꾼다.
    초안도 된다 (2026-10-21 실측: 새로 만든 비공개 초안에 올라갔다. 지워진 초안 id 로는 403 이었다).
  - ⚠️ **velog 는 파일 형식을 보지 않는다.** 받은 바이트를 `image.<원래 확장자>` 로 공개 CDN 에 올린다 (같은 소스. 확장자가
    없으면 파일 이름 전체가 확장자가 된다). 그래서 service 가 네트워크 전에 파일 첫 바이트로 PNG·JPEG·GIF·WebP·AVIF 인지,
    SVG 는 맨 앞(BOM·XML 선언·주석·DOCTYPE 뒤)이 `<svg` 요소인지 보고 아니면 `INVALID_ARGUMENT` 로 막는다
    (`IMAGE_SIGNATURES`·`SVG_PATTERN`). 프롬프트 인젝션을 당한 에이전트가 키·`.env`·`session.json` 을 올리면 공개 URL 이 됐다.
    확장자는 믿지 않는다 (`id_rsa.png`). 이 검사가 막는 것은 엉뚱한 파일을 그대로 넘긴 경우까지다 — 이미지 헤더 뒤에 내용을
    붙이거나 SVG 주석에 넣어 일부러 만든 파일은 형식과 상관없이 통과한다. SVG 를 따로 막지 않는 것은 그래서다 (PNG 와 같은 수준).
    SVG 는 CDN 이 `image/svg+xml` 로 올린 바이트 그대로 준다 (2026-10-21 실측: 비공개 테스트 글에 올려 받아 봄). 글 본문의
    이미지로 보인다.

### 조용한 실패: null 결과와 "not found"

v2 쓰기는 실패해도 HTTP 200 에 **`errors` 없이** `{"<mutation>": null}` 만 주기도 한다. 2026-10-20 에 없는 ID 로
mutation 을 하나씩 보내 확인한 결과:

| mutation | 대상이 없을 때 |
| --- | --- |
| `likePost`·`unlikePost`·`editPost` (v2 프록시) | `null`, errors 없음 (만료된 토큰일 때도 같다) |
| `writeComment`·`getStats`·`appendToSeries` | `null` + errors `NOT_FOUND` (`Post not found`·`Series not found`) |
| `editComment`·`removeComment` | `null` + errors `INTERNAL_SERVER_ERROR` (`Comment not found`) |
| `follow`·`unfollow` | `null` + errors `INTERNAL_SERVER_ERROR` (`Cannot return null for non-nullable field User.id.`) |

- service 는 mutation 결과가 null 이면 성공으로 내지 않는다 (`service/write.py` 의 `_written` → `UPSTREAM_ERROR`, "바로
  다시 보내지 말고 반영 여부를 먼저 확인" 힌트). 예전에는 `like` 가 exit 0 에 모든 필드 null 로 '성공' 을 냈다.
- `extensions.code` 가 `NOT_FOUND` 이거나 메시지에 `not found` 가 든 에러는 `graphql_data()` 가 `NOT_FOUND` 로 바꾼다
  (`UPSTREAM_ERROR` 의 '잠시 뒤 다시 시도' 힌트면 에이전트가 없는 ID 로 되풀이한다).
- 남의 것에 보낸 요청은 `FORBIDDEN` 으로 바꾼다: `extensions.code` 가 `NO_PERMISSION` 이거나 메시지에 `no permission`·
  `not yours` 가 든 에러 (2026-10-20 실측: 남의 글 `getStats` → `NO_PERMISSION` 'This post is not yours'. 댓글·시리즈는
  velog-server 소스 기준). 단 메시지가 `Not logged in` 이면 `NOT_LOGGED_IN` 이다 (소스에 `NO_PERMISSION` 으로 주는 곳이 있다).
- 이미 있는 것과 겹친 요청은 `ALREADY_EXISTS` 로 바꾼다: `createSeries` 의 같은 slug(`ALREADY_EXISTS` 'URL Slug already
  exists')와 `appendToSeries` 의 이미 든 글(`CONFLICT` 'Already added to series') (2026-10-21 실측). `UPSTREAM_ERROR` 의 '잠시
  뒤 다시 시도' 힌트로는 에이전트가 다시 보내도 결과가 같은 요청을 되풀이했다.
- 입력이 잘못됐다고 거절한 요청(`extensions.code` 가 `BAD_REQUEST`)은 `INVALID_ARGUMENT` 로 바꾼다 (2026-10-21 실측:
  level 2 대댓글에 단 답글 → 'Maximum comment level is 2'). `UPSTREAM_ERROR` 의 '잠시 뒤 다시 시도' 로는 되풀이했다.
- `writeComment`·`editComment`·`createSeries` 는 빈 text·이름도, 공백만 있는 값도 그대로 저장한다 (velog-server 리졸버에
  검사가 없고, 2026-10-21 실측: `"   "` 댓글이 저장됐다). 요청 모델이 `NonBlankStr`(`core/schema.py`)로 막는다.
  `min_length=1` 은 공백만 있는 값을 통과시켰다.
- **`getStats: null` 을 `_written` 처럼 에러로 바꾸지 않는 것은 일부러다.** 실패는 모두 errors 로 온다 (없는 글
  `NOT_FOUND`, 남의 글 `NO_PERMISSION`, 내 글은 값 — 2026-10-20 실측, velog-server 리졸버도 객체를 주거나 던진다). 쓰기가
  아니라 '반영 안 됨' 걱정이 없으므로, 혹시 errors 없이 null 이 와도 '모름'(`total: null`)으로 낸다. "null 을 성공으로
  낸다" 는 지적은 오탐이다.

### 토큰 갱신과 `require_auth`

요청마다 만료된 access_token 을 어떻게 다루는지가 다르다. 2026-10-20 에 13시간 전 만료된 access_token(refresh_token 은
유효)으로 각 요청을 보내 확인했다. **앞에 `require_auth` 를 둘지는 이 표로 정한다.**

| 요청 | 만료된 access_token | 로그인 안 됨 | `require_auth` |
| --- | --- | --- | --- |
| v2 프록시 쓰기 (`writePost`·`editPost`·`likePost`·`unlikePost`) | 내부 v3 호출이 실패해 **errors 없이 null** | — | **필요** (토큰 갱신) |
| v2 직접 처리 (`writeComment`·`editComment`·`removeComment`·`createSeries`·`appendToSeries`·`readingList`·`getStats`·`auth` 등) | 같은 요청 안에서 refresh_token 으로 갱신(Set-Cookie)하고 성공 | `UNAUTHENTICATED` | 필요 없음 |
| v2 REST 업로드 (`/api/v2/files/upload`) | 같은 요청 안에서 갱신 (같은 `consumeUser` 미들웨어) | 401 `NOT_AUTHORIZED` | 필요 없음 |
| v3 `feedPosts` | 같은 요청 안에서 갱신하고 성공 | **에러 없이 `[]`** | **필요** (무효 세션이 '빈 피드' 로 보이지 않게) |

- `comment`(writeComment)·`comment-edit`·`comment-remove`·`series-create`·`series-add`·`upload`·`liked`(readingList)·
  `stats`(getStats) 에 `require_auth` 가 없는 것은 일부러다. "다른 쓰기는 토큰을 갱신하는데 이것만 빠졌다" 는 지적은 오탐이다
  (위 실측. 2026-10-21 에 access_token 을 뺀 세션으로 `appendToSeries`·`editComment` 를 보내 로그인 판정을 지나 Set-Cookie 가
  오는 것을 다시 확인했다. velog-server 는 모든 요청 앞에서 `consumeUser` 가 갱신한다). 예전에는 앞의 넷과 `upload` 에도
  붙어 요청 한 번과 요청 제한 한 칸을 더 썼고, `upload` 는 파일을 읽기 전에 네트워크를 탔다. `upload` 의 401 은 service 가
  `NOT_LOGGED_IN` 으로 바꾼다.
- `edit`·`drafts`·`follow` 처럼 토큰 갱신이 필요 없어도 `require_auth` 를 먼저 부르는 명령은 로그인
  판정(`NOT_LOGGED_IN`)이나 username·is_trusted·사용자 id 가 필요해서다. `follow`·`unfollow` 는 velog-server 공개 소스에 없어
  직접 처리인지 확인하지 못해 그대로 둔다.

## 디버깅: `VELOGGER_DEBUG`

`VELOGGER_DEBUG=1` 을 주면 v2 GraphQL 의 **원본 응답**과 보내기 전 **쿠키 구조**(이름·도메인·경로·만료만, 값은
절대 찍지 않는다)를 stderr 로 내보낸다 (`api/client.py` 의 `_post_graphql_v2`). v2 가 에러를 삼켜 `null` 만
줄 때 원인을 좁히는 유일한 수단이라 남겨 둔다.

```bash
VELOGGER_DEBUG=1 velogger publish "제목" --body "본문"
```

쓰기가 `null` 로 올 때 좁히는 순서: ① `velogger stats <내 글 id>` (v2 **네이티브**, 쿠키 인증 확인) → ②
`velogger like <id>` (v2 **프록시**, 내부 v3 전달 확인) → 둘 다 되면 남은 건 **입력 문제**다 (2026-10-19 에 이
순서로 writePost 의 누락 키를 찾았다).

## 틀리기 쉬운 점

- **쓰기 재시도는 429·503 만.** 502·504·500 은 원 서버가 이미 처리했을 수 있어 다시 보내지 않는다 (글·댓글 중복).
  v2 는 내부 에러를 200 + null 로 삼키므로 쓰기의 5xx 는 대개 앞단 게이트웨이가 낸 것이다 (`should_retry_non_idempotent`).
- **본문 stdin 은 `--file -` 로만.** 터미널이 아니라고 stdin 을 읽으면 닫히지 않는 파이프를 물려준 하네스에서 멈춘다
  (2026-10-20 재현). Claude Code 의 셸은 stdin 이 `/dev/null` 이라 멈추지 않았지만, MCP stdio 래퍼처럼 부모 파이프를
  물려받는 하네스가 있다.
- **본문은 엄격한 UTF-8 로 읽는다.** 파일·stdin 모두 UTF-8 이 아니면 `INVALID_ARGUMENT` 다. 예전에는 파일이
  `UnicodeDecodeError`(ValueError) 라 'velog 응답이 이상하다' 는 `PARSE_ERROR` 로 나갔고, stdin 은 파이썬이 locale·UTF-8
  모드(`PYTHONUTF8=1`)에서 surrogateescape 로 읽어 **깨진 본문이 에러 없이 velog 로 갔다** (2026-10-20 재현). 맨 앞 BOM 은
  뗀다 (`utf-8-sig`, `BODY_ENCODING`): PowerShell 5 `Set-Content -Encoding UTF8` 가 붙인 BOM 이 본문 첫 글자 U+FEFF 로 남아 첫 줄
  `# 제목` 이 제목으로 렌더링되지 않았다.
- **`-` 로 시작하는 slug 는 `--` 뒤에 둔다.** velog 는 제목 '- 회고' 의 slug 를 '-회고' 로 만든다 (velog-server escapeForUrl
  은 앞의 `-` 를 지우지 않는다). 그대로 넘기면 Click 이 옵션으로 읽어 'No such option: -회' 가 난다. `run()` 이 그때 `--` 를
  쓰라고 힌트를 주고, 매일 API 감시도 받은 slug 앞에 `--` 를 둔다 (`post`·`series` 단계).
- **인자 NFC 정규화는 slug 에도 괜찮다 (오탐 정리).** `run()` 은 모든 인자를 NFC 로 바꾼다. "NFD slug 인 글을 못 찾는다" 는
  지적이 있었지만, velog 는 글 slug 에서 NFD 자모(U+1100–11FF)를 지워 저장해 NFD slug 인 글이 없다 (2026-10-21 실측: 비공개
  테스트 글의 slug 를 NFD 'nfd-확인용' 으로 고치니 'nfd-' 로 저장됐다. velog-server escapeForUrl 도 'ㄱ-힣' 만 남긴다).
  다만 **혼자서도 NFC 가 바꾸는 글자는 그대로 둔다** (`_compose_argument`). CJK 호환 한자(樂 U+F914 → U+6A02)·옴 기호
  (U+2126 → Ω U+03A9) 같은 글자로, 제목·본문·댓글이 쓴 것과 다르게 저장됐다 (2026-10-21 실측: 비공개 테스트 글 제목의
  U+F914 가 U+6A02 로 저장됐고, velog 자체는 받은 그대로 저장한다). NFD 결과에는 이런 글자가 없어 자모 합치기와 상관없다.
- **stdout 이 못 담는 글자는 `\uXXXX` 로 쓴다.** Windows 에서 `PYTHONUTF8` 없이 파이프로 받으면 stdout 이 cp949 라 이모지가 든
  결과(2026-10-21 실측: 트렌딩 20건 중 9글자)가 `UnicodeEncodeError` 로 'velog 응답이 이상하다' 는 `PARSE_ERROR` 가 됐다. 쓰기는
  이미 반영된 뒤라 에이전트가 다시 보낼 수 있었다 (`cli/output.py` 의 `_dumps`).
- **파일 경로는 NFD 로도 찾는다** (`cli/app.py` 의 `_local_path`). `run()` 이 인자를 NFC 로 바꾸므로, macOS 에서 만든
  한글 이름 파일을 Linux(ext4)로 옮기면 그 이름으로 열리지 않는다. macOS(APFS)는 두 형태를 같은 파일로 찾아 재현되지 않는다.
- **세션 파일을 읽지 못하면 조회도 에러다 (일부러).** `session.json` 이 있는데 권한·샌드박스로 못 읽으면 `trending` 같은
  공개 조회도 `INTERNAL_ERROR`(힌트: `VELOGGER_CONFIG_DIR`)로 끝난다. 익명 조회로 말없이 넘어가면 본인 비공개 글이
  `NOT_FOUND` 로 보여 에이전트가 '없는 글' 로 결론 낸다. "로그인 없는 조회가 세션 오류로 실패한다" 는 지적은 오탐이다
  (2026-10-20 재현·검토).
- **세션 파일 권한.** `save_session` 은 `mkstemp`(늘 0600 새 파일)로 쓰고 바꿔치기한다. 고정 이름 tmp 를 `O_CREAT` 로
  열면 남아 있던 0644 tmp 의 권한을 물려받았다. 폴더 `chmod 0700` 은 새로 만든 폴더에만 한다 (`VELOGGER_CONFIG_DIR`
  로 고른 기존 폴더는 건드리지 않는다). Windows 는 POSIX 권한이 없어 `st_mode` 가 늘 0o666 으로 보인다 (테스트가 건너뛴다).
- **팔로워·팔로잉의 `id` 는 사용자 ID 가 아니다.** v3 `followers`·`followings` 항목의 사용자 ID 는 `userId` 이고 `id` 는
  다른 값(팔로우 관계 ID 로 보인다)이다 (2026-10-21 실측: `userId` 가 `velogUserId` 로 받은 사용자 ID 와 같았다). 그래서
  `user_id` 는 `userId` 만 쓰고, 없으면 `id` 로 채우지 않고 `null` 이다.
- **빈 목록은 `[]`.** v3 는 시리즈·태그가 없는 사용자에게 `series_list: []`·`userTags.tags: []`·`profile_links: {}` 를
  준다. `or None` 으로 바꾸면 '모름(null)' 이 된다 (2026-10-20 실측: `series: null` 로 나왔다).

- **v3 에서 댓글 작성자가 null.** 비로그인 v3 `readPost` 의 `comments[].user`·`replies_count` 가 null 로 온다.
  작성자·대댓글이 필요하면 v2 GraphQL(`post.comments`, `subcomments(comment_id)`)로 받는다. v2 는 구버전이라
  언젠가 없어질 수 있어, 조회 명령을 붙이면 이 경로를 검증 대상에 넣는다.
- **GraphQL 좌표·숫자 타입.** velog 는 아니지만 일부 GraphQL 은 숫자를 문자열로 받기도 하니 실제 응답으로 확인한다.
- **trendingWriters 는 빈 응답.** v3 `trendingWriters` 가 `content-length: 0` 을 줘서 사실상 못 쓴다. 쓰지 않는다.
- **최신 글 스팸.** `recentPosts` 상단에 스팸이 끼기도 한다. 서버 결과를 우리 기준으로 다시 거르지 않는 원칙상
  임의로 지우지 않고, 필요하면 `is_private` 같은 서버 제공 필드로만 가른다.
- **RSS 백업.** `v2.velog.io/rss/@username` 으로 사용자 글 목록을 XML 로도 받을 수 있다 (GraphQL 이 막히면 대체용).
