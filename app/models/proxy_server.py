#!/usr/bin/env python
# -*- coding: utf-8 -*-

import socket
import select
import struct
import threading
import logging
import time
import sys
import os
import importlib.util
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import queue
import ipaddress

from app.models.connection import Connection
from app.models.blacklist import BlacklistIP
from app.models.whitelist import WhitelistIP
from app.models.log_entry import LogEntry
from config.config import get_local_time

# 确保重新加载配置文件
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../config/config.py'))
spec = importlib.util.spec_from_file_location("config", config_path)
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)

# 手动定义超时常量，防止配置加载问题
CONNECTION_TIMEOUT = getattr(config, 'CONNECTION_TIMEOUT', 30)
DATA_TRANSFER_TIMEOUT = getattr(config, 'DATA_TRANSFER_TIMEOUT', 5)

# 设置日志
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL), 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=config.LOG_FILE
)
logger = logging.getLogger('socks5_proxy')

# 创建独立的数据库引擎和会话工厂，避免与Flask应用共享会话
_engine = create_engine(config.SQLALCHEMY_DATABASE_URI)
_SessionFactory = sessionmaker(bind=_engine)
Session = scoped_session(_SessionFactory)

# SOCKS5协议常量
SOCKS_VERSION = 5  # SOCKS5协议版本号

# 认证方法
AUTH_METHODS = {
    0x00: 'NO_AUTH',
    0x02: 'USERNAME_PASSWORD'
}

# 命令类型
CMD_CONNECT = 0x01
CMD_BIND = 0x02
CMD_UDP_ASSOCIATE = 0x03

# 地址类型
ADDR_TYPE_IPV4 = 0x01
ADDR_TYPE_DOMAIN = 0x03
ADDR_TYPE_IPV6 = 0x04

# 响应码
REP_SUCCESS = 0x00
REP_SERVER_FAILURE = 0x01
REP_CONNECTION_REFUSED = 0x05
REP_COMMAND_NOT_SUPPORTED = 0x07

# 定义数据库操作队列和处理线程
db_queue = queue.Queue()

def db_worker():
    """数据库操作工作线程，从队列中获取任务并执行"""
    while True:
        task = db_queue.get()
        if task is None:  # 终止信号
            break
            
        action, kwargs = task
        
        try:
            session = Session()
            if action == 'update_connection':
                _perform_update_connection(session, **kwargs)
            elif action == 'log_entry':
                _perform_log_entry(session, **kwargs)
            elif action == 'create_connection':
                conn_id = _perform_create_connection(session, **kwargs)
                kwargs['callback'](conn_id)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"数据库操作失败: {str(e)}")
        finally:
            session.close()
            db_queue.task_done()

def _perform_update_connection(session, connection_id, target_addr=None, target_port=None, 
                               status=None, error=None, bytes_sent=0, bytes_received=0, user_id=None):
    """执行连接更新操作"""
    connection = session.query(Connection).get(connection_id)
    if connection:
        if target_addr and target_port:
            connection.target_addr = target_addr
            connection.target_port = target_port
            connection.status = 'CONNECTED'
        if status:
            connection.status = status
        if error:
            connection.error = error
        if bytes_sent > 0:
            connection.bytes_sent += bytes_sent
        if bytes_received > 0:
            connection.bytes_received += bytes_received
        if user_id is not None:
            connection.user_id = user_id
        if status == 'CLOSED' or status == 'ERROR':
            connection.end_time = get_local_time()

def _perform_log_entry(session, level, message, **kwargs):
    """执行日志记录操作"""
    # 修正参数名称，确保与LogEntry类定义兼容
    if 'target_addr' in kwargs:
        kwargs['target_host'] = kwargs.pop('target_addr')
        
    # 移除username参数，该参数不被LogEntry接受
    if 'username' in kwargs:
        # 如果有username但没有user_id，可以尝试查找用户ID
        if 'user_id' not in kwargs:
            try:
                from app.models.user import User
                user = session.query(User).filter_by(username=kwargs['username']).first()
                if user:
                    kwargs['user_id'] = user.id
            except Exception:
                pass
        # 移除username参数
        kwargs.pop('username')
        
    log_entry = LogEntry(level=level, message=message, **kwargs)
    session.add(log_entry)

