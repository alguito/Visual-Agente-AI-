"""
run.py - Punto de entrada para el ejecutable empaquetado con PyInstaller
"""
from app import app
import webbrowser
import threading
import time

def open_browser():
    time.sleep(2)
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    threading.Thread(target=open_browser, daemon=True).start()
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    except OSError as e:
        if getattr(e, 'winerror', None) == 10038:
            pass
        else:
            raise