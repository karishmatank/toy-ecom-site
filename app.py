from flask import flash, Flask, g, redirect, render_template, request, session, url_for
import bcrypt
from functools import wraps
from toy_ecom.database_persistence import DatabasePersistence
import secrets

app = Flask(__name__)
app.secret_key=secrets.token_hex(32)

def is_valid_credential(username, password):
    actual = g.storage.get_user_pwd(username)
    if actual:
        return bcrypt.checkpw(password.encode('utf-8'), actual.encode('utf-8'))
    return False

def is_user_signed_in():
    return 'id' in session

def transform_inventory_format():
    """Transform format of inventory data for templates"""
    inventory = g.storage.get_inventory()
    inventory = [dict(item) for item in inventory]

    inventory_reformat = {
        item['id']: {key: value for key, value in item.items() if key != 'id'} 
        for item in inventory
    }

    return inventory_reformat

@app.context_processor
def inventory_utilities_processor():
    """Makes the inventory available in all templates"""
    return dict(
        inventory = transform_inventory_format()
    )

@app.before_request
def initialize_session():
    if not is_user_signed_in() and 'cart' not in session:
        session['cart'] = dict()

@app.before_request
def load_db():
    g.storage = DatabasePersistence(app.config['TESTING'] == True)

def sign_in_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'id' not in session:
            flash("You must be signed in before continuing.", "warning")
            return redirect(url_for('sign_in'))
        return func(*args, **kwargs)
    return wrapper
    

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/item/<int:item_id>")
def view_product(item_id):
    if not g.storage.is_item_in_inventory(item_id):
        flash("Item does not exist.", "warning")
        return redirect(url_for("index"))

    return render_template('product_page.html', item_id=item_id)

@app.route("/item/<int:item_id>/add-to-cart", methods=['POST'])
def add_product_to_cart(item_id):
    if not g.storage.is_item_in_inventory(item_id):
        flash("Item does not exist.", "warning")
        return redirect(url_for("index"))

    # Validate quantity
    quantity = request.form.get('quantity', None)
    if not quantity:
        flash("Please enter a quantity.", "warning")
        return render_template('product_page.html', item_id=item_id)
    
    if '.' in quantity:
        flash("Please enter an integer quantity.", "warning")
        return render_template('product_page.html', item_id=item_id)
    
    quantity = int(quantity)

    if not g.storage.is_quantity_valid(quantity, item_id):
        flash("Quantity is invalid for this item.", "warning")
        return render_template('product_page.html', item_id=item_id)
    
    # Add item to cart
    # With Flask, session data is serialized, meaning the item_id is kept as a string, not int in the session data
    # So we have to cast it to str to check below
    if not is_user_signed_in():
        session['cart'][str(item_id)] = session['cart'].get(str(item_id), 0) + quantity
        session.modified = True
    else:
        g.storage.add_to_cart(session['id'], {item_id: quantity})
    
    flash("Added to cart!", "success")
    return render_template('product_page.html', item_id=item_id)

@app.route('/cart')
def view_cart():
    if not is_user_signed_in():
        cart = session['cart']
    else:
        cart = g.storage.get_user_cart(session['id'])
        cart = {item['item_id']: item['quantity'] for item in cart}

    return render_template('cart.html', cart=cart)

@app.route('/cart/<int:item_id>/delete', methods=['POST'])
def delete_item_from_cart(item_id):
    if not g.storage.is_item_in_inventory(item_id):
        flash("Item does not exist.", "warning")
        return redirect(url_for("index"))
    
    # Check that item is actually in the cart
    # With Flask, session data is serialized, meaning the item_id is kept as a string, not int in the session data
    # So we have to cast it to str to check below
    if ((not is_user_signed_in() and str(item_id) not in session['cart']) or
        (is_user_signed_in() and not g.storage.is_item_in_cart(session['id'], item_id))):
        flash("Item is not in cart.", "warning")
        return redirect(url_for('view_cart'))

    # Remove item from cart
    # With Flask, session data is serialized, meaning the item_id is kept as a string, not int in the session data
    # So we have to cast it to str to check below
    if not is_user_signed_in():
        del session['cart'][str(item_id)]
        session.modified = True
    else:
        g.storage.remove_item_from_cart(session['id'], item_id)

    flash("Item removed from cart", "success")
    return redirect(url_for('view_cart'))

@app.route('/users/sign-up', methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        # Check to make sure all fields were properly passed in (no blank values)
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("Please provide a username and password.", "warning")
            return render_template('sign_up.html', username=username), 422

        # Check to make sure username doesn't overlap with existing
        if g.storage.is_existing_user(username):
            flash("Username already exists.", "warning")
            return render_template('sign_up.html', username=username), 422

        # Hash the password, store in a yaml, direct to log in page
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        hashed_password_str = hashed_password.decode('utf-8')
        g.storage.update_user_info(username, hashed_password_str)

        # Create a new cart for this new user
        id = g.storage.get_user_id(username)
        g.storage.create_cart(id)

        flash("Sign up successful! Please log in.", "success")
        return redirect(url_for('sign_in'))

    return render_template('sign_up.html')

@app.route("/users/sign-in", methods=['GET', 'POST'])
def sign_in():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Check if username and password supplied
        if not is_valid_credential(username, password):
            flash('Invalid credentials', 'warning')
            return render_template('sign_in.html', username=username), 422
        
        session['id'] = g.storage.get_user_id(username)

        # Move any cart items in the session to the database
        if 'cart' in session and session['cart']:
            g.storage.add_to_cart(session['id'], session['cart'])
            del session['cart']

        flash('Welcome back!', "success")
        return redirect(url_for('index'))

    return render_template('sign_in.html')

@app.route("/users/sign-out", methods=['POST'])
def sign_out():
    if 'id' in session:
        del session['id']
    
    flash("You have been signed out.", "success")
    return redirect(url_for('index'))

@app.route("/users/check-out", methods=['POST'])
@sign_in_decorator
def check_out_cart():
    # Make sure there are actually items in the cart, otherwise nothing to check out
    cart = g.storage.get_user_cart(session['id'])

    if not cart:
        flash("No items to check out!", "warning")
        return redirect(url_for("view_cart"))
    
    # Update inventory
    g.storage.update_inventory(session['id'])

    # Add purchase to a history file
    g.storage.update_orders(session['id'])

    # Clear cart
    g.storage.clear_cart(session['id'])

    flash("Thank you for your purchase!", "success")
    return redirect(url_for('user_history'))

@app.route("/users/history")
@sign_in_decorator
def user_history():
    user_purchases = [dict(purchase) for purchase in g.storage.get_user_history(session['id'])]

    # Group items together by order_id for easier implementation in template
    user_purchases_grouped = dict()

    for purchase in user_purchases:
        order_id = purchase['order_id']

        if order_id in user_purchases_grouped:
            # Add current purchase item to group
            items = user_purchases_grouped[order_id]['items']
            items[purchase['item_id']] = purchase['quantity']
        else:
            data = dict()
            data['date'] = purchase['purchase_date']
            data['items'] = {purchase['item_id']: purchase['quantity']}

            user_purchases_grouped[order_id] = data

    return render_template('user_history.html', purchases=user_purchases_grouped)

if __name__ == '__main__':
    app.run(debug=True, port=5003)