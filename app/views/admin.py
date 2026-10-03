#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.blacklist import BlacklistIP
from app.models.whitelist import WhitelistIP
from app.models.connection import Connection
from app.models.log_entry import LogEntry
from sqlalchemy import desc
from app.models.scenario import Scenario

import datetime
import ipaddress

# 导入新表单类
from app.controllers.forms import UserForm, BlacklistForm, WhitelistForm, ScenarioForm

# 创建蓝图
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
def check_admin():
    """确保只有管理员才能访问管理界面"""
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('您没有权限访问管理页面', 'danger')
        return redirect(url_for('auth.login'))

def validate_ip_or_cidr(value: str) -> bool:
    """
    校验一个字符串是否是合法的 IPv4/IPv6 地址或者合法的 CIDR 网络段。
    返回 True 表示合法，False 表示不合法。
    """
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        pass

    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False

@admin_bp.route('/')
@login_required
def dashboard():
    """管理员仪表盘视图"""
    stats = {
        'active_connections': Connection.query.filter_by(status='CONNECTED').count(),
        'total_connections': Connection.query.count(),
        'blacklist_count': BlacklistIP.query.filter_by(is_active=True).count(),
        'whitelist_count': WhitelistIP.query.filter_by(is_active=True).count(),
        'user_count': User.query.count(),
        'recent_logs': LogEntry.query.order_by(desc(LogEntry.timestamp)).limit(10).all()
    }
    recent_connections = Connection.query.order_by(desc(Connection.start_time)).limit(10).all()
    return render_template('admin/dashboard.html', stats=stats, recent_connections=recent_connections)

@admin_bp.route('/users')
@login_required
def user_list():
    """用户列表视图"""
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@login_required
def add_user():
    """添加用户视图"""
    form = UserForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        raw_email = form.email.data.strip() if form.email.data else ''
        is_admin = form.is_admin.data
        is_active = form.is_active.data

        if not username or not password:
            flash('用户名和密码为必填项', 'danger')
            return render_template('admin/add_user.html', form=form)

        email = raw_email if raw_email else None

        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return render_template('admin/add_user.html', form=form)

        if email and User.query.filter_by(email=email).first():
            flash('邮箱已被其他用户使用', 'danger')
            return render_template('admin/add_user.html', form=form)

        user = User(username=username, password=password, email=email, is_admin=is_admin, is_active=is_active)
        db.session.add(user)
        try:
            db.session.commit()
            LogEntry.info(f"管理员 {current_user.username} 添加了用户 {username}",
                          client_ip=request.remote_addr,
                          user_id=current_user.id)
            flash(f'用户 {username} 创建成功', 'success')
            return redirect(url_for('admin.user_list'))
        except Exception as e:
            db.session.rollback()
            flash('插入数据库时发生错误，请检查输入或稍后重试', 'danger')
            return render_template('admin/add_user.html', form=form)

    return render_template('admin/add_user.html', form=form)

