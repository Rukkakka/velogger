"""글 작성·편집·반응 (`publish`·`edit`·`drafts`·`like`·`unlike`·`comment`·`stats` 등). 로그인 세션이 필요하다.

발행(`is_temp=False`)은 신뢰 계정(is_trusted)만 캡차 없이 된다. 신뢰 계정이 아니면 캡차(Turnstile)를 풀지
않고 발행을 막는다 (웹에서 발행하라고 안내). 임시저장(초안)은 캡차가 없어 누구나 된다.

v2 쓰기는 실패해도 HTTP 200 + `errors` 없는 null 만 주기도 한다 (2026-10-20 실측: 없는 글이나 만료된 토큰으로 보낸
likePost·editPost). 그래서 mutation 결과가 null 이면 성공으로 내지 않고 `_written` 으로 에러를 낸다.
"""

import re
import unicodedata
from pathlib import Path

from httpx import HTTPStatusError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from velogger.api.client import VelogClient
from velogger.api.request.users import VelogGetUserRequestPayloadModel
from velogger.api.request.write import (
    VelogCreateSeriesRequestPayloadModel,
    VelogEditCommentRequestPayloadModel,
    VelogEditPostRequestPayloadModel,
    VelogWriteCommentRequestPayloadModel,
    VelogWritePostRequestPayloadModel,
)
from velogger.api.response.auth import VelogAuthUserModel
from velogger.api.response.write import VelogWrittenPostModel
from velogger.core.errors import VeloggerError
from velogger.service.common import (
    VelogPostList,
    edit_url,
    graphql_data,
    not_logged_in_error,
    post_list_of,
    post_url,
    require_auth,
)

from typing import (
    Annotated,
    TypeVar,
)


_Result = TypeVar('_Result')

# 올릴 수 있는 이미지 형식과, 그 형식이면 파일의 이 위치(offset)에 있는 바이트. velog 는 받은 파일의 형식을 보지 않고
# `image.<원래 확장자>` 로 공개 CDN 에 올린다 (velog-server `files/upload` 라우트). 이미지가 아닌 파일(키·.env·session.json)을
# 넘기면 그대로 누구나 받을 수 있는 URL 이 되므로, 확장자가 아니라 내용으로 이미지인지 먼저 본다. 이 검사가 막는 것은
# '엉뚱한 파일을 그대로 넘긴 경우' 까지다. 이미지 헤더 뒤에 다른 내용을 붙여 일부러 만든 파일은 형식과 상관없이 통과한다.
IMAGE_SIGNATURES: tuple[tuple[str, tuple[tuple[int, bytes], ...]], ...] = (
    ('PNG', ((0, b'\x89PNG\r\n\x1a\n'),)),
    ('JPEG', ((0, b'\xff\xd8\xff'),)),
    ('GIF', ((0, b'GIF87a'),)),
    ('GIF', ((0, b'GIF89a'),)),
    ('WebP', ((0, b'RIFF'), (8, b'WEBP'))),
    ('AVIF', ((4, b'ftypavif'),)),
    ('AVIF', ((4, b'ftypavis'),)),
)
# SVG 는 정해진 첫 바이트가 없는 글자(XML) 파일이라, 맨 앞(BOM·XML 선언·주석·DOCTYPE 뒤)이 `<svg` 요소인지로 본다.
# 키·.env·session.json 은 이렇게 시작하지 않아 위 형식들과 같은 수준으로 막힌다.
SVG_PATTERN: re.Pattern[bytes] = re.compile(
    rb'\A(?:\xef\xbb\xbf)?\s*(?:<\?xml[^>]*>\s*)?(?:(?:<!--.*?-->|<!DOCTYPE[^>]*>)\s*)*<svg[\s>]',
    re.DOTALL,
)
IMAGE_FORMATS_TEXT: str = 'PNG·JPEG·GIF·WebP·AVIF·SVG'
# 마크다운 이미지 alt 에서 뜻이 있는 글자. 파일 이름 `diagram]v2.png` 를 그대로 넣으면 `![diagram]v2](...)` 가 돼 이미지가
# 아니라 글자로 보인다
MARKDOWN_ALT_SPECIAL: re.Pattern[str] = re.compile(r'([\\\[\]])')


