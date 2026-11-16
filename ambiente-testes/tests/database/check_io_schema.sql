-- Executed only in the isolated transaction/schema created by scripts/test.sh schema.
-- Business invariants: valid persistence, referential integrity and one event
-- per request/run. Fixtures never touch the experiment's public tables.

CREATE FUNCTION pg_temp.expect_sqlstate(statement text, expected_state text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    actual_state text;
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
    END;
    IF actual_state IS DISTINCT FROM expected_state THEN
        RAISE EXCEPTION 'Expected SQLSTATE %, got % for: %',
            expected_state, coalesce(actual_state, 'success'), statement;
    END IF;
END;
$$;

INSERT INTO category (id, name, slug, description)
VALUES (1, 'Peripherals', 'peripherals', 'Synthetic test category');

INSERT INTO catalog_item (
    id, category_id, sku, name, description, brand, model,
    price, currency, weight_grams, status
) VALUES (
    1, 1, 'SKU-000001', 'Wireless Mouse', repeat('x', 1024), 'Brand 01', 'WM-001',
    149.90, 'BRL', 120, 'ACTIVE'
);

INSERT INTO access_event (item_id, run_id, request_id, event_type)
VALUES (
    1, '00000000-0000-4000-8000-000000000001',
    '00000000-0000-4000-8000-000000000002', 'ITEM_VIEW'
);

-- A request ID may be reused by a different run.
INSERT INTO access_event (item_id, run_id, request_id, event_type)
VALUES (
    1, '00000000-0000-4000-8000-000000000003',
    '00000000-0000-4000-8000-000000000002', 'ITEM_VIEW'
);

DO $$
BEGIN
    IF (SELECT count(*) FROM access_event) <> 2
       OR (SELECT count(DISTINCT id) FROM access_event) <> 2
       OR (SELECT count(*) FROM access_event WHERE created_at IS NOT NULL AND id > 0) <> 2
       OR (SELECT price FROM catalog_item WHERE id = 1) <> 149.90
       OR (SELECT octet_length(description) FROM catalog_item WHERE id = 1) <> 1024 THEN
        RAISE EXCEPTION 'Valid fixture did not preserve values, identity or timestamps';
    END IF;

    PERFORM pg_temp.expect_sqlstate(
        'UPDATE catalog_item SET category_id = 999 WHERE id = 1', '23503');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE access_event SET item_id = 999', '23503');
    PERFORM pg_temp.expect_sqlstate(
        'DELETE FROM category WHERE id = 1', '23503');
    PERFORM pg_temp.expect_sqlstate(
        'DELETE FROM catalog_item WHERE id = 1', '23503');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE catalog_item SET price = -0.01 WHERE id = 1', '23514');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE catalog_item SET price = ''NaN'' WHERE id = 1', '23514');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE catalog_item SET weight_grams = -1 WHERE id = 1', '23514');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE catalog_item SET currency = ''brl'' WHERE id = 1', '23514');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE catalog_item SET status = ''INVALID'' WHERE id = 1', '23514');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE catalog_item SET updated_at = created_at - interval ''1 second'' WHERE id = 1', '23514');
    PERFORM pg_temp.expect_sqlstate(
        'INSERT INTO category (id, name, slug, description) VALUES (2, ''Other'', ''peripherals'', '''')',
        '23505');
    PERFORM pg_temp.expect_sqlstate(
        'INSERT INTO catalog_item SELECT 2, category_id, sku, name, description, brand, model,
            price, currency, weight_grams, status, created_at, updated_at
         FROM catalog_item WHERE id = 1', '23505');
    PERFORM pg_temp.expect_sqlstate(
        'INSERT INTO access_event (item_id, run_id, request_id, event_type)
         SELECT item_id, run_id, request_id, event_type FROM access_event LIMIT 1', '23505');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE access_event SET request_id = NULL', '23502');
    PERFORM pg_temp.expect_sqlstate(
        'UPDATE access_event SET event_type = ''   ''', '23514');
END;
$$;

SELECT 'Schema /io: valid persistence and 15 integrity checks passed' AS result;
