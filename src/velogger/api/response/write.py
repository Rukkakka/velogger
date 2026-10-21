from pydantic import Field

from velogger.api.response.common import VelogPostUserModel
from velogger.core.schema import ResponseModel

from typing import (
    Annotated,
    Any,
)


class VelogWrittenPostModel(ResponseModel):
    """`writePost`·`editPost` 결과. 저장된 글의 식별자."""

    id: Annotated[str | None, Field(description='글 ID')] = None
    url_slug: Annotated[str | None, Field(description='글 slug')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='글쓴이')] = None


class VelogWritePostDataModel(ResponseModel):
    """`writePost` mutation 의 data."""

    write_post: Annotated[
        VelogWrittenPostModel | None,
        Field(description='저장된 글. v2 가 내부 에러를 삼키면 errors 없이 null')
    ] = Field(default=None, alias='writePost')


class VelogEditPostDataModel(ResponseModel):
    """`editPost` mutation 의 data."""

    edit_post: Annotated[
        VelogWrittenPostModel | None,
        Field(description='고친 글. v2 가 내부 에러를 삼키면 errors 없이 null')
    ] = Field(default=None, alias='editPost')


class VelogPostForEditSeriesModel(ResponseModel):
    """편집할 글이 속한 시리즈 (`ReadPostForEdit` 의 `series`)."""

    id: Annotated[str | None, Field(description='시리즈 ID')] = None
    name: Annotated[str | None, Field(description='시리즈 이름')] = None


class VelogPostForEditModel(ResponseModel):
    """`ReadPostForEdit` 로 받은 기존 글 (편집 병합용).

    editPost 는 보낸 값으로 글을 덮으므로 시리즈·meta 까지 받아 그대로 돌려보낸다 (series_id 를 null 로 보내면 글이
    시리즈에서 빠진다, 2026-10-20 실측).
    """

    id: Annotated[str | None, Field(description='글 ID')] = None
    title: Annotated[str | None, Field(description='제목')] = None
    tags: Annotated[list[str] | None, Field(description='태그')] = None
    body: Annotated[str | None, Field(description='본문')] = None
    is_markdown: Annotated[bool | None, Field(description='본문이 마크다운인지')] = None
    is_private: Annotated[bool | None, Field(description='비공개 여부')] = None
    is_temp: Annotated[bool | None, Field(description='임시저장(초안) 글인지')] = None
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None
    url_slug: Annotated[str | None, Field(description='글 slug')] = None
    meta: Annotated[dict[str, Any] | None, Field(description='글 메타 (short_description 등)')] = None
    series: Annotated[VelogPostForEditSeriesModel | None, Field(description='속한 시리즈')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='글쓴이 (본인 글인지 가린다)')] = None


class VelogPostForEditDataModel(ResponseModel):
    """`ReadPostForEdit` 쿼리의 data."""

    post: Annotated[VelogPostForEditModel | None, Field(description='기존 글. 없거나 볼 수 없는 글이면 null')] = None


class VelogLikeResultModel(ResponseModel):
    """`likePost`·`unlikePost` 결과 (v2 는 `liked` 로 준다)."""

    id: Annotated[str | None, Field(description='글 ID')] = None
    likes: Annotated[int | None, Field(description='현재 좋아요 수')] = None
    liked: Annotated[bool | None, Field(description='내가 좋아요한 상태인지')] = None


class VelogLikePostDataModel(ResponseModel):
    """`likePost` mutation 의 data."""

    like_post: Annotated[
        VelogLikeResultModel | None,
        Field(description='좋아요 결과. 토큰이 만료됐으면 errors 없이 null')
    ] = Field(default=None, alias='likePost')


class VelogUnlikePostDataModel(ResponseModel):
    """`unlikePost` mutation 의 data."""

    unlike_post: Annotated[
        VelogLikeResultModel | None,
        Field(description='좋아요 취소 결과. 토큰이 만료됐으면 errors 없이 null')
    ] = Field(default=None, alias='unlikePost')


class VelogCommentResultModel(ResponseModel):
    """`writeComment` 결과."""

    id: Annotated[str | None, Field(description='댓글 ID')] = None
    text: Annotated[str | None, Field(description='저장된 댓글 내용')] = None
    replies_count: Annotated[int | None, Field(description='대댓글 수')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='작성자(본인)')] = None


class VelogWriteCommentDataModel(ResponseModel):
    """`writeComment` mutation 의 data."""

    write_comment: Annotated[
        VelogCommentResultModel | None,
        Field(description='단 댓글')
    ] = Field(default=None, alias='writeComment')


class VelogStatsDayModel(ResponseModel):
    """일별 조회수 한 칸."""

    day: Annotated[str | None, Field(description='날짜')] = None
    count: Annotated[int | None, Field(description='그날 조회수')] = None


class VelogStatsModel(ResponseModel):
    """`getStats` 결과 (본인 글 조회수)."""

    total: Annotated[int | None, Field(description='전체 조회수')] = None
    count_by_day: Annotated[list[VelogStatsDayModel] | None, Field(description='일별 조회수')] = None


class VelogStatsDataModel(ResponseModel):
    """`getStats` 쿼리의 data."""

    get_stats: Annotated[
        VelogStatsModel | None,
        Field(description='조회수 통계')
    ] = Field(default=None, alias='getStats')
