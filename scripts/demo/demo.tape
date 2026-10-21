# README 데모 GIF 녹화 대본 (VHS). 저장소 루트에서, velogger·jq 가 PATH 에 있는 셸로 녹화한다:
#   brew install charmbracelet/tap/vhs
#   vhs scripts/demo/demo.tape      → docs/demo/demo.gif
#
# 로그인·쓰기는 녹화하지 않는다 (실제 글이 올라가고, 화면에 계정 정보가 남는다). 조회만 보여 준다.
# 녹화하는 사람의 로그인 세션을 쓰지 않도록, 화면에 안 보이는 구간에서 빈 임시 폴더를 세션 폴더로 둔다
# (`velogger logout` 은 실제 세션을 지우므로 하지 않는다).

Output docs/demo/demo.gif

Require velogger
Require jq

Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 700
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms

Hide
Type 'export VELOGGER_CONFIG_DIR="$(mktemp -d)" && clear'
Enter
Sleep 500ms
Show

Type "velogger guide | head -12"
Enter
Sleep 4s

Type "clear"
Enter
Sleep 500ms

Type "velogger trending --limit 3 | jq '.posts[] | {title, username, likes}'"
Enter
Sleep 5s

Type "clear"
Enter
Sleep 500ms

Type `velogger post teo ai-native-fe | jq '{title, tags, likes, body: (.body[0:120] + "...")}'`
Enter
Sleep 6s

Sleep 2s
