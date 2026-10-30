# AI Movie Advisor · 9万天

基于 React、FastAPI、SQLite 和 Dify 的本地电影推荐项目。

当前完成 **最小正式工程、模块 2 作品资料与身份匹配、模块 3 我的片库**。支持电影和剧集各季的真实搜索与详情、个人想看／看过、可选整数星评分、搜索筛选和持久化。保留资料缓存、来源映射、健康检查和 Dify SSE 客户端。豆瓣导入、画像与推荐按后续模块实现。

## 目录

- frontend：React＋TypeScript＋Vite。
- backend：FastAPI、SQLite、Alembic、TMDB／Dify 客户端、作品匹配与测试。
- ai-movie-advisor：保留的墨刀 HTML 原型。
- 开发执行计划.md、模块开发执行指引.md：仅保留在本地的产品规则与后续模块文档，不纳入 Git。

## 首次安装

以下命令在 Windows PowerShell 中执行，工作目录为 D:/movie-agent。

~~~powershell
python -m venv backend/.venv
cd backend
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
./.venv/Scripts/python.exe scripts/init_env.py
./.venv/Scripts/python.exe -m alembic upgrade head
cd ../frontend
npm ci
~~~

init_env.py 仅在配置文件不存在时创建 backend/.env，并生成 MOVIE_INTERNAL_TOKEN。真实 JSON、配置、数据库、虚拟环境与 node_modules 均被 Git 忽略。前端不保存 API Key。

后端固定版本依赖记录在 backend/requirements.lock。需要按已验证版本安装时，先安装该文件，再使用 pip install --no-deps -e . 安装本项目。

## 启动后端

在第一个 PowerShell 终端：

~~~powershell
cd D:/movie-agent/backend
./.venv/Scripts/python.exe -m app
~~~

- 健康状态：http://localhost:8000/health
- 交互式接口文档：http://localhost:8000/docs
- 数据库默认 backend/data/movie_advisor.db；相对 DATABASE_PATH 从 backend 解析。

仓库默认后端端口为 8000。本机实测 8000 被 Windows 保留，因此本机 backend/.env 已使用 BACKEND_PORT=18000，frontend/.env.local 已使用 VITE_BACKEND_URL=http://127.0.0.1:18000。这两个文件都不提交 Git。本机接口地址为 http://localhost:18000/docs；其他机器可以使用默认值，只需两边地址一致。

初始迁移 0001 建立 Alembic 版本基线；0002 建立 catalog_items 作品缓存与 source_mappings 来源映射；0003 建立 user_items 个人片库表。升级已有工程时也需执行 alembic upgrade head。应用不会用 create_all 自动建表；未迁移时 /health 返回 503。

## 启动前端

在第二个终端：

~~~powershell
cd D:/movie-agent/frontend
npm run dev
~~~

打开 http://localhost:5173。开发服务器把 /api 请求转发至 VITE_BACKEND_URL，默认本机 8000，当前机器为 18000；浏览器不需要额外 CORS 配置。

首页为按墨刀原型布局实现的“我的片库”：左侧片单、右侧观影画像区域。片库可切换想看／看过、搜索名称、筛选电影／剧集并分页。画像尚未生成时显示真实观影记录数量与空状态，不显示原型中的模拟偏好。

“手动添加”按名称和类型搜索 TMDB，不提供年份输入；候选仍显示年份。剧集搜索直接展开为各季独立词条，点击某一季即可加入想看或标记看过，不再提供整剧词条、季选择器或返回整剧按钮。正常季按季号排列，特别篇独立列在其后；季数来自 TMDB，不硬编码。正式界面不再单独展示“已确认作品”列表或要求额外确认资料。

“服务状态”页实际读取后端和数据库状态。Dify／TMDB 在该页只显示凭据是否填写，不代表外部调用成功。

## 作品资料与匹配

