"""글 하나 상세 조회 (`post`) — 본문(마크다운)과 메타·시리즈·이전/다음 글."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from velogger.api.client import VelogClient
from velogger.api.request.posts import VelogReadPostRequestPayloadModel
from velogger.api.response.common import VelogGraphQLResponse
from velogger.api.response.posts import (
    VelogLinkedPostRefModel,
    VelogReadPostDataModel,
    VelogReadPostModel,
)
from velogger.core.errors import VeloggerError
from velogger.service.common import (
    graphql_data,
    post_url,
    series_url,
)

from typing import Annotated


# 로그인한 본인이 시리즈에 든 자기 글을 읽으면 v3 가 이 필드에서 실패한다 (2026-10-21 실측, `run_request_read_post`).
# 글 데이터는 그대로 오고 시리즈 안 글 목록만 null 이다.
SERIES_POSTS_ERROR_PATH: tuple[str, ...] = ('post', 'series', 'series_posts')
SERIES_POSTS_MISSING_NOTE: str = (
    'velog 서버 오류로 시리즈 안 글 목록을 받지 못해 series.posts 가 null 입니다. '
    '목록은 velogger series <username> <시리즈 url 끝부분> 으로 받으세요'
)


class VelogLinkedRef(BaseModel):
    """이전/다음 글 참조."""

    model_config = ConfigDict(extra='forbid')

    title: Annotated[str | None, Field(description='제목')] = None
    url: Annotated[str | None, Field(description='글 주소')] = None


class VelogSeriesPostRef(BaseModel):
    """시리즈 안 글 하나."""

    model_config = ConfigDict(extra='forbid')

    title: Annotated[str | None, Field(description='제목')] = None
    url: Annotated[str | None, Field(description='글 주소')] = None


class VelogSeriesRef(BaseModel):
    """글이 속한 시리즈."""

    model_config = ConfigDict(extra='forbid')

    name: Annotated[str | None, Field(description='시리즈 이름')] = None
    url: Annotated[str | None, Field(description='시리즈 주소')] = None
    posts: Annotated[
        list[VelogSeriesPostRef] | None,
        Field(description='시리즈 안 글 (순서대로). velog 가 주지 않으면 null')
    ] = None


class VelogPostDetail(BaseModel):
    """글 상세. 본문은 `body`(마크다운이면 `is_markdown: true`)."""

    model_config = ConfigDict(extra='forbid')

    id: Annotated[str | None, Field(description='글 ID')] = None
    title: Annotated[str | None, Field(description='제목')] = None
    username: Annotated[str | None, Field(description='글쓴이 아이디')] = None
    display_name: Annotated[str | None, Field(description='글쓴이 표시 이름')] = None
    url: Annotated[str | None, Field(description='원 글 주소')] = None
    url_slug: Annotated[str | None, Field(description='글 slug')] = None
    released_at: Annotated[str | None, Field(description='발행 시각 (ISO)')] = None
    updated_at: Annotated[str | None, Field(description='수정 시각 (ISO)')] = None
    tags: Annotated[list[str] | None, Field(description='태그')] = None
    likes: Annotated[int | None, Field(description='좋아요 수')] = None
    comments_count: Annotated[int | None, Field(description='댓글 수')] = None
    is_private: Annotated[bool | None, Field(description='비공개 여부')] = None
    is_temp: Annotated[bool | None, Field(description='임시 저장 글인지')] = None
    is_markdown: Annotated[bool | None, Field(description='본문이 마크다운인지')] = None
    body: Annotated[str | None, Field(description='본문')] = None
    series: Annotated[VelogSeriesRef | None, Field(description='속한 시리즈')] = None
    previous_post: Annotated[VelogLinkedRef | None, Field(description='같은 시리즈의 이전 글')] = None
    next_post: Annotated[VelogLinkedRef | None, Field(description='같은 시리즈의 다음 글')] = None
    notes: Annotated[
        list[str],
        Field(exclude=True, description='받지 못한 항목 안내. CLI 가 emit 의 notes 로 맨 앞에 붙인다')
    ] = []


def _linked(ref: VelogLinkedPostRefModel | None) -> VelogLinkedRef | None:
    if ref is None:
        return None
    username = ref.user.username if ref.user else None
    return VelogLinkedRef(title=ref.title, url=post_url(username, ref.url_slug))


def _detail_of(post: VelogReadPostModel) -> VelogPostDetail:
    username = post.user.username if post.user else None
    display_name = post.user.profile.display_name if post.user and post.user.profile else None
    series = None
    if post.series is not None:
        series = VelogSeriesRef(
            name=post.series.name,
            url=series_url(username, post.series.url_slug),
            # v3 가 series_posts 를 null 로 줄 때만 null(모름)이다. 빈 목록은 [] 로 둔다 (값이 없을 때 규칙)
            posts=None if post.series.series_posts is None else [
                VelogSeriesPostRef(
                    title=ref.post.title if ref.post else None,
                    url=post_url(username, ref.post.url_slug) if ref.post else None,
                )
                for ref in post.series.series_posts
            ],
        )
    return VelogPostDetail(
        id=post.id,
        title=post.title,
        username=username,
        display_name=display_name,
        url=post_url(username, post.url_slug),
        url_slug=post.url_slug,
        released_at=post.released_at,
        updated_at=post.updated_at,
        tags=post.tags,
        likes=post.likes,
        comments_count=post.comments_count,
        is_private=post.is_private,
        is_temp=post.is_temp,
        is_markdown=post.is_markdown,
        body=post.body,
        series=series,
        previous_post=_linked(post.linked_posts.previous) if post.linked_posts else None,
        next_post=_linked(post.linked_posts.next) if post.linked_posts else None,
    )


def read_post(client: VelogClient, username: str, url_slug: str) -> VelogPostDetail:
    """글 본문과 메타를 조회한다 (v3).

    시리즈 안 글 목록만 실패한 응답(로그인한 본인의 시리즈 글, `SERIES_POSTS_ERROR_PATH`)은 에러로 끝내지 않고, 받은 글을
    `series.posts: null` 과 `notes` 로 낸다. 그 밖의 `errors` 는 `graphql_data` 가 판정한다.

    Raises:
        VeloggerError: 글이 없을 때 (`NOT_FOUND`).
    """
    response = client.run_request_read_post(VelogReadPostRequestPayloadModel(username=username, url_slug=url_slug))
    notes: list[str] = []
    if _only_series_posts_failed(response):
        response = response.model_copy(update={'errors': None})
        notes.append(SERIES_POSTS_MISSING_NOTE)
    data = graphql_data(response)
    if data is None or data.post is None:
        raise VeloggerError(
            code='NOT_FOUND',
            message=f'글을 찾지 못했습니다: @{username}/{url_slug}',
            hint='username 과 url_slug 가 맞는지, 비공개·삭제된 글은 아닌지 확인하세요 (목록의 username·url_slug 를 그대로 쓰세요)',
        )
    detail = _detail_of(data.post)
    detail.notes = notes
    return detail


def _only_series_posts_failed(response: VelogGraphQLResponse[VelogReadPostDataModel]) -> bool:
    """글은 왔고 `errors` 가 모두 시리즈 안 글 목록(`SERIES_POSTS_ERROR_PATH`)에서 났는지."""
    if not response.errors or response.data is None or response.data.post is None:
        return False
    return all(tuple(error.path or ())[:len(SERIES_POSTS_ERROR_PATH)] == SERIES_POSTS_ERROR_PATH for error in response.errors)
