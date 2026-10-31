# AI Movie Advisor · 9万天

基于 React、FastAPI、SQLite 和 Dify 的本地电影推荐项目。

当前完成 **最小正式工程、模块 2 作品资料与身份匹配、模块 3 我的片库、模块 4 豆瓣 JSON 导入**。支持电影和剧集各季的搜索与详情、个人想看／看过、可选整数星评分，以及导入进度、逐条结果、暂停和继续。保留资料缓存、来源映射、健康检查和 Dify SSE 客户端。画像与推荐按后续模块实现。

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

初始迁移 0001 建立 Alembic 版本基线；0002 建立作品缓存与来源映射；0003 建立个人片库；0004 建立导入任务和明细；0005 支持没有 TMDB ID 的豆瓣资料；0006 修正单正式季资料；0007 补充全部上映年份去重；0008 建立 profile_records，绑定每条个人记录保存六字段资料，清空片库时级联清空。升级已有工程时执行 alembic upgrade head；应用不会用 create_all 自动建表。

## 启动前端

在第二个终端：

~~~powershell
cd D:/movie-agent/frontend
npm run dev
~~~

打开 http://localhost:5173。开发服务器把 /api 请求转发至 VITE_BACKEND_URL，默认本机 8000，当前机器为 18000；浏览器不需要额外 CORS 配置。

首页为按墨刀原型布局实现的“我的片库”：左侧片单、右侧观影画像区域。片库可切换想看／看过、搜索名称、筛选电影／剧集并分页。画像尚未生成时显示真实观影记录数量与空状态，不显示原型中的模拟偏好。

“手动添加”按名称搜索 TMDB，不提供年份或类型输入；候选仍显示年份。有多个正式季的作品逐季展开为独立词条；只有一个正式季时使用剧名和原名本身，不附加“第一季”，链接打开 TMDB 作品主页。特别篇不计入正式季数量，仍是独立词条。内部保留季引用以读取资料，界面不提供整剧选择或季选择器。正常季按季号排列，特别篇列在其后；季数来自 TMDB，不硬编码。正式界面不单独展示“已确认作品”列表或要求额外确认资料。

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

本地单用户使用，界面统一称为影片，不再展示电影／剧集分类或类型筛选。每季作为独立影片保存状态和评分。看过记录默认按最近标记时间排序，每页 12 条；状态数量始终为全量计数，搜索结果数量单独计算。点击片库名称打开来源页面：豆瓣导入打开豆瓣，手动添加打开 TMDB；想看条目的“标记看过”仍在本应用内完成。

跨来源按原语言名称＋上映年份识别同一影片；originalTitle 为空时使用 title。JSON 开头连续上映日期中的全部年份参与匹配，例如电影节首映 2023、公映 2024 都可匹配，片库仍显示原来的首个年份；不自动放宽为相邻年份。名称统一大小写、空白和标点，明确季号保留在识别键中，不把不同季合并。年份缺失的记录仍可导入，但不生成名称＋年份识别键。手动添加时复用已有状态和评分，不因豆瓣 ID 与 TMDB ID 不同而重复添加。后续推荐模块将复用相同规则排除看过，想看不作为排除条件；本阶段不实现 AI 推荐。中文名不同于原名时不额外作为匹配依据，名称规则保持不变。

单正式季的 TMDB 作品按不带季号的原名＋年份与豆瓣记录对应，例如《白色巨塔》（2003）与手动搜索得到的同一作品复用个人记录；也识别豆瓣导入中明确写了该季季号的记录。多正式季的《怪奇物语》仍保留各季身份，第一季的状态不影响第二季。

| 当前状态 | 想看按钮 | 看过按钮 |
|---|---|---|
| 未加入 | 加入想看，可点击 | 标记看过，可点击 |
| 想看 | 已加入想看，置灰 | 标记看过，可点击，更新原记录 |
| 看过 | 加入想看，置灰 | 已看过，置灰 |

1～5 个整数星分别对应 2、4、6、8、10 分，不支持半星。评分以整数星保存，十分制由星级乘 2 得到。“跳过评分”保存为看过且 rating=null，展示“未评分”，仍计入看过数量。重复添加不新增，看过不降级，已有看过记录的评分不会被重复操作覆盖；本阶段不提供逐条修改评分或删除记录。

右侧星级、分数或“未评分”区域可点击，打开当前影片的评论小卡片；没有评论时显示“暂无评论”。弹卡支持关闭按钮、Esc 和点击卡片外关闭。左侧名称继续打开来源链接。标记看过的评分卡片提供选填评论框；跳过评分时也保存已填写的评论，不增加对已有看过记录的编辑功能。

