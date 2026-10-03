from datetime import datetime
from app import db

class Scenario(db.Model):
    __tablename__ = 'scenarios'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, comment="场景名称")
    description = db.Column(db.String(256), nullable=True, comment="场景描述（可选）")
    proxy_host = db.Column(db.String(64), nullable=False, default='0.0.0.0', comment="代理监听地址")
    port = db.Column(db.Integer, nullable=False, default=1080, comment="代理监听端口")
    max_connections = db.Column(db.Integer, nullable=False, default=100, comment="最大连接数")
    buffer_size = db.Column(db.Integer, nullable=False, default=4096, comment="缓冲区大小")
    proxy_timeout = db.Column(db.Integer, nullable=False, default=60, comment="连接超时时间（秒）")
    log_level = db.Column(db.String(16), nullable=False, default='INFO', comment="日志级别")
    enable_auth = db.Column(db.Boolean, nullable=False, default=True, comment="是否启用用户认证")
    is_active = db.Column(db.Boolean, nullable=False, default=True, comment="是否启用该场景")

    def __repr__(self):
        return f"<Scenario {self.name} (port={self.port})>"
