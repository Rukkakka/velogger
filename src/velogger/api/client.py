import os
import sys
from functools import cached_property
from urllib.parse import quote

from httpx import (
    AsyncClient,
    Client,
    Cookies,
    Response,
    codes,
)
from pydantic import (
    BaseModel,
    Field,
)
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
)

from velogger.api.request.auth import VelogSendmailRequestPayloadModel
from velogger.api.request.cache import (
    VelogTagPostsRequestParameterModel,
    VelogTrendingPostsRequestParameterModel,
)
from velogger.api.request.posts import (
    VelogPostsRequestPayloadModel,
    VelogReadPostRequestPayloadModel,
    VelogRecentPostsRequestPayloadModel,
    VelogSearchPostsRequestPayloadModel,
)
from velogger.api.request.social import (
    VelogFeedPostsRequestPayloadModel,
    VelogFollowListRequestPayloadModel,
    VelogReadingListRequestPayloadModel,
    VelogSeriesRequestPayloadModel,
)
from velogger.api.request.users import VelogGetUserRequestPayloadModel
from velogger.api.request.write import (
    VelogCreateSeriesRequestPayloadModel,
    VelogEditCommentRequestPayloadModel,
    VelogEditPostRequestPayloadModel,
    VelogWriteCommentRequestPayloadModel,
    VelogWritePostRequestPayloadModel,
)
from velogger.api.response.auth import (
    VelogAuthResponseModel,
    VelogSendmailResponseModel,
)
from velogger.api.response.cache import (
    VelogCachePostModel,
    VelogTagPostsResponseModel,
)
from velogger.api.response.common import VelogGraphQLResponse
from velogger.api.response.posts import (
    VelogPostsDataModel,
    VelogReadPostDataModel,
    VelogRecentPostsDataModel,
    VelogSearchPostsDataModel,
)
from velogger.api.response.social import (
    VelogAppendToSeriesDataModel,
    VelogCommentRepliesDataModel,
    VelogCreateSeriesDataModel,
    VelogEditCommentDataModel,
    VelogFeedPostsDataModel,
    VelogFollowDataModel,
    VelogFollowersDataModel,
    VelogFollowingsDataModel,
    VelogPostCommentsDataModel,
    VelogReadingListDataModel,
    VelogRemoveCommentDataModel,
    VelogSeriesDataModel,
    VelogUnfollowDataModel,
)
from velogger.api.response.users import (
    VelogTagDataModel,
    VelogUserDataModel,
    VelogUserIdDataModel,
)
from velogger.api.response.write import (
    VelogEditPostDataModel,
    VelogLikePostDataModel,
    VelogPostForEditDataModel,
    VelogStatsDataModel,
    VelogUnlikePostDataModel,
    VelogWriteCommentDataModel,
    VelogWritePostDataModel,
)
from velogger.core.http import (
    BaseHTTPClient,
    create_base_url,
    log_retry_before_sleep,
    raise_for_status,
    should_retry_idempotent,
    should_retry_non_idempotent,
    wait_retry_after,
)
from velogger.core.schema import RequestModel
from velogger.core.session import StoredCookie

from typing import (
    Annotated,
    Any,
    ClassVar,
    TypeVar,
)


_Response = TypeVar('_Response', bound=BaseModel)


# 재시도를 포함한 요청 횟수 (조회·쓰기 재시도 공통)
RETRY_ATTEMPTS: int = 3
# VELOGGER_DEBUG 가 stderr 에 찍는 원본 응답의 앞부분 길이. v2 는 실패 원인이 본문 errors 에만 있어 가장 길게, v3 조회는
# 본문(글 내용)이 길어 조금 짧게, 업로드는 `{"path": ...}` 한 줄이라 짧게 둔다
DEBUG_PREVIEW_V2: int = 2000
DEBUG_PREVIEW_V3: int = 1500
DEBUG_PREVIEW_UPLOAD: int = 1000

velog_retry = retry(
    retry=retry_if_exception(should_retry_idempotent),
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_retry_after,
    reraise=True,
    before_sleep=log_retry_before_sleep,
)
"""조회 전용 엔드포인트 공통 재시도: 최대 3회, 1초(또는 `Retry-After`) 간격, 5xx·429·timeout·transport 오류만."""

velog_write_retry = retry(
    retry=retry_if_exception(should_retry_non_idempotent),
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_retry_after,
    reraise=True,
    before_sleep=log_retry_before_sleep,
)
"""상태를 바꾸는 요청(쓰기 mutation·sendmail·upload)용 재시도: 429·503 만.

502·504·500 과 timeout·transport 오류는 서버가 이미 처리했을 수 있어(글·댓글이 두 번 생긴다) 다시 보내지 않는다
(`should_retry_non_idempotent`).
"""

# v2 GraphQL `auth` 쿼리. is_trusted 는 v2 의 `auth` 에만 있어(v3 currentUser 에는 없다) whoami 는 v2 를 쓴다.
# 계정 이메일은 요청하지 않는다. 어디에도 쓰지 않는 개인정보라 받지 않으면 모델·로그에 남을 일도 없다 (2026-10-23 실측: 빼도
# id·username·is_trusted 가 그대로 왔다). id 는 edit 가 본인 글인지 가릴 때 쓴다.
AUTH_QUERY: str = (
    'query { auth { id username is_trusted profile { display_name thumbnail short_bio } } }'
)

