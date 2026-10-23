from pydantic import Field

from velogger.api.response.common import VelogProfileModel
from velogger.core.schema import ResponseModel

from typing import Annotated


class VelogSeriesListItemModel(ResponseModel):
    """사용자의 시리즈 하나 (`user.series_list`)."""

    id: Annotated[str | None, Field(description='시리즈 ID')] = None
    name: Annotated[str | None, Field(description='시리즈 이름')] = None
    description: Annotated[str | None, Field(description='설명')] = None
    url_slug: Annotated[str | None, Field(description='시리즈 slug')] = None
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None
    updated_at: Annotated[str | None, Field(description='수정 시각 (ISO)')] = None
    posts_count: Annotated[int | None, Field(description='시리즈 안 글 수')] = None


class VelogUserModel(ResponseModel):
    """사용자. `user` 조회에서 프로필과 시리즈 목록까지 받는다."""

    id: Annotated[str | None, Field(description='사용자 ID')] = None
    username: Annotated[str | None, Field(description='아이디 (@username)')] = None
    profile: Annotated[VelogProfileModel | None, Field(description='프로필')] = None
    series_list: Annotated[list[VelogSeriesListItemModel] | None, Field(description='시리즈 목록')] = None


class VelogUserTagModel(ResponseModel):
    """사용자가 쓴 태그 하나 (`userTags.tags`)."""

    id: Annotated[str | None, Field(description='태그 ID')] = None
    name: Annotated[str | None, Field(description='태그 이름')] = None
    description: Annotated[str | None, Field(description='설명')] = None
    posts_count: Annotated[int | None, Field(description='이 사용자가 이 태그로 쓴 글 수')] = None
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None


class VelogUserTagsModel(ResponseModel):
    """`userTags` 값. 사용자의 태그 목록과 전체 글 수."""

    posts_count: Annotated[int | None, Field(description='사용자의 전체 글 수')] = None
    tags: Annotated[list[VelogUserTagModel] | None, Field(description='사용자가 쓴 태그')] = None


class VelogUserDataModel(ResponseModel):
    """`user` + `userTags` 를 한 번에 받는 쿼리의 data."""

    user: Annotated[VelogUserModel | None, Field(description='사용자. 없는 사용자면 null')] = None
    user_tags: Annotated[
        VelogUserTagsModel | None,
        Field(description='사용자의 태그 목록', alias='userTags')
    ] = None


class VelogUserIdDataModel(ResponseModel):
    """`user` 를 id·username 만 받는 쿼리(`velogUserId`)의 data. 없는 사용자면 `user` 가 null."""

    user: Annotated[VelogUserModel | None, Field(description='사용자 (id·username 만). 없는 사용자면 null')] = None


class VelogTagInfoModel(ResponseModel):
    """태그 정보 (`tag(name)`)."""

    id: Annotated[str | None, Field(description='태그 ID')] = None
    name: Annotated[str | None, Field(description='태그 이름')] = None
    posts_count: Annotated[
        int | None,
        Field(description='태그 전체 글 수라지만 v3 는 늘 0 을 준다 (2026-10-20 실측). 실제 수는 캐시 tag-posts 의 count')
    ] = None
    description: Annotated[str | None, Field(description='태그 설명')] = None
    thumbnail: Annotated[str | None, Field(description='썸네일 URL')] = None


class VelogTagDataModel(ResponseModel):
    """`tag(name)` 쿼리의 data."""

    tag: Annotated[VelogTagInfoModel | None, Field(description='태그 정보. 없는 태그면 null')] = None
