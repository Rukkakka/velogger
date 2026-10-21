from pydantic import Field

from velogger.core.schema import RequestModel

from typing import Annotated


class VelogSendmailRequestPayloadModel(RequestModel):
    """`POST /api/v2/auth/sendmail` 본문. 이메일로 로그인/가입 링크를 보내 달라고 요청한다."""

    email: Annotated[
        str,
        Field(description='로그인 링크를 받을 이메일 주소')
    ]
