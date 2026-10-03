#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import db
from app.models.user import User
from app.models.log_entry import LogEntry
from datetime import datetime


class AuthController:
    """
    认证控制器类，处理用户身份验证相关的业务逻辑
    """

    @staticmethod
    def authenticate(username, password):
        """
        验证用户登录凭据

        参数:
            username (str): 用户名
            password (str): 密码

        返回:
            User或None: 如果验证成功返回用户对象，否则返回None
        """
        user = User.query.filter_by(username=username).first()

        if user is None or not user.verify_password(password):
            return None

        # 更新最后登录时间
        user.last_login = datetime.utcnow()
        db.session.commit()

        return user

    @staticmethod
    def register_user(username, password, email=None, is_admin=False, created_by=None):
        """
        注册新用户

        参数:
            username (str): 用户名
            password (str): 密码
            email (str, 可选): 电子邮箱
            is_admin (bool, 可选): 是否为管理员
            created_by (int, 可选): 创建者的用户ID

        返回:
            tuple: (User对象, 错误消息) - 如果成功，错误消息为None
        """
        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            return None, "用户名已存在"

        # 检查邮箱是否已存在
        if email and User.query.filter_by(email=email).first():
            return None, "邮箱已被使用"

        # 创建新用户
        new_user = User(username=username, password=password, email=email, is_admin=is_admin)

        try:
            db.session.add(new_user)
            db.session.commit()

            # 记录日志
            creator = "系统" if created_by is None else User.query.get(created_by).username
            LogEntry.info(f"用户 {username} 被 {creator} 创建",
                          user_id=new_user.id)

            return new_user, None
        except Exception as e:
            db.session.rollback()
            return None, f"创建用户时出错: {str(e)}"

    @staticmethod
    def update_user(user_id, username=None, email=None, password=None,
                    is_admin=None, is_active=None, updated_by=None):
        """
        更新用户信息

        参数:
            user_id (int): 用户ID
            username (str, 可选): 新用户名
            email (str, 可选): 新电子邮箱
            password (str, 可选): 新密码
            is_admin (bool, 可选): 是否为管理员
            is_active (bool, 可选): 是否激活
            updated_by (int, 可选): 更新者的用户ID

        返回:
            tuple: (User对象, 错误消息) - 如果成功，错误消息为None
        """
        user = User.query.get(user_id)
        if not user:
            return None, "用户不存在"

        # 检查新用户名是否与其他用户冲突
        if username and username != user.username:
            if User.query.filter(User.username == username, User.id != user_id).first():
                return None, "用户名已被使用"

            old_username = user.username
            user.username = username

        # 检查新邮箱是否与其他用户冲突
        if email and email != user.email:
            if email and User.query.filter(User.email == email, User.id != user_id).first():
                return None, "邮箱已被使用"

            user.email = email

        # 更新密码
        if password:
            user.set_password(password)

        # 更新管理员状态
        if is_admin is not None:
            user.is_admin = is_admin

        # 更新活动状态
        if is_active is not None:
            user.is_active = is_active

        try:
            db.session.commit()

            # 记录日志
            changes = []
            if username and username != old_username:
                changes.append(f"用户名从 {old_username} 改为 {username}")
            if password:
                changes.append("密码已更改")
            if email and email != user.email:
                changes.append("邮箱已更改")
            if is_admin is not None:
                changes.append(f"管理员状态改为 {is_admin}")
            if is_active is not None:
                changes.append(f"活动状态改为 {is_active}")

            if changes and updated_by:
                updater = User.query.get(updated_by)
                if updater:
                    changes_str = ", ".join(changes)
                    LogEntry.info(f"用户 {user.username} 的信息被 {updater.username} 更新: {changes_str}",
                                  user_id=user.id)

            return user, None
        except Exception as e:
            db.session.rollback()
            return None, f"更新用户信息时出错: {str(e)}"

    @staticmethod
    def delete_user(user_id, deleted_by=None):
        """
        删除用户

        参数:
            user_id (int): 要删除的用户ID
            deleted_by (int, 可选): 执行删除操作的用户ID

        返回:
            tuple: (bool, 错误消息) - 如果成功，返回(True, None)
        """
        user = User.query.get(user_id)
        if not user:
            return False, "用户不存在"

        # 不允许删除自己
        if deleted_by and user_id == deleted_by:
            return False, "不能删除自己的账户"

        username = user.username

        try:
            db.session.delete(user)
            db.session.commit()

            # 记录日志
            if deleted_by:
                deleter = User.query.get(deleted_by)
                if deleter:
                    LogEntry.info(f"用户 {username} 被 {deleter.username} 删除",
                                  user_id=deleted_by)

            return True, None
        except Exception as e:
            db.session.rollback()
            return False, f"删除用户时出错: {str(e)}"

    @staticmethod
    def verify_credentials(username, password):
        """
        验证用户凭据（用于Socks5代理认证）

        参数:
            username (str): 用户名
            password (str): 密码

        返回:
            bool: 验证是否成功
        """
        user = User.query.filter_by(username=username).first()

        if not user:
            return False

        # 验证密码并检查用户是否激活
        if user.is_active and user.verify_password(password):
            return True

        return False