from pydantic import Field

from velogger.core.schema import RequestModel

from typing import Annotated


class VelogGetUserRequestPayloadModel(RequestModel):
    """v3 `user`·`userTags`·시리즈 목록 쿼리가 함께 쓰는 input (GetUserInput·UserTagsInput)."""

    username: Annotated[str, Field(description='사용자 아이디 (@username)')]
