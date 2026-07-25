"""
database.py - Conexión a PostgreSQL para Visual Agent AI
Con fallback a users.json cuando PostgreSQL no está disponible.
"""
import json
import os
from datetime import datetime

USERS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.json')

def _load_users_json():
    """Cargar usuarios desde users.json"""
    if not os.path.exists(USERS_JSON_PATH):
        return {}
    try:
        with open(USERS_JSON_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _save_users_json(data):
    """Guardar usuarios en users.json"""
    try:
        with open(USERS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False

def _get_user_from_json(username):
    """Buscar usuario en users.json y retornar dict compatible con PostgreSQL"""
    users = _load_users_json()
    if username not in users:
        return None

    user_data = users[username]
    if isinstance(user_data, str):
        return {
            'id': hash(username) % 100000,
            'username': username,
            'password': user_data,
            'role': 'desarrollador',
            'secret_question': None,
            'secret_answer': None,
            'email': None
        }
    elif isinstance(user_data, dict):
        return {
            'id': hash(username) % 100000,
            'username': username,
            'password': user_data.get('password', ''),
            'role': user_data.get('role', 'desarrollador'),
            'secret_question': user_data.get('secret_question'),
            'secret_answer': user_data.get('secret_answer'),
            'email': user_data.get('email'),
            'last_login': user_data.get('last_login')
        }
    return None

def _create_user_in_json(username, password, secret_question, secret_answer, email=None):
    """Crear usuario en users.json"""
    users = _load_users_json()
    if username in users:
        return False
    users[username] = {
        'password': password,
        'role': 'desarrollador',
        'secret_question': secret_question,
        'secret_answer': secret_answer,
        'email': email or '',
        'created_at': datetime.now().isoformat(),
        'last_login': None
    }
    return _save_users_json(users)

def _update_password_in_json(username, new_password):
    """Actualizar contraseña en users.json"""
    users = _load_users_json()
    if username not in users:
        return False
    user_data = users[username]
    if isinstance(user_data, str):
        users[username] = new_password
    elif isinstance(user_data, dict):
        users[username]['password'] = new_password
    return _save_users_json(users)

def _update_last_login_in_json(username):
    """Actualizar último login en users.json"""
    users = _load_users_json()
    if username not in users:
        return False
    user_data = users[username]
    if isinstance(user_data, dict):
        users[username]['last_login'] = datetime.now().isoformat()
        return _save_users_json(users)
    return True

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    DB_CONFIG = {
        'dbname': 'visual_agent_db',
        'user': 'postgres',
        'password': 'maria1234',
        'host': 'localhost',
        'port': '5432'
    }

    def get_connection():
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            return conn
        except Exception as e:
            print(f"PostgreSQL no disponible: {e}")
            return None

    def get_user(username):
        conn = get_connection()
        if conn:
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("SELECT * FROM desarrolladores WHERE username = %s AND is_active = TRUE", (username,))
                user = cursor.fetchone()
                cursor.close()
                conn.close()
                return user
            except Exception as e:
                print(f"Error obteniendo usuario: {e}")
                return None
        else:
            return _get_user_from_json(username)

    def create_user(username, password, secret_question, secret_answer, email=None):
        conn = get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO desarrolladores
                       (username, password, role, secret_question, secret_answer, email)
                       VALUES (%s, %s, 'desarrollador', %s, %s, %s)""",
                    (username, password, secret_question, secret_answer, email)
                )
                conn.commit()
                cursor.close()
                conn.close()
                return True
            except psycopg2.IntegrityError:
                print("El usuario ya existe")
                return False
            except Exception as e:
                print(f"Error creando usuario: {e}")
                return False
        else:
            return _create_user_in_json(username, password, secret_question, secret_answer, email)

    def update_last_login(username):
        conn = get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE desarrolladores SET last_login = %s WHERE username = %s",
                    (datetime.now(), username)
                )
                conn.commit()
                cursor.close()
                conn.close()
                return True
            except Exception as e:
                print(f"Error actualizando login: {e}")
                return False
        else:
            return _update_last_login_in_json(username)

    def update_password(username, new_password):
        conn = get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE desarrolladores SET password = %s WHERE username = %s",
                    (new_password, username)
                )
                conn.commit()
                cursor.close()
                conn.close()
                return True
            except Exception as e:
                print(f"Error actualizando contrasena: {e}")
                return False
        else:
            return _update_password_in_json(username, new_password)

    def user_exists(username):
        conn = get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM desarrolladores WHERE username = %s", (username,))
                exists = cursor.fetchone() is not None
                cursor.close()
                conn.close()
                return exists
            except Exception as e:
                print(f"Error verificando usuario: {e}")
                return False
        else:
            return _get_user_from_json(username) is not None

    def log_activity(usuario_id, accion, descripcion="", ip_address=""):
        conn = get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO actividad_logs (usuario_id, accion, descripcion, ip_address)
                       VALUES (%s, %s, %s, %s)""",
                    (usuario_id, accion, descripcion, ip_address)
                )
                conn.commit()
                cursor.close()
                conn.close()
                return True
            except Exception as e:
                print(f"Error registrando actividad: {e}")
                return False
        else:
            return True

except ImportError:
    print("psycopg2 no instalado - usando users.json como almacenamiento")

    def get_connection():
        return None

    def get_user(username):
        return _get_user_from_json(username)

    def create_user(username, password, secret_question, secret_answer, email=None):
        return _create_user_in_json(username, password, secret_question, secret_answer, email)

    def update_last_login(username):
        return _update_last_login_in_json(username)

    def update_password(username, new_password):
        return _update_password_in_json(username, new_password)

    def user_exists(username):
        return _get_user_from_json(username) is not None

    def log_activity(usuario_id, accion, descripcion="", ip_address=""):
        return True
