from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from app import get_db_connection
from data.menu_data import menu_data
from data.staff_data import STAFF_LIST, STATIONS
from datetime import datetime, timedelta
import calendar
from data.staff_data import STAFF_LIST, STATIONS
import random
from decimal import Decimal
import csv
import io
from flask import Response

manager_bp = Blueprint('manager', __name__)

def manager_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') not in ['manager', 'super_admin']:
            flash("Access Denied: Manager privileges required.")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@manager_bp.route('/manager/dashboard')
@manager_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. RESERVATION COUNTS
        cursor.execute("SELECT COUNT(*) as count FROM reservations WHERE status IN ('reserve', 'confirmed')")
        table_count = cursor.fetchone()['count'] or 0

        cursor.execute("SELECT COUNT(*) as count FROM event_reservations WHERE status IN ('confirmed', 'completed')")
        event_count = cursor.fetchone()['count'] or 0

        # 2. FINANCIAL STATS (REVENUE)
        cursor.execute("SELECT SUM(total_price) as rev FROM reservations WHERE status = 'completed'")
        table_revenue = cursor.fetchone()['rev'] or 0

        cursor.execute("SELECT SUM(total_price) as rev FROM event_reservations WHERE status = 'completed'")
        event_revenue = cursor.fetchone()['rev'] or 0

        grand_total = float(table_revenue) + float(event_revenue)

        # 3. OPERATIONAL STATS (Inventory & Requests)
        cursor.execute("SELECT COUNT(*) as count FROM purchase_requests WHERE status = 'PENDING'")
        pending_purchase_count = cursor.fetchone()['count'] or 0

        # FIXED: Ginamit ang 'quantity' at 'min_stock_level' base sa DESCRIBE inventory mo
        cursor.execute("SELECT * FROM inventory")
        inventory_items = cursor.fetchall()
        low_stock_count = sum(1 for i in inventory_items if float(i['quantity'] or 0) <= float(i['min_stock_level'] or 0))

        # FIXED: Nilagyan ng check kung may record sa spoilage
        cursor.execute("SELECT SUM(cost_loss) as loss FROM spoilage_reports")
        spoilage_data = cursor.fetchone()
        total_spoilage_loss = spoilage_data['loss'] or 0 if spoilage_data else 0

        # 4. SALES PROJECTION LOGIC
        now = datetime.now()
        day_of_month = now.day
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        
        daily_avg = grand_total / day_of_month if day_of_month > 0 else 0
        projected_total = daily_avg * days_in_month
        
        monthly_target = 500000 
        progress_percent = (grand_total / monthly_target) * 100 if monthly_target > 0 else 0

        # 5. TIER SALES (Para sa breakdown card)
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN package = 'normal' THEN total_price ELSE 0 END) as normal,
                SUM(CASE WHEN package = 'high' THEN total_price ELSE 0 END) as high,
                SUM(CASE WHEN package = 'hard' THEN total_price ELSE 0 END) as hard
            FROM reservations WHERE status = 'completed'
        """)
        tier_data = cursor.fetchone()
        tier_sales = {
            "normal": tier_data['normal'] or 0 if tier_data else 0,
            "high": tier_data['high'] or 0 if tier_data else 0,
            "hard": tier_data['hard'] or 0 if tier_data else 0
        }

    except Exception as e:
        print(f"Dashboard Error: {e}")
        flash("May mali sa pag-load ng dashboard data.")
        # Mag-provide ng default values para hindi mag-crash ang template
        return redirect(url_for('manager.dashboard')) 
        
    finally:
        cursor.close()
        conn.close()

    return render_template('manager/dashboard.html', 
                           grand_total=grand_total,
                           projected_total=projected_total,
                           monthly_target=monthly_target,
                           progress_percent=min(progress_percent, 100),
                           total_spoilage_loss=total_spoilage_loss,
                           table_count=table_count,
                           event_count=event_count,
                           pending_purchase_count=pending_purchase_count,
                           low_stock_count=low_stock_count,
                           tier_sales=tier_sales)

@manager_bp.route('/manager/staff-management')
@manager_required
def staff_management():
    return render_template("manager/staff_management.html", 
                           staff=STAFF_LIST, 
                           stations=STATIONS)

@manager_bp.route('/manager/staff/update', methods=['POST'])
@manager_required
def update_staff():
    data = request.get_json()
    staff_id = int(data.get('id'))
    new_status = data.get('status')
    new_station = data.get('station')

   
    for member in STAFF_LIST:
        if member['id'] == staff_id:
            member['status'] = new_status
            member['station'] = new_station
            return jsonify({"success": True})

    return jsonify({"success": False, "message": "Staff not found"}), 404

@manager_bp.route('/manager/reservations')
@manager_required
def manage_reservations():
    # Kunin ang filter (default ay 'seating')
    current_filter = request.args.get('type', 'seating')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        if current_filter == 'seating':
            cursor.execute("SELECT id, code, full_name, email, phone_number, pax, table_number, package, reservation_date,  payment_method, down_payment, total_price, status, created_at FROM reservations")
        else:
            # Para sa events
            cursor.execute("SELECT id, code, full_name, email, phone_number, pax, event_package, event_datetime, downpayment, total_price, status, created_at FROM event_reservations")
            
        reservations = cursor.fetchall()
        
    except Exception as e:
        print(f"Error fetching reservations: {e}")
        reservations = []
    finally:
        cursor.close()
        conn.close()

    return render_template('manager/reservations.html', 
                           reservations=reservations, 
                           current_filter=current_filter)

@manager_bp.route('/manager/inventory')
@manager_required
def inventory_overview():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
        
        query = """
            SELECT *, 
            CASE 
                WHEN quantity <= 0 THEN 'Out of Stock'
                WHEN quantity <= min_stock_level THEN 'Low Stock'
                ELSE 'In Stock'
            END AS calculated_status
            FROM inventory 
            ORDER BY category ASC, item_name ASC
        """
        cursor.execute(query)
        inventory_items = cursor.fetchall()
        
        return render_template("manager/inventory_overview.html", inventory=inventory_items)
    except Exception as e:
        print(f"Inventory Error: {e}")
        return f"Error: {e}", 500
    finally:
        cursor.close()
        db.close()

@manager_bp.route('/manager/inventory/transfer/<int:item_id>', methods=['POST'])
@manager_required
def transfer_to_kitchen(item_id):
    data = request.get_json()
    transfer_amount = float(data.get('quantity', 0)) # Basahin ang input ni manager
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM inventory WHERE id = %s", (item_id,))
        item = cursor.fetchone()

        if not item or item['quantity'] < transfer_amount:
            return jsonify({"success": False, "message": "Insufficient stock!"}), 400

        # I-update ang main inventory (bawas)
        cursor.execute("UPDATE inventory SET quantity = quantity - %s WHERE id = %s", 
                       (transfer_amount, item_id))

        # I-update ang kitchen stock
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            INSERT INTO kitchen_stocks (inventory_id, item_name, transferred_quantity, unit, transfer_date)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE transferred_quantity = transferred_quantity + VALUES(transferred_quantity)
        """, (item_id, item['item_name'], transfer_amount, item['unit'], today))

        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@manager_bp.route('/manager/kitchen-view')
