from flask import Flask, request, jsonify
import sqlite3
from functools import wraps
import secrets
import time

app = Flask(__name__)
app.config['DEBUG'] = True

tokens = {}
TOKEN_EXPIRATION_SECONDS = 300

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({"error": "Token requerido"}), 401
        if token not in tokens or time.time() > tokens[token]["expires"]:
            return jsonify({"error": "Token inválido o expirado"}), 403
        return f(*args, **kwargs)
    return decorated

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    cursor.execute(""" 
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            descripcion TEXT,
            fecha_creacion DATE,
            precio_llegada REAL,
            precio_menudeo REAL,
            precio_mayoreo REAL
        )
    """)

    cursor.execute("""
        INSERT INTO products (nombre, descripcion, fecha_creacion, precio_llegada, precio_menudeo, precio_mayoreo)
        SELECT 'The Legend of Zelda: Breath of the Wild', 'NSW','2017-10-27', 1600, 1800, 1700
        WHERE NOT EXISTS (SELECT 1 FROM products WHERE nombre='The Legend of Zelda: Breath of the Wild')
    """)
    cursor.execute("""
        INSERT INTO products (nombre, descripcion, fecha_creacion, precio_llegada, precio_menudeo, precio_mayoreo)
        SELECT 'Super Mario Oddysey', 'NSW', '2017-03-03', 1600, 1800, 1700
        WHERE NOT EXISTS (SELECT 1 FROM products WHERE nombre='Super Mario Oddysey')
    """)
    conn.commit()
    conn.close()

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        return jsonify({"error": "Username y password requeridos"}), 400

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Usuario ya existe"}), 409

    conn.close()
    return jsonify({"message": "Usuario registrado correctamente"})

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        token = secrets.token_hex(16)
        expiration = time.time() + TOKEN_EXPIRATION_SECONDS
        tokens[token] = {"user_id": user[0], "expires": expiration}
        return jsonify({"token": token, "expires_in": TOKEN_EXPIRATION_SECONDS})
    else:
        return jsonify({"error": "Credenciales inválidas"}), 401

@app.route('/product')
@token_required
def get_product():
    nombre = request.args.get('nombre') or ''
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE nombre = ?", (nombre,))
    product = cursor.fetchone()
    conn.close()

    if product:
        return jsonify({"product": dict(zip(
            ["id", "nombre", "descripcion", "fecha_creacion", "precio_llegada", "precio_menudeo", "precio_mayoreo"], product
        ))})
    else:
        return jsonify({"error": "Producto no encontrado"}), 404

@app.route('/product/whole')
@token_required
def whole_product():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    conn.close()

    product_list = [{
        "id": p[0], "nombre": p[1], "descripcion": p[2], 
        "fecha_creacion": p[3], "precio_llegada": p[4],
        "precio_menudeo": p[5], "precio_mayoreo": p[6]
    } for p in products]

    return jsonify({"products": product_list}) if product_list else jsonify({"error": "No hay productos registrados"}), 404

@app.route('/product/all')
@token_required
def get_all():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE precio_menudeo = 1800")
    products = cursor.fetchall()
    conn.close()

    product_list = [{
        "id": p[0], "nombre": p[1], "descripcion": p[2], 
        "fecha_creacion": p[3], "precio_llegada": p[4],
        "precio_menudeo": p[5], "precio_mayoreo": p[6]
    } for p in products]

    return jsonify({"products": product_list}) if product_list else jsonify({"error": "No hay productos registrados"}), 404

@app.route('/product/add')
@token_required
def add_product():
    args = request.args
    required_fields = ['nombre', 'descripcion', 'fecha_creacion', 'precio_llegada', 'precio_menudeo', 'precio_mayoreo']
    
    if not all(field in args for field in required_fields):
        return jsonify({"error": "Todos los campos son requeridos"}), 400

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE nombre = ?", (args['nombre'],))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "El producto ya existe"}), 409

    cursor.execute("""
        INSERT INTO products (nombre, descripcion, fecha_creacion, precio_llegada, precio_menudeo, precio_mayoreo)
        VALUES (?, ?, ?, ?, ?, ?)
    """, tuple(args[field] for field in required_fields))
    conn.commit()

    cursor.execute("SELECT * FROM products WHERE nombre = ?", (args['nombre'],))
    product = cursor.fetchone()
    conn.close()

    return jsonify({"product": dict(zip(
        ["id", "nombre", "descripcion", "fecha_creacion", "precio_llegada", "precio_menudeo", "precio_mayoreo"], product
    ))})

@app.route('/product/edit/<int:product_id>')
@token_required
def edit_product(product_id):
    field = request.args.get('field')
    value = request.args.get('value')
    valid_fields = ['nombre', 'descripcion', 'fecha_creacion', 'precio_llegada', 'precio_menudeo', 'precio_mayoreo']

    if field not in valid_fields:
        return jsonify({"error": "Campo no válido para actualizar."}), 400

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(f"UPDATE products SET {field} = ? WHERE id = ?", (value, product_id))
    conn.commit()

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Producto no encontrado o sin cambios."}), 404

    cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    return jsonify({
        "message": "Producto actualizado correctamente.",
        "product": dict(zip(
            ["id", "nombre", "descripcion", "fecha_creacion", "precio_llegada", "precio_menudeo", "precio_mayoreo"], product
        ))
    })

@app.route('/product/erase/<int:product_id>')
@token_required
def erase_product(product_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Producto no encontrado."}), 404

    conn.close()
    return jsonify({"message": f"Producto con ID {product_id} eliminado correctamente."})

@app.route('/admin/data')
def admin_data():
    return jsonify({"data": "Datos confidenciales. ¡Acceso sin autenticación!"})

if __name__ == '__main__':
    init_db()
    app.run()
