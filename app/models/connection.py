#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import db
from datetime import datetime
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config.config import get_local_time

class Connection(db.Model):
    """代理连接模型，记录每个代理连接的详细信息"""
    __tablename__ = 'connections'
    
    id = db.Column(db.Integer, primary_key=True)
    client_addr = db.Column(db.String(50))  # 客户端地址
    client_port = db.Column(db.Integer)     # 客户端端口
    target_addr = db.Column(db.String(255)) # 目标地址
    target_port = db.Column(db.Integer)     # 目标端口
    
    # 连接状态：CONNECTING, CONNECTED, CLOSED, ERROR
    status = db.Column(db.String(20), default='CONNECTING')
    
    start_time = db.Column(db.DateTime, default=get_local_time)
    end_time = db.Column(db.DateTime, nullable=True)
    
    # 如果有身份验证，记录用户ID
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # 添加与用户的关系
    user = db.relationship('User', backref=db.backref('connections', lazy='dynamic'))
    
    # 数据统计
    bytes_sent = db.Column(db.BigInteger, default=0)
    bytes_received = db.Column(db.BigInteger, default=0)
    
    # 错误信息
    error_message = db.Column(db.String(255), nullable=True)
    
    def __init__(self, client_addr, client_port, target_addr=None, target_port=None, user_id=None):
        self.client_addr = client_addr
        self.client_port = client_port
        self.target_addr = target_addr
        self.target_port = target_port
        self.user_id = user_id
    
    def set_connected(self, target_addr, target_port):
        """设置连接状态为已连接"""
        self.status = 'CONNECTED'
        self.target_addr = target_addr
        self.target_port = target_port
        db.session.commit()
    
    def close(self, error=None):
        """关闭连接"""
        self.status = 'ERROR' if error else 'CLOSED'
        self.end_time = get_local_time()
        if error:
            self.error_message = str(error)
        db.session.commit()
    
    def update_traffic(self, sent=0, received=0):
        """更新流量统计"""
        self.bytes_sent += sent
        self.bytes_received += received
        db.session.commit()
    
    @property
    def duration(self):
        """连接持续时间（秒）"""
        end = self.end_time or get_local_time()
        return (end - self.start_time).total_seconds()
    
    def __repr__(self):
        return f"<Connection {self.client_addr}:{self.client_port} -> {self.target_addr}:{self.target_port}>" 