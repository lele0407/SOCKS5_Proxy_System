#!/usr/bin/env python
# -*- coding: utf-8 -*-

import uuid
import io
import random
import string
from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    make_response,
    current_app as app
)
from flask_login import login_user, logout_user, login_required, current_user
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from app import db
from app.models.user import User
from app.models.log_entry import LogEntry
from werkzeug.urls import url_parse

from app.models.blacklist import BlacklistIP
from app.models.whitelist import WhitelistIP
from app.controllers.forms import LoginForm, ProfileForm

# 创建蓝图
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# —— 全局内存存储验证码信息 —— #
# 注意：仅适用于单进程部署。生产环境多进程/多实例请换为 Redis 等集中式存储。
captcha_store = {}


def _generate_captcha_text(length=4):
    """生成随机验证码字符串（数字 + 大写字母）。"""
    chars = string.digits + string.ascii_uppercase
    return ''.join(random.choices(chars, k=length))


def _create_captcha_image(text):
    """
    根据 text（例如 "A7K9"）生成一张验证码图片（PIL Image）。
    图片大小、字体等可按需调整。
    """
    width, height = 100, 40
    bg_color = (255, 255, 255)  # 白色背景
    font_size = 24
    font_path = app.root_path + '/static/fonts/Arial.ttf'  # 请确保这里有字体文件

    image = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        font = ImageFont.load_default()

    # 画每个字符，随机位置 + 随机深色
    for i, ch in enumerate(text):
        char_color = (
            random.randint(0, 100),
            random.randint(0, 100),
            random.randint(0, 100)
        )
        x = 5 + i * 24
        y = random.randint(0, 10)
        draw.text((x, y), ch, font=font, fill=char_color)

    # 增加几条干扰线
    for _ in range(5):
        line_color = (
            random.randint(150, 200),
            random.randint(150, 200),
            random.randint(150, 200)
        )
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line(((x1, y1), (x2, y2)), fill=line_color, width=1)

    # 简单加点锐化
    image = image.filter(ImageFilter.EDGE_ENHANCE_MORE)
    return image


@auth_bp.route('/captcha')
def captcha():
    """
    生成验证码图片，将 {captcha_id: {text, timestamp}} 存到服务器端 captcha_store。
    在 HTTP Header X-Captcha-ID 中返回 captcha_id，前端通过 JS 读取并写入隐藏域。
    """
    # 1) 随机生成 4 位验证码文本
    text = _generate_captcha_text(4)
    # 2) 生成唯一 ID
    captcha_id = str(uuid.uuid4())

    # 3) 存入全局 captcha_store
    captcha_store[captcha_id] = {
        'text': text,
        'timestamp': datetime.utcnow().timestamp()
    }

    # 4) 用 Pillow 生成图片
    image = _create_captcha_image(text)
    buf = io.BytesIO()
    image.save(buf, 'PNG')
    buf.seek(0)

    # 5) 返回 PNG，同时在 Header 中返回 captcha_id
    response = make_response(buf.read())
    response.headers['Content-Type'] = 'image/png'
    response.headers['X-Captcha-ID'] = captcha_id
    return response


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    用户登录视图——仅允许管理员登录，非管理员用户不能登录。
    同时校验验证码（一次性 + 60 秒有效期），并在校验后立即从 captcha_store 删除该条记录。
    """
    form = LoginForm()
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        logout_user()
        flash('无权访问，请使用管理员账号登录', 'danger')
        return redirect(url_for('auth.login'))

    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data
        input_captcha = form.captcha.data.strip().upper()
        captcha_id = form.captcha_id.data
        remember = form.remember.data

        # —— 验证验证码部分 —— #
        captcha_data = captcha_store.get(captcha_id)
        if not captcha_data:
            flash('验证码无效或已过期', 'danger')
            return redirect(url_for('auth.login'))

        now_ts = datetime.utcnow().timestamp()
        # 判断是否超时（60 秒有效期）
        if now_ts - captcha_data['timestamp'] > 60:
            del captcha_store[captcha_id]
            flash('验证码已过期，请刷新后重试', 'danger')
            return redirect(url_for('auth.login'))

        # 校对用户输入的验证码
        if input_captcha != captcha_data['text']:
            del captcha_store[captcha_id]
            flash('验证码错误，请重新输入', 'danger')
            return redirect(url_for('auth.login'))

        # 验证通过后立即删除，防止重放
        del captcha_store[captcha_id]

        # —— 验证用户名/密码 与 管理员权限 —— #
        user = User.query.filter_by(username=username).first()
        if user is None or not user.verify_password(password):
            flash('用户名或密码不正确', 'danger')
            LogEntry.warning(f"用户 {username} 登录失败（账号或密码错误）",
                             client_ip=request.remote_addr)
            return redirect(url_for('auth.login'))

        if not user.is_admin:
            flash('无权访问，请使用管理员账号登录', 'danger')
            LogEntry.warning(f"普通用户 {username} 尝试登录后台，已拒绝",
                             client_ip=request.remote_addr, user_id=user.id)
            return redirect(url_for('auth.login'))

        # 管理员且密码正确，允许登录
        login_user(user, remember=remember)
        user.update_last_login()
        LogEntry.info(f"管理员 {username} 登录成功",
                      client_ip=request.remote_addr, user_id=user.id)

        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('admin.dashboard')
        return redirect(next_page)

    # GET 请求 或 验证失败后，重新渲染表单
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    注销视图：改为 POST 方式，避免 CSRF。前端需要用带有隐藏 CSRF Token 的 form 来提交。
    模板示例（放在 base.html 或合适的位置）：
        <form id="logout-form" action="{{ url_for('auth.logout') }}" method="post">
          {{ csrf_token() }}
          <button type="submit" class="dropdown-item">退出登录</button>
        </form>
    """
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """
    用户个人资料视图
    支持：1）更新邮箱；2）更新密码（需要填写当前密码和确认密码）。
    """
    form = ProfileForm()
    if form.validate_on_submit():
        # 验证当前密码（如果输入了）
        if form.current_password.data:
            if not current_user.verify_password(form.current_password.data):
                flash('当前密码不正确', 'danger')
                return redirect(url_for('auth.profile'))

        # 更新邮箱
        new_email = form.email.data.strip() if form.email.data else None
        if new_email and new_email != current_user.email:
            current_user.email = new_email

        # 更新密码（如果填写了新密码）
        if form.new_password.data:
            current_user.set_password(form.new_password.data)
            flash('密码已更新', 'success')
            LogEntry.info(f"用户 {current_user.username} 更新了密码",
                          client_ip=request.remote_addr,
                          user_id=current_user.id)

        db.session.commit()
        flash('个人资料已更新', 'success')
        return redirect(url_for('auth.profile'))

    # GET 请求，或 POST 未通过验证时，把当前数据填入表单
    if request.method == 'GET':
        form.email.data = current_user.email

    return render_template('auth/profile.html', form=form)
