# AI Movie Advisor · 9万天

基于 React、FastAPI、SQLite 和 Dify 的本地电影推荐项目。

当前完成 **1.7 最小正式工程**：健康状态页面、SQLite 迁移基础、内部认证检查和 Dify SSE 客户端。片库、导入、画像与推荐按后续模块实现。

## 目录

- frontend：React＋TypeScript＋Vite。
- backend：FastAPI、SQLite、Alembic、Dify 客户端与测试。
- ai-movie-advisor：保留的墨刀 HTML 原型。
- 开发执行计划.md、模块开发执行指引.md：产品规则与后续模块。

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

初始迁移 0001 建立 Alembic 版本基线，作品与片库表从模块 2 加入。应用不会用 create_all 自动建表；未迁移时 /health 返回 503。

## 启动前端

在第二个终端：

~~~powershell
cd D:/movie-agent/frontend
npm run dev
~~~

打开 http://localhost:5173。开发服务器把 /api 请求转发至 VITE_BACKEND_URL，默认本机 8000，当前机器为 18000；浏览器不需要额外 CORS 配置。

页面实际读取后端和数据库状态。Dify／TMDB 只显示凭据是否填写，不代表外部调用成功。停止后端再点击“重新检查”，页面会显示真实连接错误。

## 填写服务端配置

编辑 backend/.env：

- DIFY_BASE_URL=http://127.0.0.1:18080/v1。
- DIFY_SMOKE_API_KEY：已发布的 movie-connection-test 应用的 Service API Key，不是 DeepSeek Key。
- TMDB_READ_ACCESS_TOKEN：TMDB 的只读访问令牌。
- MOVIE_INTERNAL_TOKEN：本机已自动生成，Dify 回调时使用相同值。
- 三个业务 Workflow 的 Key 在后续模块配置。

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

测试使用独立临时 SQLite 和模拟 HTTP 流，覆盖真实迁移、内部认证、SSE 分块／UTF-8／失败与中断；不调用真实模型或产生模型费用。真实 Dify 联调需填写本机 Key 后执行内部检查。

## Git

远端：https://github.com/0825lee/AI-Movie-Advisor

提交前使用 git status --short 检查待提交文件。原始豆瓣 JSON 属于个人数据，不作为公共仓库样例提交。
