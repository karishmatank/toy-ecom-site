from contextlib import contextmanager
import logging
import psycopg2
from psycopg2.extras import DictCursor

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

class DatabasePersistence:
    def __init__(self, testing_mode):
        self.testing = testing_mode
        self._setup_schema()

    @contextmanager
    def _database_connect(self):
        if self.testing:
            connection = psycopg2.connect(dbname='toy_ecomm_test')
        else:
            connection = psycopg2.connect(dbname='toy_ecomm')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _setup_schema(self):
        with self._database_connect() as connection:
            with connection.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT table_name, count(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    GROUP BY table_name;
                """)
            
                tables = cursor.fetchall()
        
                existing_tables = set(table['table_name'] for table in tables if table['count'] == 1)
                names = set(['users', 'inventory', 'orders', 'order_items', 'shopping_carts', 'cart_items'])

                for table_name in (names - existing_tables):
                    match table_name:
                        case 'users':
                            query = """
                                CREATE TABLE users (
                                    id serial PRIMARY KEY,
                                    username text NOT NULL UNIQUE,
                                    hashed_pwd text NOT NULL
                                );
                            """
                        case 'inventory':
                            query = """
                                CREATE TABLE inventory (
                                    id serial PRIMARY KEY,
                                    available integer NOT NULL CHECK (available >= 0),
                                    product_name text NOT NULL,
                                    description text NOT NULL
                                );
                            """
                        case 'orders':
                            query = """
                                CREATE TABLE orders (
                                    id serial PRIMARY KEY,
                                    purchase_date date NOT NULL DEFAULT NOW(),
                                    user_id integer NOT NULL REFERENCES users (id) ON DELETE CASCADE
                                );
                            """
                        case 'order_items':
                            query = """
                                CREATE TABLE order_items (
                                    id serial PRIMARY KEY,
                                    order_id integer NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
                                    item_id integer NOT NULL REFERENCES inventory (id) ON DELETE CASCADE,
                                    quantity integer NOT NULL CHECK (quantity > 0)
                                );
                            """
                        case 'shopping_carts':
                            query = """
                                CREATE TABLE shopping_carts (
                                    id serial PRIMARY KEY,
                                    FOREIGN KEY (id) REFERENCES users (id) ON DELETE CASCADE
                                );
                            """
                        case 'cart_items':
                            query = """
                                CREATE TABLE cart_items (
                                    id serial PRIMARY KEY,
                                    item_id integer NOT NULL REFERENCES inventory (id) ON DELETE CASCADE
                                );
                            """

                    cursor.execute(query)

    def is_user_existing(self, username):
        """Check if user already exists"""
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT *
                    FROM users
                    WHERE username = %s;
                """, (username, ))
                match = cursor.fetchone()
            
        return bool(match)
    
    def is_item_in_inventory(self, item_id):
        """Check if item is in inventory"""
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT *
                    FROM inventory
                    WHERE id = %s;
                """, (item_id, ))
                match = cursor.fetchone()
            
        return bool(match)
    
    def update_user_info(self, username, hashed_password):
        """Add a new user to the database"""
        query = """
            INSERT INTO users (username, hashed_pwd) VALUES
            (%s, %s);
        """
        logger.info("Executing query: %s with username: %s", query, username)
        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (username, hashed_password))

    def get_user_cart(self, user_id):
        """Get items from user's cart"""
        with self._database_connect() as connection:
            with connection.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT users.id AS user_id, cart_items.item_id, cart_items.quantity
                    FROM cart_items
                    JOIN users ON users.id = cart_items.cart_id 
                    WHERE users.id = %s;
                """, (user_id, ))
        
                cart = cursor.fetchall()
        
        # logger.info("Cart is: %s", [dict(item) for item in cart])
        return cart
    
    def get_inventory(self):
        """Get inventory information"""
        with self._database_connect() as connection:
            with connection.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute("""
                    SELECT *
                    FROM inventory;
                """)

                inventory = cursor.fetchall()

        return inventory

    def update_inventory(self, user_id):
        """Update inventory information after item ordered"""

        # Get items from user's cart
        cart = self.get_user_cart(user_id)

        # To avoid an N+1 query, where we would otherwise loop through the cart
        # to execute an update statement for each cart item, we do the below:
        placeholders = ", ".join(["(%s, %s)" for _ in cart])
        values = tuple(i for item in cart for i in (item['item_id'], item['quantity']))

        query = f"""
            UPDATE inventory AS i
            SET available = i.available - c.quantity
            FROM (VALUES {placeholders}) AS c(item_id, quantity)
            WHERE i.id = c.item_id;
        """
        logger.info("Executing query: %s with cart: %s", query, cart)

        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
    
    def update_orders(self, user_id):
        """Update orders and order_items tables after order placed"""
        
        # Get items from user's cart
        cart = self.get_user_cart(user_id)

        # Create a new order. Using RETURNING to get the row back with the id information
        query_order = """
            INSERT INTO orders (user_id) VALUES 
            (%s)
            RETURNING *;
        """
        logger.info("Executing query: %s", query_order)

        with self._database_connect() as connection:
            with connection.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query_order, (user_id, ))
                order_info = cursor.fetchone()

        # Create new order items based on cart
        placeholders = ", ".join(["(%s, %s, %s)" for _ in cart])
        values = tuple(i for item in cart for i in (order_info['id'], item['item_id'], item['quantity']))

        query_order_items = f"""
            INSERT INTO order_items (order_id, item_id, quantity) VALUES {placeholders};
        """
        logger.info("Executing query: %s", query_order_items)

        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query_order_items, values)
    
    def is_quantity_valid(self, quantity, item_id):
        query = """
            SELECT available
            FROM inventory
            WHERE id = %s;
        """
        logger.info("Executing query: %s on item_id: %s", query, item_id)

        with self._database_connect() as connection:
            with connection.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query, (item_id, ))
                available = cursor.fetchone()['available']
        
        return quantity > 0 and quantity <= available
    
    def is_existing_user(self, username):
        query = """
            SELECT * FROM users WHERE username = %s;
        """
        logger.info("Executing query: %s on username: %s", query, username)

        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (username, ))
                results = cursor.fetchone()
        
        return bool(results)
    
    def get_user_id(self, username):
        query = """
            SELECT id FROM users WHERE username = %s;
        """
        with self._database_connect() as connection:
            with connection.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query, (username,))
                return cursor.fetchone()['id']

    def get_user_pwd(self, username):
        if self.is_existing_user(username):
            query = """
                SELECT hashed_pwd
                FROM users
                WHERE username = %s;
            """
            
            with self._database_connect() as connection:
                with connection.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute(query, (username,))
                    actual = cursor.fetchone()['hashed_pwd']

            return actual
        return None
    
    def get_user_history(self, user_id):
        """Get user order history"""
        query = """
            SELECT 
                orders.id AS order_id, 
                orders.purchase_date, 
                order_items.item_id,
                order_items.quantity
            FROM orders
            JOIN order_items ON orders.id = order_items.order_id
            WHERE orders.user_id = %s;
        """
        logger.info("Executing query: %s on user_id: %s", query, user_id)

        with self._database_connect() as connection:
            with connection.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query, (user_id,))
                order_history = cursor.fetchall()

        return order_history
    
    def create_cart(self, user_id):
        """Create a cart for new users"""

        query = """
            INSERT INTO shopping_carts (id) VALUES (%s);
        """

        with self._database_connect() as connection:
            with connection.cursor() as cursor: 
                cursor.execute(query, (user_id,))
    
    def add_to_cart(self, user_id, cart_items):
        # Get cart based on user ID
        cart = self.get_user_cart(user_id)

        existing_items = [row['item_id'] for row in cart]
        items_to_update = set(existing_items) & set(cart_items.keys())
        items_to_add = set(cart_items.keys()) - set(existing_items)

        if items_to_update:
            # If an item is already in the cart, we just update its value
            placeholders = ", ".join(["(%s, %s)" for _ in items_to_update])
            values = tuple(
                [i for item_id, quantity in cart_items.items()
                    if item_id in items_to_update
                    for i in (item_id, quantity)] + 
                [user_id]
            )
            query_update = f"""
                UPDATE cart_items AS ci
                SET quantity = ci.quantity + i.quantity
                FROM (VALUES {placeholders}) AS i(item_id, quantity)
                WHERE ci.item_id = i.item_id AND cart_id = %s;
            """
            with self._database_connect() as connection:
                with connection.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute(query_update, values)

        if items_to_add:
            # If an item is not in the cart, add it as a new entry in the table
            placeholders = ", ".join(["(%s, %s, %s)" for _ in items_to_add])
            values = tuple(i for item_id, quantity in cart_items.items() 
                             if item_id in items_to_add
                             for i in (user_id, item_id, quantity)
                          )
            query_insert = f"""
                INSERT INTO cart_items (cart_id, item_id, quantity) VALUES {placeholders}; 
            """

            with self._database_connect() as connection:
                with connection.cursor(cursor_factory=DictCursor) as cursor:
                    cursor.execute(query_insert, values)

    def is_item_in_cart(self, user_id, item_id):
        """Check if item is in user's cart"""
        query = """
            SELECT count(*)
            FROM cart_items
            WHERE cart_id = %s AND item_id = %s;
        """

        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (user_id, item_id))
                return bool(cursor.fetchone())
            
    def remove_item_from_cart(self, user_id, item_id):
        """Remove specified items from user cart"""

        query = """
            DELETE FROM cart_items
            WHERE cart_id = %s AND item_id = %s;
        """

        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (user_id, item_id))

    def clear_cart(self, user_id):
        """Remove all items from a user's cart"""

        query = """
            DELETE FROM cart_items
            WHERE cart_id = %s;
        """

        with self._database_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (user_id,))
