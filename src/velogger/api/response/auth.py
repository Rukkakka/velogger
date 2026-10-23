from pydantic import (
    ConfigDict,
    Field,
)

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


class VelogCodeLoginResponseModel(ResponseModel):
    """`GET /api/v2/auth/code/{code}` 응답 본문 (velog-server `routes/api/v2/auth/index.ts`, 소스 기준).

    가입된 이메일이면 세션 쿠키를 Set-Cookie 로 주고 본문에 사용자(`...user`, `profile`, `tokens`)를, 계정이 없는
    이메일이면 쿠키 없이 `{email, register_token}` 만 준다 (가입용 code 라 code 를 쓴 것으로 표시하지도 않는다).
    본문의 토큰·이메일은 담지 않는다 (`extra='ignore'`): 모르는 필드를 보존하는 `ResponseModel` 기본값대로 두면 비밀
    값이 모델에 남는다.
    """

    model_config = ConfigDict(validate_by_name=True, extra='ignore')

    username: Annotated[
        str | None,
        Field(description='로그인한 계정의 아이디 (@username). 가입용 code 면 없다')
    ] = None
    is_trusted: Annotated[
        bool | None,
        Field(description='신뢰 계정 여부. velog-server 소스의 User 에는 없는 필드라 오지 않을 수 있다')
    ] = None
    register_token: Annotated[
        str | None,
        Field(repr=False, description='계정이 없는 이메일일 때 주는 가입용 토큰 (비밀). 있는지만 본다')
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

    auth: Annotated[VelogAuthUserModel | None, Field(description='로그인한 사용자. 로그인하지 않았으면 null')] = None


class VelogAuthResponseModel(VelogGraphQLResponse[VelogAuthDataModel]):
    """v2 GraphQL `auth` 쿼리의 전체 응답 (`data` + `errors`). 다른 GraphQL 응답과 같은 봉투라 `graphql_data()` 로 판정한다."""