def _perform_create_connection(session, client_addr, client_port, callback=None):
    """创建新连接记录并返回ID"""
    connection = Connection(client_addr, client_port)
    connection.start_time = get_local_time()  # 显式设置开始时间，确保时区正确
    session.add(connection)
    session.flush()  # 获取ID但不提交
    conn_id = connection.id
    if callback:
        callback(conn_id)
    return conn_id

# 启动数据库工作线程
db_thread = threading.Thread(target=db_worker)
db_thread.daemon = True
db_thread.start()

class ProxyServer:
    """Socks5代理服务器实现"""
    
    def __init__(self, host=None, port=None):
        """初始化Socks5代理服务器
        
        Args:
            host: 监听地址，默认使用配置文件中的PROXY_HOST
            port: 监听端口，默认使用配置文件中的PROXY_PORT
        """
        # 确保每次创建实例时重新加载最新配置
        import sys
        import os
        
        # 直接从磁盘读取配置文件
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../config/config.py'))
        
        # 默认配置值
        proxy_host = '0.0.0.0'
        proxy_port = 1080
        max_connections = 100
        buffer_size = 4096
        enable_auth = False
        
        # 读取配置文件
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
                # 解析配置文件
                for line in config_content.splitlines():
                    line = line.strip()
                    if line.startswith('PROXY_HOST'):
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
                    elif line.startswith('BUFFER_SIZE'):
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            try:
                                buffer_size = int(parts[1].strip())
                            except ValueError:
                                pass
                    elif line.startswith('ENABLE_AUTH'):
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            value_str = parts[1].strip()
                            enable_auth = value_str.lower() == 'true'
            
            # 创建一个简单的配置对象
            class Config:
                pass
            
            self.config = Config()
            self.config.PROXY_HOST = proxy_host
            self.config.PROXY_PORT = proxy_port
            self.config.MAX_CONNECTIONS = max_connections
            self.config.BUFFER_SIZE = buffer_size
            self.config.ENABLE_AUTH = enable_auth
            
            # 调试日志
            import logging
            logger = logging.getLogger('socks5_proxy')
            logger.info(f"配置已直接从磁盘加载 - 认证状态: {'启用' if enable_auth else '禁用'}")
        except Exception as e:
            # 读取配置失败时使用默认值
            import logging
            logger = logging.getLogger('socks5_proxy')
            logger.error(f"读取配置文件失败，将使用默认值: {str(e)}")
            
            # 创建默认配置对象
            class Config:
                pass
            
            self.config = Config()
            self.config.PROXY_HOST = proxy_host
            self.config.PROXY_PORT = proxy_port
            self.config.MAX_CONNECTIONS = max_connections
            self.config.BUFFER_SIZE = buffer_size
            self.config.ENABLE_AUTH = enable_auth
        
        # 使用最新的配置
        self.host = host or self.config.PROXY_HOST
        self.port = port or self.config.PROXY_PORT
        self.socket = None
        self.running = False
        self.connections = {}  # 活动连接字典
        self.lock = threading.Lock()
        # 确保从最新配置中读取认证设置
        self.enable_auth = self.config.ENABLE_AUTH
        
        # 更新日志记录
        logger.info(f"代理服务器已初始化 - 认证状态: {'启用' if self.enable_auth else '禁用'}")
    
    def _add_db_task(self, action, **kwargs):
        """添加数据库任务到队列"""
        db_queue.put((action, kwargs))
    
    def _update_connection_status(self, connection_id, target_addr=None, target_port=None, 
                                 status=None, error=None, bytes_sent=0, bytes_received=0, user_id=None):
        """更新连接状态（异步）"""
        self._add_db_task('update_connection', connection_id=connection_id,
                        target_addr=target_addr, target_port=target_port,
                        status=status, error=error,
                        bytes_sent=bytes_sent, bytes_received=bytes_received,
                        user_id=user_id)
    
    def _log_entry(self, level, message, **kwargs):
        """记录日志条目（异步）"""
        try:
            # 修正参数名称，确保与LogEntry类定义兼容
            if 'target_addr' in kwargs:
                kwargs['target_host'] = kwargs.pop('target_addr')
            
            # 确保client_ip参数存在
            if 'client_addr' in kwargs and 'client_ip' not in kwargs:
                kwargs['client_ip'] = kwargs.pop('client_addr')
            
            # 移除username参数，该参数不被LogEntry接受
            if 'username' in kwargs:
                # 如果有username但没有user_id，可以尝试查找用户ID
                if 'user_id' not in kwargs:
                    try:
                        from app.models.user import User
                        session = Session()
                        user = session.query(User).filter_by(username=kwargs['username']).first()
                        if user:
                            kwargs['user_id'] = user.id
                        session.close()
                    except Exception:
                        pass
                # 移除username参数，防止传递给数据库操作
                kwargs.pop('username')
            
            self._add_db_task('log_entry', level=level, message=message, **kwargs)
        except Exception as e:
            logger.error(f"记录日志条目失败: {str(e)}")
            # 尝试使用日志记录器直接记录
            if level == 'INFO':
                logger.info(message)
            elif level == 'WARNING':
                logger.warning(message)
            elif level == 'ERROR':
                logger.error(message)
            elif level == 'CRITICAL':
                logger.critical(message)
    
    def start(self):
        """启动代理服务器"""
        # 创建服务器套接字
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(self.config.MAX_CONNECTIONS)  # 使用实例配置
            self.running = True
            
            logger.info(f"Socks5代理服务器已启动，监听 {self.host}:{self.port}")
            self._log_entry('INFO', f"Socks5代理服务器已启动，监听 {self.host}:{self.port}")
            
            # 开始接受连接
            while self.running:
                try:
                    client_socket, client_addr = self.socket.accept()
                    logger.info(f"接受来自 {client_addr[0]}:{client_addr[1]} 的连接")
                    
                    # 每次接受新连接都同步配置
                    self.sync_config()
                    logger.info(f"已同步最新配置 - 当前认证模式: {'启用' if self.enable_auth else '禁用'}")
                    
                    # 检查黑白名单
                    if not self._check_access(client_addr[0]):
                        logger.warning(f"拒绝来自 {client_addr[0]} 的连接（黑白名单限制）")
                        self._log_entry('WARNING', f"拒绝来自 {client_addr[0]} 的连接（黑白名单限制）", 
                                       client_ip=client_addr[0], client_port=client_addr[1])
                        client_socket.close()
                        continue
                    
                    # 使用回调函数接收新创建的连接ID
                    connection_received = threading.Event()
                    connection_id_container = [None]  # 使用列表存储ID，以便在回调中修改
                    
                    def connection_callback(conn_id):
                        connection_id_container[0] = conn_id
                        connection_received.set()
                    
                    # 创建连接记录（异步）
                    self._add_db_task('create_connection', 
                                    client_addr=client_addr[0], 
                                    client_port=client_addr[1], 
                                    callback=connection_callback)
                    
                    # 等待连接ID（最多等待1秒）
                    if not connection_received.wait(1.0):
                        logger.error("获取连接ID超时")
                        client_socket.close()
                        continue
                    
                    connection_id = connection_id_container[0]
                    if connection_id is None:
                        logger.error("无法获取连接ID")
                        client_socket.close()
                        continue
                    
                    # 创建线程处理连接
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_addr, connection_id)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except (KeyboardInterrupt, SystemExit):
                    break
                except Exception as e:
                    logger.error(f"处理连接时出错: {str(e)}")
                    self._log_entry('ERROR', f"处理连接时出错: {str(e)}")
            
        except Exception as e:
            logger.critical(f"代理服务器启动失败: {str(e)}")
            self._log_entry('CRITICAL', f"代理服务器启动失败: {str(e)}")
        finally:
            self.stop()

    def _check_access(self, ip_address: str) -> bool:
        """检查IP是否被允许访问，支持 CIDR 格式判断

        Args:
            ip_address (str): 客户端IP地址

        Returns:
            bool: True 表示允许访问，False 表示拒绝
        """
        try:
            # 格式校验
            try:
                client_ip = ipaddress.ip_address(ip_address.strip())
            except ValueError:
                logger.warning(f"非法IP地址格式: {ip_address}")
                return False  # 格式错误的 IP 默认拒绝访问

            session = Session()
            try:
                # === 黑名单判断 ===
                for entry in session.query(BlacklistIP).filter_by(is_active=True).all():
                    try:
                        network = ipaddress.ip_network(entry.ip_address.strip(), strict=False)
                        if client_ip in network:
                            logger.info(f"IP {ip_address} 命中黑名单 {entry.ip_address}")
                            return False
                    except ValueError:
                        continue  # 跳过无法解析的 IP/CIDR

                # === 白名单判断 ===
                whitelist_entries = session.query(WhitelistIP).filter_by(is_active=True).all()
                if whitelist_entries:  # 开启白名单限制模式
                    allowed = False
                    for entry in whitelist_entries:
                        try:
                            network = ipaddress.ip_network(entry.ip_address.strip(), strict=False)
                            if client_ip in network:
                                allowed = True
                                break
                        except ValueError:
                            continue
                    if not allowed:
                        logger.info(f"IP {ip_address} 未命中白名单，拒绝访问")
                        return False

                # 默认允许
                return True

            finally:
                session.close()

        except Exception as e:
            logger.error(f"检查IP访问权限失败: {str(e)}")
            return True  # 出错时默认允许访问
    def sync_config(self):
        """强制同步配置文件中的设置到实例中
        
        这个方法会直接从磁盘读取配置文件，确保使用最新的配置值
        """
        try:
            # 直接读取配置文件而不使用importlib
            import os
            config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../config/config.py'))
            
            # 直接读取文件并查找ENABLE_AUTH行
            enable_auth = self.enable_auth  # 默认保持当前值
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
                # 查找ENABLE_AUTH的配置行
                for line in config_content.splitlines():
                    if line.strip().startswith('ENABLE_AUTH'):
                        # 提取值 (True 或 False)
                        value_str = line.split('=')[1].strip()
                        enable_auth = value_str.lower() == 'true'
                        break
            
            # 更新认证设置
            if self.enable_auth != enable_auth:
                logger.warning(f"同步配置 - 认证设置已变更: {self.enable_auth} → {enable_auth}")
                self.enable_auth = enable_auth
            
            # 其他配置项也可以用类似方法提取和更新
            
            return True
        except Exception as e:
            logger.error(f"同步配置时出错: {str(e)}")
            return False
            
    def _handle_client(self, client_socket, addr, connection_id):
        """处理客户端连接
        
        Args:
            client_socket: 客户端套接字
            addr: 客户端地址
            connection_id: 连接ID
        """
        try:
            # 在处理前同步配置
            self.sync_config()
            
            # 处理Socks5握手
            if not self._process_handshake(client_socket, addr, connection_id):
                return
            
            # 处理Socks5请求
            if not self._process_client_request(client_socket, addr, connection_id):
                return
                
        except Exception as e:
            error_msg = f"处理客户端 {addr[0]}:{addr[1]} 连接时出错: {str(e)}"
            logger.error(error_msg)
            self._log_entry('ERROR', error_msg, connection_id=connection_id, client_addr=addr[0], client_port=addr[1])
            self._update_connection_status(connection_id, status='ERROR', error=str(e))
        finally:
            # 关闭客户端连接
            try:
                client_socket.close()
            except:
                pass
            # 更新连接状态
            self._update_connection_status(connection_id, status='CLOSED')
            # 从活动连接中移除
            with self.lock:
                if connection_id in self.connections:
                    target_socket = self.connections.pop(connection_id)
                    try:
                        target_socket.close()
                    except:
                        pass
    
    def _process_handshake(self, client_socket, addr, connection_id):
        """处理Socks5握手
        
        Args:
            client_socket: 客户端套接字
            addr: 客户端地址
            connection_id: 连接ID
            
        Returns:
            bool: 握手是否成功
        """
        try:
            # 强制直接从配置文件读取认证设置，忽略实例属性
            enable_auth = False
            try:
                with open(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../config/config.py')), 'r', encoding='utf-8') as f:
                    config_content = f.read()
                    # 查找ENABLE_AUTH的配置行
                    for line in config_content.splitlines():
                        if line.strip().startswith('ENABLE_AUTH'):
                            # 提取值 (True 或 False)
                            value_str = line.split('=')[1].strip()
                            enable_auth = value_str.lower() == 'true'
                            break
                logger.info(f"直接从文件读取的认证设置: {enable_auth}")
                # 更新实例属性以保持一致
                self.enable_auth = enable_auth
            except Exception as e:
                logger.error(f"读取配置文件失败: {str(e)}")
                # 失败时使用实例的当前值
                enable_auth = self.enable_auth
            
            # 接收客户端发送的SOCKS5协议版本和支持的认证方法
            data = client_socket.recv(2)
            if not data or len(data) < 2:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 握手失败: 数据不足")
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 握手失败: 数据不足", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error="握手失败: 数据不足")
                return False
            
            version, nmethods = struct.unpack('!BB', data)
            if version != SOCKS_VERSION:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 使用不支持的SOCKS版本: {version}")
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 使用不支持的SOCKS版本: {version}", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error=f"不支持的SOCKS版本: {version}")
                return False
            
            # 接收认证方法列表
            methods = client_socket.recv(nmethods)
            if len(methods) != nmethods:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 握手失败: 认证方法数据不足")
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 握手失败: 认证方法数据不足", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error="握手失败: 认证方法数据不足")
                return False
                
            # 调试日志 - 显示认证状态
            methods_list = [m for m in methods]
            logger.info(f"客户端 {addr[0]}:{addr[1]} 支持的认证方法: {methods_list}")
            logger.info(f"当前使用的认证设置: {enable_auth}")
            
            # 如果需要认证并且客户端支持用户名密码认证
            if enable_auth and 0x02 in methods:
                # 选择用户名密码认证方法
                client_socket.sendall(struct.pack('!BB', SOCKS_VERSION, 0x02))
                logger.info(f"要求客户端 {addr[0]}:{addr[1]} 进行认证")
                if not self._authenticate_user(client_socket, addr, connection_id):
                    return False
            # 如果不需要认证或客户端支持无认证
            elif not enable_auth and 0x00 in methods:
                # 选择无需认证
                client_socket.sendall(struct.pack('!BB', SOCKS_VERSION, 0x00))
                logger.info(f"允许客户端 {addr[0]}:{addr[1]} 无需认证通过")
            else:
                # 不支持客户端提供的任何认证方法
                client_socket.sendall(struct.pack('!BB', SOCKS_VERSION, 0xFF))
                logger.error(f"客户端 {addr[0]}:{addr[1]} 不支持所需的认证方法")
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 不支持所需的认证方法", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error="不支持所需的认证方法")
                return False
            
            logger.info(f"客户端 {addr[0]}:{addr[1]} 握手成功")
            return True
            
        except Exception as e:
            error_msg = f"处理握手时出错: {str(e)}"
            logger.error(error_msg)
            self._log_entry('ERROR', error_msg, connection_id=connection_id)
            self._update_connection_status(connection_id, status='ERROR', error=error_msg)
            return False
    
    def _authenticate_user(self, client_socket, addr, connection_id):
        """进行用户名密码认证
        
        Args:
            client_socket: 客户端套接字
            addr: 客户端地址
            connection_id: 连接ID
            
        Returns:
            bool: 认证是否成功
        """
        try:
            # 接收认证数据
            version = client_socket.recv(1)
            if not version or version[0] != 0x01:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 认证版本不支持: {version[0] if version else 'None'}")
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 认证版本不支持", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error="认证版本不支持")
                client_socket.sendall(struct.pack('!BB', 0x01, 0x01))  # 认证失败
                return False
            
            # 读取用户名长度和用户名
            ulen = client_socket.recv(1)
            if not ulen:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 认证失败: 无法读取用户名长度")
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 认证失败: 无法读取用户名长度", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error="认证失败: 无法读取用户名长度")
                client_socket.sendall(struct.pack('!BB', 0x01, 0x01))  # 认证失败
                return False
            
            username_len = ulen[0]
            username = client_socket.recv(username_len).decode('utf-8')
            
            # 读取密码长度和密码
            plen = client_socket.recv(1)
            if not plen:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 认证失败: 无法读取密码长度")
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 认证失败: 无法读取密码长度", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error="认证失败: 无法读取密码长度")
                client_socket.sendall(struct.pack('!BB', 0x01, 0x01))  # 认证失败
                return False
            
            password_len = plen[0]
            password = client_socket.recv(password_len).decode('utf-8')
            
            # 验证用户名和密码
            auth_success = False
            user_info = None
            
            session = Session()
            try:
                # 从数据库中查询用户
                from app.models.user import User
                user_info = session.query(User).filter_by(username=username).first()
                auth_success = user_info and user_info.verify_password(password)
            except Exception as e:
                logger.error(f"验证用户失败: {str(e)}")
                self._log_entry('ERROR', f"验证用户失败: {str(e)}", connection_id=connection_id)
            finally:
                session.close()
            
            if auth_success:
                client_socket.sendall(struct.pack('!BB', 0x01, 0x00))  # 认证成功
                logger.info(f"用户 {username} 认证成功")
                self._log_entry('INFO', f"用户 {username} 认证成功", connection_id=connection_id, username=username)
                # 更新连接记录中的用户信息
                self._update_connection_status(connection_id, status='AUTHENTICATED', user_id=user_info.id)
                return True
            else:
                client_socket.sendall(struct.pack('!BB', 0x01, 0x01))  # 认证失败
                logger.warning(f"用户 {username} 认证失败")
                self._log_entry('WARNING', f"用户 {username} 认证失败", connection_id=connection_id, username=username)
                self._update_connection_status(connection_id, status='ERROR', error=f"用户 {username} 认证失败")
                return False
            
        except Exception as e:
            error_msg = f"处理认证时出错: {str(e)}"
            logger.error(error_msg)
            self._log_entry('ERROR', error_msg, connection_id=connection_id)
            self._update_connection_status(connection_id, status='ERROR', error=error_msg)
            try:
                client_socket.sendall(struct.pack('!BB', 0x01, 0x01))  # 认证失败
            except:
                pass
            return False
    
    def _process_client_request(self, client_socket, addr, connection_id):
        """处理客户端请求
        
        Args:
            client_socket: 客户端套接字
            addr: 客户端地址
            connection_id: 连接ID
            
        Returns:
            bool: 请求处理是否成功
        """
        try:
            # 接收请求数据
            data = client_socket.recv(4)
            if len(data) < 4:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 请求数据不足")
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 请求数据不足", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error="请求数据不足")
                return False
            
            version, cmd, _, atyp = struct.unpack('!BBBB', data)
            if version != SOCKS_VERSION:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 使用不支持的SOCKS版本: {version}")
                self._send_reply(client_socket, REP_SERVER_FAILURE)
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 使用不支持的SOCKS版本: {version}", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error=f"不支持的SOCKS版本: {version}")
                return False
            
            # 获取目标地址
            target_addr = None
            port = 0
            
            # IPv4
            if atyp == ADDR_TYPE_IPV4:
                addr_data = client_socket.recv(4)
                if len(addr_data) < 4:
                    logger.error(f"客户端 {addr[0]}:{addr[1]} IPv4地址数据不足")
                    self._send_reply(client_socket, REP_SERVER_FAILURE)
                    self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} IPv4地址数据不足", connection_id=connection_id)
                    self._update_connection_status(connection_id, status='ERROR', error="IPv4地址数据不足")
                    return False
                target_addr = socket.inet_ntoa(addr_data)
            
            # 域名
            elif atyp == ADDR_TYPE_DOMAIN:
                domain_len = client_socket.recv(1)[0]
                domain = client_socket.recv(domain_len)
                if len(domain) < domain_len:
                    logger.error(f"客户端 {addr[0]}:{addr[1]} 域名数据不足")
                    self._send_reply(client_socket, REP_SERVER_FAILURE)
                    self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 域名数据不足", connection_id=connection_id)
                    self._update_connection_status(connection_id, status='ERROR', error="域名数据不足")
                    return False
                target_addr = domain.decode('utf-8')
            
            # IPv6
            elif atyp == ADDR_TYPE_IPV6:
                addr_data = client_socket.recv(16)
                if len(addr_data) < 16:
                    logger.error(f"客户端 {addr[0]}:{addr[1]} IPv6地址数据不足")
                    self._send_reply(client_socket, REP_SERVER_FAILURE)
                    self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} IPv6地址数据不足", connection_id=connection_id)
                    self._update_connection_status(connection_id, status='ERROR', error="IPv6地址数据不足")
                    return False
                target_addr = socket.inet_ntop(socket.AF_INET6, addr_data)
            
            # 不支持的地址类型
            else:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 使用不支持的地址类型: {atyp}")
                self._send_reply(client_socket, REP_SERVER_FAILURE)
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 使用不支持的地址类型: {atyp}", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error=f"不支持的地址类型: {atyp}")
                return False
            
            # 获取端口
            port_data = client_socket.recv(2)
            if len(port_data) < 2:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 端口数据不足")
                self._send_reply(client_socket, REP_SERVER_FAILURE)
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 端口数据不足", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error="端口数据不足")
                return False
            port = struct.unpack('!H', port_data)[0]
            
            # 处理CONNECT命令
            if cmd == CMD_CONNECT:
                return self._handle_connect(client_socket, addr, target_addr, port, connection_id)
            
            # 不支持的命令
            else:
                logger.error(f"客户端 {addr[0]}:{addr[1]} 使用不支持的命令: {cmd}")
                self._send_reply(client_socket, REP_COMMAND_NOT_SUPPORTED)
                self._log_entry('ERROR', f"客户端 {addr[0]}:{addr[1]} 使用不支持的命令: {cmd}", connection_id=connection_id)
                self._update_connection_status(connection_id, status='ERROR', error=f"不支持的命令: {cmd}")
                return False
                
        except Exception as e:
            error_msg = f"处理客户端请求时出错: {str(e)}"
            logger.error(error_msg)
            self._log_entry('ERROR', error_msg, 
                        connection_id=connection_id,
                        client_addr=addr[0],
                        client_port=addr[1])
            try:
                self._send_reply(client_socket, REP_SERVER_FAILURE)
            except:
                pass
            return False
    
    def _handle_connect(self, client_socket, addr, target_addr, target_port, connection_id):
        """处理CONNECT命令
        
        Args:
            client_socket: 客户端套接字
            addr: 客户端地址
            target_addr: 目标地址
            target_port: 目标端口
            connection_id: 连接ID
            
        Returns:
            bool: 连接是否成功
        """
        try:
            # 连接目标服务器
            logger.info(f"连接到 {target_addr}:{target_port}")
            target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_socket.settimeout(CONNECTION_TIMEOUT)  # 使用直接定义的超时常量
            target_socket.connect((target_addr, target_port))
            
            # 发送连接成功回复
            bind_addr = target_socket.getsockname()[0]
            bind_port = target_socket.getsockname()[1]
            self._send_reply(client_socket, REP_SUCCESS, bind_addr, bind_port)
            
            # 更新连接状态
            self._update_connection_status(connection_id, 
                                         target_addr=target_addr, 
                                         target_port=target_port)
            
            # 记录日志时使用正确的参数名
            self._log_entry('INFO', f"成功连接到 {target_addr}:{target_port}", 
                          connection_id=connection_id, 
                          client_addr=addr[0],
                          client_port=addr[1],
                          target_host=target_addr,
                          target_port=target_port)
            
            # 保存目标服务器套接字
            with self.lock:
                self.connections[connection_id] = target_socket
            
            # 开始数据转发
            self._forward_data(client_socket, target_socket, addr, target_addr, target_port, connection_id)
            return True
            
        except Exception as e:
            error_msg = f"连接到 {target_addr}:{target_port} 失败: {str(e)}"
            logger.error(error_msg)
            # 记录日志时使用正确的参数名
            self._log_entry('ERROR', error_msg, 
                          connection_id=connection_id,
                          client_addr=addr[0],
                          client_port=addr[1],
                          target_host=target_addr,
                          target_port=target_port)
            self._update_connection_status(connection_id, status='ERROR', error=error_msg)
            try:
                self._send_reply(client_socket, REP_CONNECTION_REFUSED)
            except:
                pass
            return False

    def _send_reply(self, client_socket, rep, bind_addr="0.0.0.0", bind_port=0):
        """发送SOCKS5回复
        
        Args:
            client_socket: 客户端套接字
            rep: 回复代码
            bind_addr: 绑定地址
            bind_port: 绑定端口
        """
        try:
            # 发送回复头
            client_socket.sendall(struct.pack('!BBB', SOCKS_VERSION, rep, 0))
            
            # 发送绑定地址和端口（IPv4）
            client_socket.sendall(struct.pack('!B', ADDR_TYPE_IPV4))
            client_socket.sendall(socket.inet_aton(bind_addr))
            client_socket.sendall(struct.pack('!H', bind_port))
        except Exception as e:
            logger.error(f"发送回复失败: {str(e)}")
    
    def _forward_data(self, client_socket, target_socket, client_addr, target_addr, target_port, connection_id):
        """在客户端和目标服务器之间转发数据
        
        Args:
            client_socket: 客户端套接字
            target_socket: 目标服务器套接字
            client_addr: 客户端地址
            target_addr: 目标地址
            target_port: 目标端口
            connection_id: 连接ID
        """
        try:
            client_socket.setblocking(False)
            target_socket.setblocking(False)
            
            # 设置超时时间
            timeout = DATA_TRANSFER_TIMEOUT  # 使用直接定义的超时常量
            
            # 用于记录流量
            bytes_sent = 0
            bytes_received = 0
            last_update_time = time.time()
            
            # 开始转发数据循环
            while True:
                # 定期更新连接状态（每5秒一次）
                current_time = time.time()
                if current_time - last_update_time >= 5:
                    self._update_connection_status(connection_id,
                                                bytes_sent=bytes_sent,
                                                bytes_received=bytes_received)
                    bytes_sent = 0
                    bytes_received = 0
                    last_update_time = current_time
                
                # 使用select监听套接字
                readable, _, exceptional = select.select(
                    [client_socket, target_socket], [], [client_socket, target_socket], timeout
                )
                
                if not readable and not exceptional:
                    continue
                
                if client_socket in exceptional or target_socket in exceptional:
                    # 套接字异常，关闭连接
                    logger.warning(f"连接 {client_addr[0]}:{client_addr[1]} 异常")
                    break
                
                # 从客户端读取数据，发送到目标服务器
                if client_socket in readable:
                    try:
                        data = client_socket.recv(self.config.BUFFER_SIZE)  # 使用实例配置
                        if not data:
                            # 客户端关闭连接
                            break
                        bytes_sent += len(data)
                        target_socket.sendall(data)
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                        logger.warning(f"客户端 {client_addr[0]}:{client_addr[1]} 连接重置")
                        break
                    except Exception as e:
                        logger.error(f"从客户端 {client_addr[0]}:{client_addr[1]} 读取数据失败: {str(e)}")
                        break
                
                # 从目标服务器读取数据，发送到客户端
                if target_socket in readable:
                    try:
                        data = target_socket.recv(self.config.BUFFER_SIZE)  # 使用实例配置
                        if not data:
                            # 目标服务器关闭连接
                            break
                        bytes_received += len(data)
                        client_socket.sendall(data)
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                        logger.warning(f"目标服务器 {target_addr}:{target_port} 连接重置")
                        break
                    except Exception as e:
                        logger.error(f"从目标服务器 {target_addr}:{target_port} 读取数据失败: {str(e)}")
                        break
                
        except Exception as e:
            logger.error(f"转发数据时出错: {str(e)}")
        finally:
            # 更新连接状态
            if bytes_sent > 0 or bytes_received > 0:
                self._update_connection_status(connection_id,
                                             bytes_sent=bytes_sent,
                                             bytes_received=bytes_received)
    
    def stop(self):
        """停止代理服务器"""
        self.running = False
        
        # 关闭服务器套接字
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"关闭服务器套接字失败: {str(e)}")
        
        # 关闭所有连接
        with self.lock:
            for connection_id, target_socket in self.connections.items():
                try:
                    target_socket.close()
                except:
                    pass
                try:
                    self._update_connection_status(connection_id, status='CLOSED')
                except Exception as e:
                    logger.error(f"更新连接状态失败: {str(e)}")
            # 确保完全清空连接字典
            self.connections.clear()
        
        # 安全记录停止日志
        try:
            logger.info("代理服务器已停止")
            
            # 分开处理数据库日志记录，以防止数据库上下文错误
            try:
                self._log_entry('INFO', "代理服务器已停止")
            except Exception as e:
                logger.error(f"数据库日志记录失败: {str(e)}")
        except Exception as e:
            # 如果连logger也无法使用，则不再尝试记录
            pass
        
        # 关闭数据库工作线程
        try:
            db_queue.put(None)  # 发送终止信号
            db_thread.join(1.0)  # 等待线程结束，最多1秒
        except Exception as e:
            logger.error(f"关闭数据库工作线程失败: {str(e)}") 