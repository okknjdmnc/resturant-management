from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import get_db_connection
from functools import wraps
from routes.manager import log_inventory_action
from decimal import Decimal

inventory_bp = Blueprint('inventory', __name__)

def inventory_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow staff, manager, and super_admin to access inventory
        if session.get('role') not in ['staff', 'manager', 'super_admin']:
            flash("Access Denied: Inventory Staff privileges required.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@inventory_bp.route('/inventory/dashboard')
@inventory_required
def dashboard():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    # 1. Kunin ang Low Stock Alerts
    cursor.execute("SELECT COUNT(*) as count FROM inventory WHERE quantity <= min_stock_level")
    low_stock_count = cursor.fetchone()['count']
    
    # 2. Kunin ang Last 5 Activities na ginawa ng staff
    cursor.execute("SELECT * FROM inventory_logs WHERE performed_by = 'Inventory Staff' ORDER BY timestamp DESC LIMIT 5")
    recent_logs = cursor.fetchall()
    
    return render_template("inventory/dashboard.html", 
                           low_stock=low_stock_count, 
                           recent_logs=recent_logs)

@inventory_bp.route('/inventory/register-stock', methods=['GET', 'POST']) # Siguraduhin na tama ang URL path mo
@inventory_required
def add_item():
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        # 1. Kunin ang raw inputs
        raw_name = request.form.get('item_name')
        qty_input = request.form.get('quantity')
        log_id = request.form.get('log_id')
        unit = request.form.get('unit', 'kg')

        # SAFETY CHECK: Wag ituloy kung walang item name (iwas NoneType.upper error)
        if not raw_name:
            flash("Error: Item name is required.", "danger")
            return redirect(url_for('inventory.add_item'))

        try:
            item_name = raw_name.upper().strip()
            qty_received = Decimal(qty_input) if qty_input else Decimal('0.00')

            # 2. Kunin ang current stock levels
            cursor.execute("SELECT quantity FROM inventory WHERE item_name = %s", (item_name,))
            row = cursor.fetchone()
            
            # Siguraduhin na Decimal ang prev_qty
            prev_qty = Decimal(str(row['quantity'])) if row else Decimal('0.00')
            new_qty = prev_qty + qty_received

            # 3. Update o Insert sa Inventory Table
            if row:
                cursor.execute("UPDATE inventory SET quantity = %s WHERE item_name = %s", (new_qty, item_name))
            else:
                cursor.execute("INSERT INTO inventory (item_name, quantity, unit) VALUES (%s, %s, %s)", 
                               (item_name, qty_received, unit))

            # 4. TAWAGIN ANG LOGGING FUNCTION (Gamit ang Decimal values)
            log_inventory_action(
                item_name=item_name,
                action="STOCK IN",
                qty_changed=qty_received,
                prev_qty=prev_qty,
                new_qty=new_qty,
                remarks=f"Received from PO #{log_id}" if log_id else "Manual Stock In"
            )

            # 5. I-UPDATE ang Purchasing Log status sa 'Received'
            if log_id:
                cursor.execute("UPDATE purchasing_logs SET status = 'Received' WHERE id = %s", (log_id,))

            db.commit()
            flash(f"Confirmed: {qty_received} {unit} of {item_name} added to stock.", "success")
            
        except Exception as e:
            db.rollback()
            flash(f"System Error: {str(e)}", "danger")
        
        return redirect(url_for('inventory.add_item'))

    # --- GET REQUEST (Displaying the page) ---
    # Dito natin kukunin ang listahan ng 'Ordered' para sa cards mo
    cursor.execute("SELECT * FROM purchasing_logs WHERE status = 'Ordered' ORDER BY order_date DESC")
    pending_purchases = cursor.fetchall()
    
    return render_template("inventory/purchase_orders.html", pending_purchases=pending_purchases)

@inventory_bp.route('/kitchen-orders')
@inventory_required
@inventory_required
def kitchen_orders():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Kunin ang mga KOT na hindi pa 'Served'
    cursor.execute("""
        SELECT id, or_number, table_number, items_ordered, status, created_at 
        FROM kot_tickets 
        WHERE status IN ('Pending', 'Preparing')
        ORDER BY created_at ASC
    """)
    active_kots = cursor.fetchall()
    
    # Kunin din ang current stock levels para sa quick reference ng dispatcher
    cursor.execute("SELECT item_name, transferred_quantity, unit FROM kitchen_stocks")
    stocks = cursor.fetchall()
    
    conn.close()
    return render_template('inventory/kitchen_orders.html', kots=active_kots, stocks=stocks)

@inventory_bp.route('/dispatch-stock/<int:kot_id>', methods=['POST'])
@inventory_required
def dispatch_stock(kot_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. Kunin ang items ordered sa KOT
        cursor.execute("SELECT items_ordered, table_number FROM kot_tickets WHERE id = %s", (kot_id,))
        kot = cursor.fetchone()
        
        if not kot:
            flash("KOT Ticket not found!", "danger")
            return redirect(url_for('inventory.kitchen_orders'))

        items_list = [i.strip() for i in kot['items_ordered'].split(',')]
        
        for item_name in items_list:
            deduction = Decimal('0.20')  # Gamit ang Decimal para accurate
            
            # --- ITO ANG DAGDAG NA LOGIC PARA SA DUPLICATES ---
            
            # A. Bawasan ang MAIN Inventory (Warehouse)
            cursor.execute("UPDATE inventory SET quantity = quantity - %s WHERE item_name LIKE %s", (deduction, f"%{item_name}%"))

            # B. I-check kung may record na ang item na ito sa kitchen_stocks para sa araw na ito
            cursor.execute("SELECT id FROM kitchen_stocks WHERE item_name LIKE %s", (f"%{item_name}%",))
            existing_kitchen_item = cursor.fetchone()

            if existing_kitchen_item:
                # KUNG MERON NA: I-update lang ang quantity (Dagdag)
                cursor.execute("""
                    UPDATE kitchen_stocks 
                    SET transferred_quantity = transferred_quantity + %s,
                        created_at = NOW()
                    WHERE id = %s
                """, (deduction, existing_kitchen_item['id']))
            else:
                # KUNG WALA PA: Saka lang mag-INSERT ng bagong row
                # Kunin muna ang tamang unit mula sa main inventory
                cursor.execute("SELECT unit FROM inventory WHERE item_name LIKE %s", (f"%{item_name}%",))
                unit_row = cursor.fetchone()
                unit = unit_row['unit'] if unit_row else 'kg'

                cursor.execute("""
                    INSERT INTO kitchen_stocks (item_name, transferred_quantity, unit, created_at)
                    VALUES (%s, %s, %s, NOW())
                """, (item_name, deduction, unit))
            
            # ------------------------------------------------

            # Mag-record sa Logs
            log_msg = f"Dispatched {item_name} for Table {kot['table_number']}"
            cursor.execute("""
                INSERT INTO inventory_logs (item_name, action, qty_changed, performed_by, remarks) 
                VALUES (%s, %s, %s, %s, %s)
            """, (item_name, 'DISPATCH', deduction, 'Inventory Staff', f"Table {kot['table_number']}"))

        # Update KOT status
        cursor.execute("UPDATE kot_tickets SET status = 'Preparing' WHERE id = %s", (kot_id,))

        conn.commit()
        flash(f"Dispatch Successful for Table {kot['table_number']}!", "success")

    except Exception as e:
        conn.rollback()
        flash(f"Dispatch Failed: {str(e)}", "danger")
    finally:
        conn.close()
        
    return redirect(url_for('inventory.kitchen_orders'))

@inventory_bp.route('/eod-returns', methods=['GET', 'POST'])
@inventory_required
def eod_returns():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        try:
            # 1. Kunin lahat ng items na may stock pa sa kitchen
            cursor.execute("SELECT item_name, transferred_quantity, unit FROM kitchen_stocks WHERE transferred_quantity > 0")
            kitchen_items = cursor.fetchall()
            
            for item in kitchen_items:
                qty = item['transferred_quantity']
                name = item['item_name']
                
                # 2. Ibalik sa Main Inventory (Dagdagan ang stock sa warehouse)
                cursor.execute("""
                    UPDATE inventory 
                    SET quantity = quantity + %s 
                    WHERE item_name = %s
                """, (qty, name))
                
                # 3. I-zero out ang Kitchen Stocks
                cursor.execute("UPDATE kitchen_stocks SET transferred_quantity = 0 WHERE item_name = %s", (name,))
                
                # 4. Mag-log para sa Audit
                log_msg = f"EOD RETURN: {qty} {item['unit']} of {name} returned to Warehouse"
                cursor.execute("INSERT INTO system_logs (action, user_role) VALUES (%s, %s)", (log_msg, 'Inventory Staff'))
            
            conn.commit()
            flash("EOD Returns processed! All kitchen stocks returned to Warehouse.", "success")
        except Exception as e:
            conn.rollback()
            flash(f"Error during EOD return: {str(e)}", "danger")
        finally:
            conn.close()
        return redirect(url_for('inventory.dashboard'))

    # GET Request: Ipakita ang listahan ng ibabalik na stocks
    cursor.execute("SELECT * FROM kitchen_stocks WHERE transferred_quantity > 0")
    to_return = cursor.fetchall()
    conn.close()
    return render_template('inventory/eod_returns.html', items=to_return)

@inventory_bp.route('/report-waste', methods=['GET', 'POST'])
@inventory_required
def report_waste():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        item_name = request.form.get('item_name')
        quantity = float(request.form.get('quantity'))
        reason = request.form.get('reason')
        source = request.form.get('source') # 'Kitchen' o 'Warehouse'
        
        try:
            # 1. Bawasan ang stock sa tamang table
            if source == 'Kitchen':
                cursor.execute("UPDATE kitchen_stocks SET transferred_quantity = transferred_quantity - %s WHERE item_name = %s", (quantity, item_name))
            else:
                cursor.execute("UPDATE inventory SET quantity = quantity - %s WHERE item_name = %s", (quantity, item_name))
            
            # 2. I-record sa Waste Logs
            cursor.execute("""
                INSERT INTO waste_logs (item_name, quantity, unit, reason, reported_by) 
                VALUES (%s, %s, %s, %s, %s)
            """, (item_name, quantity, 'kg', reason, session.get('role', 'Inventory Staff')))
            
            # 3. Mag-log sa System Logs
            log_msg = f"WASTE REPORTED: {quantity}kg of {item_name} due to {reason}"
            cursor.execute("INSERT INTO system_logs (action, user_role) VALUES (%s, %s)", (log_msg, 'Inventory Staff'))
            
            conn.commit()
            flash(f"Waste reported successfully: {item_name}", "warning")
        except Exception as e:
            conn.rollback()
            flash(f"Error reporting waste: {str(e)}", "danger")
        finally:
            conn.close()
        return redirect(url_for('inventory.dashboard'))

    # Kunin ang listahan ng items para sa dropdown
    cursor.execute("SELECT item_name FROM inventory")
    all_items = cursor.fetchall()
    conn.close()
    return render_template('inventory/report_waste.html', items=all_items)