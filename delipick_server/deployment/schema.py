"""Schema for the fictional, standalone demonstration database."""
STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS categories (category_id INT PRIMARY KEY, category_name VARCHAR(50) NOT NULL)",
    """CREATE TABLE IF NOT EXISTS restaurants (
        id INT PRIMARY KEY, name VARCHAR(100) NOT NULL, category_id INT,
        address VARCHAR(255), latitude DOUBLE, longitude DOUBLE,
        google_rating DECIMAL(2,1), image_url TEXT, prep_time INT, delivery_time INT,
        delivery_score FLOAT DEFAULT 0, last_delivery_update DATETIME,
        INDEX idx_lab_category_id(category_id,id), FOREIGN KEY(category_id) REFERENCES categories(category_id))""",
    """CREATE TABLE IF NOT EXISTS menus (
        id INT PRIMARY KEY, restaurant_id INT NOT NULL, menu_name VARCHAR(100) NOT NULL,
        price INT NOT NULL, image_url TEXT,
        INDEX idx_lab_price_rest(price,restaurant_id,id), INDEX idx_lab_rest_price(restaurant_id,price,id),
        FOREIGN KEY(restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS menu_flavors (
        menu_id INT PRIMARY KEY, menu_name VARCHAR(100) NOT NULL,
        salty DECIMAL(3,1), sweet DECIMAL(3,1), sour DECIMAL(3,1), umami DECIMAL(3,1), spicy DECIMAL(3,1),
        reason TEXT, semantic_embedding LONGTEXT,
        review_salty DECIMAL(3,1), review_sweet DECIMAL(3,1), review_sour DECIMAL(3,1),
        review_umami DECIMAL(3,1), review_spicy DECIMAL(3,1), review_reason TEXT,
        review_embedding LONGTEXT, menu_tags LONGTEXT,
        FOREIGN KEY(menu_id) REFERENCES menus(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS reviews (
        id INT PRIMARY KEY, restaurant_id INT NOT NULL, menu_id INT,
        content TEXT NOT NULL, positive_score FLOAT DEFAULT 0, negative_score FLOAT DEFAULT 0,
        review_score FLOAT DEFAULT 0, review_reason TEXT,
        INDEX idx_lab_review_score(restaurant_id,review_score),
        FOREIGN KEY(restaurant_id) REFERENCES restaurants(id) ON DELETE CASCADE,
        FOREIGN KEY(menu_id) REFERENCES menus(id) ON DELETE SET NULL)""",
    """CREATE TABLE IF NOT EXISTS menu_tag_map (
        menu_id INT NOT NULL, tag_type VARCHAR(32) NOT NULL, tag_value VARCHAR(64) NOT NULL,
        PRIMARY KEY(menu_id,tag_type,tag_value), INDEX idx_tag_lookup(tag_value,menu_id),
        FOREIGN KEY(menu_id) REFERENCES menus(id) ON DELETE CASCADE)""",
    "CREATE TABLE IF NOT EXISTS deployment_state (state_key VARCHAR(64) PRIMARY KEY, state_value TEXT NOT NULL)",
]
