import os
import redis
import mysql.connector
from flask import Flask, redirect, url_for, flash, request as flask_request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_limiter.errors import RateLimitExceeded
from config import config
from flask_mail import Mail

# Initialize Extensions
mail = Mail()

# --- REDIS CONFIG ---
redis_uri = os.getenv("REDIS_URL", "memory://")
r = None
if redis_uri.startswith("redis"):
    r = redis.from_url(redis_uri, decode_responses=True)

# --- LIMITER ---
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=redis_uri,
    storage_options={"ssl_cert_reqs": None} # Para sa Upstash/Cloud
)

# --- MYSQL CONNECTION HELPER ---
def get_db_connection():
    from flask import current_app
    return mysql.connector.connect(
        host=current_app.config['MYSQL_HOST'],
        user=current_app.config['MYSQL_USER'],
        password=current_app.config['MYSQL_PASSWORD'],
        database=current_app.config['MYSQL_DB']
    )

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Create upload folder if not exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Init Extensions
    mail.init_app(app)
    limiter.init_app(app)

    # --- SECURITY: BLACKLIST CHECK ---
    @app.before_request
    def check_ip_blacklist():
        if flask_request.path.startswith('/static'):
            return

        ip = flask_request.remote_addr
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # Check kung ang IP ay nasa blacklist table sa MySQL
            cursor.execute("SELECT * FROM ip_blacklist WHERE ip_address = %s AND is_whitelisted = 0", (ip,))
            if cursor.fetchone():
                return "Your IP has been restricted from accessing Gojo House.", 403
        except Exception as e:
            app.logger.error(f"Blacklist Error: {e}")
        finally:
            cursor.close()
            conn.close()

    # --- HEADERS: NO CACHE ---
    @app.after_request
    def add_header(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # --- ERROR HANDLER ---
    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(e):
        flash("Too many attempts. The system has temporarily throttled your request.", "error")
        return redirect(url_for('auth.login')), 429

    # --- REGISTER BLUEPRINTS ---
    from routes.customer import customer_bp
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.manager import manager_bp
    from routes.inventory import inventory_bp
    from routes.front_desk import front_desk_bp
    from routes.chasier import cashier_bp
    from routes.kitchen import kitchen_bp

    app.register_blueprint(customer_bp, url_prefix='/')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp) 
    app.register_blueprint(manager_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(front_desk_bp)
    app.register_blueprint(cashier_bp)
    app.register_blueprint(kitchen_bp)

    return app