def slugify(title: str) -> str:
    """제목에서 url_slug 를 만든다 (velog 는 한글 slug 를 허용한다). 공백은 `-`, 그 밖의 특수문자는 뺀다.

    앞뒤의 `.` 도 뗀다. 점만 남은 slug(`..`)는 글 주소가 `velog.io/@user/..` 처럼 상위 경로가 된다.
    """
    text = unicodedata.normalize('NFC', title).strip()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^\w가-힣.\-]', '', text)
    text = re.sub(r'-{2,}', '-', text).strip('-.')
    return text or 'post'


class VelogPublishResult(BaseModel):
    """글 저장 결과."""

    model_config = ConfigDict(extra='forbid')

    id: Annotated[str | None, Field(description='글 ID')] = None
    url_slug: Annotated[str | None, Field(description='글 slug')] = None
    url: Annotated[str | None, Field(description='글 주소')] = None
    status: Annotated[str, Field(description="'published'(발행) 또는 'draft'(임시저장)")]
    is_private: Annotated[bool, Field(description='비공개 여부')]


class VelogLikeResult(BaseModel):
    """좋아요/취소 결과."""

    model_config = ConfigDict(extra='forbid')

    id: Annotated[str | None, Field(description='글 ID')] = None
    likes: Annotated[int | None, Field(description='현재 좋아요 수')] = None
    liked: Annotated[bool | None, Field(description='내가 좋아요한 상태인지')] = None


class VelogCommentResult(BaseModel):
    """댓글 작성 결과."""

    model_config = ConfigDict(extra='forbid')

    id: Annotated[str | None, Field(description='댓글 ID')] = None
    text: Annotated[str | None, Field(description='저장된 댓글 내용')] = None
    replies_count: Annotated[int | None, Field(description='대댓글 수')] = None


class VelogCommentRemoveResult(BaseModel):
    """댓글 삭제 결과."""

    model_config = ConfigDict(extra='forbid')

    comment_id: Annotated[str, Field(description='지운 댓글 ID')]
    removed: Annotated[bool, Field(description='지워졌는지')]


class VelogFollowResult(BaseModel):
    """팔로우/취소 결과."""

    model_config = ConfigDict(extra='forbid')

    username: Annotated[str, Field(description='대상 아이디 (@username)')]
    user_id: Annotated[str, Field(description='대상 사용자 ID')]
    is_followed: Annotated[bool | None, Field(description='지금 팔로우한 상태인지')] = None


class VelogSeriesCreateResult(BaseModel):
    """시리즈 만들기 결과."""

    model_config = ConfigDict(extra='forbid')

    id: Annotated[str | None, Field(description='시리즈 ID (publish --series-id·series-add 에 쓴다)')] = None
    name: Annotated[str, Field(description='시리즈 이름')]
    url_slug: Annotated[str, Field(description='시리즈 slug')]


class VelogSeriesAddResult(BaseModel):
    """시리즈에 글 넣기 결과."""

    model_config = ConfigDict(extra='forbid')

    series_id: Annotated[str, Field(description='시리즈 ID')]
    post_id: Annotated[str, Field(description='넣은 글 ID')]
    added: Annotated[bool, Field(description='들어갔는지')]
    index: Annotated[int, Field(description='시리즈 안 순번 (1부터)')]


class VelogUploadResult(BaseModel):
    """이미지 업로드 결과."""

    model_config = ConfigDict(extra='forbid')

    filename: Annotated[str, Field(description='올린 파일 이름')]
    url: Annotated[str, Field(description='이미지 주소')]
    markdown: Annotated[str, Field(description='본문에 그대로 넣는 마크다운 이미지 문법')]