- 可标记作品用 movie:ID、season:剧集ID:季号确定身份；支持季号 0（特别篇）。tv:ID 仅作为父剧资料缓存和已有来源匹配的内部身份，不作为新个人片库条目。
- 详情存入 SQLite，缓存 7 天；查看详情不会自动确认。刷新资料会重新请求 TMDB，保留已有确认状态。
- 搜索候选仍请求 TMDB；将父剧展开为各季时复用已缓存的父剧资料，点击某一季再获取该季完整详情。详情缓存命中时无需再次请求远端。
- 中文简介缺失时尝试英文，均缺失时保留空值；缺海报或图片加载失败时显示占位。
- 导演、主创与演员保存 TMDB 人物 ID；主要演员按 TMDB 顺序保留前两位。主创与导演分别展示。
- 匹配优先复用来源映射，再核对名称、原名或已知别名、年份、类型与季号；结果分为 matched、ambiguous、missing_data、not_found。单季核对该季年份，不用整剧首播年份替代。
- TMDB 调用使用 20 秒超时，不自动重试；网络错误、找不到作品、限流分别返回明确状态。
- 本模块不搭建新的 Dify 工作流。测试接口或调用只读工具可能写入公共资料缓存，不修改个人观看状态。

后端接口（浏览器通过 /api 前缀代理）：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | /catalog/search | query、media_type=all/movie/tv、可选 year、page；tv 结果展开为每季，支持“剧名 第二季”等检索 |
| GET | /catalog/details | media_type=movie/tv/season、tmdb_id、单季 season_number；refresh=true 更新缓存 |
| POST | /catalog/confirm | 确认作品，可附带 source 来源映射；重复确认不新增 |
| GET | /catalog/items | 已确认作品，page 分页，每页 24 条 |
| POST | /catalog/match | title、可选 original_title/year/media_type/season_number/source |
| GET | /internal/movies/search | 受认证保护的电影搜索，operationId=search_movies |
| GET | /internal/movies/{tmdb_id} | 受认证保护的电影详情，operationId=get_movie_details |

详细模型、工具输入输出和 X-Internal-Token 认证定义见运行中的 /openapi.json。电影工具留待后续模块注册到 Dify。

## 我的片库

本地单用户使用，每部作品只有一条个人记录。列表使用本地作品缓存，不为每个条目重新请求 TMDB。看过记录默认按最近标记时间排序，每页 12 条；状态数量始终为全量计数，搜索结果数量单独计算。每季独立保存状态和评分，不将一季的标记传播到其他季，也不允许新增整剧个人记录。

| 当前状态 | 想看按钮 | 看过按钮 |
|---|---|---|
| 未加入 | 加入想看，可点击 | 标记看过，可点击 |
| 想看 | 已加入想看，置灰 | 标记看过，可点击，更新原记录 |
| 看过 | 加入想看，置灰 | 已看过，置灰 |

1～5 个整数星分别对应 2、4、6、8、10 分，不支持半星。评分以整数星保存，十分制由星级乘 2 得到。“跳过评分”保存为看过且 rating=null，展示“未评分”，仍计入看过数量。重复添加不新增，看过不降级，已有看过记录的评分不会被重复操作覆盖；本阶段不提供修改评分或删除看过记录。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | /library | status=wish/watched、media_type=all/movie/tv、query、page；剧集筛选包含各季及保留的旧整剧记录 |
| GET | /library/state | media_type、tmdb_id、可选 season_number；读取作品的个人状态、记录 ID 和评分 |
| POST | /library/manual | 作品身份、status、可选 rating；新增或将想看更新为看过 |
| POST | /library/{item_id}/watched | rating=1～5 或 null；将已有想看更新为看过，无需重新访问 TMDB |

标记日期与实际观影日期分开理解。添加来源及创建／更新时间保存在数据库，供后续导入复用。豆瓣导入和 AI 选片入口暂未开放；模块 3 无需新增 Dify 工作流。

## 填写服务端配置

编辑 backend/.env：

