"""쓰기 경로의 핵심 동작. velog 가 조용히 실패하는 지점을 지킨다."""

import json

import httpx
import pytest

from velogger.api.client import VelogClient
from velogger.api.request.write import VelogWritePostRequestPayloadModel
from velogger.core.errors import VeloggerError
from velogger.service.write import (
    add_to_series,
    edit_post,
    like_post,
    publish,
    slugify,
    upload_image,
)


# --- writePost 인자 (조용한 실패 방지) ---

WRITE_POST_KEYS = (
    'title', 'body', 'tags', 'is_markdown', 'is_temp',
    'is_private', 'url_slug', 'thumbnail', 'meta', 'series_id', 'token',
)


AUTH_OK = {'data': {'auth': {'id': 'u1', 'username': 'me', 'email': 'me@example.com', 'is_trusted': True}}}


def _mock_client(handler) -> VelogClient:
    client = VelogClient()
    client.__dict__['_client'] = httpx.Client(base_url=client.base_url, transport=httpx.MockTransport(handler))
    return client


def test_write_post_sends_every_argument_even_when_empty():
    """값이 없는 인자도 null 로 보내야 한다.

    v2 writePost 는 받은 인자를 내부 v3 로 그대로 넘기는데, thumbnail·series_id·meta·token 키가 빠지면 내부
    v3 가 거절하고 v2 는 그 에러를 삼켜 HTTP 200 + `writePost: null` 만 준다 (2026-10-19 실측). 에러가 전혀
    안 보여 원인을 찾기 어려우므로, 인자를 빠뜨리지 않는지 여기서 지킨다 (`exclude_none` 금지).
    """
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['body'] = json.loads(request.content)
        return httpx.Response(
            200,
            json={'data': {'writePost': {'id': 'p1', 'url_slug': 's', 'user': {'id': 'u1', 'username': 'me'}}}},
        )

    client = _mock_client(handler)
    client.run_request_write_post(
        VelogWritePostRequestPayloadModel(title='제목', body='본문', tags=[], url_slug='제목')
    )

    variables = captured['body']['variables']  # type: ignore[index]
    missing = [key for key in WRITE_POST_KEYS if key not in variables]
    assert missing == [], f'writePost 인자가 빠졌다 (velog 가 null 만 돌려준다): {missing}'
    assert variables['thumbnail'] is None
    assert variables['series_id'] is None
    assert variables['token'] is None
    assert variables['meta'] == {}


def test_edit_keeps_fields_that_were_not_given():
    """편집에서 안 준 필드는 현재 값을 그대로 보낸다 (본문이 지워지지 않게).

    시리즈·meta 도 마찬가지다. editPost 는 보낸 값으로 덮어, series_id 를 null 로 보내면 글이 시리즈에서 빠진다
    (2026-10-20 실측: 제목만 고쳤는데 시리즈에서 빠졌다).
    """
    sent: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        query = body['query']
        if 'ReadPostForEdit' in query:
            return httpx.Response(200, json={'data': {'post': {
                'id': 'p1', 'title': '원래 제목', 'body': '원래 본문', 'tags': ['a'],
                'is_markdown': True, 'is_private': False, 'is_temp': True,
                'thumbnail': 'https://img', 'url_slug': 'orig',
                'meta': {'short_description': '원래 요약'}, 'series': {'id': 's1', 'name': '시리즈'},
                'user': {'id': 'u1', 'username': 'me'},
            }}})
        if 'auth {' in query:
            # 쓰기 전 로그인 확인 겸 토큰 갱신 (require_auth)
            return httpx.Response(200, json=AUTH_OK)
        sent['variables'] = body['variables']
        return httpx.Response(
            200,
            json={'data': {'editPost': {'id': 'p1', 'url_slug': 'orig', 'user': {'id': 'u1', 'username': 'me'}}}},
        )

    client = _mock_client(handler)
    # 제목만 바꾼다. 본문·태그·썸네일은 건드리지 않는다.
    edit_post(client, 'p1', title='새 제목')

    variables = sent['variables']  # type: ignore[index]
    assert variables['title'] == '새 제목'
    assert variables['body'] == '원래 본문'
    assert variables['tags'] == ['a']
    assert variables['thumbnail'] == 'https://img'
    assert variables['is_temp'] is True
    assert variables['series_id'] == 's1', 'series_id 가 빠지면 글이 시리즈에서 빠진다'
    assert variables['meta'] == {'short_description': '원래 요약'}


