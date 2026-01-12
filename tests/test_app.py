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
    
    def tearDown(self):
        os.remove(self.inventory_path)

    def _create_session_with_cart(self, items={}):
        with self.client as c:
            with c.session_transaction() as session:
                session['cart'] = items
            return c

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


if __name__ == "__main__":
    unittest.main()