class VelogStatsDay(BaseModel):
    """일별 조회수 한 칸."""

    model_config = ConfigDict(extra='forbid')

    day: Annotated[str | None, Field(description='날짜')] = None
    count: Annotated[int | None, Field(description='그날 조회수')] = None


class VelogStatsResult(BaseModel):
    """내 글 조회수."""

    model_config = ConfigDict(extra='forbid')

    total: Annotated[int | None, Field(description='전체 조회수')] = None
    count_by_day: Annotated[
        list[VelogStatsDay] | None,
        Field(description='일별 조회수 (velog 서버가 지금은 빈 배열로 준다)')
    ] = None


def _written(result: _Result | None, action: str) -> _Result:
    """쓰기 mutation 결과가 null 이면 에러로 바꾼다.

    v2 는 내부 에러를 삼켜 HTTP 200 + null 만 주므로, null 을 그대로 성공으로 내면 에이전트가 반영되지 않은 쓰기를
    됐다고 전한다 (2026-10-20 재현: 없는 글에 like 가 exit 0 + 모든 필드 null). 반영 여부를 알 수 없으니 바로 다시
    보내지 말고 먼저 확인하라고 안내한다 (글·댓글이 두 번 생기지 않게).

    Raises:
        VeloggerError: 결과가 null 일 때 (`UPSTREAM_ERROR`).
    """
    if result is None:
        raise VeloggerError(
            code='UPSTREAM_ERROR',
            message=f'velog 가 {action} 결과를 주지 않았습니다 (반영되지 않았을 수 있습니다)',
            hint=(
                '같은 명령을 바로 다시 보내지 말고 drafts·posts·comments 등으로 반영됐는지 먼저 확인하세요. '
                '계속되면 VELOGGER_DEBUG=1 로 원본 응답을 확인하세요'
            ),
        )
    return result


def _publish_result(written: VelogWrittenPostModel, *, is_temp: bool, is_private: bool) -> VelogPublishResult:
    username = written.user.username if written.user else None
    # 초안은 공개 주소가 아직 404 라, 이어서 쓸 수 있는 편집 주소를 준다.
    url = edit_url(written.id) if is_temp and written.id else post_url(username, written.url_slug)
    return VelogPublishResult(
        id=written.id,
        url_slug=written.url_slug,
        url=url,
        status='draft' if is_temp else 'published',
        is_private=is_private,
    )


def _check_can_publish(user: VelogAuthUserModel, *, is_temp: bool, already_published: bool = False) -> None:
    """발행인데 신뢰 계정이 아니면 막는다 (캡차를 풀지 않는다).

    이미 발행된 글의 수정도 발행으로 막는 것은 일부러다. velog 웹도 발행된 글을 고칠 때 `is_temp: false` 와 Turnstile
    token 을 함께 보내고, 캡차는 신뢰 계정이 아닐 때 켜진다 (velog-client `PublishActionButtonsContainer`·
    `TurnstileProvider`, 2026-10-20 확인). 그래서 그 경우의 힌트는 '--publish 없이 하라' 가 아니라 웹에서 고치라고 한다
    (--publish 를 빼도 발행된 글은 발행 상태로 보내야 해 같은 에러가 난다).

    `user` 는 쓰기 직전에 부른 `require_auth` 결과다. 그 호출이 access_token 도 갱신해, 뒤이은 v2 프록시 쓰기가 최신
    토큰으로 나간다 (velog 의 access_token 은 수명이 1시간이라, 임시저장이라도 갱신이 필요하다).
    """
    if is_temp or user.is_trusted:
        return
    if already_published:
        raise VeloggerError(
            code='FORBIDDEN',
            message='이 계정은 발행된 글을 고칠 때도 캡차(Cloudflare Turnstile)가 필요합니다',
            hint='CLI 는 캡차를 풀지 않습니다. 발행된 글은 velog.io 웹에서 고치세요 (--publish 를 빼도 같습니다)',
        )
    raise VeloggerError(
        code='FORBIDDEN',
        message='이 계정은 글 발행에 캡차(Cloudflare Turnstile)가 필요합니다',
        hint='CLI 는 캡차를 풀지 않습니다. 이 글은 velog.io 웹에서 발행하세요. 임시저장(--publish 없이)은 됩니다',
    )