# v3 GraphQL 조회 쿼리. 필드 이름은 velog 스키마 그대로(snake_case).
RECENT_POSTS_QUERY: str = """
query recentPosts($input: RecentPostsInput!) {
  recentPosts(input: $input) {
    id title short_description thumbnail url_slug released_at updated_at is_private is_temp likes comments_count
    user { id username profile { thumbnail display_name } }
  }
}
"""

SEARCH_POSTS_QUERY: str = """
query searchPosts($input: GetSearchPostsInput!) {
  searchPosts(input: $input) {
    count
    posts {
      id title short_description thumbnail url_slug released_at tags is_private comments_count
      user { id username profile { thumbnail display_name } }
    }
  }
}
"""

POSTS_QUERY: str = """
query velogPosts($input: GetPostsInput!) {
  posts(input: $input) {
    id title short_description thumbnail url_slug released_at updated_at tags is_private is_temp likes comments_count
    user { id username profile { thumbnail display_name } }
  }
}
"""

READ_POST_QUERY: str = """
query readPost($input: ReadPostInput!) {
  post(input: $input) {
    id title released_at updated_at body short_description is_markdown is_private is_temp thumbnail
    comments_count url_slug likes tags
    user { id username profile { display_name thumbnail short_bio } }
    series { id name url_slug series_posts { id post { id title url_slug } } }
    linked_posts {
      previous { id title url_slug user { username } }
      next { id title url_slug user { username } }
    }
  }
}
"""

USER_QUERY: str = """
query velogUser($input: GetUserInput!, $tagsInput: UserTagsInput!) {
  user(input: $input) {
    id username
    profile { display_name short_bio thumbnail profile_links }
    series_list { id name description url_slug thumbnail updated_at posts_count }
  }
  userTags(input: $tagsInput) {
    posts_count
    tags { id name description posts_count thumbnail }
  }
}
"""

# follow·unfollow 가 username 을 ID 로 바꿀 때만 쓴다. USER_QUERY 는 userTags(사용자에 따라 태그 100개 이상)까지 받아 무겁다.
USER_ID_QUERY: str = 'query velogUserId($input: GetUserInput!) { user(input: $input) { id username } }'

TAG_QUERY: str = 'query tag($name: String!) { tag(name: $name) { id name posts_count description thumbnail } }'

# v2 GraphQL 쓰기·본인 조회 (세션 쿠키 필요). 신뢰 계정은 token(Turnstile) 없이 writePost 가 된다.
# writePost·editPost·likePost·unlikePost 는 CRA 웹(velog.io/write)과 같은 경로인 **v2 GraphQL** 로 보낸다.
# v2 는 평평한 인자를 받아 내부 v3 로 프록시하는데, 이때 **요청의 access_token 쿠키**로 인증한다. 그래서 쓰기
# 전에 require_auth 로 토큰을 갱신해 둬야(만료된 토큰이면 프록시의 내부 v3 호출이 실패해 null 이 온다) 성공한다.
# (2026-10-20 실측: 만료된 토큰의 likePost 는 errors 없이 null, 갱신한 토큰이면 성공.)
# 반대로 writeComment·readingList·getStats 등 v2 가 직접 처리하는 요청은 만료된 access_token 도 같은 요청 안에서
# refresh_token 으로 갱신(Set-Cookie)하고 성공한다 (같은 날 실측) — 앞에 require_auth 가 없어도 된다.
# v2 가 내부 에러를 삼켜 null 을 주기도 하므로, service 는 null 결과를 성공으로 보지 않고, 원인은 VELOGGER_DEBUG 로 원본 응답을 본다.
WRITE_POST_MUTATION: str = """
mutation WritePost(
  $title: String, $body: String, $tags: [String], $is_markdown: Boolean, $is_temp: Boolean,
  $is_private: Boolean, $url_slug: String, $thumbnail: String, $meta: JSON, $series_id: ID, $token: String
) {
  writePost(
    title: $title, body: $body, tags: $tags, is_markdown: $is_markdown, is_temp: $is_temp,
    is_private: $is_private, url_slug: $url_slug, thumbnail: $thumbnail, meta: $meta,
    series_id: $series_id, token: $token
  ) { id url_slug user { id username } }
}
"""

EDIT_POST_MUTATION: str = """
mutation EditPost(
  $id: ID!, $title: String, $body: String, $tags: [String], $is_markdown: Boolean, $is_temp: Boolean,
  $is_private: Boolean, $url_slug: String, $thumbnail: String, $meta: JSON, $series_id: ID, $token: String
) {
  editPost(
    id: $id, title: $title, body: $body, tags: $tags, is_markdown: $is_markdown, is_temp: $is_temp,
    is_private: $is_private, url_slug: $url_slug, thumbnail: $thumbnail, meta: $meta,
    series_id: $series_id, token: $token
  ) { id url_slug user { id username } }
}
"""

