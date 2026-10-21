"""캐시 REST(`cache.velcdn.com`) 응답 모델. GraphQL 과 달리 camelCase 라 별칭을 단다."""

from pydantic import Field

from velogger.core.schema import ResponseModel

from typing import Annotated


class VelogCacheUserModel(ResponseModel):
    """캐시 응답의 글쓴이 (평탄한 camelCase)."""

    id: str | None = None
    username: Annotated[str | None, Field(description='아이디 (@username)')] = None
    display_name: Annotated[str | None, Field(alias='displayName', description='표시 이름')] = None
    thumbnail: Annotated[str | None, Field(description='프로필 이미지 URL')] = None


class VelogCachePostModel(ResponseModel):
    """캐시 트렌딩·태그 글 카드 (camelCase)."""

    id: str | None = None
    title: Annotated[str | None, Field(description='제목')] = None
    url_slug: Annotated[str | None, Field(alias='urlSlug', description='글 slug')] = None
    short_description: Annotated[str | None, Field(alias='shortDescription', description='미리보기 설명')] = None
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None
    released_at: Annotated[str | None, Field(alias='releasedAt', description='발행 시각 (ISO)')] = None
    updated_at: Annotated[str | None, Field(alias='updatedAt', description='수정 시각 (ISO)')] = None
    likes: Annotated[int | None, Field(description='좋아요 수')] = None
    comments_count: Annotated[int | None, Field(alias='commentsCount', description='댓글 수')] = None
    user: VelogCacheUserModel | None = None


class VelogTagPostsResponseModel(ResponseModel):
    """캐시 `GET /api/tag-posts` 응답 (REST, 봉투 아님)."""

    tag_name: Annotated[str | None, Field(alias='tagName', description='태그 이름')] = None
    posts: list[VelogCachePostModel] | None = None
    count: Annotated[int | None, Field(description='태그 전체 글 수')] = None
    next_cursor: Annotated[str | None, Field(alias='nextCursor', description='다음 페이지 커서')] = None
