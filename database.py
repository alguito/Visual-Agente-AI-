"""
database.py - Conexión a PostgreSQL para Visual Agent AI
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime


DB_CONFIG = {
    'dbname': 'visual_agent_db',
    'user': 'postgres',
    'password': 'maria1234',  
    'host': 'localhost',
    'port': '5432'
}

def get_connection():
    """Obtener conexión a la base de datos"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Error conectando a la BD: {e}")
        return None

def get_user(username):
    """Obtener usuario por username"""
    conn = get_connection()
    if not conn:
        return None
    
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

def create_user(username, password, secret_question, secret_answer, email=None):
    """Crear nuevo desarrollador (rol por defecto: 'desarrollador')"""
    conn = get_connection()
    if not conn:
        return False
    
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
        print("⚠️ El usuario ya existe")
        return False
    except Exception as e:
        print(f"Error creando usuario: {e}")
        return False

def update_last_login(username):
    """Actualizar último inicio de sesión"""
    conn = get_connection()
    if not conn:
        return False
    
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

def update_password(username, new_password):
    """Actualizar contraseña"""
    conn = get_connection()
    if not conn:
        return False
    
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
        print(f"Error actualizando contraseña: {e}")
        return False

def user_exists(username):
    """Verificar si el usuario existe"""
    conn = get_connection()
    if not conn:
        return False
    
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

def log_activity(usuario_id, accion, descripcion="", ip_address=""):
    """Registrar actividad en el log de auditoría"""
    conn = get_connection()
    if not conn:
        return False
    
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