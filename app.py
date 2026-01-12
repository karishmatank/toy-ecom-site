from flask import flash, Flask, redirect, render_template, request, session, url_for
import os
from uuid import uuid4
import yaml

app = Flask(__name__)
app.secret_key='secret1'

def get_inventory_path():
    filename = 'inventory.yml'
    root = os.path.abspath(os.path.dirname(__file__))
    if app.config['TESTING']:
        inventory_path = os.path.join(root, 'tests', filename)
    else:
        inventory_path = os.path.join(root, 'toy-ecom', filename)
    
    return inventory_path

def load_inventory():
    inventory_path = get_inventory_path()

    with open(inventory_path, 'r') as file:
        return yaml.safe_load(file)
    
def is_item_in_inventory(item_id):
    inventory = load_inventory()
    return item_id in inventory

def is_quantity_valid(quantity, item_id):
    inventory = load_inventory()
    available = inventory[item_id]['available']
    return quantity > 0 and quantity <= available

@app.context_processor
def inventory_utilities_processor():
    """Makes the inventory available in all templates"""
    return dict(
        inventory = load_inventory()
    )

@app.before_request
def initialize_session():
    if 'cart' not in session:
        session['cart'] = dict()
    

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
    return render_template('product_page.html', item_id=item_id)

@app.route('/cart')
def view_cart():
    return render_template('cart.html')

if __name__ == '__main__':
    app.run(debug=True, port=5003)