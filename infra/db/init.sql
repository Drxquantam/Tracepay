-- Runs once, on the first start of the Postgres container.
-- Tests use their own database so they can wipe tables without touching demo data.
CREATE DATABASE tracepay_test OWNER tracepay;
