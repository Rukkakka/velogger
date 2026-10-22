"""댓글·시리즈·팔로우·피드 응답 모델."""

from pydantic import Field

from velogger.api.response.common import (
    VelogPostUserModel,
    VelogProfileModel,
)
from velogger.api.response.posts import VelogPostCardModel
from velogger.core.schema import ResponseModel

from typing import Annotated


class VelogCommentModel(ResponseModel):
    """댓글 하나. 작성자는 v2 에서만 채워진다 (v3 는 null).

    `deleted` 면 velog 웹도 '삭제된 댓글' 로만 보여 주므로 text 가 비어 온다.
    """

    id: Annotated[str | None, Field(description='댓글 ID')] = None
    text: Annotated[str | None, Field(description='댓글 내용')] = None
    replies_count: Annotated[int | None, Field(description='대댓글 수')] = None
    level: Annotated[int | None, Field(description='0 이면 최상위 댓글, 1·2 는 대댓글 (velog 는 2까지)')] = None
    created_at: Annotated[str | None, Field(description='작성 시각 (ISO)')] = None
    deleted: Annotated[bool | None, Field(description='삭제된 댓글인지')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='작성자')] = None
    replies: Annotated[
        list['VelogCommentModel'] | None,
        Field(description='대댓글. `ReloadReplies` 가 요청한 단계까지만 온다 (요청하지 않은 단계는 null)')
    ] = None


class VelogPostCommentsModel(ResponseModel):
    """`post(id)` 로 받은 댓글 묶음."""

    id: Annotated[str | None, Field(description='글 ID')] = None
    comments_count: Annotated[int | None, Field(description='전체 댓글 수 (대댓글 포함)')] = None
    comments: Annotated[list[VelogCommentModel] | None, Field(description='최상위 댓글')] = None


class VelogPostCommentsDataModel(ResponseModel):
    """`ReloadComments` 쿼리의 data."""

    post: Annotated[VelogPostCommentsModel | None, Field(description='글의 댓글 묶음. 없는 글이면 null')] = None


class VelogCommentRepliesModel(ResponseModel):
    """`comment(comment_id)` 로 받은 대댓글 묶음."""

    id: Annotated[str | None, Field(description='부모 댓글 ID')] = None
    replies: Annotated[list[VelogCommentModel] | None, Field(description='대댓글 (그 대댓글까지)')] = None


class VelogCommentRepliesDataModel(ResponseModel):
    """`ReloadReplies` 쿼리의 data."""

    comment: Annotated[VelogCommentRepliesModel | None, Field(description='부모 댓글. 없는 댓글이면 null')] = None


class VelogSeriesPostEntryModel(ResponseModel):
    """시리즈 안 글 하나 (순서 `index` 포함)."""

    id: Annotated[str | None, Field(description='시리즈 칸 ID (글 ID 가 아니다)')] = None
    index: Annotated[int | None, Field(description='시리즈 내 순서')] = None
    post: Annotated[VelogPostCardModel | None, Field(description='그 칸의 글')] = None


class VelogSeriesDetailModel(ResponseModel):
    """시리즈 상세 (`series(username, url_slug)`)."""

    id: Annotated[str | None, Field(description='시리즈 ID')] = None
    name: Annotated[str | None, Field(description='시리즈 이름')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='시리즈 주인')] = None
    series_posts: Annotated[list[VelogSeriesPostEntryModel] | None, Field(description='순서대로의 글')] = None


class VelogSeriesDataModel(ResponseModel):
    """`Series` 쿼리의 data."""

    series: Annotated[VelogSeriesDetailModel | None, Field(description='시리즈. 없는 시리즈면 null')] = None


class VelogFollowUserModel(ResponseModel):
    """팔로워·팔로잉 목록의 사용자 한 명."""

    id: Annotated[
        str | None,
        Field(description='팔로우 관계 ID. 사용자 ID 가 아니다 (2026-10-21 실측: 사용자 ID 는 userId 와 같고 이 값은 다르다)')
    ] = None
    user_id: Annotated[
        str | None,
        Field(description='사용자 ID')
    ] = Field(default=None, alias='userId')
    username: Annotated[str | None, Field(description='아이디 (@username)')] = None
    is_followed: Annotated[bool | None, Field(description='내가 팔로우 중인지')] = None
    profile: Annotated[VelogProfileModel | None, Field(description='프로필')] = None


class VelogFollowersDataModel(ResponseModel):
    """`getFollowers` 쿼리의 data."""

    followers: Annotated[list[VelogFollowUserModel] | None, Field(description='팔로워')] = None


class VelogFollowingsDataModel(ResponseModel):
    """`getFollowings` 쿼리의 data."""

    followings: Annotated[list[VelogFollowUserModel] | None, Field(description='팔로잉')] = None


class VelogFeedPostsDataModel(ResponseModel):
    """`feedPosts` 쿼리의 data."""

    feed_posts: Annotated[
        list[VelogPostCardModel] | None,
        Field(description='팔로우한 사람들의 글 카드. 로그인이 안 됐어도 에러 없이 []')
    ] = Field(default=None, alias='feedPosts')


class VelogReadingListDataModel(ResponseModel):
    """`readingList` 쿼리의 data (좋아요한 글·읽은 글)."""

    reading_list: Annotated[
        list[VelogPostCardModel] | None,
        Field(description='좋아요한 글이나 읽은 글 카드')
    ] = Field(default=None, alias='readingList')


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
        Field(description='고친 댓글')
    ] = Field(default=None, alias='editComment')


class VelogRemoveCommentDataModel(ResponseModel):
    """`removeComment` mutation 의 data (성공하면 true)."""

    remove_comment: Annotated[
        bool | None,
        Field(description='지워졌는지')
    ] = Field(default=None, alias='removeComment')


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
        Field(description='만든 시리즈')
    ] = Field(default=None, alias='createSeries')


class VelogAppendToSeriesDataModel(ResponseModel):
    """`appendToSeries` mutation 의 data. 성공하면 넣은 글의 시리즈 안 순번(1부터)이다.

    velog-server 는 `appendToSeries(...): Int` 로 정의하고 `nextIndex` 를 돌려준다 (velopert/velog-server
    `src/graphql/series.ts`). bool 로 받으면 첫 글(1)만 통과하고 두 번째 글(2)부터 검증에 실패한다 (2026-10-22 실측: 7편을
    차례로 넣으니 2편부터 PARSE_ERROR 였는데 모두 들어가 있었다).
    """

    append_to_series: Annotated[
        int | None,
        Field(description='넣은 글의 시리즈 안 순번 (1부터)')
    ] = Field(default=None, alias='appendToSeries')
