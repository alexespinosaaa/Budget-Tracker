-- CATEGORY TABLE: Includes monthly spending limit (limit_amount)
CREATE TABLE IF NOT EXISTS category (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    limit_amount REAL DEFAULT NULL,  -- interpreted as monthly limit
    type INTEGER NOT NULL, -- 0 is normal, 1 is fixed
    currency TEXT NOT NULL
);

-- WALLET TABLE: Stores wallet details
CREATE TABLE IF NOT EXISTS wallet (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0.0,
    currency TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- EXPENSE TABLE: Stores all spending details
CREATE TABLE IF NOT EXISTS expense (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category_id INTEGER,
    cost REAL NOT NULL,
    date DATE NOT NULL,
    description TEXT,
    wallet_id INTEGER,
    FOREIGN KEY (category_id) REFERENCES category(id),
    FOREIGN KEY (wallet_id) REFERENCES wallet(id)
);

-- GOAL TABLE: Tracks financial goals per category
CREATE TABLE IF NOT EXISTS goal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    amount_to_reach REAL NOT NULL,
    amount_reached REAL NOT NULL DEFAULT 0.0,
    category_id INTEGER,
    currency TEXT NOT NULL,
    completed BOOLEAN DEFAULT 0,
    start_date DATE,
    end_date DATE,
    FOREIGN KEY (category_id) REFERENCES category(id)
);


-- PROFILE TABLE: central place for app settings
CREATE TABLE IF NOT EXISTS profile (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL,             

    -- User
    photo_path       TEXT,                      
    monthly_budget   REAL DEFAULT 0.0,

    -- Preferences
    main_wallet_id   INTEGER,                   
    skip_months      TEXT DEFAULT '[]',         
    theme            INTEGER,

    -- Security
    password_hash    TEXT,                      

    -- Misc
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login       TIMESTAMP
);
