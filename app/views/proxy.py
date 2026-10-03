#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
import importlib
import sys
import os
from app.models.log_entry import LogEntry
import logging
from app.models.scenario import Scenario

# 获取配置模块，确保它作为全局变量可用
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
try:
    config_module = importlib.import_module('config.config')
except ImportError:
    # 确保至少有一个备用配置，防止整个应用崩溃
    import types
    config_module = types.ModuleType('config')
    config_module.PROXY_HOST = '0.0.0.0'
    config_module.PROXY_PORT = 1080
    config_module.MAX_CONNECTIONS = 100
    config_module.BUFFER_SIZE = 4096
    config_module.PROXY_TIMEOUT = 60
    config_module.ENABLE_AUTH = True
    config_module.LOG_LEVEL = 'INFO'

# 创建蓝图
proxy_bp = Blueprint('proxy', __name__, url_prefix='/proxy')

@proxy_bp.before_request
def check_admin():
    """确保只有管理员才能访问代理配置页面"""
    if not current_user.is_authenticated or not current_user.is_admin:
        flash('您没有权限访问代理配置页面', 'danger')
        return redirect(url_for('auth.login'))

@proxy_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """代理设置视图，支持手动输入配置或直接应用某个“场景”配置。"""
    global config_module

    logger = logging.getLogger('socks5_proxy')

    # 1. 重新加载配置模块，保证拿到最新值
    try:
        if 'config.config' in sys.modules:
            config_module = importlib.reload(sys.modules['config.config'])
        else:
            config_module = importlib.import_module('config.config')
    except Exception as e:
        logger.error(f"重新加载配置模块时出错: {e}")

    # 2. 查询所有可用场景，用于在模板里渲染“选择场景”下拉框
    scenarios = Scenario.query.filter_by(is_active=True).order_by(Scenario.name).all()

    if request.method == 'POST':
        # 如果表单里传了 scenario_id，就应用场景；否则走手动更新
        chosen_id = request.form.get('scenario_id', type=int)
        if chosen_id:
            # --------- 应用某个已有场景 ------------
            scenario = Scenario.query.get(chosen_id)
            if not scenario:
                flash('未找到对应的场景，请刷新后重试。', 'warning')
                return redirect(url_for('proxy.settings'))

            try:
                config_file = os.path.abspath(
                    os.path.join(os.path.dirname(__file__), '../../config/config.py')
                )
                with open(config_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                with open(config_file, 'w', encoding='utf-8') as f:
                    for line in lines:
                        if line.startswith('PROXY_HOST'):
                            f.write(f"PROXY_HOST = '{scenario.proxy_host}'\n")
                        elif line.startswith('PROXY_PORT'):
                            f.write(f"PROXY_PORT = {scenario.port}\n")
                        elif line.startswith('MAX_CONNECTIONS'):
                            f.write(f"MAX_CONNECTIONS = {scenario.max_connections}\n")
                        elif line.startswith('BUFFER_SIZE'):
                            f.write(f"BUFFER_SIZE = {scenario.buffer_size}\n")
                        elif line.startswith('PROXY_TIMEOUT'):
                            f.write(f"PROXY_TIMEOUT = {scenario.proxy_timeout}\n")
                        elif line.startswith('ENABLE_AUTH'):
                            f.write(f"ENABLE_AUTH = {scenario.enable_auth}\n")
                        elif line.startswith('LOG_LEVEL'):
                            f.write(f"LOG_LEVEL = '{scenario.log_level}'\n")
                        else:
                            f.write(line)

                # 清理 import 缓存并重新加载
                for m in list(sys.modules.keys()):
                    if m.startswith('config.') or m == 'config':
                        sys.modules.pop(m, None)
                importlib.invalidate_caches()
                config_module = importlib.import_module('config.config')

                logger.info(f"管理员 {current_user.username} 应用场景 “{scenario.name}” (ID: {scenario.id})")
                LogEntry.info(
                    f"管理员 {current_user.username} 应用场景 “{scenario.name}” (ID: {scenario.id})",
                    client_ip=request.remote_addr,
                    user_id=current_user.id
                )

                flash(f"场景 “{scenario.name}” 已应用，请重启服务器以使改动生效。", 'success')

            except Exception as e:
                logger.error(f"应用场景时写配置文件出错: {e}")
                LogEntry.error(
                    f"应用场景时写配置文件出错: {e}",
                    client_ip=request.remote_addr,
                    user_id=current_user.id
                )
                flash(f"应用场景失败: {e}", 'danger')

            return redirect(url_for('proxy.settings'))

        # --------- 否则走手动更新逻辑 ------------
        proxy_host = request.form.get('proxy_host', '0.0.0.0')
        proxy_port = request.form.get('proxy_port', 1080)
        max_connections = request.form.get('max_connections', 100)
        buffer_size = request.form.get('buffer_size', 4096)
        proxy_timeout = request.form.get('proxy_timeout', 60)
        enable_auth = 'enable_auth' in request.form
        log_level = request.form.get('log_level', 'INFO')

        # 手动数值型字段验证
        try:
            proxy_port = int(proxy_port)
            max_connections = int(max_connections)
            buffer_size = int(buffer_size)
            proxy_timeout = int(proxy_timeout)
        except ValueError:
            flash('请输入有效的数值', 'danger')
            return render_template(
                'proxy/settings.html',
                config=config_module,
                scenarios=scenarios
            )

        # 写回 配置文件 config.py
        try:
            config_file = os.path.abspath(
                os.path.join(os.path.dirname(__file__), '../../config/config.py')
            )
            with open(config_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            with open(config_file, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.startswith('PROXY_HOST'):
                        f.write(f"PROXY_HOST = '{proxy_host}'\n")
                    elif line.startswith('PROXY_PORT'):
                        f.write(f"PROXY_PORT = {proxy_port}\n")
                    elif line.startswith('MAX_CONNECTIONS'):
                        f.write(f"MAX_CONNECTIONS = {max_connections}\n")
                    elif line.startswith('BUFFER_SIZE'):
                        f.write(f"BUFFER_SIZE = {buffer_size}\n")
                    elif line.startswith('PROXY_TIMEOUT'):
                        f.write(f"PROXY_TIMEOUT = {proxy_timeout}\n")
                    elif line.startswith('ENABLE_AUTH'):
                        f.write(f"ENABLE_AUTH = {enable_auth}\n")
                    elif line.startswith('LOG_LEVEL'):
                        f.write(f"LOG_LEVEL = '{log_level}'\n")
                    else:
                        f.write(line)

            # 清理缓存并重新加载
            for m in list(sys.modules.keys()):
                if m.startswith('config.') or m == 'config':
                    sys.modules.pop(m, None)
            importlib.invalidate_caches()
            config_module = importlib.import_module('config.config')

            logger.info(f"管理员 {current_user.username} 手动更新了代理配置")
            LogEntry.info(
                f"管理员 {current_user.username} 手动更新了代理配置",
                client_ip=request.remote_addr,
                user_id=current_user.id
            )

            flash('代理设置已更新。请重启服务器以应用更改。', 'success')
        except Exception as e:
            logger.error(f"更新配置文件时出错: {e}")
            LogEntry.error(
                f"更新配置文件时出错: {e}",
                client_ip=request.remote_addr,
                user_id=current_user.id
            )
            flash(f'更新配置文件时出错: {e}', 'danger')

        return redirect(url_for('proxy.settings'))

    # GET 请求：渲染模板时一并传入当前配置与“可用场景列表”
    return render_template(
        'proxy/settings.html',
        config=config_module,
        scenarios=scenarios
    )

@proxy_bp.route('/restart', methods=['GET', 'POST'])
@login_required
def restart():
    """重启代理服务器视图"""
    global config_module
    
    # 确保导入必要的模块
    import sys
    import os
    import time
    import importlib
    import logging
    
    # 将项目根目录添加到sys.path
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
    sys.path.append(root_path)
    
    # 彻底清除配置模块的缓存
    config_to_reload = ['config', 'config.config']
    for module_name in list(sys.modules.keys()):
        if module_name in config_to_reload or module_name.startswith('config.'):
            try:
                del sys.modules[module_name]
            except KeyError:
                pass
    
    # 清除路径缓存
    sys.path_importer_cache.clear()
    
    # 重新加载配置模块
    try:
        importlib.invalidate_caches()  # 使importlib刷新缓存
        config_module = importlib.import_module('config.config')  # 更新全局变量
        # 记录配置状态
        logger = logging.getLogger('socks5_proxy')
        logger.info(f"重启前的配置加载 - 认证状态: {'启用' if config_module.ENABLE_AUTH else '禁用'}")
    except Exception as e:
        LogEntry.error(f"重新加载配置模块时出错: {str(e)}",
                     client_ip=request.remote_addr,
                     user_id=current_user.id)
    
    # 然后请求重启代理服务器
    from run import request_restart
    
    LogEntry.info(f"管理员 {current_user.username} 请求重启代理服务器",
                 client_ip=request.remote_addr,
                 user_id=current_user.id)
    
    # 请求重启代理服务器
    request_restart()
    
    # 给一些时间让重启过程开始
    time.sleep(2)  # 增加等待时间，确保有足够时间处理重启
    
    flash('代理服务器正在重启。这可能需要几秒钟时间。', 'success')
    return redirect(url_for('admin.dashboard'))

@proxy_bp.route('/status')
@login_required
def status():
    """代理服务器状态视图，返回JSON格式的状态信息"""
    global config_module
    
    # 确保导入必要的模块
    import os
    import sys
    import importlib
    import logging
    
    # 默认配置值
    proxy_host = '0.0.0.0'
    proxy_port = 1080
    max_connections = 100
    enable_auth = False
    
    # 直接从文件读取配置，确保最新
    try:
        config_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../config/config.py'))
        with open(config_file, 'r', encoding='utf-8') as f:
            config_content = f.read()
            for line in config_content.splitlines():
                line = line.strip()
                if line.startswith('ENABLE_AUTH'):
                    value_str = line.split('=')[1].strip()
                    enable_auth = value_str.lower() == 'true'
                elif line.startswith('PROXY_HOST'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        proxy_host = value.strip("'\"")
                elif line.startswith('PROXY_PORT'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        try:
                            proxy_port = int(parts[1].strip())
                        except ValueError:
                            pass
                elif line.startswith('MAX_CONNECTIONS'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        try:
                            max_connections = int(parts[1].strip())
                        except ValueError:
                            pass
        
        logger = logging.getLogger('socks5_proxy')
        logger.info(f"从文件读取的认证设置: {enable_auth}")
    except Exception as e:
        # 如果读取失败，退回到使用配置模块
        logger = logging.getLogger('socks5_proxy')
        logger.error(f"直接读取配置失败: {str(e)}")
        try:
            if 'config.config' in sys.modules:
                config_module = importlib.reload(sys.modules['config.config'])
            else:
                config_module = importlib.import_module('config.config')
            enable_auth = config_module.ENABLE_AUTH
            proxy_host = config_module.PROXY_HOST
            proxy_port = config_module.PROXY_PORT
            max_connections = config_module.MAX_CONNECTIONS
        except Exception as e2:
            logger.error(f"加载配置模块失败: {str(e2)}")
            
    # 导入全局代理服务器实例
    # 将项目根目录添加到sys.path
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
    try:
        from run import proxy_server
    except Exception as e:
        logger.error(f"导入proxy_server失败: {str(e)}")
        proxy_server = None
    
    # 如果代理服务器尚未启动或已停止
    running = False
    host = proxy_host
    port = proxy_port
    
    # 如果代理服务器实例存在
    if proxy_server is not None:
        running = proxy_server.running
        host = proxy_server.host
        port = proxy_server.port
        # 更新代理服务器的认证设置
        proxy_server.enable_auth = enable_auth
    
    # 计算当前连接数
    try:
        from app.models.connection import Connection
        active_connections = Connection.query.filter_by(status='CONNECTED').count()
    except Exception as e:
        logger.error(f"查询连接数失败: {str(e)}")
        active_connections = 0
    
    # 返回状态信息
    status_info = {
        'running': running,
        'host': host,
        'port': port,
        'active_connections': active_connections,
        'max_connections': max_connections,
        'enable_auth': enable_auth
    }
    
    return jsonify(status_info) 