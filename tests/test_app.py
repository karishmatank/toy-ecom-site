import unittest
from app import app
import psycopg2
from contextlib import contextmanager
import os

class RoutesTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

        self.sql_path = os.path.join(os.path.dirname(__file__), '..', 'schema.sql')
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                with open(self.sql_path, "r") as f:
                    cursor.execute(f.read())
    
    def tearDown(self):
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DROP TABLE IF EXISTS 
                        users, 
                        inventory, 
                        orders, 
                        order_items, 
                        shopping_carts, 
                        cart_items;
                    """)
        
    @contextmanager
    def _database_connect(self):
        connection = psycopg2.connect(dbname='toy_ecomm_test')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _create_session_with_cart(self, items={}):
        with self.client as c:
            with c.session_transaction() as session:
                session['cart'] = items
            return c
        
    def _create_db_cart(self, items={}):
        if not items:
            return
        user_id = 1
        placeholders = ", ".join(["(%s, %s, %s)" for _ in items])
        values = tuple(i for item_id, quantity in items.items() for i in (user_id, item_id, quantity))
        query = f"""
            INSERT INTO cart_items (cart_id, item_id, quantity) VALUES {placeholders}
        """

        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, values)    

    def _get_cart_count(self, user_id):
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT count(*)
                    FROM cart_items
                    WHERE cart_id = %s;
                """, (user_id,))
                return cursor.fetchone()[0]
        
    def _sign_in(self):
        with self.client as c:
            with c.session_transaction() as session:
                session['id'] = 1
            return c
        
    def _get_current_inventory(self, item_id):        
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT available
                    FROM inventory
                    WHERE id = %s;
                """, (item_id,))
                return cursor.fetchone()[0]
        
    def _get_purchase_history(self):
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT count(id)
                    FROM orders;
                """)
                return cursor.fetchone()[0]

    def test_index(self):
        """Test index route (/)"""
        response = self.client.get("/")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "text/html; charset=utf-8")
        self.assertIn('White T-Shirt', body)
        self.assertIn("Black Jeans", body)

    def test_item_page(self):
        """Test item page"""
        response = self.client.get("/item/2")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('White T-Shirt', body)
        self.assertIn('Classic white t-shirt, goes with every outfit.', body)

    def test_item_page_nonexistent(self):
        """Test item page with nonexistent ID"""
        with self.client.get("/item/99") as response:
            self.assertEqual(response.status_code, 302)
            redirect_location = response.headers['Location']

        with self.client.get(redirect_location) as response:
            self.assertIn("Item does not exist.", response.get_data(as_text=True))

    def test_add_to_cart(self):
        """Test add to cart functionality"""
        self.client = self._create_session_with_cart()

        item_id = 2
        data = {'quantity': "1"}
        response = self.client.post(
            f"/item/{item_id}/add-to-cart", 
            data=data, 
            follow_redirects=True
        )

        body = response.get_data(as_text=True)
        self.assertIn('Added to cart!', body)

        # With Flask, session data is serialized, meaning the item_id is kept as a string, not int in the session data
        # So we have to cast it to str to check below
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'][str(item_id)], 1)

    def test_add_to_cart_invalid_quantity(self):
        """Test add to cart with a quantity too large and too small"""
        # Too large
        self.client = self._create_session_with_cart()

        item_id = 1
        data = {'quantity': "3"}
        response = self.client.post(
            f"/item/{item_id}/add-to-cart", 
            data=data, 
            follow_redirects=True
        )

        body = response.get_data(as_text=True)
        self.assertIn('Quantity is invalid for this item.', body)

        with self.client.session_transaction() as session:
            self.assertNotIn(item_id, session['cart'])

        # Too small
        data = {'quantity': "0"}
        response = self.client.post(
            f"/item/{item_id}/add-to-cart", 
            data=data, 
            follow_redirects=True
        )

        body = response.get_data(as_text=True)
        self.assertIn('Quantity is invalid for this item.', body)

        with self.client.session_transaction() as session:
            self.assertNotIn(item_id, session['cart'])
    
    def test_add_to_cart_invalid_id(self):
        """Test add to cart with invalid product ID"""
        self.client = self._create_session_with_cart()

        item_id = 99
        data = {'quantity': "3"}
        response = self.client.post(
            f"/item/{item_id}/add-to-cart", 
            data=data, 
            follow_redirects=True
        )

        body = response.get_data(as_text=True)
        self.assertIn('Item does not exist.', body)
        self.assertIn('Please browse our products below:', body)

        with self.client.session_transaction() as session:
            self.assertNotIn(item_id, session['cart'])

    def test_add_to_cart_existing_cart_no_login(self):
        """Tests add to cart functionality when there is an existing cart item (not logged in)"""
        self.client = self._create_session_with_cart({
            2: 1
        })

        item_id = 2
        data = {'quantity': "3"}
        response = self.client.post(
            f"/item/{item_id}/add-to-cart", 
            data=data, 
            follow_redirects=True
        )

        body = response.get_data(as_text=True)
        self.assertIn('Added to cart!', body)

        # With Flask, session data is serialized, meaning the item_id is kept as a string, not int in the session data
        # So we have to cast it to str to check below
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'][str(item_id)], 4)
    
    def test_add_to_cart_existing_cart_login(self):
        """Tests add to cart functionality when there is an existing cart item (logged in)"""
        self.client = self._sign_in()
        self._create_db_cart({
            2: 1
        })

        item_id = 2
        data = {'quantity': "3"}
        response = self.client.post(
            f"/item/{item_id}/add-to-cart", 
            data=data, 
            follow_redirects=True
        )

        body = response.get_data(as_text=True)
        self.assertIn('Added to cart!', body)

        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT quantity
                    FROM cart_items
                    WHERE cart_id = 1 AND
                    item_id = %s;
                """, (item_id,))
                self.assertEqual(cursor.fetchone()[0], 4)

    def test_view_cart(self):
        """Test view cart"""
        # No cart
        self.client = self._create_session_with_cart()
        response = self.client.get("/cart")
        body = response.get_data(as_text=True)
        self.assertIn('You have no items in your cart!', body)

        # Items in cart
        self.client = self._create_session_with_cart({
            2: 1
        })
        response = self.client.get("/cart")
        body = response.get_data(as_text=True)
        self.assertIn('White T-Shirt', body)
        self.assertIn('Quantity 1', body)

    def test_view_cart_signed_in(self):
        """Test view cart when user is signed in"""
        # No cart
        self.client = self._sign_in()
        self._create_db_cart()
        response = self.client.get("/cart")
        body = response.get_data(as_text=True)
        self.assertIn('You have no items in your cart!', body)

        # Items in cart
        self._create_db_cart({
            2: 1
        })
        response = self.client.get("/cart")
        body = response.get_data(as_text=True)
        self.assertIn('White T-Shirt', body)
        self.assertIn('Quantity 1', body)

    def test_clear_cart(self):
        """Test clear cart functionality"""
        self.client = self._create_session_with_cart({
            2: 1
        })

        item_id = 2
        response = self.client.post(f"/cart/{item_id}/delete", follow_redirects=True)
        body = response.get_data(as_text=True)

        self.assertIn("Item removed from cart", body)

    def test_clear_cart_signed_in(self):
        """Test clear cart functionality when signed in"""
        self.client = self._sign_in()
        self._create_db_cart({
            2: 1
        })

        item_id = 2
        response = self.client.post(f"/cart/{item_id}/delete", follow_redirects=True)
        body = response.get_data(as_text=True)

        self.assertIn("Item removed from cart", body)

        # Check that the item cleared from the cart
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT count(*)
                    FROM cart_items
                    WHERE cart_id = 1 AND
                    item_id = %s;
                """, (item_id,))
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_session_cart_emptied_on_sign_in(self):
        """Test that the session cart is deleted after a user signs in"""
        cart = {2: 1}
        self.client = self._create_session_with_cart(cart)

        # Sign in
        data = {'username': 'admin', 'password': 'secret'}
        response = self.client.post("/users/sign-in", data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Check if session cart is cleared
        with self.client.session_transaction() as session:
            self.assertFalse('cart' in session)

        # Check if cart in the database now
        cart_count = self._get_cart_count(user_id=1)
        self.assertEqual(cart_count, 1)

    def test_clear_cart_nonexistent_id(self):
        """Test clear cart functionality if item ID doesn't exist"""
        self.client = self._create_session_with_cart({
            2: 1
        })

        item_id = 99
        response = self.client.post(f"/cart/{item_id}/delete", follow_redirects=True)
        body = response.get_data(as_text=True)

        self.assertIn("Item does not exist.", body)

    def test_clear_cart_item_not_in_cart(self):
        """Test clear cart functionality for valid ID but item not in cart"""
        self.client = self._create_session_with_cart({
            2: 1
        })

        item_id = 1
        response = self.client.post(f"/cart/{item_id}/delete", follow_redirects=True)
        body = response.get_data(as_text=True)

        self.assertIn("Item is not in cart.", body)

    def test_sign_up(self):
        """Test sign up capability"""
        data = {'username': 'new_user', 'password': 'new_password'}
        response = self.client.post('/users/sign-up', data=data, follow_redirects=True)
        body = response.get_data(as_text=True)
        self.assertIn("Sign up successful! Please log in.", body)

    def test_sign_up_existing_user(self):
        """Test sign up with existing username"""
        data = {'username': 'admin', 'password': 'new_password'}
        response = self.client.post('/users/sign-up', data=data, follow_redirects=True)
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Username already exists.", body)
    
    def test_sign_up_missing_info(self):
        """Test sign up with missing info (missing username and/or password)"""
        data = {'username': ' ', 'password': 'new_password'}
        response = self.client.post('/users/sign-up', data=data, follow_redirects=True)
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Please provide a username and password.", body)

        data = {'username': 'new_user', 'password': ' '}
        response = self.client.post('/users/sign-up', data=data, follow_redirects=True)
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Please provide a username and password.", body)
    
    def test_sign_in(self):
        """Test sign in capability"""
        data = {'username': 'admin', 'password': 'secret'}
        response = self.client.post("/users/sign-in", data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Welcome', response.get_data(as_text=True))

    def test_sign_in_incorrect_credentials(self):
        """Test sign in with incorrect credentials"""
        data = {'username': 'admin', 'password': 'password'}
        response = self.client.post("/users/sign-in", data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 422)
        self.assertIn('Invalid credentials', response.get_data(as_text=True))

    def test_sign_out(self):
        self.client = self._sign_in()

        with self.client.session_transaction() as session:
            self.assertEqual(session['id'], 1)

        response = self.client.post("/users/sign-out", follow_redirects=True)

        self.assertIn("You have been signed out.", response.get_data(as_text=True))

        with self.client.session_transaction() as session:
            self.assertNotIn('id', session)

    def test_check_out(self):
        self.client = self._sign_in()
        self._create_db_cart({
            2: 1
        })

        # Check inventory file before we do anything
        item_id = 2
        current_inventory = self._get_current_inventory(item_id)
        self.assertEqual(current_inventory, 10)

        response = self.client.post("/users/check-out", follow_redirects=True)
        self.assertIn('Thank you for your purchase!', response.get_data(as_text=True))

        # Check inventory file afterwards
        new_inventory = self._get_current_inventory(item_id)
        self.assertEqual(new_inventory, 9)

        # Check cart is empty
        cart_count = self._get_cart_count(user_id=1)
        self.assertEqual(cart_count, 0)

        # Check that there are 3 purchases in the purchase history file (there were 2 to start)
        purchase_count = self._get_purchase_history()
        self.assertEqual(purchase_count, 3)

    def test_check_out_empty_cart(self):
        """Test that checkout doesn't go through with an empty cart"""
        self.client = self._sign_in()
        self._create_db_cart()

        response = self.client.post("/users/check-out", follow_redirects=True)
        self.assertIn('No items to check out!', response.get_data(as_text=True))

    def test_purchase_history(self):
        """Test that purchase history page populates correctly"""
        self.client = self._sign_in()

        response = self.client.get("/users/history")
        body = response.get_data(as_text=True)
        self.assertIn('White T-Shirt', body)
        self.assertIn('Quantity 1', body)
        self.assertIn('Confirmation number: 1', body)

        # Confirm the other fake user's purchase is not shown
        self.assertNotIn('Black Jeans', body)
        self.assertNotIn('Confirmation number: 2', body)


if __name__ == "__main__":
    unittest.main()