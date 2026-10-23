from pydantic import Field

from velogger.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


# v2 `readingList` 가 받는 목록 종류.
ReadingListType = Literal['LIKED', 'READ']


class VelogFollowListRequestPayloadModel(RequestModel):
    """v3 `followers`·`followings(input: GetFollowInput!)` 의 input."""

    username: Annotated[str, Field(description='대상 사용자 아이디 (@username)')]
    limit: Annotated[int, Field(ge=1, description='받을 사람 수')] = 20
    cursor: Annotated[
        str | None,
        Field(description='이전 페이지 마지막 사람의 팔로우 관계 id (응답 `id`). 사용자 id(`userId`)를 주면 404 Invalid cursor')
    ] = None


class VelogFeedPostsRequestPayloadModel(RequestModel):
    """v3 `feedPosts(input: FeedPostsInput!)` 의 input. 내가 팔로우한 사람들의 글 (로그인 필요)."""

    limit: Annotated[int, Field(ge=1, description='받을 글 수')] = 20
    cursor: Annotated[str | None, Field(description='다음 페이지 커서')] = None


class VelogReadingListRequestPayloadModel(RequestModel):
    """v2 `readingList(type, cursor, limit)` 변수. 로그인한 사용자가 좋아요한 글(LIKED)이나 읽은 글(READ)."""

    type: Annotated[ReadingListType, Field(description='목록 종류')] = 'LIKED'
    limit: Annotated[int, Field(ge=1, le=100, description="받을 글 수 (velog-server 는 100 을 넘으면 'Max limit is 100')")] = 20
    cursor: Annotated[
        str | None,
        Field(description='이전 페이지 마지막 글 id (READ 는 2026-10-23 실측, LIKED 는 velog-server `readingList` 소스 기준)')
    ] = None


class VelogSeriesRequestPayloadModel(RequestModel):
    """v2 `series(username, url_slug)` 변수."""

    username: Annotated[str, Field(description='시리즈 주인 아이디 (@username)')]
    url_slug: Annotated[str, Field(description='시리즈 slug (user 결과 series 의 url 끝부분)')]
