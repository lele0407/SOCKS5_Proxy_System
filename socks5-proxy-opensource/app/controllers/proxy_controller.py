#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import db
from app.models.connection import Connection
from app.models.blacklist import BlacklistIP
from app.models.whitelist import WhitelistIP
from app.models.log_entry import LogEntry
import importlib
import sys
import os

# 导入配置模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
config_module = importlib.import_module('config.config')

class ProxyController:
    """
    代理控制器类，处理代理服务相关的业务逻辑
    """
    
    @staticmethod
    def check_access(ip_address):
        """
        检查IP地址是否被允许访问
        
        参数:
            ip_address (str): 客户端IP地址
            
        返回:
            tuple: (bool, str) - (是否允许访问, 拒绝原因或None)
        """
        # 检查黑名单
        if BlacklistIP.is_blacklisted(ip_address):
            return False, "IP地址在黑名单中"
        
        # 检查白名单（如果启用）
        if WhitelistIP.is_whitelist_enabled() and not WhitelistIP.is_whitelisted(ip_address):
            return False, "IP地址不在白名单中"
        
        return True, None
    
    @staticmethod
    def add_to_blacklist(ip_address, description=None, created_by=None):
        """
        将IP地址添加到黑名单
        
        参数:
            ip_address (str): 要添加的IP地址
            description (str, 可选): 描述信息
            created_by (int, 可选): 创建者的用户ID
            
        返回:
            tuple: (BlacklistIP或None, 错误消息或None)
        """
        # 检查IP是否已在黑名单中
        existing = BlacklistIP.query.filter_by(ip_address=ip_address).first()
        if existing:
            if existing.is_active:
                return None, "IP地址已在黑名单中"
            else:
                # 如果存在但已停用，则重新激活
                existing.activate()
                return existing, None
        
        # 添加新的黑名单项
        blacklist_item = BlacklistIP(
            ip_address=ip_address,
            description=description,
            created_by=created_by
        )
        
        try:
            db.session.add(blacklist_item)
            db.session.commit()
            
            # 记录日志
            from app.models.user import User
            creator = "系统" if created_by is None else User.query.get(created_by).username
            LogEntry.info(f"IP {ip_address} 被 {creator} 添加到黑名单")
            
            return blacklist_item, None
        except Exception as e:
            db.session.rollback()
            return None, f"添加黑名单项时出错: {str(e)}"
    
    @staticmethod
    def remove_from_blacklist(ip_address_or_id):
        """
        从黑名单中移除IP地址
        
        参数:
            ip_address_or_id (str或int): IP地址或黑名单项ID
            
        返回:
            tuple: (bool, 错误消息或None)
        """
        # 根据ID或IP地址查找黑名单项
        if isinstance(ip_address_or_id, int):
            blacklist_item = BlacklistIP.query.get(ip_address_or_id)
        else:
            blacklist_item = BlacklistIP.query.filter_by(ip_address=ip_address_or_id).first()
        
        if not blacklist_item:
            return False, "未找到指定的黑名单项"
        
        try:
            db.session.delete(blacklist_item)
            db.session.commit()
            
            LogEntry.info(f"IP {blacklist_item.ip_address} 已从黑名单中移除")
            return True, None
        except Exception as e:
            db.session.rollback()
            return False, f"移除黑名单项时出错: {str(e)}"
    
    @staticmethod
    def add_to_whitelist(ip_address, description=None, created_by=None):
        """
        将IP地址添加到白名单
        
        参数:
            ip_address (str): 要添加的IP地址
            description (str, 可选): 描述信息
            created_by (int, 可选): 创建者的用户ID
            
        返回:
            tuple: (WhitelistIP或None, 错误消息或None)
        """
        # 检查IP是否已在白名单中
        existing = WhitelistIP.query.filter_by(ip_address=ip_address).first()
        if existing:
            if existing.is_active:
                return None, "IP地址已在白名单中"
            else:
                # 如果存在但已停用，则重新激活
                existing.activate()
                return existing, None
        
        # 添加新的白名单项
        whitelist_item = WhitelistIP(
            ip_address=ip_address,
            description=description,
            created_by=created_by
        )
        
        try:
            db.session.add(whitelist_item)
            db.session.commit()
            
            # 记录日志
            from app.models.user import User
            creator = "系统" if created_by is None else User.query.get(created_by).username
            LogEntry.info(f"IP {ip_address} 被 {creator} 添加到白名单")
            
            return whitelist_item, None
        except Exception as e:
            db.session.rollback()
            return None, f"添加白名单项时出错: {str(e)}"
    
    @staticmethod
    def remove_from_whitelist(ip_address_or_id):
        """
        从白名单中移除IP地址
        
        参数:
            ip_address_or_id (str或int): IP地址或白名单项ID
            
        返回:
            tuple: (bool, 错误消息或None)
        """
        # 根据ID或IP地址查找白名单项
        if isinstance(ip_address_or_id, int):
            whitelist_item = WhitelistIP.query.get(ip_address_or_id)
        else:
            whitelist_item = WhitelistIP.query.filter_by(ip_address=ip_address_or_id).first()
        
        if not whitelist_item:
            return False, "未找到指定的白名单项"
        
        try:
            db.session.delete(whitelist_item)
            db.session.commit()
            
            LogEntry.info(f"IP {whitelist_item.ip_address} 已从白名单中移除")
            return True, None
        except Exception as e:
            db.session.rollback()
            return False, f"移除白名单项时出错: {str(e)}"
    
    @staticmethod
    def close_connection(connection_id, closed_by=None):
        """
        关闭指定连接
        
        参数:
            connection_id (int): 连接ID
            closed_by (int, 可选): 关闭操作执行者的用户ID
            
        返回:
            tuple: (bool, 错误消息或None)
        """
        connection = Connection.query.get(connection_id)
        if not connection:
            return False, "未找到指定的连接"
        
        # 只能关闭活动状态的连接
        if connection.status != 'CONNECTED':
            return False, "只能关闭活动状态的连接"
        
        try:
            connection.close()
            
            # 记录日志
            if closed_by:
                from app.models.user import User
                closer = User.query.get(closed_by)
                if closer:
                    LogEntry.info(f"连接 {connection_id} 被 {closer.username} 手动关闭",
                                 connection_id=connection_id,
                                 user_id=closed_by)
            
            return True, None
        except Exception as e:
            return False, f"关闭连接时出错: {str(e)}"
    
    @staticmethod
    def get_connection_stats():
        """
        获取连接统计信息
        
        返回:
            dict: 连接统计信息
        """
        active_count = Connection.query.filter_by(status='CONNECTED').count()
        closed_count = Connection.query.filter_by(status='CLOSED').count()
        error_count = Connection.query.filter_by(status='ERROR').count()
        total_count = Connection.query.count()
        
        # 计算总流量
        total_sent = db.session.query(db.func.sum(Connection.bytes_sent)).scalar() or 0
        total_received = db.session.query(db.func.sum(Connection.bytes_received)).scalar() or 0
        
        # 格式化流量数据
        def format_bytes(bytes):
            units = ['B', 'KB', 'MB', 'GB', 'TB']
            unit_index = 0
            size = float(bytes)
            
            while size >= 1024 and unit_index < len(units) - 1:
                size /= 1024
                unit_index += 1
                
            return f"{size:.2f} {units[unit_index]}"
        
        return {
            'active_connections': active_count,
            'closed_connections': closed_count,
            'error_connections': error_count,
            'total_connections': total_count,
            'bytes_sent': total_sent,
            'bytes_received': total_received,
            'formatted_sent': format_bytes(total_sent),
            'formatted_received': format_bytes(total_received)
        }
    
    @staticmethod
    def update_proxy_config(config_updates):
        """
        更新代理服务器配置
        
        参数:
            config_updates (dict): 要更新的配置项
            
        返回:
            tuple: (bool, 错误消息或None)
        """
        config_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../config/config.py'))
        
        try:
            # 读取当前配置文件
            with open(config_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # 更新配置
            with open(config_file, 'w', encoding='utf-8') as f:
                for line in lines:
                    line_updated = False
                    
                    for key, value in config_updates.items():
                        # 判断是否为布尔值
                        if isinstance(value, bool):
                            value_str = str(value)
                        # 判断是否为字符串
                        elif isinstance(value, str):
                            value_str = f"'{value}'"
                        # 其他类型
                        else:
                            value_str = str(value)
                            
                        # 更新配置行
                        if line.strip().startswith(key + ' ='):
                            f.write(f"{key} = {value_str}\n")
                            line_updated = True
                            break
                            
                    if not line_updated:
                        f.write(line)
                    
            # 重新加载配置模块
            importlib.reload(config_module)
            
            return True, None
        except Exception as e:
            return False, f"更新配置文件时出错: {str(e)}" 