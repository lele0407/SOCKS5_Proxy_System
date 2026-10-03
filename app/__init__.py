#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config.config import TIMEZONE_OBJ
from flask_wtf import CSRFProtect


# 初始化数据库
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('../config/config.py')
    csrf = CSRFProtect(app)
    csrf.init_app(app)
    
    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)
    
    # 添加自定义过滤器
    @app.template_filter('format_datetime')
    def format_datetime(value):
        """格式化日期时间，确保正确显示时区"""
        if value is None:
            return ''
        if value.tzinfo is None:
            # 为无时区的时间添加时区信息
            value = TIMEZONE_OBJ.localize(value)
        return value.strftime('%Y-%m-%d %H:%M:%S')
    
    # 注册蓝图
    from app.views.auth import auth_bp
    from app.views.admin import admin_bp
    from app.views.proxy import proxy_bp
    from app.views.scenario import scenario_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(proxy_bp)
    app.register_blueprint(scenario_bp)

    
    # 创建数据库表
    with app.app_context():
        db.create_all()
    
    return app 