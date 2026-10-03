# app/views/scenario.py

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from app.models.scenario import Scenario
from app.controllers.forms import ScenarioForm

scenario_bp = Blueprint('scenario', __name__, url_prefix='/scenario')

@scenario_bp.route('/')
@login_required
def list_scenarios():
    page = request.args.get('page', 1, type=int)
    pagination = Scenario.query.order_by(Scenario.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    scenarios = pagination.items
    return render_template(
        'scenario/list.html',
        scenarios=scenarios,
        pagination=pagination
    )

@scenario_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_scenario():
    form = ScenarioForm()
    if form.validate_on_submit():
        if Scenario.query.filter_by(name=form.name.data.strip()).first():
            flash('该场景名称已存在，请使用其他名称。', 'warning')
            return render_template('scenario/form.html', form=form, mode='create')

        new_scenario = Scenario(
            name=form.name.data.strip(),
            description=form.description.data.strip(),
            port=form.port.data,
            proxy_host=form.proxy_host.data.strip(),
            max_connections=form.max_connections.data,
            buffer_size=form.buffer_size.data,
            proxy_timeout=form.proxy_timeout.data,
            log_level=form.log_level.data,
            is_active=form.is_active.data,
            checkbox=form.checkbox.data,
        )
        db.session.add(new_scenario)
        db.session.commit()
        flash('场景已创建', 'success')
        return redirect(url_for('scenario.list_scenarios'))
    return render_template('scenario/form.html', form=form, mode='create')

@scenario_bp.route('/<int:scenario_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_scenario(scenario_id):
    scenario = Scenario.query.get_or_404(scenario_id)
    form = ScenarioForm(obj=scenario)
    if form.validate_on_submit():
        new_name = form.name.data.strip()
        if new_name != scenario.name and Scenario.query.filter_by(name=new_name).first():
            flash('该场景名称已被占用，请换一个。', 'warning')
            return render_template('scenario/form.html', form=form, mode='edit')
        scenario.name = new_name
        scenario.description = form.description.data.strip()
        scenario.port = form.port.data
        scenario.log_path = form.log_path.data.strip()
        scenario.whitelist = form.whitelist.data.strip()
        scenario.blacklist = form.blacklist.data.strip()
        scenario.is_active = form.is_active.data
        db.session.commit()
        flash('场景已更新', 'success')
        return redirect(url_for('scenario.list_scenarios'))
    return render_template('scenario/form.html', form=form, mode='edit', scenario=scenario)

@scenario_bp.route('/<int:scenario_id>/delete', methods=['POST'])
@login_required
def delete_scenario(scenario_id):
    scenario = Scenario.query.get_or_404(scenario_id)
    db.session.delete(scenario)
    db.session.commit()
    flash(f"已删除场景：{scenario.name}", 'info')
    return redirect(url_for('scenario.list_scenarios'))
