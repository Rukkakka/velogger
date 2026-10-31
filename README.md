<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Rukkakka/velogger/main/docs/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/Rukkakka/velogger/main/docs/logo-light.svg" alt="velogger — velog 비공식 CLI" width="440">
  </picture>
</p>

<p align="center">
  <a href="https://pypi.org/project/velogger/"><img src="https://img.shields.io/pypi/v/velogger" alt="PyPI"></a>
  <a href="https://pypi.org/project/velogger/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="https://github.com/Rukkakka/velogger/actions/workflows/ci.yml"><img src="https://github.com/Rukkakka/velogger/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Rukkakka/velogger/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center">
  velog(velog.io) 를 조회하고, 로그인한 내 계정의 글·반응을 다루는 LLM 에이전트용 비공식 CLI.<br>
  An unofficial velog CLI for LLM agents: browse velog, and act on your own account once you log in.
</p>

<p align="center">
  <a href="https://github.com/Rukkakka/velogger#기능">기능</a> ·
  <a href="https://github.com/Rukkakka/velogger#빠른-시작">빠른 시작</a> ·
  <a href="https://github.com/Rukkakka/velogger#설치">설치</a> ·
  <a href="https://github.com/Rukkakka/velogger#로그인하기">로그인하기</a> ·
  <a href="https://github.com/Rukkakka/velogger#llm-에이전트에-연결하기">LLM 에이전트에 연결하기</a> ·
  <a href="https://github.com/Rukkakka/velogger#문서">문서</a>
</p>

> 비공식 API 를 쓴다. 스펙이 예고 없이 바뀔 수 있고, 자동수집·자동작성은 velog 약관과 상충할 소지가 있으니 개인 용도로만 쓴다.

