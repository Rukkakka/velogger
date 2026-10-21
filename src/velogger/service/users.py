"""사용자·태그 조회 (`user`·`tag`)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from velogger.api.client import VelogClient
from velogger.api.request.users import VelogGetUserRequestPayloadModel
from velogger.api.response.users import (
    VelogTagInfoModel,
    VelogUserDataModel,
)
from velogger.core.errors import VeloggerError
from velogger.service.common import (
    VELOG_BASE,
    graphql_data,
    series_url,
)

from typing import Annotated


class VelogUserTagRef(BaseModel):
    """사용자가 쓴 태그 하나."""

    model_config = ConfigDict(extra='forbid')

    name: Annotated[str | None, Field(description='태그 이름')] = None
    posts_count: Annotated[int | None, Field(description='이 사용자가 이 태그로 쓴 글 수')] = None


class VelogUserSeriesRef(BaseModel):
    """사용자의 시리즈 하나."""

    model_config = ConfigDict(extra='forbid')

    name: Annotated[str | None, Field(description='시리즈 이름')] = None
    url: Annotated[str | None, Field(description='시리즈 주소')] = None
    posts_count: Annotated[int | None, Field(description='시리즈 안 글 수')] = None


class VelogUserProfile(BaseModel):
    """사용자 프로필 + 태그 + 시리즈. 글 목록은 `velogger posts <username>` 로 받는다."""

    model_config = ConfigDict(extra='forbid')

    username: Annotated[str | None, Field(description='아이디 (@username)')] = None
    display_name: Annotated[str | None, Field(description='표시 이름')] = None
    short_bio: Annotated[str | None, Field(description='한 줄 소개')] = None
    thumbnail: Annotated[str | None, Field(description='프로필 이미지 URL')] = None
    url: Annotated[str | None, Field(description='블로그 주소')] = None
    links: Annotated[dict[str, str] | None, Field(description='외부 링크 (github·twitter·url·email 등). 없으면 {}')] = None
    posts_count: Annotated[int | None, Field(description='전체 글 수')] = None
    tags: Annotated[list[VelogUserTagRef] | None, Field(description='많이 쓴 태그. 없으면 []')] = None
    series: Annotated[list[VelogUserSeriesRef] | None, Field(description='시리즈 목록. 없으면 []')] = None


class VelogTagInfo(BaseModel):
    """태그 정보. 그 태그의 글 목록은 `velogger tag <name>` 이 함께 돌려준다.

    태그 전체 글 수는 여기 두지 않고 목록의 `count`(캐시 tag-posts)로 준다. v3 `tag.posts_count` 는 늘 0 이라
    (2026-10-20 실측: react 가 `posts_count: 0`, 같은 응답의 `count` 는 56891) 그대로 내면 에이전트가 '글 없는 태그' 로 읽는다.
    """

    model_config = ConfigDict(extra='forbid')

    name: Annotated[str | None, Field(description='태그 이름')] = None
    description: Annotated[str | None, Field(description='태그 설명')] = None


def _profile_of(data: VelogUserDataModel, username: str) -> VelogUserProfile:
    # velog 가 빈 목록(`series_list: []`, `userTags.tags: []`, `profile_links: {}`)을 주면 그대로 비어 있음으로 낸다.
    # null 로 바꾸면 '모름' 이 돼 에이전트가 시리즈·태그가 없다고 하지 못한다 (2026-10-20 실측: 시리즈 없는 사용자가
    # `series: null` 로 나왔다). velog 가 필드 자체를 안 줬을 때만 null 이다.
    user = data.user
    profile = user.profile if user else None
    links = None
    if profile and profile.profile_links is not None:
        # 빈 값은 빼서 깔끔하게. 문자열 값만 남긴다.
        links = {key: value for key, value in profile.profile_links.items() if isinstance(value, str) and value}
    tags = None
    series = None
    posts_count = None
    if data.user_tags is not None:
        posts_count = data.user_tags.posts_count
        if data.user_tags.tags is not None:
            tags = [VelogUserTagRef(name=tag.name, posts_count=tag.posts_count) for tag in data.user_tags.tags]
    if user is not None and user.series_list is not None:
        series = [
            VelogUserSeriesRef(
                name=item.name,
                url=series_url(username, item.url_slug),
                posts_count=item.posts_count,
            )
            for item in user.series_list
        ]
    return VelogUserProfile(
        username=user.username if user else username,
        display_name=profile.display_name if profile else None,
        short_bio=profile.short_bio if profile else None,
        thumbnail=profile.thumbnail if profile else None,
        url=f'{VELOG_BASE}/@{username}',
        links=links,
        posts_count=posts_count,
        tags=tags,
        series=series,
    )


def get_user(client: VelogClient, username: str) -> VelogUserProfile:
    """사용자 프로필·태그·시리즈를 조회한다 (v3 `user` + `userTags`).

    Raises:
        VeloggerError: 사용자가 없을 때 (`NOT_FOUND`).
    """
    data = graphql_data(client.run_request_user(VelogGetUserRequestPayloadModel(username=username)))
    if data is None or data.user is None:
        raise VeloggerError(
            code='NOT_FOUND',
            message=f'사용자를 찾지 못했습니다: @{username}',
            hint='username(@ 뒤 아이디)이 맞는지 확인하세요',
        )
    return _profile_of(data, username)


def _tag_info_of(info: VelogTagInfoModel) -> VelogTagInfo:
    return VelogTagInfo(name=info.name, description=info.description)


def get_tag_info(client: VelogClient, name: str) -> VelogTagInfo | None:
    """태그 이름·설명 (v3 `tag`). 태그가 없으면 None (글 목록 조회는 계속한다). 전체 글 수는 목록의 `count` 다."""
    data = graphql_data(client.run_request_tag(name))
    if data is None or data.tag is None:
        return None
    return _tag_info_of(data.tag)
