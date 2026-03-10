from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from .customer import get_supabase 
from supabase import create_client
admin_bp = Blueprint('admin', __name__)

# iche-check nito kung admin ang pumasok
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"DEBUG: Current Session Role is -> {session.get('role')}")
        if not session.get('user_id') or session.get('role') != 'super_admin':
            flash("Access Denied: Super Admin privileges required.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_supabase_admin():
    url = "https://vtsmhotqxtmwyhwznvlx.supabase.co"
    service_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ0c21ob3RxeHRtd3lod3pudmx4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MjUzODQwNywiZXhwIjoyMDg4MTE0NDA3fQ.D4BpfR-oxK1RtSOml5LgeBNNH5yLPu-sbc2Dg6d6LoA"
    return create_client(url, service_key)

# --- ROUTES ---

@admin_bp.route('/admin/dashboard')
@admin_required 
def dashboard():
    supabase = get_supabase()
    
    # total reservations
    res = supabase.table('reservations').select("*", count="exact").execute()
    total_res = res.count if res.count else 0
    
    return render_template('admin/dashboard.html', 
                         user=session.get('user_email'),
                         total_reservations=total_res)

@admin_bp.route('/admin/audit-logs')
@admin_required
def audit_logs():
    supabase = get_supabase()
    
    try:
        # Kunin ang lahat ng logs mula sa 'audit_logs' table
        # limitahan sa 50 para mabilis mag-load
        response = supabase.table('audit_logs') \
            .select("*") \
            .order('created_at', desc=True) \
            .limit(50) \
            .execute()
        
        logs_data = response.data
        
    except Exception as e:
        print(f"Error fetching audit logs: {e}")
        logs_data = [] # Para hindi mag-crash  kung walang data
        flash("Could not retrieve system logs.")

    # I-render ang template 
    return render_template('admin/audit_logs.html', logs=logs_data)

@admin_bp.route('/admin/staff/add', methods=['GET', 'POST'])
@admin_required
def add_staff():

    supabase = get_supabase()
    supabase_admin = get_supabase_admin()

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        try:
            # register ang user sa Auth ng Supabase
            auth_res = supabase_admin.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True
            })
            
            if auth_res.user:
                # insert ang role sa profiles table
                supabase.table('profiles').insert({
                    "id": auth_res.user.id,
                    "role": role,
                    "email": email
                }).execute()

                # Mag-log sa Audit Logs
                supabase.table('audit_logs').insert({
                    "user_id": session.get('user_id'),
                    "user_email": session.get('user_email'),
                    "action": f"CREATED_STAFF_{role.upper()}",
                    "module": "STAFF_MANAGEMENT",
                    "ip_address": request.remote_addr
                }).execute()

                flash(f"Successfully added {email} as {role}.")
                return redirect(url_for('admin.dashboard'))

        except Exception as e:
            print(f"Error adding staff: {e}")
            flash(f"Failed to add staff: {str(e)}")

    try:
        staff_res = supabase.table('profiles').select("*").order('role').execute()
        staff_list = staff_res.data
    except Exception as e:
        print(f"Error fetching staff: {e}")
        staff_list = []
    return render_template('admin/add_staff.html', staff_list=staff_list)