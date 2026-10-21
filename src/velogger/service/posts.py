"""글 목록 조회 (`trending`·`recent`·`search`·`posts`·`tag`)."""

from velogger.api.client import VelogClient
from velogger.api.request.cache import (
    Timeframe,
    VelogTagPostsRequestParameterModel,
    VelogTrendingPostsRequestParameterModel,
)
from velogger.api.request.posts import (
    VelogPostsRequestPayloadModel,
    VelogRecentPostsRequestPayloadModel,
    VelogSearchPostsRequestPayloadModel,
)
from velogger.service.common import (
    VelogPostList,
    graphql_data,
    post_list_of,
    summary_of_cache,
    summary_of_card,
)


def get_trending(client: VelogClient, *, timeframe: Timeframe = 'week', limit: int = 20, offset: int = 0) -> VelogPostList:
    """트렌딩 글 (캐시 REST). 기간은 day·week·month·year."""
    posts = client.run_request_trending_posts(
        VelogTrendingPostsRequestParameterModel(timeframe=timeframe, limit=limit, offset=offset)
    )
    summaries = [summary_of_cache(post) for post in posts]
    return VelogPostList(returned=len(summaries), posts=summaries)


def get_recent(client: VelogClient, *, limit: int = 20, cursor: str | None = None) -> VelogPostList:
    """최신 글 (v3). 상단에 스팸이 끼기도 하나 서버 결과를 임의로 거르지 않는다."""
    data = graphql_data(client.run_request_recent_posts(VelogRecentPostsRequestPayloadModel(limit=limit, cursor=cursor)))
    return post_list_of(data.recent_posts if data else None)


def search_posts(
    client: VelogClient,
    keyword: str,
    *,
    username: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> VelogPostList:
    """글 검색 (v3). `username` 을 주면 그 사용자 글만. `count` 로 전체 결과 수를 알려 준다."""
    data = graphql_data(client.run_request_search_posts(
        VelogSearchPostsRequestPayloadModel(keyword=keyword, username=username, offset=offset, limit=limit)
    ))
    result = data.search_posts if data else None
    cards = (result.posts if result else None) or []
    summaries = [summary_of_card(card) for card in cards]
    return VelogPostList(returned=len(summaries), count=result.count if result else None, posts=summaries)


def get_user_posts(
    client: VelogClient,
    username: str,
    *,
    tag: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> VelogPostList:
    """한 사용자의 글 목록 (v3). `tag` 는 그 사용자 글 안에서 거른다 (전역 태그 검색은 `get_tag_posts`)."""
    data = graphql_data(client.run_request_posts(
        VelogPostsRequestPayloadModel(username=username, tag=tag, cursor=cursor, limit=limit)
    ))
    return post_list_of(data.posts if data else None)


def get_tag_posts(client: VelogClient, tag: str, *, limit: int = 20, cursor: str | None = None) -> VelogPostList:
    """태그별 글 (캐시 REST). GraphQL 로는 빈 배열이라 캐시를 쓴다. `count`·`next_cursor` 를 함께 준다."""
    response = client.run_request_tag_posts(VelogTagPostsRequestParameterModel(tag=tag, limit=limit, cursor=cursor))
    summaries = [summary_of_cache(post) for post in response.posts or []]
    return VelogPostList(
        returned=len(summaries),
        count=response.count,
        next_cursor=response.next_cursor,
        posts=summaries,
    )
