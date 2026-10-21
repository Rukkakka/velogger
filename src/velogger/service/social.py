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
    VelogSeriesRequestPayloadModel,
)
from velogger.api.response.social import VelogCommentModel
from velogger.core.errors import VeloggerError
from velogger.service.common import (
    VELOG_BASE,
    VelogPostList,
    VelogPostSummary,
    graphql_data,
    post_url,
    require_auth,
    series_url,
    summary_of_card,
)

from typing import (
    Annotated,
    Any,
)


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
    replies: Annotated[list['VelogComment'] | None, Field(description='대댓글 (--replies 일 때만 키가 있다)')] = None

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
    comments: list[VelogComment]


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
    users: list[VelogFollowUser]


def _comment_of(model: VelogCommentModel) -> VelogComment:
    username = model.user.username if model.user else None
    display_name = model.user.profile.display_name if model.user and model.user.profile else None
    return VelogComment(
        id=model.id,
        username=username,
        display_name=display_name,
        text=model.text,
        created_at=model.created_at,
        replies_count=model.replies_count,
        deleted=model.deleted,
    )


def get_comments(client: VelogClient, post_id: str, *, with_replies: bool = False) -> VelogCommentList:
    """글의 댓글을 읽는다 (v2 — 작성자가 채워지는 쪽).

    `with_replies` 면 대댓글이 있는 댓글마다 한 번씩 더 조회한다 (요청이 댓글 수만큼 늘어난다).

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
        comment = _comment_of(model)
        if with_replies:
            # 대댓글 수가 0 이면 비어 있음([]). 받으러 갔는데 velog 가 묶음을 주지 않으면 모름(null).
            replies: list[VelogComment] | None = []
            if (model.replies_count or 0) > 0 and model.id:
                reply_data = graphql_data(client.run_request_comment_replies(model.id))
                found = reply_data.comment if reply_data else None
                replies = None if found is None or found.replies is None else [_comment_of(reply) for reply in found.replies]
            comment.replies = replies  # 대입해야 model_fields_set 에 들어가 키가 나온다
        comments.append(comment)
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


def get_reading_list(client: VelogClient, *, list_type: ReadingListType = 'LIKED', limit: int = 20) -> VelogPostList:
    """로그인한 사용자가 좋아요한 글(LIKED)이나 읽은 글(READ) 목록. 세션이 필요하다.

    readingList 는 v2 가 직접 처리해, 만료된 토큰도 같은 요청 안에서 갱신하고 로그인이 안 됐으면 UNAUTHENTICATED 를
    준다 (2026-10-20 실측). 그래서 앞에 `require_auth` 를 두지 않는다.
    """
    data = graphql_data(client.run_request_reading_list(list_type, limit))
    cards = (data.reading_list if data else None) or []
    summaries = [summary_of_card(card) for card in cards]
    return VelogPostList(returned=len(summaries), posts=summaries)


def get_feed(client: VelogClient, *, limit: int = 20) -> VelogPostList:
    """내가 팔로우한 사람들의 최신 글. 세션이 필요하다.

    v3 feedPosts 는 로그인이 안 됐어도 에러 없이 `[]` 를 준다 (2026-10-20 실측). 그대로 두면 무효한 세션이 '피드가
    비었다' 로 보이므로 `require_auth` 로 먼저 막는다. 토큰 갱신 때문은 아니다 — v3 도 만료된 access_token 을 같은
    요청 안에서 갱신한다 (같은 날 실측).
    """
    require_auth(client)
    data = graphql_data(client.run_request_feed_posts(VelogFeedPostsRequestPayloadModel(limit=limit)))
    cards = (data.feed_posts if data else None) or []
    summaries = [summary_of_card(card) for card in cards]
    return VelogPostList(returned=len(summaries), posts=summaries)


def _follow_user_of(model: object) -> VelogFollowUser:
    username = getattr(model, 'username', None)
    profile = getattr(model, 'profile', None)
    return VelogFollowUser(
        user_id=getattr(model, 'user_id', None) or getattr(model, 'id', None),
        username=username,
        display_name=profile.display_name if profile else None,
        short_bio=profile.short_bio if profile else None,
        url=f'{VELOG_BASE}/@{username}' if username else None,
        is_followed=getattr(model, 'is_followed', None),
    )


def get_followers(client: VelogClient, username: str, *, limit: int = 20) -> VelogFollowList:
    """그 사용자를 팔로우하는 사람들."""
    data = graphql_data(client.run_request_followers(
        VelogFollowListRequestPayloadModel(username=username, limit=limit)
    ))
    users = [_follow_user_of(item) for item in (data.followers if data else None) or []]
    return VelogFollowList(returned=len(users), users=users)


def get_followings(client: VelogClient, username: str, *, limit: int = 20) -> VelogFollowList:
    """그 사용자가 팔로우하는 사람들."""
    data = graphql_data(client.run_request_followings(
        VelogFollowListRequestPayloadModel(username=username, limit=limit)
    ))
    users = [_follow_user_of(item) for item in (data.followings if data else None) or []]
    return VelogFollowList(returned=len(users), users=users)
