from pydantic import Field

from velogger.core.schema import RequestModel

from typing import (
    Annotated,
    Literal,
)


# 캐시 트렌딩이 받는 기간 값.
Timeframe = Literal['day', 'week', 'month', 'year']


class VelogTrendingPostsRequestParameterModel(RequestModel):
    """캐시 REST `GET cache.velcdn.com/api/trending-posts` 쿼리. 트렌딩 글."""

    timeframe: Annotated[Timeframe, Field(description='집계 기간')] = 'week'
    limit: Annotated[int, Field(ge=1, description='받을 글 수')] = 20
    offset: Annotated[int, Field(ge=0, description='건너뛸 수 (페이지)')] = 0


class VelogTagPostsRequestParameterModel(RequestModel):
    """캐시 REST `GET cache.velcdn.com/api/tag-posts` 쿼리. 태그별 글 (GraphQL 로는 빈 배열이라 캐시를 쓴다)."""

    tag: Annotated[str, Field(min_length=1, description='태그 이름')]
    limit: Annotated[int, Field(ge=1, description='받을 글 수')] = 20
    cursor: Annotated[str | None, Field(description='이전 페이지 nextCursor (다음 페이지)')] = None