def publish(
    client: VelogClient,
    *,
    title: str,
    body: str,
    tags: list[str],
    publish_now: bool = False,
    is_private: bool = False,
    is_markdown: bool = True,
    url_slug: str | None = None,
    thumbnail: str | None = None,
    series_id: str | None = None,
) -> VelogPublishResult:
    """새 글을 쓴다. 기본은 임시저장(초안)이고 `publish_now=True` 여야 발행한다.

    Raises:
        VeloggerError: 발행인데 신뢰 계정이 아닐 때 (`FORBIDDEN`), 로그인 안 됨 (`NOT_LOGGED_IN`), velog 가 결과를
            주지 않았을 때 (`UPSTREAM_ERROR`).
    """
    is_temp = not publish_now
    _check_can_publish(require_auth(client), is_temp=is_temp)
    payload = VelogWritePostRequestPayloadModel(
        title=title,
        body=body,
        tags=tags,
        is_markdown=is_markdown,
        is_temp=is_temp,
        is_private=is_private,
        url_slug=url_slug or slugify(title),
        thumbnail=thumbnail,
        series_id=series_id,
    )
    data = graphql_data(client.run_request_write_post(payload))
    written = _written(data.write_post if data else None, '글 저장(writePost)')
    return _publish_result(written, is_temp=is_temp, is_private=is_private)


