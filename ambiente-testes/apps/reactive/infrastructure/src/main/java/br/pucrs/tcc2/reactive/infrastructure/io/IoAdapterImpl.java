package br.pucrs.tcc2.reactive.infrastructure.io;

import br.pucrs.tcc2.reactive.common.exception.ExceptionMaker;
import br.pucrs.tcc2.reactive.domain.io.model.dto.AccessEventDto;
import br.pucrs.tcc2.reactive.domain.io.model.dto.CatalogItemDto;
import br.pucrs.tcc2.reactive.domain.io.model.dto.CategoryDto;
import br.pucrs.tcc2.reactive.domain.io.model.input.AccessEventInput;
import br.pucrs.tcc2.reactive.domain.io.port.spi.IoSpiPort;
import br.pucrs.tcc2.reactive.infrastructure.io.mapper.IoInfrastructureMapper;
import br.pucrs.tcc2.reactive.infrastructure.io.model.CatalogItemEntity;
import br.pucrs.tcc2.reactive.infrastructure.io.model.CategoryEntity;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.OffsetDateTime;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class IoAdapterImpl implements IoSpiPort {
    private static final String SELECT_ITEM = """
            SELECT id, category_id, sku, name, description, brand, model, price, currency,
                   weight_grams, status, created_at, updated_at
              FROM catalog_item
             WHERE id = :itemId
            """;
    private static final String SELECT_CATEGORY = """
            SELECT id, name, slug, description, display_order, active, created_at, updated_at
              FROM category
             WHERE id = :categoryId
            """;
    private static final String INSERT_EVENT = """
            INSERT INTO access_event (item_id, run_id, request_id, event_type)
            VALUES (:itemId, :runId, :requestId, :eventType)
            ON CONFLICT (run_id, request_id) DO NOTHING
            RETURNING id, created_at
            """;

    private final DatabaseClient databaseClient;
    private final IoInfrastructureMapper mapper;
    private final double databaseDelaySeconds;

    public IoAdapterImpl(DatabaseClient databaseClient, IoInfrastructureMapper mapper,
                         @Value("${tcc.io.database-delay:0ms}") Duration databaseDelay) {
        this.databaseClient = databaseClient;
        this.mapper = mapper;
        this.databaseDelaySeconds = validateDelay(databaseDelay);
    }

    private static double validateDelay(Duration delay) {
        if (delay.isNegative() || delay.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException("tcc.io.database-delay must be between 0ms and 30s");
        }
        return delay.toNanos() / 1_000_000_000.0;
    }

    @Override
    public Mono<Void> applyDatabaseDelay() {
        if (databaseDelaySeconds == 0) {
            return Mono.empty();
        }
        return databaseClient.sql("SELECT pg_sleep(:delaySeconds)")
                .bind("delaySeconds", databaseDelaySeconds)
                .map((row, metadata) -> Boolean.TRUE)
                .one()
                .then();
    }

    @Override
    public Mono<CatalogItemDto> findItemById(long itemId) {
        return databaseClient.sql(SELECT_ITEM)
                .bind("itemId", itemId)
                .map((row, metadata) -> new CatalogItemEntity(
                        row.get("id", Long.class),
                        row.get("category_id", Long.class),
                        row.get("sku", String.class),
                        row.get("name", String.class),
                        row.get("description", String.class),
                        row.get("brand", String.class),
                        row.get("model", String.class),
                        row.get("price", BigDecimal.class),
                        row.get("currency", String.class),
                        row.get("weight_grams", Integer.class),
                        row.get("status", String.class),
                        row.get("created_at", OffsetDateTime.class).toInstant(),
                        row.get("updated_at", OffsetDateTime.class).toInstant()))
                .one()
                .map(mapper::toDomain);
    }

    @Override
    public Mono<CategoryDto> findCategoryById(long categoryId) {
        return databaseClient.sql(SELECT_CATEGORY)
                .bind("categoryId", categoryId)
                .map((row, metadata) -> new CategoryEntity(
                        row.get("id", Long.class),
                        row.get("name", String.class),
                        row.get("slug", String.class),
                        row.get("description", String.class),
                        row.get("display_order", Integer.class),
                        Boolean.TRUE.equals(row.get("active", Boolean.class)),
                        row.get("created_at", OffsetDateTime.class).toInstant(),
                        row.get("updated_at", OffsetDateTime.class).toInstant()))
                .one()
                .map(mapper::toDomain);
    }

    @Override
    public Mono<AccessEventDto> appendEvent(AccessEventInput input) {
        return databaseClient.sql(INSERT_EVENT)
                .bind("itemId", input.itemId())
                .bind("runId", input.runId())
                .bind("requestId", input.requestId())
                .bind("eventType", input.eventType())
                .map((row, metadata) -> new AccessEventDto(
                        row.get("id", Long.class), input.itemId(), input.runId(), input.requestId(),
                        input.eventType(), row.get("created_at", OffsetDateTime.class).toInstant()))
                .one()
                .switchIfEmpty(Mono.defer(() -> Mono.error(ExceptionMaker.duplicateRequest())));
    }
}