Claude, ChatGPT 같은 LLM 에이전트가 velog 를 다룰 때 셸로 부르는 도구다. 무엇을 할지는 사용자와 LLM 이 정하고, velog 의 조회 절차·요청 제한·로그인을 지키며 결과를 공통 JSON 으로 돌려주는 일은 CLI 가 맡는다. 이름은 velog 사용자를 부르는 말 "벨로거"에서 따왔고, velog 가 만든 공식 도구가 아니다. 같은 구조의 형제 프로젝트로 부동산 [jibsa](https://github.com/Rukkakka/jibsa) 와 항공권 [baenggipyo](https://github.com/Rukkakka/baenggipyo) 가 있다.

## 기능

| 무엇을 | 명령 | 로그인 |
| --- | --- | --- |
| 글 목록 | `trending` · `recent` · `search <검색어>` · `tag <태그>` · `posts <username>` | — |
| 글 하나 | `post <username> <url_slug>` (본문 마크다운) · `comments <post_id>` · `series <username> <url_slug>` | — |
| 사람 | `user <username>` · `followers` · `followings` | — |
| 내 목록 | `feed` · `liked` · `drafts` · `stats` | 필요 |
| 쓰기 | `publish` · `edit` · `upload` · `series-create` · `series-add` | 필요 |
| 반응 | `like` · `unlike` · `comment` · `comment-edit` · `comment-remove` · `follow` · `unfollow` | 필요 |
| 계정·상태 | `login` · `logout` · `whoami` · `limits` · `guide` | — |

- **조회는 로그인 없이 된다.** 로그인돼 있으면 세션을 함께 보내 본인 비공개 글도 보인다
- **쓰기는 기본이 안전한 쪽이다.** `publish` 는 기본이 임시저장이고 발행은 `--publish` 를 붙여야 한다. 댓글 삭제는 `--yes` 가 필요하고, 글 삭제 명령은 없다
- 발행은 신뢰 계정(`is_trusted`)만 된다. 캡차를 풀지 않고, 아니면 웹에서 발행하라고 안내한다
- **토큰·쿠키는 어떤 출력에도 나오지 않는다.** 로그인 정보는 로그인 여부·`username`·`is_trusted` 만 보여 준다 ([로그인에 대해](https://github.com/Rukkakka/velogger#로그인에-대해-jibsabaenggipyo-와-다른-점))
- 결과는 JSON 이고 글마다 velog 주소(`url`)가 붙는다. 조회 범위·제한은 `notes` 로 알린다
- 모든 요청이 요청 제한을 지나고, 그 상태를 모든 velogger 프로세스가 함께 쓴다

명령별 인자·옵션·반환값은 [velogger 사용법](https://github.com/Rukkakka/velogger/blob/main/docs/velogger.md)에 있다.

## 빠른 시작

```bash
uv tool install velogger        # 또는 pipx install velogger
velogger trending --limit 1
```

결과는 stdout 에 JSON 하나로 나온다 (에러는 stderr 에 JSON). 아래는 위 명령의 실제 출력에서 `short_description`·`thumbnail` 을 줄인 것이다 (2026-10-20 조회).

```json
{
  "returned": 1,
  "posts": [
    {
      "id": "3b37cb3d-ef8f-4b16-bb52-059525d16784",
      "title": "AI Native FE 개발로의 전환, 150일간의 여정",
      "username": "teo",
      "display_name": "teo.v",
      "url_slug": "ai-native-fe",
      "url": "https://velog.io/@teo/ai-native-fe",
      "short_description": "AI만으로 개발하는 시대, FE 개발자의 업무는 어떻게 변했을까? …",
      "thumbnail": "https://velog.velcdn.com/images/teo/post/…/image.png",
      "tags": null,
      "released_at": "2026-10-15T00:15:36.325Z",
      "updated_at": "2026-10-19T22:38:20.895Z",
      "likes": 59,
      "comments_count": null,
      "is_private": null,
      "is_temp": null
    }
  ]
}
```

이어서 `velogger post teo ai-native-fe` 로 그 글의 본문을 마크다운으로 받는다. 로그인이 필요한 명령은 [로그인하기](https://github.com/Rukkakka/velogger#로그인하기)를 먼저 한다.

![로그인 없이 velogger guide 로 에이전트용 가이드를 읽고, trending 으로 트렌딩 글 셋을, post 로 그중 한 글의 제목·태그·본문 앞부분을 jq 로 골라 보는 터미널 데모](https://raw.githubusercontent.com/Rukkakka/velogger/main/docs/demo/demo.gif)

로그인 없이 `guide`·`trending`·`post` 를 차례로 불러 본 실제 화면이다 (2026-10-21 녹화, 결과는 `jq` 로 일부 칸만 골랐다).

## 설치

Python 3.11 이상이 필요하고 (uv 로 설치하면 없어도 된다), macOS·Linux·Windows 에서 쓸 수 있다. 셋 중 하나만 하면 된다.

| 방법 | 설치 | 업데이트 |
| --- | --- | --- |
| **uv** (권장) | `uv tool install velogger` | `uv tool upgrade velogger` |
| pipx | `pipx install velogger` | `pipx upgrade velogger` |
| pip + 가상환경 | `python3 -m venv ~/.venvs/velogger && ~/.venvs/velogger/bin/pip install velogger` | `~/.venvs/velogger/bin/pip install -U velogger` |

```bash
velogger --help      # 명령 목록이 나오면 성공
velogger limits      # 요청 제한 상태 JSON. 네트워크 요청은 보내지 않는다
```

설치하지 않고 한 번 써 보려면 `uvx velogger --help` 로 부른다. 아직 릴리스하지 않은 최신 수정은 `uv tool install git+https://github.com/Rukkakka/velogger` 로 받는다. 삭제는 `uv tool uninstall velogger` (pipx 는 `pipx uninstall velogger`) 다. `velogger: command not found` 가 나오면 새 터미널을 열거나 `uv tool update-shell` 로 `~/.local/bin` 을 PATH 에 넣는다. 버전마다 바뀐 점은 [변경 기록](https://github.com/Rukkakka/velogger/blob/main/CHANGELOG.md)에 있다.

```bash
# 저장소를 받아 개발 설치 (코드를 고칠 때)
git clone https://github.com/Rukkakka/velogger && cd velogger
uv venv --python 3.11
uv pip install -e ".[dev]"
.venv/bin/velogger --help
```

자세한 개발 환경·검증 방법은 [개발 환경](https://github.com/Rukkakka/velogger/blob/main/docs/development/README.md)에 있다.

## 로그인하기

velog 가입을 이메일로 했든 깃허브·구글로 했든, 계정 이메일로 로그인 링크를 받는다.

```bash
velogger login you@example.com          # 1) velog 가 그 주소로 로그인 링크를 보낸다
# 2) 메일 속 링크(velog.io/email-login?code=...)를 복사한다 (브라우저로 열지 말 것)
velogger login --code '<붙여넣기>'       # 3) 세션 저장
velogger whoami                         # 로그인 확인 (is_trusted 도 보여 준다)
```

브라우저에 이미 로그인돼 있으면 쿠키를 붙여넣어도 된다: `velogger login --cookie 'name=value; ...'`.

## LLM 에이전트에 연결하기

에이전트에게는 [LLM 사용 가이드](https://github.com/Rukkakka/velogger/blob/main/docs/llm.md) 하나를 먼저 읽게 한다. 설치본에 들어 있어 `velogger guide` 로 바로 출력된다 (설치한 버전과 내용이 같고 네트워크를 쓰지 않는다). 지침 파일(`CLAUDE.md`, `AGENTS.md` 등)에 이렇게 적어 두면 된다.

```text
velog 를 다룰 때는 velogger CLI 를 쓴다. 처음 쓰기 전에 `velogger guide` 를 실행해 읽고 그 규칙을 따른다.
로그인이 필요하면 사용자가 직접 `velogger login` 을 실행한다.
```

## 설정

설정 파일은 없다. 환경 변수만 쓴다.

| 환경 변수 | 하는 일 |
| --- | --- |
| `VELOGGER_CONFIG_DIR` | 로그인 세션 파일(`session.json`, 사용자 전용 권한 0600)을 둘 디렉터리. 기본은 `~/.config/velogger` |
| `VELOGGER_STATE_DIR` | 요청 제한 상태 파일을 둘 디렉터리. 기본은 `~/.cache/velogger`. 기본 위치에 쓸 수 없는 환경(샌드박스 등)이면 쓸 수 있는 폴더로 바꾼다 |
| `XDG_CONFIG_HOME` · `XDG_CACHE_HOME` | 절대 경로로 설정해 두었으면 그 아래 `velogger` 를 쓴다 (`VELOGGER_CONFIG_DIR`·`VELOGGER_STATE_DIR` 이 우선) |
| `PYTHONUTF8` | Windows 에서 `1` 로 설정한다 (아래) |

### Windows 에서 쓸 때

Windows 의 Python 은 출력 인코딩이 기본으로 UTF-8 이 아니다 (한국어 Windows 는 cp949). LLM 에이전트가 velogger 를 부르면 출력이 파이프로 넘어가는데, 이때 한글이 깨지거나 cp949 에 없는 문자(이모지 등)에서 오류가 날 수 있다. 아래처럼 사용자 환경 변수를 설정하고 새 터미널을 연다. macOS·Linux 는 따로 할 것이 없다.

```powershell
setx PYTHONUTF8 1
```

## 왜 만들었나

LLM 이 velog 를 다루려면 비공식 API 를 추측해 호출하다 막히거나, 로그인·토큰을 어설프게 다루다 자격증명을 흘릴 수 있다. 이 CLI 는 조회·로그인 절차와 요청 제한을 지키고, 토큰을 안전하게(사용자 전용 파일, 출력 비노출) 보관하며, 결과를 LLM 이 읽기 좋은 JSON 으로 돌려준다.

## 로그인에 대해 (jibsa·baenggipyo 와 다른 점)

형제 프로젝트는 "로그인 없는 기능만" 이 원칙이지만, velogger 는 로그인을 포함한다. 대신 자격증명은 **떳떳하게만** 다룬다.

- velog 공식 로그인 API 로 인증하거나(이메일 매직 링크), 사용자가 직접 넘긴 쿠키만 쓴다.
- **브라우저 쿠키 저장소를 몰래 복호화해 꺼내 오지 않는다** (인포스틸러 기법이라 넣지 않는다). 소셜 OAuth 를 헤드리스로 가로채지 않는다.
- 로그인 code·쿠키는 사용자가 자기 터미널에서 직접 넣는다. 에이전트가 대신 다루지 않는다.
- 토큰·쿠키는 어떤 출력에도 나오지 않고, `~/.config/velogger/session.json` 에 권한 0600 으로만 저장된다.

## 문서

사용 문서

- [LLM 사용 가이드](https://github.com/Rukkakka/velogger/blob/main/docs/llm.md): 에이전트용 요약. 처음 읽을 문서
- [공통 사용 규칙](https://github.com/Rukkakka/velogger/blob/main/docs/common.md): JSON 출력, 누락값, 오류 대응, 로그인·요청 제한
- [velogger 사용법](https://github.com/Rukkakka/velogger/blob/main/docs/velogger.md)
- [변경 기록](https://github.com/Rukkakka/velogger/blob/main/CHANGELOG.md)

개발 문서

- [공통 개발 규약](https://github.com/Rukkakka/velogger/blob/main/AGENTS.md) · [개발 환경](https://github.com/Rukkakka/velogger/blob/main/docs/development/README.md) · [아키텍처](https://github.com/Rukkakka/velogger/blob/main/docs/development/architecture.md) · [버전·릴리스](https://github.com/Rukkakka/velogger/blob/main/docs/development/release.md)
- [velog API 개발 가이드](https://github.com/Rukkakka/velogger/blob/main/docs/development/velog-api.md)

## 기여

버그·기능 제안은 [이슈](https://github.com/Rukkakka/velogger/issues/new/choose)로 열고, 코드를 고치기 전에 [개발 규약](https://github.com/Rukkakka/velogger/blob/main/AGENTS.md)의 "꼭 지킬 것"(토큰·쿠키 비출력, 로그인은 사용자가, 캡차를 풀지 않음 등)을 읽는다. 개발 환경 설치와 검사는 [개발 환경](https://github.com/Rukkakka/velogger/blob/main/docs/development/README.md), 브랜치 → 커밋 → PR 절차는 [작업 절차](https://github.com/Rukkakka/velogger/blob/main/docs/development/workflow.md)에 있다. 모든 변경은 PR 로 들어가고 CI(ruff·mypy·pytest·설치 확인)를 통과해야 한다.

## 라이선스

[MIT](https://github.com/Rukkakka/velogger/blob/main/LICENSE)
