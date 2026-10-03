#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import create_app
from app.models.proxy_server import ProxyServer
from app.models.log_entry import LogEntry
import threading
import logging
import time
import importlib
import sys
import os

# 创建应用实例
app = create_app()
logger = logging.getLogger('socks5_proxy')

# 创建全局代理服务器实例和状态控制
proxy_server = None
restart_event = threading.Event()
proxy_thread = None

def start_proxy_server():
    """启动代理服务器"""
    global proxy_server, restart_event
    
    while True:
        try:
            with app.app_context():
                # 先清理旧的代理服务器实例（如果存在）
                if proxy_server is not None:
                    if proxy_server.running:
                        logger.info("正在停止现有代理服务器实例...")
                        try:
                            proxy_server.stop()
                            time.sleep(1)  # 给一些时间清理资源
                            logger.info("现有代理服务器实例已停止")
                            # 释放旧实例的引用
                            proxy_server = None
                            # 强制垃圾回收
                            import gc
                            gc.collect()
                        except Exception as e:
                            logger.error(f"停止现有代理服务器实例时出错: {str(e)}")
                
                # 如果是重启操作，先尝试重新加载配置模块
                if restart_event.is_set():
                    try:
                        # 重新加载配置模块，确保获取最新的配置
                        config_module = sys.modules.get('config.config')
                        if config_module:
                            importlib.reload(config_module)
                            logger.info("配置模块已重新加载")
                            # 输出认证模式状态，用于调试
                            logger.info(f"当前认证模式: {'启用' if config_module.ENABLE_AUTH else '禁用'}")
                    except Exception as e:
                        logger.error(f"重新加载配置模块时出错: {str(e)}")
                
                # 在Flask应用上下文中启动代理服务器
                logger.info("正在启动代理服务器...")
                try:
                    LogEntry.info("正在启动代理服务器...")
                except Exception as log_err:
                    logger.error(f"日志记录失败: {str(log_err)}")
                
                # 确保在创建新实例前从磁盘重新加载最新配置
                try:
                    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'config/config.py'))
                    
                    # 直接读取文件而不是使用importlib
                    enable_auth = False  # 默认值
                    
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_content = f.read()
                        # 解析ENABLE_AUTH设置
                        for line in config_content.splitlines():
                            if line.strip().startswith('ENABLE_AUTH'):
                                value_str = line.split('=')[1].strip()
                                enable_auth = value_str.lower() == 'true'
                                break
                    
                    logger.info(f"直接从磁盘加载了最新配置 - 认证模式: {'启用' if enable_auth else '禁用'}")
                except Exception as e:
                    logger.error(f"重新加载配置文件时出错: {str(e)}")
                    
                # 重新创建代理服务器实例（会重新加载配置）
                proxy_server = ProxyServer()
                logger.info(f"新的代理服务器实例已创建 - 认证状态: {'启用' if proxy_server.enable_auth else '禁用'}")
                proxy_server.start()
                
                # 如果程序没有被要求重启，那么就退出循环
                if not restart_event.is_set():
                    break
                
                # 重置重启标志，准备下一次潜在的重启
                restart_event.clear()
                
        except Exception as e:
            logger.critical(f"代理服务器线程异常: {str(e)}")
            try:
                with app.app_context():
                    LogEntry.critical(f"代理服务器线程异常: {str(e)}")
            except Exception:
                pass
            # 如果出错，等待一段时间后重试，除非被要求退出
            time.sleep(5)
            if not restart_event.is_set():
                break

def request_restart():
    """请求重启代理服务器"""
    global restart_event, proxy_server
    
    # 记录重启请求
    logger.info("收到重启代理服务器请求")
    
    try:
        # 直接从文件读取认证状态
        config_file = os.path.abspath(os.path.join(os.path.dirname(__file__), 'config/config.py'))
        with open(config_file, 'r', encoding='utf-8') as f:
            config_content = f.read()
            for line in config_content.splitlines():
                if line.strip().startswith('ENABLE_AUTH'):
                    value_str = line.split('=')[1].strip()
                    enable_auth = value_str.lower() == 'true'
                    logger.info(f"配置文件中的认证设置: {enable_auth}")
                    break
    except Exception as e:
        logger.error(f"直接读取配置文件失败: {str(e)}")
    
    # 先尝试清除模块缓存并重新加载配置
    try:
        # 清除可能存在的模块缓存
        sys.path_importer_cache.clear()
        if 'config.config' in sys.modules:
            del sys.modules['config.config']
            # 重新导入以获取最新配置
            new_config = importlib.import_module('config.config')
            logger.info(f"重新加载的配置模块认证设置: {new_config.ENABLE_AUTH}")
    except Exception as e:
        logger.error(f"重启前清除配置模块缓存时出错: {str(e)}")
    
    # 如果有活动的代理服务器，强制关闭所有连接
    if proxy_server is not None and proxy_server.running:
        try:
            # 记录当前连接数量
            connection_count = len(proxy_server.connections)
            logger.info(f"准备关闭 {connection_count} 个活动连接")
            
            # 打印当前代理服务器的认证设置
            logger.info(f"当前代理服务器认证设置: {proxy_server.enable_auth}")
            
            # 强制关闭所有连接
            proxy_server.stop()
            logger.info("已关闭所有连接，等待Socket资源释放")
            
            # 给一些时间让资源完全释放
            time.sleep(2)
        except Exception as e:
            logger.error(f"关闭连接时出错: {str(e)}")
    
    # 设置重启标志
    restart_event.set()
    logger.info("已设置重启标志，等待重启过程开始")

if __name__ == '__main__':
    # 启动Socks5代理服务器
    proxy_thread = threading.Thread(target=start_proxy_server)
    proxy_thread.daemon = True
    proxy_thread.start()
    
    # 启动Web管理界面（生产环境请使用 gunicorn/uwsgi 等 WSGI 服务器）
    app.run(host='0.0.0.0', port=5000, debug=False)