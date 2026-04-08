from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from functools import wraps
from app import get_db_connection
from datetime import datetime, timezone
from data.menu_data import menu_data

kitchen_bp = Blueprint("kitchen", __name__)

# Authentication Decorator
def kitchen_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') not in ['kitchen', 'manager', 'super_admin']:
            flash("Access Denied: Kitchen Staff access only.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# --- DASHBOARD ROUTE ---
@kitchen_bp.route('/kitchen/dashboard')
@kitchen_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. Kunin ang Kitchen Stocks (Base sa table mo)
        cursor.execute("""
            SELECT item_name, transferred_quantity, unit 
            FROM kitchen_stocks 
            ORDER BY item_name ASC
        """)
        stocks = cursor.fetchall()
        
        # 2. Kunin ang mga Active KOT (Pending at Preparing)
        # Naka-order by ASC para First-In, First-Out (FIFO)
        cursor.execute("""
            SELECT id, or_number, table_number, items_ordered, status, created_at 
            FROM kot_tickets 
            WHERE status IN ('Pending', 'Preparing') 
            ORDER BY created_at ASC
        """)
        active_kots = cursor.fetchall()
        
    except Exception as e:
        print(f"Kitchen Error: {e}")
        flash("Error loading kitchen data.", "danger")
        stocks, active_kots = [], []
    finally:
        conn.close()
        
    return render_template('kitchen/dashboard.html', 
                           stocks=stocks, 
                           kots=active_kots)

# --- UPDATE KOT STATUS ---
@kitchen_bp.route('/update_status/<int:kot_id>/<string:new_status>', methods=['POST'])
@kitchen_required
def update_status(kot_id, new_status):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Update KOT status
        cursor.execute("UPDATE kot_tickets SET status = %s WHERE id = %s", (new_status, kot_id))
        
        # Log action
        log_msg = f"KOT #{kot_id} updated to {new_status}"
        cursor.execute("INSERT INTO system_logs (action, user_role) VALUES (%s, %s)", (log_msg, session.get('role')))
        
        conn.commit()
        
        # REDIRECT LOGIC: Kung 'Preparing', punta sa Active Sessions. Kung 'Served', balik sa Dashboard.
        if new_status == 'Preparing':
            flash(f"Order #{kot_id} is now being prepared!", "success")
            return redirect(url_for('kitchen.active_sessions'))
        else:
            flash(f"Order #{kot_id} served!", "success")
            return redirect(url_for('kitchen.dashboard'))
            
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('kitchen.dashboard'))
    finally:
        conn.close()

# --- RECENTLY SERVED (Para sa Monitoring) ---
@kitchen_bp.route('/kitchen/history')
@kitchen_required
def history():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    # Pakita yung huling 20 orders na nase-serve na
    cursor.execute("SELECT * FROM kot_tickets WHERE status = 'Served' ORDER BY created_at DESC LIMIT 20")
    served_history = cursor.fetchall()
    conn.close()
    return render_template('kitchen/history.html', history=served_history)

import json

@kitchen_bp.route('/active-sessions')
@kitchen_required
def active_sessions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Kunin ang mga tables na status ay 'dining' o 'arrive'
    # Gagamitin natin ang reservations table bilang base ng 'session'
    cursor.execute("""
        SELECT id, table_number as table_no, package as menu_level, 
               created_at, refill_count, refill_history 
        FROM reservations 
        WHERE status = 'dining' 
        ORDER BY table_number ASC
    """)
    sessions = cursor.fetchall()
    
    # I-parse ang refill_history (dahil JSON string ito sa DB)
    for s in sessions:
        if s['refill_history']:
            s['refill_history'] = json.loads(s['refill_history'])
        else:
            s['refill_history'] = []

    conn.close()
    return render_template('kitchen/active_sessions.html', sessions=sessions, menu_data=menu_data)

@kitchen_bp.route('/trigger-refill/<int:order_id>/<string:item_name>')
@kitchen_required
def trigger_refill(order_id, item_name):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. Bawasan ang kitchen_stocks (Fixed deduction: 0.20kg or 200g)
        # Gagamitin natin ang 'item_name' para hanapin ang stock
        cursor.execute("""
            UPDATE kitchen_stocks 
            SET transferred_quantity = transferred_quantity - 0.20 
            WHERE item_name LIKE %s AND transferred_quantity >= 0.20
        """, (f"%{item_name}%",))
        
        if cursor.rowcount == 0:
            flash(f"Insufficient stock for {item_name}!", "danger")
            return redirect(url_for('kitchen.active_sessions'))

        # 2. I-update ang refill_history sa reservations table
        cursor.execute("SELECT refill_history, refill_count FROM reservations WHERE id = %s", (order_id,))
        res = cursor.fetchone()
        
        current_history = json.loads(res['refill_history']) if res['refill_history'] else []
        new_entry = {
            "items": item_name,
            "status": "served", # o 'pending' kung gusto mo pa i-verify
            "timestamp": datetime.now().strftime("%H:%M")
        }
        current_history.append(new_entry)
        
        new_count = (res['refill_count'] or 0) + 1
        
        cursor.execute("""
            UPDATE reservations 
            SET refill_history = %s, refill_count = %s 
            WHERE id = %s
        """, (json.dumps(current_history), new_count, order_id))
        
        conn.commit()
        flash(f"Refill added: {item_name} (-200g stock)", "success")
        
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for('kitchen.active_sessions'))

@kitchen_bp.route('/mark-done/<int:order_id>')
@kitchen_required
def mark_done(order_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Tapos na kumain, gawing 'finished' ang status para mawala sa active list
        # Pero ang table status sa 'tables' table ay dapat maging 'cleaning' or 'available'
        cursor.execute("SELECT table_number FROM reservations WHERE id = %s", (order_id,))
        table_no = cursor.fetchone()[0]
        
        cursor.execute("UPDATE reservations SET status = 'completed' WHERE id = %s", (order_id,))
        cursor.execute("UPDATE tables SET status = 'available' WHERE table_number = %s", (table_no,))
        
        conn.commit()
        flash(f"Table {table_no} session ended.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for('kitchen.active_sessions'))