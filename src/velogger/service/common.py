"""두 모듈 이상이 쓰는 결과 모델·변환·GraphQL 에러 처리."""

import re
from collections.abc import Callable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from velogger.api.client import VelogClient
from velogger.api.response.auth import VelogAuthUserModel
from velogger.api.response.cache import VelogCachePostModel
from velogger.api.response.common import (
    VelogGraphQLErrorModel,
    VelogGraphQLResponse,
)
from velogger.api.response.posts import VelogPostCardModel
from velogger.core.errors import VeloggerError

from typing import (
    Annotated,
    Any,
    TypeVar,
)


_Data = TypeVar('_Data')
_Item = TypeVar('_Item')

VELOG_BASE: str = 'https://velog.io'
UNAUTHENTICATED_CODE: str = 'UNAUTHENTICATED'
NOT_FOUND_CODE: str = 'NOT_FOUND'
NO_PERMISSION_CODE: str = 'NO_PERMISSION'
# 대상이 없을 때 v2 가 주는 에러. `extensions.code` 가 NOT_FOUND 이거나(writeComment·getStats·appendToSeries 의
# 'Post not found'·'Series not found'), INTERNAL_SERVER_ERROR 에 메시지만 'Comment not found' 로 온다
# (editComment·removeComment). 2026-10-20 실측 (없는 ID 로 각 mutation 을 보냄).
NOT_FOUND_MESSAGE_PATTERN: re.Pattern[str] = re.compile(r'\bnot found\b', re.IGNORECASE)
# 남의 글·댓글·시리즈에 보낸 요청. getStats 는 NO_PERMISSION 코드에 'This post is not yours' 를 준다 (2026-10-20 실측).
# velog-server 소스로는 editComment·removeComment 가 코드 없이 'No permission' 을, 시리즈가 'This series is not yours' 를 준다.
NO_PERMISSION_MESSAGE_PATTERN: re.Pattern[str] = re.compile(r'\bno permission\b|\bnot yours\b', re.IGNORECASE)
# velog-server 는 일부 요청에서 로그인 안 됨을 UNAUTHENTICATED 가 아니라 NO_PERMISSION + 'Not logged in' 으로 준다
NOT_LOGGED_IN_MESSAGE_PATTERN: re.Pattern[str] = re.compile(r'\bnot logged in\b', re.IGNORECASE)
# 이미 있는 것과 겹쳐 거절된 요청. createSeries 의 같은 slug 는 ALREADY_EXISTS 'URL Slug already exists' (2026-10-21 실측),
# appendToSeries 의 이미 든 글은 CONFLICT 'Already added to series' (같은 날 실측)
ALREADY_EXISTS_CODES: frozenset[str] = frozenset({'ALREADY_EXISTS', 'CONFLICT'})
# velog 가 입력이 잘못됐다고 거절한 요청 (velog-server 리졸버의 'Maximum comment level is 2'·'Max limit is 100' 등).
# 2026-10-21 실측: level 2 대댓글에 --reply-to 로 답글을 달면 BAD_REQUEST 'Maximum comment level is 2'
BAD_REQUEST_CODE: str = 'BAD_REQUEST'
NOT_LOGGED_IN_HINT: str = '사용자가 터미널에서 `velogger login` 을 직접 실행해 로그인해야 합니다'


def not_logged_in_error(message: str = '로그인이 필요한 기능입니다') -> VeloggerError:
    """`NOT_LOGGED_IN` 에러. 힌트는 늘 같다: 에이전트가 아니라 사용자가 직접 로그인한다 (AGENTS.md '꼭 지킬 것')."""
    return VeloggerError(code='NOT_LOGGED_IN', message=message, hint=NOT_LOGGED_IN_HINT)


def post_url(username: str | None, url_slug: str | None) -> str | None:
    """글 주소 `https://velog.io/@{username}/{url_slug}`. 둘 중 하나라도 없으면 None."""
    if not username or not url_slug:
        return None
    return f'{VELOG_BASE}/@{username}/{url_slug}'


def series_url(username: str | None, url_slug: str | None) -> str | None:
    """시리즈 주소 `https://velog.io/@{username}/series/{url_slug}`. 둘 중 하나라도 없으면 None."""
    if not username or not url_slug:
        return None
    return f'{VELOG_BASE}/@{username}/series/{url_slug}'


def edit_url(post_id: str | None) -> str | None:
    """초안을 이어 쓰는 편집 주소 `https://velog.io/write?id={post_id}`. 초안의 공개 주소(`post_url`)는 404 다."""
    return f'{VELOG_BASE}/write?id={post_id}' if post_id else None


