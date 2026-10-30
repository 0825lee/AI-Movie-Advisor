# AI Movie Advisor · 9万天

基于 React、FastAPI、SQLite 和 Dify 的本地电影推荐项目。

当前完成 **最小正式工程与模块 2：作品资料与身份匹配**。支持电影、整剧和单季的真实搜索、详情预览、确认保存、资料缓存与来源映射，保留健康状态页面、内部认证和 Dify SSE 客户端。想看／看过、评分、导入、画像与推荐按后续模块实现。

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

初始迁移 0001 建立 Alembic 版本基线；0002 建立 catalog_items 作品缓存与 source_mappings 来源映射。升级已有工程时也需执行 alembic upgrade head。个人片库表在模块 3 建立。应用不会用 create_all 自动建表；未迁移时 /health 返回 503。

## 启动前端

在第二个终端：

~~~powershell
cd D:/movie-agent/frontend
npm run dev
~~~

打开 http://localhost:5173。开发服务器把 /api 请求转发至 VITE_BACKEND_URL，默认本机 8000，当前机器为 18000；浏览器不需要额外 CORS 配置。

首页为“发现作品”，支持按名称、可选年份和电影／剧集类型搜索。选择候选查看详情；整剧详情中可切换具体季，确认后出现在“已确认作品”中。确认的是作品资料，不会标为想看或看过。

“服务状态”页实际读取后端和数据库状态。Dify／TMDB 在该页只显示凭据是否填写，不代表外部调用成功。

## 作品资料与匹配

- 电影、整剧、单季分别用 movie:ID、tv:ID、season:剧集ID:季号确定身份；支持季号 0（特别篇）。
- 详情存入 SQLite，缓存 7 天；查看详情不会自动确认。刷新资料会重新请求 TMDB，保留已有确认状态。
- 中文简介缺失时尝试英文，均缺失时保留空值；缺海报或图片加载失败时显示占位。
- 导演、主创与演员保存 TMDB 人物 ID；主要演员按 TMDB 顺序保留前两位。主创与导演分别展示。
- 匹配优先复用来源映射，再核对名称、原名或已知别名、年份、类型与季号；结果分为 matched、ambiguous、missing_data、not_found。单季核对该季年份，不用整剧首播年份替代。
- TMDB 调用使用 20 秒超时，不自动重试；网络错误、找不到作品、限流分别返回明确状态。
- 本模块不搭建新的 Dify 工作流。测试接口或调用只读工具可能写入公共资料缓存，不修改个人观看状态。

后端接口（浏览器通过 /api 前缀代理）：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | /catalog/search | query、media_type=all/movie/tv、可选 year、page |
| GET | /catalog/details | media_type=movie/tv/season、tmdb_id、单季 season_number；refresh=true 更新缓存 |
| POST | /catalog/confirm | 确认作品，可附带 source 来源映射；重复确认不新增 |
| GET | /catalog/items | 已确认作品，page 分页，每页 24 条 |
| POST | /catalog/match | title、可选 original_title/year/media_type/season_number/source |
| GET | /internal/movies/search | 受认证保护的电影搜索，operationId=search_movies |
| GET | /internal/movies/{tmdb_id} | 受认证保护的电影详情，operationId=get_movie_details |

详细模型、工具输入输出和 X-Internal-Token 认证定义见运行中的 /openapi.json。电影工具留待后续模块注册到 Dify。

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

29 项测试使用独立临时 SQLite 和模拟 HTTP，覆盖迁移、内部认证、SSE、作品身份、单季年份、资料缓存、确认持久化、来源映射和匹配歧义；不调用真实模型或产生模型费用。真实 Dify 联调需填写本机 Key 后执行内部检查。

模块 2 已用真实 TMDB 验证《盗梦空间》搜索／详情／海报、两版《沙丘》按年份区分、《权力的游戏》整剧及前两季、重复确认和重建应用后的持久化。真实验收使用独立本地数据库，不写入个人片库。浏览器自动化因无法可靠识别当前网址而停止，页面目视验收尚未完成。

## Git

远端：https://github.com/0825lee/AI-Movie-Advisor

提交前使用 git status --short 检查待提交文件。原始豆瓣 JSON 属于个人数据，不作为公共仓库样例提交。

除 README.md 外，Markdown 开发文档以及 Word／PDF 等文档仅在本地维护，由忽略规则排除。
