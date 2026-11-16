package br.pucrs.tcc2.virtualthreads.infrastructure.io;

import br.pucrs.tcc2.virtualthreads.common.exception.ExceptionMaker;
import br.pucrs.tcc2.virtualthreads.domain.io.model.dto.AccessEventDto;
import br.pucrs.tcc2.virtualthreads.domain.io.model.dto.CatalogItemDto;
import br.pucrs.tcc2.virtualthreads.domain.io.model.dto.CategoryDto;
import br.pucrs.tcc2.virtualthreads.domain.io.model.input.AccessEventInput;
import br.pucrs.tcc2.virtualthreads.domain.io.port.spi.IoSpiPort;
import br.pucrs.tcc2.virtualthreads.infrastructure.io.mapper.IoInfrastructureMapper;
import br.pucrs.tcc2.virtualthreads.infrastructure.io.model.CatalogItemEntity;
import br.pucrs.tcc2.virtualthreads.infrastructure.io.model.CategoryEntity;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.time.OffsetDateTime;
import java.time.Duration;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.stereotype.Repository;

@Repository
public class IoAdapterImpl implements IoSpiPort {
    private static final String INSERT_EVENT = """
            INSERT INTO access_event (item_id, run_id, request_id, event_type)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (run_id, request_id) DO NOTHING
            RETURNING id, created_at
            """;

    @PersistenceContext
    private EntityManager entityManager;
    private final JdbcTemplate jdbcTemplate;
    private final IoInfrastructureMapper mapper;
    private final double databaseDelaySeconds;

    public IoAdapterImpl(JdbcTemplate jdbcTemplate, IoInfrastructureMapper mapper,
                         @Value("${tcc.io.database-delay:0ms}") Duration databaseDelay) {
        this.jdbcTemplate = jdbcTemplate;
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
    public void applyDatabaseDelay() {
        if (databaseDelaySeconds == 0) {
            return;
        }
        jdbcTemplate.execute((ConnectionCallback<Void>) connection -> {
            try (var statement = connection.prepareStatement("SELECT pg_sleep(?)")) {
                statement.setDouble(1, databaseDelaySeconds);
                statement.execute();
            }
            return null;
        });
    }

    @Override
    public Optional<CatalogItemDto> findItemById(long itemId) {
        return Optional.ofNullable(entityManager.find(CatalogItemEntity.class, itemId)).map(mapper::toDomain);
    }

    @Override
    public Optional<CategoryDto> findCategoryById(long categoryId) {
        return Optional.ofNullable(entityManager.find(CategoryEntity.class, categoryId)).map(mapper::toDomain);
    }

    @Override
    public AccessEventDto appendEvent(AccessEventInput input) {
        // JdbcTemplate uses the same DataSource/transaction managed by JpaTransactionManager.
        var events = jdbcTemplate.query(INSERT_EVENT, (row, index) -> new AccessEventDto(
                row.getLong("id"), input.itemId(), input.runId(), input.requestId(), input.eventType(),
                row.getObject("created_at", OffsetDateTime.class).toInstant()),
                input.itemId(), input.runId(), input.requestId(), input.eventType());
        if (events.isEmpty()) {
            throw ExceptionMaker.duplicateRequest();
        }
        return events.getFirst();
    }
}
