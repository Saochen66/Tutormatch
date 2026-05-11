import os
import json
from collections import Counter
from statistics import mean, median
from functools import wraps
import requests
from sqlalchemy import inspect, text
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from werkzeug.local import LocalProxy
from config import Config, SUBJECTS, GRADES, TEACHING_MODES, WEEKDAYS
from models import db, User, TutorInfo, StudentInfo, Admin, Favorite, Review

SILICONFLOW_API_KEY = os.environ.get('SILICONFLOW_API_KEY', '').strip()
SILICONFLOW_API_URL = os.environ.get('SILICONFLOW_API_URL', 'https://api.siliconflow.cn/v1/chat/completions').strip()
DEFAULT_MODEL = os.environ.get('SILICONFLOW_MODEL', 'Qwen/Qwen2-7B-Instruct').strip()

app = Flask(__name__)
app.config.from_object(Config)
app.config['UPLOAD_FOLDER'] = Config.UPLOAD_FOLDER

SILICONFLOW_API_KEY = app.config.get('SILICONFLOW_API_KEY', SILICONFLOW_API_KEY)
SILICONFLOW_API_URL = app.config.get('SILICONFLOW_API_URL', SILICONFLOW_API_URL)
DEFAULT_MODEL = app.config.get('SILICONFLOW_MODEL', DEFAULT_MODEL)
MODEL_CANDIDATES = app.config.get('SILICONFLOW_MODELS', [DEFAULT_MODEL])
OPENROUTER_API_KEY = app.config.get('OPENROUTER_API_KEY', '')
OPENROUTER_API_URL = app.config.get('OPENROUTER_API_URL', 'https://openrouter.ai/api/v1/chat/completions')
LLM_REQUEST_TIMEOUT = int(app.config.get('LLM_REQUEST_TIMEOUT', 22))

ASSISTANT_PLATFORM_KNOWLEDGE = {
    'core_flows': {
        'roles': ['tutor', 'student', 'admin'],
        'entry_pages': {
            'tutor': '/tutor/home',
            'student': '/student/home',
            'assistant': '/assistant',
            'my_center': '/my',
            'my_favorites': '/my/favorites'
        },
        'matching_type': '家教与学生双向筛选匹配'
    },
    'tutor_profile_fields': {
        'subjects': '家教可授课科目，支持多选',
        'grades': '可授课年级，支持多选',
        'teaching_mode': '授课方式（线上/线下）支持多选',
        'fee': '每小时费用（元），填写范围0-1000',
        'teaching_time': '每周可授课时间段',
        'introduction': '个人介绍，最多50字',
        'accept_opposite_gender': '是否接受异性学生'
    },
    'student_profile_fields': {
        'subjects': '学生需求科目，支持多选',
        'grade': '当前年级，单选',
        'teaching_mode': '期望授课方式（线上/线下）支持多选',
        'budget_upper': '预算上限（元/小时）',
        'teaching_time': '每周可上课时间段',
        'requirements': '补充要求，最多50字',
        'accept_opposite_gender': '是否只接受同性家教'
    },
    'search_logic': {
        'student_search_tutors': [
            '默认按学生需求科目做包含匹配',
            '若学生不接受异性家教，则按性别过滤',
            '支持按授课方式筛选',
            '支持按费用区间筛选',
            '支持按最新或最低费用排序'
        ],
        'tutor_search_students': [
            '默认按家教科目做包含匹配',
            '若家教不接受异性学生，则按性别过滤',
            '支持按年级筛选',
            '支持按科目筛选',
            '支持按授课方式筛选',
            '支持按预算区间筛选',
            '支持按最新或最高预算排序'
        ]
    },
    'new_features': {
        'favorites': '双方筛选列表支持点击星标收藏；我的收藏可查看和取消收藏',
        'best_match': '筛选页顶部会展示最佳匹配及匹配度解释',
        'withdraw_listing': '用户可在我的页面撤回需求；撤回后不会被筛选列表和AI统计看到'
    }
}

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

ROLE_USER_IDS_KEY = 'role_user_ids'
ACTIVE_ROLE_KEY = 'active_role'
TUTOR_ENDPOINTS = {
    'tutor_home',
    'tutor_info',
    'search_students',
    'student_detail',
    'received_reviews',
    'tutor_reviews'
}
STUDENT_ENDPOINTS = {
    'student_home',
    'student_info',
    'search_tutors',
    'tutor_detail',
    'my_reviews',
    'display_add_review',
    'add_review',
    'edit_review',
    'delete_review'
}


class _AnonymousRequestUser:
    is_authenticated = False
    is_active = False
    id = None
    nickname = ''
    role = ''
    tutor_info = None
    student_info = None


def _get_role_user_ids():
    role_user_ids = session.get(ROLE_USER_IDS_KEY)
    if not isinstance(role_user_ids, dict):
        role_user_ids = {}
        session[ROLE_USER_IDS_KEY] = role_user_ids
    return role_user_ids


def _set_role_user(role, user_id):
    role_user_ids = _get_role_user_ids()
    role_user_ids[role] = user_id
    session[ROLE_USER_IDS_KEY] = role_user_ids
    session[ACTIVE_ROLE_KEY] = role
    session.modified = True


def _clear_role_user(role=None):
    role_user_ids = _get_role_user_ids()
    if role:
        role_user_ids.pop(role, None)
        session[ROLE_USER_IDS_KEY] = role_user_ids
        if session.get(ACTIVE_ROLE_KEY) == role:
            session.pop(ACTIVE_ROLE_KEY, None)
    else:
        session.pop(ROLE_USER_IDS_KEY, None)
        session.pop(ACTIVE_ROLE_KEY, None)
    session.modified = True


