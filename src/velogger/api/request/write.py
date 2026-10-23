from pydantic import Field

from velogger.core.schema import (
    NonBlankStr,
    RequestModel,
)

from typing import (
    Annotated,
    Any,
)


class VelogWritePostRequestPayloadModel(RequestModel):
    """v2 `writePost` mutation 변수. 신뢰 계정(is_trusted)은 token(Turnstile) 없이 발행된다.

    `is_temp=True` 면 임시저장(초안), False 면 발행. 비공개는 `is_private`. 변수는 velog 스키마 이름 그대로
    (snake_case)라 별칭이 없다.

    **값이 없는 필드도 null 로 꼭 보낸다** (`exclude_none` 을 쓰지 않는다). v2 는 받은 인자를 그대로 내부 v3 의
    `WritePostInput` 으로 넘기는데, 키가 빠지면 내부 v3 가 거절하고 v2 는 그 에러를 삼켜 `writePost: null` 만
    돌려준다 (2026-10-19 실측: thumbnail·series_id·meta·token 을 빼면 null, 넣으면 저장됨). 웹(CRA)도 이
    필드들을 null 이라도 항상 보낸다.
    """

    title: Annotated[str, Field(description='제목')]
    body: Annotated[str, Field(description='본문 (is_markdown 이면 마크다운)')]
    tags: Annotated[list[str], Field(description='태그 목록')] = []
    is_markdown: Annotated[bool, Field(description='본문이 마크다운인지')] = True
    is_temp: Annotated[bool, Field(description='임시저장(초안)인지. False 면 발행')] = True
    is_private: Annotated[bool, Field(description='비공개 여부')] = False
    url_slug: Annotated[str, Field(description='글 slug')]
    thumbnail: Annotated[str | None, Field(description='썸네일 이미지 URL')] = None
    series_id: Annotated[str | None, Field(description='넣을 시리즈 ID')] = None
    meta: Annotated[
        dict[str, Any],
        Field(description='글 메타 (웹은 short_description 등을 넣는다). 비어 있어도 키는 보낸다')
    ] = {}
    token: Annotated[
        str | None,
        Field(repr=False, description='Cloudflare Turnstile 토큰. 신뢰 계정은 null (CLI 는 캡차를 풀지 않는다)')
    ] = None


class VelogEditPostRequestPayloadModel(VelogWritePostRequestPayloadModel):
    """v2 `editPost` mutation 변수. `id` 로 고칠 글을 고르고, 나머지는 writePost 와 같다.

    편집은 기존 글을 먼저 읽어(ReadPostForEdit) 바꾸지 않은 필드를 채운 뒤 보낸다 (본문 등이 지워지지 않게).
    """

    id: Annotated[str, Field(description='고칠 글 ID')]


class VelogWriteCommentRequestPayloadModel(RequestModel):
    """v2 `writeComment` mutation 변수."""

    post_id: Annotated[str, Field(description='댓글을 달 글 ID')]
    text: Annotated[NonBlankStr, Field(description='댓글 내용')]
    comment_id: Annotated[str | None, Field(description='대댓글이면 부모 댓글 ID')] = None


class VelogEditCommentRequestPayloadModel(RequestModel):
    """v2 `editComment` mutation 변수.

    velog 는 빈 text 도 그대로 저장해 댓글이 비므로(velog-server `editComment` 리졸버는 검사 없이 `comment.text = text`)
    여기서 막는다. 공백만 있는 text 도 빈 댓글로 보여 함께 막는다 (`NonBlankStr`, `writeComment` 와 같다).
    """

    id: Annotated[str, Field(description='고칠 댓글 ID')]
    text: Annotated[NonBlankStr, Field(description='새 댓글 내용')]


class VelogCreateSeriesRequestPayloadModel(RequestModel):
    """v2 `createSeries` mutation 변수.

    velog 는 빈 이름도 받아 이름 없는 시리즈를 만든다 (velog-server `createSeries` 리졸버는 이름을 검사하지 않는다).
    공백만 있는 이름·slug 도 같아 함께 막는다 (`NonBlankStr`).
    """

    name: Annotated[NonBlankStr, Field(description='시리즈 이름')]
    url_slug: Annotated[NonBlankStr, Field(description='시리즈 slug')]
