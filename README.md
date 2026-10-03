# SOCKS5 Proxy System

一个基于 **Python + Flask** 的轻量级 SOCKS5 代理服务器，自带 Web 管理后台。代理核心用标准 socket 从零实现，Web 端用 Flask + SQLAlchemy 提供仪表盘、用户管理、黑白名单、连接监控与日志查询。适合学习 SOCKS5 协议、快速搭一个带管理界面的内网/个人代理。

---

## 功能特性

### 代理核心（`app/models/proxy_server.py`）

- 完整实现 **SOCKS5 (RFC 1928)** 握手流程：
  - 认证方法协商：支持 **无认证 (0x00)** 与 **用户名/密码 (0x02)** 两种方式，可在后台开关。
  - 地址类型：支持 **IPv4 / 域名 / IPv6** 目标地址。
  - 命令：实现 **CONNECT (0x01)**；BIND / UDP ASSOCIATE 会按协议规范返回"命令不支持"。
- 每连接一个工作线程，转发阶段用 `select` 做双向 IO 多路复用。
- **数据库异步写入**：连接记录与日志通过队列交给独立 worker 线程落库，避免 DB 操作阻塞代理转发。
- 黑白名单基于 `ipaddress` 模块解析，支持单 IP 与 **CIDR 网段**。

### Web 管理后台（Flask 蓝图）

- **仪表盘**：代理运行状态、在线连接数、流量概览。
- **用户管理**：增删改用户、启停账号、bcrypt 密码哈希、管理员标记。
- **实时连接**：查看当前活动连接、按客户端/目标筛选、强制断开。
- **黑白名单**：按 IP / CIDR 放行或封禁。
- **日志查询**：连接日志 + 系统日志分页检索。
- **运行参数热更新**：监听地址、端口、超时、并发、缓冲大小、认证开关等可在线调整并**热重启代理线程**，不中断 Web 服务。
- **多场景配置**：可保存多套参数（端口、超时、并发……）并一键切换。
- **登录保护**：管理员才能登录后台；登录页带 4 位图形验证码（Pillow 生成，60 秒一次性有效）。

---

## 技术栈

| 层 | 选型 |
|---|---|
| 语言 | Python 3.8+（3.8 / 3.11 实测通过） |
| Web 框架 | Flask 2.0 + Flask-SQLAlchemy 2.5 + Flask-Login + Flask-WTF |
| 密码哈希 | bcrypt |
| 验证码 | Pillow |
| 数据库 | SQLite（零外部依赖） |
| 代理 | 标准库 socket / select / threading |

---

## 快速开始

### 1. 克隆并安装依赖

```bash
git clone <your-repo-url>
cd socks5-proxy-opensource

python -m venv venv
# Windows:  venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

pip install -r requirements.txt
```

### 2. 配置环境变量（生产必改）

```bash
# Linux / macOS
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="请改成一个强密码"

# Windows PowerShell
$env:SECRET_KEY = -join ((1..64) | ForEach-Object { '{0:x}' % (Get-Random -Max 16) })
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "请改成一个强密码"
```

> 不设置环境变量也能跑，但 `SECRET_KEY` 会使用仓库里的开发占位符，**仅限本地调试**，公网部署必须改。

### 3. 初始化数据库

```bash
python db_init.py
```

这会自动建表，并创建默认管理员与一个测试用户（见下文"默认账号"）。

### 4. 启动

```bash
python run.py
```

启动后同时监听两个端口：

| 服务 | 地址 |
|---|---|
| SOCKS5 代理 | `0.0.0.0:1080` |
| Web 管理后台 | `http://127.0.0.1:5000` |

---

## 作为客户端使用代理

代理启动后，在任意支持 SOCKS5 的客户端里填：

- **服务器**：代理机器 IP
- **端口**：`1080`
- **认证**：若后台开启了认证，填入后台创建的用户名/密码；关闭认证则留空。

命令行验证：

```bash
# 无认证模式
curl --socks5 127.0.0.1:1080 https://example.com -I

# 用户名密码认证模式（注意末尾的 s 表示走域名解析也经过代理）
curl --socks5 user:pass@127.0.0.1:1080 https://example.com -I
```

浏览器可配合 SwitchyOmega / 代理 SwitchySharp 等插件，协议选 SOCKS5，地址端口同上。

---

## 管理后台路由

登录 <http://127.0.0.1:5000> 后：

| 路径 | 功能 |
|---|---|
| `/auth/login`、`/auth/logout`、`/auth/profile` | 登录 / 登出 / 改密 |
| `/admin/` | 仪表盘 |
| `/admin/users` | 用户列表与增删改 |
| `/admin/blacklist`、`/admin/whitelist` | 黑白名单管理 |
| `/admin/connections` | 实时连接、强制断开 |
| `/admin/logs` | 日志查询 |
| `/admin/scenarios` | 多套配置场景 CRUD |
| `/proxy/settings`、`/proxy/restart`、`/proxy/status` | 代理参数调整、热重启、状态查看 |

