# QuickModel MCP 使用指南

## 1. MCP 是什么

MCP（Model Context Protocol）是一套让 AI 客户端调用外部工具的通用协议。

在 QuickModel 中，工作流程如下：

```text
用户提问
  -> QuickModel Agent 判断是否需要工具
  -> 调用 MCP Server 提供的 Tool
  -> MCP Server 返回结果
  -> Agent 根据结果继续推理并回答
```

可以把 MCP Server 理解为一个“工具插件进程”。它可以提供天气查询、文件管理、数据库查询、浏览器自动化、GitHub 操作等能力。

QuickModel v1.9.2 当前支持：

- MCP Tools
- 本地 `stdio` 传输
- 远程 `Streamable HTTP` 传输
- 工具发现、调用、状态查询和手动重连
- 可信服务器自动执行
- 未信任服务器逐次确认
- 工具白名单
- `${ENV_VAR}` 环境变量占位符

当前暂不支持：

- MCP Resources
- MCP Prompts
- Sampling、Elicitation
- OAuth 登录
- 旧版 SSE 传输
- Claude Desktop JSON 一键导入

## 2. stdio 与 Streamable HTTP 的区别

### stdio

QuickModel 在本机启动一个 MCP Server 子进程，通过标准输入输出与它通信。

适合：

- 本地文件工具
- 本地数据库工具
- `npx`、`uvx` 或 Python 启动的 MCP Server
- 不希望把服务暴露到网络的场景

典型配置：

```text
Command: npx
Arguments:
  -y
  @modelcontextprotocol/server-filesystem
  E:/workspace
```

### Streamable HTTP

QuickModel 连接一个已经运行的远程 MCP HTTP Endpoint。

适合：

- 团队共享的 MCP 服务
- 部署在服务器或容器中的 MCP Server
- 需要 Header 鉴权的服务

典型配置：

```text
URL: https://example.com/mcp
Headers:
  Authorization = Bearer ${MCP_API_TOKEN}
```

注意：QuickModel 不支持旧 MCP SSE 地址。服务器必须提供 Streamable HTTP Endpoint。

## 3. 五分钟快速体验：文件系统 MCP

这个例子需要先安装 Node.js，并保证 `npx` 可以在终端中运行。

1. 打开“设置 -> MCP”。
2. 点击“添加服务器”。
3. 填写以下内容：

```text
名称：filesystem
传输方式：stdio
Command：npx
Arguments：
-y
@modelcontextprotocol/server-filesystem
E:/workspace
```

`Arguments` 输入框要求每行一个参数。最后一行请替换成允许 MCP 访问的目录。

4. 暂时不要开启“信任并自动执行”。
5. 点击“测试连接”。
6. 测试成功后检查发现到的工具列表。
7. 点击“保存服务器”。
8. 点击设置窗口底部的“保存”，使配置正式生效。

然后新建或继续一个对话，发送：

```text
请使用 filesystem MCP 列出 E:/workspace 下的文件，但不要修改任何内容。
```

模型会看到类似下面的动态工具名称：

```text
mcp__filesystem__list_directory
```

工具实际名称由 MCP Server 决定。QuickModel 会统一添加 `mcp__服务器名__` 前缀，并在名称过长或冲突时追加稳定哈希。

> 文件系统 MCP 通常具有读写文件能力。只授权确实需要访问的目录，不要直接开放整个系统盘。

## 4. 天气 MCP 示例

下面创建一个不需要 API Key 的本地天气 MCP Server。它通过 Open-Meteo 查询指定城市的当前天气。

### 4.1 准备 Python 环境

MCP Server 使用外部 Python 运行。安装依赖：

```powershell
python -m pip install "mcp>=1.28.1,<2" requests
```

如果使用本项目的 Conda 环境，可以执行：

```powershell
D:\miniconda\envs\ai_api\python.exe -m pip install "mcp>=1.28.1,<2" requests
```

### 4.2 创建天气 Server

创建 `weather_mcp.py`：

