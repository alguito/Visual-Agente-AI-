"""
app.py - Visual Agent AI (Versión Final con PostgreSQL y todas las correcciones)
"""
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
from functools import wraps
from visual_agent_utils import VisualAgentUtils
from database import get_user, create_user, update_last_login, update_password, user_exists, log_activity
import os
import re
import atexit
import time
import traceback
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-for-thesis'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

SECRET_QUESTIONS = [
    '¿Cuál es el nombre de tu mascota?',
    '¿Cuál es tu color favorito?',
    '¿En qué ciudad naciste?',
    '¿Cuál es el nombre de tu mejor amigo?',
    '¿Cuál es tu comida favorita?',
    '¿Cómo se llamaba tu primer maestro?'
]

agent = VisualAgentUtils(base_dir=app.config['UPLOAD_FOLDER'])

@atexit.register
def shutdown_agent():
    agent.cleanup()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def validate_password(password):
    errors = []
    if len(password) < 6:
        errors.append('Debe tener al menos 6 caracteres')
    if not re.search(r'\d', password):
        errors.append('Debe contener al menos un numero')
    if not re.search(r'[A-Z]', password):
        errors.append('Debe contener al menos una mayuscula')
    if not re.search(r'[a-z]', password):
        errors.append('Debe contener al menos una minuscula')
    return errors

#==========================================
# RUTAS DE AUTENTICACIÓN
#==========================================

@app.route('/login')
def login_page():
    if 'user' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = get_user(username)
        
        if user and user['password'] == password:
            session['user'] = username
            session['role'] = user['role']
            update_last_login(username)
            log_activity(user['id'], 'login', f'Inicio de sesión exitoso')
            return jsonify({
                'success': True, 
                'message': 'Bienvenido', 
                'username': username,
                'role': user['role']
            })
        else:
            return jsonify({'success': False, 'error': 'Usuario o contraseña incorrectos'}), 401
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Faltan datos'}), 400
        
        pass_errors = validate_password(password)
        if pass_errors:
            return jsonify({'success': False, 'error': ';'.join(pass_errors)}), 400
        
        if user_exists(username):
            return jsonify({'success': False, 'error': 'El usuario ya existe'}), 400
        
        secret_question = data.get('secret_question', '')
        secret_answer = data.get('secret_answer', '')
        email = data.get('email', '')
        
        if not secret_question or not secret_answer:
            return jsonify({'success': False, 'error': 'Debes seleccionar una pregunta secreta'}), 400
        
        if create_user(username, password, secret_question, secret_answer, email):
            return jsonify({'success': True, 'message': 'Usuario creado correctamente'})
        else:
            return jsonify({'success': False, 'error': 'Error al crear usuario'}), 500
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('role', None)
    return redirect(url_for('login_page'))

@app.route('/api/secret_questions')
def api_secret_questions():
    return jsonify({'questions': SECRET_QUESTIONS})

@app.route('/api/get_secret_question', methods=['POST'])
def api_get_secret_question():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        
        if not username:
            return jsonify({'success': False, 'error': 'Ingresa tu usuario'}), 400
        
        user = get_user(username)
        
        if not user:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        if not user.get('secret_question'):
            return jsonify({'success': False, 'error': 'Sin pregunta secreta'}), 400
        
        return jsonify({'success': True, 'question': user['secret_question']})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/recover_password', methods=['POST'])
def api_recover_password():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        answer = data.get('answer', '').strip().lower()
        new_password = data.get('new_password', '')
        
        if not username or not answer or not new_password:
            return jsonify({'success': False, 'error': 'Faltan datos'}), 400
        
        pass_errors = validate_password(new_password)
        if pass_errors:
            return jsonify({'success': False, 'error': ';'.join(pass_errors)}), 400
        
        user = get_user(username)
        
        if not user:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'}), 404
        
        if user.get('secret_answer', '').lower() != answer:
            return jsonify({'success': False, 'error': 'Respuesta incorrecta'}), 401
        
        if update_password(username, new_password):
            log_activity(user['id'], 'recuperar_password', 'Contraseña actualizada')
            return jsonify({'success': True, 'message': 'Contraseña actualizada correctamente'})
        else:
            return jsonify({'success': False, 'error': 'Error al actualizar contraseña'}), 500
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#==========================================
# RUTAS PROTEGIDAS DEL AGENTE
#==========================================

@app.route('/')
@login_required
def index():
    baselines_data = agent.get_baseline_list()
    baselines_names = [b['name'] for b in baselines_data]
    return render_template('index.html', baselines=baselines_names, current_user=session.get('user'))

