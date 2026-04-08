from flask import Blueprint, render_template, current_app, request, redirect, url_for, jsonify
import mysql.connector
import uuid
import os
import string
import random
from datetime import datetime
from flask_mail import Message
from app import mail
from helper import send_reservation_email, send_event_confirmation_email

customer_bp = Blueprint('customer', __name__)

# --- HELPERS ---

def generate_res_code():
    chars = string.ascii_uppercase + string.digits
    return "GOJO-" + ''.join(random.choices(chars, k=6))

def get_db():
    return mysql.connector.connect(
        host=current_app.config['MYSQL_HOST'],
        user=current_app.config['MYSQL_USER'],
        password=current_app.config['MYSQL_PASSWORD'],
        database=current_app.config['MYSQL_DB']
    )

def fetch_menu_from_db():
    """Pinagsama ang DB items at UI metadata (colors/icons)"""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM menu_items")
        rows = cursor.fetchall()
        
        # Default structure na kailangan ng templates mo
        formatted_menu = {
            "normal": {
                "label": "Normal", "color": "#4ade80", "icon": "🟢", "price_add": 699,
                "description": "Classic comfort dishes — perfect for all diners", "items": []
            },
            "high": {
                "label": "High-End", "color": "#facc15", "icon": "🟡", "price_add": 998,
                "description": "Premium cuts and elevated flavors", "items": []
            },
            "hard": {
                "label": "Hard Mode", "color": "#f87171", "icon": "🔴", "price_add": 1298,
                "description": "Bold, extreme, and unforgettable", "items": []
            }
        }
        
        for row in rows:
            t_raw = row['tier'].lower()
            if 'hard' in t_raw: key = 'hard'
            elif 'high' in t_raw: key = 'high'
            else: key = 'normal'
            formatted_menu[key]['items'].append(row)
            
        return formatted_menu
    finally:
        cursor.close()
        db.close()

# --- ROUTES ---

@customer_bp.route('/')
def index():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM menu_items")
        all_items = cursor.fetchall()
        
        normal_items = [item for item in all_items if item.get('category') == 'Normal']
        high_items = [item for item in all_items if item.get('category') == 'High-End']
        hard_items = [item for item in all_items if item.get('category') == 'Hard Mode']
        
        return render_template(
            "costumer/index.html", 
            normal_items=normal_items,
            high_items=high_items,   
            hard_items=hard_items    
        )

    except Exception as e:
        print(f"Error logic: {e}")
        return f"Error: {e}", 500
    finally:
        cursor.close()
        db.close()

@customer_bp.route('/reserve')
def reserve_selection():
    return render_template("costumer/reserve_selection.html")

@customer_bp.route('/reserve/tiers')
def reserve_tiers():
    menu_data = fetch_menu_from_db()
    return render_template("costumer/tier_selection.html", menu=menu_data)

@customer_bp.route('/reserve/table-selection/<tier>')
def table_selection(tier):
    menu_data = fetch_menu_from_db()
    tier_info = menu_data.get(tier)
    
    if not tier_info:
        return redirect(url_for('customer.reserve_tiers'))
    
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tables ORDER BY table_number")
    db_tables = cursor.fetchall()
    
    couples = [t for t in db_tables if t['capacity'] == 2]
    family = [t for t in db_tables if t['capacity'] == 4]
    
    cursor.close()
    db.close()
    
    return render_template(
        "costumer/table_selection.html", 
        tier=tier, 
        tier_info=tier_info,
        couples=couples,
        family=family
    )

@customer_bp.route('/reserve/details')
def reserve_details():
    tier = request.args.get('tier')
    table_no = request.args.get('table') 
    
    pax = request.args.get('num_guests') or request.args.get('pax') or 2
    
    print(f"DEBUG Step 2: Pax from URL is {pax}") 

    menu_data = fetch_menu_from_db()
    tier_info = menu_data.get(tier)

    if not table_no:
        return redirect(url_for('customer.table_selection', tier=tier))

    return render_template(
        "costumer/booking_form.html", 
        tier=tier, 
        table_id=table_no, 
        pax=pax,
        tier_info=tier_info
    )

