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
    cursor: Annotated[str | None, Field(description='다음 페이지 커서')] = None


class VelogFeedPostsRequestPayloadModel(RequestModel):
    """v3 `feedPosts(input: FeedPostsInput!)` 의 input. 내가 팔로우한 사람들의 글 (로그인 필요)."""

    limit: Annotated[int, Field(ge=1, description='받을 글 수')] = 20
    cursor: Annotated[str | None, Field(description='다음 페이지 커서')] = None


class VelogSeriesRequestPayloadModel(RequestModel):
    """v2 `series(username, url_slug)` 변수."""

    username: Annotated[str, Field(description='시리즈 주인 아이디 (@username)')]
    url_slug: Annotated[str, Field(description='시리즈 slug (user 결과 series 의 url 끝부분)')]
