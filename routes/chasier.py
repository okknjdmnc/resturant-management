from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from functools import wraps
from app import get_db_connection
from datetime import datetime, timezone
import random
import string

cashier_bp = Blueprint('cashier', __name__)

# Security: Cashier Check
def cashier_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') not in ['cashier', 'manager', 'super_admin']:
            flash("Access Denied: Cashier privileges required.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@cashier_bp.route('/dashboard')
@cashier_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Kunin ang lahat ng 'arrive' status (Active Diners na sisingilin)
    cursor.execute("SELECT * FROM reservations WHERE status = 'arrive' ORDER BY table_number ASC")
    active_tables = cursor.fetchall()

    # 2. Shift Summary: Sales Today (Basihan ay yung 'dining' status at date today)
    cursor.execute("""
        SELECT SUM(total_price) as daily_total, COUNT(*) as transaction_count 
        FROM reservations 
        WHERE status = 'dining' AND DATE(created_at) = CURDATE()
    """)
    summary = cursor.fetchone()
    
    daily_total = float(summary['daily_total'] or 0)
    transaction_count = summary['transaction_count'] or 0

    conn.close()
    return render_template('cashier/dashboard.html', 
                           active_tables=active_tables, 
                           daily_total=daily_total, 
                           transaction_count=transaction_count)

@cashier_bp.route('/billing/<int:res_id>')
@cashier_required
def billing(res_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM reservations WHERE id = %s", (res_id,))
    res = cursor.fetchone()
    conn.close()

    if not res:
        flash("Reservation not found!", "danger")
        return redirect(url_for('cashier.dashboard'))

    # Gamitin ang mismong data galing sa DB base sa pinakita mong listahan
    total_price = float(res['total_price'] or 0)
    down_payment = float(res['down_payment'] or 0)
    balance_due = total_price - down_payment

    return render_template('cashier/billing.html', 
                           res=res, 
                           total_price=total_price, 
                           balance_due=balance_due)

@cashier_bp.route('/settle/<int:res_id>', methods=['POST'])
@cashier_required
def settle_account(res_id):
    # Kunin ang values mula sa form (siguraduhin na ang name sa input ay 'cash_received' at 'final_price')
    final_price = float(request.form.get('final_price', 0))
    cash_received = float(request.form.get('cash_received', 0))
    
    # Kunin ang downpayment mula sa DB para sa net calculation kung kailangan
    # Pero base sa billing natin, final_price na ang kailangang bayaran
    change_amount = cash_received - final_price
    
    or_num = "OR-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # --- DAGDAG: Kunin ang details para sa KOT ---
        cursor.execute("SELECT full_name, table_number, package, pax FROM reservations WHERE id = %s", (res_id,))
        res_info = cursor.fetchone()
        guest_name = res_info['full_name'] if res_info else "Unknown"

        # I-save ang tamang cash at change sa transactions table
        cursor.execute("""
            INSERT INTO transactions (reservation_id, or_number, guest_name, total_amount, cash_received, change_amount, processed_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (res_id, or_num, guest_name, final_price, cash_received, change_amount, session.get('role')))

        cursor.execute("UPDATE reservations SET status = 'dining', total_price = %s WHERE id = %s", (final_price, res_id))
        
        # --- DAGDAG: KOT (Kitchen Order Ticket) Generation ---
        if res_info:
            order_summary = f"{res_info['package'].upper()} PACKAGE x {res_info['pax']} PAX"
            cursor.execute("""
                INSERT INTO kot_tickets (or_number, table_number, items_ordered, status) 
                VALUES (%s, %s, %s, 'Pending')
            """, (or_num, res_info['table_number'], order_summary))

        # --- DAGDAG: System Logs ---
        log_msg = f"Payment Processed: {or_num} for {guest_name} | Table {res_info['table_number'] if res_info else 'N/A'}"
        cursor.execute("INSERT INTO system_logs (action, user_role) VALUES (%s, %s)", (log_msg, session.get('role')))

        conn.commit()
        return redirect(url_for('cashier.view_receipt', or_num=or_num))
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('cashier.dashboard'))
    finally:
        conn.close()

@cashier_bp.route('/receipt/<or_num>')
@cashier_required
def view_receipt(or_num):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM transactions WHERE or_number = %s", (or_num,))
    receipt = cursor.fetchone()
    conn.close()
    
    if not receipt:
        flash("Receipt not found!", "danger")
        return redirect(url_for('cashier.dashboard'))
        
    return render_template('cashier/receipt.html', receipt=receipt)