def edit_post(
    client: VelogClient,
    post_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    is_private: bool | None = None,
    publish_now: bool = False,
    url_slug: str | None = None,
    thumbnail: str | None = None,
) -> VelogPublishResult:
    """기존 글을 고친다. 바꾸지 않은 필드는 현재 값을 그대로 보내(본문 등이 지워지지 않게) editPost 로 보낸다.

    editPost 는 보낸 값으로 글을 덮으므로 시리즈(`series_id`)·`meta`(short_description 등)도 현재 값을 그대로
    보낸다. series_id 를 빼면 null 로 가 글이 시리즈에서 빠진다 (2026-10-20 실측). `publish_now=True` 면 초안을
    발행 상태로 바꾼다 (신뢰 계정만). `thumbnail` 을 주면 글 목록 카드의 썸네일을 그 이미지 URL 로 바꾼다.

    Raises:
        VeloggerError: 로그인 안 됨 (`NOT_LOGGED_IN`), 글이 없을 때 (`NOT_FOUND`), 남의 글이거나 발행인데 신뢰 계정이
            아닐 때 (`FORBIDDEN`), 글의 발행·공개 상태를 모를 때 (`PARSE_ERROR`), velog 가 결과를 주지 않았을 때
            (`UPSTREAM_ERROR`).
    """
    # 로그인부터 확인한다. 세션이 무효하면 ReadPostForEdit 가 익명 조회가 돼 본인 초안이 null 로 오고, 그대로 두면
    # NOT_LOGGED_IN 대신 NOT_FOUND('본인 글의 ID 인지 확인') 가 나 에이전트가 엉뚱한 ID 를 찾는다 (2026-10-20 재현).
    user = require_auth(client)
    current_data = graphql_data(client.run_request_read_post_for_edit(post_id))
    current = current_data.post if current_data else None
    if current is None:
        raise VeloggerError(
            code='NOT_FOUND',
            message=f'고칠 글을 찾지 못했습니다: {post_id}',
            hint='본인 글의 ID 인지 확인하세요 (velogger posts·drafts 결과의 id)',
        )
    # ReadPostForEdit 는 남의 공개 글도 준다 (2026-10-21 실측). 그대로 editPost 를 보내면 v2 가 거절을 삼켜 null 이 와,
    # FORBIDDEN 대신 '반영됐는지 확인하라' 는 UPSTREAM_ERROR 가 나간다. 글쓴이를 모르면(velog 가 안 주면) 막지 않는다:
    # 남의 글이어도 velog 가 거절할 뿐 바뀌는 것은 없다.
    owner_id = current.user.id if current.user else None
    if owner_id and user.id and owner_id != user.id:
        raise VeloggerError(
            code='FORBIDDEN',
            message=f'본인 글이 아니라 고칠 수 없습니다: {post_id}',
            hint='edit 은 내 글에만 됩니다. id 를 velogger posts <내 아이디>·drafts 결과에서 가져왔는지 확인하세요',
        )
    # 발행·공개 상태를 모르면 보내지 않는다. editPost 는 보낸 값으로 덮어, 추측해 보내면 발행된 글이 초안이 되거나(공개
    # 주소 404) 비공개 글이 공개된다. 2026-10-21 실측으로는 내 글·초안 모두 두 값이 왔다.
    is_temp = False if publish_now else current.is_temp
    resolved_private = is_private if is_private is not None else current.is_private
    if is_temp is None or resolved_private is None:
        raise VeloggerError(
            code='PARSE_ERROR',
            message=f'velog 가 글의 발행·공개 상태를 주지 않아 고치지 않았습니다: {post_id}',
            hint='모르는 채 보내면 발행 상태나 공개 여부가 바뀔 수 있습니다. velogger 를 업데이트하거나 VELOGGER_DEBUG=1 로 원본 응답을 확인하세요',
        )
    _check_can_publish(user, is_temp=is_temp, already_published=current.is_temp is False)
    payload = VelogEditPostRequestPayloadModel(
        id=post_id,
        title=title if title is not None else (current.title or ''),
        body=body if body is not None else (current.body or ''),
        tags=tags if tags is not None else (current.tags or []),
        is_markdown=current.is_markdown if current.is_markdown is not None else True,
        is_temp=is_temp,
        is_private=resolved_private,
        url_slug=url_slug or current.url_slug or slugify(current.title or 'post'),
        thumbnail=thumbnail if thumbnail is not None else current.thumbnail,
        series_id=current.series.id if current.series else None,
        meta=current.meta or {},
    )
    data = graphql_data(client.run_request_edit_post(payload))
    written = _written(data.edit_post if data else None, '글 수정(editPost)')
    return _publish_result(written, is_temp=is_temp, is_private=resolved_private)


def get_drafts(client: VelogClient, *, limit: int = 20) -> VelogPostList:
    """로그인한 사용자의 임시저장(초안) 글 목록.

    서버는 초안을 한 번에 100개까지 준다 (velog-server `findTempPosts` 의 `take: limit`, 소스 기준). 다음 페이지(`--cursor`)를
    두지 않는 것은 일부러다. 같은 소스에서 커서는 `released_at` 으로 거르는데 정렬은 `created_at` 이라, 둘이 다른 초안은
    건너뛰거나 되풀이될 수 있고, 초안이 없는 계정이라 실측하지 못했다 (2026-10-23). 공개 글의 v2 `posts` 는 마지막 글 id 커서로
    이어졌다 (같은 날 실측).

    Raises:
        VeloggerError: 로그인 안 됨 (`NOT_LOGGED_IN`).
    """
    user = require_auth(client)
    data = graphql_data(client.run_request_drafts(user.username or '', limit))
    return post_list_of(data.posts if data else None)


def like_post(client: VelogClient, post_id: str) -> VelogLikeResult:
    """글에 좋아요. 로그인 안 됐으면 `NOT_LOGGED_IN`."""
    require_auth(client)  # v2 프록시라 토큰을 먼저 갱신한다 (만료된 토큰이면 errors 없이 null)
    data = graphql_data(client.run_request_like_post(post_id))
    result = _written(data.like_post if data else None, '좋아요(likePost)')
    return VelogLikeResult(id=result.id or post_id, likes=result.likes, liked=result.liked)


