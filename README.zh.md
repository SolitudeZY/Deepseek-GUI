# QuickModel

Windows 妗岄潰 AI 鍔╂墜锛屾敮鎸侀€氳繃 OpenAI 鍏煎 API 鎺ュ叆澶氬 LLM 鏈嶅姟鍟嗐€傚熀浜?pywebview (WebView2) + Python 鍚庣鏋勫缓銆?

![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

[English](./README.md) | 涓枃

## 鍔熻兘鐗规€?

### 鏍稿績 Agent
- **澶氭湇鍔″晢鏀寔** 鈥?鍏煎浠讳綍 OpenAI 鏍煎紡 API锛欴eepSeek锛圴3/R1/V4 Pro/V4 Flash锛夈€丱penAI銆丵wen銆丱llama 绛?
- **澶氭ā鍨嬮厤缃?* 鈥?鍦ㄨ缃腑閰嶇疆骞跺垏鎹㈠涓ā鍨嬪悗绔?
- **鎺ㄧ悊寮哄害涓夋。锛堝叧 / 楂?/ 娣憋級** 鈥?宸ュ叿鏍忓惊鐜垏鎹㈡€濊€冩繁搴︼紝璺ㄤ細璇濇寔涔呭寲
- **鑷姩鍘嬬缉** 鈥?瓒呰繃 80k token锛圴4 妯″瀷 800k锛夎嚜鍔ㄦ€荤粨鍘嬬缉涓婁笅鏂囷紱鏀寔 `/compact` 鎵嬪姩鍘嬬缉锛涘墠缂€缂撳瓨鎰熺煡鍘嬬缉绛栫暐鏈€澶у寲 DeepSeek 缂撳瓨鍛戒腑
- **鍥剧墖鐞嗚В** 鈥?绮樿创鎴栨嫋鎷藉浘鐗囧埌鑱婂ぉ涓紝閫氳繃 Qwen-VL 鎴栦换鎰忚瑙?API 鎻忚堪骞舵敞鍏ヤ笂涓嬫枃
- **瀹炴椂鎴愭湰璺熻釜** 鈥?鎸夎疆娆″拰浼氳瘽缁熻 token 鐢ㄩ噺锛屽惈缂撳瓨鍛戒腑/鏈懡涓槑缁嗭紝渚ц竟鏍忓疄鏃舵樉绀?

### 鍐呯疆宸ュ叿
| 宸ュ叿 | 鎻忚堪 |
|------|------|
| `read_file` | 璇诲彇鏈湴鏂囦欢锛坱xt銆乵d銆乸y銆乯son銆乧sv銆乸df銆乨ocx銆亁lsx 绛夛級 |
| `write_file` | 鍐欏叆鎴栬鐩栫鐩樻枃浠?|
| `apply_patch` | 鐢?unified diff 鏍煎紡绮惧噯淇敼鏂囦欢鎸囧畾琛岋紙姣?`write_file` 鏇村畨鍏級 |
| `list_directory` | 鍒楀嚭鐩綍鍐呭 |
| `run_command` | 鎵ц PowerShell 鍛戒护锛堝甫纭寮圭獥锛?|
| `web_search` | 閫氳繃澶氬紩鎿庢悳绱簰鑱旂綉锛屾敮鎸佽嚜鍔ㄩ檷绾?|
| `web_read` | 鑾峰彇骞堕槄璇诲畬鏁寸綉椤靛唴瀹癸紙HTML 鈫?绾枃鏈級 |
| `rlm_query` | 骞惰娲惧彂 1鈥?6 涓瓙浠诲姟鍒颁綆鎴愭湰妯″瀷锛坉eepseek-v4-flash锛?|
| `compact` | 鎵嬪姩瑙﹀彂涓婁笅鏂囧帇缂?|
| `todo_write` | 缁存姢缁撴瀯鍖栧緟鍔炴竻鍗曪紝杩借釜澶氭楠ゅ伐浣?|
| `subagent` | 鐢熸垚涓撴敞鐨勫瓙浠ｇ悊锛屾嫢鏈夌嫭绔嬪伐鍏峰惊鐜?|

### 澶氬紩鎿庣綉缁滄悳绱?
- **6 涓悳绱㈠悗绔?* 鈥?Tavily銆丅rave Search銆丗irecrawl銆丟oogle Custom Search銆丼earXNG銆丏uckDuckGo
- **鑷姩闄嶇骇** 鈥?棣栭€夊紩鎿庡け璐ユ椂鑷姩灏濊瘯涓嬩竴涓彲鐢ㄥ紩鎿庯紱DuckDuckGo锛堝厤璐规棤闇€ key锛変綔涓烘渶缁堝厹搴?
- **鑷姩璇诲彇** 鈥?鎼滅储瀹屾垚鍚庤嚜鍔ㄦ姄鍙栧墠鍑犱釜缁撴灉鐨勫畬鏁寸綉椤靛唴瀹癸紝鍑忓皯鍚庣画鎼滅储娆℃暟
- **杞檺鍒?* 鈥?鍗曡疆鎼滅储杈?5 娆″悗锛岃嚜鍔ㄦ彁绀?Agent 鏁寸悊宸叉湁缁撴灉
- **鑷姩/鎵嬪姩妯″紡** 鈥?鑷姩妯″紡涓嬫ā鍨嬭嚜琛屽喅瀹氭悳绱紱鎵嬪姩妯″紡涓嬬敱宸ュ叿鏍忔寜閽帶鍒?

### 鎶€鑳界郴缁燂紙Skills锛?
- **鍐呯疆涓庤嚜瀹氫箟鎶€鑳?* 鈥?淇濆瓨骞跺鐢ㄦ彁绀鸿瘝妯℃澘锛屾敼鍙?Agent 琛屼负
- **瀵煎叆 Claude 椋庢牸鎶€鑳?* 鈥?浠庢枃浠跺す瀵煎叆锛堣嚜鍔ㄦ娴?`SKILL.md` + 闄勫睘鏂囦欢锛屾敮鎸佹壒閲忓鍏ワ級
- **瀹屾暣绠＄悊闈㈡澘** 鈥?鍒涘缓銆佺紪杈戙€佸垹闄ゆ妧鑳?

### 璁板繂绯荤粺锛圡emory锛?
- **鎸佷箙鍖栭敭鍊煎瓨鍌?* 鈥?Agent 鍙法瀵硅瘽淇濆瓨鍜屽洖蹇嗕簨瀹烇紙`memory_read`銆乣memory_write`锛?
- **鑷姩娉ㄥ叆** 鈥?`/new` 鏂板缓瀵硅瘽鏃惰嚜鍔ㄦ敞鍏ヨ蹇嗘憳瑕?

### 宸ヤ綔鏍戦殧绂伙紙Worktree锛?
- **Git Worktree 闆嗘垚** 鈥?姣忎釜瀵硅瘽鍙湪鐙珛 worktree 涓搷浣?
- **鍛戒护瀹夊叏** 鈥?鎵ц鍓嶇‘璁ゅ脊绐楋紝鏀寔鏅鸿兘閫氶厤绗︽ā寮忓缓璁紙`git *`銆乣python *`锛?
- **宸ヤ綔鏍戦潰鏉?* 鈥?渚ч潰鏉挎樉绀烘椿璺冨伐浣滄爲銆佸垎鏀強缁戝畾浠诲姟

### 鍥㈤槦鍗忎綔锛圱eam锛?
- **澶?Agent 鍥㈤槦** 鈥?鐢熸垚鍦ㄧ嫭绔嬬嚎绋嬩腑杩愯鐨勬寔涔呭寲鍥㈤槦鎴愬憳
- **娑堟伅鎬荤嚎** 鈥?鍐呭瓨鏀朵欢绠?鍙戜欢绠卞疄鐜?Agent 闂撮€氫俊
- **UI 閫氱煡** 鈥?鍥㈤槦鎴愬憳瀹屾垚宸ヤ綔鏃跺疄鏃跺洖璋?

### 浠诲姟绠＄悊锛圱ask锛?
- **鎸佷箙鍖栦换鍔?* 鈥?璺ㄥ璇濆瓨娲荤殑缁撴瀯鍖栦换鍔?
- **渚濊禆鍥?* 鈥?浠诲姟闂村彲浜掔浉闃诲锛坧ending 鈫?in_progress 鈫?completed锛?
- **宸ヤ綔鏍戠粦瀹?* 鈥?绉婚櫎 worktree 鏃惰嚜鍔ㄥ畬鎴愮粦瀹氫换鍔?

### RLM 骞惰澶勭悊
- **鎵归噺瀛愪换鍔?* 鈥?涓€娆℃淳鍙戞渶澶?16 涓嫭绔嬫彁绀鸿瘝鍒?deepseek-v4-flash 骞惰鎵ц
- **搴旂敤鍦烘櫙** 鈥?鎵归噺缈昏瘧銆佷唬鐮佸鏌ャ€佸鏂囦欢鍒嗘瀽銆佹暟鎹彁鍙?
- **鑷姩閫夋嫨妯″瀷** 鈥?浠庡凡閰嶇疆鐨勬ā鍨嬪垪琛ㄤ腑鑷姩閫夊彇 flash 妯″瀷

### 鐢ㄦ埛鐣岄潰
- **pywebview 妗岄潰搴旂敤** 鈥?鍘熺敓绐楀彛鎵胯浇缃戦〉鑱婂ぉ鐣岄潰
- **瀵硅瘽绠＄悊** 鈥?渚ц竟鏍忔敮鎸佹嫋鎷芥帓搴忋€佹悳绱€侀噸鍛藉悕銆佸垹闄ゃ€佸鍑轰负 Markdown
- **鍙姌鍙犲伐鍏锋皵娉?* 鈥?宸ュ叿璋冪敤鍜岀粨鏋滀互鍙姌鍙犳皵娉″睍绀?
- **鑱婂ぉ瀵艰埅** 鈥?涓?涓嬩竴鏉℃秷鎭寜閽紝骞虫粦婊氬姩鍔ㄧ敾
- **Markdown & LaTeX** 鈥?瀹屾暣娓叉煋鏀寔锛宮arked.js + KaTeX锛堟湰鍦扮绾匡紝鏃?CDN锛?
- **涓婚鏀寔** 鈥?娴呰壊/娣辫壊涓婚锛屽彲璋冭妭瀛楀彿
- **鎴愭湰涓庝笂涓嬫枃鏄剧ず** 鈥?渚ц竟鏍忓疄鏃舵樉绀?token 鐢ㄩ噺銆佺紦瀛樺懡涓巼銆佷笂涓嬫枃浣跨敤鎯呭喌

## 鎴浘

> 鍗冲皢鏇存柊

## 鐜瑕佹眰

- Windows 10/11锛岄渶瀹夎 [WebView2 Runtime](https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/)锛圵in11 閫氬父宸查瑁咃級
- Python 3.10+
- 鑷冲皯涓€瀹?LLM 鏈嶅姟鍟嗙殑 API Key

## 瀹夎

### 浠庢簮鐮佽繍琛?

```bash
git clone https://github.com/SolitudeZY/Deepseek-GUI.git
cd Deepseek-GUI

pip install openai pywebview tavily-python duckduckgo-search firecrawl-py

python main.py
```

### 涓嬭浇棰勭紪璇?.exe

浠?[Releases](https://github.com/SolitudeZY/Deepseek-GUI/releases) 涓嬭浇 `QuickModel.exe`锛屽弻鍑荤洿鎺ヨ繍琛岋紝鏃犻渶瀹夎銆?

## 鎵撳寘

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name QuickModel --icon=icon.ico --add-data "app/static;app/static" --add-data "icon.ico;." main.py
```

杈撳嚭鏂囦欢锛歚dist/QuickModel.exe`

## 閰嶇疆

棣栨鍚姩鍚庯紝鐐瑰嚮鍙充笂瑙?*璁剧疆**杩涜閰嶇疆銆傞厤缃枃浠跺瓨鍌ㄤ簬 `%APPDATA%\AIDesktopAssistant\config.json`銆?

```json
{
  "model_configs": [
    {"name": "DeepSeek V4 Pro", "api_key": "sk-...", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-pro"},
    {"name": "DeepSeek V4 Flash", "api_key": "sk-...", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-flash"}
  ],
  "thinking": "high",
  "search_engine": "brave",
  "search_fallback": true,
  "tavily_api_key": "tvly-...",
  "brave_api_key": "BSAy_...",
  "firecrawl_api_key": "fc-...",
  "google_api_key": "",
  "google_cx": "",
  "searxng_url": "",
  "search_mode": "auto",
  "search_enabled": true,
  "vision_api_key": "sk-...",
  "vision_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "vision_model": "qwen-vl-max"
}
```

| 閰嶇疆椤?| 璇存槑 |
|--------|------|
| `model_configs` | 澶氭ā鍨嬪悗绔紙鍙湪璁剧疆涓垏鎹級 |
| `thinking` | 鎺ㄧ悊寮哄害锛歚"off"`锛堝叧锛夈€乣"high"`锛堥珮锛夈€乣"max"`锛堟繁锛?|
| `search_engine` | 棣栭€夋悳绱㈠紩鎿庯細`tavily`銆乣brave`銆乣firecrawl`銆乣duckduckgo`銆乣google`銆乣searxng` |
| `search_fallback` | 澶辫触鏃惰嚜鍔ㄩ檷绾у埌涓嬩竴涓彲鐢ㄥ紩鎿?|
| `tavily_api_key` | [app.tavily.com](https://app.tavily.com) 鈥?鍏嶈垂 1000 娆?鏈?|
| `brave_api_key` | [brave.com/search/api](https://brave.com/search/api/) 鈥?鍏嶈垂 2000 娆?鏈?|
| `firecrawl_api_key` | [firecrawl.dev](https://www.firecrawl.dev) 鈥?鍏嶈垂 500 娆?鏈堬紝杩斿洖瀹屾暣 Markdown |
| `google_api_key` / `google_cx` | Google Custom Search 鈥?鍏嶈垂 100 娆?澶╋紙2026骞磋捣浠呴檺 50 涓煙鍚嶏級 |
| `searxng_url` | 鑷缓 SearXNG 瀹炰緥鍦板潃 |
| `search_mode` | `"auto"` = 妯″瀷鑷鍐冲畾锛沗"manual"` = 鐢ㄦ埛宸ュ叿鏍忔墜鍔ㄥ紑鍏?|
| `vision_api_key` / `vision_base_url` / `vision_model` | 鍥剧墖鎻忚堪鐨勮瑙夋ā鍨?|

## 鏀寔鐨勬湇鍔″晢

| 鏈嶅姟鍟?| Base URL |
|--------|----------|
| DeepSeek | `https://api.deepseek.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Ollama锛堟湰鍦帮級 | `http://localhost:11434/v1` |
| DashScope锛堥€氫箟鍗冮棶锛?| `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 鍏朵粬 OpenAI 鍏煎 API | 鑷畾涔夊湴鍧€ |

## 浣跨敤鎶€宸?

- **鎶€鑳?*锛氬紑濮嬩换鍔″墠鍏堟墦寮€鎶€鑳介潰鏉垮垱寤烘垨瀵煎叆涓撲笟鍖栭厤缃?
- **宸ヤ綔鏍?*锛氬綋 Agent 闇€瑕佷慨鏀逛唬鐮佹椂锛屽厛璁╁畠鍒涘缓 worktree 浠ラ殧绂荤幆澧?
- **璁板繂**锛氬 Agent 璇淬€岃浣忚繖涓€︺€嶏紝瀹冧細淇濆瓨鍒版寔涔呭寲璁板繂涓?
- **鎺ㄧ悊寮哄害**锛氱敤 馃挱 鎸夐挳鍦?鍏?鈫?楂?鈫?娣?闂村惊鐜垏鎹紱绠€鍗曚换鍔＄敤銆屽叧銆嶅姞閫熷搷搴旓紝澶嶆潅鎺ㄧ悊鐢ㄣ€屾繁銆?
- **鎼滅储**锛氱爺绌剁被浠诲姟鐢ㄨ嚜鍔ㄦā寮忥紱闇€瑕佹帶鍒舵悳绱㈢敤閲忔椂鍒囨崲鍒版墜鍔ㄦā寮?
- **RLM 骞惰**锛氳 Agent 鎵归噺澶勭悊浠诲姟锛堝銆岀炕璇戣繖 10 娈垫枃瀛椼€嶏級锛屽畠浼氳嚜鍔ㄤ娇鐢ㄥ苟琛屽瓙浠诲姟
- **apply_patch**锛氱簿纭唬鐮佷慨鏀规椂锛孉gent 浼氫娇鐢?unified diff 鑰岄潪瑕嗙洊鏁翠釜鏂囦欢
- **鍘嬬缉**锛氬璇濊繃闀挎椂浣跨敤 `/compact` 鎴栫瓑寰呰嚜鍔ㄥ帇缂?
- **鎴愭湰**锛氫晶杈规爮瀹炴椂鏌ョ湅 token 鐢ㄩ噺鍜岀紦瀛樺懡涓巼锛屼紭鍖?API 璐圭敤

## 椤圭洰缁撴瀯

```
quick_model/
鈹溾攢鈹€ main.py              # 鍏ュ彛鏂囦欢
鈹溾攢鈹€ app/
鈹?  鈹溾攢鈹€ agent.py         # 鏍稿績 Agent 寰幆銆佸伐鍏峰垎鍙戙€佸帇缂╅€昏緫
鈹?  鈹溾攢鈹€ tools.py         # 鍐呯疆宸ュ叿瀹炵幇锛堟枃浠躲€佹悳绱€丼hell锛?
鈹?  鈹溾攢鈹€ advanced_tools.py # 瀛愪唬鐞嗐€佷换鍔°€佸悗鍙颁换鍔°€佸緟鍔炵鐞?
鈹?  鈹溾攢鈹€ skills.py        # 鎶€鑳?CRUD銆佸鍏ャ€佽蹇嗘寔涔呭寲
鈹?  鈹溾攢鈹€ team.py          # 澶?Agent 鍥㈤槦銆佹秷鎭€荤嚎銆亀orktree 绱㈠紩
鈹?  鈹溾攢鈹€ webview_app.py   # pywebview API 妗ユ帴锛圥ython 鈫?JavaScript锛?
鈹?  鈹溾攢鈹€ config.py        # 閰嶇疆鍔犺浇/淇濆瓨锛岄粯璁ゅ€?
鈹?  鈹溾攢鈹€ conversation.py  # 瀵硅瘽 CRUD銆佸鍑恒€佹帓搴?
鈹?  鈹溾攢鈹€ compact.py       # 涓婁笅鏂囧帇缂╁拰鎬荤粨
鈹?  鈹溾攢鈹€ vision.py        # 閫氳繃瑙嗚 API 杩涜鍥剧墖鎻忚堪
鈹?  鈹溾攢鈹€ command_safety.py # 鍛戒护鐧藉悕鍗曞拰妯″紡鍖归厤
鈹?  鈹溾攢鈹€ static/          # HTML/CSS/JS 鍓嶇
鈹?  鈹?  鈹溾攢鈹€ index.html   # 涓荤晫闈㈠竷灞€
鈹?  鈹?  鈹溾攢鈹€ app.js       # 鍓嶇閫昏緫涓庝簨浠跺鐞?
鈹?  鈹?  鈹斺攢鈹€ style.css    # 娣辫壊/娴呰壊涓婚鏍峰紡
鈹?  鈹斺攢鈹€ skills/          # 榛樿鎶€鑳藉畾涔夛紙.md 鏂囦欢锛?
鈹斺攢鈹€ conversations/       # 瀵硅瘽鍘嗗彶锛堣嚜鍔ㄥ垱寤猴級
```

## 鎶€鏈爤

- **鍓嶇**锛歱ywebview (WebView2)銆丠TML/CSS/JS
- **鍚庣**锛歅ython銆丱penAI SDK
- **娓叉煋**锛歮arked.js銆並aTeX銆乭ighlight.js锛堝叏閮ㄦ湰鍦扮绾匡級
- **鎵撳寘**锛歅yInstaller

## 璁稿彲璇?

MIT