片单标题右侧提供“清空片库”按钮，确认后移除全部想看、看过、个人评分、评论及关联的六字段资料，列表和数量归零。公开作品资料缓存及豆瓣来源身份映射保留，供重新导入复用。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | /library | status=wish/watched、query、page；界面统一列出影片，旧 media_type 参数保留兼容 |
| GET | /library/profile-input | 返回当前看过记录的六字段 JSON：records 数组；不包含想看 |
| DELETE | /library | 清空个人片库，返回 deleted 数量；不删除作品资料及来源映射 |
| GET | /library/state | media_type、tmdb_id、可选 season_number；读取作品的个人状态、记录 ID 和评分 |
| POST | /library/manual | 作品身份、status、可选 rating 和 comment；新增或将想看更新为看过 |
| POST | /library/{item_id}/watched | rating=1～5 或 null、可选 comment；将已有想看更新为看过，无需重新访问 TMDB |

标记日期与实际观影日期分开理解。添加来源及创建／更新时间保存在数据库，供导入复用。AI 选片入口暂未开放；模块 3 无需新增 Dify 工作流。

模块 4 的已确认导入规则：评分只取豆瓣 JSON 的 stars，缺失即未评分，不从 rating 回填、不比较两字段。按用户先清空、再重新导入的流程实现，本阶段不新增已有片库的合并策略。

## 豆瓣 JSON 导入

点击“导入豆瓣记录”，选择或拖入包含 records 数组的 JSON 文件。页面显示文件中的记录总数、看过／想看数量及已评分数量。片库非空时先使用“清空片库”，再点击“开始导入”。

- collect 映射为看过，wish 映射为想看；片库星级仍只读取 stars，缺失即未评分。画像资料另按原样保留 title、originalTitle、info、rating、markedAt、comment 六字段；导入任务保留所需字段以支持中断恢复。标签、封面及账号信息不保存。
- 从 title／originalTitle 读取名称和季号，从 info 的开头读取上映或播出年份；markedAt 按上海日期解析，缺失时保留 null，不以导入时间代替原始标记时间。
- JSON 直接解析入库，不请求 TMDB 或 Dify。豆瓣 ID 保存为来源身份，豆瓣链接用于跳转；不要求影片具有 TMDB ID，不因 TMDB 未收录而跳过。
- 从 info 提取类型、国家／地区、导演、演员、语言和时长，并保留原始 info。按日期→演员→国家／地区→官网／导演→时长划分区段；导演段去掉网址、日期和剧名。多个时长取首个，缺少的资料保留空值。提取规则针对当前导出格式，不适配其他导出器。
- 每季各是一条影片；没有季号时按原条目保存，不查询或自动选择第一季。
- 后台本地逐条处理，影片资料、个人记录和行结果在同一短事务内提交。结果分为新增、转看过、重复、跳过和失败，数量可与总进度核对。
- 进度每两秒更新，支持筛选及分页查看明细。关闭弹窗后仍继续运行，再次打开可查看最近十个任务。
- 可手动暂停，点击“继续导入”只处理未完成记录；导入不依赖 TMDB 网络连接。
- 后端退出会暂停任务；异常退出留下的运行中任务在下次查询时恢复为暂停，导入进度来自 SQLite。
- 导入运行时暂不能修改或清空片库，可先暂停。清空片库会结束未完成任务，避免旧任务继续写回已清空的记录；作品缓存和来源映射保留。
- 本模块沿用现有依赖，不需要新增 Dify 工作流。原始 JSON 不上传 GitHub 或 Dify；手动搜索和详情继续使用 TMDB。

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | /imports | filename 与 data（原始导出 JSON 对象），创建并开始导入 |
| GET | /imports | 最近十个任务及当前进度 |
| GET | /imports/{job_id} | 状态、已处理数量、分类统计与当前作品 |
| GET | /imports/{job_id}/rows | outcome=all/pending/added/upgraded/duplicate/skipped/failed，page 分页，每页 20 条 |
| POST | /imports/{job_id}/pause | 暂停导入，保留已完成结果 |
| POST | /imports/{job_id}/resume | 从未完成记录继续 |

模块 5 再接入画像生成；当前仅刷新真实片库数量和记录积累进度。

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

