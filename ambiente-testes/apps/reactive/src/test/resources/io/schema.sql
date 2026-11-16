-- PostgreSQL 16. Apply with scripts/database.sh apply-schema, in one transaction.
-- The caller selects the schema: public for use, a temporary schema for checks.
-- Catalog IDs are assigned by the reproducible seed; event IDs are generated.

CREATE TABLE category (
    id              bigint       NOT NULL,
    name            varchar(100) NOT NULL,
    slug            varchar(100) NOT NULL,
    description     text         NOT NULL,
    display_order   integer      NOT NULL DEFAULT 0,
    active          boolean      NOT NULL DEFAULT true,
    created_at      timestamptz  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      timestamptz  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT category_pk PRIMARY KEY (id),
    CONSTRAINT category_slug_uk UNIQUE (slug),
    CONSTRAINT category_id_positive CHECK (id > 0),
    CONSTRAINT category_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT category_slug_not_blank CHECK (btrim(slug) <> ''),
    CONSTRAINT category_display_order_valid CHECK (display_order >= 0),
    CONSTRAINT category_dates_valid CHECK (updated_at >= created_at)
);

CREATE TABLE catalog_item (
    id              bigint         NOT NULL,
    category_id     bigint         NOT NULL,
    sku             varchar(64)    NOT NULL,
    name            varchar(200)   NOT NULL,
    description     text           NOT NULL,
    brand           varchar(100)   NOT NULL,
    model           varchar(100)   NOT NULL,
    price           numeric(12, 2) NOT NULL,
    currency        varchar(3)     NOT NULL,
    weight_grams    integer        NOT NULL,
    status          varchar(16)    NOT NULL,
    created_at      timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      timestamptz    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT catalog_item_pk PRIMARY KEY (id),
    CONSTRAINT catalog_item_sku_uk UNIQUE (sku),
    CONSTRAINT catalog_item_category_fk FOREIGN KEY (category_id)
        REFERENCES category (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT catalog_item_id_positive CHECK (id > 0),
    CONSTRAINT catalog_item_sku_not_blank CHECK (btrim(sku) <> ''),
    CONSTRAINT catalog_item_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT catalog_item_brand_not_blank CHECK (btrim(brand) <> ''),
    CONSTRAINT catalog_item_model_not_blank CHECK (btrim(model) <> ''),
    -- The finite upper bound also excludes PostgreSQL numeric NaN.
    CONSTRAINT catalog_item_price_valid CHECK (price BETWEEN 0 AND 9999999999.99),
    CONSTRAINT catalog_item_currency_valid CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT catalog_item_weight_valid CHECK (weight_grams >= 0),
    CONSTRAINT catalog_item_status_valid CHECK (status IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT catalog_item_dates_valid CHECK (updated_at >= created_at)
);

-- Append-only is the workload's operation policy; no update/delete triggers.
CREATE TABLE access_event (
    id              bigint GENERATED ALWAYS AS IDENTITY,
    item_id         bigint      NOT NULL,
    run_id          uuid        NOT NULL,
    request_id      uuid        NOT NULL,
    event_type      varchar(32) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT access_event_pk PRIMARY KEY (id),
    CONSTRAINT access_event_item_fk FOREIGN KEY (item_id)
        REFERENCES catalog_item (id) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT access_event_run_request_uk UNIQUE (run_id, request_id),
    CONSTRAINT access_event_type_not_blank CHECK (btrim(event_type) <> '')
);

-- PK/UNIQUE constraints create the six indexes of this initial design.
-- The workload reads product/category by PK and inserts one event per request.
-- Additional indexes must be justified and kept identical between models.