```python
from mcp.server.fastmcp import FastMCP
import requests


mcp = FastMCP("weather")

WEATHER_CODES = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷暴",
}


@mcp.tool()
def get_weather(city: str) -> dict:
    """查询指定城市或区县的当前天气。"""
    geo_response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": city,
            "count": 1,
            "language": "zh",
            "format": "json",
        },
        timeout=15,
    )
    geo_response.raise_for_status()
    locations = geo_response.json().get("results", [])

    if not locations:
        return {"error": f"没有找到地点：{city}"}

    location = locations[0]
    weather_response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": ",".join([
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "weather_code",
                "wind_speed_10m",
            ]),
            "timezone": "auto",
        },
        timeout=15,
    )
    weather_response.raise_for_status()

    current = weather_response.json()["current"]
    weather_code = current.get("weather_code")

    return {
        "location": location["name"],
        "province": location.get("admin1", ""),
        "country": location.get("country", ""),
        "weather": WEATHER_CODES.get(weather_code, f"天气代码 {weather_code}"),
        "temperature_c": current.get("temperature_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "observation_time": current.get("time"),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 4.3 在 QuickModel 中配置

```text
名称：weather
传输方式：stdio
Command：D:\miniconda\envs\ai_api\python.exe
Arguments：
E:/你的目录/weather_mcp.py
连接超时：15
调用超时：60
```

点击“测试连接”后，应当看到：

```text
get_weather
```

保存服务器和整个设置窗口，然后发送：

```text
请调用天气 MCP 查询杭州市西湖区当前天气，告诉我体感温度、湿度和风速。
```

也可以明确指定工具：

```text
请调用 mcp__weather__get_weather 查询北京市海淀区当前天气。
```

QuickModel 当前不会自动读取电脑的精确地理位置。“查询我所在位置的天气”最好同时提供城市或区县。这样也可以避免使用基于公网 IP 的第三方定位服务。

## 5. 配置字段说明

| 字段 | 说明 |
| --- | --- |
| 名称 | Server 的显示名称，同时参与生成模型工具名；不可重复 |
| 启用 | 关闭后，Server 不会出现在下一条消息的模型工具列表中 |
| 传输方式 | `stdio` 或 `Streamable HTTP` |
| 信任并自动执行 | 开启后，该 Server 的工具调用不再弹确认框 |
| 连接超时 | 初始化和发现工具的最大等待时间，默认 15 秒 |
| 调用超时 | 单次工具调用的最大等待时间，默认 60 秒 |
| Command | stdio Server 的启动程序，例如 `npx`、`uvx`、`python.exe` |
| Arguments | stdio 启动参数，每行一个 |
| Working Directory | 子进程工作目录，可留空 |
| Environment | 传递给 stdio 子进程的环境变量 |
| Endpoint URL | Streamable HTTP 的 MCP 地址 |
| Headers | HTTP 请求 Header，常用于鉴权 |

## 6. 工具权限与安全

### 未信任服务器

默认情况下 Server 不受信任。每次调用时，QuickModel 会显示：

- Server 名称
- 原始工具名称
- 模型生成的调用参数

你可以批准或拒绝执行。

### 可信服务器

开启“信任并自动执行”后，Server 的全部已启用工具可以自动执行，不再逐次确认。

建议只信任：

- 你自己编写和检查过的本地 Server
- 来源可信、权限范围明确的 Server
- 只读且风险较低的工具

对于文件写入、Shell、数据库修改、发邮件、云资源管理等工具，建议保留确认。

> MCP Server 自己声明的只读/破坏性注解仅用于界面说明。QuickModel 不会把 Server 自己的声明当作安全依据。

### 工具白名单

测试连接后，可以逐项取消工具。

- 所有工具都勾选：`all` 模式，Server 将来新增的工具会自动可用。
- 取消任意工具：切换到 `allowlist` 模式，只有勾选的工具可用。
- `allowlist` 模式下，Server 将来新增的工具默认不会获得权限。

对于会持续升级的第三方 Server，建议使用白名单模式。

## 7. 密钥与环境变量

Environment 和 HTTP Headers 支持 `${ENV_VAR}`：

```text
Authorization = Bearer ${MCP_API_TOKEN}
```

QuickModel 会在建立连接前解析变量，并对解析后的值进行脱敏。解析后的密钥不会进入：

- 模型工具 schema
- 模型对话历史
- 确认框中的 Server 配置
- MCP 工具结果
- MCP 错误详情

如果变量不存在，连接会失败并提示缺少的变量名称。

注意：操作系统环境变量通常在应用启动时继承。如果 QuickModel 已经运行，再从系统设置中新增或修改环境变量，运行中的 QuickModel 进程一般看不到新值。这种情况下需要重启 QuickModel。仅修改 MCP 界面中的普通配置不需要重启。

## 8. MCP 是否支持热更新

支持。正常添加、修改、启停或删除 MCP Server 后，不需要重启 QuickModel。

实际生效流程：

1. 在 MCP 编辑器中点击“保存服务器”。
2. 点击设置窗口底部的“保存”。
3. QuickModel 立即校验新配置。
4. 被删除、禁用或连接参数发生变化的旧会话会被关闭。
5. 下一条用户消息创建 Agent 时，会重新读取当前 MCP 工具列表。

热更新边界：

- 正在生成中的当前消息会缓存本轮工具列表，不会在执行中途变化。
- 修改配置后，应等待当前回复结束，或者停止当前回复，再发送下一条消息。
- 只点击“保存服务器”还只是设置窗口中的草稿；必须点击整个设置窗口底部的“保存”。
- 修改外部操作系统环境变量后，通常仍需重启软件，让进程继承新变量。
- MCP Server 自身代码变化后，可以点击“重连”；修改了 stdio 启动参数并保存时，QuickModel 也会关闭旧进程并按需启动新进程。

因此，最常见的使用流程是：

```text
修改 MCP 配置 -> 保存设置 -> 发送下一条消息
```

不需要重启软件。

## 9. 连接状态

| 状态 | 含义 |
| --- | --- |
| 未连接 | 尚未按需连接，或连接已经关闭 |
| 连接中 | 正在初始化并读取工具列表 |
| 已连接 | 会话可用，工具已经发现 |
| 错误 | 初始化、连接或调用失败；悬停可查看错误摘要 |
| 待保存 | 设置窗口中的配置已修改，但还没有保存到后端 |

QuickModel 采用按需连接。刚启动软件时显示“未连接”并不一定是错误；测试连接、手动重连或下一次 Agent 获取工具列表时才会建立连接。

## 10. 常见问题

### 测试连接提示 command not found

- 确认命令在普通终端中可以执行。
- Windows 可以填写完整路径，例如 `C:/Program Files/nodejs/npx.cmd`。
- Python Server 可以填写完整的 `python.exe` 路径。
- 检查 Working Directory 是否有效。

### 添加后模型看不到工具

依次确认：

1. Server 已启用。
2. 测试连接可以发现工具。
3. 目标工具已勾选。
4. 已点击“保存服务器”。
5. 已点击设置窗口底部的“保存”。
6. 已发送一条新的用户消息。

### HTTP Server 连接失败

- URL 必须以 `http://` 或 `https://` 开头。
- 确认地址是 Streamable HTTP MCP Endpoint，而不是网页地址或旧 SSE 地址。
- 检查 Header 名称和 `${ENV_VAR}`。
- 检查代理、防火墙和证书。

### 一个 Server 失败会不会影响其他 Server

不会。单个 MCP Server 失败只会把该 Server 标记为错误，其他 MCP Server 和 QuickModel 内置工具仍然可用。

### 调用失败后会不会自动重试

连接在调用前已经不可用时，QuickModel 会尝试重新建立连接。

如果工具调用已经发送，但返回途中连接断开，QuickModel不会自动重复执行该调用。因为远端操作可能已经成功，自动重试可能造成重复写入、重复发送或重复扣费。

### MCP 输出很长怎么办

单次 MCP 结果最多保留 60,000 个字符。超过限制时会截断，并标记原始长度。

## 11. 使用建议

- 第一次接入 Server 时保持“不信任”，先观察它会调用哪些工具。
- 对第三方 Server 使用工具白名单。
- stdio 文件工具只授权必要目录。
- 密钥优先使用 `${ENV_VAR}`，不要写进提示词或聊天消息。
- 写操作和外部副作用操作保留确认。
- 工具描述不清晰时，在提问中明确指定 Server、工具和目标。
- 遇到异常先使用“测试连接”，再查看状态错误摘要。

