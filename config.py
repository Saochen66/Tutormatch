import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_local_env_file():
    env_path = os.path.join(BASE_DIR, '.env')
    if not os.path.exists(env_path):
        return

    with open(env_path, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                current = os.environ.get(key)
                if current is None or str(current).strip() == '':
                    os.environ[key] = value


_load_local_env_file()


def _load_or_create_secret_key():
    env_secret = os.environ.get('SECRET_KEY', '').strip()
    if env_secret:
        return env_secret

    secret_file = os.path.join(BASE_DIR, '.secret_key')
    if os.path.exists(secret_file):
        with open(secret_file, 'r', encoding='utf-8') as f:
            saved_key = f.read().strip()
        if saved_key:
            return saved_key

    generated_key = secrets.token_hex(32)
    with open(secret_file, 'w', encoding='utf-8') as f:
        f.write(generated_key)
    return generated_key

class Config:
    SECRET_KEY = _load_or_create_secret_key()
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'tutor_service.db').replace('\\', '/')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
    NVIDIA_API_KEY = os.environ.get('NVIDIA_API_KEY', '').strip()
    NVIDIA_API_URL = os.environ.get('NVIDIA_API_URL', 'https://integrate.api.nvidia.com/v1/chat/completions').strip()
    NVIDIA_MODEL = os.environ.get('NVIDIA_MODEL', 'qwen/qwen3.5-397b-a17b').strip()
    NVIDIA_MODELS = [
        item.strip() for item in os.environ.get(
            'NVIDIA_MODELS',
            'qwen/qwen3.5-397b-a17b,meta/llama-3.1-70b-instruct,mistralai/mixtral-8x7b-instruct-v0.1,qwen/qwen2.5-72b-instruct'
        ).split(',') if item.strip()
    ]
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY', '').strip()
    OPENROUTER_API_URL = os.environ.get('OPENROUTER_API_URL', 'https://openrouter.ai/api/v1/chat/completions').strip()
    SILICONFLOW_API_KEY = os.environ.get('SILICONFLOW_API_KEY', '').strip()
    SILICONFLOW_API_URL = os.environ.get('SILICONFLOW_API_URL', 'https://api.siliconflow.cn/v1/chat/completions').strip()
    SILICONFLOW_MODEL = os.environ.get('SILICONFLOW_MODEL', 'internlm/internlm2_5-7b-chat').strip()
    SILICONFLOW_MODELS = [
        item.strip() for item in os.environ.get(
            'SILICONFLOW_MODELS',
            'internlm/internlm2_5-7b-chat'
        ).split(',') if item.strip()
    ]
    LLM_REQUEST_TIMEOUT = int(os.environ.get('LLM_REQUEST_TIMEOUT', '22'))

SUBJECTS = ['语文', '数学', '英语', '物理', '化学', '生物', '政治', '历史', '地理', '体育']
GRADES = ['一年级', '二年级', '三年级', '四年级', '五年级', '六年级', '初一', '初二', '初三', '高一', '高二', '高三']
TEACHING_MODES = ['线上', '线下']
WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
