#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import db, login_manager
from flask_login import UserMixin
import bcrypt
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config.config import get_local_time

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    email = db.Column(db.String(120), unique=True, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_local_time)
    last_login = db.Column(db.DateTime, nullable=True)
    
    def __init__(self, username, password, email=None, is_admin=False, is_active=True):
        self.username = username
        self.set_password(password)
        self.email = email
        self.is_admin = is_admin
        self.is_active = is_active
    
    def set_password(self, password):
        """设置用户密码，使用bcrypt进行加密"""
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def verify_password(self, password):
        """验证用户密码"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def update_last_login(self):
        """更新最后登录时间"""
        self.last_login = get_local_time()
        db.session.commit()
    
    def __repr__(self):
        return f"<User {self.username}>"

@login_manager.user_loader
def load_user(user_id):
    """Flask-Login用于加载用户的回调函数"""
    return User.query.get(int(user_id)) 