- DIFY_BASE_URL=http://127.0.0.1:18080/v1。
- DIFY_SMOKE_API_KEY：已发布的 movie-connection-test 应用的 Service API Key，不是 DeepSeek Key。
- TMDB_READ_ACCESS_TOKEN：TMDB 的只读访问令牌。
- MOVIE_INTERNAL_TOKEN：本机已自动生成，Dify 回调时使用相同值。
- DIFY_PROFILE_API_KEY：观影画像 Workflow 的 Key，模块 5 配置。
- DIFY_REQUEST_API_KEY：按本次需求推荐 Workflow 的 Key，模块 6 配置。
- DIFY_PERSONALIZED_API_KEY：按画像推荐 Workflow 的 Key，模块 7 配置。

当前三个业务 Key 均可留空，连通测试只使用 DIFY_SMOKE_API_KEY。

修改配置后重启后端。

## 内部连通检查

GET /internal/health 要求 X-Internal-Token，缺失或错误返回 401。可在 /docs 的 Authorize 中输入本机 MOVIE_INTERNAL_TOKEN 后执行。

Dify 的 HTTP 节点使用：

- 地址：http://host.docker.internal:18000/internal/health（当前机器；默认配置使用 8000）。
- Header：X-Internal-Token，值从本机 backend/.env 读取后填写。
- 按已部署的 Dify 配置放行所需宿主机地址。

内部接口不向前端提供令牌。

## 验证 Dify SSE

在 /docs 授权后执行 POST /internal/dify/check：

~~~json
{
  "inputs": {
    "query": "请回复连接成功"
  }
}
~~~

后端以 streaming 调用 Dify，消费 SSE，成功后返回 task_id、workflow_run_id 与 outputs。inputs 使用测试 Workflow 的真实输入变量名。尚未配置应用 Key 时返回 503；上游超时返回 504，其余调用失败返回 502。未配置 Key 时不会伪造结果。

本阶段不自动重试、查询或停止远端任务；这些在推荐任务生命周期模块加入。

## 检查

~~~powershell
cd D:/movie-agent/backend
./.venv/Scripts/python.exe -m pytest
cd ../frontend
npm run build
~~~

42 个测试用例使用独立临时 SQLite 和模拟 HTTP，覆盖迁移、内部认证、SSE、作品身份、单季年份、资料缓存、来源映射、匹配歧义、个人片库状态、整数星评分、跳过评分、分页筛选、搜索展开各季、拒绝整剧标记和重建应用后的持久化；不调用真实模型或产生模型费用。真实 Dify 联调需填写本机 Key 后执行内部检查。

模块 2 已用真实 TMDB 验证《盗梦空间》搜索／详情／海报、两版《沙丘》按年份区分、《权力的游戏》整剧及前两季、重复确认和重建应用后的持久化。

模块 3 真实联调通过：无年份输入的作品搜索、想看去重、想看转看过、4 星对应 8 分、跳过评分、拒绝半星、看过不降级且不覆盖评分、电影与剧集筛选、本地片名搜索和应用重建后的记录保留。真实验收使用独立本地数据库，不向日常片库写入测试记录；记录保存在被忽略的 .runtime/module3-live-check.json。前端构建及真实代理接口验证通过；本轮浏览器预览服务不可用，页面外观与交互仍需目视验收。

按季搜索调整已真实验证：《瑞克和莫蒂》第 1～9 季及特别篇分别出现在搜索结果中，不包含整剧。独立验收数据库内第一季 5 星／10 分、第二季 3 星／6 分互不影响；记录为 .runtime/season-search-check.json。41 项整体回归通过，增加禁止整剧标记后针对片库用例复验。

## Git

远端：https://github.com/0825lee/AI-Movie-Advisor

提交前使用 git status --short 检查待提交文件。原始豆瓣 JSON 属于个人数据，不作为公共仓库样例提交。

除 README.md 外，Markdown 开发文档以及 Word／PDF 等文档仅在本地维护，由忽略规则排除。