# editPost 는 받은 값으로 글을 통째로 덮는다. series_id 를 null 로 보내면 글이 시리즈에서 빠지고(2026-10-20 실측),
# meta(short_description 등)도 보낸 값이 된다. 그래서 편집 전에 시리즈·meta 까지 읽어 그대로 돌려보낸다.
# `post(id)` 는 남의 공개 글도 돌려줘(2026-10-21 실측, velog-server `post` 리졸버는 초안·비공개만 본인으로 거른다) user 로
# 본인 글인지 가린다. 남의 글에 editPost 를 보내면 v2 가 거절을 삼켜 null 만 준다.
READ_POST_FOR_EDIT_QUERY: str = """
query ReadPostForEdit($id: ID) {
  post(id: $id) {
    id title tags body is_markdown is_private is_temp thumbnail url_slug meta
    series { id name }
    user { id username }
  }
}
"""

LIKE_POST_MUTATION: str = 'mutation LikePost($id: ID!) { likePost(id: $id) { id likes liked } }'
UNLIKE_POST_MUTATION: str = 'mutation UnlikePost($id: ID!) { unlikePost(id: $id) { id likes liked } }'

WRITE_COMMENT_MUTATION: str = """
mutation WriteComment($post_id: ID!, $text: String!, $comment_id: ID) {
  writeComment(post_id: $post_id, text: $text, comment_id: $comment_id) {
    id text replies_count user { id username profile { thumbnail display_name } }
  }
}
"""

GET_STATS_QUERY: str = """
query GetStats($post_id: ID!) {
  getStats(post_id: $post_id) { total count_by_day { count day } }
}
"""

POST_COMMENTS_QUERY: str = """
query ReloadComments($id: ID!) {
  post(id: $id) {
    id comments_count
    comments {
      id text replies_count level created_at deleted
      user { id username profile { thumbnail display_name } }
    }
  }
}
"""

# velog 는 대댓글에 다시 대댓글을 달 수 있고 level 2 까지다 (velog-server `writeComment` 가 level 3 부터 'Maximum comment
# level is 2' 로 막는다). `replies` 는 Comment 의 필드라 한 번 더 중첩해 한 요청으로 2단계까지 받는다.
COMMENT_REPLIES_QUERY: str = """
query ReloadReplies($id: ID!) {
  comment(comment_id: $id) {
    id
    replies {
      id text replies_count level created_at deleted
      user { id username profile { thumbnail display_name } }
      replies {
        id text replies_count level created_at deleted
        user { id username profile { thumbnail display_name } }
      }
    }
  }
}
"""

SERIES_QUERY: str = """
query Series($username: String, $url_slug: String) {
  series(username: $username, url_slug: $url_slug) {
    id name
    user { id username profile { display_name thumbnail } }
    series_posts {
      id index
      post { id title thumbnail short_description url_slug released_at }
    }
  }
}
"""

READING_LIST_QUERY: str = """
query ReadingList($type: ReadingListOption, $cursor: ID, $limit: Int) {
  readingList(type: $type, cursor: $cursor, limit: $limit) {
    id title short_description thumbnail url_slug released_at updated_at comments_count tags is_private is_temp likes
    user { id username profile { thumbnail display_name } }
  }
}
"""

FEED_POSTS_QUERY: str = """
query feedPosts($input: FeedPostsInput!) {
  feedPosts(input: $input) {
    id title short_description thumbnail url_slug released_at updated_at is_private is_temp likes comments_count
    user { id username profile { thumbnail display_name } }
  }
}
"""

FOLLOWERS_QUERY: str = """
query getFollowers($input: GetFollowInput!) {
  followers(input: $input) {
    id userId username is_followed
    profile { short_bio thumbnail display_name }
  }
}
"""

FOLLOWINGS_QUERY: str = """
query getFollowings($input: GetFollowInput!) {
  followings(input: $input) {
    id userId username is_followed
    profile { short_bio thumbnail display_name }
  }
}
"""

EDIT_COMMENT_MUTATION: str = 'mutation EditComment($id: ID!, $text: String!) { editComment(id: $id, text: $text) { id text } }'
REMOVE_COMMENT_MUTATION: str = 'mutation RemoveComment($id: ID!) { removeComment(id: $id) }'
FOLLOW_MUTATION: str = 'mutation Follow($following_user_id: ID!) { follow(following_user_id: $following_user_id) { id is_followed } }'
UNFOLLOW_MUTATION: str = 'mutation Unfollow($following_user_id: ID!) { unfollow(following_user_id: $following_user_id) { id is_followed } }'
CREATE_SERIES_MUTATION: str = """
mutation CreateSeries($name: String!, $url_slug: String!) {
  createSeries(name: $name, url_slug: $url_slug) { id name url_slug created_at }
}
"""
APPEND_TO_SERIES_MUTATION: str = """
mutation AppendToSeries($series_id: ID!, $post_id: ID!) {
  appendToSeries(series_id: $series_id, post_id: $post_id)
}
"""

DRAFTS_QUERY: str = """
query Posts($username: String, $temp_only: Boolean, $limit: Int) {
  posts(username: $username, temp_only: $temp_only, limit: $limit) {
    id title short_description thumbnail url_slug released_at updated_at tags is_private is_temp likes comments_count
    user { id username profile { thumbnail display_name } }
  }
}
"""


def _has_partial_data(response: Response) -> bool:
    """본문이 `errors` 와 함께 값이 하나라도 든 `data` 를 담은 GraphQL 봉투인지 (일부 필드만 실패한 응답)."""
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict) or not body.get('errors'):
        return False
    data = body.get('data')
    return isinstance(data, dict) and any(value is not None for value in data.values())


