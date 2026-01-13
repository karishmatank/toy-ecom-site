from flask import flash, Flask, redirect, render_template, request, session, url_for
import os
from uuid import uuid4
import yaml
import bcrypt
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key='secret1'

def get_file_path(filename):
    root = os.path.abspath(os.path.dirname(__file__))
    if app.config['TESTING']:
        inventory_path = os.path.join(root, 'tests', filename)
    else:
        inventory_path = os.path.join(root, 'toy-ecom', filename)
    
    return inventory_path

def load_file(filename):
    filepath = get_file_path(filename)

    with open(filepath, 'r') as file:
        return yaml.safe_load(file)
    
def update_users_file(username, password):
    contents = load_file('users.yml')
    if not contents:
        contents = {}

    contents[username] = password

    with open(get_file_path('users.yml'), 'w') as file:
        yaml.safe_dump(contents, file)

def update_inventory_file(items):
    contents = load_file('inventory.yml')
    for item, quantity in items.items():
        contents[item]['available'] -= quantity

    with open(get_file_path('inventory.yml'), 'w') as file:
        yaml.safe_dump(contents, file)

def update_purchase_history():
    purchase_id = str(uuid4())
    contents = load_file('purchases.yml')
    if not contents:
        contents = {}

    contents[purchase_id] = {
        'user': session['username'],
        'items': session['cart'],
        'date': datetime.today().strftime("%Y-%m-%d")
    }

    with open(get_file_path('purchases.yml'), 'w') as file:
        yaml.safe_dump(contents, file)
    
def is_item_in_inventory(item_id):
    inventory = load_file('inventory.yml')
    return item_id in inventory

def is_quantity_valid(quantity, item_id):
    inventory = load_file('inventory.yml')
    available = inventory[item_id]['available']
    return quantity > 0 and quantity <= available

def is_user_existing(username):
    users = load_file('users.yml')
    if not users:
        return False
    return username in users

def is_valid_credential(username, password):
    users = load_file('users.yml')
    if is_user_existing(username):
        return bcrypt.checkpw(password.encode('utf-8'), users[username].encode('utf-8'))
    return False

@app.context_processor
def inventory_utilities_processor():
    """Makes the inventory available in all templates"""
    return dict(
        inventory = load_file('inventory.yml')
    )

@app.before_request
def initialize_session():
    if 'cart' not in session:
        session['cart'] = dict()

def sign_in_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            flash("You must be signed in before continuing.", "warning")
            return redirect(url_for('sign_in'))
        return func(*args, **kwargs)
    return wrapper
    

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/item/<item_id>")
def view_product(item_id):
    if not is_item_in_inventory(item_id):
        flash("Item does not exist.", "warning")
        return redirect(url_for("index"))

    return render_template('product_page.html', item_id=item_id)

@app.route("/item/<item_id>/add-to-cart", methods=['POST'])
def add_product_to_cart(item_id):
    if not is_item_in_inventory(item_id):
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

    if not is_quantity_valid(quantity, item_id):
        flash("Quantity is invalid for this item.", "warning")
        return render_template('product_page.html', item_id=item_id)
    
    # Add item to cart
    session['cart'][item_id] = session['cart'].get(item_id, 0) + quantity
    
    flash("Added to cart!", "success")
    session.modified = True
    return render_template('product_page.html', item_id=item_id)

@app.route('/cart')
def view_cart():
    return render_template('cart.html')

@app.route('/cart/<item_id>/delete', methods=['POST'])
def delete_item_from_cart(item_id):
    if not is_item_in_inventory(item_id):
        flash("Item does not exist.", "warning")
        return redirect(url_for("index"))
    
    # Check that item is actually in the cart
    if not item_id in session['cart']:
        flash("Item is not in cart.", "warning")
        return redirect(url_for('view_cart'))

    # Remove item from cart
    del session['cart'][item_id]

    flash("Item removed from cart", "success")
    session.modified = True
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
        if is_user_existing(username):
            flash("Username already exists.", "warning")
            return render_template('sign_up.html', username=username), 422

        # Hash the password, store in a yaml, direct to log in page
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        hashed_password_str = hashed_password.decode('utf-8')
        update_users_file(username, hashed_password_str)

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
        
        session['username'] = username
        flash('Welcome back!', "success")
        return redirect(url_for('index'))

    return render_template('sign_in.html')

@app.route("/users/sign-out", methods=['POST'])
def sign_out():
    if 'username' in session:
        del session['username']
    
    flash("You have been signed out.", "success")
    return redirect(url_for('index'))

@app.route("/users/check-out", methods=['POST'])
@sign_in_decorator
def check_out_cart():
    # Make sure there are actually items in the cart, otherwise nothing to check out
    if not session['cart']:
        flash("No items to check out!", "warning")
        return redirect(url_for("view_cart"))
    
    # Update inventory file
    update_inventory_file(session['cart'])

    # Add purchase to a history file
    update_purchase_history()

    # Clear cart
    session['cart'] = dict()

    flash("Thank you for your purchase!", "success")
    session.modified = True
    return redirect(url_for('user_history'))

@app.route("/users/history")
@sign_in_decorator
def user_history():
    all_purchases = load_file('purchases.yml')
    if not all_purchases:
        all_purchases = {}
    user_purchases = {key: value for key, value in all_purchases.items()
                                 if value['user'] == session['username']}

    return render_template('user_history.html', purchases=user_purchases)

if __name__ == '__main__':
    app.run(debug=True, port=5003)