> 后台默认仅管理员可登录（`ADMIN_ONLY_LOGIN=True`）。

---

## 配置项说明

所有可调参数集中在 `config/config.py`：

| 配置 | 默认 | 说明 |
|---|---|---|
| `SECRET_KEY` | 环境变量 `SECRET_KEY` | Flask 会话密钥，生产必须改 |
| `DEBUG` | `False`（环境变量 `FLASK_DEBUG=1` 开启） | 调试模式 |
| `PROXY_HOST` / `PROXY_PORT` | `0.0.0.0` / `1080` | SOCKS5 监听地址与端口 |
| `PROXY_TIMEOUT` | `60` | 代理整体超时（秒） |
| `MAX_CONNECTIONS` | `100` | 最大并发连接数 |
| `BUFFER_SIZE` | `4096` | 转发缓冲区字节数 |
| `CONNECTION_TIMEOUT` | `30` | 建链超时 |
| `DATA_TRANSFER_TIMEOUT` | `5` | 数据收发空闲超时 |
| `ENABLE_AUTH` | `True` | 是否启用 SOCKS5 用户名密码认证 |
| `ADMIN_ONLY_LOGIN` | `True` | 是否仅允许管理员登录后台 |
| `LOG_LEVEL` / `LOG_FILE` | `INFO` / `./logs/proxy_test.log` | 日志级别与路径 |

---

## 默认账号

`db_init.py` 首次运行会创建：

| 用户名 | 密码 | 权限 |
|---|---|---|
| `admin` | `admin` | 管理员 |
| `test` | `test` | 普通用户 |

> ⚠️ **首次部署后请立刻登录修改密码**。生产环境建议通过 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 环境变量覆盖默认值。

---

## 目录结构

```
.
├── run.py                  # 入口：启动代理线程 + Flask Web
├── db_init.py              # 初始化数据库与默认账号
├── requirements.txt
├── config/
│   └── config.py           # 全部可调参数（密钥/账号走环境变量）
├── app/
│   ├── __init__.py         # Flask 应用工厂、蓝图注册、模板过滤器
│   ├── models/
│   │   ├── proxy_server.py # SOCKS5 服务端核心（协议握手 + 转发 + 异步 DB worker）
│   │   ├── user.py         # 用户模型（bcrypt）
│   │   ├── connection.py   # 连接记录
│   │   ├── blacklist.py / whitelist.py
│   │   ├── log_entry.py
│   │   └── scenario.py    # 多场景配置
│   ├── views/              # Flask 蓝图路由：auth / admin / proxy / scenario
│   ├── controllers/        # 业务逻辑封装
│   └── templates/          # Jinja2 后台页面
└── logs/                   # 运行日志（.gitignore 忽略 *.log）
```

---

## ⚠️ 安全须知

- 本项目默认 `DEBUG=False`，且仓库**不附带** `app.db` 与 `logs/`，首次运行自动生成。
- **不要在公网直接用 `python run.py` 跑生产**。建议用 `gunicorn` / `uWSGI` 跑 Web 部分，前置 Nginx；SOCKS5 监听本身直接暴露即可，但务必配合防火墙与强认证。
- `0.0.0.0` 表示对所有网卡开放。仅本机使用时建议改成 `127.0.0.1`。
- 登录验证码当前存在**进程内存**里（`auth.py` 的 `captcha_store`），多进程/多实例部署需换成 Redis 等集中存储，否则验证码校验会随机失败。
- 请勿将运行后产生的 `app.db`、`logs/*.log` 提交到公开仓库（`.gitignore` 已默认忽略）。

## 已知限制

- SOCKS5 仅实现 **CONNECT** 命令；BIND 与 UDP ASSOCIATE 不支持。
- 无 TLS / mTLS 层，SOCKS5 流量明文（含用户名密码）。公网使用建议前面套一层 WireGuard / SSH 隧道，或自行加 TLS。
- 单进程模型；水平扩展需要额外改造（验证码会话、在线连接状态目前都在内存里）。

## 开发

```bash
# 跑起来（开发模式）
$env:FLASK_DEBUG=1   # Windows
# export FLASK_DEBUG=1   # Linux/macOS
python run.py
```

欢迎提 Issue / PR。提交前请确认：

- 不提交 `app.db`、`logs/`、`.idea/`、`__pycache__/`。
- 新配置项写进 `config/config.py` 并在本文档"配置项说明"里补一行。

## License

MIT，详见 [LICENSE](./LICENSE)。