@pytest.mark.parametrize(
    ('post', 'code'),
    [
        # ReadPostForEdit 는 남의 공개 글도 준다 (2026-10-21 실측). 보내면 v2 가 거절을 삼켜 UPSTREAM_ERROR 가 된다
        ({'is_temp': False, 'is_private': False, 'user': {'id': 'someone-else', 'username': 'other'}}, 'FORBIDDEN'),
        # 발행 상태를 모르면 초안(is_temp=True)으로 추측해 보내 발행된 글이 내려갔다
        ({'is_temp': None, 'is_private': False, 'user': {'id': 'u1', 'username': 'me'}}, 'PARSE_ERROR'),
        # 공개 여부를 모르면 공개(False)로 추측해 보내 비공개 글이 공개됐다
        ({'is_temp': False, 'is_private': None, 'user': {'id': 'u1', 'username': 'me'}}, 'PARSE_ERROR'),
        # 본문을 모르면 '' 로 채워 보내 본문이 지워졌다 (--body 없이 제목만 고칠 때)
        ({'is_temp': False, 'is_private': False, 'body': None, 'user': {'id': 'u1', 'username': 'me'}}, 'PARSE_ERROR'),
        # meta 를 모르면 {} 로 보내 사용자가 쓴 요약(meta.short_description)이 본문에서 뽑은 요약으로 바뀌었다
        ({'is_temp': False, 'is_private': False, 'meta': None, 'user': {'id': 'u1', 'username': 'me'}}, 'PARSE_ERROR'),
    ],
)
def test_edit_does_not_send_edit_post_when_it_would_change_what_it_should_not(post, code):
    """editPost 는 보낸 값으로 글을 덮는다. 남의 글이거나 바꾸지 않을 칸의 현재 값을 모르면 editPost 를 보내지 않는다."""
    sent: list[str] = []
    current = {
        'id': 'p1', 'title': '제목', 'body': '본문', 'tags': ['a'], 'is_markdown': True,
        'url_slug': 'orig', 'meta': {'short_description': '요약'}, 'thumbnail': None, 'series': None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)['query']
        if 'auth {' in query:
            return httpx.Response(200, json=AUTH_OK)
        if 'ReadPostForEdit' in query:
            return httpx.Response(200, json={'data': {'post': {**current, **post}}})
        sent.append(query)
        return httpx.Response(200, json={'data': {'editPost': None}})

    with pytest.raises(VeloggerError) as caught:
        edit_post(_mock_client(handler), 'p1', title='새 제목')
    assert caught.value.code == code
    assert sent == [], 'editPost 를 보내면 안 된다'


