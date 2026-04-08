import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # --- MySQL Configuration ---
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'resturant_system')
    # ----------------------------------------

    # Idagdag ito sa Config class sa config.py
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') # Ang email mo
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') # Ang App Password (hindi regular password)
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME')

    # Session settings
    SESSION_COOKIE_SECURE = True       
    SESSION_COOKIE_HTTPONLY = True     
    SESSION_COOKIE_SAMESITE = 'Lax'   
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)  
    SESSION_PERMANENT = True

    # Supabase
    SUPABASE_URL = os.environ.get('SUPABASE_URL')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

    # --- File Upload Settings Receipts / Menu Images ---
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # Limit sa 5MB ang uploads
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    # -------------------------------------------------------------

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  
    

class ProductionConfig(Config):
    DEBUG = False

    SESSION_COOKIE_SECURE = True

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}