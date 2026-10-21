"""캐시 REST(`cache.velcdn.com`) 응답 모델. GraphQL 과 달리 camelCase 라 별칭을 단다."""

from pydantic import Field

from velogger.core.schema import ResponseModel

from typing import Annotated


class VelogCacheUserModel(ResponseModel):
    """캐시 응답의 글쓴이 (평탄한 camelCase)."""

    id: Annotated[str | None, Field(description='사용자 ID')] = None
    username: Annotated[str | None, Field(description='아이디 (@username)')] = None
    display_name: Annotated[
        str | None,
        Field(description='표시 이름')
    ] = Field(default=None, alias='displayName')
    thumbnail: Annotated[str | None, Field(description='프로필 이미지 URL')] = None


class VelogCachePostModel(ResponseModel):
    """캐시 트렌딩·태그 글 카드 (camelCase)."""

    id: Annotated[str | None, Field(description='글 ID')] = None
    title: Annotated[str | None, Field(description='제목')] = None
    url_slug: Annotated[
        str | None,
        Field(description='글 slug')
    ] = Field(default=None, alias='urlSlug')
    short_description: Annotated[
        str | None,
        Field(description='미리보기 설명')
    ] = Field(default=None, alias='shortDescription')
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None
    released_at: Annotated[
        str | None,
        Field(description='발행 시각 (ISO)')
    ] = Field(default=None, alias='releasedAt')
    updated_at: Annotated[
        str | None,
        Field(description='수정 시각 (ISO)')
    ] = Field(default=None, alias='updatedAt')
    likes: Annotated[int | None, Field(description='좋아요 수')] = None
    comments_count: Annotated[
        int | None,
        Field(description='댓글 수')
    ] = Field(default=None, alias='commentsCount')
    user: Annotated[VelogCacheUserModel | None, Field(description='글쓴이')] = None


class VelogTagPostsResponseModel(ResponseModel):
    """캐시 `GET /api/tag-posts` 응답 (REST, 봉투 아님)."""

    tag_name: Annotated[
        str | None,
        Field(description='태그 이름')
    ] = Field(default=None, alias='tagName')
    posts: Annotated[list[VelogCachePostModel] | None, Field(description='태그 글 카드')] = None
    count: Annotated[int | None, Field(description='태그 전체 글 수')] = None
    next_cursor: Annotated[
        str | None,
        Field(description='다음 페이지 커서')
    ] = Field(default=None, alias='nextCursor')