@customer_bp.route('/reserve/submit', methods=["POST"])
def submit_reservation():
    db = get_db()
    cursor = db.cursor()
    res_code = generate_res_code()
    customer_email = request.form.get('email') 
    
    try:
        # 1. File Handling (ID and Receipt)
        id_file = request.files.get('id_image')
        receipt_file = request.files.get('receipt_image')
        id_path, receipt_path = "", ""

        if id_file and id_file.filename != '':
            id_filename = f"id_{res_code}_{uuid.uuid4().hex[:4]}.jpg"
            id_file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], id_filename))
            id_path = id_filename 

        if receipt_file and receipt_file.filename != '':
            rec_filename = f"rec_{res_code}_{uuid.uuid4().hex[:4]}.jpg"
            receipt_file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], rec_filename))
            receipt_path = rec_filename

        # 2. Form Data Handling
        full_name = request.form.get('customer_name')
        phone = request.form.get('phone_number') 
        address = request.form.get('address')   
        res_date = request.form.get('res_date')
        res_time_raw = request.form.get('res_time') 
        
        # Time conversion safety check
        try:
            res_time_24 = datetime.strptime(res_time_raw, "%I:%M %p").strftime("%H:%M:%S")
        except ValueError:
            res_time_24 = "12:00:00" # Default or handle error
            
        full_datetime = f"{res_date} {res_time_24}"
        
        table_no = request.form.get('table_number')
        
        # --- PAX & PRICING LOGIC 
        try:
            pax = int(request.form.get('num_guests', 2))
        except (ValueError, TypeError):
            pax = 2 # Default fallback
            
        package = request.form.get('tier')
        pay_method = request.form.get('payment_method')

        tier_prices = {
            'normal': 699.00,
            'high': 998.00,
            'hard': 1298.00
        }
        
        # 2. Convert to float and compute correctly
        price_per_pax = float(tier_prices.get(package, 0))
        total_price = price_per_pax * pax
        down_payment = 500.00

        # DEBUG Console
        print(f"DEBUG: Processing {res_code} | Pax: {pax} | Total: {total_price}")

        # 3. DB Insert 
        sql = """INSERT INTO reservations 
                 (code, full_name, phone_number, email, address, reservation_date, pax, package, 
                  table_number, down_payment, total_price, payment_method, status, 
                  verification_id, downpayment_receipt) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        
        values = (
            res_code, full_name, phone, customer_email, address, full_datetime, 
            pax, package, table_no, down_payment, total_price, pay_method, 'reserve', 
            id_path, receipt_path
        )
        
        cursor.execute(sql, values)
        cursor.execute("UPDATE tables SET status = 'occupied' WHERE table_number = %s", (table_no,))
        db.commit()

        # 4. Email logic 
        if customer_email:
            res_info = {
                'name': full_name,
                'code': res_code,
                'date': full_datetime, 
                'pax': pax,
                'table': table_no
            }
            send_reservation_email(customer_email, res_info)
            
        reservation_data = {
            'customer_name': full_name,
            'reservation_date': res_date,
            'reservation_time': res_time_raw, 
            'phone_number': phone
        }

        return render_template(
            "costumer/success.html", 
            code=res_code, 
            reservation=reservation_data, 
            is_event=False
        )

    except Exception as e:
        db.rollback()
        print(f"❌ Error logic: {e}") 
        return f"Database Error: {e}", 500
    finally:
        cursor.close()
        db.close()

@customer_bp.route('/reserve/event-form')
def event_form():   
    package_id = request.args.get('package')
    
    return render_template("costumer/event_form.html", package_id=package_id)

@customer_bp.route('/reserve/event-packages')
def event_packages():
    # SAMPLE DATA
    packages = [
        {
            'id': 'party_prime',
            'name': 'Party Prime',
            'pax': '15-25 Persons',
            'price': 12500,
            'inclusion': ['Standard Meat Selection', 'Unlimited Rice', 'Unlimited Side Dishes', '3 Hours Venue Use']
        },
        {
            'id': 'grand_feast',
            'name': 'Grand Feast',
            'pax': '30-50 Persons',
            'price': 22000,
            'inclusion': ['Premium Meat Selection', 'Seafood Platter', 'Unlimited Drinks', '4 Hours Venue Use', 'Free Sound System']
        }
    ]
    return render_template("costumer/event_selection.html", packages=packages)
@customer_bp.route('/submit_event', methods=['POST'])
def submit_event():
    # 1. Kunin ang Form Data
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    phone = request.form.get('phone_number')
    address = request.form.get('address')
    e_date = request.form.get('event_date')
    package = request.form.get('event_package') 
    pax_raw = request.form.get('pax')
    requests = request.form.get('special_requests')

    # --- PAX VALIDATION ---
    try:
        pax = int(pax_raw) if pax_raw else 0
        if package == 'party_prime' and (pax < 15 or pax > 25):
            return "Error: Party Prime is for 15-25 persons.", 400
        elif package == 'grand_feast' and (pax < 30 or pax > 50):
            return "Error: Grand Feast is for 30-50 persons.", 400
        elif pax < 15:
            return "Error: Minimum 15 pax for events.", 400
    except (ValueError, TypeError):
        return "Error: Invalid pax count.", 400

    event_code = f"EVT-{uuid.uuid4().hex[:6].upper()}"

    package_prices = {
        'party_prime': 12500,
        'grand_feast': 22000
    }
    total_price = package_prices.get(package, 0)
    down_payment = 5000.00

    # 2. Handle File Uploads (ID at Receipt)
    id_img = request.files.get('id_image')
    rec_img = request.files.get('receipt_image')
    
    id_filename = f"id_{event_code}.jpg" if id_img else ""
    rec_filename = f"rec_{event_code}.jpg" if rec_img else ""
    
    if id_img: id_img.save(os.path.join('static/uploads/ids', id_filename))
    if rec_img: rec_img.save(os.path.join('static/uploads/receipts', rec_filename))

    # 3. Save to DB (Status is now 'confirmed')
    db = get_db()
    cursor = db.cursor()
    try:
        # Idinagdag ang valid_id_image sa columns at values
        sql = """INSERT INTO event_reservations 
                 (code, full_name, email, phone_number, address, event_datetime, 
                  pax, event_package, total_price, special_requests, valid_id_image, 
                  downpayment_receipt, status) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmed')"""
        
        cursor.execute(sql, (event_code, full_name, email, phone, address, e_date, 
                            pax, package, total_price, requests, id_filename, rec_filename))
        db.commit()

        # 4. Email Confirmation with Disclaimer
        event_data = {
            'name': full_name,
            'code': event_code,
            'date': e_date,
            'pax': pax,
            'package': package,
            'type': 'EVENT'
        }
        send_event_confirmation_email(email, event_data)

        reservation_data = {
            'customer_name': full_name,
            'event_type': request.form.get('event_type'), 
            'phone_number': phone
        }

        return render_template(
            "costumer/success.html", 
            code=event_code, 
            reservation=reservation_data, 
            is_event=True
        )
    except Exception as e:
        db.rollback()
        print(f"❌ Database Error: {e}")
        return f"Database Error: {str(e)}", 500
    finally:
        cursor.close()
        db.close()

@customer_bp.route('/api/booked-dates')
def get_booked_dates():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    # Block dates if status is confirmed or completed
    cursor.execute("""
        SELECT DATE(event_datetime) as booked_date 
        FROM event_reservations 
        WHERE status IN ('confirmed', 'completed')
    """)
    rows = cursor.fetchall()
    
    booked_dates = [row['booked_date'].strftime('%Y-%m-%d') for row in rows]
    
    cursor.close()
    db.close()
    return jsonify(booked_dates)

@customer_bp.route('/costumer/menu')
def menu():
    menu = fetch_menu_from_db()
    return render_template('costumer/menu.html', menu=menu)