def _is_login_error(error: VelogGraphQLErrorModel) -> bool:
    return (
        (error.extensions or {}).get('code') == UNAUTHENTICATED_CODE
        or bool(NOT_LOGGED_IN_MESSAGE_PATTERN.search(error.message or ''))
    )


def graphql_data(response: VelogGraphQLResponse[_Data]) -> _Data | None:
    """GraphQL 봉투에서 `data` 를 꺼낸다. `errors` 가 있으면 에러로 바꾼다 (조회에는 UNAUTHENTICATED 가 안 온다).

    Raises:
        VeloggerError: `errors` 가 있을 때. UNAUTHENTICATED 면 `NOT_LOGGED_IN`, 대상이 없으면 `NOT_FOUND`,
            남의 글·댓글·시리즈면 `FORBIDDEN`, 이미 있는 것과 겹치면 `ALREADY_EXISTS`, 입력이 잘못됐으면
            `INVALID_ARGUMENT`, 그 밖은 `UPSTREAM_ERROR`.
    """
    if response.errors:
        if any(_is_login_error(error) for error in response.errors):
            raise not_logged_in_error('로그인이 필요한 조회입니다')
        messages = '; '.join(error.message or '' for error in response.errors)
        if any(
            (error.extensions or {}).get('code') == NOT_FOUND_CODE or NOT_FOUND_MESSAGE_PATTERN.search(error.message or '')
            for error in response.errors
        ):
            # UPSTREAM_ERROR 의 '잠시 뒤 다시 시도' 힌트로 두면 에이전트가 없는 ID 로 같은 요청을 되풀이한다
            raise VeloggerError(
                code='NOT_FOUND',
                message=f'velog 가 대상을 찾지 못했습니다: {messages}',
                hint='글·댓글·시리즈 id 를 이전 결과(posts·drafts·comments·series)에서 그대로 복사했는지 확인하세요',
            )
        if any(
            (error.extensions or {}).get('code') == NO_PERMISSION_CODE or NO_PERMISSION_MESSAGE_PATTERN.search(error.message or '')
            for error in response.errors
        ):
            # 이것도 UPSTREAM_ERROR 의 '잠시 뒤 다시 시도' 로 두면 에이전트가 남의 글로 같은 요청을 되풀이한다 (2026-10-20 재현: stats)
            raise VeloggerError(
                code='FORBIDDEN',
                message=f'본인 것이 아니라 velog 가 거절했습니다: {messages}',
                hint='통계·수정·삭제는 내 글·댓글·시리즈에만 됩니다. id 가 내 것(posts <내 아이디>·drafts·comments 결과)인지 확인하세요',
            )
        if any((error.extensions or {}).get('code') in ALREADY_EXISTS_CODES for error in response.errors):
            # UPSTREAM_ERROR 의 '잠시 뒤 다시 시도' 로 두면 에이전트가 같은 slug 로 되풀이한다. 다시 보내도 결과가 같다
            raise VeloggerError(
                code='ALREADY_EXISTS',
                message=f'이미 있어 velog 가 거절했습니다: {messages}',
                hint=(
                    '같은 요청을 다시 보내지 마세요. 시리즈 slug 가 겹치면 --slug 로 다른 값을 주거나 이미 있는 시리즈를 쓰고'
                    '(velogger user <내 아이디> 의 series), 이미 시리즈에 든 글이면 그대로 두면 됩니다'
                ),
            )
        if any((error.extensions or {}).get('code') == BAD_REQUEST_CODE for error in response.errors):
            # 이것도 UPSTREAM_ERROR 의 '잠시 뒤 다시 시도' 로 두면 에이전트가 같은 요청을 되풀이한다
            raise VeloggerError(
                code='INVALID_ARGUMENT',
                message=f'velog 가 잘못된 요청이라고 거절했습니다: {messages}',
                hint=(
                    '다시 보내도 결과가 같습니다. 메시지대로 값을 고치세요. 대댓글은 2단계까지라, 대댓글의 대댓글에는 '
                    '--reply-to 로 답글을 달 수 없습니다 (그 위 대댓글에 다세요)'
                ),
            )
        raise VeloggerError(
            code='UPSTREAM_ERROR',
            message=f'velog 가 오류를 반환했습니다: {messages}',
            hint='잠시 뒤 다시 시도하거나, 계속되면 velog 응답 형식이 바뀐 것일 수 있습니다',
        )
    return response.data


