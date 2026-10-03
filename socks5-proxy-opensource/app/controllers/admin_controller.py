#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import db
from app.models.user import User
from app.models.connection import Connection
from app.models.blacklist import BlacklistIP
from app.models.whitelist import WhitelistIP
from app.models.log_entry import LogEntry
from sqlalchemy import desc, func
import datetime


class AdminController:
    """
    管理控制器类，处理管理界面相关的业务逻辑
    """

    @staticmethod
    def get_dashboard_stats():
        """
        获取仪表盘统计数据
        
        返回:
            dict: 仪表盘统计数据
        """
        stats = {
            'active_connections': Connection.query.filter_by(status='CONNECTED').count(),
            'total_connections': Connection.query.count(),
            'blacklist_count': BlacklistIP.query.filter_by(is_active=True).count(),
            'whitelist_count': WhitelistIP.query.filter_by(is_active=True).count(),
            'user_count': User.query.count(),
            'recent_logs': LogEntry.query.order_by(desc(LogEntry.timestamp)).limit(10).all(),
            'recent_connections': Connection.query.order_by(desc(Connection.start_time)).limit(10).all()
        }

        # 计算今日连接数
        today = datetime.datetime.now().date()
        today_start = datetime.datetime.combine(today, datetime.time.min)
        today_end = datetime.datetime.combine(today, datetime.time.max)

        stats['today_connections'] = Connection.query.filter(
            Connection.start_time.between(today_start, today_end)
        ).count()

        # 计算今日总流量
        today_connections = Connection.query.filter(
            Connection.start_time.between(today_start, today_end)
        ).all()

        total_sent = sum(conn.bytes_sent for conn in today_connections)
        total_received = sum(conn.bytes_received for conn in today_connections)

        # 格式化流量
        def format_bytes(bytes_value):
            units = ['B', 'KB', 'MB', 'GB', 'TB']
            unit_index = 0
            size = float(bytes_value)

            while size >= 1024 and unit_index < len(units) - 1:
                size /= 1024
                unit_index += 1

            return f"{size:.2f} {units[unit_index]}"

        stats['today_traffic_sent'] = format_bytes(total_sent)
        stats['today_traffic_received'] = format_bytes(total_received)
        stats['today_traffic_total'] = format_bytes(total_sent + total_received)

        return stats

    @staticmethod
    def get_users(search_term=None, sort_by='username', sort_order='asc'):
        """
        获取用户列表
        
        参数:
            search_term (str, 可选): 搜索关键词
            sort_by (str, 可选): 排序字段
            sort_order (str, 可选): 排序顺序 ('asc' 或 'desc')
            
        返回:
            list: 用户列表
        """
        query = User.query

        # 搜索过滤
        if search_term:
            query = query.filter(
                (User.username.like(f'%{search_term}%')) |
                (User.email.like(f'%{search_term}%'))
            )

        # 排序
        if sort_by not in ['username', 'email', 'is_admin', 'is_active', 'created_at', 'last_login']:
            sort_by = 'username'

        column = getattr(User, sort_by)
        if sort_order == 'desc':
            query = query.order_by(desc(column))
        else:
            query = query.order_by(column)

        return query.all()

    @staticmethod
    def get_blacklist(search_term=None):
        """
        获取黑名单列表
        
        参数:
            search_term (str, 可选): 搜索关键词
            
        返回:
            list: 黑名单列表
        """
        query = BlacklistIP.query

        # 搜索过滤
        if search_term:
            query = query.filter(
                (BlacklistIP.ip_address.like(f'%{search_term}%')) |
                (BlacklistIP.description.like(f'%{search_term}%'))
            )

        return query.order_by(BlacklistIP.ip_address).all()

    @staticmethod
    def get_whitelist(search_term=None):
        """
        获取白名单列表
        
        参数:
            search_term (str, 可选): 搜索关键词
            
        返回:
            list: 白名单列表
        """
        query = WhitelistIP.query

        # 搜索过滤
        if search_term:
            query = query.filter(
                (WhitelistIP.ip_address.like(f'%{search_term}%')) |
                (WhitelistIP.description.like(f'%{search_term}%'))
            )

        return query.order_by(WhitelistIP.ip_address).all()

    @staticmethod
    def get_connections(status=None, sort_by='start_time', sort_order='desc'):
        """
        获取连接列表
        
        参数:
            status (str, 可选): 连接状态过滤
            sort_by (str, 可选): 排序字段
            sort_order (str, 可选): 排序顺序 ('asc' 或 'desc')
            
        返回:
            list: 连接列表
        """
        query = Connection.query

        # 状态过滤
        if status:
            query = query.filter_by(status=status)

        # 排序
        if sort_by not in ['id', 'client_addr', 'target_addr', 'status', 'start_time', 'end_time', 'bytes_sent',
                           'bytes_received']:
            sort_by = 'start_time'

        column = getattr(Connection, sort_by)
        if sort_order == 'desc':
            query = query.order_by(desc(column))
        else:
            query = query.order_by(column)

        return query.all()

    @staticmethod
    def get_active_connections():
        """
        获取活动连接列表
        
        返回:
            list: 活动连接列表
        """
        return Connection.query.filter_by(status='CONNECTED').order_by(desc(Connection.start_time)).all()

    @staticmethod
    def get_recent_closed_connections(limit=20):
        """
        获取最近关闭的连接列表
        
        参数:
            limit (int, 可选): 返回记录数量限制
            
        返回:
            list: 最近关闭的连接列表
        """
        return Connection.query.filter(
            Connection.status.in_(['CLOSED', 'ERROR'])
        ).order_by(desc(Connection.end_time)).limit(limit).all()

    @staticmethod
    def get_logs(level=None, client_ip=None, start_date=None, end_date=None, page=1, per_page=50):
        """
        获取日志列表
        
        参数:
            level (str, 可选): 日志级别过滤
            client_ip (str, 可选): 客户端IP过滤
            start_date (str, 可选): 开始日期过滤 (格式: 'YYYY-MM-DD')
            end_date (str, 可选): 结束日期过滤 (格式: 'YYYY-MM-DD')
            page (int, 可选): 页码
            per_page (int, 可选): 每页记录数
            
        返回:
            tuple: (日志分页对象, 总记录数)
        """
        query = LogEntry.query

        # 日志级别过滤
        if level:
            query = query.filter_by(level=level)

        # 客户端IP过滤
        if client_ip:
            query = query.filter_by(client_ip=client_ip)

        # 日期范围过滤
        if start_date:
            try:
                start_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(LogEntry.timestamp >= start_datetime)
            except ValueError:
                pass

        if end_date:
            try:
                end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                end_datetime = end_datetime + datetime.timedelta(days=1)  # 包含整个结束日期
                query = query.filter(LogEntry.timestamp <= end_datetime)
            except ValueError:
                pass

        # 排序并分页
        query = query.order_by(desc(LogEntry.timestamp))
        logs_pagination = query.paginate(page=page, per_page=per_page)

        return logs_pagination, query.count()

    @staticmethod
    def get_traffic_stats(days=7):
        """
        获取流量统计数据
        
        参数:
            days (int, 可选): 统计天数
            
        返回:
            dict: 流量统计数据
        """
        end_date = datetime.datetime.now().date()
        start_date = end_date - datetime.timedelta(days=days - 1)

        stats = {
            'labels': [],
            'sent': [],
            'received': []
        }

        # 逐日统计
        current_date = start_date
        while current_date <= end_date:
            day_start = datetime.datetime.combine(current_date, datetime.time.min)
            day_end = datetime.datetime.combine(current_date, datetime.time.max)

            # 当日发送流量
            day_sent = db.session.query(func.sum(Connection.bytes_sent)).filter(
                Connection.start_time.between(day_start, day_end)
            ).scalar() or 0

            # 当日接收流量
            day_received = db.session.query(func.sum(Connection.bytes_received)).filter(
                Connection.start_time.between(day_start, day_end)
            ).scalar() or 0

            stats['labels'].append(current_date.strftime('%m-%d'))
            stats['sent'].append(day_sent)
            stats['received'].append(day_received)

            current_date += datetime.timedelta(days=1)

        return stats
