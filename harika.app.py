from flask import Flask, request, jsonify, send_file, render_template
import psycopg2  # pip install psycopg2
import qrcode    # pip install qrcode
import io
import numpy as np
import cv2
from PIL import Image
from psycopg2 import sql
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime

app = Flask(__name__)
CORS(app)

SECRET_KEY = 'this_is_a_secret_key'

db_host = 'localhost'
db_name = 'postgres'
db_user = 'postgres'
db_password ='postgres'

def get_db_connection():
    try:
        connection = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password
        )
        return connection
    except psycopg2.Error as e:
        raise Exception(f"Database connection error: {e}")

def create_users_table_if_not_exist():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_generator_data_table_if_not_exist():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generator_data (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            content TEXT NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

def create_read_data_table_if_not_exist():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS read_data (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL
        );
    """)
    connection.commit()
    cursor.close()
    connection.close()

# Initialize tables
create_users_table_if_not_exist()
create_generator_data_table_if_not_exist()
create_read_data_table_if_not_exist()

@app.route('/')
def index_page():
    return render_template('index.html')

@app.route('/signin')
def signin_page():
    return render_template('signin.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/home')
def home_page():
    return render_template('home.html')

@app.route('/generate')
def generate_page():
    return render_template('generate.html')

@app.route('/read')
def read_page():
    return render_template('read.html')

@app.route('/user/qr_contents')
def view_qr_contents_page():
    return render_template('view_qr_contents.html')

@app.route('/register', methods=['POST'])
def register():
    username = request.json.get('username')
    email = request.json.get('email')
    password = request.json.get('password')

    if not username or not email or not password:
        return jsonify({"error": "Check the entered details properly"}), 400

    hashed_password = generate_password_hash(password)
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO users(username, email, password) VALUES(%s, %s, %s);
        """, (username, email, hashed_password))
        connection.commit()
        cursor.close()
        connection.close()
        return jsonify({"message": "User registered successfully"}), 201
    except psycopg2.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route('/signin', methods=['POST'])
def signin():
    username = request.json.get('username')
    password = request.json.get('password')

    if not username or not password:
        return jsonify({"error": "Both username and password are required"}), 400

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT password FROM users WHERE username=%s;
        """, (username,))
        user = cursor.fetchone()
        cursor.close()
        connection.close()

        if not user or not check_password_hash(user[0], password):
            return jsonify({"error": "Invalid username or password"}), 401

        expiration_time = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        token = jwt.encode({
            'username': username,
            'exp': expiration_time
        }, SECRET_KEY, algorithm='HS256')

        return jsonify({"message": "User signed in successfully", "token": token}), 200
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route('/generate/qr', methods=['POST'])
def qr_code():
    token = request.headers.get('Authorization')
    content = request.json.get('content')

    if not token or not content:
        return jsonify({"error": "Token and content are required"}), 400

    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        username = decoded_token['username']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token expired."}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    # Generate the QR code
    img = qrcode.make(content)

    # Save the QR code image to a buffer
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO generator_data (content, username) VALUES (%s, %s);",
            (content, username)
        )
        connection.commit()
        cursor.close()
        connection.close()
    except Exception as e:
        return jsonify({"error": f"Failed to save QR code data: {e}"}), 500

    # Return the QR code image as a response
    return send_file(buffer, mimetype='image/png', as_attachment=False, download_name='QRcode.png')

@app.route('/read/qr', methods=['POST'])
def read_qr():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        img = Image.open(file.stream)
        img = img.convert('RGB')
        img = np.array(img)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        detector = cv2.QRCodeDetector()
        data, points, _ = detector.detectAndDecode(gray)

        if data:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("INSERT INTO read_data (content) VALUES (%s);", (data,))
            connection.commit()
            cursor.close()
            connection.close()
            return jsonify({'qr_data': data})
        else:
            return jsonify({"error": "No QR code found in the image"}), 400
    except Exception as e:
        return jsonify({"error": f"An error occurred while reading QR code: {e}"}), 500
    


@app.route('/user/get_qr_contents', methods=['GET'])
def get_qr_codes():
    # Get the token from the Authorization header
    token = request.headers.get('Authorization')
    
    if not token:
        return jsonify({"error": "Token is required."}), 400
    
    try:
        # Decode the token to get the username
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        username = decoded_token['username']
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired."}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token."}), 401

    # Query the database to get the QR code ids and contents for the given username
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT id, username FROM users WHERE username = %s;
    """, (username,))
    
    qr_codes_contents = cursor.fetchall()
    
    # Close the connection
    cursor.close()
    connection.close()
    
    if not qr_codes_contents:
        return jsonify({"message": "No QR codes found for this user."}), 404
    
    # Prepare the list of QR code details (id and content)
    qr_contents_details = [{"id": qr_content[0], "content": qr_content[1]} for qr_content in qr_codes_contents]
    
    # Return the QR code details in the response
    return jsonify({"qr_codes": qr_contents_details}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True)
