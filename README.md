# ERP

基于 Django 的企业管理软件，包含销售、采购、库存、组织、工作流等常用模块；本仓库为适配后的自用版本，并集成吉客云销售单同步。

技术栈：**Python 3.11+** / **Django 4.2**（本地默认 SQLite，可选 MySQL）。

源项目参考：[zhuinfo/Django-ERP](https://github.com/zhuinfo/Django-ERP)

---

## 功能概览

- 销售管理、采购管理、库存管理、组织与基础数据
- 工作流审批
- 采购单、报价单等批量导入
- **吉客云开放平台**：拉取销售单写入本地（`oms.trade.fullinfoget` / `oms.trade.countget`）

---

## 环境要求

- Python 3.11 或更高版本
- Windows / Linux / macOS
- （可选）MySQL，若不用可直接使用项目自带的 SQLite

---

## 快速开始

### 1. 克隆代码

```bash
git clone git@github.com:huaye0517/ERP.git
cd ERP
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv venv

# Windows PowerShell
.\venv\Scripts\Activate.ps1

# Linux / macOS
# source venv/bin/activate

pip install -r Install/requirements.txt
```

### 3. 初始化数据库

本地默认使用 SQLite（`mis/settings.py`），无需单独建库：

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. 启动

```bash
python manage.py runserver 0.0.0.0:8000
```

浏览器访问：http://127.0.0.1:8000/admin/

---

## 数据库配置

配置文件：`mis/settings.py`

**当前默认（SQLite）：**

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}
```

**如需改用 MySQL**，可改为类似：

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'HOST': 'localhost',
        'NAME': 'mis',
        'USER': 'root',
        'PASSWORD': 'your_password',
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}
```

项目已通过 PyMySQL 兼容 Django 的 MySQL 驱动，一般无需再装 `mysqlclient`。

也可参考历史初始化脚本：`Install/SQL/mis.sql`（面向早期 MySQL 结构，新环境优先使用 `migrate`）。

---

## 吉客云销售单同步

### 前置条件

1. 在 [吉客云开放平台](https://open.jackyun.com/) 创建自研应用，并完成审核  
2. 联系客户经理开通「开放平台」调用权限（仅「已审核」不够）  
3. 订阅接口：
   - `oms.trade.fullinfoget`（销售单查询）
   - `oms.trade.countget`（销售单总数查询）

### 配置

在环境变量中配置密钥（**不要把 Secret 写进仓库**）：

```powershell
# Windows PowerShell
$env:JACKYUN_APP_KEY="你的AppKey"
$env:JACKYUN_APP_SECRET="你的AppSecret"
```

```bash
# Linux / macOS
export JACKYUN_APP_KEY="你的AppKey"
export JACKYUN_APP_SECRET="你的AppSecret"
```

相关配置项见 `mis/settings.py` 中的 `JACKYUN_*`。

### 同步方式

**后台：** 吉客云同步 → 吉客云同步日志 →「立即同步最近7天销售单」

**命令行：**

```bash
python manage.py sync_jackyun_orders --days 7
```

说明：

- 平台限制单次查询时间跨度不超过 **7 天**
- 以吉客云 `tradeNo` 作为本地销售单 `code`，重复同步会跳过
- 缺失的客户、物料会按需自动创建

---

## 常用命令

```bash
# 数据库迁移
python manage.py migrate

# 创建管理员
python manage.py createsuperuser

# 修改管理员密码
python manage.py changepassword admin

# 吉客云同步
python manage.py sync_jackyun_orders --days 3
```

---

## 目录说明（节选）

| 目录/文件 | 说明 |
|-----------|------|
| `mis/` | 项目配置与入口 |
| `sale/` / `purchase/` / `invent/` | 销售 / 采购 / 库存 |
| `basedata/` / `organ/` / `workflow/` | 基础数据 / 组织 / 工作流 |
| `jackyun/` | 吉客云 API 客户端与同步 |
| `Install/requirements.txt` | Python 依赖 |
| `static/` / `templates/` | 静态资源与后台模板 |

---

## 排错

### MySQL 驱动相关

若改用 MySQL 后提示找不到驱动，请确认已安装依赖：

```bash
pip install PyMySQL
```

并保证 `mis/__init__.py` 中已按项目方式加载 PyMySQL。

### 吉客云返回「未开通开放平台」

应用状态为「已审核」仍可能无法调用。请联系吉客云客户经理开通开放平台权限后重试。

### 静态文件 / 中文界面

界面语言为简体中文（`LANGUAGE_CODE = 'zh-hans'`）。若样式异常，确认 `static/` 目录完整且服务已重启。