class VelogClient(BaseHTTPClient):
    """velog (velog.io) 비공식 API 클라이언트.

    로그인·글쓰기는 구(舊) v2 서버(`v2.velog.io`)가, 공개 조회는 v3 서버(`v3.velog.io`)가, 트렌딩·태그별
    글은 CDN 캐시(`cache.velcdn.com`)가 맡는다. velog 는 비밀번호가 없어, 이메일 매직 링크나 소셜
    로그인으로 받은 **세션 쿠키**가 인증 수단이다. `cookies` 로 받은 쿠키를 httpx 쿠키 자에 실어 보내고,
    velog 가 응답으로 새 쿠키를 주면(토큰 갱신) 자에 반영되므로 service 가 `current_cookies()` 로 다시
    저장한다.

    조회는 로그인 없이 되고, `auth`·글쓰기·통계는 세션 쿠키가 필요하다. GraphQL 은 HTTP 200 안에 `errors`
    (인증 실패·잘못된 입력)를 담을 수 있어, client 는 `data` 와 `errors` 를 봉투 모델로 돌려주고 판정은
    service 가 한다.

    Args:
        host: 로그인·쓰기용 v2 호스트. Defaults to 'v2.velog.io'.
        graphql_v3_host: 공개 조회용 v3 GraphQL 호스트. Defaults to 'v3.velog.io'.
        cache_host: 트렌딩·태그 글 캐시 호스트. Defaults to 'cache.velcdn.com'.
        cookies: 저장된 세션 쿠키. 없으면 로그인하지 않은 상태로 공개 조회만 된다. Defaults to None.
    """

    source_name: ClassVar[str] = 'velog'
    # velog 는 명시적 요청 제한 헤더가 보이지 않았지만, LLM 이 연달아 부르는 것을 감안해 보수적으로 둔다.
    default_rate_limit: ClassVar[dict[str, object]] = {
        'min_interval': 0.3,
        'max_per_minute': 90,
        'cooldown': 120.0,
    }

    sendmail_endpoint: ClassVar[str] = '/api/v2/auth/sendmail'
    code_endpoint: ClassVar[str] = '/api/v2/auth/code/{code}'
    graphql_endpoint: ClassVar[str] = '/graphql'
    trending_posts_endpoint: ClassVar[str] = '/api/trending-posts'
    tag_posts_endpoint: ClassVar[str] = '/api/tag-posts'
    files_upload_endpoint: ClassVar[str] = '/api/v2/files/upload'

    host: str = 'v2.velog.io'

    graphql_v3_host: str = 'v3.velog.io'

    cache_host: str = 'cache.velcdn.com'

    cookies: Annotated[
        list[StoredCookie] | None,
        Field(repr=False)
    ] = None

    @property
    def base_url(self) -> str:
        return create_base_url(schema=self.url_schema, host=self.host)

    @property
    def graphql_v2_url(self) -> str:
        return self.base_url + self.graphql_endpoint

    @property
    def graphql_v3_url(self) -> str:
        return create_base_url(schema=self.url_schema, host=self.graphql_v3_host) + self.graphql_endpoint

    @property
    def cache_url(self) -> str:
        return create_base_url(schema=self.url_schema, host=self.cache_host)

    @property
    def base_header(self) -> dict[str, str]:
        return {
            'Accept': 'application/json',
            'Origin': 'https://velog.io',
            'User-Agent': self.user_agent,
        }

    def _cookie_jar(self) -> Cookies:
        jar = Cookies()
        for cookie in self.cookies or []:
            jar.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
        return jar

    @cached_property
    def _client(self) -> Client:
        return Client(
            base_url=self.base_url,
            headers=self.base_header,
            cookies=self._cookie_jar(),
            follow_redirects=True,
            event_hooks=self.rate_limit_hooks(),
            verify=self.verify,
            timeout=self.timeout,
            proxy=self.proxy,
        )

    @cached_property
    def _async_client(self) -> AsyncClient:
        return AsyncClient(
            base_url=self.base_url,
            headers=self.base_header,
            cookies=self._cookie_jar(),
            follow_redirects=True,
            event_hooks=self.async_rate_limit_hooks(),
            verify=self.verify,
            timeout=self.timeout,
            proxy=self.proxy,
        )

    def current_cookies(self) -> list[StoredCookie]:
        """지금 클라이언트 쿠키 자에 든 쿠키를 저장용 모델로 내보낸다.

        로그인(`code`) 직후나 토큰 갱신(응답 Set-Cookie) 뒤에 바뀐 쿠키를 세션 파일에 다시 쓰려고 쓴다.
        """
        return [
            StoredCookie(
                name=cookie.name,
                value=cookie.value or '',
                domain=cookie.domain,
                path=cookie.path,
            )
            for cookie in self._client.cookies.jar
        ]

    def _graphql_body(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        return {'query': query, 'variables': variables}

    # ----------------------------------------------------------------- 인증 (v2)

    @velog_write_retry
    def run_request_sendmail(
        self,
        payload: VelogSendmailRequestPayloadModel
    ) -> VelogSendmailResponseModel:
        """Request a login/registration link via `POST v2.velog.io/api/v2/auth/sendmail`.

        429·503 만 재시도한다 (502·504·timeout·transport 오류는 메일이 이미 나갔을 수 있어 다시 보내지 않는다).
        요청 제한이 켜져 있으면 429 는 재시도 없이 `RateLimitedError` 로 끝난다.
        """
        response = self._client.post(
            url=self.sendmail_endpoint,
            json=payload.model_dump(by_alias=True, exclude_none=True),
        )
        raise_for_status(response=response)
        return VelogSendmailResponseModel.model_validate(response.json())

    @velog_retry
    def run_request_code(self, code: str) -> Response:
        """Exchange a login code for session cookies via `GET v2.velog.io/api/v2/auth/code/{code}`.

        성공하면 velog 가 세션 쿠키를 Set-Cookie 로 주고, httpx 가 클라이언트 쿠키 자에 담는다. 없는 code 는 404,
        이미 쓴 code 는 403 `{"name": "TOKEN_ALREADY_USED"}`, 24시간 지난 code 는 410 `{"name": "EXPIRED_CODE"}` 다
        (velog-server `routes/api/v2/auth/index.ts`. 2026-10-20 실측: 404·403, 410 은 소스 기준). 처리된 뒤 응답만 잃은 요청을
        다시 보내도 403 으로 끝나 로그인이 두 번 되지 않으므로 재시도해도 안전하다.

        code 는 경로에 실리므로 `/`·`?`·`#`·`%` 를 이스케이프해 다른 엔드포인트로 새지 않게 한다.
        """
        response = self._client.get(url=self.code_endpoint.format(code=quote(code, safe='')))
        raise_for_status(response=response)
        return response

    @velog_retry
    def run_request_auth(self) -> VelogAuthResponseModel:
        """Fetch the logged-in user via `POST v2.velog.io/graphql` (`auth`).

        저장된 세션 쿠키로 보낸다. 로그인하지 않았으면 `data.auth` 가 null 이다. is_trusted 가 여기에 있다.
        """
        response = self._client.post(url=self.graphql_v2_url, json={'query': AUTH_QUERY})
        raise_for_status(response=response)
        return VelogAuthResponseModel.model_validate(response.json())

    # --------------------------------------------------------------- 조회 (v3 GraphQL)

    @velog_retry
    def run_request_recent_posts(
        self,
        payload: VelogRecentPostsRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogRecentPostsDataModel]:
        """Fetch recent posts via `POST v3.velog.io/graphql` (`recentPosts`).

        요청 제한이 켜져 있으면 429 는 재시도 없이 `RateLimitedError` 로 끝난다.
        """
        return self._query_v3(RECENT_POSTS_QUERY, payload, VelogGraphQLResponse[VelogRecentPostsDataModel])

    @velog_retry
    def run_request_search_posts(
        self,
        payload: VelogSearchPostsRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogSearchPostsDataModel]:
        """Search posts via `POST v3.velog.io/graphql` (`searchPosts`)."""
        return self._query_v3(SEARCH_POSTS_QUERY, payload, VelogGraphQLResponse[VelogSearchPostsDataModel])

    @velog_retry
    def run_request_posts(
        self,
        payload: VelogPostsRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogPostsDataModel]:
        """Fetch one user's posts via `POST v3.velog.io/graphql` (`posts`)."""
        return self._query_v3(POSTS_QUERY, payload, VelogGraphQLResponse[VelogPostsDataModel])

    @velog_retry
    def run_request_read_post(
        self,
        payload: VelogReadPostRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogReadPostDataModel]:
        """Fetch one post with body via `POST v3.velog.io/graphql` (`readPost`).

        로그인한 본인이 시리즈에 든 자기 글을 읽으면 v3 가 HTTP 500 을 주지만, 본문은 글 데이터(`series_posts` 만 null)와
        `errors` 가 든 GraphQL 봉투다 (2026-10-21 실측: prisma `seriesPost.findMany()` 의 `orderBy` 오류. 익명이거나 남의
        글이면 200). 그 응답은 에러로 올리지 않고 봉투로 돌려줘 service 가 판정한다 (`keep_partial`). 다시 보내도 같아
        재시도하지 않는다.
        """
        return self._query_v3(
            READ_POST_QUERY, payload, VelogGraphQLResponse[VelogReadPostDataModel], keep_partial=True,
        )

    @velog_retry
    def run_request_user(
        self,
        payload: VelogGetUserRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogUserDataModel]:
        """Fetch a user (profile + series + tags) via `POST v3.velog.io/graphql` (`user` + `userTags`)."""
        variables = {
            'input': payload.model_dump(by_alias=True, exclude_none=True),
            'tagsInput': payload.model_dump(by_alias=True, exclude_none=True),
        }
        return VelogGraphQLResponse[VelogUserDataModel].model_validate(
            self._post_graphql_v3(USER_QUERY, variables).json()
        )

    @velog_retry
    def run_request_user_id(
        self,
        payload: VelogGetUserRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogUserIdDataModel]:
        """Fetch only a user's ID via `POST v3.velog.io/graphql` (`user`, id·username 만).

        `user` 를 루트로 쓰는 쿼리가 둘이라(`run_request_user` 는 프로필·시리즈·태그까지) 뜻으로 구분해 `user_id` 로 부른다.
        없는 사용자면 `user` 가 null 이다.
        """
        return self._query_v3(USER_ID_QUERY, payload, VelogGraphQLResponse[VelogUserIdDataModel])

    @velog_retry
    def run_request_tag(self, name: str) -> VelogGraphQLResponse[VelogTagDataModel]:
        """Fetch tag info via `POST v3.velog.io/graphql` (`tag`)."""
        return VelogGraphQLResponse[VelogTagDataModel].model_validate(
            self._post_graphql_v3(TAG_QUERY, {'name': name}).json()
        )

    # ------------------------------------------------------------------- 조회 (캐시 REST)

    @velog_retry
    def run_request_trending_posts(
        self,
        parameter: VelogTrendingPostsRequestParameterModel
    ) -> list[VelogCachePostModel]:
        """Fetch trending posts via `GET cache.velcdn.com/api/trending-posts`.

        응답은 글 카드의 평탄한 배열(camelCase)이다.
        """
        response = self._client.get(
            url=self.cache_url + self.trending_posts_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
        )
        raise_for_status(response=response)
        return [VelogCachePostModel.model_validate(item) for item in response.json()]

    @velog_retry
    def run_request_tag_posts(
        self,
        parameter: VelogTagPostsRequestParameterModel
    ) -> VelogTagPostsResponseModel:
        """Fetch posts for a tag via `GET cache.velcdn.com/api/tag-posts`.

        태그별 글은 GraphQL 로는 빈 배열이라 이 캐시 REST 를 쓴다. 응답은 `posts` + `nextCursor` + `count`.
        """
        response = self._client.get(
            url=self.cache_url + self.tag_posts_endpoint,
            params=parameter.model_dump(by_alias=True, exclude_none=True),
        )
        raise_for_status(response=response)
        return VelogTagPostsResponseModel.model_validate(response.json())

    # ------------------------------------------------------------ 쓰기·본인 조회 (v2, 세션 필요)

    def _post_graphql_v3(self, query: str, variables: dict[str, Any], *, keep_partial: bool = False) -> Response:
        """공개 조회용 v3 GraphQL. 인증이 필요한 조회(feed 등)는 세션 쿠키로 인증된다.

        `keep_partial` 이면 HTTP 500 이라도 본문이 데이터가 든 GraphQL 봉투(일부 필드만 실패)일 때 에러로 올리지 않는다.
        """
        response = self._client.post(url=self.graphql_v3_url, json=self._graphql_body(query, variables))
        if os.environ.get('VELOGGER_DEBUG'):
            sys.stderr.write(f'[VELOGGER_DEBUG] v3 <- {response.status_code} {response.text[:DEBUG_PREVIEW_V3]}\n')
        if keep_partial and response.status_code == codes.INTERNAL_SERVER_ERROR and _has_partial_data(response):
            return response
        raise_for_status(response=response)
        return response

    def _query_v3(
        self,
        query: str,
        payload: RequestModel,
        response_model: type[_Response],
        *,
        keep_partial: bool = False,
    ) -> _Response:
        """`input` 하나만 받는 v3 GraphQL 조회. 응답 봉투를 `response_model` 로 검증한다 (재시도는 부르는 쪽 데코레이터)."""
        variables = {'input': payload.model_dump(by_alias=True, exclude_none=True)}
        response = self._post_graphql_v3(query, variables, keep_partial=keep_partial)
        return response_model.model_validate(response.json())

    def _post_graphql_v2(self, query: str, variables: dict[str, Any]) -> Response:
        if os.environ.get('VELOGGER_DEBUG'):
            # 보내기 전 쿠키 구조 (이름·도메인·경로·만료만, 값은 절대 안 찍는다)
            jar = [(c.name, c.domain, c.path, c.expires) for c in self._client.cookies.jar]
            sys.stderr.write(f'[VELOGGER_DEBUG] v2 jar before -> {jar}\n')
        response = self._client.post(url=self.graphql_v2_url, json=self._graphql_body(query, variables))
        if os.environ.get('VELOGGER_DEBUG'):
            # 응답 본문(토큰·쿠키 없음) + 이번 응답이 새로 심은 쿠키 이름
            setc = [c.split('=', 1)[0] for c in response.headers.get_list('set-cookie')]
            sys.stderr.write(f'[VELOGGER_DEBUG] v2 graphql <- {response.status_code} set-cookie={setc} body={response.text[:DEBUG_PREVIEW_V2]}\n')
        raise_for_status(response=response)
        return response

    @velog_write_retry
    def run_request_write_post(
        self,
        payload: VelogWritePostRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogWritePostDataModel]:
        """Write or save a post via `POST v2.velog.io/graphql` (`writePost`). 세션 쿠키가 필요하다.

        상태를 바꾸는 요청이라 429·503 만 재시도한다 (502·504·500·timeout·transport 는 글이 이미 저장됐을 수 있어
        다시 보내지 않는다). 로그인 안 됨·권한 없음은 200 안의 GraphQL `errors` 로 오며 service 가 판정한다.
        """
        # exclude_none 을 쓰지 않는다: 키가 빠지면 내부 v3 가 거절하고 v2 가 null 로 삼킨다 (요청 모델 docstring).
        variables = payload.model_dump(by_alias=True)
        return VelogGraphQLResponse[VelogWritePostDataModel].model_validate(
            self._post_graphql_v2(WRITE_POST_MUTATION, variables).json()
        )

    @velog_write_retry
    def run_request_edit_post(
        self,
        payload: VelogEditPostRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogEditPostDataModel]:
        """Edit a post via `POST v2.velog.io/graphql` (`editPost`). Same retry behaviour as `run_request_write_post`."""
        variables = payload.model_dump(by_alias=True)
        return VelogGraphQLResponse[VelogEditPostDataModel].model_validate(
            self._post_graphql_v2(EDIT_POST_MUTATION, variables).json()
        )

    @velog_retry
    def run_request_read_post_for_edit(self, post_id: str) -> VelogGraphQLResponse[VelogPostForEditDataModel]:
        """Fetch a post's current fields for editing via `POST v2.velog.io/graphql` (`ReadPostForEdit`)."""
        return VelogGraphQLResponse[VelogPostForEditDataModel].model_validate(
            self._post_graphql_v2(READ_POST_FOR_EDIT_QUERY, {'id': post_id}).json()
        )

    @velog_write_retry
    def run_request_like_post(self, post_id: str) -> VelogGraphQLResponse[VelogLikePostDataModel]:
        """Like a post via `POST v2.velog.io/graphql` (`likePost`). Same retry behaviour as `run_request_write_post`."""
        return VelogGraphQLResponse[VelogLikePostDataModel].model_validate(
            self._post_graphql_v2(LIKE_POST_MUTATION, {'id': post_id}).json()
        )

    @velog_write_retry
    def run_request_unlike_post(self, post_id: str) -> VelogGraphQLResponse[VelogUnlikePostDataModel]:
        """Unlike a post via `POST v2.velog.io/graphql` (`unlikePost`)."""
        return VelogGraphQLResponse[VelogUnlikePostDataModel].model_validate(
            self._post_graphql_v2(UNLIKE_POST_MUTATION, {'id': post_id}).json()
        )

    @velog_write_retry
    def run_request_write_comment(
        self,
        payload: VelogWriteCommentRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogWriteCommentDataModel]:
        """Write a comment via `POST v2.velog.io/graphql` (`writeComment`). Same retry behaviour as `run_request_write_post`."""
        variables = payload.model_dump(by_alias=True, exclude_none=True)
        return VelogGraphQLResponse[VelogWriteCommentDataModel].model_validate(
            self._post_graphql_v2(WRITE_COMMENT_MUTATION, variables).json()
        )

    @velog_retry
    def run_request_get_stats(self, post_id: str) -> VelogGraphQLResponse[VelogStatsDataModel]:
        """Fetch a post's view stats via `POST v2.velog.io/graphql` (`getStats`). 본인 글만, 세션 필요."""
        return VelogGraphQLResponse[VelogStatsDataModel].model_validate(
            self._post_graphql_v2(GET_STATS_QUERY, {'post_id': post_id}).json()
        )

    @velog_retry
    def run_request_post_comments(self, post_id: str) -> VelogGraphQLResponse[VelogPostCommentsDataModel]:
        """Fetch a post's comments via `POST v2.velog.io/graphql` (`ReloadComments`).

        댓글 작성자는 v2 에만 채워져 온다 (v3 readPost 는 user 가 null).
        """
        return VelogGraphQLResponse[VelogPostCommentsDataModel].model_validate(
            self._post_graphql_v2(POST_COMMENTS_QUERY, {'id': post_id}).json()
        )

    @velog_retry
    def run_request_comment_replies(self, comment_id: str) -> VelogGraphQLResponse[VelogCommentRepliesDataModel]:
        """Fetch one comment's replies (and their replies, down to level 2) via `POST v2.velog.io/graphql` (`ReloadReplies`)."""
        return VelogGraphQLResponse[VelogCommentRepliesDataModel].model_validate(
            self._post_graphql_v2(COMMENT_REPLIES_QUERY, {'id': comment_id}).json()
        )

    @velog_retry
    def run_request_series(
        self,
        payload: VelogSeriesRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogSeriesDataModel]:
        """Fetch a series and its ordered posts via `POST v2.velog.io/graphql` (`Series`)."""
        return VelogGraphQLResponse[VelogSeriesDataModel].model_validate(
            self._post_graphql_v2(SERIES_QUERY, payload.model_dump(by_alias=True, exclude_none=True)).json()
        )

    @velog_retry
    def run_request_reading_list(
        self,
        payload: VelogReadingListRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogReadingListDataModel]:
        """Fetch the logged-in user's liked/read posts via `POST v2.velog.io/graphql` (`readingList`). 세션 필요."""
        return VelogGraphQLResponse[VelogReadingListDataModel].model_validate(
            self._post_graphql_v2(READING_LIST_QUERY, payload.model_dump(by_alias=True, exclude_none=True)).json()
        )

    @velog_retry
    def run_request_feed_posts(
        self,
        payload: VelogFeedPostsRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogFeedPostsDataModel]:
        """Fetch the logged-in user's feed via `POST v3.velog.io/graphql` (`feedPosts`). 세션 필요."""
        return self._query_v3(FEED_POSTS_QUERY, payload, VelogGraphQLResponse[VelogFeedPostsDataModel])

    @velog_retry
    def run_request_followers(
        self,
        payload: VelogFollowListRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogFollowersDataModel]:
        """Fetch a user's followers via `POST v3.velog.io/graphql` (`getFollowers`)."""
        return self._query_v3(FOLLOWERS_QUERY, payload, VelogGraphQLResponse[VelogFollowersDataModel])

    @velog_retry
    def run_request_followings(
        self,
        payload: VelogFollowListRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogFollowingsDataModel]:
        """Fetch who a user follows via `POST v3.velog.io/graphql` (`getFollowings`)."""
        return self._query_v3(FOLLOWINGS_QUERY, payload, VelogGraphQLResponse[VelogFollowingsDataModel])

    @velog_write_retry
    def run_request_edit_comment(
        self,
        payload: VelogEditCommentRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogEditCommentDataModel]:
        """Edit a comment via `POST v2.velog.io/graphql` (`editComment`)."""
        return VelogGraphQLResponse[VelogEditCommentDataModel].model_validate(
            self._post_graphql_v2(EDIT_COMMENT_MUTATION, payload.model_dump(by_alias=True)).json()
        )

    @velog_write_retry
    def run_request_remove_comment(self, comment_id: str) -> VelogGraphQLResponse[VelogRemoveCommentDataModel]:
        """Remove a comment via `POST v2.velog.io/graphql` (`removeComment`)."""
        return VelogGraphQLResponse[VelogRemoveCommentDataModel].model_validate(
            self._post_graphql_v2(REMOVE_COMMENT_MUTATION, {'id': comment_id}).json()
        )

    @velog_write_retry
    def run_request_follow(self, user_id: str) -> VelogGraphQLResponse[VelogFollowDataModel]:
        """Follow a user via `POST v2.velog.io/graphql` (`follow`). 인자는 username 이 아니라 사용자 ID 다."""
        return VelogGraphQLResponse[VelogFollowDataModel].model_validate(
            self._post_graphql_v2(FOLLOW_MUTATION, {'following_user_id': user_id}).json()
        )

    @velog_write_retry
    def run_request_unfollow(self, user_id: str) -> VelogGraphQLResponse[VelogUnfollowDataModel]:
        """Unfollow a user via `POST v2.velog.io/graphql` (`unfollow`)."""
        return VelogGraphQLResponse[VelogUnfollowDataModel].model_validate(
            self._post_graphql_v2(UNFOLLOW_MUTATION, {'following_user_id': user_id}).json()
        )

    @velog_write_retry
    def run_request_create_series(
        self,
        payload: VelogCreateSeriesRequestPayloadModel
    ) -> VelogGraphQLResponse[VelogCreateSeriesDataModel]:
        """Create a series via `POST v2.velog.io/graphql` (`createSeries`).

        같은 slug 의 시리즈가 이미 있으면 errors `ALREADY_EXISTS`('URL Slug already exists')다 (2026-10-21 실측).
        """
        return VelogGraphQLResponse[VelogCreateSeriesDataModel].model_validate(
            self._post_graphql_v2(CREATE_SERIES_MUTATION, payload.model_dump(by_alias=True)).json()
        )

    @velog_write_retry
    def run_request_append_to_series(
        self,
        series_id: str,
        post_id: str,
    ) -> VelogGraphQLResponse[VelogAppendToSeriesDataModel]:
        """Add a post to a series via `POST v2.velog.io/graphql` (`appendToSeries`).

        이미 그 시리즈에 든 글이면 errors `CONFLICT`('Already added to series')다 (2026-10-21 실측).
        """
        return VelogGraphQLResponse[VelogAppendToSeriesDataModel].model_validate(
            self._post_graphql_v2(APPEND_TO_SERIES_MUTATION, {'series_id': series_id, 'post_id': post_id}).json()
        )

    @velog_write_retry
    def run_request_upload_image(
        self,
        filename: str,
        content: bytes,
        ref_id: str,
        upload_type: str = 'post',
    ) -> Response:
        """Upload an image via `POST v2.velog.io/api/v2/files/upload` (multipart). 세션 필요.

        웹 에디터(CRA)와 같은 형식(`image`·`type`·`ref_id`)으로 보낸다. **`ref_id`(이미지가 들어갈 글 ID)가 없으면
        velog 앞단이 403 `Forbidden` 으로 막는다** — 웹 에디터도 글을 초안으로 먼저 저장해 id 를 받은 뒤에야 이미지를
        올린다 (2026-10-20 실측: ref_id 없이 403). 응답 모양은 velog 가 바꿀 수 있어 service 가 URL 로 보이는 값을 찾아 쓴다.
        """
        response = self._client.post(
            url=self.files_upload_endpoint,
            files={'image': (filename, content)},
            data={'type': upload_type, 'ref_id': ref_id},
        )
        if os.environ.get('VELOGGER_DEBUG'):
            sys.stderr.write(f'[VELOGGER_DEBUG] upload <- {response.status_code} {response.text[:DEBUG_PREVIEW_UPLOAD]}\n')
        raise_for_status(response=response)
        return response

    @velog_retry
    def run_request_drafts(self, username: str, limit: int) -> VelogGraphQLResponse[VelogPostsDataModel]:
        """Fetch the logged-in user's draft (temp) posts via `POST v2.velog.io/graphql` (`posts(temp_only: true)`)."""
        variables = {'username': username, 'temp_only': True, 'limit': limit}
        return VelogGraphQLResponse[VelogPostsDataModel].model_validate(
            self._post_graphql_v2(DRAFTS_QUERY, variables).json()
        )
