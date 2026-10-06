-- =============================================================================
-- WBMS-Lite database schema (SQLite)
--
-- Rules used throughout:
--   * Every statement is IF NOT EXISTS, so running this file twice is harmless.
--   * Timestamps are UTC text in the form 2026-10-05T14:30:00Z. That shape sorts
--     correctly as plain text, so "expires_at <= :now" works without conversion.
--     Code that writes a timestamp must use the same shape.
--   * Money is whole Kenyan shillings (INTEGER). No decimals, no rounding bugs.
--   * Foreign keys use ON DELETE RESTRICT: a row that is still referenced can
--     never be deleted. Packages are retired with is_active = 0, not deleted.
--   * Foreign keys only work when PRAGMA foreign_keys = ON, which wbms.db does
--     for every connection.
-- =============================================================================


-- packages: the price list. What a customer can buy: how long, how fast, how much
-- data. A NULL data_limit_mb means unlimited data. Retire a package by setting
-- is_active = 0 so old transactions keep pointing at a real row.
CREATE TABLE IF NOT EXISTS packages (
    id               INTEGER PRIMARY KEY,
    name             TEXT    NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    price_kes        INTEGER NOT NULL CHECK (price_kes >= 0),
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    data_limit_mb    INTEGER          CHECK (data_limit_mb IS NULL OR data_limit_mb > 0),
    speed_kbps       INTEGER NOT NULL CHECK (speed_kbps > 0),
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);


-- customers: one row per phone number, created on the customer's first payment.
-- phone_number is stored in the normalised form produced by wbms.phone, so the
-- same person can never appear twice under different spellings of one number.
CREATE TABLE IF NOT EXISTS customers (
    id           INTEGER PRIMARY KEY,
    phone_number TEXT NOT NULL UNIQUE CHECK (length(trim(phone_number)) > 0),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);


-- transactions: one row per attempt to buy a package, by M-Pesa or by voucher.
-- status moves pending -> success or pending -> failed, never back.
--   * gateway_ref is the gateway's checkout id. It is NULL until the gateway
--     answers, and UNIQUE so one gateway reference can only ever be applied to
--     one transaction. SQLite allows many NULLs in a UNIQUE column.
--   * method is 'mpesa' or 'voucher'. A voucher redemption has no phone number,
--     so customer_id may be NULL only for method = 'voucher'.
--   * paid_at is set exactly when status = 'success'.
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers (id) ON DELETE RESTRICT,
    package_id  INTEGER NOT NULL REFERENCES packages (id) ON DELETE RESTRICT,
    method      TEXT    NOT NULL DEFAULT 'mpesa' CHECK (method IN ('mpesa', 'voucher')),
    amount_kes  INTEGER NOT NULL CHECK (amount_kes >= 0),
    status      TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'success', 'failed')),
    gateway_ref TEXT    UNIQUE,
    receipt     TEXT,
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    paid_at     TEXT,
    CHECK (method = 'voucher' OR customer_id IS NOT NULL),
    CHECK ((status = 'success') = (paid_at IS NOT NULL))
);


-- sessions: the period of internet access a paid transaction bought. The UNIQUE
-- transaction_id is the last line of defence against the classic billing bug:
-- a duplicated payment callback must never create a second session.
-- status: pending_activation (paid, router not told yet), active, expired,
-- revoked. started_at and expires_at are UTC; data_used_mb grows as the
-- customer browses.
CREATE TABLE IF NOT EXISTS sessions (
    id             INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL UNIQUE REFERENCES transactions (id) ON DELETE RESTRICT,
    mac_address    TEXT    NOT NULL CHECK (length(trim(mac_address)) > 0),
    started_at     TEXT    NOT NULL,
    expires_at     TEXT    NOT NULL,
    data_used_mb   INTEGER NOT NULL DEFAULT 0 CHECK (data_used_mb >= 0),
    status         TEXT    NOT NULL DEFAULT 'active'
                           CHECK (status IN ('pending_activation', 'active', 'expired', 'revoked')),
    CHECK (expires_at > started_at)
);


-- vouchers: prepaid codes sold offline (printed cards, resellers). A voucher is
-- used once: unused -> redeemed, or unused -> void. batch_id groups the codes
-- created by one "generate" command so a whole batch can be listed or voided.
-- redeemed_at is set exactly when status = 'redeemed'.
CREATE TABLE IF NOT EXISTS vouchers (
    id          INTEGER PRIMARY KEY,
    code        TEXT    NOT NULL UNIQUE CHECK (length(code) > 0),
    package_id  INTEGER NOT NULL REFERENCES packages (id) ON DELETE RESTRICT,
    status      TEXT    NOT NULL DEFAULT 'unused'
                        CHECK (status IN ('unused', 'redeemed', 'void')),
    batch_id    TEXT,
    redeemed_at TEXT,
    CHECK ((status = 'redeemed') = (redeemed_at IS NOT NULL))
);


-- admins: people who may log in to /admin. Only a password HASH is stored,
-- never the password itself (see werkzeug.security.generate_password_hash).
CREATE TABLE IF NOT EXISTS admins (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE CHECK (length(trim(username)) > 0),
    password_hash TEXT NOT NULL CHECK (length(password_hash) > 0),
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);


-- Indexes ---------------------------------------------------------------------
-- The expiry worker asks "which active sessions are overdue?" every few seconds.
CREATE INDEX IF NOT EXISTS idx_sessions_status_expires ON sessions (status, expires_at);
-- The reconcile job and the dashboard filter transactions by status.
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions (status);
-- SQLite does not index foreign keys by itself. These keep joins and the
-- ON DELETE RESTRICT checks fast, and let the portal find a device's session.
CREATE INDEX IF NOT EXISTS idx_transactions_customer ON transactions (customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_package  ON transactions (package_id);
CREATE INDEX IF NOT EXISTS idx_vouchers_package      ON vouchers (package_id);
CREATE INDEX IF NOT EXISTS idx_sessions_mac          ON sessions (mac_address);
