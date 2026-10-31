# Changelog

velogger 의 버전별 변경 기록. 사용자(에이전트 포함)에게 보이는 변경만 적고, 아직 릴리스하지 않은 변경은
`Unreleased` 에 쌓는다. 번호 규칙과 쓰는 법은 [references/release.md](references/release.md) 에 있다.

## Unreleased

### 추가

- `publish`·`edit` 에 `--description "<소개글>"`: 글 목록·시리즈에 보이는 소개글(velog 웹의 '포스트 미리보기')을 쓴다. 150자까지다.
  예전에는 CLI 로 소개글을 쓸 방법이 없어, velog 가 본문 앞부분을 잘라 대신 보여 줬다 (#41)

## 0.3.0 — 2026-10-23

### 추가

- `posts`·`recent`·`liked`·`followers`·`followings` 에 `--cursor` 와 결과의 `next_cursor`(다음 페이지, `null` 이면 마지막 페이지).
  예전에는 첫 `--limit` 개(최대 100) 뒤의 글·사람을 받을 방법이 없었다 (#24)

### 변경

- `edit` 이 바꾸지 않을 칸(본문·제목·태그·slug·요약 등)의 현재 값을 velog 가 주지 않으면 빈 값으로 덮어쓰지 않고 `PARSE_ERROR`
  로 멈춘다 (메시지에 빠진 칸 이름). 발행·공개 상태에만 하던 확인을 넓혔다 (#26)

### 수정

- `posts --limit` 이 50보다 크면 50개만 오던 문제. velog 가 한 번에 50개까지만 줘서, 이제 나눠 받아 `--limit` 만큼 채운다 (#24)
- `posts --tag` 가 `--limit` 과 상관없이 20개를 주던 문제 (`--limit 4` 면 20개가 왔고 `--limit 100` 이면 20개에서 끝났다) (#24)
- 명령이 도는 사이 다른 터미널에서 `logout`(또는 다른 계정으로 `login`)하면, 그 명령이 끝날 때 옛 세션을 다시 저장해
  로그아웃이 풀리던 문제 (#25)

## 0.2.0 — 2026-10-22

### 추가

- `edit --thumbnail <URL>`: 이미 만든 글의 목록 카드 썸네일을 바꾼다. `upload` 로 올린 이미지의 `url` 을 그대로 준다 (#15)
- `post` 결과에 `thumbnail`(목록 카드의 썸네일 이미지 URL). 목록에는 있었는데 글 상세에만 없었다 (#14)
- `series-add` 결과에 `index`(넣은 글의 시리즈 안 순번, 1부터) (#13)

### 수정

- `series-add` 가 시리즈의 두 번째 글부터 `PARSE_ERROR` 를 내던 문제. velog 는 넣은 글의 순번(숫자)을 돌려주는데 참/거짓으로 읽었다. 에러가 나도 글은 들어가 있었다 (#13)

## 0.1.1 — 2026-10-21

### 수정

- README·PyPI 의 개발 상태 표시가 pre-alpha 로 남아 있던 것을 alpha(`Development Status :: 3 - Alpha`)로 고침 (#9)

## 0.1.0 — 2026-10-21

### 추가

- 로그인·세션 관리: `login`(이메일 매직 링크 또는 `--cookie` 붙여넣기)·`logout`·`whoami`. velog 는 비밀번호가
  없어 세션 쿠키로 로그인하며, 토큰은 `~/.config/velogger/session.json`(0600)에만 저장하고 출력하지 않는다. 로그인
  정보는 `logged_in`·`username`·`is_trusted` 만 보여 준다 (이메일·사용자 ID 는 내보내지 않는다). code 가 없거나 이미
  쓰였거나 만료됐으면 `LOGIN_FAILED` 로 새 링크를 받으라고 안내하고, 계정이 없는 이메일로 온 가입 링크면
  `LOGIN_FAILED`(`details.registered: false`)로 그렇다고 알린다. code 로 받은 세션은 바로 저장해 뒤이은 확인 요청이
  실패해도 로그인이 남는다. velog 가 갱신해 준 토큰은 쓰기뿐 아니라 조회·`whoami` 뒤에도, 명령이 실패했거나 출력을 받는
  쪽이 먼저 닫혀도 다시 저장해, 조회만 해도 세션이 30일 뒤 끊기지 않는다
- 조회 명령: `trending`·`recent`·`search`·`posts`·`post`(본문 마크다운)·`user`·`tag`(`--cursor` 로 다음 페이지,
  전체 글 수는 `count`). 로그인 없이 되며, 목록은 공통 요약 모양(`url`·`is_private`·`is_temp` 포함, 초안의 `url` 은
  편집 주소)으로, 본문은 `post` 로 받는다. 로그인한 채로 시리즈에 든 내 글을 읽으면 velog 서버 오류로 시리즈 안 글
  목록만 빼고(`series.posts: null`, `notes` 로 안내) 글을 준다
- 작성 명령(로그인 필요): `publish`(기본 임시저장, `--publish` 로 발행, 본문은 `--body`·`--file`, 파이프는
  `--file -`, UTF-8 이고 맨 앞 BOM 은 뗀다)·`edit`(안 준 필드·시리즈·요약은 유지, 남의 글이거나 발행·공개 상태를
  모르면 고치지 않는다)·`drafts`·`like`·`unlike`·`comment`·`stats`. 발행은 신뢰 계정(`is_trusted`)만 되고, 아니면
  `FORBIDDEN` 으로 막고 웹 발행을 안내한다 (캡차를 풀지 않는다). velog 가 쓰기 결과를 주지 않으면 성공으로 내지 않고
  `UPSTREAM_ERROR` 로 알린다. 남의 글·댓글·시리즈에 보낸 요청은 `FORBIDDEN`, 이미 있는 시리즈 slug·이미 시리즈에 든
  글은 `ALREADY_EXISTS`, velog 가 잘못된 요청이라고 거절한 것(대댓글의 대댓글에 단 답글 등)은 `INVALID_ARGUMENT`.
  빈 댓글·공백만 있는 댓글과 시리즈 이름은 보내지 않는다. 글 삭제 명령은 없다
- 댓글·시리즈·사람 조회: `comments`(작성자 포함, `--replies` 로 대댓글의 대댓글까지)·`series`(순서대로)·`followers`·
  `followings`. 글 본문(`post`)은 댓글 수만 주므로 내용은 `comments` 로 받는다
- 로그인 목록: `feed`(팔로우한 사람들의 글)·`liked`(좋아요한 글, `--read` 면 읽은 글)
- 반응·편집: `comment-edit`·`comment-remove`(되돌릴 수 없어 `--yes` 필요)·`follow`·`unfollow`
- 시리즈·이미지: `series-create`·`series-add`·`upload`(PNG·JPEG·GIF·WebP·AVIF·SVG 이미지만 올려 본문용 URL·markdown 을 준다.
  이미지가 아닌 파일은 공개 주소가 되지 않게 내용으로 보고 막는다)
- 요청 제한 상태 조회 `limits`
- LLM 에이전트용 사용 가이드 `guide` (`docs/llm.md`·`docs/common.md`·`docs/velogger.md`)
- 매일 조회 명령을 실제로 불러 보는 API 감시 (`scripts/monitor/`, `.github/workflows/api-monitor.yml`)와
  README 데모 녹화 대본 (`scripts/demo/`)
