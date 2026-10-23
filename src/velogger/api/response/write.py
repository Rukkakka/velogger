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
        Field(description='저장된 글. v2 가 내부 에러를 삼키면 errors 없이 null', alias='writePost')
    ] = None


class VelogEditPostDataModel(ResponseModel):
    """`editPost` mutation 의 data."""

    edit_post: Annotated[
        VelogWrittenPostModel | None,
        Field(description='고친 글. v2 가 내부 에러를 삼키면 errors 없이 null', alias='editPost')
    ] = None


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
        Field(description='좋아요 결과. 토큰이 만료됐으면 errors 없이 null', alias='likePost')
    ] = None


class VelogUnlikePostDataModel(ResponseModel):
    """`unlikePost` mutation 의 data."""

    unlike_post: Annotated[
        VelogLikeResultModel | None,
        Field(description='좋아요 취소 결과. 토큰이 만료됐으면 errors 없이 null', alias='unlikePost')
    ] = None


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
        Field(description='단 댓글', alias='writeComment')
    ] = None


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
        Field(description='조회수 통계', alias='getStats')
    ] = None


class VelogFollowResultModel(ResponseModel):
    """`follow`·`unfollow` 결과."""

    id: Annotated[str | None, Field(description='대상 사용자 ID')] = None
    is_followed: Annotated[bool | None, Field(description='팔로우 상태')] = None


class VelogFollowDataModel(ResponseModel):
    """`follow` mutation 의 data."""

    follow: Annotated[VelogFollowResultModel | None, Field(description='팔로우 결과')] = None


class VelogUnfollowDataModel(ResponseModel):
    """`unfollow` mutation 의 data."""

    unfollow: Annotated[VelogFollowResultModel | None, Field(description='팔로우 취소 결과')] = None


class VelogEditedCommentModel(ResponseModel):
    """`editComment` 결과."""

    id: Annotated[str | None, Field(description='댓글 ID')] = None
    text: Annotated[str | None, Field(description='고친 내용')] = None


class VelogEditCommentDataModel(ResponseModel):
    """`editComment` mutation 의 data."""

    edit_comment: Annotated[
        VelogEditedCommentModel | None,
        Field(description='고친 댓글', alias='editComment')
    ] = None


class VelogRemoveCommentDataModel(ResponseModel):
    """`removeComment` mutation 의 data (성공하면 true)."""

    remove_comment: Annotated[
        bool | None,
        Field(description='지워졌는지', alias='removeComment')
    ] = None


class VelogCreatedSeriesModel(ResponseModel):
    """`createSeries` 결과."""

    id: Annotated[str | None, Field(description='시리즈 ID')] = None
    name: Annotated[str | None, Field(description='시리즈 이름')] = None
    url_slug: Annotated[str | None, Field(description='시리즈 slug')] = None
    created_at: Annotated[str | None, Field(description='만든 시각 (ISO)')] = None


class VelogCreateSeriesDataModel(ResponseModel):
    """`createSeries` mutation 의 data."""

    create_series: Annotated[
        VelogCreatedSeriesModel | None,
        Field(description='만든 시리즈', alias='createSeries')
    ] = None


class VelogAppendToSeriesDataModel(ResponseModel):
    """`appendToSeries` mutation 의 data. 성공하면 넣은 글의 시리즈 안 순번(1부터)이다.

    velog-server 는 `appendToSeries(...): Int` 로 정의하고 `nextIndex` 를 돌려준다 (velopert/velog-server
    `src/graphql/series.ts`). bool 로 받으면 첫 글(1)만 통과하고 두 번째 글(2)부터 검증에 실패한다 (2026-10-22 실측: 7편을
    차례로 넣으니 2편부터 PARSE_ERROR 였는데 모두 들어가 있었다).
    """

    append_to_series: Annotated[
        int | None,
        Field(description='넣은 글의 시리즈 안 순번 (1부터)', alias='appendToSeries')
    ] = None
