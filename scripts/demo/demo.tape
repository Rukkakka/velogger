# README 데모 GIF 녹화 대본 (VHS). 녹화:
#   brew install charmbracelet/tap/vhs
#   vhs scripts/demo/demo.tape      → docs/demo/demo.gif
#
# 로그인·쓰기는 녹화하지 않는다 (실제 글이 올라가고, 화면에 계정 정보가 남는다).
# 조회만 보여 준다. 녹화 전 `velogger logout` 으로 세션이 없는 상태인지 확인한다.

Output docs/demo/demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 700
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms

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

Type "velogger post teo ai-native-fe | jq '{title, tags, likes, body: (.body[0:120] + \"...\")}'"
Enter
Sleep 6s

Sleep 2s
