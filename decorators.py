from functools import wraps
from flask import session, redirect, url_for, flash

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('user_id'):
                return redirect(url_for('auth.login'))
            
            
            if session.get('role') not in allowed_roles and session.get('role') != 'super_admin':
                flash("Access Denied: You don't have permission for this module.")
                return redirect(url_for('main.dashboard')) 
            return f(*args, **kwargs)
        return decorated_function
    return decorator