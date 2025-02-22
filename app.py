from flask import Flask, request, render_template, send_from_directory, redirect, url_for, session
import os
import json
import re
from datetime import datetime
from urllib.parse import quote
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Clave secreta para manejar sesiones
UPLOAD_FOLDER = "uploads"  # Carpeta para almacenar archivos subidos
MESSAGES_FILE = "messages.json"  # Archivo para almacenar mensajes
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Decorador para requerir login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Cargar usuarios desde JSON
def load_users():
    if not os.path.exists('users.json'):
        return []
    with open('users.json', 'r') as f:
        return json.load(f)

# Guardar usuarios en JSON
def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(users, f, indent=4)

# Cargar mensajes desde JSON
def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        return []
    with open(MESSAGES_FILE, 'r') as f:
        return json.load(f)

# Guardar mensajes en JSON
def save_messages(messages):
    with open(MESSAGES_FILE, 'w') as f:
        json.dump(messages, f, indent=4)

# Verificar el estado de verificación del usuario
def check_verification_status():
    if 'logged_in' in session:
        users = load_users()
        user = next((u for u in users if u['username'] == session['username']), None)
        if user and user.get('verified') != session.get('verified'):
            session['verified'] = user['verified']

# Ejecutar antes de cada solicitud
@app.before_request
def before_request():
    check_verification_status()

# Rutas de autenticación
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = load_users()
        username_or_email = request.form['username_or_email']
        password = request.form['password']
        
        user = next((u for u in users if (u['username'] == username_or_email or u['email'] == username_or_email) and u['password'] == password), None)
        
        if user:
            session['logged_in'] = True
            session['username'] = user['username']
            session['email'] = user['email']
            session['verified'] = user.get('verified', False)
            return redirect(url_for('index'))
        return render_template('login.html', error="Credenciales incorrectas")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users = load_users()
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return render_template('register.html', error="Correo electrónico no válido")
        
        if any(u['email'] == email for u in users):
            return render_template('register.html', error="El correo electrónico ya está registrado")
        if any(u['username'] == username for u in users):
            return render_template('register.html', error="El nombre de usuario ya existe")
        
        users.append({
            'username': username,
            'email': email,
            'password': password,
            'verified': False
        })
        save_users(users)
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Rutas principales
@app.route("/")
@login_required
def index():
    return render_template("index.html", username=session['username'], verified=session['verified'])

@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    if "file" not in request.files:
        return "No file part"
    file = request.files["file"]
    if file.filename == "":
        return "No selected file"
    
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    
    file_info = {
        "name": file.filename,
        "owner": session['username'],
        "owner_verified": session['verified'],
        "upload_date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "size": f"{os.path.getsize(file_path) / 1024:.2f} KB"
    }
    
    files_info = []
    if os.path.exists('files_info.json'):
        with open('files_info.json', 'r') as f:
            files_info = json.load(f)
    
    files_info.append(file_info)
    with open('files_info.json', 'w') as f:
        json.dump(files_info, f, indent=4)
    
    return redirect(url_for('list_files'))

@app.route("/files")
@login_required
def list_files():
    if os.path.exists('files_info.json'):
        with open('files_info.json', 'r') as f:
            files_info = json.load(f)
    else:
        files_info = []
    return render_template("files.html", files=files_info)

@app.route("/download/<filename>")
@login_required
def download_file(filename):
    filename = filename.encode('utf-8').decode('utf-8')
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route("/delete/<filename>", methods=["POST"])
@login_required
def delete_file(filename):
    file_info = get_file_info(filename)
    if not file_info:
        return "Archivo no encontrado", 404
    
    if session['username'] == file_info['owner'] or (session['verified'] and not file_info['owner_verified']):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        if os.path.exists('files_info.json'):
            with open('files_info.json', 'r') as f:
                files_info = json.load(f)
            files_info = [fi for fi in files_info if fi['name'] != filename]
            with open('files_info.json', 'w') as f:
                json.dump(files_info, f, indent=4)
        
        return redirect(url_for('list_files'))
    else:
        return "No tienes permiso para eliminar este archivo", 403

# Ruta para enviar mensajes
@app.route("/send_message", methods=["POST"])
@login_required
def send_message():
    message = request.form.get('message')
    if not message:
        return "Mensaje vacío", 400
    
    messages = load_messages()
    messages.append({
        "username": session['username'],
        "message": message,
        "verified": session['verified'],
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })
    save_messages(messages)
    return redirect(url_for('show_messages'))

# Ruta para mostrar mensajes
@app.route("/messages")
@login_required
def show_messages():
    messages = load_messages()
    return render_template("messages.html", messages=messages)

# Función para obtener información de un archivo
def get_file_info(filename):
    if os.path.exists('files_info.json'):
        with open('files_info.json', 'r') as f:
            files_info = json.load(f)
            for file_info in files_info:
                if file_info['name'] == filename:
                    return file_info
    return None

# Iniciar la aplicación
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)