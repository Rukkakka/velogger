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

    id: str | None = None
    text: Annotated[str | None, Field(description='댓글 내용')] = None
    replies_count: Annotated[int | None, Field(description='대댓글 수')] = None
    level: Annotated[int | None, Field(description='0 이면 최상위 댓글, 1 이상은 대댓글')] = None
    created_at: Annotated[str | None, Field(description='작성 시각 (ISO)')] = None
    deleted: Annotated[bool | None, Field(description='삭제된 댓글인지')] = None
    user: Annotated[VelogPostUserModel | None, Field(description='작성자')] = None


class VelogPostCommentsModel(ResponseModel):
    """`post(id)` 로 받은 댓글 묶음."""

    id: str | None = None
    comments_count: int | None = None
    comments: list[VelogCommentModel] | None = None


class VelogPostCommentsDataModel(ResponseModel):
    """`ReloadComments` 쿼리의 data."""

    post: VelogPostCommentsModel | None = None


class VelogCommentRepliesModel(ResponseModel):
    """`comment(comment_id)` 로 받은 대댓글 묶음."""

    id: str | None = None
    replies: list[VelogCommentModel] | None = None


class VelogCommentRepliesDataModel(ResponseModel):
    """`ReloadReplies` 쿼리의 data."""

    comment: VelogCommentRepliesModel | None = None


class VelogSeriesPostEntryModel(ResponseModel):
    """시리즈 안 글 하나 (순서 `index` 포함)."""

    id: str | None = None
    index: Annotated[int | None, Field(description='시리즈 내 순서')] = None
    post: VelogPostCardModel | None = None


class VelogSeriesDetailModel(ResponseModel):
    """시리즈 상세 (`series(username, url_slug)`)."""

    id: str | None = None
    name: Annotated[str | None, Field(description='시리즈 이름')] = None
    user: VelogPostUserModel | None = None
    series_posts: Annotated[list[VelogSeriesPostEntryModel] | None, Field(description='순서대로의 글')] = None


class VelogSeriesDataModel(ResponseModel):
    """`Series` 쿼리의 data."""

    series: VelogSeriesDetailModel | None = None


class VelogFollowUserModel(ResponseModel):
    """팔로워·팔로잉 목록의 사용자 한 명."""

    id: str | None = None
    user_id: Annotated[str | None, Field(alias='userId', description='사용자 ID')] = None
    username: Annotated[str | None, Field(description='아이디 (@username)')] = None
    is_followed: Annotated[bool | None, Field(description='내가 팔로우 중인지')] = None
    profile: VelogProfileModel | None = None


class VelogFollowersDataModel(ResponseModel):
    """`getFollowers` 쿼리의 data."""

    followers: list[VelogFollowUserModel] | None = None


class VelogFollowingsDataModel(ResponseModel):
    """`getFollowings` 쿼리의 data."""

    followings: list[VelogFollowUserModel] | None = None


class VelogFeedPostsDataModel(ResponseModel):
    """`feedPosts` 쿼리의 data."""

    feed_posts: Annotated[list[VelogPostCardModel] | None, Field(alias='feedPosts')] = None


class VelogReadingListDataModel(ResponseModel):
    """`readingList` 쿼리의 data (좋아요한 글·읽은 글)."""

    reading_list: Annotated[list[VelogPostCardModel] | None, Field(alias='readingList')] = None


class VelogFollowResultModel(ResponseModel):
    """`follow`·`unfollow` 결과."""

    id: str | None = None
    is_followed: Annotated[bool | None, Field(description='팔로우 상태')] = None


class VelogFollowDataModel(ResponseModel):
    """`follow` mutation 의 data."""

    follow: VelogFollowResultModel | None = None


class VelogUnfollowDataModel(ResponseModel):
    """`unfollow` mutation 의 data."""

    unfollow: VelogFollowResultModel | None = None


class VelogEditedCommentModel(ResponseModel):
    """`editComment` 결과."""

    id: str | None = None
    text: str | None = None


class VelogEditCommentDataModel(ResponseModel):
    """`editComment` mutation 의 data."""

    edit_comment: Annotated[VelogEditedCommentModel | None, Field(alias='editComment')] = None


class VelogRemoveCommentDataModel(ResponseModel):
    """`removeComment` mutation 의 data (성공하면 true)."""

    remove_comment: Annotated[bool | None, Field(alias='removeComment')] = None


class VelogCreatedSeriesModel(ResponseModel):
    """`createSeries` 결과."""

    id: str | None = None
    name: str | None = None
    url_slug: str | None = None
    created_at: str | None = None


class VelogCreateSeriesDataModel(ResponseModel):
    """`createSeries` mutation 의 data."""

    create_series: Annotated[VelogCreatedSeriesModel | None, Field(alias='createSeries')] = None


class VelogAppendToSeriesDataModel(ResponseModel):
    """`appendToSeries` mutation 의 data (성공하면 true)."""

    append_to_series: Annotated[bool | None, Field(alias='appendToSeries')] = None