def _resolve_request_role():
    endpoint = request.endpoint or ''
    # Some tutor pages are role-neutral (both students and tutors may view them).
    # For those, prefer the student's session when available so student-specific
    # UI (like "我要评价") can show correctly.
    neutral_tutor_views = {'tutor_reviews', 'tutor_detail'}
    if endpoint in neutral_tutor_views:
        role_user_ids = session.get(ROLE_USER_IDS_KEY)
        if isinstance(role_user_ids, dict) and role_user_ids.get('student'):
            return 'student'
        if isinstance(role_user_ids, dict) and role_user_ids.get('tutor'):
            return 'tutor'
        return None

    if endpoint in TUTOR_ENDPOINTS:
        return 'tutor'
    if endpoint in STUDENT_ENDPOINTS:
        return 'student'
    if endpoint in {'my_center', 'my_favorites', 'withdraw_listing', 'toggle_favorite', 'my_reviews', 'received_reviews'}:
        active_role = session.get(ACTIVE_ROLE_KEY)
        if active_role in {'tutor', 'student'}:
            return active_role
    active_role = session.get(ACTIVE_ROLE_KEY)
    if active_role in {'tutor', 'student'}:
        return active_role
    if request.path.startswith('/tutor/'):
        return 'tutor'
    if request.path.startswith('/student/'):
        return 'student'
    return None


def _get_current_request_user():
    role = _resolve_request_role()
    if role not in {'tutor', 'student'}:
        return _AnonymousRequestUser()

    user_id = _get_role_user_ids().get(role)
    if not user_id:
        return _AnonymousRequestUser()

    user = User.query.get(int(user_id))
    if not user or not user.is_active:
        return _AnonymousRequestUser()
    return user


current_user = LocalProxy(_get_current_request_user)


def login_user(user):
    _set_role_user(user.role, user.id)
    return True


def logout_user(role=None):
    _clear_role_user(role or _resolve_request_role())


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        user = _get_current_request_user()
        if not getattr(user, 'is_authenticated', False):
            flash('请先登录')
            return redirect(url_for('login'))
        return view_func(*args, **kwargs)

    return wrapped_view


@app.context_processor
def inject_current_user():
    return {'current_user': _get_current_request_user()}


@app.before_request
def remember_active_role():
    role = _resolve_request_role()
    if role in {'tutor', 'student'}:
        session[ACTIVE_ROLE_KEY] = role

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def save_avatar(file, role_prefix, user_id):
    if not file or not file.filename or not allowed_file(file.filename):
        return None

    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = secure_filename(f"{role_prefix}_{user_id}.{ext}")
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    return filename


def _parse_teaching_time(raw_json_text):
    if not raw_json_text:
        return {}
    try:
        data = json.loads(raw_json_text)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _to_minutes(clock_text):
    if not clock_text or ':' not in clock_text:
        return None
    try:
        hour, minute = clock_text.split(':', 1)
        return int(hour) * 60 + int(minute)
    except ValueError:
        return None


def _time_overlap_minutes(slot_a, slot_b):
    start_a = _to_minutes(slot_a.get('start'))
    end_a = _to_minutes(slot_a.get('end'))
    start_b = _to_minutes(slot_b.get('start'))
    end_b = _to_minutes(slot_b.get('end'))
    if None in (start_a, end_a, start_b, end_b):
        return 0
    overlap = min(end_a, end_b) - max(start_a, start_b)
    return max(0, overlap)