def test_null_write_result_is_an_error_not_success():
    """v2 는 반영되지 않은 쓰기를 HTTP 200 + errors 없는 null 로 준다. 이를 성공으로 내지 않는다.

    2026-10-20 실측: 없는 글이나 만료된 토큰으로 보낸 likePost·editPost 가 `{"likePost": null}` 만 돌려줬고, 이전에는
    CLI 가 exit 0 에 모든 필드 null 로 '성공' 을 냈다. 에이전트가 반영되지 않은 쓰기를 됐다고 전하게 된다.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)['query']
        if 'auth {' in query:
            return httpx.Response(200, json=AUTH_OK)
        field = 'writePost' if 'writePost' in query else 'likePost'
        return httpx.Response(200, json={'data': {field: None}})

    with pytest.raises(VeloggerError) as caught:
        like_post(_mock_client(handler), 'p1')
    assert caught.value.code == 'UPSTREAM_ERROR'

    with pytest.raises(VeloggerError) as caught:
        publish(_mock_client(handler), title='제목', body='본문', tags=[])
    assert caught.value.code == 'UPSTREAM_ERROR'


# --- 이미지 업로드 ---

def test_upload_sends_ref_id_and_reads_path(tmp_path):
    """업로드는 이미지가 들어갈 글 ID(`ref_id`)를 꼭 보내고, 응답의 `path` 를 URL 로 쓴다.

    velog 는 ref_id 가 없으면 앞단에서 평문 403 `Forbidden` 으로 막는다 (2026-10-20 실측). 응답은
    `{"path": "<url>"}` 이다 (같은 날 실측).
    """
    image = tmp_path / 'a.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\n')
    sent: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent['body'] = request.content
        return httpx.Response(200, json={'path': 'https://velog.velcdn.com/images/me/post/x/image.png'})

    result = upload_image(_mock_client(handler), image, post_id='post-123')

    assert b'name="ref_id"' in sent['body'], 'ref_id 가 빠지면 velog 가 403 으로 막는다'
    assert b'post-123' in sent['body']
    assert result.url == 'https://velog.velcdn.com/images/me/post/x/image.png'
    assert result.markdown == '![a](https://velog.velcdn.com/images/me/post/x/image.png)'


@pytest.mark.parametrize(
    ('name', 'text'),
    [
        ('id_rsa.png', '-----BEGIN OPENSSH PRIVATE KEY-----\n'),
        # SVG 는 글자 파일이라 맨 앞이 <svg 요소인지로 본다. 확장자만 .svg 인 파일은 막는다
        ('env.svg', 'API_KEY=secret\n'),
        ('session.svg', '{"cookies": [{"name": "access_token", "value": "x"}]}'),
    ],
)
def test_upload_refuses_a_file_that_is_not_an_image_without_network(tmp_path, name, text):
    """velog 는 받은 파일의 형식을 보지 않고 공개 CDN 주소로 올린다 (velog-server `files/upload` 라우트).

    이미지가 아닌 파일(키·.env·session.json)이 그대로 누구나 받을 수 있는 URL 이 되지 않게, 확장자가 아니라 내용으로
    보고 네트워크 전에 막는다.
    """
    secret = tmp_path / name
    secret.write_text(text, encoding='utf-8')
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'path': 'https://velog.velcdn.com/x'})

    with pytest.raises(VeloggerError) as caught:
        upload_image(_mock_client(handler), secret, post_id='post-123')
    assert caught.value.code == 'INVALID_ARGUMENT'
    assert requests == []


@pytest.mark.parametrize(
    'text',
    [
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        '\ufeff<?xml version="1.0" encoding="UTF-8"?>\n<!-- Generator: Figma -->\n<!DOCTYPE svg>\n<svg width="1"></svg>',
    ],
)
def test_upload_accepts_svg_by_its_leading_svg_element(tmp_path, text):
    """SVG 는 정해진 첫 바이트가 없어, BOM·XML 선언·주석·DOCTYPE 뒤의 <svg 요소로 이미지임을 본다."""
    image = tmp_path / 'logo.svg'
    image.write_text(text, encoding='utf-8')

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'path': 'https://velog.velcdn.com/images/me/post/x/image.svg'})

    assert upload_image(_mock_client(handler), image, post_id='post-123').url.endswith('image.svg')


# --- slug ---

def test_slugify_keeps_hangul_and_replaces_spaces():
    assert slugify('CLI 테스트 글') == 'CLI-테스트-글'
    assert slugify('  공백   여러 개  ') == '공백-여러-개'
    assert slugify('!!!') == 'post'
    assert slugify('..') == 'post', '점만 남은 slug 는 글 주소가 상위 경로(@user/..)가 된다'


def test_series_add_reads_the_series_index_velog_returns():
    """appendToSeries 는 넣은 글의 시리즈 안 순번(Int)을 준다.

    bool 로 받던 때는 첫 글(1)만 통과하고 두 번째 글(2)부터 PARSE_ERROR 였다. 글은 들어가 있어, 에이전트가 실패로 알고
    같은 글을 다시 넣으려 했다 (2026-10-22 실측, velog-server `appendToSeries: Int`).
    """
    client = _mock_client(lambda request: httpx.Response(200, json={'data': {'appendToSeries': 2}}))

    result = add_to_series(client, 's1', 'p2')

    assert result.added is True
    assert result.index == 2
