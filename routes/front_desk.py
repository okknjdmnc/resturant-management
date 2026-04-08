from flask import Blueprint, render_template, redirect, url_for, request, session, flash, jsonify
from functools import wraps
from datetime import datetime
from app import get_db_connection 

front_desk_bp = Blueprint('front_desk', __name__)

# --- ROLE DECORATOR ---
def front_desk_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') not in ['front_desk', 'manager', 'super_admin']:
            flash("Access Denied: Front-desk privileges required.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# --- VIEW FRONT-DESK DASHBOARD ---
@front_desk_bp.route('/front_desk/dashboard')
@front_desk_required
def dashboard():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
        # 1. Kunin ang tables
        cursor.execute("SELECT * FROM tables ORDER BY table_number ASC")
        all_tables = cursor.fetchall()
        
        # 2. Kunin ang active reservations para sa araw na ito
        # Ginagamit natin ang DATE(reservation_date) para makuha lang ang YYYY-MM-DD
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute("""
            SELECT * FROM reservations 
            WHERE status IN ('reserve',  'dining') 
            AND DATE(reservation_date) = %s
            ORDER BY reservation_date ASC
        """, (today,))
        
        active_reservations = cursor.fetchall()

        return render_template(
            "front_desk/front_desk_dashboard.html", 
            tables=all_tables, 
            reservations=active_reservations
        )
    finally:
        cursor.close()
        db.close()

# --- ACTION: MARK AS ARRIVED (SEATED) ---
@front_desk_bp.route('/front_desk/arrive/<int:table_no>/<int:res_id>', methods=['GET', 'POST'])
@front_desk_required
def mark_arrival(table_no, res_id):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # 1. Gawing 'occupied' ang table status
        cursor.execute("UPDATE tables SET status = 'occupied' WHERE table_number = %s", (table_no,))
        
        # 2. Gawing 'arrive' ang reservation status (Base sa ENUM mo)
        # Gagamitin natin ang 'arrive' dahil ito ang nasa listahan mo
        cursor.execute("UPDATE reservations SET status = 'arrive' WHERE id = %s", (res_id,))
        
        db.commit()
        
        # 3. I-redirect sa Table Slip para ma-print agad
        flash(f"Guest Table #{table_no} is now ARRIVED. Printing slip...", "success")
        return redirect(url_for('front_desk.view_slip', res_id=res_id))

    except Exception as e:
        db.rollback()
        print(f"DATABASE ERROR: {str(e)}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('front_desk.dashboard'))
    finally:
        cursor.close()
        db.close()
        
# --- ACTION: CHECKOUT ---
@front_desk_bp.route('/front_desk/checkout/<int:table_no>')
@front_desk_required
def checkout_table(table_no):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # 1. Ibalik sa 'available' ang table status
        cursor.execute("UPDATE tables SET status = 'available' WHERE table_number = %s", (table_no,))
        
        # 2. I-complete ang 'arrive' status para sa table na ito
        # Gumamit tayo ng rowcount check para malaman kung may nagbago talaga
        cursor.execute("""
            UPDATE reservations 
            SET status = 'completed' 
            WHERE table_number = %s AND status = 'arrive'
        """, (table_no,))
        
        db.commit()
        
        if cursor.rowcount > 0:
            flash(f"Table {table_no} has been checked out successfully.", "info")
        else:
            flash(f"Table {table_no} was cleared, but no active 'arrive' record was found.", "warning")

    except Exception as e:
        db.rollback()
        flash(f"Error during checkout: {str(e)}", "danger")
    finally:
        cursor.close()
        db.close()
    
    # 3. REDIRECT: Balik sa Guest List (o kung saan mo tinawag ang modal)
    # Palitan ang 'guest_list' kung iba ang function name ng guest page mo
    return redirect(url_for('front_desk.guest_directory'))

@front_desk_bp.route('/view-slip/<int:res_id>') # Ito ang URL
@front_desk_required
def view_slip(res_id): # Ito ang endpoint name para sa url_for
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM reservations WHERE id = %s", (res_id,))
        res = cursor.fetchone()
        
        if not res:
            flash("Reservation not found.", "danger")
            return redirect(url_for('front_desk.dashboard'))
            
        return render_template('front_desk/table_slip.html', res=res)
    finally:
        cursor.close()
        db.close()

@front_desk_bp.route('/view-event-slip/<int:ev_id>')
@front_desk_required
def view_event_slip(ev_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        # Kukuha ng data mula sa event_reservations table
        cursor.execute("SELECT * FROM event_reservations WHERE id = %s", (ev_id,))
        ev = cursor.fetchone()
        
        if not ev:
            flash("Event booking not found.", "danger")
            return redirect(url_for('front_desk.dashboard'))
            
        # I-render ang event_slip.html at ipasa ang 'ev' variable
        return render_template('front_desk/event_slip.html', ev=ev)
    except Exception as e:
        print(f"Error: {e}")
        flash("An error occurred while fetching the event slip.", "danger")
        return redirect(url_for('front_desk.dashboard'))
    finally:
        cursor.close()
        db.close()

@front_desk_bp.route('/guest-directory')
@front_desk_required
def guest_directory():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
        # Kunin ang lahat ng Table Reservations
        cursor.execute("""
            SELECT id, code, full_name, table_number, reservation_date, status, 
                   down_payment, payment_method, downpayment_receipt, verification_id, 
                   pax, package 
            FROM reservations 
            ORDER BY created_at DESC
        """)
        table_guests = cursor.fetchall()

        # Kunin ang lahat ng Private Events (Assuming 'events' table name)
        cursor.execute("SELECT * FROM event_reservations ORDER BY event_datetime DESC")
        event_guests = cursor.fetchall()

        return render_template(
            "front_desk/guest_list.html", 
            table_guests=table_guests, 
            event_guests=event_guests
        )
    finally:
        cursor.close()
        db.close()

@front_desk_bp.route('/cancel-booking/<int:res_id>')
@front_desk_required
def cancel_booking(res_id):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # I-update ang status sa 'cancelled'
        cursor.execute("UPDATE reservations SET status = 'cancelled' WHERE id = %s", (res_id,))
        db.commit()
        
        flash(f"Booking #{res_id} has been cancelled.", "warning")
    except Exception as e:
        db.rollback()
        flash("Error cancelling booking.", "danger")
    finally:
        cursor.close()
        db.close()
        
    return redirect(url_for('front_desk.dashboard'))

@front_desk_bp.route('/front_desk/get_reservation/<int:res_id>')
@front_desk_required
def get_reservation(res_id):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Gagamit tayo ng 'AS' para magtugma sa JavaScript keys
    cursor.execute("""
        SELECT 
            full_name AS name, 
            pax, 
            package AS tier 
        FROM reservations 
        WHERE id = %s
    """, (res_id,))
    res = cursor.fetchone()
    
    cursor.close()
    db.close()
    
    if res:
        return jsonify(res)
    return jsonify({"error": "Not found"}), 404

@front_desk_bp.route('/front_desk/checkin/<int:table_no>', methods=['POST'])
@front_desk_required
def checkin_guest(table_no):
    # Kunin ang data mula sa form ng Modal
    res_id = request.form.get('res_id')
    menu_level = request.form.get('menu_level') # 'standard', 'premium', etc.
    
    db = get_db_connection()
    cursor = db.cursor()
    try:
        # 1. Gawing 'occupied' ang table status
        cursor.execute("UPDATE tables SET status = 'occupied' WHERE table_number = %s", (table_no,))
        
        # 2. Check kung Reservation o Walk-in
        if res_id and res_id != '0':
            # KUNG RESERVATION: I-update ang existing record
            cursor.execute("""
                UPDATE reservations 
                SET status = 'arrive', package = %s 
                WHERE id = %s AND table_number = %s
            """, (menu_level, res_id, table_no))
        else:
            # KUNG WALK-IN: Gawan ng bagong record para pumasok sa sales/history
            cursor.execute("""
                INSERT INTO reservations (full_name, table_number, status, package, pax, reservation_date)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, ('Walk-in Guest', table_no, 'arrive', menu_level, 1)) # Default 1 pax kung walk-in
            
        db.commit()
        flash(f"Check-in successful for Table {table_no}!", "success")
    except Exception as e:
        db.rollback()
        flash(f"Database Error: {str(e)}", "danger")
    finally:
        cursor.close()
        db.close()
        
    return redirect(url_for('front_desk.dashboard'))