def _build_time_match_score(tutor_time_json, student_time_json):
    tutor_time = _parse_teaching_time(tutor_time_json)
    student_time = _parse_teaching_time(student_time_json)
    if not tutor_time or not student_time:
        return 0, '时间信息不足'

    total_overlap = 0
    overlap_days = 0
    for day in WEEKDAYS:
        if day in tutor_time and day in student_time:
            overlap = _time_overlap_minutes(tutor_time[day], student_time[day])
            if overlap > 0:
                overlap_days += 1
                total_overlap += overlap

    if total_overlap <= 0:
        return 0, '时间段重叠较少'

    score = min(25, overlap_days * 6 + total_overlap // 40)
    return int(score), f'有{overlap_days}天时间可对齐'


def _favorite_target_role_for_user(user_role):
    if user_role == 'student':
        return 'tutor'
    if user_role == 'tutor':
        return 'student'
    return None


def _get_user_favorite_ids(user_id, target_role):
    favorites = Favorite.query.filter_by(user_id=user_id, target_role=target_role).all()
    return {item.target_profile_id for item in favorites}


def _ensure_schema_updates():
    inspector = inspect(db.engine)

    tutor_columns = {col['name'] for col in inspector.get_columns('tutor_infos')}
    student_columns = {col['name'] for col in inspector.get_columns('student_infos')}

    if 'listing_active' not in tutor_columns:
        db.session.execute(text('ALTER TABLE tutor_infos ADD COLUMN listing_active BOOLEAN DEFAULT 1'))
    if 'listing_active' not in student_columns:
        db.session.execute(text('ALTER TABLE student_infos ADD COLUMN listing_active BOOLEAN DEFAULT 1'))
    db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', 'tutor')

        if not nickname or not password:
            flash('请填写所有必填项')
            return render_template('register.html', nickname=nickname, role=role)

        if User.query.filter_by(nickname=nickname).first():
            flash('昵称已存在，请更换')
            return render_template('register.html', nickname=nickname, role=role)

        if len(password) < 8:
            flash('密码至少8位')
            return render_template('register.html', nickname=nickname, role=role)

        if password != confirm_password:
            flash('两次密码不一致')
            return render_template('register.html', nickname=nickname, role=role)

        # Iteration spec keeps registration lightweight; persist empty strings for legacy non-null columns.
        if not phone:
            phone = ''
        if not email:
            email = ''

        user = User(nickname=nickname, phone=phone, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('注册成功，请登录')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(nickname=nickname).first()

        if not user:
            flash('用户不存在')
            return render_template('login.html', nickname=nickname)

        if not user.is_active:
            flash('账号已注销')
            return render_template('login.html', nickname=nickname)

        if user.check_password(password):
            login_user(user)
            if user.role == 'tutor':
                return redirect(url_for('tutor_home'))
            else:
                return redirect(url_for('student_home'))
        else:
            flash('密码错误')
            return render_template('login.html', nickname=nickname)

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/tutor/logout')
@login_required
def tutor_logout():
    logout_user('tutor')
    return redirect(url_for('index'))


@app.route('/student/logout')
@login_required
def student_logout():
    logout_user('student')
    return redirect(url_for('index'))


@app.route('/my')
@login_required
def my_center():
    query_endpoint = 'search_students' if current_user.role == 'tutor' else 'search_tutors'
    profile = None
    if current_user.role == 'tutor':
        profile = TutorInfo.query.filter_by(user_id=current_user.id).first()
    if current_user.role == 'student':
        profile = StudentInfo.query.filter_by(user_id=current_user.id).first()

    return render_template('my_center.html', profile=profile, query_endpoint=query_endpoint)


@app.route('/my/withdraw_listing', methods=['POST'])
@login_required
def withdraw_listing():
    if current_user.role == 'tutor':
        profile = TutorInfo.query.filter_by(user_id=current_user.id).first()
    else:
        profile = StudentInfo.query.filter_by(user_id=current_user.id).first()

    if not profile:
        flash('请先完善信息后再操作')
        return redirect(url_for('my_center'))

    current_active = profile.listing_active is not False
    profile.listing_active = not current_active
    db.session.commit()

    if profile.listing_active:
        flash('已重新发布需求，其他用户和AI助手可再次看到您的信息')
    else:
        flash('已撤回需求，其他用户与AI助手将不再看到您的信息')

    return redirect(url_for('my_center'))


@app.route('/favorite/toggle', methods=['POST'])
@login_required
def toggle_favorite():
    data = request.get_json(silent=True) or request.form
    target_role = (data.get('target_role') or '').strip()
    raw_target_profile_id = data.get('target_profile_id') if hasattr(data, 'get') else None
    try:
        target_profile_id = int(raw_target_profile_id)
    except (TypeError, ValueError):
        target_profile_id = None

    expected_target_role = _favorite_target_role_for_user(current_user.role)
    if target_role != expected_target_role or not target_profile_id:
        return jsonify({'error': '收藏目标不合法'}), 400

    if target_role == 'tutor':
        target = TutorInfo.query.get(target_profile_id)
    else:
        target = StudentInfo.query.get(target_profile_id)

    if not target:
        return jsonify({'error': '目标不存在'}), 404

    exists = Favorite.query.filter_by(
        user_id=current_user.id,
        target_role=target_role,
        target_profile_id=target_profile_id
    ).first()

    if exists:
        db.session.delete(exists)
        db.session.commit()
        return jsonify({'favorited': False})

    fav = Favorite(user_id=current_user.id, target_role=target_role, target_profile_id=target_profile_id)
    db.session.add(fav)
    db.session.commit()
    return jsonify({'favorited': True})


@app.route('/my/favorites')
@login_required
def my_favorites():
    target_role = _favorite_target_role_for_user(current_user.role)
    favorite_ids = _get_user_favorite_ids(current_user.id, target_role)

    tutors = []
    students = []
    if target_role == 'tutor' and favorite_ids:
        tutors = TutorInfo.query.join(User).filter(TutorInfo.id.in_(favorite_ids), User.is_active == True).order_by(TutorInfo.updated_at.desc()).all()
    if target_role == 'student' and favorite_ids:
        students = StudentInfo.query.join(User).filter(StudentInfo.id.in_(favorite_ids), User.is_active == True).order_by(StudentInfo.updated_at.desc()).all()

    return render_template(
        'my_favorites.html',
        target_role=target_role,
        tutors=tutors,
        students=students,
        favorite_ids=favorite_ids
    )


@app.route('/tutor/my')
@login_required
def tutor_my_center():
    session[ACTIVE_ROLE_KEY] = 'tutor'
    return my_center()


@app.route('/student/my')
@login_required
def student_my_center():
    session[ACTIVE_ROLE_KEY] = 'student'
    return my_center()


@app.route('/tutor/favorites')
@login_required
def tutor_my_favorites():
    session[ACTIVE_ROLE_KEY] = 'tutor'
    return my_favorites()


@app.route('/student/favorites')
@login_required
def student_my_favorites():
    session[ACTIVE_ROLE_KEY] = 'student'
    return my_favorites()

@app.route('/tutor/home')
@login_required
def tutor_home():
    if current_user.role != 'tutor':
        return redirect(url_for('index'))
    tutor_info = TutorInfo.query.filter_by(user_id=current_user.id).first()
    return render_template('tutor_info.html', tutor_info=tutor_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='home')

@app.route('/tutor/info', methods=['GET', 'POST'])
@login_required
def tutor_info():
    if current_user.role != 'tutor':
        return redirect(url_for('index'))

    tutor_info = TutorInfo.query.filter_by(user_id=current_user.id).first()

    if request.method == 'POST':
        gender = request.form.get('gender')
        selected_subjects = request.form.getlist('subjects')
        selected_grades = request.form.getlist('grades')
        teaching_mode = ','.join(request.form.getlist('teaching_mode'))
        fee = request.form.get('fee', type=int)
        introduction = request.form.get('introduction', '').strip()
        wechat = request.form.get('wechat', '').strip()
        accept_opposite_gender = 'accept_opposite_gender' in request.form

        if not gender:
            flash('请选择性别')
            return render_template('tutor_info.html', tutor_info=tutor_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if not selected_subjects:
            flash('请至少选择1个擅长科目')
            return render_template('tutor_info.html', tutor_info=tutor_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if not selected_grades:
            flash('请至少选择1个授课年级')
            return render_template('tutor_info.html', tutor_info=tutor_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if not teaching_mode:
            flash('请至少选择1种授课方式')
            return render_template('tutor_info.html', tutor_info=tutor_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if fee is None or fee < 0 or fee > 1000:
            flash('费用范围为0-1000元')
            return render_template('tutor_info.html', tutor_info=tutor_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if not introduction or len(introduction) > 50:
            flash('自我介绍必填且不超过50字')
            return render_template('tutor_info.html', tutor_info=tutor_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')

        teaching_time_data = {}
        for day in WEEKDAYS:
            if request.form.get(f'time_enabled_{day}'):
                start = request.form.get(f'time_start_{day}')
                end = request.form.get(f'time_end_{day}')
                if start and end:
                    teaching_time_data[day] = {'start': start, 'end': end}

        avatar_path = tutor_info.avatar_path if tutor_info else None
        if 'avatar' in request.files:
            file = request.files['avatar']
            saved_avatar = save_avatar(file, 'tutor', current_user.id)
            if saved_avatar:
                avatar_path = saved_avatar

        if tutor_info:
            tutor_info.gender = gender
            tutor_info.avatar_path = avatar_path
            tutor_info.subjects = ','.join(selected_subjects)
            tutor_info.grades = ','.join(selected_grades)
            tutor_info.teaching_mode = teaching_mode
            tutor_info.fee = fee
            tutor_info.teaching_time = json.dumps(teaching_time_data)
            tutor_info.introduction = introduction
            tutor_info.wechat = wechat
            tutor_info.accept_opposite_gender = accept_opposite_gender
        else:
            tutor_info = TutorInfo(
                user_id=current_user.id,
                gender=gender,
                avatar_path=avatar_path,
                subjects=','.join(selected_subjects),
                grades=','.join(selected_grades),
                teaching_mode=teaching_mode,
                fee=fee,
                teaching_time=json.dumps(teaching_time_data),
                introduction=introduction,
                wechat=wechat,
                accept_opposite_gender=accept_opposite_gender
            )
            db.session.add(tutor_info)

        db.session.commit()
        flash('保存成功')
        return redirect(url_for('tutor_home'))

    teaching_time = json.loads(tutor_info.teaching_time) if tutor_info and tutor_info.teaching_time else {}
    return render_template('tutor_info.html', tutor_info=tutor_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, teaching_time=teaching_time, mode='edit')

@app.route('/student/home')
@login_required
def student_home():
    if current_user.role != 'student':
        return redirect(url_for('index'))
    student_info = StudentInfo.query.filter_by(user_id=current_user.id).first()
    return render_template('student_info.html', student_info=student_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='home')

@app.route('/student/info', methods=['GET', 'POST'])
@login_required
def student_info():
    if current_user.role != 'student':
        return redirect(url_for('index'))

    student_info = StudentInfo.query.filter_by(user_id=current_user.id).first()

    if request.method == 'POST':
        gender = request.form.get('gender')
        selected_subjects = request.form.getlist('subjects')
        grade = request.form.get('grade')
        teaching_mode = ','.join(request.form.getlist('teaching_mode'))
        budget_upper = request.form.get('budget_upper', type=int)
        requirements = request.form.get('requirements', '').strip()
        wechat = request.form.get('wechat', '').strip()
        accept_opposite_gender = 'accept_opposite_gender' in request.form

        if not gender:
            flash('请选择性别')
            return render_template('student_info.html', student_info=student_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if not selected_subjects:
            flash('请至少选择1个科目')
            return render_template('student_info.html', student_info=student_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if not grade:
            flash('请选择年级')
            return render_template('student_info.html', student_info=student_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if not teaching_mode:
            flash('请至少选择1种授课方式')
            return render_template('student_info.html', student_info=student_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')
        if requirements and len(requirements) > 50:
            flash('补充要求不超过50字')
            return render_template('student_info.html', student_info=student_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, mode='edit')

        teaching_time_data = {}
        for day in WEEKDAYS:
            if request.form.get(f'time_enabled_{day}'):
                start = request.form.get(f'time_start_{day}')
                end = request.form.get(f'time_end_{day}')
                if start and end:
                    teaching_time_data[day] = {'start': start, 'end': end}

        avatar_path = student_info.avatar_path if student_info else None
        if 'avatar' in request.files:
            file = request.files['avatar']
            saved_avatar = save_avatar(file, 'student', current_user.id)
            if saved_avatar:
                avatar_path = saved_avatar

        if student_info:
            student_info.gender = gender
            student_info.avatar_path = avatar_path
            student_info.subjects = ','.join(selected_subjects)
            student_info.grade = grade
            student_info.teaching_mode = teaching_mode
            student_info.budget_upper = budget_upper
            student_info.teaching_time = json.dumps(teaching_time_data)
            student_info.requirements = requirements
            student_info.wechat = wechat
            student_info.accept_opposite_gender = accept_opposite_gender
        else:
            student_info = StudentInfo(
                user_id=current_user.id,
                gender=gender,
                avatar_path=avatar_path,
                subjects=','.join(selected_subjects),
                grade=grade,
                teaching_mode=teaching_mode,
                budget_upper=budget_upper,
                teaching_time=json.dumps(teaching_time_data),
                requirements=requirements,
                wechat=wechat,
                accept_opposite_gender=accept_opposite_gender
            )
            db.session.add(student_info)

        db.session.commit()
        flash('保存成功')
        return redirect(url_for('student_home'))

    teaching_time = json.loads(student_info.teaching_time) if student_info and student_info.teaching_time else {}
    return render_template('student_info.html', student_info=student_info, subjects=SUBJECTS, grades=GRADES, teaching_modes=TEACHING_MODES, weekdays=WEEKDAYS, teaching_time=teaching_time, mode='edit')

@app.route('/student/search_tutors')
@login_required
def search_tutors():
    if current_user.role != 'student':
        return redirect(url_for('index'))

    student_info = StudentInfo.query.filter_by(user_id=current_user.id).first()
    if not student_info:
        flash('请先填写需求信息')
        return redirect(url_for('student_info'))

    query = TutorInfo.query.join(User).filter(
        User.is_active == True,
        db.or_(TutorInfo.listing_active == True, TutorInfo.listing_active.is_(None))
    )

    if student_info.subjects:
        subject_list = student_info.subjects.split(',')
        conditions = [TutorInfo.subjects.contains(s) for s in subject_list]
        query = query.filter(db.or_(*conditions))

    if student_info.accept_opposite_gender == False:
        query = query.filter(TutorInfo.gender == student_info.gender)

    # 年级匹配：只显示教该学生年级的家教
    if student_info.grade:
        query = query.filter(TutorInfo.grades.contains(student_info.grade))

    sort = request.args.get('sort', 'newest')
    fee_min = request.args.get('fee_min', type=int)
    fee_max = request.args.get('fee_max', type=int)
    teaching_mode_filter = request.args.getlist('teaching_mode')

    if teaching_mode_filter:
        conditions = []
        for mode in teaching_mode_filter:
            conditions.append(TutorInfo.teaching_mode.contains(mode))
        query = query.filter(db.or_(*conditions))

    if fee_min:
        query = query.filter(TutorInfo.fee >= fee_min)
    if fee_max:
        query = query.filter(TutorInfo.fee <= fee_max)

    if sort == 'lowest_fee':
        query = query.order_by(TutorInfo.fee.asc())
    else:
        query = query.order_by(TutorInfo.updated_at.desc())

    tutors = query.all()
    favorite_ids = _get_user_favorite_ids(current_user.id, 'tutor')

    # 获取每个家教的平均评分
    tutor_ratings = {}
    tutor_ids = [t.id for t in tutors]
    if tutor_ids:
        rating_data = db.session.query(
            Review.tutor_id,
            db.func.avg(Review.rating).label('avg_rating'),
            db.func.count(Review.id).label('count')
        ).filter(Review.tutor_id.in_(tutor_ids)).group_by(Review.tutor_id).all()

        for tutor_id, avg_rating, count in rating_data:
            tutor_ratings[tutor_id] = {
                'avg': round(avg_rating, 1) if avg_rating else None,
                'count': count
            }

    best_match = None
    best_explanation = ''
    best_score = 0
    if tutors:
        scored = []
        for tutor in tutors:
            score, reasons = _score_tutor_for_student(student_info, tutor)
            scored.append((score, reasons, tutor))
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_reasons, best_match = scored[0]
        best_explanation = '；'.join(best_reasons[:3]) if best_reasons else '满足基础筛选条件'

    return render_template(
        'search_tutors.html',
        tutors=tutors,
        student_info=student_info,
        teaching_modes=TEACHING_MODES,
        sort=sort,
        fee_min=fee_min or '',
        fee_max=fee_max or '',
        teaching_mode_filter=teaching_mode_filter,
        favorite_ids=favorite_ids,
        best_match=best_match,
        best_score=best_score,
        best_explanation=best_explanation,
        tutor_ratings=tutor_ratings
    )

@app.route('/student/tutor_detail/<int:tutor_id>')
@login_required
def tutor_detail(tutor_id):
    if current_user.role != 'student':
        return redirect(url_for('index'))
    tutor = TutorInfo.query.get_or_404(tutor_id)
    tutor_teaching_time = {}
    if tutor.teaching_time:
        try:
            tutor_teaching_time = json.loads(tutor.teaching_time)
        except (TypeError, json.JSONDecodeError):
            tutor_teaching_time = {}
    return render_template('tutor_detail.html', tutor=tutor, tutor_teaching_time=tutor_teaching_time)

@app.route('/tutor/search_students')
@login_required
def search_students():
    if current_user.role != 'tutor':
        return redirect(url_for('index'))

    tutor_info = TutorInfo.query.filter_by(user_id=current_user.id).first()
    if not tutor_info:
        flash('请先填写授课信息')
        return redirect(url_for('tutor_info'))

    query = StudentInfo.query.join(User).filter(
        User.is_active == True,
        db.or_(StudentInfo.listing_active == True, StudentInfo.listing_active.is_(None))
    )

    if tutor_info.subjects:
        subject_list = tutor_info.subjects.split(',')
        conditions = [StudentInfo.subjects.contains(s) for s in subject_list]
        query = query.filter(db.or_(*conditions))

    if tutor_info.accept_opposite_gender == False:
        query = query.filter(StudentInfo.gender == tutor_info.gender)

    sort = request.args.get('sort', 'newest')
    grade_filter = request.args.getlist('grade')
    subject_filter = request.args.getlist('subject')
    teaching_mode_filter = request.args.getlist('teaching_mode')
    budget_min = request.args.get('budget_min', type=int)
    budget_max = request.args.get('budget_max', type=int)

    if grade_filter:
        query = query.filter(StudentInfo.grade.in_(grade_filter))

    if subject_filter:
        conditions = [StudentInfo.subjects.contains(s) for s in subject_filter]
        query = query.filter(db.or_(*conditions))

    if teaching_mode_filter:
        conditions = []
        for mode in teaching_mode_filter:
            conditions.append(StudentInfo.teaching_mode.contains(mode))
        query = query.filter(db.or_(*conditions))

    if budget_min:
        query = query.filter(StudentInfo.budget_upper >= budget_min)
    if budget_max:
        query = query.filter(StudentInfo.budget_upper <= budget_max)

    if sort == 'highest_budget':
        query = query.order_by(StudentInfo.budget_upper.desc().nullslast())
    else:
        query = query.order_by(StudentInfo.updated_at.desc())

    students = query.all()
    favorite_ids = _get_user_favorite_ids(current_user.id, 'student')

    best_match = None
    best_explanation = ''
    best_score = 0
    if students:
        scored = []
        for student in students:
            score, reasons = _score_student_for_tutor(tutor_info, student)
            scored.append((score, reasons, student))
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_reasons, best_match = scored[0]
        best_explanation = '；'.join(best_reasons[:3]) if best_reasons else '满足基础筛选条件'

    return render_template(
        'search_students.html',
        students=students,
        tutor_info=tutor_info,
        subjects=SUBJECTS,
        grades=GRADES,
        teaching_modes=TEACHING_MODES,
        sort=sort,
        grade_filter=grade_filter or [],
        subject_filter=subject_filter or [],
        teaching_mode_filter=teaching_mode_filter or [],
        budget_min=budget_min or '',
        budget_max=budget_max or '',
        favorite_ids=favorite_ids,
        best_match=best_match,
        best_score=best_score,
        best_explanation=best_explanation
    )

@app.route('/tutor/student_detail/<int:student_id>')
@login_required
def student_detail(student_id):
    if current_user.role != 'tutor':
        return redirect(url_for('index'))
    student = StudentInfo.query.get_or_404(student_id)
    student_teaching_time = {}
    if student.teaching_time:
        try:
            student_teaching_time = json.loads(student.teaching_time)
        except (TypeError, json.JSONDecodeError):
            student_teaching_time = {}
    return render_template('student_detail.html', student=student, student_teaching_time=student_teaching_time)

@app.route('/deactivate', methods=['POST'])
@login_required
def deactivate():
    current_user.is_active = False
    db.session.commit()
    logout_user()
    flash('账号已注销')
    return redirect(url_for('index'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        admin = Admin.query.filter_by(username=username).first()
        if not admin or not admin.check_password(password):
            flash('用户名或密码错误')
            return render_template('admin/login.html', username=username)

        session['admin_id'] = admin.id
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    sort = request.args.get('sort', 'created_at')
    if sort == 'nickname':
        users = User.query.order_by(User.nickname).all()
    elif sort == 'role':
        users = User.query.order_by(User.role).all()
    else:
        users = User.query.order_by(User.created_at.desc()).all()

    return render_template('admin/dashboard.html', users=users, sort=sort)

@app.route('/admin/change_password/<int:user_id>', methods=['POST'])
def admin_change_password(user_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    new_password = request.form.get('new_password', '')
    if len(new_password) < 8:
        flash('密码至少8位')
        return redirect(url_for('admin_dashboard'))

    user = User.query.get(user_id)
    if user:
        user.set_password(new_password)
        db.session.commit()
        flash('密码修改成功')
    return redirect(url_for('admin_dashboard'))

def init_db():
    with app.app_context():
        db.create_all()
        _ensure_schema_updates()
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            admin = Admin(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('管理员账号已创建: admin / admin123')


def _split_csv_values(raw_text):
    if not raw_text:
        return []
    return [item.strip() for item in raw_text.split(',') if item and item.strip()]


def _build_fee_stats(fees):
    if not fees:
        return {
            'count': 0,
            'min': None,
            'max': None,
            'avg': None,
            'median': None
        }

    fees_sorted = sorted(fees)
    return {
        'count': len(fees_sorted),
        'min': fees_sorted[0],
        'max': fees_sorted[-1],
        'avg': round(mean(fees_sorted), 2),
        'median': round(median(fees_sorted), 2)
    }


def _dedupe_keep_order(items):
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _build_llm_backends():
    backends = []
    if SILICONFLOW_API_KEY:
        backends.append({'name': 'siliconflow', 'url': SILICONFLOW_API_URL, 'api_key': SILICONFLOW_API_KEY})
    if OPENROUTER_API_KEY:
        backends.append({'name': 'openrouter', 'url': OPENROUTER_API_URL, 'api_key': OPENROUTER_API_KEY})
    return backends


def _build_local_fallback_reply(message, db_context):
    overview = db_context.get('overview', {})
    active_users = overview.get('active_user_count', 0)
    active_tutors = overview.get('active_tutor_profile_count', 0)
    active_students = overview.get('active_student_profile_count', 0)
    top_subjects = overview.get('top_student_requested_subjects', [])

    top_subject_text = '、'.join([item[0] for item in top_subjects[:3]]) if top_subjects else '暂无统计'
    msg = (message or '').strip()

    if '多少' in msg or '人数' in msg or '数量' in msg:
        return (
            f"当前系统可见数据概览：活跃用户{active_users}人，"
            f"可见家教档案{active_tutors}份，可见学生需求{active_students}份。"
        )

    if '科目' in msg or '热门' in msg:
        return f"当前需求较多的科目前三是：{top_subject_text}。如需我再按授课方式或价格细分，请继续提问。"

    return (
        "当前外部大模型服务暂时不可用，我先基于本地统计给你一个快速结论："
        f"活跃用户{active_users}人、可见家教{active_tutors}人、可见需求{active_students}人，热门科目包括{top_subject_text}。"
        "你可以继续问价格区间、匹配数量、筛选规则，我会优先用本地数据回答。"
    )


def _match_tutor_and_student(tutor, student):
    tutor_subjects = set(_split_csv_values(tutor.subjects))
    student_subjects = set(_split_csv_values(student.subjects))
    has_subject_overlap = len(tutor_subjects.intersection(student_subjects)) > 0

    if not has_subject_overlap:
        return False

    if tutor.accept_opposite_gender is False and tutor.gender != student.gender:
        return False
    if student.accept_opposite_gender is False and student.gender != tutor.gender:
        return False

    return True


def _score_tutor_for_student(student_info, tutor):
    score = 0
    reasons = []

    student_subjects = set(_split_csv_values(student_info.subjects))
    tutor_subjects = set(_split_csv_values(tutor.subjects))
    subject_overlap = student_subjects.intersection(tutor_subjects)
    if subject_overlap:
        score += min(28, 10 + len(subject_overlap) * 9)
        reasons.append(f"科目匹配: {','.join(sorted(subject_overlap))}")

    tutor_grades = set(_split_csv_values(tutor.grades))
    if student_info.grade in tutor_grades:
        score += 18
        reasons.append('年级覆盖匹配')

    student_modes = set(_split_csv_values(student_info.teaching_mode))
    tutor_modes = set(_split_csv_values(tutor.teaching_mode))
    mode_overlap = student_modes.intersection(tutor_modes)
    if mode_overlap:
        score += 14
        reasons.append(f"授课方式匹配: {','.join(sorted(mode_overlap))}")

    if student_info.budget_upper and tutor.fee:
        if tutor.fee <= student_info.budget_upper:
            score += 18
            reasons.append('费用在预算内')
        else:
            score += max(0, 18 - (tutor.fee - student_info.budget_upper) // 10)
            reasons.append('费用略高于预算')

    time_score, time_reason = _build_time_match_score(tutor.teaching_time, student_info.teaching_time)
    score += time_score
    if time_score > 0:
        reasons.append(time_reason)

    return min(100, int(score)), reasons


def _score_student_for_tutor(tutor_info, student):
    score = 0
    reasons = []

    tutor_subjects = set(_split_csv_values(tutor_info.subjects))
    student_subjects = set(_split_csv_values(student.subjects))
    subject_overlap = tutor_subjects.intersection(student_subjects)
    if subject_overlap:
        score += min(30, 10 + len(subject_overlap) * 10)
        reasons.append(f"科目匹配: {','.join(sorted(subject_overlap))}")

    tutor_grades = set(_split_csv_values(tutor_info.grades))
    if student.grade in tutor_grades:
        score += 17
        reasons.append('授课年级匹配')

    tutor_modes = set(_split_csv_values(tutor_info.teaching_mode))
    student_modes = set(_split_csv_values(student.teaching_mode))
    mode_overlap = tutor_modes.intersection(student_modes)
    if mode_overlap:
        score += 14
        reasons.append(f"授课方式匹配: {','.join(sorted(mode_overlap))}")

    if tutor_info.fee and student.budget_upper:
        if student.budget_upper >= tutor_info.fee:
            score += 16
            reasons.append('预算可覆盖费用')
        else:
            score += max(0, 16 - (tutor_info.fee - student.budget_upper) // 10)
            reasons.append('预算略低于期望费用')

    time_score, time_reason = _build_time_match_score(tutor_info.teaching_time, student.teaching_time)
    score += time_score
    if time_score > 0:
        reasons.append(time_reason)

    return min(100, int(score)), reasons


def build_assistant_db_context():
    active_users = User.query.filter_by(is_active=True).all()
    active_tutors = TutorInfo.query.join(User).filter(
        User.is_active == True,
        db.or_(TutorInfo.listing_active == True, TutorInfo.listing_active.is_(None))
    ).all()
    active_students = StudentInfo.query.join(User).filter(
        User.is_active == True,
        db.or_(StudentInfo.listing_active == True, StudentInfo.listing_active.is_(None))
    ).all()

    tutor_subject_counter = Counter()
    for tutor in active_tutors:
        tutor_subject_counter.update(_split_csv_values(tutor.subjects))

    student_subject_counter = Counter()
    for student in active_students:
        student_subject_counter.update(_split_csv_values(student.subjects))

    all_fees = [t.fee for t in active_tutors if isinstance(t.fee, int)]

    fee_by_subject = {}
    for subject in SUBJECTS:
        subject_fees = []
        for tutor in active_tutors:
            tutor_subjects = _split_csv_values(tutor.subjects)
            if subject in tutor_subjects and isinstance(tutor.fee, int):
                subject_fees.append(tutor.fee)
        stats = _build_fee_stats(subject_fees)
        if stats['count'] > 0:
            fee_by_subject[subject] = stats

    fee_by_mode = {}
    for mode in TEACHING_MODES:
        mode_fees = []
        for tutor in active_tutors:
            modes = _split_csv_values(tutor.teaching_mode)
            if mode in modes and isinstance(tutor.fee, int):
                mode_fees.append(tutor.fee)
        stats = _build_fee_stats(mode_fees)
        if stats['count'] > 0:
            fee_by_mode[mode] = stats

    context = {
        'overview': {
            'active_user_count': len(active_users),
            'active_tutor_profile_count': len(active_tutors),
            'active_student_profile_count': len(active_students),
            'top_tutor_subjects': tutor_subject_counter.most_common(5),
            'top_student_requested_subjects': student_subject_counter.most_common(5),
            'fee_overview': _build_fee_stats(all_fees),
            'fee_by_subject': fee_by_subject,
            'fee_by_teaching_mode': fee_by_mode
        },
        'current_user': {
            'is_authenticated': bool(current_user.is_authenticated)
        }
    }

    if current_user.is_authenticated:
        context['current_user']['id'] = current_user.id
        context['current_user']['nickname'] = current_user.nickname
        context['current_user']['role'] = current_user.role

        if current_user.role == 'tutor':
            tutor_info = TutorInfo.query.filter_by(user_id=current_user.id).first()
            if tutor_info:
                matched_students = [
                    s for s in active_students if _match_tutor_and_student(tutor_info, s)
                ]
                subject_set = set(_split_csv_values(tutor_info.subjects))
                mode_set = set(_split_csv_values(tutor_info.teaching_mode))
                comparable_tutor_fees = []
                for tutor in active_tutors:
                    if not isinstance(tutor.fee, int):
                        continue
                    if tutor.id == tutor_info.id:
                        continue
                    tutor_subjects = set(_split_csv_values(tutor.subjects))
                    tutor_modes = set(_split_csv_values(tutor.teaching_mode))
                    if tutor_subjects.intersection(subject_set) and tutor_modes.intersection(mode_set):
                        comparable_tutor_fees.append(tutor.fee)
                context['current_user']['tutor_profile'] = {
                    'subjects': _split_csv_values(tutor_info.subjects),
                    'grades': _split_csv_values(tutor_info.grades),
                    'teaching_mode': _split_csv_values(tutor_info.teaching_mode),
                    'fee': tutor_info.fee,
                    'estimated_match_count': len(matched_students),
                    'comparable_fee_stats': _build_fee_stats(comparable_tutor_fees)
                }
            else:
                context['current_user']['tutor_profile'] = {'missing_profile': True}

        if current_user.role == 'student':
            student_info = StudentInfo.query.filter_by(user_id=current_user.id).first()
            if student_info:
                matched_tutors = [
                    t for t in active_tutors if _match_tutor_and_student(t, student_info)
                ]
                context['current_user']['student_profile'] = {
                    'subjects': _split_csv_values(student_info.subjects),
                    'grade': student_info.grade,
                    'teaching_mode': _split_csv_values(student_info.teaching_mode),
                    'budget_upper': student_info.budget_upper,
                    'estimated_match_count': len(matched_tutors)
                }
            else:
                context['current_user']['student_profile'] = {'missing_profile': True}

    return context


@app.route('/assistant')
def assistant_page():
    return render_template('assistant.html')


@app.route('/api/assistant/chat', methods=['POST'])
def assistant_chat():
    payload = request.get_json(silent=True) or {}
    message = (payload.get('message') or '').strip()
    history = payload.get('history') or []

    if not message:
        return jsonify({'error': '消息不能为空'}), 400

    llm_backends = _build_llm_backends()

    requested_model = (payload.get('model') or '').strip()
    candidate_models = []
    if requested_model:
        candidate_models.append(requested_model)
    candidate_models.extend(MODEL_CANDIDATES)
    candidate_models.append(DEFAULT_MODEL)
    candidate_models = _dedupe_keep_order(candidate_models)

    safe_history = []
    for item in history[-10:]:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = (item.get('content') or '').strip()
        if role in ('user', 'assistant') and content:
            safe_history.append({'role': role, 'content': content[:1000]})

    db_context = build_assistant_db_context()
    system_prompt = (
        '你是家教服务系统的智能助手。你必须使用给出的数据库上下文和系统设计知识来回答。'
        '回答要求：1) 使用中文；2) 不编造数据库中没有的信息；'
        '3) 如果用户询问敏感信息（如密码、手机号、邮箱），请拒绝并提示隐私保护；'
        '4) 当问题超出家教系统范围时，明确告知可回答范围；'
        '5) 当用户询问价格是否合适时，先引用对应科目/授课方式/可比样本统计，再给建议。'
    )
    user_prompt = (
        f"数据库上下文(JSON)：{json.dumps(db_context, ensure_ascii=False)}\n"
        f"系统设计知识(JSON)：{json.dumps(ASSISTANT_PLATFORM_KNOWLEDGE, ensure_ascii=False)}\n"
        f"用户问题：{message}"
    )

    common_messages = [
        {'role': 'system', 'content': system_prompt},
        *safe_history,
        {'role': 'user', 'content': user_prompt}
    ]

    errors = []
    for backend in llm_backends:
        headers = {
            'Authorization': f"Bearer {backend['api_key']}",
            'Content-Type': 'application/json'
        }

        for model_name in candidate_models:
            payload_data = {
                'model': model_name,
                'messages': common_messages,
                'stream': False,
                'temperature': 0.3
            }

            try:
                upstream_resp = requests.post(
                    backend['url'],
                    headers=headers,
                    json=payload_data,
                    timeout=LLM_REQUEST_TIMEOUT
                )
            except requests.RequestException as exc:
                errors.append(f"{backend['name']}::{model_name}: 请求异常 {exc}")
                continue

            if not upstream_resp.ok:
                errors.append(f"{backend['name']}::{model_name}: 状态码 {upstream_resp.status_code}, 详情 {upstream_resp.text[:120]}")
                continue

            try:
                data = upstream_resp.json()
                reply = data['choices'][0]['message']['content'].strip()
                return jsonify({
                    'reply': reply,
                    'model': model_name,
                    'backend': backend['name'],
                    'fallback_used': (backend != llm_backends[0]) or (model_name != candidate_models[0])
                })
            except (ValueError, KeyError, IndexError, TypeError):
                errors.append(f"{backend['name']}::{model_name}: 响应格式异常")
                continue

    # All external APIs failed: degrade gracefully to deterministic local answer.
    fallback_reply = _build_local_fallback_reply(message, db_context)
    return jsonify({
        'reply': fallback_reply,
        'model': 'local-fallback',
        'backend': 'local',
        'fallback_used': True,
        'warnings': errors[-4:]
    })


# ========== 评价功能相关路由 ==========

@app.route('/tutor/<int:tutor_id>/reviews')
@login_required
def tutor_reviews(tutor_id):
    tutor = TutorInfo.query.get_or_404(tutor_id)
    reviews = Review.query.filter_by(tutor_id=tutor_id).order_by(Review.created_at.desc()).all()
    avg_rating = db.session.query(db.func.avg(Review.rating)).filter_by(tutor_id=tutor_id).scalar()

    user_review = None
    if current_user.role == 'student':
        user_review = Review.query.filter_by(student_id=current_user.id, tutor_id=tutor_id).first()

    return render_template('tutor_reviews.html', tutor=tutor, reviews=reviews,
                           avg_rating=avg_rating, user_review=user_review)


@app.route('/review/add/<int:tutor_id>', methods=['GET'])
@login_required
def display_add_review(tutor_id):
    if current_user.role != 'student':
        flash('仅学生可以评价家教')
        return redirect(url_for('index'))

    tutor = TutorInfo.query.get_or_404(tutor_id)

    # 检查是否已有评价
    existing_review = Review.query.filter_by(student_id=current_user.id, tutor_id=tutor_id).first()

    return render_template('add_review.html', tutor=tutor, review=existing_review, is_edit=existing_review is not None)


@app.route('/api/reviews/add', methods=['POST'])
@login_required
def add_review():
    if current_user.role != 'student':
        return jsonify({'error': '仅学生可以评价家教'}), 403

    data = request.get_json(silent=True) or {}
    tutor_id = data.get('tutor_id')
    rating = data.get('rating')
    comment = (data.get('comment') or '').strip()[:100]

    if not tutor_id or not rating:
        return jsonify({'error': '参数不完整'}), 400
    if not (1 <= int(rating) <= 5):
        return jsonify({'error': '评分必须是1-5'}), 400

    tutor = TutorInfo.query.get_or_404(tutor_id)

    existing = Review.query.filter_by(student_id=current_user.id, tutor_id=tutor_id).first()
    if existing:
        return jsonify({'error': '您已经评价过这位家教'}), 400

    review = Review(
        student_id=current_user.id,
        tutor_id=tutor_id,
        rating=int(rating),
        comment=comment
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({'message': '评价成功', 'review_id': review.id})


@app.route('/api/reviews/<int:review_id>/edit', methods=['PUT'])
@login_required
def edit_review(review_id):
    review = Review.query.get_or_404(review_id)

    if review.student_id != current_user.id:
        return jsonify({'error': '无权修改'}), 403

    data = request.get_json(silent=True) or {}
    rating = data.get('rating')
    comment = data.get('comment')

    if rating is not None:
        if not (1 <= int(rating) <= 5):
            return jsonify({'error': '评分必须是1-5'}), 400
        review.rating = int(rating)

    if comment is not None:
        review.comment = comment.strip()[:100]

    db.session.commit()
    return jsonify({'message': '修改成功'})


@app.route('/api/reviews/<int:review_id>', methods=['DELETE'])
@login_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)

    if review.student_id != current_user.id:
        return jsonify({'error': '无权删除'}), 403

    db.session.delete(review)
    db.session.commit()
    return jsonify({'message': '删除成功'})


@app.route('/my/reviews')
@login_required
def my_reviews():
    if current_user.role != 'student':
        flash('仅学生可以查看')
        return redirect(url_for('my_center'))

    reviews = Review.query.filter_by(student_id=current_user.id).order_by(Review.updated_at.desc()).all()
    return render_template('my_reviews.html', reviews=reviews)


@app.route('/my/received_reviews')
@login_required
def received_reviews():
    if current_user.role != 'tutor':
        flash('仅家教可以查看')
        return redirect(url_for('my_center'))

    if not current_user.tutor_info:
        flash('请先完善家教信息')
        return redirect(url_for('tutor_info'))

    reviews = Review.query.filter_by(tutor_id=current_user.tutor_info.id).order_by(Review.created_at.desc()).all()
    avg_rating = db.session.query(db.func.avg(Review.rating)).filter_by(tutor_id=current_user.tutor_info.id).scalar()

    return render_template('received_reviews.html', reviews=reviews, avg_rating=avg_rating)


@app.route('/api/tutor/<int:tutor_id>/rating')
def get_tutor_rating(tutor_id):
    avg_rating = db.session.query(db.func.avg(Review.rating)).filter_by(tutor_id=tutor_id).scalar()
    count = Review.query.filter_by(tutor_id=tutor_id).count()
    return jsonify({
        'avg_rating': round(avg_rating, 1) if avg_rating else None,
        'count': count
    })


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
