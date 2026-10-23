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
from velogger.api.response.posts import VelogPostCardModel
from velogger.service.common import (
    VelogPostList,
    collect_pages,
    graphql_data,
    paged_post_list_of,
    summary_of_cache,
    summary_of_card,
)


# 한 번에 받는 글 수의 서버 상한. v3 `posts`(한 사용자 글)는 50개까지만 준다 (velog-server `findPostsByUserId` 의
# `Math.min(50, size)`, 2026-10-23 실측: limit 100 에 50개). `recentPosts` 는 100개까지 준다 (같은 날 실측). 커서는 둘 다
# 이전 페이지 마지막 글의 id 다 (같은 날 실측: 3개씩 두 번 받은 것이 6개 한 번 받은 것과 같았다).
USER_POSTS_PAGE_SIZE: int = 50
# `tag` 로 거르면 v3 `posts` 는 limit 을 무시하고 20개씩 준다 (2026-10-23 실측: lcs3947 의 python 글 32개를 limit 1·5·30·100 으로
# 부르니 모두 20개, 다음 커서로 12개. velog-server 의 옛 `findPostsByTag` 도 `take: 20`). 예전에는 `posts --tag --limit 4` 가 20개를,
# `--limit 100` 이 20개에서 말없이 끝났다.
USER_TAG_POSTS_PAGE_SIZE: int = 20
RECENT_POSTS_PAGE_SIZE: int = 100


def get_trending(client: VelogClient, *, timeframe: Timeframe = 'week', limit: int = 20, offset: int = 0) -> VelogPostList:
    """트렌딩 글 (캐시 REST). 기간은 day·week·month·year."""
    posts = client.run_request_trending_posts(
        VelogTrendingPostsRequestParameterModel(timeframe=timeframe, limit=limit, offset=offset)
    )
    summaries = [summary_of_cache(post) for post in posts]
    return VelogPostList(returned=len(summaries), posts=summaries)


def get_recent(client: VelogClient, *, limit: int = 20, cursor: str | None = None) -> VelogPostList:
    """최신 글 (v3). 상단에 스팸이 끼기도 하나 서버 결과를 임의로 거르지 않는다. 다음 페이지는 `next_cursor` 로 받는다."""
    def fetch(size: int, after: str | None) -> list[VelogPostCardModel] | None:
        data = graphql_data(client.run_request_recent_posts(VelogRecentPostsRequestPayloadModel(limit=size, cursor=after)))
        return data.recent_posts if data else None

    cards, next_cursor = collect_pages(
        fetch, limit=limit, page_size=RECENT_POSTS_PAGE_SIZE, cursor=cursor, cursor_of=lambda card: card.id,
    )
    return paged_post_list_of(cards, next_cursor)


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
    """한 사용자의 글 목록 (v3). `tag` 는 그 사용자 글 안에서 거른다 (전역 태그 검색은 `get_tag_posts`).

    서버가 한 번에 50개(태그로 거르면 20개)까지만 줘 `limit` 이 그보다 크면 나눠 받는다 (`USER_POSTS_PAGE_SIZE`·
    `USER_TAG_POSTS_PAGE_SIZE`). 다음 페이지는 `next_cursor` 로 받는다.
    """
    def fetch(size: int, after: str | None) -> list[VelogPostCardModel] | None:
        data = graphql_data(client.run_request_posts(
            VelogPostsRequestPayloadModel(username=username, tag=tag, cursor=after, limit=size)
        ))
        return data.posts if data else None

    page_size = USER_TAG_POSTS_PAGE_SIZE if tag else USER_POSTS_PAGE_SIZE
    cards, next_cursor = collect_pages(
        fetch, limit=limit, page_size=page_size, cursor=cursor, cursor_of=lambda card: card.id,
    )
    return paged_post_list_of(cards, next_cursor)


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
