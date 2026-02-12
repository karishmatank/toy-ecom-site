CREATE TABLE users (
  id serial PRIMARY KEY,
  username text NOT NULL UNIQUE,
  hashed_pwd text NOT NULL
);

INSERT INTO users (username, hashed_pwd) VALUES
('admin', '$2b$12$ugokt6qiEsW28czTnPB6j.3x9/cZrZLsyTUW5qyxykp0JoW3uzIDu'),
('existing_user', '$2b$12$ugokt6qiEsW28czTnPB6j.3x9/cZrZLsyTUW5qyxykp0JoW3uzIDu');

CREATE TABLE inventory (
  id serial PRIMARY KEY,
  available integer NOT NULL CHECK (available >= 0),
  product_name text NOT NULL UNIQUE,
  description text NOT NULL
);

INSERT INTO inventory (available, product_name, description) VALUES
(2, 'Black Jeans', 'Durable jeans!'),
(10, 'White T-Shirt', 'Classic white t-shirt, goes with every outfit.');

CREATE TABLE orders (
  id serial PRIMARY KEY,
  purchase_date timestamp NOT NULL DEFAULT NOW(),
  user_id integer NOT NULL REFERENCES users (id) ON DELETE CASCADE
);

INSERT INTO orders (user_id) VALUES (1), (2);

CREATE TABLE order_items (
  id serial PRIMARY KEY,
  order_id integer NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
  item_id integer NOT NULL REFERENCES inventory (id) ON DELETE CASCADE,
  UNIQUE (order_id, item_id),
  quantity integer NOT NULL CHECK (quantity > 0)
);

INSERT INTO order_items (order_id, item_id, quantity) VALUES
(1, 2, 1),
(2, 1, 1);

CREATE TABLE shopping_carts (
  id integer PRIMARY KEY,
  FOREIGN KEY (id) REFERENCES users (id) ON DELETE CASCADE
);

INSERT INTO shopping_carts (id) VALUES (1), (2);

CREATE TABLE cart_items (
  id serial PRIMARY KEY,
  cart_id integer NOT NULL REFERENCES shopping_carts (id) ON DELETE CASCADE,
  item_id integer NOT NULL REFERENCES inventory (id) ON DELETE CASCADE,
  quantity integer NOT NULL CHECK (quantity > 0),
  UNIQUE (cart_id, item_id)
);