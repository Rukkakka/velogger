"""README 맨 위 로고(docs/logo-light.svg·docs/logo-dark.svg)를 만든다.

원고지 칸에 `velogger` 를 한 글자씩 쓰고 끝에 펜촉을 둔 로고다. 이 CLI 는 velog 가 만든 것이 아닌 비공식 도구라,
공식 velog 로고(청록 글자)와 헷갈리지 않게 청록을 피하고 '비공식 CLI' 를 적는다. 칸 수(이름 길이)에 맞춰 폭과
펜촉 위치를 계산한다.
글자색이 배경에 따라 달라야 해서 밝은 화면용과 어두운 화면용 두 파일을 만들고, README 가 `<picture>` 로 고른다
(PyPI 는 `<source>` 를 걸러 내서 밝은 판만 보인다).

글자는 외곽선(path)으로 바꿔 넣는다. SVG 안에 글자로 두면 보는 사람 컴퓨터에 그 글꼴이 없을 때 다른 글꼴로 바뀐다.
글꼴은 저장소에 두지 않는다. Google Fonts 의 IBM Plex Mono SemiBold 와 IBM Plex Sans KR SemiBold(둘 다 OFL)를 받아
경로를 넘긴다.

    uv run --no-project --with fonttools python scripts/logo/build_logo.py IBMPlexMono-SemiBold.ttf IBMPlexSansKR-SemiBold.ttf
"""

import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


DOCS: Path = Path(__file__).resolve().parents[2] / 'docs'
# 화면별 색: 글자, 원고지 칸·펜촉, 아래 설명
COLORS: dict[str, dict[str, str]] = {
    'light': {'ink': '#1E1B2E', 'accent': '#6A4BD6', 'muted': '#6B6880'},
    'dark': {'ink': '#ECEAF5', 'accent': '#A08CFF', 'muted': '#A9A5BD'},
}
NAME: str = 'velogger'
CAPTION: str = '벨로거 · velog 비공식 CLI'
# 원고지 칸: 왼쪽 x, 위 y, 한 칸 크기
CELL_X: int = 12
CELL_Y: int = 14
CELL: int = 52
# 마지막 칸 오른쪽에서 펜촉 중심까지, 펜촉 오른쪽 여백까지
NIB_OFFSET: int = 26
RIGHT_MARGIN: int = 58
# 펜촉 (24×24, 중심 12,12). 숨구멍·슬릿·띠는 evenodd 로 뚫린 구멍이라 배경이 비친다
NIB: str = 'M8 3H16L19 11L12 22L5 11ZM12 9.4A1.6 1.6 0 1 0 12 12.6A1.6 1.6 0 1 0 12 9.4ZM11.45 12.6H12.55V19.5H11.45ZM7.6 6H16.4V7H7.6Z'


def _number(value: float) -> str:
    """좌표를 소수 둘째 자리까지, 끝의 0 은 떼고 쓴다."""
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def _advance(font: TTFont, char: str, size: float) -> float:
    """글자 하나의 가로 폭(px)."""
    glyph_set = font.getGlyphSet()
    return glyph_set[font.getBestCmap()[ord(char)]].width * size / font['head'].unitsPerEm


def text_path(font: TTFont, text: str, x: float, baseline: float, size: float, spacing: float = 0) -> str:
    """글자열 하나를 SVG path 의 d 값으로 바꾼다.

    Args:
        font: 글꼴.
        text: 쓸 글자열.
        x: 첫 글자의 왼쪽 x.
        baseline: 기준선 y.
        size: 글자 크기(px).
        spacing: SVG letter-spacing 처럼 글자마다 뒤에 더하는 간격(px). Defaults to 0.

    Returns:
        모든 글자의 외곽선을 이은 d 값.
    """
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    scale = size / font['head'].unitsPerEm
    pen = SVGPathPen(glyph_set, ntos=_number)
    for char in text:
        glyph = glyph_set[cmap[ord(char)]]
        # 글꼴 좌표는 y 가 위로 커지고 SVG 는 아래로 커진다
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += glyph.width * scale + spacing
    return pen.getCommands()


def build(mono: TTFont, sans: TTFont, colors: dict[str, str]) -> str:
    """한 화면용 로고 SVG 를 만든다."""
    cells = []
    letters = []
    for index, char in enumerate(NAME):
        x = CELL_X + index * CELL
        cells.append(f'<rect x="{x}" y="{CELL_Y}" width="{CELL}" height="{CELL}"/>')
        # 칸 가운데에 오도록 글자 폭의 절반만큼 왼쪽에서 시작한다
        left = x + CELL / 2 - _advance(mono, char, 32) / 2
        letters.append(text_path(mono, char, x=left, baseline=CELL_Y + 38, size=32))
    caption = text_path(sans, CAPTION, x=13, baseline=90, size=14, spacing=1.5)
    cells_end = CELL_X + len(NAME) * CELL
    width = cells_end + RIGHT_MARGIN
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="100" viewBox="0 0 {width} 100" role="img" aria-label="velogger — velog 비공식 CLI">
  <title>velogger — velog 비공식 CLI</title>
  <g fill="none" stroke="{colors['accent']}" stroke-width="2">
    {''.join(cells)}
  </g>
  <path d="{''.join(letters)}" fill="{colors['ink']}"/>
  <path d="{NIB}" fill="{colors['accent']}" fill-rule="evenodd" transform="translate({cells_end + NIB_OFFSET} 40) rotate(35) scale(1.6) translate(-12 -12)"/>
  <path d="{caption}" fill="{colors['muted']}"/>
</svg>
"""


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('사용법: build_logo.py <IBMPlexMono-SemiBold.ttf> <IBMPlexSansKR-SemiBold.ttf>')
    mono, sans = (TTFont(path) for path in sys.argv[1:])
    for mode, colors in COLORS.items():
        output = DOCS / f'logo-{mode}.svg'
        svg = build(mono, sans, colors)
        output.write_text(svg, encoding='utf-8')
        print(f'{output} ({len(svg.encode())} bytes)')


if __name__ == '__main__':
    main()
