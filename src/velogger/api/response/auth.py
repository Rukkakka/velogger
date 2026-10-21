from pydantic import Field

from velogger.api.response.common import (
    VelogGraphQLResponse,
    VelogProfileModel,
)
from velogger.core.schema import ResponseModel

from typing import Annotated


class VelogSendmailResponseModel(ResponseModel):
    """`POST /api/v2/auth/sendmail` 응답. 그 이메일이 이미 가입돼 있는지 알려 준다.

    `registered` 가 True 면 로그인 링크, False 면 가입 링크를 보냈다는 뜻이다 (velog 가 어느 쪽이든
    메일을 보낸다). velog 가 필드 이름을 바꿔도 깨지지 않도록 선택 필드로 둔다.
    """

    registered: Annotated[
        bool | None,
        Field(description='이미 가입된 이메일인지 (True 면 로그인 메일, False 면 가입 메일)')
    ] = None


class VelogAuthUserModel(ResponseModel):
    """로그인한 사용자. v2 GraphQL `auth` 쿼리의 결과이자 `code` 로그인 응답 본문의 사용자."""

    id: Annotated[str | None, Field(description='사용자 ID (UUID)')] = None
    username: Annotated[str | None, Field(description='velog 아이디 (@username)')] = None
    email: Annotated[str | None, Field(repr=False, description='계정 이메일')] = None
    is_trusted: Annotated[
        bool | None,
        Field(description='신뢰 계정 여부. False 면 글 발행에 Cloudflare Turnstile 캡차가 붙는다')
    ] = None
    profile: Annotated[VelogProfileModel | None, Field(description='프로필')] = None


class VelogAuthDataModel(ResponseModel):
    """`auth` 쿼리 응답의 `data`. 로그인하지 않았으면 `auth` 가 null 이다."""

    auth: VelogAuthUserModel | None = None


class VelogAuthResponseModel(VelogGraphQLResponse[VelogAuthDataModel]):
    """v2 GraphQL `auth` 쿼리의 전체 응답 (`data` + `errors`). 다른 GraphQL 응답과 같은 봉투라 `graphql_data()` 로 판정한다."""
