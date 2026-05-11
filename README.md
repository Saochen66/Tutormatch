# 家教服务系统

一个连接家教与学生/家长的供需匹配平台。

## 功能特性

- 用户注册登录（支持家教/学生家长两种角色）
- 家教发布授课信息
- 学生/家长发布家教需求
- 双向搜索与匹配
- 管理员后台（用户管理、密码修改）
- AI 智能助手（基于数据库摘要上下文回答系统问题）

## 技术栈

- **后端**: Python 3 + Flask
- **数据库**: SQLite（开发）/ PostgreSQL（生产）
- **前端**: HTML + CSS + Jinja2模板

## 开发环境要求

- Ubuntu 24.04 Desktop
- Python 3.8+
- 网络访问（用于安装依赖）

---

## 一、部署步骤

### 1.1 基础环境

```bash
# 更新系统包
sudo apt update && sudo apt upgrade -y

# 安装Python3和pip
sudo apt install -y python3 python3-pip python3-venv
```

### 1.2 创建项目目录

```bash
# 创建项目目录
mkdir -p /home/work/家教系统

# 进入目录
cd /home/work/家教系统
```

### 1.3 获取项目代码

**方式A: 从本机器复制**
```bash
# 如果代码在本机，直接复制
cp -r /home/work/家教系统/* /home/work/家教系统/
```

**方式B: 从GitHub获取（如果有仓库）**
```bash
git clone <仓库地址> /home/work/家教系统
```

### 1.4 创建虚拟环境并安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖（使用国内源）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 1.5 启动服务

```bash
# 启动应用（开发模式）
python app.py
```

如果启用了 AI 助手，请先配置环境变量（Windows PowerShell 示例）：

```powershell
$env:NVIDIA_API_KEY="你的API Key"
$env:NVIDIA_MODEL="qwen/qwen2.5-72b-instruct"
$env:NVIDIA_MODELS="qwen/qwen2.5-72b-instruct,meta/llama-3.1-70b-instruct,mistralai/mixtral-8x7b-instruct-v0.1,qwen/qwen3.5-397b-a17b"

# 可选：配置更多提供商，助手会自动轮询重试
$env:OPENROUTER_API_KEY="你的OpenRouter Key"
$env:SILICONFLOW_API_KEY="你的硅基流动 Key"

# 可选：上游超时（秒）
$env:LLM_REQUEST_TIMEOUT="22"

python app.py
```

助手稳定性策略：
- 先按候选模型重试
- 同时支持多 API 提供商（NVIDIA/OpenRouter/硅基流动）依次重试
- 若所有外部 API 不可用，自动回退到本地统计回复（不报 500）

服务启动后访问：
- 本机: http://localhost:5000
- 局域网: http://<本机IP>:5000

### 1.6 后台运行（可选）

```bash
# 使用nohup后台运行
nohup python app.py > app.log 2>&1 &

# 查看日志
tail -f app.log

# 停止服务
pkill -f "python app.py"
```

---

## 二、初始化数据

首次启动时，系统会自动创建：
- SQLite数据库文件: `tutor_service.db`
- 管理员账号: 用户名 `admin`，密码 `admin123`
- 上传目录: `static/uploads/`

---

## 三、切换到 PostgreSQL（可选生产环境）

### 3.1 安装PostgreSQL

```bash
# 安装PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# 启动服务
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 3.2 创建数据库

```bash
# 切换到postgres用户
sudo -u postgres psql

# 创建数据库
CREATE DATABASE tutor_service;

# 创建用户
CREATE USER tutoruser WITH PASSWORD 'your_password';

# 授权
GRANT ALL PRIVILEGES ON DATABASE tutor_service TO tutoruser;

# 退出
\q
```

### 3.3 修改配置

编辑 `config.py`，将数据库URI改为：

```python
SQLALCHEMY_DATABASE_URI = 'postgresql://tutoruser:your_password@localhost/tutor_service'
```

---

## 四、使用说明

### 4.1 访问系统

浏览器打开: http://<服务器IP>:5000

AI 助手入口: http://<服务器IP>:5000/assistant

### 4.2 角色说明

| 角色 | 功能 |
|------|------|
| 家教 | 发布授课信息、搜寻生源、查看学生需求详情 |
| 学生/家长 | 发布需求信息、搜寻家教、查看家教详情 |
| 管理员 | 通过 /admin/login 访问，管理用户账号 |

### 4.3 登录会话说明

- 系统会把家教和学生的登录态按角色分别保存，因此同一浏览器里可以同时保留一个家教账号和一个学生账号。
- 同一角色下仍然只保留当前登录账号；如果再次登录同角色的新账号，会覆盖该角色原来的登录态。
- 部署时请为 `SECRET_KEY` 配置固定值，避免应用重启或多进程部署后出现会话失效、账号显示混乱的问题。

### 4.4 业务流程

1. **注册**: 选择身份（家教/学生家长），填写信息注册
2. **登录**: 使用昵称和密码登录
3. **完善信息**: 
   - 家教填写授课信息（科目、年级、费用、时间等）
   - 学生填写需求信息
4. **搜索匹配**: 根据条件搜索并查看详情
5. **联系**: 通过微信号联系对方

---

## 五、目录结构

```
家教系统/
├── app.py              # Flask主应用
├── config.py           # 配置文件
├── models.py           # 数据库模型
├── requirements.txt    # Python依赖
├── tutor_service.db    # SQLite数据库
├── venv/               # 虚拟环境
├── static/
│   └── uploads/        # 头像上传目录
└── templates/          # HTML模板
    ├── base.html
    ├── index.html
    ├── register.html
    ├── login.html
    ├── tutor_info.html
    ├── student_info.html
    ├── search_tutors.html
    ├── search_students.html
    ├── tutor_detail.html
    ├── student_detail.html
    └── admin/
        ├── login.html
        └── dashboard.html
```

---

## 六、常见问题

### Q1: 启动失败，提示端口被占用
```bash
# 查看占用进程
lsof -i:5000

# 杀掉进程
kill <PID>

# 或使用其他端口
python app.py --port=8080
```

### Q2: 无法上传头像
```bash
# 检查上传目录权限
ls -la static/uploads/

# 如果没有权限，修改
sudo chmod 777 static/uploads/
```

### Q3: 数据库初始化失败
```bash
# 删除旧数据库文件
rm tutor_service.db

# 重新启动应用（会自动创建）
python app.py
```

### Q4: 需要修改管理员密码
```bash
# 在Python中修改
python3
>>> from app import app, db, Admin
>>> from werkzeug.security import generate_password_hash
>>> with app.app_context():
...     admin = Admin.query.filter_by(username='admin').first()
...     admin.set_password('新密码')
...     db.session.commit()
```

---

## 七、安全建议

1. **修改默认密码**: 首次部署后修改admin密码
2. **使用HTTPS**: 生产环境配置SSL证书
3. **限制端口**: 防火墙只开放必要端口
4. **定期备份**: 定期备份数据库文件
5. **日志监控**: 定期检查日志文件

---

## 八、技术支持

如有问题，请检查：
1. Python版本: `python3 --version`（需3.8+）
2. 依赖安装: `pip list`
3. 端口监听: `netstat -tlnp | grep 5000`

---

*文档版本: V1.0*
*更新日期: 2026-03-29*