def fetch_auth(client: VelogClient) -> VelogAuthUserModel | None:
    """로그인한 사용자를 조회한다. 로그인하지 않았으면 None.

    velog 는 로그인하지 않으면 `data.auth` 를 null 로 준다 (또는 UNAUTHENTICATED errors). 둘 다 None 으로
    본다. 그 밖의 GraphQL 에러는 그대로 올린다 (응답 형식이 바뀐 것일 수 있음).

    Raises:
        VeloggerError: UNAUTHENTICATED 가 아닌 GraphQL 에러가 왔을 때 (`UPSTREAM_ERROR`).
    """
    try:
        data = graphql_data(client.run_request_auth())
    except VeloggerError as exc:
        if exc.code == 'NOT_LOGGED_IN':
            return None
        raise
    return data.auth if data else None


def require_auth(client: VelogClient) -> VelogAuthUserModel:
    """로그인한 사용자를 돌려주고, 로그인하지 않았으면 에러로 막는다 (인증이 필요한 명령용).

    v2 `auth` 를 치므로 access_token 이 만료됐으면 v2 가 refresh_token 으로 새 토큰을 Set-Cookie 해 같은 클라이언트
    자에 담긴다. v2 프록시 mutation(likePost 등)·v3 처럼 요청 안에서 토큰을 갱신하지 않거나, 로그인 안 됨을
    에러로 알리지 않는 요청 앞에 부른다 (docs/development/velog-api.md '토큰 갱신과 require_auth').

    Raises:
        VeloggerError: 로그인하지 않았을 때 (`NOT_LOGGED_IN`).
    """
    user = fetch_auth(client)
    if user is None:
        raise not_logged_in_error()
    return user


class VelogPostSummary(BaseModel):
    """글 목록의 한 줄. recentPosts·searchPosts·posts·캐시 카드를 한 모양으로 정규화한다.

    `url` 로 원 글을 열고, 본문은 `velogger post <username> <url_slug>` 로 받는다. 초안(`is_temp`)은 공개 주소가
    404 라 `url` 이 편집 주소다.
    """

    model_config = ConfigDict(extra='forbid')

    id: Annotated[str | None, Field(description='글 ID')] = None
    title: Annotated[str | None, Field(description='제목')] = None
    username: Annotated[str | None, Field(description='글쓴이 아이디 (@username)')] = None
    display_name: Annotated[str | None, Field(description='글쓴이 표시 이름')] = None
    url_slug: Annotated[str | None, Field(description='글 slug (post 조회에 쓴다)')] = None
    url: Annotated[str | None, Field(description='원 글 주소')] = None
    short_description: Annotated[str | None, Field(description='미리보기 설명')] = None
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None
    tags: Annotated[list[str] | None, Field(description='태그 (주는 조회만)')] = None
    released_at: Annotated[str | None, Field(description='발행 시각 (ISO)')] = None
    updated_at: Annotated[str | None, Field(description='수정 시각 (ISO)')] = None
    likes: Annotated[int | None, Field(description='좋아요 수')] = None
    comments_count: Annotated[int | None, Field(description='댓글 수')] = None
    is_private: Annotated[bool | None, Field(description='비공개 여부')] = None
    is_temp: Annotated[bool | None, Field(description='임시저장(초안) 글인지')] = None


def summary_of_card(card: VelogPostCardModel) -> VelogPostSummary:
    """v3·v2 GraphQL 글 카드를 공통 요약으로."""
    username = card.user.username if card.user else None
    display_name = card.user.profile.display_name if card.user and card.user.profile else None
    # 초안의 공개 주소는 404 다 (2026-10-20 실측: drafts 가 준 url 로 post 를 부르면 NOT_FOUND)
    url = edit_url(card.id) if card.is_temp else post_url(username, card.url_slug)
    return VelogPostSummary(
        id=card.id,
        title=card.title,
        username=username,
        display_name=display_name,
        url_slug=card.url_slug,
        url=url,
        short_description=card.short_description,
        thumbnail=card.thumbnail,
        tags=card.tags,
        released_at=card.released_at,
        updated_at=card.updated_at,
        likes=card.likes,
        comments_count=card.comments_count,
        is_private=card.is_private,
        is_temp=card.is_temp,
    )


def summary_of_cache(post: VelogCachePostModel) -> VelogPostSummary:
    """캐시(트렌딩·태그) 글 카드를 공통 요약으로."""
    username = post.user.username if post.user else None
    display_name = post.user.display_name if post.user else None
    return VelogPostSummary(
        id=post.id,
        title=post.title,
        username=username,
        display_name=display_name,
        url_slug=post.url_slug,
        url=post_url(username, post.url_slug),
        short_description=post.short_description,
        thumbnail=post.thumbnail,
        released_at=post.released_at,
        updated_at=post.updated_at,
        likes=post.likes,
        comments_count=post.comments_count,
    )


