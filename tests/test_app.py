import unittest
from app import app
import os
import yaml

class RoutesTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

        # Create an inventory yaml file
        self.inventory_path = os.path.join(os.path.dirname(__file__), 'inventory.yml')
        with open(self.inventory_path, 'w') as file:
            yaml.safe_dump({
                "4931f25f-ff1c-4d49-b1d1-15c78bcc92d3": {
                    "product_name": "White T-Shirt",
                    "description": "Classic white t-shirt, goes with every outfit.",
                    "available": 10
                },
                "1eb43f24-b5c9-4d60-ae93-1d13912669c2": {
                    "product_name": "Black Jeans",
                    "description": "Durable jeans!",
                    "available": 2
                },
            }, file)
        
        # Create a users yaml file
        self.users_path = os.path.join(os.path.dirname(__file__), 'users.yml')
        with open(self.users_path, 'w') as file:
            yaml.safe_dump({
                'admin': '$2b$12$ugokt6qiEsW28czTnPB6j.3x9/cZrZLsyTUW5qyxykp0JoW3uzIDu'
            }, file)

        # Create a purchases yaml file
        self.purchases_path = os.path.join(os.path.dirname(__file__), 'purchases.yml')
        with open(self.purchases_path, 'w') as file:
            yaml.safe_dump({
                'e3cfe3dd-62ef-4bdd-b307-4d982ba0e2b5': {
                    'user': 'admin',
                    'items': {
                        '4931f25f-ff1c-4d49-b1d1-15c78bcc92d3': 1
                    },
                    'date': '2026-01-12'
                },
                '5d39b0c0-4cee-464d-81fb-fc9787ceefcb': {
                    'user': 'other-user',
                    'items': {
                        '1eb43f24-b5c9-4d60-ae93-1d13912669c2': 1
                    },
                    'date': '2026-01-11'
                }
            }, file)
    
    def tearDown(self):
        os.remove(self.inventory_path)
        os.remove(self.users_path)
        os.remove(self.inventory_path)

    def _create_session_with_cart(self, items={}):
        with self.client as c:
            with c.session_transaction() as session:
                session['cart'] = items
            return c
        
    def _sign_in(self):
        with self.client as c:
            with c.session_transaction() as session:
                session['username'] = 'admin'
            return c
        
    def _get_current_inventory(self):
        with open(self.inventory_path, 'r') as file:
            return yaml.safe_load(file)
        
    def _get_purchase_history(self):
        with open(self.purchases_path, 'r') as file:
            return yaml.safe_load(file)

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
        response = self.client.get("/item/4931f25f-ff1c-4d49-b1d1-15c78bcc92d3")
        body = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('White T-Shirt', body)
        self.assertIn('Classic white t-shirt, goes with every outfit.', body)

    def test_item_page_nonexistent(self):
        """Test item page with nonexistent ID"""
        with self.client.get("/item/1") as response:
            self.assertEqual(response.status_code, 302)
            redirect_location = response.headers['Location']

        with self.client.get(redirect_location) as response:
            self.assertIn("Item does not exist.", response.get_data(as_text=True))

    def test_add_to_cart(self):
        """Test add to cart functionality"""
        self.client = self._create_session_with_cart()

        item_id = "4931f25f-ff1c-4d49-b1d1-15c78bcc92d3"
        data = {'quantity': "1"}
        response = self.client.post(
            f"/item/{item_id}/add-to-cart", 
            data=data, 
            follow_redirects=True
        )

        body = response.get_data(as_text=True)
        self.assertIn('Added to cart!', body)

        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'][item_id], 1)

    def test_add_to_cart_invalid_quantity(self):
        """Test add to cart with a quantity too large and too small"""
        # Too large
        self.client = self._create_session_with_cart()

        item_id = "1eb43f24-b5c9-4d60-ae93-1d13912669c2"
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

        item_id = "1"
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

    def test_view_cart(self):
        """Test view cart"""
        # No cart
        self.client = self._create_session_with_cart()
        response = self.client.get("/cart")
        body = response.get_data(as_text=True)
        self.assertIn('You have no items in your cart!', body)

        # Items in cart
        self.client = self._create_session_with_cart({
            '4931f25f-ff1c-4d49-b1d1-15c78bcc92d3': 1
        })
        response = self.client.get("/cart")
        body = response.get_data(as_text=True)
        self.assertIn('White T-Shirt', body)
        self.assertIn('Quantity 1', body)
    
    def test_clear_cart(self):
        """Test clear cart functionality"""
        self.client = self._create_session_with_cart({
            '4931f25f-ff1c-4d49-b1d1-15c78bcc92d3': 1
        })

        item_id = '4931f25f-ff1c-4d49-b1d1-15c78bcc92d3'
        response = self.client.post(f"/cart/{item_id}/delete", follow_redirects=True)
        body = response.get_data(as_text=True)

        self.assertIn("Item removed from cart", body)

    def test_clear_cart_nonexistent_id(self):
        """Test clear cart functionality if item ID doesn't exist"""
        self.client = self._create_session_with_cart({
            '4931f25f-ff1c-4d49-b1d1-15c78bcc92d3': 1
        })

        item_id = "1"
        response = self.client.post(f"/cart/{item_id}/delete", follow_redirects=True)
        body = response.get_data(as_text=True)

        self.assertIn("Item does not exist.", body)

    def test_clear_cart_item_not_in_cart(self):
        """Test clear cart functionality for valid ID but item not in cart"""
        self.client = self._create_session_with_cart({
            '4931f25f-ff1c-4d49-b1d1-15c78bcc92d3': 1
        })

        item_id = "1eb43f24-b5c9-4d60-ae93-1d13912669c2"
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
            self.assertEqual(session['username'], 'admin')

        response = self.client.post("/users/sign-out", follow_redirects=True)

        self.assertIn("You have been signed out.", response.get_data(as_text=True))

        with self.client.session_transaction() as session:
            self.assertNotIn('username', session)

    def test_check_out(self):
        self.client = self._sign_in()
        self.client = self._create_session_with_cart({
            '4931f25f-ff1c-4d49-b1d1-15c78bcc92d3': 1
        })

        # Check inventory file before we do anything
        current_inventory = self._get_current_inventory()
        item_id = '4931f25f-ff1c-4d49-b1d1-15c78bcc92d3'
        self.assertEqual(current_inventory[item_id]['available'], 10)

        response = self.client.post("/users/check-out", follow_redirects=True)
        self.assertIn('Thank you for your purchase!', response.get_data(as_text=True))

        # Check inventory file afterwards
        new_inventory = self._get_current_inventory()
        self.assertEqual(new_inventory[item_id]['available'], 9)

        # Check session cart is empty
        with self.client.session_transaction() as session:
            self.assertEqual(session['cart'], {})

        # Check that there are 3 purchases in the purchase history file (there were 2 to start)
        purchases = self._get_purchase_history()
        self.assertEqual(len(purchases), 3)

    def test_check_out_empty_cart(self):
        """Test that checkout doesn't go through with an empty cart"""
        self.client = self._sign_in()
        self.client = self._create_session_with_cart()

        response = self.client.post("/users/check-out", follow_redirects=True)
        self.assertIn('No items to check out!', response.get_data(as_text=True))

    def test_purchase_history(self):
        """Test that purchase history page populates correctly"""
        self.client = self._sign_in()

        response = self.client.get("/users/history")
        body = response.get_data(as_text=True)
        self.assertIn('White T-Shirt', body)
        self.assertIn('Quantity 1', body)
        self.assertIn('Confirmation number: e3cfe3dd-62ef-4bdd-b307-4d982ba0e2b5', body)
        self.assertIn('Purchase date: 2026-01-12', body)

        # Confirm the other fake user's purchase is not shown
        self.assertNotIn('Black Jeans', body)
        self.assertNotIn('Confirmation number: 5d39b0c0-4cee-464d-81fb-fc9787ceefcb', body)
        self.assertNotIn('Purchase date: 2026-01-11', body)


if __name__ == "__main__":
    unittest.main()