"""댓글 읽기·시리즈·팔로우·피드·좋아요 목록 (`comments`·`series`·`followers`·`followings`·`feed`·`liked`)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from velogger.api.client import VelogClient
from velogger.api.request.social import (
    ReadingListType,
    VelogFeedPostsRequestPayloadModel,
    VelogFollowListRequestPayloadModel,
    VelogReadingListRequestPayloadModel,
    VelogSeriesRequestPayloadModel,
)
from velogger.api.response.posts import VelogPostCardModel
from velogger.api.response.social import (
    VelogCommentModel,
    VelogFollowUserModel,
)
from velogger.core.errors import VeloggerError
from velogger.service.common import (
    VELOG_BASE,
    VelogPostList,
    VelogPostSummary,
    collect_pages,
    graphql_data,
    paged_post_list_of,
    post_list_of,
    post_url,
    require_auth,
    series_url,
    summary_of_card,
)

from typing import (
    Annotated,
    Any,
)


# 한 번에 받는 수의 서버 상한. v3 `followers`·`followings` 와 v2 `readingList` 는 100개까지 준다 (2026-10-23 실측: velopert
# 팔로워 limit 100 에 100명, 읽은 글 100개. readingList 는 velog-server 소스로도 100 을 넘으면 'Max limit is 100'). CLI
# `--limit` 최대와 같아 한 번에 받는다. 커서는 `collect_pages` 가 이어 받는다.
FOLLOW_LIST_PAGE_SIZE: int = 100
READING_LIST_PAGE_SIZE: int = 100


class VelogComment(BaseModel):
    """댓글 하나. 삭제된 댓글은 velog 가 내용을 주지 않아 `deleted: true` 로만 온다.

    `replies` 는 `--replies` 로 대댓글을 받았을 때만 키가 있다 (안 받았으면 해당 없음이라 키를 뺀다).
    """

    model_config = ConfigDict(extra='forbid')

    id: Annotated[str | None, Field(description='댓글 ID (edit·remove 에 쓴다)')] = None
    username: Annotated[str | None, Field(description='작성자 아이디')] = None
    display_name: Annotated[str | None, Field(description='작성자 표시 이름')] = None
    text: Annotated[str | None, Field(description='내용')] = None
    created_at: Annotated[str | None, Field(description='작성 시각 (ISO)')] = None
    replies_count: Annotated[int | None, Field(description='대댓글 수')] = None
    deleted: Annotated[bool | None, Field(description='삭제된 댓글인지')] = None
    replies: Annotated[
        list['VelogComment'] | None,
        Field(description='대댓글 (--replies 일 때만 키가 있다). 대댓글의 대댓글도 같은 모양으로 담는다 (velog 는 2단계까지)')
    ] = None

    @model_serializer(mode='wrap')
    def _drop_unrequested_replies(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if 'replies' not in self.model_fields_set:
            data.pop('replies', None)
        return data


class VelogCommentList(BaseModel):
    """글 하나의 댓글 목록."""

    model_config = ConfigDict(extra='forbid')

    post_id: Annotated[str | None, Field(description='글 ID')] = None
    comments_count: Annotated[int | None, Field(description='velog 가 세는 전체 댓글 수 (대댓글 포함)')] = None
    returned: Annotated[int, Field(description='이번에 반환한 최상위 댓글 수')]
    comments: Annotated[list[VelogComment], Field(description='최상위 댓글')]


class VelogSeriesDetail(BaseModel):
    """시리즈와 그 안의 글 (순서대로)."""

    model_config = ConfigDict(extra='forbid')

    id: Annotated[str | None, Field(description='시리즈 ID (series-add 에 쓴다)')] = None
    name: Annotated[str | None, Field(description='시리즈 이름')] = None
    username: Annotated[str | None, Field(description='시리즈 주인')] = None
    url: Annotated[str | None, Field(description='시리즈 주소')] = None
    returned: Annotated[int, Field(description='시리즈 안 글 수')]
    posts: Annotated[list[VelogPostSummary], Field(description='순서대로의 글')]
    notes: Annotated[
        list[str],
        Field(exclude=True, description='뺀 항목 안내. CLI 가 emit 의 notes 로 맨 앞에 붙인다')
    ] = []


class VelogFollowUser(BaseModel):
    """팔로워·팔로잉 목록의 한 명."""

    model_config = ConfigDict(extra='forbid')

    user_id: Annotated[str | None, Field(description='사용자 ID (follow·unfollow 에 쓴다)')] = None
    username: Annotated[str | None, Field(description='아이디 (@username)')] = None
    display_name: Annotated[str | None, Field(description='표시 이름')] = None
    short_bio: Annotated[str | None, Field(description='한 줄 소개')] = None
    url: Annotated[str | None, Field(description='블로그 주소')] = None
    is_followed: Annotated[bool | None, Field(description='내가 팔로우 중인지 (로그인 시)')] = None


class VelogFollowList(BaseModel):
    """팔로워·팔로잉 목록."""

    model_config = ConfigDict(extra='forbid')

    returned: Annotated[int, Field(description='반환한 사람 수')]
    next_cursor: Annotated[str | None, Field(description='다음 페이지 커서 (--cursor 로 넘긴다). null 이면 마지막 페이지')] = None
    users: Annotated[list[VelogFollowUser], Field(description='사람 목록')]


def _comment_of(model: VelogCommentModel, *, with_replies: bool = False) -> VelogComment:
    """댓글 하나. `with_replies` 면 `model.replies` 를 대댓글로, 그 대댓글의 대댓글까지 같은 모양으로 붙인다."""
    username = model.user.username if model.user else None
    display_name = model.user.profile.display_name if model.user and model.user.profile else None
    comment = VelogComment(
        id=model.id,
        username=username,
        display_name=display_name,
        text=model.text,
        created_at=model.created_at,
        replies_count=model.replies_count,
        deleted=model.deleted,
    )
    if with_replies:
        # 대댓글 수가 0 이면 비어 있음([]). 있는데 velog 가 묶음을 주지 않았으면 모름(null).
        # 대입해야 model_fields_set 에 들어가 키가 나온다
        comment.replies = (
            [] if not model.replies_count
            else None if model.replies is None
            else [_comment_of(reply, with_replies=True) for reply in model.replies]
        )
    return comment


def get_comments(client: VelogClient, post_id: str, *, with_replies: bool = False) -> VelogCommentList:
    """글의 댓글을 읽는다 (v2 — 작성자가 채워지는 쪽).

    `with_replies` 면 대댓글이 있는 최상위 댓글마다 한 번씩 더 조회한다 (요청이 댓글 수만큼 늘어난다). 한 번의 조회로
    대댓글의 대댓글(level 2, velog 의 최대 단계)까지 받는다.

    Raises:
        VeloggerError: 글이 없을 때 (`NOT_FOUND`).
    """
    data = graphql_data(client.run_request_post_comments(post_id))
    post = data.post if data else None
    if post is None:
        raise VeloggerError(
            code='NOT_FOUND',
            message=f'글을 찾지 못했습니다: {post_id}',
            hint='목록·post 결과의 id 를 그대로 쓰세요',
        )
    comments: list[VelogComment] = []
    for model in post.comments or []:
        if with_replies and model.replies_count and model.id:
            reply_data = graphql_data(client.run_request_comment_replies(model.id))
            found = reply_data.comment if reply_data else None
            model = model.model_copy(update={'replies': found.replies if found else None})
        comments.append(_comment_of(model, with_replies=with_replies))
    return VelogCommentList(
        post_id=post.id or post_id,
        comments_count=post.comments_count,
        returned=len(comments),
        comments=comments,
    )


def get_series(client: VelogClient, username: str, url_slug: str) -> VelogSeriesDetail:
    """시리즈와 그 안의 글을 순서대로 조회한다.

    Raises:
        VeloggerError: 시리즈가 없을 때 (`NOT_FOUND`).
    """
    data = graphql_data(client.run_request_series(
        VelogSeriesRequestPayloadModel(username=username, url_slug=url_slug)
    ))
    series = data.series if data else None
    if series is None:
        raise VeloggerError(
            code='NOT_FOUND',
            message=f'시리즈를 찾지 못했습니다: @{username}/series/{url_slug}',
            hint='velogger user <username> 결과의 series 에서 url 끝부분(slug)을 확인하세요',
        )
    entries = sorted(series.series_posts or [], key=lambda entry: entry.index if entry.index is not None else 0)
    posts: list[VelogPostSummary] = []
    skipped = 0
    for entry in entries:
        if entry.post is None:
            # 글 정보 없이 온 칸은 순서만 있고 무슨 글인지 알 수 없어 뺀다. 뺐다는 사실은 notes 로 알린다
            skipped += 1
            continue
        summary = summary_of_card(entry.post)
        # 시리즈 글 카드에는 글쓴이가 없다. 시리즈 주인이 글쓴이다.
        summary.username = summary.username or username
        summary.url = summary.url or post_url(username, entry.post.url_slug)
        posts.append(summary)
    return VelogSeriesDetail(
        id=series.id,
        name=series.name,
        username=username,
        url=series_url(username, url_slug),
        returned=len(posts),
        posts=posts,
        notes=[f'velog 가 글 정보를 주지 않은 시리즈 항목 {skipped}개를 뺐습니다'] if skipped else [],
    )


def get_reading_list(
    client: VelogClient,
    *,
    list_type: ReadingListType = 'LIKED',
    limit: int = 20,
    cursor: str | None = None,
) -> VelogPostList:
    """로그인한 사용자가 좋아요한 글(LIKED)이나 읽은 글(READ) 목록. 세션이 필요하다. 다음 페이지는 `next_cursor` 로 받는다.

    readingList 는 v2 가 직접 처리해, 만료된 토큰도 같은 요청 안에서 갱신하고 로그인이 안 됐으면 UNAUTHENTICATED 를
    준다 (2026-10-20 실측). 그래서 앞에 `require_auth` 를 두지 않는다.
    """
    def fetch(size: int, after: str | None) -> list[VelogPostCardModel] | None:
        data = graphql_data(client.run_request_reading_list(
            VelogReadingListRequestPayloadModel(type=list_type, limit=size, cursor=after)
        ))
        return data.reading_list if data else None

    cards, next_cursor = collect_pages(
        fetch, limit=limit, page_size=READING_LIST_PAGE_SIZE, cursor=cursor, cursor_of=lambda card: card.id,
    )
    return paged_post_list_of(cards, next_cursor)


def get_feed(client: VelogClient, *, limit: int = 20) -> VelogPostList:
    """내가 팔로우한 사람들의 최신 글. 세션이 필요하다.

    v3 feedPosts 는 로그인이 안 됐어도 에러 없이 `[]` 를 준다 (2026-10-20 실측). 그대로 두면 무효한 세션이 '피드가
    비었다' 로 보이므로 `require_auth` 로 먼저 막는다. 토큰 갱신 때문은 아니다 — v3 도 만료된 access_token 을 같은
    요청 안에서 갱신한다 (같은 날 실측).

    다음 페이지(`--cursor`)를 두지 않는 것은 일부러다. `FeedPostsInput` 에 cursor 는 있지만 커서가 무엇인지 확인하지 못했다
    (2026-10-23: 확인한 계정이 아무도 팔로우하지 않아 피드가 비었고, v3 는 소스가 공개돼 있지 않다). 확인하지 않은 커서를 내면
    글을 건너뛰거나 되풀이해도 알 수 없어, 확인할 때까지 첫 `--limit` 개만 준다.
    """
    require_auth(client)
    data = graphql_data(client.run_request_feed_posts(VelogFeedPostsRequestPayloadModel(limit=limit)))
    return post_list_of(data.feed_posts if data else None)


def _follow_user_of(model: VelogFollowUserModel) -> VelogFollowUser:
    """팔로워·팔로잉 한 명. `user_id` 는 `userId` 만 쓴다 (`id` 는 팔로우 관계 ID 라 모르면 null 로 둔다)."""
    profile = model.profile
    return VelogFollowUser(
        user_id=model.user_id,
        username=model.username,
        display_name=profile.display_name if profile else None,
        short_bio=profile.short_bio if profile else None,
        url=f'{VELOG_BASE}/@{model.username}' if model.username else None,
        is_followed=model.is_followed,
    )


def _follow_list_of(models: list[VelogFollowUserModel], next_cursor: str | None) -> VelogFollowList:
    users = [_follow_user_of(model) for model in models]
    return VelogFollowList(returned=len(users), next_cursor=next_cursor, users=users)


def get_followers(client: VelogClient, username: str, *, limit: int = 20, cursor: str | None = None) -> VelogFollowList:
    """그 사용자를 팔로우하는 사람들. 다음 페이지는 `next_cursor` 로 받는다.

    커서는 사용자 ID 가 아니라 마지막 사람의 팔로우 관계 ID(응답 `id`)다 (2026-10-23 실측: `userId` 를 주면 404 'Invalid cursor').
    """
    def fetch(size: int, after: str | None) -> list[VelogFollowUserModel] | None:
        data = graphql_data(client.run_request_followers(
            VelogFollowListRequestPayloadModel(username=username, limit=size, cursor=after)
        ))
        return data.followers if data else None

    models, next_cursor = collect_pages(
        fetch, limit=limit, page_size=FOLLOW_LIST_PAGE_SIZE, cursor=cursor, cursor_of=lambda model: model.id,
    )
    return _follow_list_of(models, next_cursor)


def get_followings(client: VelogClient, username: str, *, limit: int = 20, cursor: str | None = None) -> VelogFollowList:
    """그 사용자가 팔로우하는 사람들. 커서는 `get_followers` 와 같다."""
    def fetch(size: int, after: str | None) -> list[VelogFollowUserModel] | None:
        data = graphql_data(client.run_request_followings(
            VelogFollowListRequestPayloadModel(username=username, limit=size, cursor=after)
        ))
        return data.followings if data else None

    models, next_cursor = collect_pages(
        fetch, limit=limit, page_size=FOLLOW_LIST_PAGE_SIZE, cursor=cursor, cursor_of=lambda model: model.id,
    )
    return _follow_list_of(models, next_cursor)