class VelogPostList(BaseModel):
    """글 목록 결과. `returned` 는 실제 반환 수다.

    `count`·`next_cursor` 는 그 값을 주는 명령(`count` 는 search·tag, `next_cursor` 는 커서로 다음 페이지를 받는
    tag·posts·recent·liked)만 키가 있다. 다른 명령은 해당 없음이라 키를 뺀다. 늘 `null` 로 두면 '마지막 페이지' 를 뜻하는
    `next_cursor: null` 과 구별되지 않아, 페이지가 없는 명령의 결과를 '더 없음' 으로 읽게 된다.
    """

    model_config = ConfigDict(extra='forbid')

    returned: Annotated[int, Field(description='이번에 반환한 글 수')]
    count: Annotated[int | None, Field(description='전체 개수 (search·tag 만 키가 있다. null 은 모름)')] = None
    next_cursor: Annotated[
        str | None,
        Field(description='다음 페이지 커서 (tag·posts·recent·liked 만 키가 있다. null 이면 마지막 페이지)')
    ] = None
    posts: Annotated[list[VelogPostSummary], Field(description='글 목록')]

    @model_serializer(mode='wrap')
    def _drop_unsupported_paging(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        for key in ('count', 'next_cursor'):
            if key not in self.model_fields_set:
                data.pop(key, None)
        return data


def post_list_of(cards: list[VelogPostCardModel] | None) -> VelogPostList:
    """GraphQL 글 카드 목록을 페이지 정보 없는 목록 결과로. velog 가 목록을 주지 않으면(null) 빈 목록으로 낸다."""
    summaries = [summary_of_card(card) for card in cards or []]
    return VelogPostList(returned=len(summaries), posts=summaries)


def paged_post_list_of(cards: list[VelogPostCardModel], next_cursor: str | None) -> VelogPostList:
    """커서로 다음 페이지를 받는 글 목록 결과. `next_cursor` 는 null(마지막 페이지)이어도 키를 둔다."""
    summaries = [summary_of_card(card) for card in cards]
    return VelogPostList(returned=len(summaries), next_cursor=next_cursor, posts=summaries)


def collect_pages(
    fetch: Callable[[int, str | None], list[_Item] | None],
    *,
    limit: int,
    page_size: int,
    cursor: str | None,
    cursor_of: Callable[[_Item], str | None],
) -> tuple[list[_Item], str | None]:
    """커서 페이지를 `limit` 개까지 이어 받는다. (받은 항목, 다음 커서)를 돌려주고, 다음 커서가 None 이면 마지막 페이지다.

    `fetch(개수, 커서)` 는 한 페이지를 받는다. 서버가 한 번에 `page_size` 개까지만 주는 목록(v3 `posts` 는 50개)도 `--limit`
    만큼 채운다. 예전에는 `posts --limit 100` 이 말없이 50개만 줬다 (2026-10-23 실측: lcs3947 의 글 64개 중 50개).

    - 요청한 수보다 적게 오면 마지막 페이지로 보고 멈춘다 (다음 커서 None). 그래서 `page_size` 는 서버가 실제로 주는 수와
      같거나 작아야 한다. 크면 상한만큼 온 첫 페이지를 마지막으로 읽는다.
    - 요청한 수보다 많이 오면 요청한 만큼만 남기고, 남긴 마지막 항목을 커서로 쓴다. 태그로 거른 v3 `posts` 는 limit 을 무시하고
      20개를 준다 (2026-10-23 실측). 커서는 '그 항목 다음' 이라 버린 항목은 다음 페이지에 다시 온다.
    - 꽉 찬 페이지로 `limit` 을 채우면 마지막 항목의 커서를 다음 커서로 준다. 그 뒤에 글이 없으면 다음 요청이 빈 목록이다.
    - 마지막 항목에 커서가 없거나 커서가 나아가지 않으면(같은 값) 멈춘다 (같은 페이지를 되풀이하지 않게).
    """
    items: list[_Item] = []
    while len(items) < limit:
        want = min(page_size, limit - len(items))
        page = (fetch(want, cursor) or [])[:want]
        items.extend(page)
        last = cursor_of(page[-1]) if page else None
        if len(page) < want or last is None or last == cursor:
            return items, None
        cursor = last
    return items, cursor
