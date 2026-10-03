#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import create_app, db
from app.models.user import User
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('db_init')

def init_database():
    """初始化数据库，创建默认用户"""
    try:
        app = create_app()
        with app.app_context():
            # 检查是否已存在管理员用户
            admin = User.query.filter_by(username='admin').first()
            if admin is None:
                # 创建默认管理员用户
                admin = User(
                    username='admin',
                    password='admin',
                    email='admin@example.com',
                    is_admin=True
                )
                db.session.add(admin)
                
                # 创建测试用户
                test_user = User(
                    username='test',
                    password='test',
                    email='test@example.com',
                    is_admin=False
                )
                db.session.add(test_user)
                
                db.session.commit()
                logger.info("已创建默认管理员用户和测试用户")
            else:
                logger.info("管理员用户已存在，跳过创建")
    
    except Exception as e:
        logger.error(f"初始化数据库时出错: {str(e)}")
        return False
    
    return True

if __name__ == '__main__':
    success = init_database()
    if success:
        print("数据库初始化成功!")
    else:
        print("数据库初始化失败，请查看日志获取详细信息。") 