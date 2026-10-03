#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from datetime import datetime
import pytz

# 基本配置
# 生产环境务必通过环境变量 SECRET_KEY 注入随机密钥，切勿在此处硬编码
DEBUG = os.environ.get('FLASK_DEBUG', '0') == '1'
SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-only-insecure-please-set-SECRET_KEY-env'
SESSION_COOKIE_SAMESITE = "Strict"

# 时区配置
TIMEZONE = 'Asia/Shanghai'
TIMEZONE_OBJ = pytz.timezone(TIMEZONE)

# 数据库配置
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.abspath(os.path.join(os.path.dirname(__file__), '../app.db'))
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Socks5代理服务器配置
PROXY_HOST = '0.0.0.0'
PROXY_PORT = 1080
PROXY_TIMEOUT = 60
MAX_CONNECTIONS = 100
BUFFER_SIZE = 4096
CONNECTION_TIMEOUT = 30
DATA_TRANSFER_TIMEOUT = 5

# 认证配置
ENABLE_AUTH = True
# 注意：以下仅为首次初始化数据库时创建的默认账号，部署后请立即登录并修改密码
DEFAULT_ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

# 登录权限控制（新增）
ADMIN_ONLY_LOGIN = True  # 只允许管理员登录后台

# 日志配置
LOG_LEVEL = 'INFO'
LOG_FILE = './logs/proxy_test.log'

# 获取当前本地时间的函数
def get_local_time():
    """获取当前本地时间"""
    return datetime.now(TIMEZONE_OBJ)
