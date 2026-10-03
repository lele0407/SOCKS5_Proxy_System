#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import db
from datetime import datetime
import ipaddress

class BlacklistIP(db.Model):
    """黑名单IP模型，用于存储被禁止的IP地址"""
    __tablename__ = 'blacklist_ips'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), unique=True, index=True)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    def __init__(self, ip_address, description=None, created_by=None):
        self.ip_address = ip_address
        self.description = description
        self.created_by = created_by
    
    @staticmethod
    def is_blacklisted(ip_address):
        """检查IP是否在黑名单中"""
        return BlacklistIP.query.filter_by(ip_address=ip_address, is_active=True).first() is not None

    def deactivate(self):
        """停用黑名单项"""
        self.is_active = False
        db.session.commit()
    
    def activate(self):
        """激活黑名单项"""
        self.is_active = True
        db.session.commit()
    
    def __repr__(self):
        return f"<BlacklistIP {self.ip_address}>" 