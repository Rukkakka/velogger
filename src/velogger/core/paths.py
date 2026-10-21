"""velogger 가 파일을 두는 사용자 폴더 (로그인 세션은 config, 요청 제한 상태는 cache)."""

import os
from pathlib import Path


APP_DIR_NAME: str = 'velogger'


def user_dir(override_env: str, xdg_env: str, home_fallback: str) -> Path:
    """`$<override_env>` > `$<xdg_env>/velogger` > `~/<home_fallback>/velogger`.

    XDG 변수가 상대 경로면 없는 것으로 본다 (XDG Base Directory 명세). 그대로 쓰면 실행한 폴더마다 다른 곳을 가리켜,
    폴더를 옮길 때마다 로그인이 풀리고 요청 제한 상태가 프로세스끼리 공유되지 않는다.
    """
    override = os.environ.get(override_env)
    if override:
        return Path(override)
    xdg_home = os.environ.get(xdg_env)
    base = Path(xdg_home) if xdg_home and os.path.isabs(xdg_home) else Path.home() / home_fallback
    return base / APP_DIR_NAME
