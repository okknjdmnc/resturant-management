from flask import Flask
from config import config
import os

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    from routes.customer import customer_bp
    from routes.auth import auth_bp
    from routes.admin import admin_bp


    app.register_blueprint(customer_bp, url_prefix='/')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp)

    return app