76 项完整回归通过，新增补齐用例及相关 9 项复验通过，使用独立临时 SQLite 和模拟 HTTP，覆盖旧片库迁移、内部认证、SSE、TMDB 检索、个人评分、清空、JSON 资料解析、离线导入、逐条明细、暂停继续、重启恢复、跨来源名称＋年份去重、多个上映年份与展示年份保留、单正式季命名与去重及私有字段排除；不调用真实模型或产生模型费用。真实 Dify 联调需填写本机 Key 后执行内部检查。

模块 2 已用真实 TMDB 验证《盗梦空间》搜索／详情／海报、两版《沙丘》按年份区分、《权力的游戏》整剧及前两季、重复确认和重建应用后的持久化。

模块 3 真实联调通过：无年份输入的作品搜索、想看去重、想看转看过、4 星对应 8 分、跳过评分、拒绝半星、看过不降级且不覆盖评分、电影与剧集筛选、本地片名搜索和应用重建后的记录保留。真实验收使用独立本地数据库，不向日常片库写入测试记录；记录保存在被忽略的 .runtime/module3-live-check.json。前端构建及真实代理接口验证通过；本轮浏览器预览服务不可用，页面外观与交互仍需目视验收。

按季搜索调整已真实验证：《瑞克和莫蒂》第 1～9 季及特别篇分别出现在搜索结果中，不包含整剧。独立验收数据库内第一季 5 星／10 分、第二季 3 星／6 分互不影响；记录为 .runtime/season-search-check.json。41 项整体回归通过，增加禁止整剧标记后针对片库用例复验。

模块 4 当前验证：完整本地 JSON 共 521 条，416 看过、105 想看、273 条有评分。本轮包含六字段同步的实际导入耗时 5.541 秒，新增 521、重复／跳过／失败均为 0，TMDB 请求为 0。提取到演员的影片 519 条、导演 515 条、国家和类型各 520 条；这些是字段非空覆盖数量，不代表独立人工核验了每一位人物的角色。44 页列表响应及重建应用后的片库和报告保留通过。使用独立验收数据库，不向日常片库写入测试记录；报告为 .runtime/local-import-check.json。前端构建通过，界面目视验收待用户完成。

单正式季修正已真实验证：豆瓣导入《白色巨塔》后，TMDB 搜索和详情不显示“第一季”，状态识别为已看过，重复添加不新增；《怪奇物语》仍返回第 1～5 季，导入第一季不会将第二季标记看过。验证使用独立数据库，报告为 .runtime/single-season-live-check.json。

## 画像输入准备

profile_records 与个人记录一一对应，包含想看与看过的六字段资料；提供给画像 AI 时只读取看过。豆瓣导入的字段值和空值按原样保存，info 不拆分；用户后续标记看过时同步更新个人评分、日期和评论。手动添加的影片使用已有 TMDB 资料组装 info，个人评分换算为十分制 rating。数据库同步不依赖导出静态文件。

0008 为旧片库建立关联资料；此前导入没有存下的评论和原始空原名，可使用原始 JSON 补齐：

~~~powershell
cd backend
.\.venv\Scripts\python.exe scripts/backfill_profile_records.py "原始豆瓣导出文件的完整路径"
~~~

工具只补齐现有豆瓣影片，不增加片库记录；保留用户在导出之后更新的个人评分、标记日期和已写评论。日常片库已完成补齐，521 条记录保留；当前 420 条看过、77 条看过记录有评论。上述数量是本轮操作时的快照。

本地 private_data/profile 已准备六字段输入快照、画像系统提示词、增量提示词、输出 Schema 和 Dify 操作说明，不上传 GitHub。后续设计为画像使用同一 Chatflow 会话，每新增至少 50 条看过更新；按画像推荐和按本次需求推荐分别使用独立 Workflow，后者不读取画像。目前未调用画像模型、未创建 Chatflow、未实现画像生成和自动更新。

完整 76 项回归及新增补齐用例通过，前端构建通过。真实原始 521 条在独立库完整导入，关联资料 521 条、看过输入 416 条，六字段逐值与原文件一致，77 条评论保留，重启后持久化及清库后关联资料归零通过。本轮完整导入耗时 5.541 秒。页面外观和弹卡交互需用户目视验收。

## Git

远端：https://github.com/0825lee/AI-Movie-Advisor

提交前使用 git status --short 检查待提交文件。原始豆瓣 JSON 属于个人数据，不作为公共仓库样例提交。

除 README.md 外，Markdown 开发文档以及 Word／PDF 等文档仅在本地维护，由忽略规则排除。
