from pydantic import Field

from velogger.api.response.common import VelogPostUserModel
from velogger.core.schema import ResponseModel

from typing import Annotated


class VelogPostCardModel(ResponseModel):
    """글 목록의 카드 하나. recentPosts·searchPosts·posts 가 거의 같은 모양을 준다.

    소스마다 빼는 필드가 있어(예: searchPosts 는 updated_at·likes 를 안 준다) 전부 선택이다.
    """

    id: Annotated[str | None, Field(description='글 ID')] = None
    title: Annotated[str | None, Field(description='제목')] = None
    short_description: Annotated[str | None, Field(description='미리보기 설명')] = None
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None
    url_slug: Annotated[str | None, Field(description='글 slug (post 조회에 쓴다)')] = None
    released_at: Annotated[str | None, Field(description='발행 시각 (ISO)')] = None
    updated_at: Annotated[str | None, Field(description='수정 시각 (ISO)')] = None
    tags: Annotated[list[str] | None, Field(description='태그')] = None
    likes: Annotated[int | None, Field(description='좋아요 수')] = None
    comments_count: Annotated[int | None, Field(description='댓글 수')] = None
    is_private: Annotated[bool | None, Field(description='비공개 여부')] = None
    is_temp: Annotated[bool | None, Field(description='임시저장(초안) 글인지 (searchPosts 는 null 을 준다)')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='글쓴이')] = None


class VelogRecentPostsDataModel(ResponseModel):
    """`recentPosts` 쿼리의 data."""

    recent_posts: Annotated[list[VelogPostCardModel] | None, Field(alias='recentPosts')] = None


class VelogPostsDataModel(ResponseModel):
    """`posts`(한 사용자 글) 쿼리의 data. 루트 필드는 `posts`."""

    posts: list[VelogPostCardModel] | None = None


class VelogSearchResultModel(ResponseModel):
    """`searchPosts` 값 (`count` + `posts`)."""

    count: Annotated[int | None, Field(description='검색 결과 총 개수')] = None
    posts: list[VelogPostCardModel] | None = None


class VelogSearchPostsDataModel(ResponseModel):
    """`searchPosts` 쿼리의 data."""

    search_posts: Annotated[VelogSearchResultModel | None, Field(alias='searchPosts')] = None


class VelogSeriesPostRefModel(ResponseModel):
    """시리즈 안 글 하나 (상세의 series_posts)."""

    id: str | None = None
    post: VelogPostCardModel | None = None


class VelogPostSeriesModel(ResponseModel):
    """글이 속한 시리즈."""

    id: str | None = None
    name: Annotated[str | None, Field(description='시리즈 이름')] = None
    url_slug: Annotated[str | None, Field(description='시리즈 slug')] = None
    series_posts: Annotated[list[VelogSeriesPostRefModel] | None, Field(description='시리즈 안 글들')] = None


class VelogLinkedPostRefModel(ResponseModel):
    """이전/다음 글 참조."""

    id: str | None = None
    title: str | None = None
    url_slug: str | None = None
    user: VelogPostUserModel | None = None


class VelogLinkedPostsModel(ResponseModel):
    """글의 이전/다음 글 (같은 시리즈 흐름)."""

    previous: VelogLinkedPostRefModel | None = None
    next: VelogLinkedPostRefModel | None = None


class VelogReadPostModel(ResponseModel):
    """글 상세. 본문(마크다운)과 메타·시리즈·이전/다음 글."""

    id: str | None = None
    title: Annotated[str | None, Field(description='제목')] = None
    released_at: Annotated[str | None, Field(description='발행 시각 (ISO)')] = None
    updated_at: Annotated[str | None, Field(description='수정 시각 (ISO)')] = None
    body: Annotated[str | None, Field(description='본문. is_markdown 이면 마크다운')] = None
    short_description: Annotated[str | None, Field(description='미리보기 설명')] = None
    is_markdown: Annotated[bool | None, Field(description='본문이 마크다운인지')] = None
    is_private: Annotated[bool | None, Field(description='비공개 여부')] = None
    is_temp: Annotated[bool | None, Field(description='임시 저장 글인지')] = None
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None
    comments_count: Annotated[int | None, Field(description='댓글 수')] = None
    url_slug: Annotated[str | None, Field(description='글 slug')] = None
    likes: Annotated[int | None, Field(description='좋아요 수')] = None
    tags: Annotated[list[str] | None, Field(description='태그')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='글쓴이')] = None
    series: Annotated[VelogPostSeriesModel | None, Field(description='속한 시리즈')] = None
    linked_posts: Annotated[VelogLinkedPostsModel | None, Field(description='이전/다음 글')] = None


class VelogReadPostDataModel(ResponseModel):
    """`post`(readPost) 쿼리의 data. 글이 없으면 `post` 가 null."""

    post: VelogReadPostModel | None = None
