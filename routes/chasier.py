from flask import Blueprint, render_template, request, url_for, flash, session, redirect
from .customer import get_supabase


cashier_bp = Blueprint("cashier_bp", __name__)

def cashier_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"DEBUG: Current Session Role is -> {session.get('role')}")
        if not session.get('user_id') or session.get('role') != 'cashier':
            flash("Access Denied: Cashier privileges required.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@cashier_bp.route('/cashier')
@cashier_required
def dashboard():
    return render_template("")