
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from functools import wraps
from werkzeug.security import generate_password_hash
from app import get_db_connection, r 
import redis

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

admin_bp = Blueprint('admin', __name__)

def log_event(action, module, email=None, ip=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO audit_logs (user_email, action, module, ip_address) VALUES (%s, %s, %s, %s)",
            (email or session.get('user_email'), action, module, ip or request.remote_addr)
        )
        conn.commit()
    except Exception as e:
        print(f"Logging Error: {e}")
    finally:
        cursor.close()
        conn.close()

# --- MIDDLEWARE: PROTECT ROUTES ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Double check: Dapat logged in at 'super_admin' ang role sa session
        if not session.get('user_id') or session.get('role') != 'super_admin':
            flash("Access Denied: Super Admin privileges required.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# --- DASHBOARD ---
@admin_bp.route('/admin/dashboard')
@admin_required 
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Reservations Count
        cursor.execute("SELECT COUNT(*) as total FROM reservations")
        total_reservations = cursor.fetchone()['total']

        # 2. Inventory Items na Low Stock o Out of Stock
        cursor.execute("SELECT COUNT(*) as low_count FROM inventory WHERE status != 'In Stock'")
        low_stock_count = cursor.fetchone()['low_count']

        # 3. Security: Failed Logins from login_attempts (yung may > 0 attempts)
        cursor.execute("SELECT SUM(attempts) as failed_total FROM login_attempts")
        failed_data = cursor.fetchone()
        failed_logins = failed_data['failed_total'] if failed_data['failed_total'] else 0

        # 4. Security: Blacklisted IPs
        cursor.execute("SELECT COUNT(*) as black_total FROM ip_blacklist WHERE is_whitelisted = 0")
        blacklisted_ips = cursor.fetchone()['black_total']

        # 5. Recent Logs for the Feed
        cursor.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 5")
        recent_logs = cursor.fetchall()

        return render_template('admin/dashboard.html', 
                             total_reservations=total_reservations,
                             low_stock_count=low_stock_count,
                             failed_logins=failed_logins,
                             blacklisted_ips=blacklisted_ips,
                             recent_logs=recent_logs)
    except Exception as e:
        print(f"Admin Error: {e}")
        return "Internal Error", 500
    finally:
        cursor.close()
        conn.close()

# --- STAFF MANAGEMENT ---
@admin_bp.route('/admin/staff/add', methods=['GET', 'POST'])
@admin_required
def add_staff():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        # Basic Validation
        if not name or not email or not password:
            flash("All fields are required for provisioning.")
            return redirect(url_for('admin.add_staff'))

        try:
            # 1. Check kung existing na ang email
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash(f"Provisioning Failed: {email} is already in the system.")
                return redirect(url_for('admin.add_staff'))

            # 2. Secure Hashing of Temporary Password
            hashed_password = generate_password_hash(password)

            # 3. Insert to MySQL
            query = """
                INSERT INTO users (email, password_hash, role, full_name) 
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (email, hashed_password, role, name))
            
            # 4. Log the action (Security Audit)
            log_event(
                action=f"CREATED_ACCOUNT: {email} ({role})",
                module="USER_MGMT",
                email=session.get('user_email')
            )

            conn.commit()
            flash(f"Success: {name} has been provisioned as {role.upper()}.")
            
        except Exception as e:
            conn.rollback()
            flash(f"System Error during provisioning: {str(e)}")
        finally:
            cursor.close()
            conn.close()
            return redirect(url_for('admin.add_staff'))

    # --- GET REQUEST: Load Directory ---
    try:
        # Kunin lahat ng staff members maliban sa kasalukuyang super_admin 
        # para maiwasan ang accidental self-revocation
        cursor.execute("""
            SELECT id, email, full_name, role, created_at 
            FROM users 
            ORDER BY created_at DESC
        """)
        staff_members = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template('admin/add_staff.html', staff=staff_members)

@admin_bp.route('/admin/staff/revoke/<int:user_id>', methods=['POST'])
@admin_required
def revoke_access(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if user:
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            log_event(f"REVOKED_ACCESS: {user['email']}", "USER_MGMT")
            conn.commit()
            flash(f"Access for {user['email']} has been revoked.")
    except Exception as e:
        flash("Error revoking access.")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin.add_staff'))

# --- SECURITY & AUDIT LOGS ---
@admin_bp.route('/admin/logs')
@admin_required
def audit_logs():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        query = """
            SELECT id, user_id, user_email, action, module, ip_address, created_at 
            FROM audit_logs 
            ORDER BY created_at DESC 
            LIMIT 100
        """
        cursor.execute(query)
        logs = cursor.fetchall()
    except Exception as e:
        print(f"Log Fetch Error: {e}")
        logs = []
    finally:
        cursor.close()
        conn.close()
        
    return render_template('admin/audit_logs.html', logs=logs)

# --- RESTRICTED USERS (Login Failures) ---
@admin_bp.route('/admin/restricted')
@admin_required
def restricted_users():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
  
    query = """
        SELECT email, attempts, is_blocked, last_attempt_at 
        FROM login_attempts 
        ORDER BY attempts DESC, last_attempt_at DESC
    """
    cursor.execute(query)
    users = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('admin/restricted_users.html', users=users)

# --- IP MANAGER (Blacklist/Whitelist) ---
@admin_bp.route('/admin/ip-manager')
@admin_required
def ip_manager():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM ip_blacklist ORDER BY created_at DESC")
    ip_list = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('admin/ip_manager.html', ip_list=ip_list)

@admin_bp.route('/admin/ip/blacklist', methods=['POST'])
@admin_required
def blacklist_ip():
    ip = request.form.get('ip_address')
    status = request.form.get('status', 'blacklisted')
    reason = request.form.get('reason', 'Manual Entry')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "REPLACE INTO ip_blacklist (ip_address, status, reason) VALUES (%s, %s, %s)"
    cursor.execute(query, (ip, status, reason))
    conn.commit()
    conn.close()
    
    flash(f"Rule updated for IP: {ip}")
    return redirect(url_for('admin.ip_manager'))

@admin_bp.route('/admin/ip/remove', methods=['POST'])
@admin_required
def remove_ip():
    ip = request.form.get('ip_address')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM ip_blacklist WHERE ip_address = %s", (ip,))
    conn.commit()
    conn.close()
    
    flash(f"Removed access rule for {ip}")
    return redirect(url_for('admin.ip_manager'))

@admin_bp.route('/admin/block_user/<email>', methods=['POST'])
@admin_required
def block_user(email):
    # Dito mo i-uupdate ang 'is_blocked' status sa database mo
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE login_attempts SET is_blocked = 1 WHERE email = %s", (email,))
    conn.commit()
    conn.close()
    
    flash(f"User {email} has been restricted.")
    return redirect(url_for('admin.restricted_users'))

@admin_bp.route('/admin/unblock_user/<email>', methods=['POST'])
@admin_required
def unblock_user(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    # I-reset ang attempts at i-unblock ang user
    cursor.execute("UPDATE login_attempts SET attempts = 0, is_blocked = 0 WHERE email = %s", (email,))
    conn.commit()
    conn.close()
    
    flash(f"Access restored for {email}.")
    return redirect(url_for('admin.restricted_users'))