def unlike_post(client: VelogClient, post_id: str) -> VelogLikeResult:
    """글 좋아요 취소."""
    require_auth(client)  # v2 프록시라 토큰을 먼저 갱신한다 (만료된 토큰이면 errors 없이 null)
    data = graphql_data(client.run_request_unlike_post(post_id))
    result = _written(data.unlike_post if data else None, '좋아요 취소(unlikePost)')
    return VelogLikeResult(id=result.id or post_id, likes=result.likes, liked=result.liked)


def write_comment(client: VelogClient, post_id: str, text: str, *, comment_id: str | None = None) -> VelogCommentResult:
    """글에 댓글(또는 대댓글)을 단다.

    앞에 `require_auth` 를 두지 않는 것은 일부러다. writeComment 는 v2 가 직접 처리해(프록시가 아니다), 만료된
    access_token 도 같은 요청 안에서 refresh_token 으로 갱신하고 성공하며, 로그인이 안 됐으면 UNAUTHENTICATED 를
    준다 (2026-10-20 실측: 13시간 전 만료된 토큰으로 댓글이 달리고 Set-Cookie 로 새 토큰이 왔다).
    """
    data = graphql_data(client.run_request_write_comment(
        VelogWriteCommentRequestPayloadModel(post_id=post_id, text=text, comment_id=comment_id)
    ))
    result = _written(data.write_comment if data else None, '댓글 작성(writeComment)')
    return VelogCommentResult(id=result.id, text=result.text, replies_count=result.replies_count)


def edit_comment(client: VelogClient, comment_id: str, text: str) -> VelogCommentResult:
    """내 댓글 내용을 고친다. 빈 내용은 요청 모델이 막는다 (velog 는 빈 댓글로 저장한다).

    앞에 `require_auth` 를 두지 않는 것은 일부러다 (`write_comment` 와 같다). editComment·removeComment·createSeries·
    appendToSeries 는 v2 가 직접 처리해, 만료된 access_token 도 같은 요청 안에서 refresh_token 으로 갱신하고 로그인이 안
    됐으면 UNAUTHENTICATED 를 준다 (2026-10-21 실측: access_token 을 뺀 세션으로 appendToSeries·editComment 를 보내니 로그인
    판정을 지나 Set-Cookie 로 새 토큰이 왔다. velog-server 는 모든 요청 앞에서 `consumeUser` 미들웨어가 토큰을 갱신한다).
    """
    payload = VelogEditCommentRequestPayloadModel(id=comment_id, text=text)
    data = graphql_data(client.run_request_edit_comment(payload))
    result = _written(data.edit_comment if data else None, '댓글 수정(editComment)')
    return VelogCommentResult(id=result.id or comment_id, text=result.text)


def remove_comment(client: VelogClient, comment_id: str) -> VelogCommentRemoveResult:
    """내 댓글을 지운다 (되돌릴 수 없다. CLI 는 `--yes` 를 받은 뒤에만 부른다).

    `require_auth` 를 두지 않는 이유는 `edit_comment` 와 같다.
    """
    data = graphql_data(client.run_request_remove_comment(comment_id))
    removed = _written(data.remove_comment if data else None, '댓글 삭제(removeComment)')
    return VelogCommentRemoveResult(comment_id=comment_id, removed=bool(removed))


def _resolve_user_id(client: VelogClient, username: str) -> str:
    """username 을 사용자 ID 로 바꾼다 (follow·unfollow 는 ID 를 받는다).

    Raises:
        VeloggerError: 사용자가 없을 때 (`NOT_FOUND`).
    """
    data = graphql_data(client.run_request_user_id(VelogGetUserRequestPayloadModel(username=username)))
    user_id = data.user.id if data and data.user else None
    if not user_id:
        raise VeloggerError(
            code='NOT_FOUND',
            message=f'사용자를 찾지 못했습니다: @{username}',
            hint='username(@ 뒤 아이디)이 맞는지 확인하세요',
        )
    return user_id


