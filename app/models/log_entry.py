#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import db
from datetime import datetime
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config.config import get_local_time

class LogEntry(db.Model):
    """日志条目模型，记录系统日志"""
    __tablename__ = 'log_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=get_local_time, index=True)
    level = db.Column(db.String(20))  # 日志级别: INFO, WARNING, ERROR, CRITICAL
    message = db.Column(db.Text)
    
    # 相关信息
    client_ip = db.Column(db.String(50), nullable=True)
    client_port = db.Column(db.Integer, nullable=True)
    target_host = db.Column(db.String(255), nullable=True)
    target_port = db.Column(db.Integer, nullable=True)
    
    # 用户信息
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # 连接信息
    connection_id = db.Column(db.Integer, db.ForeignKey('connections.id'), nullable=True)
    
    def __init__(self, level, message, client_ip=None, client_port=None,
                 target_host=None, target_port=None, user_id=None, connection_id=None):
        self.level = level
        self.message = message
        self.client_ip = client_ip
        self.client_port = client_port
        self.target_host = target_host
        self.target_port = target_port
        self.user_id = user_id
        self.connection_id = connection_id
    
    @staticmethod
    def log(level, message, **kwargs):
        """创建新的日志条目"""
        log_entry = LogEntry(level=level, message=message, **kwargs)
        db.session.add(log_entry)
        db.session.commit()
        return log_entry
    
    @staticmethod
    def info(message, **kwargs):
        """创建信息级别日志"""
        return LogEntry.log('INFO', message, **kwargs)
    
    @staticmethod
    def warning(message, **kwargs):
        """创建警告级别日志"""
        return LogEntry.log('WARNING', message, **kwargs)
    
    @staticmethod
    def error(message, **kwargs):
        """创建错误级别日志"""
        return LogEntry.log('ERROR', message, **kwargs)
    
    @staticmethod
    def critical(message, **kwargs):
        """创建严重错误级别日志"""
        return LogEntry.log('CRITICAL', message, **kwargs)
    
    def __repr__(self):
        return f"<LogEntry [{self.level}] {self.timestamp}: {self.message[:50]}>" 