@admin_bp.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """编辑用户视图"""
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)  # 用 obj 参数预填充表单

    if form.validate_on_submit():
        new_username = form.username.data.strip()
        new_email = form.email.data.strip() if form.email.data else None
        new_password = form.password.data
        is_admin = form.is_admin.data
        is_active = form.is_active.data

        if new_username != user.username and User.query.filter_by(username=new_username).first():
            flash('用户名已存在', 'danger')
            return render_template('admin/edit_user.html', form=form, user=user)

        user.username = new_username
        user.email = new_email
        if new_password:
            user.set_password(new_password)
        user.is_admin = is_admin
        user.is_active = is_active

        db.session.commit()
        LogEntry.info(f"管理员 {current_user.username} 更新了用户 {new_username} 的信息",
                      client_ip=request.remote_addr,
                      user_id=current_user.id)
        flash(f'用户 {new_username} 信息已更新', 'success')
        return redirect(url_for('admin.user_list'))

    return render_template('admin/edit_user.html', form=form, user=user)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    """删除用户视图（改为只接受 POST）"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('不能删除当前登录的用户', 'danger')
        return redirect(url_for('admin.user_list'))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    LogEntry.info(f"管理员 {current_user.username} 删除了用户 {username}",
                  client_ip=request.remote_addr,
                  user_id=current_user.id)
    flash(f'用户 {username} 已删除', 'success')
    return redirect(url_for('admin.user_list'))

@admin_bp.route('/blacklist')
@login_required
def blacklist():
    """黑名单管理视图"""
    blacklist_ips = BlacklistIP.query.order_by(BlacklistIP.id.desc()).all()
    return render_template('admin/blacklist.html', blacklist_ips=blacklist_ips)

@admin_bp.route('/blacklist/add', methods=['GET', 'POST'])
@login_required
def add_blacklist():
    """添加黑名单项视图"""
    form = BlacklistForm()
    if form.validate_on_submit():
        ip_address = form.ip_address.data.strip()
        description = form.description.data.strip()

        if not validate_ip_or_cidr(ip_address):
            flash('请输入合法的 IPv4/IPv6 地址或 CIDR（如 192.168.1.0/24）', 'danger')
            return render_template('admin/add_blacklist.html', form=form)

        if BlacklistIP.query.filter_by(ip_address=ip_address).first():
            flash(f'IP 或网段 {ip_address} 已在黑名单中', 'warning')
            return render_template('admin/add_blacklist.html', form=form)

        blacklist_ip = BlacklistIP(
            ip_address=ip_address,
            description=description,
            created_by=current_user.id
        )
        db.session.add(blacklist_ip)
        db.session.commit()

        LogEntry.info(f"管理员 {current_user.username} 添加了黑名单IP {ip_address}",
                      client_ip=request.remote_addr,
                      user_id=current_user.id)

        flash(f'IP 或网段 {ip_address} 已添加到黑名单', 'success')
        return redirect(url_for('admin.blacklist'))

    return render_template('admin/add_blacklist.html', form=form)

@admin_bp.route('/blacklist/delete/<int:blacklist_id>', methods=['POST'])
@login_required
def delete_blacklist(blacklist_id):
    """删除黑名单项视图"""
    blacklist_ip = BlacklistIP.query.get_or_404(blacklist_id)
    ip_address = blacklist_ip.ip_address

    db.session.delete(blacklist_ip)
    db.session.commit()

    LogEntry.info(f"管理员 {current_user.username} 删除了黑名单IP {ip_address}",
                  client_ip=request.remote_addr,
                  user_id=current_user.id)

    flash(f'IP 或网段 {ip_address} 已从黑名单中删除', 'success')
    return redirect(url_for('admin.blacklist'))

@admin_bp.route('/whitelist')
@login_required
def whitelist():
    """白名单管理视图"""
    whitelist_ips = WhitelistIP.query.order_by(WhitelistIP.id.desc()).all()
    return render_template('admin/whitelist.html', whitelist_ips=whitelist_ips)

@admin_bp.route('/whitelist/add', methods=['GET', 'POST'])
@login_required
def add_whitelist():
    """添加白名单项视图"""
    form = WhitelistForm()
    if form.validate_on_submit():
        ip_address = form.ip_address.data.strip()
        description = form.description.data.strip()

        if not validate_ip_or_cidr(ip_address):
            flash('请输入合法的 IPv4/IPv6 地址或 CIDR（如 10.0.0.0/8）', 'danger')
            return render_template('admin/add_whitelist.html', form=form)

        if WhitelistIP.query.filter_by(ip_address=ip_address).first():
            flash(f'IP 或网段 {ip_address} 已在白名单中', 'warning')
            return render_template('admin/add_whitelist.html', form=form)

        whitelist_ip = WhitelistIP(
            ip_address=ip_address,
            description=description,
            created_by=current_user.id
        )
        db.session.add(whitelist_ip)
        db.session.commit()

        LogEntry.info(f"管理员 {current_user.username} 添加了白名单IP {ip_address}",
                      client_ip=request.remote_addr,
                      user_id=current_user.id)

        flash(f'IP 或网段 {ip_address} 已添加到白名单', 'success')
        return redirect(url_for('admin.whitelist'))

    return render_template('admin/add_whitelist.html', form=form)

@admin_bp.route('/whitelist/delete/<int:whitelist_id>', methods=['POST'])
@login_required
def delete_whitelist(whitelist_id):
    """删除白名单项视图"""
    whitelist_ip = WhitelistIP.query.get_or_404(whitelist_id)
    ip_address = whitelist_ip.ip_address

    db.session.delete(whitelist_ip)
    db.session.commit()

    LogEntry.info(f"管理员 {current_user.username} 删除了白名单IP {ip_address}",
                  client_ip=request.remote_addr,
                  user_id=current_user.id)

    flash(f'IP 或网段 {ip_address} 已从白名单中删除', 'success')
    return redirect(url_for('admin.whitelist'))

@admin_bp.route('/connections')
@login_required
def connections():
    """连接管理视图"""
    active_connections = Connection.query.filter_by(status='CONNECTED').all()
    recent_closed = Connection.query.filter(Connection.status.in_(['CLOSED', 'ERROR'])) \
                             .order_by(desc(Connection.end_time)) \
                             .limit(20) \
                             .all()
    for conn in recent_closed:
        if conn.end_time is None:
            conn.end_time = conn.start_time
    return render_template('admin/connections.html',
                          active_connections=active_connections,
                          recent_closed=recent_closed)

@admin_bp.route('/connections/close/<int:connection_id>', methods=['POST'])
@login_required
def close_connection(connection_id):
    """关闭连接视图（改为 POST）"""
    connection = Connection.query.get_or_404(connection_id)
    if connection.status != 'CONNECTED':
        flash('只能关闭活动连接', 'danger')
        return redirect(url_for('admin.connections'))

    connection.close()
    LogEntry.info(f"管理员 {current_user.username} 手动关闭了连接 {connection_id}",
                  client_ip=request.remote_addr,
                  user_id=current_user.id,
                  connection_id=connection_id)

    flash(f'连接 {connection_id} 已关闭', 'success')
    return redirect(url_for('admin.connections'))

@admin_bp.route('/logs')
@login_required
def logs():
    """日志管理视图"""
    page = request.args.get('page', 1, type=int)
    per_page = 50

    level = request.args.get('level')
    client_ip = request.args.get('client_ip')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = LogEntry.query

    if level:
        query = query.filter_by(level=level)
    if client_ip:
        query = query.filter_by(client_ip=client_ip)
    if start_date:
        try:
            start_datetime = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(LogEntry.timestamp >= start_datetime)
        except ValueError:
            pass
    if end_date:
        try:
            end_datetime = datetime.datetime.strptime(end_date, '%Y-%m-%d') + datetime.timedelta(days=1)
            query = query.filter(LogEntry.timestamp <= end_datetime)
        except ValueError:
            pass

    logs_pagination = query.order_by(desc(LogEntry.timestamp)).paginate(page=page, per_page=per_page)
    return render_template('admin/logs.html', logs_pagination=logs_pagination,
                          level=level, client_ip=client_ip,
                          start_date=start_date, end_date=end_date)

@admin_bp.route('/scenarios', methods=['GET'])
@login_required
def scenario_list():
    """显示所有场景，并提供“新增”“编辑”“删除”按钮。"""
    scenarios = Scenario.query.order_by(Scenario.name).all()
    return render_template('scenario/list.html', scenarios=scenarios)

@admin_bp.route('/scenarios/add', methods=['GET', 'POST'])
@login_required
def scenario_add():
    """新增一个场景。"""
    form = ScenarioForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        description = form.description.data.strip()
        proxy_host = form.proxy_host.data or '0.0.0.0'
        port = form.port.data or 1080
        max_connections = form.max_connections.data or 100
        buffer_size = form.buffer_size.data or 4096
        proxy_timeout = form.proxy_timeout.data or 60
        log_level = form.log_level.data or 'INFO'
        enable_auth = form.enable_auth.data
        is_active = form.is_active.data

        if Scenario.query.filter_by(name=name).first():
            flash('场景名称已存在', 'danger')
            return render_template('scenario/form.html', form=form, action='add', scenario=None)

        sc = Scenario(
            name=name,
            description=description,
            proxy_host=proxy_host,
            port=port,
            max_connections=max_connections,
            buffer_size=buffer_size,
            proxy_timeout=proxy_timeout,
            log_level=log_level,
            enable_auth=enable_auth,
            is_active=is_active
        )
        db.session.add(sc)
        db.session.commit()
        LogEntry.info(f"管理员 {current_user.username} 添加了场景 {name}",
                      client_ip=request.remote_addr,
                      user_id=current_user.id)
        flash('场景创建成功', 'success')
        return redirect(url_for('admin.scenario_list'))

    return render_template('scenario/form.html', form=form, action='add', scenario=None)

@admin_bp.route('/scenarios/edit/<int:sc_id>', methods=['GET', 'POST'])
@login_required
def scenario_edit(sc_id):
    """编辑某个已有场景。"""
    sc = Scenario.query.get_or_404(sc_id)
    form = ScenarioForm(obj=sc)

    if form.validate_on_submit():
        new_name = form.name.data.strip()
        sc.description = form.description.data.strip()
        sc.proxy_host = form.proxy_host.data or sc.proxy_host
        sc.port = form.port.data or sc.port
        sc.max_connections = form.max_connections.data or sc.max_connections
        sc.buffer_size = form.buffer_size.data or sc.buffer_size
        sc.proxy_timeout = form.proxy_timeout.data or sc.proxy_timeout
        sc.log_level = form.log_level.data or sc.log_level
        sc.enable_auth = form.enable_auth.data
        sc.is_active = form.is_active.data

        existing = Scenario.query.filter_by(name=new_name).first()
        if existing and existing.id != sc.id:
            flash('场景名称已存在，请更换', 'danger')
            return render_template('scenario/form.html', form=form, action='edit', scenario=sc)

        sc.name = new_name
        db.session.commit()
        LogEntry.info(f"管理员 {current_user.username} 更新了场景 {new_name}",
                      client_ip=request.remote_addr,
                      user_id=current_user.id)
        flash('场景更新成功', 'success')
        return redirect(url_for('admin.scenario_list'))

    return render_template('scenario/form.html', form=form, action='edit', scenario=sc)

@admin_bp.route('/scenarios/delete/<int:sc_id>', methods=['POST'])
@login_required
def scenario_delete(sc_id):
    """删除某个场景（物理删除或逻辑删除，根据需求）。"""
    sc = Scenario.query.get_or_404(sc_id)
    db.session.delete(sc)
    db.session.commit()
    LogEntry.info(f"管理员 {current_user.username} 删除了场景 {sc.name}",
                  client_ip=request.remote_addr,
                  user_id=current_user.id)
    flash('场景已删除', 'success')
    return redirect(url_for('admin.scenario_list'))