def follow_user(client: VelogClient, username: str) -> VelogFollowResult:
    """사용자를 팔로우한다 (username 을 ID 로 바꿔서 보낸다)."""
    require_auth(client)
    user_id = _resolve_user_id(client, username)
    data = graphql_data(client.run_request_follow(user_id))
    result = _written(data.follow if data else None, '팔로우(follow)')
    return VelogFollowResult(username=username, user_id=user_id, is_followed=result.is_followed)


def unfollow_user(client: VelogClient, username: str) -> VelogFollowResult:
    """사용자 팔로우를 끊는다."""
    require_auth(client)
    user_id = _resolve_user_id(client, username)
    data = graphql_data(client.run_request_unfollow(user_id))
    result = _written(data.unfollow if data else None, '팔로우 취소(unfollow)')
    return VelogFollowResult(username=username, user_id=user_id, is_followed=result.is_followed)


def create_series(client: VelogClient, name: str, *, url_slug: str | None = None) -> VelogSeriesCreateResult:
    """시리즈를 만든다. slug 를 안 주면 이름에서 만든다. `require_auth` 를 두지 않는 이유는 `edit_comment` 와 같다.

    Raises:
        VeloggerError: 같은 slug 의 시리즈가 이미 있을 때 (`ALREADY_EXISTS`).
    """
    payload = VelogCreateSeriesRequestPayloadModel(name=name, url_slug=url_slug or slugify(name))
    data = graphql_data(client.run_request_create_series(payload))
    series = _written(data.create_series if data else None, '시리즈 만들기(createSeries)')
    return VelogSeriesCreateResult(
        id=series.id, name=series.name or payload.name, url_slug=series.url_slug or payload.url_slug,
    )


def add_to_series(client: VelogClient, series_id: str, post_id: str) -> VelogSeriesAddResult:
    """시리즈 맨 뒤에 글을 넣는다. `require_auth` 를 두지 않는 이유는 `edit_comment` 와 같다.

    Raises:
        VeloggerError: 이미 그 시리즈에 든 글일 때 (`ALREADY_EXISTS`).
    """
    data = graphql_data(client.run_request_append_to_series(series_id, post_id))
    index = _written(data.append_to_series if data else None, '시리즈에 넣기(appendToSeries)')
    return VelogSeriesAddResult(series_id=series_id, post_id=post_id, added=True, index=index)


def _image_format(content: bytes) -> str | None:
    """파일 내용으로 본 이미지 형식 (`IMAGE_SIGNATURES`·`SVG_PATTERN`). 이미지가 아니면 None."""
    for name, parts in IMAGE_SIGNATURES:
        if all(content[offset:offset + len(magic)] == magic for offset, magic in parts):
            return name
    if SVG_PATTERN.match(content):
        return 'SVG'
    return None


