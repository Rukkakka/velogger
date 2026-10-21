from pydantic import Field

from velogger.api.response.common import VelogPostUserModel
from velogger.core.schema import ResponseModel

from typing import (
    Annotated,
    Any,
)


class VelogWrittenPostModel(ResponseModel):
    """`writePost`·`editPost` 결과. 저장된 글의 식별자."""

    id: str | None = None
    url_slug: Annotated[str | None, Field(description='글 slug')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='글쓴이')] = None


class VelogWritePostDataModel(ResponseModel):
    """`writePost` mutation 의 data."""

    write_post: Annotated[VelogWrittenPostModel | None, Field(alias='writePost')] = None


class VelogEditPostDataModel(ResponseModel):
    """`editPost` mutation 의 data."""

    edit_post: Annotated[VelogWrittenPostModel | None, Field(alias='editPost')] = None


class VelogPostForEditSeriesModel(ResponseModel):
    """편집할 글이 속한 시리즈 (`ReadPostForEdit` 의 `series`)."""

    id: str | None = None
    name: Annotated[str | None, Field(description='시리즈 이름')] = None


class VelogPostForEditModel(ResponseModel):
    """`ReadPostForEdit` 로 받은 기존 글 (편집 병합용).

    editPost 는 보낸 값으로 글을 덮으므로 시리즈·meta 까지 받아 그대로 돌려보낸다 (series_id 를 null 로 보내면 글이
    시리즈에서 빠진다, 2026-10-20 실측).
    """

    id: str | None = None
    title: str | None = None
    tags: list[str] | None = None
    body: str | None = None
    is_markdown: bool | None = None
    is_private: bool | None = None
    is_temp: bool | None = None
    thumbnail: str | None = None
    url_slug: str | None = None
    meta: Annotated[dict[str, Any] | None, Field(description='글 메타 (short_description 등)')] = None
    series: Annotated[VelogPostForEditSeriesModel | None, Field(description='속한 시리즈')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='글쓴이 (본인 글인지 가린다)')] = None


class VelogPostForEditDataModel(ResponseModel):
    """`ReadPostForEdit` 쿼리의 data."""

    post: VelogPostForEditModel | None = None


class VelogLikeResultModel(ResponseModel):
    """`likePost`·`unlikePost` 결과 (v2 는 `liked` 로 준다)."""

    id: str | None = None
    likes: Annotated[int | None, Field(description='현재 좋아요 수')] = None
    liked: Annotated[bool | None, Field(description='내가 좋아요한 상태인지')] = None


class VelogLikePostDataModel(ResponseModel):
    """`likePost` mutation 의 data."""

    like_post: Annotated[VelogLikeResultModel | None, Field(alias='likePost')] = None


class VelogUnlikePostDataModel(ResponseModel):
    """`unlikePost` mutation 의 data."""

    unlike_post: Annotated[VelogLikeResultModel | None, Field(alias='unlikePost')] = None


class VelogCommentResultModel(ResponseModel):
    """`writeComment` 결과."""

    id: str | None = None
    text: Annotated[str | None, Field(description='저장된 댓글 내용')] = None
    replies_count: Annotated[int | None, Field(description='대댓글 수')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='작성자(본인)')] = None


class VelogWriteCommentDataModel(ResponseModel):
    """`writeComment` mutation 의 data."""

    write_comment: Annotated[VelogCommentResultModel | None, Field(alias='writeComment')] = None


class VelogStatsDayModel(ResponseModel):
    """일별 조회수 한 칸."""

    day: str | None = None
    count: int | None = None


class VelogStatsModel(ResponseModel):
    """`getStats` 결과 (본인 글 조회수)."""

    total: Annotated[int | None, Field(description='전체 조회수')] = None
    count_by_day: Annotated[list[VelogStatsDayModel] | None, Field(description='일별 조회수')] = None


class VelogStatsDataModel(ResponseModel):
    """`getStats` 쿼리의 data."""

    get_stats: Annotated[VelogStatsModel | None, Field(alias='getStats')] = None