@app.route('/api/capture', methods=['POST'])
@login_required
def capture_screenshot():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL requerida'}), 400
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        filepath, filename = agent.capture_screenshot(url)
        
        if filepath is None:
            return jsonify({'error': 'Error captura'}), 500
        
        visual_data = agent.extract_visual_data(filepath)
        page_data = agent.extract_page_data(url)
        error_analysis = agent.analyze_interface_errors(filepath, page_data)
        marked_path, closeups = agent.draw_error_boxes(filepath, error_analysis['errors'])
        
        # Log de actividad
        user = get_user(session.get('user'))
        if user:
            log_activity(user['id'], 'captura', f'Captura de {url}')
        
        return jsonify({
            'success': True,
            'filename': filename,
            'filepath': f'screenshots/{filename}',
            'marked_filepath': f'marked/{os.path.basename(marked_path)}' if marked_path else None,
            'closeups': closeups,
            'url': url,
            'timestamp': datetime.now().isoformat(),
            'visual_data': visual_data,
            'error_analysis': error_analysis
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'{type(e).__name__}: {str(e)}'}), 500

@app.route('/api/generate_pdf', methods=['POST'])
@login_required
def generate_pdf():
    try:
        data = request.get_json()
        filename = data.get('filename')
        url = data.get('url', 'N/A')
        
        if not filename:
            return jsonify({'error': 'Nombre de archivo requerido'}), 400
        
        image_path = os.path.join(agent.screenshots_dir, filename)
        
        if not os.path.exists(image_path):
            return jsonify({'error': 'Imagen no encontrada'}), 404
        
        # Asegurar que la página esté cargada para capturar diagnósticos
        driver = agent._get_driver()
        try:
            driver.get(url)
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            time.sleep(0.5)
        except Exception:
            pass

        # Navegar y capturar errores frescos del navegador
        agent.capture_browser_diagnostics(driver)
        visual_data = agent.extract_visual_data(image_path)
        page_data = agent.extract_page_data(url)
        error_analysis = agent.analyze_interface_errors(image_path, page_data)
        design_info = agent.extract_design_and_colors(image_path)
        
        agent.draw_error_boxes(image_path, error_analysis['errors'])
        
        pdf_path, pdf_filename = agent.generate_complete_pdf_report(
            image_path, url, visual_data, error_analysis, page_data, design_info
        )
        
        if pdf_path is None:
            return jsonify({'error': 'Error al generar PDF'}), 500
        
        # Guardar recomendaciones para futuras comparaciones
        try:
            recs = [e.get('recommendation', '') for e in error_analysis.get('errors', []) if e.get('recommendation')]
            recs_path = os.path.join(agent.reports_dir, 'recommendations_last.json')
            import json
            with open(recs_path, 'w') as f:
                json.dump(recs, f)
        except Exception:
            pass
        
        user = get_user(session.get('user'))
        if user:
            log_activity(user['id'], 'generar_pdf', f'PDF generado para {url}')
        
        return jsonify({
            'success': True,
            'pdf_filename': pdf_filename,
            'pdf_path': f'reports/{pdf_filename}',
            'message': 'PDF generado'
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/compare', methods=['POST'])
@login_required
def compare_visual():
    try:
        data = request.get_json()
        baseline_name = data.get('baseline')
        current_image = data.get('current_image')
        threshold = float(data.get('threshold', 0.85))
        
        if not baseline_name or not current_image:
            return jsonify({'error': 'Baseline e imagen actual requeridas'}), 400
        
        baseline_path = os.path.join(agent.baseline_dir, f"{baseline_name}.png")
        current_path = os.path.join(agent.screenshots_dir, current_image)
        
        if not os.path.exists(baseline_path):
            return jsonify({'error': 'Baseline no encontrada'}), 404
        if not os.path.exists(current_path):
            return jsonify({'error': 'Imagen no encontrada'}), 404
        
        result = agent.compare_images(baseline_path, current_path, threshold)
        
        if result is None:
            return jsonify({'error': 'Error al comparar'}), 500
        
        # ✅ CORRECCIÓN: Asegurar que todos los valores sean serializables a JSON
        return jsonify({
            'success': True,
            'comparison': {
                'similarity_score': float(result.get('similarity_score', 0)),
                'threshold_used': float(result.get('threshold_used', 0.85)),
                'has_changes': bool(result.get('has_changes', True)),
                'difference_percentage': float(result.get('difference_percentage', 0)),
                'analysis': result.get('analysis', {})
            },
            'message': 'Comparación completada',
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate_comparison_pdf', methods=['POST'])
@login_required
def generate_comparison_pdf():
    try:
        data = request.get_json()
        baseline_name = data.get('baseline')
        current_image = data.get('current_image')
        url = data.get('url', 'N/A')
        
        if not baseline_name or not current_image:
            return jsonify({'error': 'Baseline e imagen actual requeridas'}), 400
        
        baseline_path = os.path.join(agent.baseline_dir, f"{baseline_name}.png")
        current_path = os.path.join(agent.screenshots_dir, current_image)
        
        if not os.path.exists(baseline_path):
            return jsonify({'error': 'Baseline no encontrada'}), 404
        if not os.path.exists(current_path):
            return jsonify({'error': 'Imagen no encontrada'}), 404
        
        comparison_result = agent.compare_images(baseline_path, current_path)
        
        if comparison_result is None:
            return jsonify({'error': 'Error al comparar'}), 500
        
        recs_path = os.path.join(agent.reports_dir, 'recommendations_last.json')
        previous_recommendations = []
        if os.path.exists(recs_path):
            try:
                import json
                with open(recs_path, 'r') as f:
                    previous_recommendations = json.load(f)
            except Exception:
                pass
        
        pdf_path, pdf_filename = agent.generate_comparison_pdf_report(
            baseline_path, current_path, comparison_result, url, previous_recommendations
        )
        
        if pdf_path is None:
            return jsonify({'error': 'Error al generar PDF comparativo'}), 500
        
        user = get_user(session.get('user'))
        if user:
            log_activity(user['id'], 'generar_comparacion', f'PDF comparativo para {url}')
        
        return jsonify({
            'success': True,
            'pdf_filename': pdf_filename,
            'pdf_path': f'reports/{pdf_filename}',
            'message': 'PDF comparativo generado'
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/save_baseline', methods=['POST'])
@login_required
def save_baseline():
    try:
        data = request.get_json()
        screenshot_name = data.get('screenshot')
        baseline_name = data.get('baseline_name')
        
        screenshot_path = os.path.join(agent.screenshots_dir, screenshot_name)
        
        if not os.path.exists(screenshot_path):
            return jsonify({'error': 'No existe'}), 404
        
        baseline_path = agent.save_as_baseline(screenshot_path, baseline_name)
        
        if baseline_path is None:
            return jsonify({'error': 'Error guardando'}), 500
        
        user = get_user(session.get('user'))
        if user:
            log_activity(user['id'], 'guardar_baseline', f'Baseline {baseline_name} guardada')
        
        return jsonify({'success': True, 'message': 'Guardada'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/list_screenshots')
@login_required
def list_screenshots():
    try:
        screenshots = []
        for f in os.listdir(agent.screenshots_dir):
            if f.endswith('.png'):
                fp = os.path.join(agent.screenshots_dir, f)
                screenshots.append({
                    'name': f,
                    'relative_path': f'screenshots/{f}',
                    'path': fp,
                    'created': datetime.fromtimestamp(os.path.getctime(fp)).isoformat(),
                    'size_kb': round(os.path.getsize(fp) / 1024, 2)
                })
        
        return jsonify({'screenshots': sorted(screenshots, key=lambda x: x['created'], reverse=True)})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/list_baselines')
@login_required
def list_baselines():
    try:
        return jsonify({'baselines': agent.get_baseline_list()})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/image/<path:filename>')
@login_required
def serve_image(filename):
    try:
        uploads_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
        full_path = os.path.abspath(os.path.join(uploads_folder, filename))
        
        if not full_path.startswith(uploads_folder):
            return jsonify({'error': 'Acceso denegado'}), 403
        
        if not os.path.exists(full_path):
            return jsonify({'error': f'Archivo no encontrado: {filename}'}), 404
        
        return send_file(full_path, mimetype='image/png')
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<path:filename>')
@login_required
def download_file(filename):
    try:
        uploads_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
        full_path = os.path.abspath(os.path.join(uploads_folder, filename))
        
        if not full_path.startswith(uploads_folder):
            return jsonify({'error': 'Acceso denegado'}), 403
        
        if not os.path.exists(full_path):
            return jsonify({'error': f'Archivo no encontrado: {filename}'}), 404
        
        return send_file(full_path, as_attachment=True)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/imagenes/<path:filename>')
def serve_logo(filename):
    imagenes_dir = os.path.abspath('imagenes')
    full_path = os.path.abspath(os.path.join(imagenes_dir, filename))
    if not full_path.startswith(imagenes_dir):
        return '', 403
    if not os.path.exists(full_path):
        return '', 404
    return send_file(full_path)

@app.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'Visual Agent AI'})

if __name__ == '__main__':
    print("Iniciando Visual Agent AI...")
    print("Accede desde: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)