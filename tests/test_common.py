"""여러 명령이 같이 쓰는 판정. 에러 코드가 틀어지면 에이전트가 다시 보내도 같은 요청을 되풀이한다."""

import pytest

from velogger.api.response.common import VelogGraphQLResponse
from velogger.core.errors import VeloggerError
from velogger.service.common import graphql_data


# --- GraphQL 에러 판정 ---

@pytest.mark.parametrize(
    ('error', 'code'),
    [
        # 2026-10-23 실측: 가짜 id·남의 글·한도 초과·익명으로 보낸 요청이 받은 errors 그대로
        ({'message': 'Post not found', 'extensions': {'code': 'NOT_FOUND'}, 'path': ['getStats']}, 'NOT_FOUND'),
        # 코드 없이 메시지로만 없다고 한다 (editComment·removeComment)
        ({'message': 'Comment not found', 'extensions': {'code': 'INTERNAL_SERVER_ERROR'}, 'path': ['editComment']}, 'NOT_FOUND'),
        ({'message': 'This post is not yours', 'extensions': {'code': 'NO_PERMISSION'}, 'path': ['getStats']}, 'FORBIDDEN'),
        ({'message': 'Max limit is 100', 'extensions': {'code': 'BAD_REQUEST'}, 'path': ['readingList']}, 'INVALID_ARGUMENT'),
        ({'message': 'Not Logged In', 'extensions': {'code': 'UNAUTHENTICATED'}, 'path': ['readingList']}, 'NOT_LOGGED_IN'),
        # NO_PERMISSION 이지만 로그인 안 됨이다 (익명 drafts). FORBIDDEN('내 것인지 확인')이면 에이전트가 id 를 찾아 헤맨다
        ({'message': 'Not logged in', 'extensions': {'code': 'NO_PERMISSION'}, 'path': ['posts']}, 'NOT_LOGGED_IN'),
        # 2026-10-21 실측: 같은 slug 의 시리즈·이미 시리즈에 든 글. 다시 보내 보면 실제로 생길 수 있어 다시 재지 않았다
        ({'message': 'URL Slug already exists', 'extensions': {'code': 'ALREADY_EXISTS'}}, 'ALREADY_EXISTS'),
        ({'message': 'Already added to series', 'extensions': {'code': 'CONFLICT'}}, 'ALREADY_EXISTS'),
        # 그 밖은 '잠시 뒤 다시 시도' 의 UPSTREAM_ERROR
        ({'message': 'Internal server error', 'extensions': {'code': 'INTERNAL_SERVER_ERROR'}}, 'UPSTREAM_ERROR'),
    ],
)
def test_graphql_errors_map_to_codes_that_say_whether_retrying_helps(error, code):
    """HTTP 200 안의 errors 를 에이전트가 다음 행동을 고를 수 있는 코드로 바꾼다 (출력 계약, references/output-contract.md).

    UPSTREAM_ERROR 의 '잠시 뒤 다시 시도' 로 두면 없는 id·남의 글·겹친 slug·잘못된 값으로 같은 요청을 되풀이한다.
    """
    response = VelogGraphQLResponse[dict].model_validate({'data': None, 'errors': [error]})

    with pytest.raises(VeloggerError) as caught:
        graphql_data(response)
    assert caught.value.code == code
