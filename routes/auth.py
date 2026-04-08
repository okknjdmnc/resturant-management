
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from datetime import datetime, timedelta, timezone
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.security import check_password_hash
from app import limiter, get_db_connection

auth_bp = Blueprint('auth', __name__)

MAX_ATTEMPTS = 3

# --- GMAIL SMTP FUNCTION (Same as before) ---
def send_otp_email(receiver_email, otp_code):
    sender_email = "chrmasong@gmail.com"
    app_password = "stbu vkhx otzj fbdd"
    message = MIMEMultipart()
    message["From"] = f"Gojo House <{sender_email}>"
    message["To"] = receiver_email
    message["Subject"] = f"{otp_code} is your Verification Code"
    
    body = f"""
    <html>
        <body style="font-family: sans-serif; background-color: #000; color: #fff; padding: 20px;">
            <div style="border: 1px solid #333; padding: 40px; border-radius: 20px; text-align: center;">
                <h1 style="color: #00f2ff; letter-spacing: 5px;">GOJO HOUSE</h1>
                <p>Your verification code is:</p>
                <h2 style="font-size: 40px; font-weight: bold; letter-spacing: 10px; color: #fff;">{otp_code}</h2>
                <p style="font-size: 10px; color: #555;">Expires in 5 minutes.</p>
            </div>
        </body>
    </html>
    """
    message.attach(MIMEText(body, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        return True
    except Exception as e:
        print(f"SMTP ERROR: {e}")
        return False

# --- ROUTES ---

@auth_bp.route('/login')
def login():
    return render_template('auth/login.html')

@auth_bp.route('/blocked')
def blocked():
    return render_template('auth/blocked.html')

@auth_bp.route('/login/submit', methods=['POST'])
@limiter.limit("5 per minute")
def login_post():
    email = request.form.get('email')
    password = request.form.get('password')
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if not email or not password:
        flash("Email and Password are required.")
        return redirect(url_for('auth.login'))

    # 1. Check kung blocked na sa MySQL
    cursor.execute("SELECT attempts, is_blocked FROM login_attempts WHERE email = %s", (email,))
    attempt_record = cursor.fetchone()

    if attempt_record and attempt_record['is_blocked']:
        return redirect(url_for('auth.blocked'))

    try:
        # 2. Hanapin ang user sa 'users' table (Dapat may table ka na 'users' o 'profiles')
        cursor.execute("SELECT id, email, password_hash, role FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        # 3. Verify Password using Werkzeug
        if user and check_password_hash(user['password_hash'], password):
            # SUCCESS: Reset attempts
            cursor.execute("UPDATE login_attempts SET attempts = 0, is_blocked = 0 WHERE email = %s", (email,))
            db.commit()

            # 4. Generate at Save OTP sa MySQL
            code = str(random.randint(100000, 999999))
            expires_at = datetime.now() + timedelta(minutes=5)

            cursor.execute("DELETE FROM otp_codes WHERE email = %s", (email,))
            cursor.execute("INSERT INTO otp_codes (email, code, expires_at, used) VALUES (%s, %s, %s, 0)", 
                           (email, code, expires_at))
            db.commit()

            # 5. Ipadala ang OTP email
            if send_otp_email(email, code):
                session['temp_email'] = email
                session['temp_user_id'] = user['id']
                flash("Verification code sent to your email.")
                return redirect(url_for('auth.verify_otp'))
            else:
                flash("Failed to send email.")
                return redirect(url_for('auth.login'))

        else:
            # 6. FAIL: Increment attempts sa MySQL
            new_count = (attempt_record['attempts'] + 1) if attempt_record else 1
            blocked_status = 1 if new_count >= MAX_ATTEMPTS else 0
            
            if attempt_record:
                cursor.execute("UPDATE login_attempts SET attempts = %s, is_blocked = %s WHERE email = %s", 
                               (new_count, blocked_status, email))
            else:
                cursor.execute("INSERT INTO login_attempts (email, attempts, is_blocked) VALUES (%s, %s, %s)", 
                               (email, new_count, blocked_status))
            
            db.commit()
            
            if blocked_status:
                # Audit Log sa MySQL
                cursor.execute("INSERT INTO audit_logs (user_email, action, module, ip_address) VALUES (%s, %s, %s, %s)",
                               (email, 'ACCOUNT_BLOCKED', 'AUTHENTICATION', request.remote_addr))
                db.commit()
                return redirect(url_for('auth.blocked'))
            
            flash(f"Invalid credentials. {MAX_ATTEMPTS - new_count} attempt(s) remaining.")
            return redirect(url_for('auth.login'))

    except Exception as e:
        print(f"Login Error: {e}")
        flash("An error occurred during login.")
        return redirect(url_for('auth.login'))
    finally:
        cursor.close()
        db.close()

@auth_bp.route('/verify-otp')
def verify_otp():
    if 'temp_email' not in session:
        return redirect(url_for('auth.login'))
    return render_template('auth/verify.html')

@auth_bp.route('/verify-otp/submit', methods=['POST'])
def verify_otp_submit():
    otp_code = request.form.get('otp_code')
    email = session.get('temp_email')
    user_id = session.get('temp_user_id')
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    try:
        # Check OTP sa MySQL
        cursor.execute("SELECT id, expires_at FROM otp_codes WHERE email = %s AND code = %s AND used = 0", 
                       (email, otp_code))
        otp_record = cursor.fetchone()

        if not otp_record:
            flash("Invalid OTP code.")
            return redirect(url_for('auth.verify_otp'))

        if datetime.now() > otp_record['expires_at']:
            flash("OTP has expired.")
            return redirect(url_for('auth.verify_otp'))

        # Mark OTP as used
        cursor.execute("UPDATE otp_codes SET used = 1 WHERE id = %s", (otp_record['id'],))

        send_login_notification(email, request.remote_addr)
        
        # Kunin ang Role ng user
        cursor.execute("SELECT role FROM users WHERE id = %s", (user_id,))
        user_role = cursor.fetchone()['role']

        # Set Full Session
        session.clear()
        session['user_id'] = user_id
        session['user_email'] = email
        session['role'] = user_role

        # Audit Log success
        cursor.execute("INSERT INTO audit_logs (user_id, user_email, action, module, ip_address) VALUES (%s, %s, %s, %s, %s)",
                       (user_id, email, 'MFA_LOGIN_SUCCESS', 'AUTHENTICATION', request.remote_addr))
        db.commit()

        # Redirects (Same as your previous logic)
        role_redirects = {
            'super_admin': 'admin.dashboard',
            'manager': 'manager.dashboard',
            'front_desk': 'front_desk.dashboard',
            'cashier': 'cashier.dashboard',
            'staff': 'inventory.dashboard',
            'kitchen': 'kitchen.dashboard'
        }
        return redirect(url_for(role_redirects.get(user_role, 'customer.index')))

    except Exception as e:
        print(f"OTP Error: {e}")
        flash("Verification failed.")
        return redirect(url_for('auth.verify_otp'))
    finally:
        cursor.close()
        db.close()
    
# --- LOGIN NOTIFICATION EMAIL ---
def send_login_notification(receiver_email, ip_address):
    sender_email = "chrmasong@gmail.com"
    app_password = "stbu vkhx otzj fbdd" 

    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")

    message = MIMEMultipart()
    message["From"] = f"Gojo House <{sender_email}>"
    message["To"] = receiver_email
    message["Subject"] = "New Login Detected – Gojo House"

    body = f"""
    <html>
        <body style="font-family: sans-serif; background-color: #000; color: #fff; padding: 20px;">
            <div style="border: 1px solid #333; padding: 40px; border-radius: 20px; max-width: 480px; margin: auto;">
                <h1 style="color: #00f2ff; letter-spacing: 5px; font-size: 20px;">GOJO HOUSE</h1>
                <p style="color: #aaa; font-size: 13px;">A successful login was detected on your account.</p>

                <div style="background: #111; border: 1px solid #222; border-radius: 12px; padding: 20px; margin: 24px 0;">
                    <table style="width: 100%; font-size: 12px; color: #ccc; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #555; text-transform: uppercase; letter-spacing: 2px; width: 40%;">Time</td>
                            <td style="padding: 8px 0;">{now}</td>
                        </tr>
                        <tr style="border-top: 1px solid #1a1a1a;">
                            <td style="padding: 8px 0; color: #555; text-transform: uppercase; letter-spacing: 2px;">IP Address</td>
                            <td style="padding: 8px 0;">{ip_address}</td>
                        </tr>
                        <tr style="border-top: 1px solid #1a1a1a;">
                            <td style="padding: 8px 0; color: #555; text-transform: uppercase; letter-spacing: 2px;">Account</td>
                            <td style="padding: 8px 0;">{receiver_email}</td>
                        </tr>
                    </table>
                </div>

                <p style="color: #aaa; font-size: 12px; line-height: 1.8;">
                    If this was you, no action is needed.<br>
                    If you did <strong style="color: #ff4444;">NOT</strong> perform this login,
                    please contact your administrator immediately.
                </p>

                <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #1a1a1a;">
                    <p style="color: #333; font-size: 10px; text-transform: uppercase; letter-spacing: 3px; margin: 0;">
                        Gojo House Security System - Automated Alert
                    </p>
                </div>
            </div>
        </body>
    </html>
    """
    message.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        print(f"Login notification sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"Login Notification SMTP ERROR: {e}")
        return False 

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.")
    return redirect(url_for('auth.login'))