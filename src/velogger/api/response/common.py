"""여러 기능이 같이 쓰는 응답 모델 (GraphQL 봉투·사용자·프로필 등)."""

from pydantic import Field

from velogger.core.schema import ResponseModel

from typing import (
    Annotated,
    Any,
    Generic,
    TypeVar,
)


_Data = TypeVar('_Data')


class VelogGraphQLErrorModel(ResponseModel):
    """GraphQL 응답의 `errors` 항목. velog 는 인증 실패·잘못된 입력도 HTTP 200 안의 이 배열로 알린다."""

    message: Annotated[
        str | None,
        Field(description='에러 메시지')
    ] = None
    extensions: Annotated[
        dict[str, Any] | None,
        Field(description="추가 정보 (예: {'code': 'UNAUTHENTICATED'})")
    ] = None


class VelogProfileModel(ResponseModel):
    """사용자 프로필. GraphQL 필드 이름이 snake_case 라 별칭이 필요 없다."""

    display_name: Annotated[str | None, Field(description='표시 이름')] = None
    thumbnail: Annotated[str | None, Field(description='프로필 이미지 URL')] = None
    short_bio: Annotated[str | None, Field(description='한 줄 소개')] = None
    profile_links: Annotated[
        dict[str, Any] | None,
        Field(description='외부 링크 (github·twitter·url·email 등). user 조회에서만 요청한다')
    ] = None


class VelogPostUserModel(ResponseModel):
    """글 목록·상세에 실리는 글쓴이. v3 GraphQL 공통."""

    id: Annotated[str | None, Field(description='사용자 ID')] = None
    username: Annotated[str | None, Field(description='아이디 (@username)')] = None
    profile: Annotated[VelogProfileModel | None, Field(description='프로필')] = None


class VelogGraphQLResponse(ResponseModel, Generic[_Data]):
    """GraphQL 응답 봉투. `data`(쿼리별 데이터 모델)와 `errors`(HTTP 200 안의 실패)를 함께 담는다.

    service 가 `errors` 를 판정한다 (UNAUTHENTICATED → 로그인 안 됨, 그 밖은 UPSTREAM_ERROR).
    """

    data: _Data | None = None
    errors: list[VelogGraphQLErrorModel] | None = None
