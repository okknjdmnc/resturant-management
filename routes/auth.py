from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from supabase import create_client
from datetime import datetime, timezone, timedelta
import random
import resend

auth_bp = Blueprint('auth', __name__)

RESEND_API_KEY = "re_7zP9qTJ6_2T4wTvsYa9Jpnq714bWLhxsr"
resend.api_key = RESEND_API_KEY

def get_supabase():
    url = "https://vtsmhotqxtmwyhwznvlx.supabase.co"
    key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ0c21ob3RxeHRtd3lod3pudmx4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI1Mzg0MDcsImV4cCI6MjA4ODExNDQwN30.JpH5FZSt6R6ODbxPQ8-K8tpCiF90IOpbumRPbeS1wHA"

    print(f"DEBUG: URL is {url}")
    print(f"DEBUG: Key starts with {key[:15]}")
    return create_client(url, key)

def send_otp_email(email, code):
    resend.Emails.send({
        "from": "GOJO HOUSE <onboarding@resend.dev>",
        "to": email,
        "subject": "Your Verification Code",
        "html": f"""
            <h2>Verification Code</h2>
            <p>Your OTP code is:</p>
            <h1 style="letter-spacing: 8px; color: #4F46E5;">{code}</h1>
            <p>This code expires in <strong>5 minutes</strong>.</p>
            <p>If you didn't request this, ignore this email.</p>
        """
    })

@auth_bp.route('/login')
def login():
    return render_template('auth/login.html')


# @auth_bp.route('/login/submit', methods=['POST'])
# def login_post():
#     email = request.form.get('email')
#     password = request.form.get('password')
#     supabase = get_supabase()

#     try:
#         # Siguraduhin na malinis ang session
#         supabase.auth.sign_out()

#         # I-verify ang Password
#         auth_response = supabase.auth.sign_in_with_password({
#             "email": email,
#             "password": password
#         })
        
#         user = auth_response.user

#         # Kunin ang Role mula sa profiles table
#         profile_res = supabase.table('profiles').select('role').eq('id', user.id).single().execute()
#         user_role = profile_res.data['role']

#         # I-save na ang lahat sa Session 
#         session['user_id'] = user.id
#         session['user_email'] = user.email
#         session['role'] = user_role

#         # Mag-insert ng Audit Log para sa successful login
#         supabase.table('audit_logs').insert({
#             "user_id": user.id,
#             "user_email": user.email,
#             "action": "LOGIN_BYPASS_MFA",
#             "module": "AUTHENTICATION",
#             "ip_address": request.remote_addr
#         }).execute()

#         # Redirect base sa role
#         if user_role == 'super_admin':
#             return redirect(url_for('admin.dashboard'))
#         elif user_role == 'waiter':
#             return redirect(url_for('pos.waiter_dashboard'))
#         else:
#             return redirect(url_for('customer.index'))

#     except Exception as e:
#         print(f"Login Error: {e}")
#         flash(f"Login failed: {str(e)}")
#         return redirect(url_for('auth.login'))

@auth_bp.route('/verify-otp')
def verify_otp():
    if 'temp_email' not in session:
        return redirect(url_for('auth.login'))
    return render_template('auth/verify.html')


@auth_bp.route('/login/submit', methods=['POST'])
def login_post():
    email = request.form.get('email')
    password = request.form.get('password')
    supabase = get_supabase()


    if not email:
        flash("email should not be empty", "error")
        return redirect(url_for('auth.login'))
    
    if not password:
        flash("Password should not empty")
        return redirect(url_for('auth.log'))
    
    

    try:
        # Verify password
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        # save ang user info bago mag sign_out
        user_id = auth_response.user.id
        user_email = auth_response.user.email

        # Sign out agad 
        supabase.auth.sign_out()

        # Generate OTP
        code = str(random.randint(100000, 999999))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        supabase.table('otp_codes').delete().eq('email', email).execute()
        supabase.table('otp_codes').insert({
            "email": email,
            "code": code,
            "expires_at": expires_at.isoformat(),
            "used": False
        }).execute()

        send_otp_email(email, code)

        # user_id  ang i-save hindi token
        session['temp_email'] = email
        session['temp_user_id'] = user_id

        flash("A verification code has been sent to your email.")
        return redirect(url_for('auth.verify_otp'))

    except Exception as e:
        print(f"Login Error: {e}")
        flash("Invalid email or password.")
        return redirect(url_for('auth.login'))


@auth_bp.route('/verify-otp/submit', methods=['POST'])
def verify_otp_submit():
    otp_code = request.form.get('otp_code')
    email = session.get('temp_email')
    user_id = session.get('temp_user_id')  # user_id
    supabase = get_supabase()

    try:
        now = datetime.now(timezone.utc)

        # I-check ang OTP sa database
        result = (
            supabase.table('otp_codes')
            .select('*')
            .eq('email', email)
            .eq('code', otp_code)
            .eq('used', False)
            .execute()
        )

        if not result.data:
            raise Exception("Invalid OTP code")

        otp_record = result.data[0]

        # I-check kung expired
        expires_at = datetime.fromisoformat(otp_record['expires_at'])
        if now > expires_at:
            raise Exception("OTP has expired")

        # Mark as used
        supabase.table('otp_codes').update({"used": True}).eq('id', otp_record['id']).execute()

        # Gamitin ang service role key para makuha ang user info
        profile_res = (
            supabase.table('profiles')
            .select('role')
            .eq('id', user_id)
            .single()
            .execute()
        )
        user_role = profile_res.data['role']

        # I-save sa session gamit ang naka-store na user_id
        session.clear()
        session['user_id'] = user_id
        session['user_email'] = email
        session['role'] = user_role

        supabase.table('audit_logs').insert({
            "user_id": user_id,
            "user_email": email,
            "action": "MFA_LOGIN_SUCCESS",
            "module": "AUTHENTICATION",
            "ip_address": request.remote_addr
        }).execute()

        if user_role == 'super_admin':
            return redirect(url_for('admin.dashboard'))
        elif user_role == 'waiter':
            return redirect(url_for('pos.waiter_dashboard'))
        else:
            return redirect(url_for('customer.index'))

    except Exception as e:
        print(f"OTP Error: {e}")
        flash("Invalid or expired verification code.")
        return redirect(url_for('auth.verify_otp'))
    
@auth_bp.route('/logout')
def logout():
    supabase = get_supabase()
    try:
        supabase.auth.sign_out()
    except:
        pass
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for('auth.login'))