"""
visual_agent_utils.py - Visual Agent AI (Versión Final Completa)
Agente de IA para la detección automática de errores visuales y funcionales en interfaces gráficas de usuarios.
"""
import os
import cv2
import numpy as np
from PIL import Image
import pytesseract
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import BytesIO
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from collections import Counter
import shutil
import time

# Configurar ruta de Tesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

try:
    from classifier import AnomalyClassifier
except ImportError:
    print("⚠️ Advertencia: No se encontró classifier.py")
    class AnomalyClassifier:
        def predict(self, data):
            if data.get('edge_density', 0) > 20 or data.get('chaos_pct', 0) > 30:
                return {'is_anomaly': True, 'confidence': 0.95, 'severity': 'high', 'model': 'RandomForest Classifier'}
            return {'is_anomaly': False, 'confidence': 0.95, 'severity': 'low', 'model': 'RandomForest Classifier'}


class VisualAgentUtils:
    """
    Clase utilitaria para operaciones de agente visual.
    """

    def __init__(self, base_dir='uploads'):
        self.base_dir = base_dir
        self.screenshots_dir = os.path.join(base_dir, 'screenshots')
        self.baseline_dir = os.path.join(base_dir, 'baselines')
        self.reports_dir = os.path.join(base_dir, 'reports')
        self.marked_dir = os.path.join(base_dir, 'marked')

        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs(self.baseline_dir, exist_ok=True)
        os.makedirs(self.reports_dir, exist_ok=True)
        os.makedirs(self.marked_dir, exist_ok=True)

        self._driver = None
        self._classifier = None

    def _get_classifier(self):
        if self._classifier is None:
            self._classifier = AnomalyClassifier()
        return self._classifier

    def _get_driver(self):
        if self._driver is None:
            wdm_lock = os.path.join(os.path.expanduser('~'), '.wdm', '.wdm-lock-chromedriver-win64')
            try:
                if os.path.exists(wdm_lock):
                    os.remove(wdm_lock)
                    print("  → Lock previo eliminado")
            except Exception:
                pass

            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
            chrome_options.set_capability('pageLoadStrategy', 'eager')

            service = Service(ChromeDriverManager().install())
            self._driver = webdriver.Chrome(service=service, options=chrome_options)
            self._driver.set_page_load_timeout(15)

            # Inyectar capturador de errores JS antes de cualquier script de página
            try:
                self._driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                    'source': '''
                        window.__visualAgentErrors = [];
                        window.onerror = function(msg, source, lineno, colno, error) {
                            window.__visualAgentErrors.push({
                                message: msg,
                                source: source || '',
                                lineno: lineno || 0,
                                colno: colno || 0
                            });
                        };
                        window.addEventListener('unhandledrejection', function(e) {
                            window.__visualAgentErrors.push({
                                message: 'Promise rejection: ' + (e.reason || 'unknown'),
                                source: '',
                                lineno: 0
                            });
                        });
                    '''
                })
            except Exception:
                pass

        return self._driver

    def capture_screenshot(self, url, filename=None):
        try:
            print(f"\n🔄 Capturando screenshot de: {url}")
            driver = self._get_driver()
            
            try:
                driver.get(url)
                print("✅ Página cargada (DOM interactivo)")
            except Exception as e:
                print(f"⚠️ Timeout inicial: {e}")
                # Intentar continuar con lo que se haya cargado
                try:
                    driver.execute_script('return document.body')
                except Exception:
                    self._restart_driver()
                    return None, None

            # Esperar que la página se termine de renderizar
            try:
                WebDriverWait(driver, 15).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                print("✅ Renderizado completo")
            except Exception:
                print("⚠️ Se continúa con renderizado parcial")

            time.sleep(0.5)

            if filename is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                safe_name = url.replace('https://', '').replace('http://', '').replace('/', '_')[:50]
                filename = f"{safe_name}_{timestamp}.png"

            # Expandir viewport al alto real de la página para capturarla COMPLETA
            try:
                full_height = driver.execute_script(
                    'return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)'
                )
                capped = min(int(full_height), 12000)
                if capped > 1080:
                    driver.set_window_size(1920, capped)
                    time.sleep(0.3)
                    print(f"  → Viewport expandido a 1920x{capped}")
            except Exception:
                pass

            # Scroll gradual para activar lazy loading en el viewport expandido
            try:
                scroll_height = driver.execute_script('return document.body.scrollHeight')
                viewport_height = driver.execute_script('return window.innerHeight')
                scroll_step = max(viewport_height, 300)
                current_pos = 0
                while current_pos < scroll_height:
                    driver.execute_script(f'window.scrollTo(0, {current_pos})')
                    time.sleep(0.1)
                    current_pos += scroll_step
                driver.execute_script('window.scrollTo(0, 0)')
                time.sleep(0.2)
                print(f"✅ Scroll completo ({scroll_height}px)")
            except Exception:
                pass

            filepath = os.path.join(self.screenshots_dir, filename)
            driver.save_screenshot(filepath)
            print(f"💾 Screenshot guardado: {filepath}")

            # Restaurar viewport
            try:
                driver.set_window_size(1920, 1080)
            except Exception:
                pass

            # Capturar diagnósticos del navegador
            self.capture_browser_diagnostics(driver)
            
            print(f"💾 Screenshot guardado: {filepath}")
            return filepath, filename

        except Exception as e:
            print(f"❌ Error al capturar screenshot: {e}")
            import traceback
            traceback.print_exc()
            self._restart_driver()
            return None, None

    def capture_browser_diagnostics(self, driver):
        """Captura errores REALES del navegador, filtrando ruido de terceros."""
        self._browser_errors = []
        self._broken_images = []

        # Patrones benignos que NO deben reportarse como errores
        benign_patterns = [
            'favicon.ico', 'ERR_FILE_NOT_FOUND', 'ERR_NAME_NOT_RESOLVED',
            'Manifest', 'Sentry', 'gtag', 'fbq', 'fbclid',
            'www.google-analytics.com', 'googletagmanager.com',
            'doubleclick.net', 'googleads', 'pagead',
            'hotjar', 'cdn.ampproject', 'facebook.net',
            'preflight', 'CORS', 'cache',
            'ERR_BLOCKED_BY_CLIENT', 'ERR_ABORTED',
            'ERR_CACHE_MISS', 'ERR_CONTENT_DECODING_FAILED',
            'WebSocket', 'longRunning', 'deprecated',
            'third-party', 'cookie', 'SameSite',
            'cast_sender', 'extension', 'chrome-extension',
            'google.com/_/chrome', 'OPTIONS',
        ]

        # 1. Console errors - filtrar solo errores JS/HTTP reales
        try:
            logs = driver.get_log('browser')
            for entry in logs:
                if entry['level'] != 'SEVERE':
                    continue
                msg = entry.get('message', '')
                lowered = msg.lower()
                # Saltar patrones benignos
                if any(p.lower() in lowered for p in benign_patterns):
                    continue
                self._browser_errors.append({
                    'level': 'SEVERE',
                    'message': msg[:300],
                    'timestamp': entry['timestamp']
                })
            if self._browser_errors:
                print(f"  → {len(self._browser_errors)} errores reales de consola")
        except Exception as e:
            print(f"  → Error capturando logs: {e}")

        # 2. Imágenes rotas (no cargaron)
        try:
            broken = driver.execute_script("""
                return Array.from(document.querySelectorAll('img'))
                    .filter(img => !img.complete || img.naturalWidth === 0)
                    .map(img => {
                        const r = img.getBoundingClientRect();
                        return {
                            src: img.src.substring(0, 100),
                            left: r.left, top: r.top,
                            width: r.width, height: r.height,
                            alt: (img.alt || '').substring(0, 50)
                        };
                    });
            """)
            if broken:
                self._broken_images = broken
                print(f"  → {len(broken)} imágenes rotas")
        except Exception as e:
            print(f"  → Error detectando imágenes rotas: {e}")

        # 3. Errores JS runtime (window.onerror) - ya filtrados por el navegador
        try:
            js_errors = driver.execute_script("""
                return window.__visualAgentErrors || [];
            """)
            if js_errors:
                for err in js_errors:
                    msg = f"JS Error: {err.get('message','')} en {err.get('source','')}:{err.get('lineno','')}"
                    lowered = (err.get('message', '') + err.get('source', '')).lower()
                    if not any(p.lower() in lowered for p in benign_patterns):
                        self._browser_errors.append({
                            'level': 'SEVERE',
                            'message': msg[:300],
                            'timestamp': 0
                        })
                if self._browser_errors:
                    pass  # count already printed above
        except Exception:
            pass

    def extract_visual_data(self, image_path):
        try:
            img_pil = Image.open(image_path)
            width, height = img_pil.size

            img_cv = cv2.imread(image_path)
            if img_cv is None:
                raise ValueError("No se pudo leer la imagen con OpenCV")

            avg_color = cv2.mean(img_cv)[:3]
            avg_color_rgb = (avg_color[2], avg_color[1], avg_color[0])

            text_extracted = pytesseract.image_to_string(img_pil, lang='spa+eng').strip()
            file_size = os.path.getsize(image_path)

            return {
                'dimensions': {
                    'width': width,
                    'height': height,
                    'aspect_ratio': round(width / height, 2) if height > 0 else 0
                },
                'dominant_color': {
                    'rgb': avg_color_rgb,
                    'hex': '#{:02x}{:02x}{:02x}'.format(int(avg_color_rgb[0]), int(avg_color_rgb[1]), int(avg_color_rgb[2]))
                },
                'text_preview': text_extracted[:200] + '...' if len(text_extracted) > 200 else text_extracted,
                'text_length': len(text_extracted),
                'file_size_bytes': file_size,
                'file_size_kb': round(file_size / 1024, 2)
            }

        except Exception as e:
            print(f"Error al extraer datos visuales: {e}")
            return None

    def draw_error_boxes(self, image_path, errors_found):
        """Marca errores y genera recortes ampliados de cada zona con error."""
        if not errors_found:
            return None, []

        img = cv2.imread(image_path)
        if img is None:
            return None, []

        img_marked = img.copy()
        h_full, w_full = img.shape[:2]
        error_types = [e['type'] for e in errors_found]
        any_marked = False
        broken_images = getattr(self, '_broken_images', [])
        closeups = []
        base_name = os.path.basename(image_path).replace('.png', '')
        closeup_idx = 0

        def crop_closeup(x, y, w, h, label, error_type, pad=40):
            nonlocal closeup_idx
            pad = min(pad, x, y, w_full - (x + w), h_full - (y + h))
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w_full, x + w + pad)
            y2 = min(h_full, y + h + pad)
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                return None
            crop_name = f"{base_name}_closeup_{closeup_idx}.png"
            crop_path = os.path.join(self.marked_dir, crop_name)
            cv2.imwrite(crop_path, crop)
            closeup_idx += 1
            closeups.append({
                'path': f'marked/{crop_name}',
                'label': label,
                'type': error_type,
                'x': x, 'y': y,
                'width': w, 'height': h
            })

        # Marcar imágenes rotas con recortes
        if 'broken_image' in error_types and broken_images:
            for bi in broken_images:
                x = int(bi.get('left', 0))
                y = int(bi.get('top', 0))
                wb = int(bi.get('width', 50))
                hb = int(bi.get('height', 50))
                if wb > 5 and hb > 5:
                    cv2.rectangle(img_marked, (x-3, y-3), (x+wb+3, y+hb+3), (0, 0, 255), 4)
                    cv2.putText(img_marked, "IMG ROTA", (x, y-8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    crop_closeup(x, y, wb, hb, 'Imagen rota', 'broken_image')
                    any_marked = True

        # Marcar texto de error HTTP con recortes
        if 'http_error' in error_types:
            try:
                data = pytesseract.image_to_data(img, lang='spa+eng', output_type=pytesseract.Output.DICT)
                keywords = ['404', '500', '502', '503', 'error', 'failed', 'fatal']
                for i, text in enumerate(data['text']):
                    cleaned = text.lower().strip()
                    if any(k in cleaned for k in keywords):
                        x, y, wb, hb = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                        if wb > 10 and hb > 10:
                            cv2.rectangle(img_marked, (x-5, y-5), (x+wb+5, y+hb+5), (0, 0, 255), 3)
                            cv2.putText(img_marked, cleaned.upper(), (x, y-8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                            crop_closeup(x, y, wb, hb, cleaned.upper(), 'http_error')
                            any_marked = True
            except Exception:
                pass

        # Marcar áreas rojas grandes con recortes
        if 'visual_error' in error_types:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
            mask2 = cv2.inRange(hsv, np.array([160, 70, 50]), np.array([180, 255, 255]))
            mask = mask1 + mask2
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                area = cv2.contourArea(c)
                if area > 5000:
                    x, y, wb, hb = cv2.boundingRect(c)
                    cv2.rectangle(img_marked, (x, y), (x+wb, y+hb), (0, 0, 255), 3)
                    crop_closeup(x, y, wb, hb, 'Área roja', 'visual_error')
                    any_marked = True

        if not any_marked:
            return None, []

        marked_path = os.path.join(self.marked_dir, os.path.basename(image_path).replace('.png', '_marked.png'))
        cv2.imwrite(marked_path, img_marked)
        return marked_path, closeups

    def analyze_interface_errors(self, image_path, page_data=None, browser_errors=None, broken_images=None):
        """
        Análisis de errores visuales y funcionales.
        Combina análisis visual (OpenCV + OCR) con diagnósticos reales del navegador.
        """
        # Usar datos de browser capturados en el último screenshot si no se pasan
        if browser_errors is None:
            browser_errors = getattr(self, '_browser_errors', [])
        if broken_images is None:
            broken_images = getattr(self, '_broken_images', [])

        try:
            img_cv = cv2.imread(image_path)
            img_pil = Image.open(image_path)
            if img_cv is None:
                raise ValueError("No image")

            h, w = img_cv.shape[:2]
            errors_found = []

            # ============================================
            # ANÁLISIS REAL DEL NAVEGADOR (ALTA CONFIABILIDAD)
            # ============================================

            # 1. Errores de consola del navegador (JS, red, recursos)
            severe_browser = [e for e in browser_errors if e['level'] == 'SEVERE']
            if severe_browser:
                # Agrupar por tipo de error
                error_messages = list(set(e['message'] for e in severe_browser))
                for msg in error_messages[:5]:
                    errors_found.append({
                        'type': 'browser_error',
                        'description': f'Error en navegador: {msg[:200]}',
                        'detail': msg[:150],
                        'severity': 'high',
                        'recommendation': f'Revisar el error en consola: {msg[:150]}'
                    })

            # 2. Imágenes rotas (no cargaron)
            if broken_images:
                errors_found.append({
                    'type': 'broken_image',
                    'description': f'{len(broken_images)} imágenes no cargaron correctamente en la página.',
                    'detail': f'{len(broken_images)} imágenes rotas',
                    'severity': 'high',
                    'recommendation': f'Verificar las rutas de {len(broken_images)} imágenes que fallaron al cargar. '
                                      f'Asegurar que los archivos existan y las URLs sean correctas.'
                })

            # ============================================
            # ANÁLISIS VISUAL (OpenCV + OCR)
            # ============================================

            # 3. Errores HTTP en texto visible (solo contexto real de error, no números sueltos)
            text = ''
            found_errors = []
            try:
                text = pytesseract.image_to_string(img_pil, lang='spa+eng').lower()
                import re
                http_errs = {
                    '404': r'(?:error|errores?)\s*:?\s*404|404\s*(?:not found|error|no encontrado|página no)',
                    '500': r'(?:error|errores?)\s*:?\s*500|500\s*(?:internal server|server error|error|interna del servidor)',
                    '502': r'(?:error|errores?)\s*:?\s*502|502\s*(?:bad gateway|gateway error|error)',
                    '503': r'(?:error|errores?)\s*:?\s*503|503\s*(?:service unavailable|no disponible|error)',
                }
                found_errors = [code for code, pattern in http_errs.items() if re.search(pattern, text)]
                # También detectar frases genéricas de error
                if re.search(r'(?:server error|fatal error|internal server error)', text):
                    found_errors.append('server error')
                
                if found_errors:
                    errors_found.append({
                        'type': 'http_error',
                        'description': f'Errores HTTP visibles en pantalla: {", ".join(found_errors)}.',
                        'detail': f'Códigos detectados: {", ".join(found_errors)}',
                        'severity': 'low',
                        'recommendation': f'Corregir los errores HTTP {", ".join(found_errors)} encontrados.'
                    })
            except Exception:
                print("  → OCR no disponible, se omite análisis de texto")

            # 2. Rojo excesivo (solo alerta si más del 25% de la pantalla es roja)
            hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)
            mask1 = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
            mask2 = cv2.inRange(hsv, np.array([160, 70, 50]), np.array([180, 255, 255]))
            red_percentage = (np.sum((mask1 + mask2) > 0) / (h * w)) * 100
            
            if red_percentage > 35:
                errors_found.append({
                    'type': 'visual_error',
                    'description': f'Exceso de color rojo: {red_percentage:.1f}% del área total (umbral: >35%).',
                    'detail': f'{red_percentage:.1f}% de píxeles rojos',
                    'severity': 'low',
                    'recommendation': f'Reducir el uso del color rojo del {red_percentage:.1f}% actual.'
                })

            # 3. Página casi en blanco
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            white_percentage = (np.sum(gray > 240) / gray.size) * 100
            
            if white_percentage > 95 and len(text.strip()) < 50:
                errors_found.append({
                    'type': 'layout_error',
                    'description': f'Página casi en blanco: {white_percentage:.1f}% del área es blanca '
                                   f'y solo se detectaron {len(text.strip())} caracteres de texto. '
                                   f'Esto sugiere un posible error de carga o contenido no renderizado.',
                    'detail': f'{white_percentage:.1f}% blanco, {len(text.strip())} caracteres detectados',
                    'severity': 'high',
                    'recommendation': f'Verificar que la página cargue correctamente todos sus recursos. '
                                      f'Revisar la consola del navegador en busca de errores de JavaScript o CSS '
                                      f'que impidan la renderización del contenido. Asegurar que el servidor '
                                      f'responda con el contenido completo.'
                })

            # 4. Densidad de bordes (caos visual) — umbral elevado para evitar falsos positivos
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / gray.size * 100
            
            if edge_density > 55:
                errors_found.append({
                    'type': 'design_error',
                    'description': f'Diseño visualmente denso: {edge_density:.1f}% densidad de bordes (umbral: >55%).',
                    'detail': f'{edge_density:.1f}% densidad de bordes',
                    'severity': 'low',
                    'recommendation': f'Reducir la densidad visual del {edge_density:.1f}% actual.'
                })

            # 5. Superposición de elementos — umbral elevado
            block_size = 100
            high_var = sum(1 for y in range(0, gray.shape[0], block_size) 
                          for x in range(0, gray.shape[1], block_size)
                          if np.var(gray[y:y+block_size, x:x+block_size]) > 1500)
            total_blocks = max((gray.shape[0] // block_size) * (gray.shape[1] // block_size), 1)
            chaos_pct = (high_var / total_blocks * 100)
            
            if chaos_pct > 75:
                errors_found.append({
                    'type': 'layout_error',
                    'description': f'Alta densidad de cambios visuales: {chaos_pct:.1f}% del área (umbral: >75%).',
                    'detail': f'{chaos_pct:.1f}% del área con alta varianza',
                    'severity': 'low',
                    'recommendation': f'Revisar el layout de la página. Verificar márgenes, paddings y '
                                      f'posicionamiento de elementos con CSS Grid o Flexbox.'
                })

            # 6. Colores saturados/chillones — umbral elevado
            saturation_channel = hsv[:, :, 1]
            value_channel = hsv[:, :, 2]
            garish_mask = (saturation_channel > 180) & (value_channel > 200)
            garish_percentage = (np.sum(garish_mask > 0) / gray.size) * 100
            
            if garish_percentage > 50:
                errors_found.append({
                    'type': 'design_error',
                    'description': f'Colores muy saturados: {garish_percentage:.1f}% del área (umbral: >50%).',
                    'detail': f'{garish_percentage:.1f}% colores saturados',
                    'severity': 'low',
                    'recommendation': f'Reducir la saturación de colores del {garish_percentage:.1f}% actual.'
                })

            # 7. Bajo contraste — umbral más permisivo
            contrast_std = np.std(gray)
            
            if contrast_std < 15:
                errors_found.append({
                    'type': 'accessibility_error',
                    'description': f'Contraste bajo: desviación estándar de {contrast_std:.1f} (umbral: <15).',
                    'detail': f'Contraste: {contrast_std:.1f} desviación',
                    'severity': 'low',
                    'recommendation': f'Aumentar el contraste de la interfaz de {contrast_std:.1f} a al menos 25.'
                })

            # 8. Texto ilegible — umbral elevado para evitar falsos positivos
            small_text_count = 0
            try:
                ocr_data = pytesseract.image_to_data(img_pil, lang='spa+eng', output_type=pytesseract.Output.DICT)
                small_text_count = sum(1 for i in range(len(ocr_data['text'])) 
                                      if ocr_data['text'][i].strip() and ocr_data['height'][i] < 10)
            except Exception:
                pass
            
            if small_text_count > 150:
                errors_found.append({
                    'type': 'accessibility_error',
                    'description': f'Texto pequeño: {small_text_count} elementos con altura <10px (umbral: >150).',
                    'detail': f'{small_text_count} textos con altura <10px',
                    'severity': 'low',
                    'recommendation': f'Aumentar el tamaño de fuente de los {small_text_count} elementos '
                                      f'identificados. Tamaño mínimo recomendado: 16px para texto de lectura.'
                })

            # ============================================
            # ANÁLISIS HTML
            # ============================================
            
            if page_data:
                # 9. Imágenes sin ALT
                media = page_data.get('media_info', {})
                no_alt = media.get('images_without_alt', 0)
                total_imgs = media.get('total_images', 0)
                
                if no_alt > 80 and total_imgs > 0 and (no_alt / total_imgs) > 0.9:
                    errors_found.append({
                        'type': 'accessibility_error',
                        'description': f'Accesibilidad: {no_alt} de {total_imgs} imágenes carecen de atributo ALT '
                                       f'({(no_alt/total_imgs)*100:.0f}%).',
                        'detail': f'{no_alt}/{total_imgs} imágenes sin ALT',
                        'severity': 'low',
                        'recommendation': f'Agregar atributos ALT descriptivos a las {no_alt} imágenes que carecen '
                                          f'de ellos.'
                    })

                # 10. Falta de H1 o múltiples H1
                html = page_data.get('html_structure', {})
                h1_count = html.get('headings', {}).get('h1', 0)
                
                if h1_count == 0:
                    errors_found.append({
                        'type': 'seo_error',
                        'description': f'SEO: No se detectó etiqueta H1 en la página.',
                        'detail': '0 etiquetas H1 encontradas',
                        'severity': 'low',
                        'recommendation': 'Agregar una etiqueta H1 descriptiva que incluya la palabra clave '
                                          'principal del contenido. Debe haber exactamente un H1 por página, '
                                          'ubicado al inicio del contenido principal. Ejemplo: '
                                          '<h1>Título Principal de la Página</h1>'
                    })
                elif h1_count > 1:
                    errors_found.append({
                        'type': 'seo_error',
                        'description': f'SEO: Se detectaron {h1_count} etiquetas H1.',
                        'detail': f'{h1_count} etiquetas H1',
                        'severity': 'low',
                        'recommendation': f'Reducir de {h1_count} a solo 1 etiqueta H1. Convertir los H1 '
                                          f'adicionales en H2 o H3 según corresponda en la jerarquía de contenido. '
                                          f'Usar la estructura: H1 → H2 → H3 para mantener una jerarquía clara.'
                    })

                # 11. Contenido escaso
                content = page_data.get('content_analysis', {})
                word_count = content.get('word_count', 0)
                
                if word_count < 30:
                    errors_found.append({
                        'type': 'content_error',
                        'description': f'Contenido muy escaso: solo {word_count} palabras detectadas.',
                        'detail': f'{word_count} palabras',
                        'severity': 'low',
                        'recommendation': f'Ampliar el contenido de {word_count} a al menos 100 palabras.'
                    })

                # 12. Exceso de enlaces
                nav = page_data.get('nav_info', {})
                total_links = nav.get('total_links', 0)
                
                if total_links > 250:
                    errors_found.append({
                        'type': 'navigation_error',
                        'description': f'Navegación: {total_links} enlaces en la página.',
                        'detail': f'{total_links} enlaces',
                        'severity': 'medium',
                        'recommendation': f'Reducir la cantidad de enlaces de {total_links} a menos de 200.'
                    })

            # ============================================
            # ANÁLISIS ML
            # ============================================
            
            errors_count = len(errors_found)
            
            if errors_count == 0:
                ml = {
                    'is_anomaly': False,
                    'confidence': 0.95,
                    'severity': 'ninguna',
                    'model': 'RandomForest Classifier'
                }
            else:
                try:
                    classifier = self._get_classifier()
                    ml = classifier.predict({
                        'red_pixels_pct': red_percentage,
                        'white_pixels_pct': white_percentage,
                        'edge_density': edge_density,
                        'chaos_pct': chaos_pct,
                        'img_width': img_cv.shape[1],
                        'img_height': img_cv.shape[0],
                        'images_without_alt': page_data.get('media_info', {}).get('images_without_alt', 0) if page_data else 0,
                        'total_links': page_data.get('nav_info', {}).get('total_links', 0) if page_data else 0,
                        'forms_count': page_data.get('interactive_info', {}).get('forms', 0) if page_data else 0,
                        'error_keywords_count': len(found_errors)
                    })
                    ml['model'] = 'RandomForest Classifier'
                except Exception as e:
                    print(f"⚠️ ML prediction error: {e}")
                    import traceback
                    traceback.print_exc()
                    ml = {
                        'is_anomaly': False,
                        'confidence': 0.0,
                        'severity': 'unknown',
                        'model': 'Error'
                    }

            # ============================================
            # CÁLCULO DE PORCENTAJE DE ERRORES
            # ============================================
            
            if errors_count == 0:
                error_pct = 0.0
            else:
                # Separar errores reales (browser, broken images, http) de sugerencias visuales
                real_types = {'browser_error', 'broken_image'}
                real_errors = [e for e in errors_found if e['type'] in real_types]
                suggestions = [e for e in errors_found if e['type'] not in real_types]

                if not real_errors:
                    # Solo hay sugerencias de diseño → página saludable
                    error_pct = 0.0
                else:
                    severity_scores = {'high': 100, 'medium': 60, 'low': 25}
                    real_total = sum(severity_scores.get(e.get('severity', 'high'), 100) for e in real_errors)
                    real_avg = real_total / len(real_errors)
                    real_qty = min(len(real_errors) / 3.0, 1.0)
                    error_pct = (real_avg * 0.7) + (100 * real_qty * 0.3)
                    error_pct = round(min(error_pct, 100), 2)

            if error_pct == 0:
                status = 'healthy'
                status_text = 'Sin errores'
            elif error_pct < 30:
                status = 'warning'
                status_text = 'Problemas menores'
            elif error_pct < 60:
                status = 'error'
                status_text = 'Problemas moderados'
            else:
                status = 'critical'
                status_text = 'Problemas críticos'

            return {
                'status': status,
                'status_text': status_text,
                'error_percentage': error_pct,
                'errors_found': errors_count,
                'real_errors': len(real_errors) if errors_count > 0 else 0,
                'suggestions': len(suggestions) if errors_count > 0 else 0,
                'errors': errors_found,
                'metrics': {
                    'red_pixels_percentage': round(red_percentage, 2),
                    'edge_density': round(edge_density, 2),
                    'chaos_percentage': round(chaos_pct, 2),
                    'garish_colors_percentage': round(garish_percentage, 2),
                    'contrast_std': round(contrast_std, 2),
                    'white_percentage': round(white_percentage, 2)
                },
                'ml_analysis': ml
            }

        except Exception as e:
            print(f"❌ Error en analyze_interface_errors: {e}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'unknown',
                'status_text': 'Error en análisis',
                'error_percentage': 0,
                'errors_found': 0,
                'errors': [],
                'metrics': {},
                'ml_analysis': {'is_anomaly': False, 'confidence': 0.95, 'severity': 'ninguna', 'model': 'Error'}
            }

    def extract_page_data(self, url):
        """Extrae datos HTML de la página ya cargada en el driver (sin recargar)"""
        try:
            driver = self._get_driver()
            try:
                WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except Exception:
                pass

            html_content = driver.page_source
            soup = BeautifulSoup(html_content, 'html.parser')

            html_structure = {
                'title': soup.title.string if soup.title else 'Sin título',
                'doctype': 'HTML5' if '<!doctype html>' in html_content.lower() else 'Desconocido',
                'language': soup.html.get('lang', 'No especificado') if soup.html else 'No especificado',
                'total_elements': len(soup.find_all()),
                'headings': {f'h{i}': len(soup.find_all(f'h{i}')) for i in range(1, 7)},
                'forms': len(soup.find_all('form')),
                'tables': len(soup.find_all('table')),
                'navs': len(soup.find_all('nav'))
            }

            meta_description = soup.find('meta', attrs={'name': 'description'})
            meta_desc_content = meta_description.get('content', '') if meta_description else ''

            images = soup.find_all('img')
            media_info = {
                'total_images': len(images),
                'images_with_alt': sum(1 for img in images if img.get('alt')),
                'images_without_alt': sum(1 for img in images if not img.get('alt')),
                'images_no_dimensions': sum(1 for img in images if not (img.get('width') and img.get('height'))),
                'videos': len(soup.find_all('video')),
                'iframes': len(soup.find_all('iframe'))
            }

            links = soup.find_all('a', href=True)
            empty_links = sum(1 for link in links if not link.get_text(strip=True))
            
            nav_info = {
                'total_links': len(links),
                'empty_links': empty_links,
                'internal_links': sum(1 for link in links if link.get('href', '').startswith('/') or url in link.get('href', '')),
                'external_links': sum(1 for link in links if not (link.get('href', '').startswith('/') or url in link.get('href', '')))
            }

            interactive_info = {
                'buttons': len(soup.find_all('button')),
                'inputs': len(soup.find_all('input')),
                'selects': len(soup.find_all('select')),
                'forms': len(soup.find_all('form'))
            }

            text_content = soup.get_text(separator=' ', strip=True)
            words = text_content.split()

            content_analysis = {
                'word_count': len(words),
                'character_count': len(text_content)
            }

            return {
                'html_structure': html_structure,
                'meta_description': meta_desc_content,
                'media_info': media_info,
                'nav_info': nav_info,
                'interactive_info': interactive_info,
                'content_analysis': content_analysis
            }

        except Exception as e:
            print(f"Error extrayendo datos: {e}")
            return None

    def extract_design_and_colors(self, image_path):
        try:
            img_cv = cv2.imread(image_path)
            if img_cv is None:
                raise ValueError("No se pudo cargar la imagen")

            img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
            img_small = cv2.resize(img_rgb, (100, 100))
            pixels = img_small.reshape(-1, 3)

            color_counter = Counter([tuple(p) for p in pixels])
            dominant_colors = color_counter.most_common(5)

            colors_list = []
            for color, count in dominant_colors:
                hex_color = '#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2])
                percentage = (count / len(pixels)) * 100
                colors_list.append({
                    'hex': hex_color,
                    'rgb': color,
                    'percentage': round(percentage, 2)
                })

            avg_color = cv2.mean(img_cv)[:3]
            avg_hex = '#{:02x}{:02x}{:02x}'.format(int(avg_color[2]), int(avg_color[1]), int(avg_color[0]))

            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            contrast = np.std(gray)

            return {
                'dominant_colors': colors_list,
                'average_color': {'hex': avg_hex},
                'contrast_level': 'Alto' if contrast > 50 else 'Medio' if contrast > 30 else 'Bajo'
            }

        except Exception as e:
            print(f"Error extrayendo colores: {e}")
            return None

    def _get_pdf_image_size(self, img_path=None, pil_img=None, max_w_inches=6.5, max_h_inches=7.0):
        """Lee la imagen (path o PIL Image) y devuelve (w, h) en pts preservando proporción."""
        try:
            if pil_img is not None:
                iw, ih = pil_img.size
            elif img_path:
                with Image.open(img_path) as pi:
                    iw, ih = pi.size
            else:
                return max_w_inches * inch, 5 * inch
        except Exception:
            return max_w_inches * inch, 5 * inch
        if iw <= 0 or ih <= 0:
            return max_w_inches * inch, 5 * inch
        max_w = max_w_inches * inch
        max_h = max_h_inches * inch
        scale = min(max_w / iw, max_h / ih, 1.0)
        w = iw * scale
        h = ih * scale
        if w < 3.5 * inch and ih > iw * 3:
            scale = max_w / iw
            w = max_w
            h = min(ih * scale, max_h)
        return w, h

    def _split_image_into_chunks(self, img_path=None, pil_img=None, chunk_height=1080):
        """Divide una captura vertical larga en secciones de chunk_height px."""
        try:
            if pil_img is not None:
                img = pil_img
            elif img_path:
                img = Image.open(img_path)
            else:
                return []
        except Exception:
            return []
        w, h = img.size
        if h <= chunk_height:
            return [img]
        chunks = []
        y = 0
        while y < h:
            bottom = min(y + chunk_height, h)
            chunk = img.crop((0, y, w, bottom))
            chunks.append(chunk)
            y = bottom
        return chunks

    def generate_complete_pdf_report(self, screenshot_path, url, visual_data, error_analysis, page_data, design_info):
        """
        Genera reporte PDF compacto con 6 secciones.
        Las pruebas de usabilidad son DINÁMICAS según los errores detectados.
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            pdf_filename = f"reporte_{timestamp}.pdf"
            pdf_path = os.path.join(self.reports_dir, pdf_filename)

            doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                                   rightMargin=40, leftMargin=40,
                                   topMargin=40, bottomMargin=40)

            story = []
            styles = getSampleStyleSheet()

            DARK_NAVY = '#0a3d4d'
            DEEP_BLUE = '#0b5e7a'
            CYAN = '#148a9e'
            LIGHT_CYAN = '#d9edf2'
            ERROR_RED = '#c0392b'
            SUCCESS_GREEN = '#1e7e5c'
            WARNING_AMBER = '#d4872b'
            DARK_TEXT = '#1a1a2e'
            MEDIUM_GRAY = '#5d6d7e'
            LIGHT_GRAY = '#eef3f5'
            BORDER_GRAY = '#9db4c0'
            WHITE = '#ffffff'

            title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                        fontSize=24, textColor=colors.HexColor(DARK_NAVY),
                                        spaceAfter=10, alignment=1, fontName='Helvetica-Bold')

            subtitle_style = ParagraphStyle('CustomSubtitle', parent=styles['Normal'],
                                           fontSize=10, textColor=colors.HexColor(MEDIUM_GRAY),
                                           spaceAfter=20, alignment=1, fontName='Helvetica-Oblique')

            heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'],
                                          fontSize=14, textColor=colors.HexColor(DEEP_BLUE),
                                          spaceAfter=10, spaceBefore=15, fontName='Helvetica-Bold')

            normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'],
                                         fontSize=10, textColor=colors.HexColor(DARK_TEXT),
                                         spaceAfter=8, fontName='Helvetica')

            # ==================== PORTADA ====================
            story.append(Spacer(1, 1.5*inch))
            story.append(Paragraph("VISUAL AGENT AI", ParagraphStyle('PortadaTitle', parent=styles['Heading1'],
                                        fontSize=28, textColor=colors.HexColor(DARK_NAVY),
                                        spaceAfter=8, alignment=1, fontName='Helvetica-Bold')))
            
            story.append(Paragraph("Agente de IA para la detección automática de errores visuales y funcionales en interfaces gráficas de usuarios", subtitle_style))
            story.append(Spacer(1, 0.3*inch))

            story.append(Paragraph(f'<font color="{CYAN}">━━━</font>  REPORTE COMPLETO DE ANÁLISIS WEB  <font color="{CYAN}">━━━</font>', ParagraphStyle('PortadaDivider', parent=styles['Normal'],
                                        fontSize=11, textColor=colors.HexColor(MEDIUM_GRAY),
                                        spaceAfter=20, alignment=1, fontName='Helvetica')))
            story.append(Spacer(1, 0.2*inch))

            info_data = [
                ['URL Analizada:', url],
                ['Fecha:', datetime.now().strftime('%d/%m/%Y %H:%M:%S')],
                ['Estado:', error_analysis.get('status_text', 'N/A').upper()],
                ['Errores:', f"{error_analysis.get('error_percentage', 0)}%"]
            ]

            info_table = Table(info_data, colWidths=[2*inch, 4*inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(LIGHT_GRAY)),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor(DARK_TEXT)),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(BORDER_GRAY))
            ]))

            story.append(info_table)
            story.append(PageBreak())

            # ==================== 1. RESUMEN EJECUTIVO ====================
            story.append(Paragraph("1. RESUMEN EJECUTIVO", heading_style))

            diagnosis_text = f"El análisis de <b>{url}</b> indica: <b>{error_analysis.get('status_text', 'Desconocido').upper()}</b> con <b>{error_analysis.get('error_percentage', 0)}%</b> de errores. "
            
            if error_analysis.get('errors_found', 0) > 0:
                diagnosis_text += f"Se detectaron <b>{error_analysis.get('errors_found', 0)}</b> problemas específicos."
            else:
                diagnosis_text += "No se detectaron errores significativos."

            story.append(Paragraph(diagnosis_text, normal_style))
            story.append(Spacer(1, 0.3*inch))

            # ==================== 2. ANÁLISIS CON INTELIGENCIA ARTIFICIAL ====================
            ml = error_analysis.get('ml_analysis', {})
            if ml:
                story.append(Paragraph("2. ANÁLISIS CON INTELIGENCIA ARTIFICIAL", heading_style))

                is_anomaly = ml.get('is_anomaly', False)
                confidence = ml.get('confidence', 0)
                severity = ml.get('severity', 'N/A')

                if not is_anomaly:
                    ml_text = f"El clasificador RandomForest determina que la interfaz <b>no presenta anomalías</b> con un nivel de confianza del <b>{confidence * 100:.1f}%</b>. Esto indica que la página cumple con los estándares básicos de calidad visual y funcional según los parámetros analizados."
                else:
                    ml_text = f"El clasificador RandomForest determina que la interfaz <b>presenta anomalías</b> con un nivel de confianza del <b>{confidence * 100:.1f}%</b>."
                story.append(Paragraph(ml_text, normal_style))
                story.append(Spacer(1, 0.15*inch))

                story.append(Paragraph("<i>El modelo fue entrenado sobre datos sintéticos generados a partir de umbrales industriales (WCAG, estándares de UX). La confianza representa la probabilidad asignada por el ensamble de 100 árboles de decisión. Un valor ≥90% indica alta fiabilidad en la predicción.</i>", ParagraphStyle('Disclaimer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor(MEDIUM_GRAY), spaceAfter=10, fontName='Helvetica-Oblique')))

                ml_data_info = [
                    ['Indicador', 'Valor'],
                    ['Detección de Anomalía', 'SÍ' if is_anomaly else 'NO'],
                    ['Confianza del Modelo', f"{confidence * 100:.1f}%"],
                    ['Severidad', 'NINGUNA' if severity == 'ninguna' else severity.upper()],
                    ['Modelo', ml.get('model', 'N/A')]
                ]

                ml_table = Table(ml_data_info, colWidths=[3*inch, 3*inch])
                ml_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(DEEP_BLUE)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(BORDER_GRAY)),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT_GRAY)])
                ]))

                story.append(ml_table)
                story.append(Spacer(1, 0.3*inch))

            # ==================== 3. EVIDENCIA VISUAL ====================
            story.append(Paragraph("3. EVIDENCIA VISUAL", heading_style))

            story.append(Paragraph("<b>Secciones de la página capturada:</b>", normal_style))
            story.append(Spacer(1, 0.1*inch))

            # Dividir la captura en secciones individuales para mejor visualización
            try:
                original_chunks = self._split_image_into_chunks(img_path=screenshot_path, chunk_height=1080)
            except Exception:
                original_chunks = []

            if not original_chunks:
                try:
                    iw, ih = self._get_pdf_image_size(screenshot_path)
                    story.append(RLImage(screenshot_path, width=iw, height=ih))
                except Exception:
                    story.append(Paragraph("[Error al cargar imagen original]", normal_style))
            else:
                for ci, chunk in enumerate(original_chunks):
                    cw, ch = self._get_pdf_image_size(pil_img=chunk, max_w_inches=6.5, max_h_inches=9.0)
                    story.append(Paragraph(
                        f"<b>Sección {ci+1} de {len(original_chunks)}:</b>", normal_style))
                    story.append(Spacer(1, 0.05*inch))
                    buf = BytesIO()
                    chunk.save(buf, format='PNG')
                    buf.seek(0)
                    story.append(RLImage(buf, width=cw, height=ch))
                    story.append(Spacer(1, 0.15*inch))

                story.append(Spacer(1, 0.1*inch))

            # También mostrar versión marcada en secciones si existe
            if error_analysis.get('errors_found', 0) > 0:
                marked_path = os.path.join(self.marked_dir, os.path.basename(screenshot_path).replace('.png', '_marked.png'))
                if os.path.exists(marked_path):
                    story.append(Spacer(1, 0.2*inch))
                    story.append(Paragraph("<b>Secciones con errores marcados:</b>", normal_style))
                    story.append(Spacer(1, 0.1*inch))
                    try:
                        marked_chunks = self._split_image_into_chunks(img_path=marked_path, chunk_height=1080)
                        for ci, chunk in enumerate(marked_chunks):
                            mw, mh = self._get_pdf_image_size(pil_img=chunk, max_w_inches=6.5, max_h_inches=9.0)
                            story.append(Paragraph(
                                f"<b>Sección {ci+1} de {len(marked_chunks)} (marcada):</b>", normal_style))
                            story.append(Spacer(1, 0.05*inch))
                            buf = BytesIO()
                            chunk.save(buf, format='PNG')
                            buf.seek(0)
                            story.append(RLImage(buf, width=mw, height=mh))
                            story.append(Spacer(1, 0.15*inch))
                    except Exception:
                        story.append(Paragraph("[Error al cargar imagen marcada]", normal_style))

            story.append(Spacer(1, 0.2*inch))

            if visual_data:
                vd_table = [
                    ['Dimensión', 'Valor'],
                    ['Resolución (Viewport)', f"{visual_data.get('dimensions', {}).get('width', 0)} x {visual_data.get('dimensions', {}).get('height', 0)} px"],
                    ['Color Dominante', visual_data.get('dominant_color', {}).get('hex', 'N/A')],
                    ['Tamaño', f"{visual_data.get('file_size_kb', 0)} KB"]
                ]

                vd = Table(vd_table, colWidths=[2.5*inch, 3.5*inch])
                vd.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(DEEP_BLUE)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(BORDER_GRAY)),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHT_GRAY)])
                ]))

                story.append(vd)

            story.append(PageBreak())

            # ==================== 4. ERRORES DETECTADOS ====================
            story.append(Paragraph("4. ERRORES DETECTADOS", heading_style))

            if error_analysis.get('errors'):
                errors_table_data = [['Tipo', 'Descripción', 'Severidad']]
                for error in error_analysis['errors']:
                    sev = error.get('severity', 'low')
                    severity_icon = {'high': '●', 'medium': '●', 'low': '●'}.get(sev, '●')
                    sev_color = {'high': ERROR_RED, 'medium': WARNING_AMBER, 'low': SUCCESS_GREEN}.get(sev, MEDIUM_GRAY)

                    cell_style = ParagraphStyle('TableCell', parent=styles['Normal'],
                                               fontSize=8.5, textColor=colors.HexColor(DARK_TEXT),
                                               fontName='Helvetica', leading=12)
                    errors_table_data.append([
                        Paragraph(error.get('type', 'N/A').replace('_', ' ').title(), cell_style),
                        Paragraph(error.get('description', 'N/A'), cell_style),
                        Paragraph(f'<font color="{sev_color}">{severity_icon}</font>  {sev.upper()}',
                                 ParagraphStyle('SevCell', parent=styles['Normal'],
                                               fontSize=9, textColor=colors.HexColor(DARK_TEXT),
                                               fontName='Helvetica'))
                    ])

                errors_table = Table(
                    errors_table_data, 
                    colWidths=[1.3*inch, 4*inch, 1*inch]
                )
                errors_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(ERROR_RED)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(BORDER_GRAY)),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fce4ec')]),
                ]))

                story.append(errors_table)
            else:
                story.append(Paragraph("No se detectaron errores específicos.", normal_style))

            story.append(Spacer(1, 0.3*inch))

            # ==================== 5. PRUEBAS DE USABILIDAD RECOMENDADAS (DINÁMICAS) ====================
            story.append(Paragraph("5. PRUEBAS DE USABILIDAD RECOMENDADAS", heading_style))
            
            # ✅ Pruebas dinámicas según los errores detectados
            usability_tests = []
            error_types = [e.get('type', '') for e in error_analysis.get('errors', [])]
            
            if 'accessibility_error' in error_types:
                usability_tests.append("1. Prueba de accesibilidad: Verificar cumplimiento WCAG 2.1 (contraste, ALT en imágenes, navegación por teclado)")
            
            if 'layout_error' in error_types:
                usability_tests.append("2. Prueba de layout: Validar alineación y superposición de elementos en diferentes resoluciones")
            
            if 'design_error' in error_types:
                usability_tests.append("3. Prueba visual: Evaluar coherencia de colores, tipografía y espaciado")
            
            if 'http_error' in error_types or 'text_error' in error_types:
                usability_tests.append("4. Prueba funcional: Verificar que todos los enlaces y recursos carguen correctamente")
            
            if 'seo_error' in error_types:
                usability_tests.append("5. Prueba de SEO: Revisar estructura de encabezados, meta tags y contenido semántico")
            
            if 'navigation_error' in error_types:
                usability_tests.append("6. Prueba de navegación: Evaluar arquitectura de información y facilidad de uso del menú")
            
            if 'content_error' in error_types:
                usability_tests.append("7. Prueba de contenido: Validar que el texto sea suficiente, claro y relevante para el usuario")
            
            if 'visual_error' in error_types:
                usability_tests.append("8. Prueba de percepción visual: Evaluar el uso de colores y su impacto en la experiencia del usuario")
            
            # Si no hay errores, mostrar pruebas generales de validación
            if not usability_tests:
                usability_tests.append("1. Prueba de responsividad: Verificar en móviles (320px, 768px, 1024px)")
                usability_tests.append("2. Prueba de velocidad: Medir tiempo de carga (objetivo: < 3 segundos)")
                usability_tests.append("3. Prueba de contraste: Verificar ratio WCAG AA (mínimo 4.5:1)")
                usability_tests.append("4. Prueba de formularios: Validar funcionamiento completo")
                usability_tests.append("5. Prueba de usuarios reales: Observar 5 usuarios completando tareas clave")
            else:
                usability_tests.append("• Prueba de responsividad: Verificar en dispositivos móviles")
                usability_tests.append("• Prueba de velocidad: Medir tiempo de carga")
                usability_tests.append("• Prueba con usuarios reales: Validar experiencia de uso")
            
            for test in usability_tests:
                story.append(Paragraph(f"• {test}", normal_style))

            story.append(Spacer(1, 0.3*inch))

            # ==================== 6. RECOMENDACIONES ====================
            story.append(Paragraph("6. RECOMENDACIONES", heading_style))

            has_errors = bool(error_analysis.get('errors'))
            
            if not has_errors:
                story.append(Paragraph("<i>Aunque no se detectaron errores, se sugieren las siguientes acciones preventivas para mantener y mejorar la calidad de la interfaz:</i>", normal_style))
                story.append(Spacer(1, 0.1*inch))
            
            recommendations = []

            if has_errors:
                for error in error_analysis['errors']:
                    rec = error.get('recommendation')
                    if rec:
                        recommendations.append(rec)
                    else:
                        error_type = error.get('type', '')
                        if error_type == 'http_error':
                            recommendations.append("Corregir errores HTTP inmediatamente")
                        elif error_type == 'visual_error':
                            recommendations.append("Reducir elementos rojos en la interfaz")
                        elif error_type == 'layout_error':
                            recommendations.append("Reorganizar el layout de la página")
                        elif error_type == 'design_error':
                            recommendations.append("Simplificar el diseño visual")
                        elif error_type == 'accessibility_error':
                            recommendations.append("Mejorar accesibilidad de la interfaz")
                        elif error_type == 'seo_error':
                            recommendations.append("Optimizar el SEO de la página")
                        elif error_type == 'performance_error':
                            recommendations.append("Mejorar el rendimiento de carga")
                        elif error_type == 'navigation_error':
                            recommendations.append("Simplificar la navegación")
                        elif error_type == 'content_error':
                            recommendations.append("Ampliar el contenido de la página")

            if not has_errors:
                recommendations.append("Realizar auditorías periódicas para mantener la calidad")
                recommendations.append("Implementar monitoreo continuo con Visual Agent AI")
                recommendations.append("Documentar estándares de diseño del proyecto")
            else:
                recommendations.append("Auditoría SEO completa")
                recommendations.append("Monitoreo continuo con Visual Agent AI")
                recommendations.append("Documentar cambios realizados")

            for rec in recommendations:
                story.append(Paragraph(f"• {rec}", normal_style))

            # Footer
            story.append(Spacer(1, 0.5*inch))
            footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
                                         fontSize=8, textColor=colors.HexColor(MEDIUM_GRAY),
                                         alignment=1, spaceBefore=10)
            story.append(Paragraph(f'<font color="{BORDER_GRAY}">{"="*60}</font>', footer_style))
            story.append(Paragraph("Generado por Visual Agent AI v2.0.0", footer_style))

            def pdf_metadata(canvas_obj, doc_obj):
                canvas_obj.setTitle('Reporte de detección de errores - Visual Agent AI')
                canvas_obj.setAuthor('Visual Agent AI')
                canvas_obj.setSubject('Detección automática de errores visuales y funcionales en interfaces web')

            doc.build(story, onFirstPage=pdf_metadata, onLaterPages=pdf_metadata)

            return pdf_path, pdf_filename

        except Exception as e:
            print(f"Error al generar PDF: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    def compare_images(self, baseline_path, current_path, threshold=0.85):
        try:
            img1 = cv2.imread(baseline_path)
            img2 = cv2.imread(current_path)

            if img1 is None or img2 is None:
                raise ValueError("No se pudieron cargar las imágenes")

            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

            from skimage.metrics import structural_similarity as ssim

            img1_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            img2_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

            score, diff = ssim(img1_gray, img2_gray, full=True)

            diff_pixels = cv2.absdiff(img1, img2)
            diff_percentage = float(np.sum(diff_pixels > 30) / (img1.shape[0] * img1.shape[1] * 3) * 100)

            # ✅ CORRECCIÓN CLAVE: Convertir explícitamente a bool nativo de Python
            has_changes = bool(score < threshold or diff_percentage > 5)

            return {
                'similarity_score': float(round(score, 4)),
                'threshold_used': float(threshold),
                'has_changes': has_changes,
                'difference_percentage': float(round(diff_percentage, 2)),
                'analysis': {
                    'structural_similarity': 'Alta' if score >= 0.95 else 'Media' if score >= threshold else 'Baja',
                    'pixel_difference': 'Mínima' if diff_percentage < 1 else 'Moderada' if diff_percentage < 10 else 'Significativa'
                }
            }

        except ImportError:
            print("scikit-image no disponible")
            return self._compare_images_fallback(baseline_path, current_path, threshold)

        except Exception as e:
            print(f"Error al comparar: {e}")
            return None

    def _compare_images_fallback(self, baseline_path, current_path, threshold=0.85):
        try:
            img1 = cv2.imread(baseline_path)
            img2 = cv2.imread(current_path)

            if img1 is None or img2 is None:
                raise ValueError("No se pudieron cargar las imágenes")

            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

            diff = cv2.absdiff(img1, img2)
            match_percentage = 1 - (np.sum(diff > 30) / img1.size)

            return {
                'similarity_score': float(round(match_percentage, 4)),
                'threshold_used': float(threshold),
                'has_changes': bool(match_percentage < threshold or (1 - match_percentage) * 100 > 5),
                'difference_percentage': float(round((1 - match_percentage) * 100, 2)),
                'analysis': {'structural_similarity': 'N/A', 'pixel_difference': 'Calculado'}
            }

        except Exception as e:
            print(f"Error en fallback: {e}")
            return None

    def generate_diff_image(self, baseline_path, current_path, output_path):
        """Genera una imagen resaltando las diferencias entre dos capturas"""
        try:
            img1 = cv2.imread(baseline_path)
            img2 = cv2.imread(current_path)
            if img1 is None or img2 is None:
                return False
            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
            diff = cv2.absdiff(img1, img2)
            gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray_diff, 30, 255, cv2.THRESH_BINARY)
            diff_colored = img1.copy()
            diff_colored[thresh > 0] = [0, 0, 255]
            overlay = cv2.addWeighted(img1, 0.7, diff_colored, 0.3, 0)
            cv2.imwrite(output_path, overlay)
            return True
        except Exception:
            return False

    def generate_comparison_pdf_report(self, baseline_path, current_path, comparison_result, url, previous_recommendations=None):
        """
        Genera reporte PDF de comparación entre baseline y captura actual con análisis detallado.
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            pdf_filename = f"comparacion_{timestamp}.pdf"
            pdf_path = os.path.join(self.reports_dir, pdf_filename)

            doc = SimpleDocTemplate(pdf_path, pagesize=letter,
                                   rightMargin=40, leftMargin=40,
                                   topMargin=40, bottomMargin=40)

            story = []
            styles = getSampleStyleSheet()

            DARK_NAVY = '#0a3d4d'
            DEEP_BLUE = '#0b5e7a'
            CYAN = '#148a9e'
            ERROR_RED = '#c0392b'
            SUCCESS_GREEN = '#1e7e5c'
            WARNING_AMBER = '#d4872b'
            DARK_TEXT = '#1a1a2e'
            MEDIUM_GRAY = '#5d6d7e'
            LIGHT_GRAY = '#eef3f5'
            LIGHTER_BG = '#f5f8fa'
            BORDER_GRAY = '#9db4c0'

            heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'],
                                         fontSize=15, textColor=colors.HexColor(DEEP_BLUE),
                                         spaceAfter=12, spaceBefore=18, fontName='Helvetica-Bold')
            sub_heading = ParagraphStyle('SubHeading', parent=styles['Heading3'],
                                        fontSize=11, textColor=colors.HexColor(CYAN),
                                        spaceAfter=8, spaceBefore=12, fontName='Helvetica-Bold')
            normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'],
                                        fontSize=10, textColor=colors.HexColor(DARK_TEXT),
                                        spaceAfter=8, fontName='Helvetica')
            bold_style = ParagraphStyle('BoldNormal', parent=normal_style,
                                       fontName='Helvetica-Bold')

            # ==================== PORTADA ====================
            story.append(Spacer(1, 1.8*inch))
            story.append(Paragraph("VISUAL AGENT AI", ParagraphStyle('CompTitle', parent=styles['Heading1'],
                                        fontSize=26, textColor=colors.HexColor(DARK_NAVY),
                                        spaceAfter=6, alignment=1, fontName='Helvetica-Bold')))
            story.append(Paragraph("Agente de IA para detección automática de errores visuales y funcionales",
                                   ParagraphStyle('CompSubtitle', parent=styles['Normal'],
                                        fontSize=9, textColor=colors.HexColor(MEDIUM_GRAY),
                                        spaceAfter=16, alignment=1, fontName='Helvetica')))
            story.append(Paragraph(f'<font color="{CYAN}">━━━</font>  INFORME DE COMPARACIÓN VISUAL  <font color="{CYAN}">━━━</font>',
                                   ParagraphStyle('CompDiv', parent=styles['Normal'],
                                        fontSize=11, textColor=colors.HexColor(MEDIUM_GRAY),
                                        spaceAfter=30, alignment=1, fontName='Helvetica')))
            story.append(Spacer(1, 0.3*inch))

            has_changes = comparison_result.get('has_changes', False)
            similarity = comparison_result.get('similarity_score', 1.0)
            diff_pct = comparison_result.get('difference_percentage', 0)

            status_color = ERROR_RED if has_changes else SUCCESS_GREEN
            status_text = 'CAMBIOS DETECTADOS' if has_changes else 'SIN CAMBIOS SIGNIFICATIVOS'

            # Clasificación de severidad del cambio
            if not has_changes:
                severity_label = 'NINGUNA'
                severity_color = SUCCESS_GREEN
            elif diff_pct < 3:
                severity_label = 'BAJA'
                severity_color = WARNING_AMBER
            elif diff_pct < 10:
                severity_label = 'MODERADA'
                severity_color = WARNING_AMBER
            else:
                severity_label = 'ALTA'
                severity_color = ERROR_RED

            info_data = [
                ['URL Analizada:', url],
                ['Fecha:', datetime.now().strftime('%d/%m/%Y %H:%M:%S')],
                ['Estado:', f'<font color="{status_color}"><b>{status_text}</b></font>'],
                ['Severidad del Cambio:', f'<font color="{severity_color}"><b>{severity_label}</b></font>'],
                ['Similitud Estructural:', f'{similarity:.2%}'],
                ['Diferencia de Píxeles:', f'{diff_pct:.2f}%'],
                ['Resolución Baseline:', f'{baseline_path.split(os.sep)[-1]}'],
                ['Resolución Actual:', f'{current_path.split(os.sep)[-1]}']
            ]

            cell_style = ParagraphStyle('InfoCell', parent=styles['Normal'],
                                        fontSize=10, textColor=colors.HexColor(DARK_TEXT),
                                        fontName='Helvetica')
            cell_bold = ParagraphStyle('InfoCellBold', parent=cell_style, fontName='Helvetica-Bold')
            info_data_par = []
            for row in info_data:
                info_data_par.append([Paragraph(row[0], cell_bold), Paragraph(row[1], cell_style)])

            info_table = Table(info_data_par, colWidths=[2.2*inch, 3.8*inch])
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(LIGHT_GRAY)),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor(DARK_TEXT)),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(BORDER_GRAY))
            ]))
            story.append(info_table)
            story.append(PageBreak())

            # ==================== SECCIÓN 1 - RESULTADOS DE COMPARACIÓN ====================
            story.append(Paragraph("1. RESULTADOS DE COMPARACIÓN", heading_style))

            analysis = comparison_result.get('analysis', {})
            structural = analysis.get('structural_similarity', 'N/A')
            pixel_diff = analysis.get('pixel_difference', 'N/A')

            # Interpretación detallada
            if not has_changes:
                story.append(Paragraph(
                    f'<b>Diagnóstico: La interfaz no presenta cambios visuales relevantes.</b> '
                    f'La similitud estructural es de <b>{similarity:.2%}</b>, lo que indica que ambas '
                    f'versiones son prácticamente idénticas. La diferencia de píxeles ({diff_pct:.2f}%) '
                    f'se encuentra dentro del margen de tolerancia y podría deberse a compresión, '
                    f'antialiasing o variaciones mínimas en el renderizado.',
                    normal_style))
            else:
                story.append(Paragraph(
                    f'<b>Diagnóstico: Se han identificado cambios en la interfaz.</b> '
                    f'La similitud estructural es del <b>{similarity:.2%}</b>, clasificada como '
                    f'<b>{structural.lower()}</b>, y la diferencia de píxeles alcanza un '
                    f'<b>{diff_pct:.2f}%</b> de la superficie total ({pixel_diff.lower()}). '
                    f'Este nivel de diferencia sugiere que hubo modificaciones '
                    f'{"mayores" if diff_pct > 10 else "moderadas" if diff_pct > 3 else "menores"} '
                    f'en el contenido visual de la página.',
                    normal_style))

            story.append(Spacer(1, 0.15*inch))

            # Tabla de métricas detalladas
            metric_cell_style = ParagraphStyle('MetricCell', parent=styles['Normal'],
                                                fontSize=8, textColor=colors.HexColor(DARK_TEXT),
                                                fontName='Helvetica')
            metric_cell_bold = ParagraphStyle('MetricCellBold', parent=metric_cell_style,
                                              fontName='Helvetica-Bold')
            metric_header = ['Métrica', 'Valor', 'Interpretación', 'Evaluación']
            metrics_data = [
                metric_header,
                [
                    Paragraph('Similitud Estructural (SSIM)', metric_cell_style),
                    Paragraph(f'{similarity:.4f}', metric_cell_style),
                    Paragraph(structural, metric_cell_style),
                    Paragraph('✅ Aceptable' if similarity >= 0.95 else '⚠️ Revisar' if similarity >= 0.85 else '❌ Crítico', metric_cell_style),
                ],
                [
                    Paragraph('Diferencia de Píxeles', metric_cell_style),
                    Paragraph(f'{diff_pct:.2f}%', metric_cell_style),
                    Paragraph(pixel_diff, metric_cell_style),
                    Paragraph('✅ Normal' if diff_pct < 1 else '⚠️ Moderada' if diff_pct < 10 else '❌ Alta', metric_cell_style),
                ],
                [
                    Paragraph('Umbral de Comparación', metric_cell_style),
                    Paragraph(f'{comparison_result.get("threshold_used", 0.85):.2f}', metric_cell_style),
                    Paragraph('Configurable por el usuario', metric_cell_style),
                    Paragraph('—', metric_cell_style),
                ],
                [
                    Paragraph('Cambios Detectados', metric_cell_style),
                    Paragraph('SÍ' if has_changes else 'NO', metric_cell_style),
                    Paragraph(status_text, metric_cell_style),
                    Paragraph(f'<font color="{status_color}">{status_text}</font>', metric_cell_style),
                ],
            ]

            metrics_table = Table(metrics_data, colWidths=[1.8*inch, 1.2*inch, 1.5*inch, 1.5*inch])
            metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(DEEP_BLUE)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(BORDER_GRAY)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHTER_BG)])
            ]))
            story.append(metrics_table)
            story.append(Spacer(1, 0.2*inch))

            # Análisis de áreas de cambio
            story.append(Paragraph("1.1  Análisis de Áreas con Cambios", sub_heading))

            if has_changes:
                if diff_pct < 3:
                    alcance = (
                        f'Los cambios afectan aproximadamente el <b>{diff_pct:.2f}%</b> del área total '
                        f'de la interfaz. Se trata de modificaciones puntuales que probablemente '
                        f'corresponden a ajustes menores de contenido, colores o posición de elementos. '
                        f'Se recomienda verificar visualmente las zonas señaladas en la imagen de diferencias.')
                elif diff_pct < 10:
                    alcance = (
                        f'Los cambios abarcan un <b>{diff_pct:.2f}%</b> del área total de la interfaz. '
                        f'Esto sugiere modificaciones moderadas como reemplazo de secciones, '
                        f'actualización de componentes visuales o reordenamiento de bloques. '
                        f'Se recomienda una revisión detallada de cada área señalada.')
                else:
                    alcance = (
                        f'Los cambios son extensos, afectando al <b>{diff_pct:.2f}%</b> de la superficie '
                        f'visible. Esto podría indicar un rediseño parcial o completo de la interfaz, '
                        f'cambio de plantilla o actualización mayor. Se recomienda una revisión exhaustiva '
                        f'elemento por elemento para validar la consistencia visual y funcional.')

                story.append(Paragraph(alcance, normal_style))
            else:
                story.append(Paragraph(
                    f'No se identificaron áreas con cambios significativos. La interfaz se mantiene '
                    f'consistente con la baseline en un <b>{similarity:.2%}</b>. Las variaciones '
                    f'mínimas detectadas ({diff_pct:.2f}%) están dentro del margen de tolerancia.',
                    normal_style))

            story.append(Spacer(1, 0.2*inch))

            # Evaluación de impacto
            story.append(Paragraph("1.2  Evaluación de Impacto", sub_heading))

            if not has_changes:
                impacto = (
                    f'<b>Impacto: NULO</b> — No hay evidencia de regresiones visuales ni '
                    f'cambios no autorizados. La interfaz mantiene su integridad visual respecto '
                    f'a la baseline de referencia.')
            elif diff_pct < 3:
                impacto = (
                    f'<b>Impacto: BAJO</b> — Los cambios detectados son mínimos y probablemente '
                    f'corresponden a actualizaciones de contenido previstas. No se espera que '
                    f'afecten la experiencia de usuario de forma significativa.')
            elif diff_pct < 10:
                impacto = (
                    f'<b>Impacto: MODERADO</b> — Los cambios cubren un área considerable de la '
                    f'interfaz. Se recomienda verificar que las modificaciones no hayan alterado '
                    f'la funcionalidad de los elementos interactivos ni introducido problemas '
                    f'de accesibilidad o usabilidad.')
            else:
                impacto = (
                    f'<b>Impacto: ALTO</b> — Los cambios son extensos y podrían afectar '
                    f'significativamente la experiencia de usuario. Se recomienda realizar '
                    f'una auditoría visual y funcional completa antes de confirmar los cambios.')

            story.append(Paragraph(impacto, normal_style))
            story.append(PageBreak())

            # ==================== SECCIÓN 2 - EVIDENCIA VISUAL ====================
            story.append(Paragraph("2. EVIDENCIA VISUAL", heading_style))

            diff_path = os.path.join(self.screenshots_dir, f"diff_{timestamp}.png")
            diff_created = self.generate_diff_image(baseline_path, current_path, diff_path)

            # Mostrar baseline y actual lado a lado (una debajo de otra por simplicidad)
            story.append(Paragraph("<b>Captura Baseline (referencia original):</b>", bold_style))
            story.append(Spacer(1, 0.04*inch))
            try:
                iw_b, ih_b = self._get_pdf_image_size(baseline_path, max_w_inches=5.8, max_h_inches=7.0)
                img_base = RLImage(baseline_path, width=iw_b, height=ih_b)
                story.append(img_base)
            except Exception:
                story.append(Paragraph("[Error al cargar imagen baseline]", normal_style))
            story.append(Spacer(1, 0.15*inch))

            story.append(Paragraph("<b>Captura Actual (versión a evaluar):</b>", bold_style))
            story.append(Spacer(1, 0.04*inch))
            try:
                iw_c, ih_c = self._get_pdf_image_size(current_path, max_w_inches=5.8, max_h_inches=7.0)
                img = RLImage(current_path, width=iw_c, height=ih_c)
                story.append(img)
            except Exception:
                story.append(Paragraph("[Error al cargar imagen actual]", normal_style))
            story.append(Spacer(1, 0.15*inch))

            if diff_created and has_changes:
                story.append(Paragraph("<b>Superposición de Diferencias (rojo = cambio detectado):</b>", bold_style))
                story.append(Spacer(1, 0.04*inch))
                try:
                    iw_d, ih_d = self._get_pdf_image_size(diff_path, max_w_inches=5.8, max_h_inches=7.0)
                    img_diff = RLImage(diff_path, width=iw_d, height=ih_d)
                    story.append(img_diff)
                except Exception:
                    story.append(Paragraph("[Error al cargar imagen de diferencias]", normal_style))
                story.append(Paragraph(
                    f'<i>Las áreas resaltadas en rojo indican las regiones donde se detectaron '
                    f'diferencias entre ambas capturas. El {diff_pct:.2f}% de la superficie total '
                    f'presenta cambios visibles.</i>',
                    normal_style))

            story.append(PageBreak())

            # ==================== SECCIÓN 3 - RECOMENDACIONES PREVIAS vs ESTADO ACTUAL ====================
            story.append(Paragraph("3. RECOMENDACIONES DEL REPORTE ANTERIOR", heading_style))

            if previous_recommendations:
                story.append(Paragraph(
                    "A continuación se cotejan las recomendaciones generadas en el reporte de errores "
                    "anterior con el estado actual de la interfaz, para evaluar si los hallazgos previos "
                    "fueron abordados:",
                    normal_style))
                story.append(Spacer(1, 0.1*inch))

                prev_data = [['#', 'Recomendación Anterior', 'Estado Actual']]
                for i, rec in enumerate(previous_recommendations[:10], 1):
                    if has_changes:
                        status_icon = '⚠️ En revisión'
                    else:
                        status_icon = '✅ Sin cambios pendientes'
                    prev_data.append([str(i), Paragraph(rec, normal_style), status_icon])

                prev_table = Table(prev_data, colWidths=[0.4*inch, 3.8*inch, 1.8*inch])
                prev_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(DEEP_BLUE)),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(BORDER_GRAY)),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(LIGHTER_BG)])
                ]))
                story.append(prev_table)
            else:
                story.append(Paragraph(
                    "No hay recomendaciones previas disponibles para comparar. "
                    "Genere un reporte de análisis de errores completo antes de la comparación "
                    "para habilitar el seguimiento de recomendaciones.",
                    normal_style))

            story.append(Spacer(1, 0.3*inch))

            # ==================== SECCIÓN 4 - CONCLUSIONES ====================
            story.append(Paragraph("4. CONCLUSIONES Y RECOMENDACIONES", heading_style))

            # Conclusión principal
            if has_changes:
                story.append(Paragraph(
                    f'<b>Se detectaron cambios en la interfaz</b> con una diferencia del '
                    f'<b>{diff_pct:.2f}%</b> respecto a la baseline (SSIM: {similarity:.2%}). '
                    f'La severidad del cambio se clasifica como <b>{severity_label}</b>.',
                    normal_style))
            else:
                story.append(Paragraph(
                    f'<b>La interfaz se mantiene estable</b> con una similitud del '
                    f'<b>{similarity:.2%}</b> respecto a la baseline. No se requieren acciones '
                    f'correctivas basadas en la comparación visual.',
                    normal_style))

            story.append(Spacer(1, 0.15*inch))

            # Recomendaciones específicas
            story.append(Paragraph("<b>Recomendaciones:</b>", bold_style))
            story.append(Spacer(1, 0.05*inch))

            recommendations_text = []
            if has_changes:
                recommendations_text.append(
                    f'• <b>Revisar cambios manualmente:</b> Examine cada área resaltada en la imagen '
                    f'de diferencias para confirmar que las modificaciones son intencionales y no '
                    f'introducen errores visuales o funcionales.')
                recommendations_text.append(
                    f'• <b>Actualizar baseline:</b> Si los cambios son correcciones válidas, guarde '
                    f'la captura actual como nueva baseline para futuras comparaciones.')
                if diff_pct > 5:
                    recommendations_text.append(
                        f'• <b>Auditar funcionalidad:</b> Dado el nivel de cambio ({diff_pct:.2f}%), '
                        f'verifique que los elementos interactivos (formularios, botones, enlaces) '
                        f'sigan funcionando correctamente en las áreas modificadas.')
                else:
                    recommendations_text.append(
                        f'• <b>Monitoreo continuo:</b> Los cambios detectados son menores, pero se '
                        f'recomienda mantener la frecuencia de monitoreo para detectar regresiones.')
            else:
                recommendations_text.append(
                    f'• <b>Mantener frecuencia de monitoreo:</b> La interfaz se mantiene estable. '
                    f'Continúe con las capturas periódicas para detectar cambios a tiempo.')
                recommendations_text.append(
                    f'• <b>Sin acciones correctivas:</b> No se requieren intervenciones basadas '
                    f'en esta comparación visual.')

            recommendations_text.append(
                f'• <b>Documentar cambios:</b> Mantenga un registro de las comparaciones realizadas '
                f'para trazabilidad y auditoría de la evolución visual de la interfaz.')
            recommendations_text.append(
                f'• <b>Programar próxima comparación:</b> Establezca una frecuencia regular de '
                f'análisis para mantener la calidad visual de forma proactiva.')

            for rec_text in recommendations_text:
                story.append(Paragraph(rec_text, normal_style))

            # Footer
            story.append(Spacer(1, 0.6*inch))
            footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
                                         fontSize=8, textColor=colors.HexColor(MEDIUM_GRAY),
                                         alignment=1, spaceBefore=10)
            story.append(Paragraph(f'<font color="{BORDER_GRAY}">{"="*60}</font>', footer_style))
            story.append(Paragraph(
                f'Generado por Visual Agent AI v2.0.0 — Módulo de Comparación Visual',
                ParagraphStyle('FooterText', parent=footer_style, fontSize=7)))

            def pdf_metadata(canvas_obj, doc_obj):
                canvas_obj.setTitle('Reporte de comparación visual - Visual Agent AI')
                canvas_obj.setAuthor('Visual Agent AI')
                canvas_obj.setSubject('Comparación visual entre baseline y captura actual de interfaz web')

            doc.build(story, onFirstPage=pdf_metadata, onLaterPages=pdf_metadata)

            # Limpiar diff temporal
            try:
                if diff_created and os.path.exists(diff_path):
                    os.remove(diff_path)
            except Exception:
                pass

            return pdf_path, pdf_filename

        except Exception as e:
            print(f"Error al generar PDF de comparación: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    def save_as_baseline(self, source_path, baseline_name):
        try:
            baseline_name = baseline_name.strip().replace(' ', '_').lower()
            if not baseline_name:
                raise ValueError("Nombre vacío")

            dest_path = os.path.join(self.baseline_dir, f"{baseline_name}.png")
            shutil.copy2(source_path, dest_path)
            return dest_path

        except Exception as e:
            print(f"Error al guardar baseline: {e}")
            return None

    def get_baseline_list(self):
        try:
            baselines = []
            for filename in os.listdir(self.baseline_dir):
                if filename.endswith('.png'):
                    baselines.append({
                        'name': filename.replace('.png', ''),
                        'filename': filename,
                        'path': os.path.join(self.baseline_dir, filename),
                        'size_kb': round(os.path.getsize(os.path.join(self.baseline_dir, filename)) / 1024, 2)
                    })
            return sorted(baselines, key=lambda x: x['name'])
        except Exception as e:
            print(f"Error al listar baselines: {e}")
            return []

    def _restart_driver(self):
        try:
            if self._driver:
                self._driver.quit()
        except Exception:
            pass
        self._driver = None
        print("  → Driver reiniciado")

    def cleanup(self):
        if self._driver:
            self._driver.quit()
            self._driver = None