@manager_required
def kitchen_view():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        # Kunin ang lahat ng transfers for today
        cursor.execute("""
            SELECT item_name, SUM(transferred_quantity) as total_qty, unit, MAX(transfer_date) as last_transfer
            FROM kitchen_stocks 
            WHERE transfer_date = %s
            GROUP BY item_name, unit
            ORDER BY total_qty DESC
        """, (today,))
        kitchen_items = cursor.fetchall()
        
        return render_template("manager/kitchen_view.html", 
                               kitchen_stocks=kitchen_items, 
                               today=today)
    finally:
        cursor.close()
        db.close()

@manager_bp.route('/manager/purchasing')
@manager_required
def purchasing_stocks():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
       
        query = """
            SELECT *, (min_stock_level * 2) - quantity as suggested_order
            FROM inventory 
            WHERE quantity <= min_stock_level
            ORDER BY category ASC
        """
        cursor.execute(query)
        to_purchase = cursor.fetchall()
        
        return render_template("manager/purchasing_stocks.html", 
                               items=to_purchase,
                               today=datetime.now().strftime('%B %d, %Y'))
    finally:
        cursor.close()
        db.close()

@manager_bp.route('/manager/save-purchase-log', methods=['POST'])
@manager_required
def save_purchase_log():
    data = request.get_json()
    items_text = data.get('items')
    ref = f"PO-{datetime.now().strftime('%Y%m%d%H%M')}"
    
    db = get_db_connection()
    cursor = db.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO purchasing_logs (order_reference, items_summary, status)
            VALUES (%s, %s, 'Ordered')
        """, (ref, items_text))
        db.commit()
        return jsonify({"success": True, "ref": ref})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        db.close()

# Route para makita ang logs page
@manager_bp.route('/manager/purchasing-logs')
@manager_required
def view_purchasing_logs():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM purchasing_logs ORDER BY order_date DESC")
    logs = cursor.fetchall()
    return render_template("manager/purchasing_logs.html", logs=logs)

# Function para sa pag-log call ito sa loob ng ibang routes
def log_inventory_action(item_name, action, qty_changed, prev_qty, new_qty, remarks=""):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO inventory_logs (item_name, action_type, quantity_changed, previous_quantity, new_quantity, performed_by, remarks)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (item_name, action, qty_changed, prev_qty, new_qty, "Active Manager", remarks))
    db.commit()

@manager_bp.route('/inventory-logs')
def view_inventory_logs():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM inventory_logs ORDER BY timestamp DESC")
    logs = cursor.fetchall()
    return render_template("manager/inventory_logs.html", logs=logs)


# --- AI FORECASTING ROUTES ---

@manager_bp.route('/manager/forecast')
@manager_required
def forecast_dashboard():
    # Ang template na 'manager/forecast_dashboard.html' ang magpapakita ng chart
    return render_template("manager/forecast_dashboard.html")

@manager_bp.route('/api/forecast/data')
@manager_required
def get_forecast_data():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
        # 1. Kunin ang Actual Sales per day mula sa Transactions table
        # Tandaan: 'total_amount' ang column mo sa transactions table
        cursor.execute("""
            SELECT DATE(created_at) as date, SUM(total_amount) as total 
            FROM transactions 
            GROUP BY DATE(created_at) 
            ORDER BY date ASC
        """)
        results = cursor.fetchall()
        
        if not results:
            return jsonify({
                "actual_dates": [], "actual_amounts": [],
                "forecast_dates": [], "forecast_amounts": [],
                "avg_daily": 0, "total_actual": 0, "forecast_total": 0
            })

        actual_dates = [r['date'].strftime("%Y-%m-%d") for r in results]
        actual_amounts = [float(r['total']) for r in results]

        # 2. Weighted Moving Average Calculation
        # Mas mataas ang weight (i+1) habang mas lumalapit sa present date
        n = len(actual_amounts)
        if n >= 2:
            weights = list(range(1, n + 1))
            weighted_sum = sum(w * a for w, a in zip(weights, actual_amounts))
            avg_daily = weighted_sum / sum(weights)
        else:
            avg_daily = actual_amounts[0] if actual_amounts else 0

        # 3. Predict Next 7 Days Forecast
        forecast_dates = []
        forecast_amounts = []
        last_date = results[-1]['date']
        
        for i in range(1, 8):
            next_date = last_date + timedelta(days=i)
            
            # Pattern: Weekends (Fri=4, Sat=5, Sun=6) usually have 20% more traffic
            multiplier = 1.2 if next_date.weekday() >= 4 else 1.0
            
            # Artificial Intelligence variation (noise) between 0.90 to 1.10
            variation = random.uniform(0.90, 1.10)
            
            prediction = round(avg_daily * multiplier * variation, 2)
            forecast_amounts.append(prediction)
            forecast_dates.append(next_date.strftime("%Y-%m-%d"))

        return jsonify({
            "actual_dates": actual_dates,
            "actual_amounts": actual_amounts,
            "forecast_dates": forecast_dates,
            "forecast_amounts": forecast_amounts,
            "avg_daily": round(avg_daily, 2),
            "total_actual": round(sum(actual_amounts), 2),
            "forecast_total": round(sum(forecast_amounts), 2)
        })

    except Exception as e:
        print(f"Forecast API Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@manager_bp.route('/api/forecast/cashiers')
@manager_required
def get_cashier_performance():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Kinukuha ang total sales per cashier (processed_by)
    cursor.execute("""
        SELECT processed_by as name, SUM(total_amount) as total, COUNT(*) as count 
        FROM transactions 
        GROUP BY processed_by 
        ORDER BY total DESC
    """)
    stats = cursor.fetchall()
    db.close()
    
    return jsonify(stats)

@manager_bp.route('/manager/forecast/export')
@manager_required
def export_forecast_csv():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # Kunin ang data (same logic as API)
    cursor.execute("SELECT DATE(created_at) as date, SUM(total_amount) as total FROM transactions GROUP BY DATE(created_at) ORDER BY date ASC")
    results = cursor.fetchall()
    
    # Simple average for export logic
    amounts = [float(r['total']) for r in results]
    avg_daily = sum(amounts) / len(amounts) if amounts else 0
    last_date = results[-1]['date'] if results else datetime.now()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Type', 'Date', 'Projected Revenue (PHP)', 'Notes'])

    # Add next 7 days prediction
    for i in range(1, 8):
        next_date = last_date + timedelta(days=i)
        multiplier = 1.2 if next_date.weekday() >= 4 else 1.0
        prediction = round(avg_daily * multiplier, 2)
        writer.writerow(['FORECAST', next_date.strftime("%Y-%m-%d"), f"{prediction:.2f}", "AI Predicted Value"])

    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=GojoHouse_Forecast_{datetime.now().strftime('%Y%m%d')}.csv"}
    )