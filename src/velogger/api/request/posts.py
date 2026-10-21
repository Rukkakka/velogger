from pydantic import Field

from velogger.core.schema import RequestModel

from typing import Annotated


class VelogRecentPostsRequestPayloadModel(RequestModel):
    """v3 `recentPosts(input: RecentPostsInput!)` 의 input. 최신 글 목록."""

    limit: Annotated[int, Field(ge=1, description='받을 글 수')] = 20
    cursor: Annotated[str | None, Field(description='이전 페이지 마지막 글 id (다음 페이지)')] = None


class VelogSearchPostsRequestPayloadModel(RequestModel):
    """v3 `searchPosts(input: GetSearchPostsInput!)` 의 input. 글 검색."""

    keyword: Annotated[str, Field(min_length=1, description='검색어')]
    username: Annotated[str | None, Field(description='이 사용자의 글만 검색')] = None
    offset: Annotated[int, Field(ge=0, description='건너뛸 수 (페이지)')] = 0
    limit: Annotated[int, Field(ge=1, description='받을 글 수')] = 20


class VelogPostsRequestPayloadModel(RequestModel):
    """v3 `posts(input: GetPostsInput!)` 의 input. 한 사용자의 글 목록.

    `tag` 로 전역 태그 검색은 velog 가 빈 배열을 주므로(태그별 글은 캐시 `tag-posts` 를 쓴다) username 과 함께만 쓴다.
    """

    username: Annotated[str, Field(description='글쓴이 아이디 (@username)')]
    tag: Annotated[str | None, Field(description='이 사용자 글 중 태그 필터')] = None
    cursor: Annotated[str | None, Field(description='이전 페이지 마지막 글 id (다음 페이지)')] = None
    limit: Annotated[int, Field(ge=1, description='받을 글 수')] = 20


class VelogReadPostRequestPayloadModel(RequestModel):
    """v3 `post(input: ReadPostInput!)` 의 input. 글 하나 상세(본문 포함)."""

    username: Annotated[str, Field(description='글쓴이 아이디 (@username)')]
    url_slug: Annotated[str, Field(description='글 url_slug (글 목록의 url_slug)')]
