from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, IntegerField, SelectField, HiddenField
from wtforms.validators import DataRequired, Length, NumberRange, EqualTo, Email, Optional, IPAddress

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    captcha = StringField('验证码', validators=[DataRequired(), Length(4, 4)])
    captcha_id = HiddenField('验证码 ID', validators=[DataRequired()])
    remember = BooleanField('记住我')
    submit = SubmitField('登录')

class ProfileForm(FlaskForm):
    email = StringField('邮箱', validators=[
        Optional(), Email(message="请输入有效的邮箱地址"),
        Length(max=120, message="邮箱长度不超过 120 字符")
    ])
    current_password = PasswordField('当前密码', validators=[Optional()])
    new_password = PasswordField('新密码', validators=[Optional(), Length(min=6, message="新密码至少 6 位")])
    confirm_password = PasswordField('确认新密码', validators=[
        Optional(), EqualTo('new_password', message="两次输入的密码不一致")
    ])
    submit = SubmitField('更新资料')

# class ScenarioForm(FlaskForm):
#     name = StringField(
#         '场景名称',
#         validators=[
#             DataRequired(message="场景名称不能为空"),
#             Length(min=2, max=64, message="名称长度必须在 2 到 64 个字符之间")
#         ]
#     )
#     description = StringField(
#         '场景描述',
#         validators=[Optional(), Length(max=256, message="描述长度不超过 256 字符")]
#     )
#     port = IntegerField(
#         '代理监听端口',
#         validators=[
#             DataRequired(message="端口不能为空"),
#             NumberRange(min=1024, max=65535, message="端口号范围必须在 1024 到 65535 之间")
#         ]
#     )
#     log_path = StringField(
#         '日志路径',
#         validators=[
#             DataRequired(message="日志路径不能为空"),
#             Length(max=256, message="路径长度不超过 256 字符"),
#             Regexp(r'^(/[\w\-\.]+)+/?$', message="必须是以“/”开头的绝对路径，且不包含特殊字符")
#         ]
#     )
#     max_connections = IntegerField(
#         '最大连接数',
#         validators=[
#             DataRequired(message="请输入最大连接数"),
#             NumberRange(min=1, max=100000, message="最大连接数应在 1 到 100000 之间")
#         ]
#     )
#     buffer_size = IntegerField(
#         '缓冲区大小（字节）',
#         validators=[
#             DataRequired(message="请输入缓冲区大小"),
#             NumberRange(min=512, max=65536, message="缓冲区大小应在 512 到 65536 字节之间")
#         ]
#     )
#     proxy_timeout = IntegerField(
#         '连接超时（秒）',
#         validators=[
#             DataRequired(message="请输入连接超时时间"),
#             NumberRange(min=1, max=3600, message="连接超时应在 1 到 3600 秒之间")
#         ]
#     )
#     enable_auth = BooleanField(
#         '启用用户认证', default=False
#     )
#     log_level = SelectField(
#         '日志级别',
#         choices=[
#             ('DEBUG', 'DEBUG'),
#             ('INFO', 'INFO'),
#             ('WARNING', 'WARNING'),
#             ('ERROR', 'ERROR'),
#             ('CRITICAL', 'CRITICAL')
#         ],
#         validators=[DataRequired(message="请选择日志级别")]
#     )
#     is_active = BooleanField('是否启用', default=True)
#
#     submit = SubmitField('提交')
#

class UserForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=3, max=64)])
    password = PasswordField('密码', validators=[DataRequired(), Length(min=6)])
    email = StringField('电子邮箱', validators=[Optional(), Email(), Length(max=120)])
    is_admin = BooleanField('管理员')
    is_active = BooleanField('激活状态')
    submit = SubmitField('提交')

class BlacklistForm(FlaskForm):
    ip_address = StringField('IP 或 CIDR', validators=[DataRequired(), Length(max=50)])
    description = StringField('描述', validators=[Optional(), Length(max=255)])
    submit = SubmitField('提交')

class WhitelistForm(FlaskForm):
    ip_address = StringField('IP 或 CIDR', validators=[DataRequired(), Length(max=50)])
    description = StringField('描述', validators=[Optional(), Length(max=255)])
    submit = SubmitField('提交')

class ScenarioForm(FlaskForm):
    # 场景名称字段
    name = StringField('场景名称', validators=[
        DataRequired(message='场景名称不能为空'),
        Length(min=2, max=50, message='名称长度需在2-50个字符之间')
    ])

    # 描述字段
    description = StringField('描述', validators=[
        Length(max=255, message='描述不能超过255个字符')
    ])

    # 代理监听地址字段
    proxy_host = StringField('代理监听地址', validators=[
        DataRequired(message='监听地址不能为空'),
        IPAddress(message='请输入有效的IP地址')
    ])

    # 端口字段
    port = IntegerField('代理监听端口', validators=[
        DataRequired(message='端口不能为空'),
        NumberRange(min=1, max=65535, message='端口必须在1-65535范围内')
    ])

    # 最大连接数字段
    max_connections = IntegerField('最大连接数', validators=[
        DataRequired(message='最大连接数不能为空'),
        NumberRange(min=1, message='最小连接数为1')
    ])

    # 缓冲区大小字段
    buffer_size = IntegerField('缓冲区大小（字节）', validators=[
        DataRequired(message='缓冲区大小不能为空'),
        NumberRange(min=1024, message='缓冲区最小为1024字节')
    ])

    # 连接超时字段
    proxy_timeout = IntegerField('连接超时（秒）', validators=[
        DataRequired(message='超时时间不能为空'),
        NumberRange(min=1, message='超时时间最小为1秒')
    ])

    # 认证启用字段
    enable_auth = BooleanField('启用用户认证')

    # 日志级别字段
    log_level = SelectField('日志级别', choices=[
        ('DEBUG', 'DEBUG'),
        ('INFO', 'INFO'),
        ('WARNING', 'WARNING'),
        ('ERROR', 'ERROR'),
        ('CRITICAL', 'CRITICAL')
    ], validators=[
        DataRequired(message='请选择日志级别')
    ])

    # 场景启用字段
    is_active = BooleanField('启用该场景', default=True)