def upload_image(client: VelogClient, path: Path, *, post_id: str) -> VelogUploadResult:
    """이미지를 velog 에 올리고 글 본문에 쓸 URL 을 돌려준다.

    velog 는 이미지가 들어갈 내 글(`post_id`, 초안이어도 된다)이 아니면 올리는 것을 막는다 (403. velog-server 는 그 글의
    주인을 본다). 그래서 이미지가 들어갈 글을 먼저 초안으로 만들고 그 id 로 올린다. 응답 모양이 velog 쪽 사정으로 바뀔 수
    있어, URL 로 보이는 값을 찾아서 낸다.

    파일은 네트워크 전에 읽고 이미지인지 내용으로 본다 (`_image_format`: velog 는 아무 파일이나 공개 URL 로 올린다).
    `require_auth` 를 두지 않는 것은 일부러다. 업로드도 v2 가 직접 처리해 같은 요청 안에서 토큰을 갱신하고, 로그인이 안
    됐으면 401 을 준다 (velog-server `consumeUser`·`authorized` 미들웨어, 2026-10-21 실측: 세션 없이 보내니 401
    `NOT_AUTHORIZED`).

    Raises:
        VeloggerError: 파일을 읽지 못하거나 이미지가 아닐 때(`INVALID_ARGUMENT`), 로그인 안 됨(`NOT_LOGGED_IN`), 내 글이
            아닐 때(`FORBIDDEN`), 응답에서 URL 을 찾지 못했을 때(`PARSE_ERROR`).
    """
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise VeloggerError(
            code='INVALID_ARGUMENT',
            message=f'이미지 파일을 읽을 수 없습니다: {path} ({type(exc).__name__})',
            hint='경로가 맞는지 확인하세요',
        ) from exc
    if _image_format(content) is None:
        raise VeloggerError(
            code='INVALID_ARGUMENT',
            message=f'이미지 파일이 아닙니다: {path}',
            hint=f'{IMAGE_FORMATS_TEXT} 이미지만 올립니다. 올린 파일은 누구나 볼 수 있는 주소가 되니 이미지가 아닌 파일은 넘기지 마세요',
        )
    try:
        response = client.run_request_upload_image(path.name, content, ref_id=post_id)
    except HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise not_logged_in_error() from exc
        if exc.response.status_code == 403:
            raise VeloggerError(
                code='FORBIDDEN',
                message=f'없는 글이거나 내 글이 아니라 이미지를 올릴 수 없습니다: {post_id}',
                hint='--post 에는 내 글(초안 포함)의 id 를 줍니다. 새 글이면 publish 로 초안을 먼저 만들어 그 id 를 쓰세요',
            ) from exc
        raise
    try:
        body = response.json()
    except ValueError:
        body = response.text.strip()
    url: object = None
    if isinstance(body, dict):
        for key in ('path', 'url', 'src', 'image'):
            if isinstance(body.get(key), str) and body[key].startswith('http'):
                url = body[key]
                break
    elif isinstance(body, str) and body.startswith('http'):
        url = body
    if not isinstance(url, str):
        raise VeloggerError(
            code='PARSE_ERROR',
            message='업로드 응답에서 이미지 URL 을 찾지 못했습니다',
            hint='velog 응답 형식이 바뀌었을 수 있습니다. VELOGGER_DEBUG=1 로 원본 응답을 확인하세요',
        )
    alt = MARKDOWN_ALT_SPECIAL.sub(r'\\\1', path.stem)
    return VelogUploadResult(filename=path.name, url=url, markdown=f'![{alt}]({url})')


def get_stats(client: VelogClient, post_id: str) -> VelogStatsResult:
    """본인 글의 조회수 통계 (전체 + 일별).

    getStats 는 v2 가 직접 처리해 토큰을 같은 요청 안에서 갱신하고, 로그인이 안 됐으면 UNAUTHENTICATED 를 준다
    (2026-10-20 실측). 그래서 앞에 `require_auth` 를 두지 않는다.

    `getStats: null` 을 `_written` 처럼 에러로 바꾸지 않는 것도 일부러다. 실패는 모두 errors 로 온다: 없는 글은
    NOT_FOUND, 남의 글은 NO_PERMISSION(`FORBIDDEN`), 내 글은 값 (2026-10-20 실측. velog-server 리졸버도 객체를 주거나
    던진다). 쓰기가 아니라 '반영 안 됨' 걱정도 없어, 혹시 errors 없이 null 이 와도 '모름'(`total: null`)으로 낸다.

    Raises:
        VeloggerError: 로그인 안 됨 (`NOT_LOGGED_IN`), 없는 글일 때 (`NOT_FOUND`), 남의 글일 때 (`FORBIDDEN`).
    """
    data = graphql_data(client.run_request_get_stats(post_id))
    stats = data.get_stats if data else None
    if stats is None:
        return VelogStatsResult()
    days = None if stats.count_by_day is None else [
        VelogStatsDay(day=day.day, count=day.count) for day in stats.count_by_day
    ]
    return VelogStatsResult(total=stats.total, count_by_day=days)
