package br.pucrs.tcc2.virtualthreads.infrastructure.io;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.EntityManagerFactory;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executors;
import org.hibernate.SessionFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.mockito.stubbing.Answer;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.doAnswer;

@EnabledIfEnvironmentVariable(named = "TCC_IO_INTEGRATION", matches = "true")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {"spring.jpa.properties.hibernate.generate_statistics=true",
                "tcc.io.database-delay=1ms", "tcc.mixed.cpu-iterations=2"})
class IoPostgresIntegrationTest {
    private static final String SCHEMA = "m2_io_test_" + UUID.randomUUID().toString().replace("-", "");
    private static boolean created;

    @LocalServerPort private int port;
    @Autowired private ObjectMapper mapper;
    @Autowired private JdbcTemplate jdbc;
    @Autowired private EntityManagerFactory entityManagerFactory;
    @MockitoSpyBean private IoAdapterImpl adapter;
    private final HttpClient client = HttpClient.newHttpClient();

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) throws Exception {
        try (Connection connection = connection()) {
            connection.setAutoCommit(false);
            try (var statement = connection.createStatement()) {
                statement.execute("CREATE SCHEMA " + SCHEMA);
                statement.execute("SET LOCAL search_path TO " + SCHEMA + ", pg_catalog");
                ScriptUtils.executeSqlScript(connection, new ClassPathResource("io/schema.sql"));
                statement.executeUpdate("""
                        INSERT INTO category (id, name, slug, description)
                        VALUES (1, 'Category 1', 'category-1', 'Category description')
                        """);
                statement.executeUpdate("""
                        INSERT INTO catalog_item
                            (id, category_id, sku, name, description, brand, model, price, currency, weight_grams, status)
                        VALUES (1, 1, 'SKU-1', 'Item 1', 'Item description', 'Brand', 'Model', 12.34, 'BRL', 100, 'ACTIVE')
                        """);
            }
            connection.commit();
            created = true;
        }
        registry.add("spring.datasource.url", () -> required("IO_TEST_DATABASE_URL") + "?currentSchema=" + SCHEMA);
        registry.add("spring.datasource.username", () -> required("IO_TEST_DATABASE_USER"));
        registry.add("spring.datasource.password", () -> required("IO_TEST_DATABASE_PASSWORD"));
    }

    private static Connection connection() throws Exception {
        return DriverManager.getConnection(required("IO_TEST_DATABASE_URL"),
                required("IO_TEST_DATABASE_USER"), required("IO_TEST_DATABASE_PASSWORD"));
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing integration configuration: " + name);
        }
        return value;
    }

    @AfterEach
    void closeClient() {
        client.close();
    }

    @AfterAll
    static void removeOnlyOwnedSchema() throws Exception {
        if (created) {
            try (var connection = connection(); var statement = connection.createStatement()) {
                statement.execute("DROP SCHEMA " + SCHEMA + " CASCADE");
            }
        }
    }

    @Test
    void executesBothReadsAndTheWriteOnTheSameVirtualThreadInOneTransaction() throws Exception {
        var threads = new CopyOnWriteArrayList<Thread>();
        var transactions = new CopyOnWriteArrayList<Boolean>();
        Answer<Object> recordExecution = invocation -> {
            threads.add(Thread.currentThread());
            transactions.add(TransactionSynchronizationManager.isActualTransactionActive());
            return invocation.callRealMethod();
        };
        doAnswer(recordExecution).when(adapter).findItemById(anyLong());
        doAnswer(recordExecution).when(adapter).findCategoryById(anyLong());
        doAnswer(recordExecution).when(adapter).appendEvent(any());

        UUID run = UUID.randomUUID();
        UUID request = UUID.randomUUID();
        assertThat(execute(1, run, request).statusCode()).isEqualTo(200);
        assertThat(threads).hasSize(3).allMatch(Thread::isVirtual);
        assertThat(threads).allMatch(thread -> thread == threads.getFirst());
        assertThat(transactions).containsExactly(true, true, true);
        assertThat(count(run, request)).isEqualTo(1);
    }

    @Test
    void returnsAllFieldsAfterCommitAndPerformsTwoOrmReads() throws Exception {
        UUID run = UUID.randomUUID();
        UUID request = UUID.randomUUID();
        var statistics = entityManagerFactory.unwrap(SessionFactory.class).getStatistics();
        statistics.clear();

        var response = execute(1, run, request);
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(2);
        JsonNode body = mapper.readTree(response.body());
        assertThat(body.path("item").size()).isEqualTo(13);
        assertThat(body.path("category").size()).isEqualTo(8);
        assertThat(body.path("event").size()).isEqualTo(6);
        assertThat(body.path("item").path("price").decimalValue()).isEqualByComparingTo("12.34");
        assertThat(body.path("category").path("description").asText()).isEqualTo("Category description");
        assertThat(body.path("event").path("eventType").asText()).isEqualTo("ITEM_VIEW");
        assertThat(body.path("event").path("createdAt").asText()).isNotBlank();
        assertThat(count(run, request)).isEqualTo(1);
        // A separate connection can see the write only after the HTTP transaction committed.
        try (var connection = connection(); var statement = connection.prepareStatement(
                "SELECT id FROM " + SCHEMA + ".access_event WHERE run_id = ? AND request_id = ?")) {
            statement.setObject(1, run);
            statement.setObject(2, request);
            try (var rows = statement.executeQuery()) {
                assertThat(rows.next()).isTrue();
                assertThat(rows.getLong(1)).isEqualTo(body.path("event").path("id").asLong());
            }
        }
    }

    @Test
    void mixedComputesCpuThenCommitsTheEquivalentIoWorkload() throws Exception {
        UUID run = UUID.randomUUID();
        UUID request = UUID.randomUUID();
        var response = executeMixed(1, run, request);
        assertThat(response.statusCode()).isEqualTo(200);
        JsonNode body = mapper.readTree(response.body());
        assertThat(body.at("/cpu/iterations").asInt()).isEqualTo(2);
        assertThat(body.at("/cpu/digest").asText()).isEqualTo(
                "58e23d6b458d9c012ecbb4262f25acc194378b35154dff0f487c4d4dc963591c");
        assertThat(body.at("/io/item/id").asLong()).isEqualTo(1);
        assertThat(count(run, request)).isEqualTo(1);
    }

    @Test
    void duplicatePairReturnsConflictAndKeepsOneEvent() throws Exception {
        UUID run = UUID.randomUUID();
        UUID request = UUID.randomUUID();
        assertThat(execute(1, run, request).statusCode()).isEqualTo(200);
        var duplicate = execute(1, run, request);
        assertThat(duplicate.statusCode()).isEqualTo(409);
        assertThat(mapper.readTree(duplicate.body()).at("/errors/0/code").asText()).isEqualTo("DUPLICATE_REQUEST");
        assertThat(count(run, request)).isEqualTo(1);
        UUID otherRun = UUID.randomUUID();
        assertThat(execute(1, otherRun, request).statusCode()).isEqualTo(200);
        assertThat(count(otherRun, request)).isEqualTo(1);
    }

    @Test
    void concurrentDuplicatesCommitExactlyOneEvent() throws Exception {
        UUID run = UUID.randomUUID();
        UUID request = UUID.randomUUID();
        try (var executor = Executors.newFixedThreadPool(2)) {
            var first = executor.submit(() -> execute(1, run, request).statusCode());
            var second = executor.submit(() -> execute(1, run, request).statusCode());
            assertThat(List.of(first.get(), second.get())).containsExactlyInAnyOrder(200, 409);
        }
        assertThat(count(run, request)).isEqualTo(1);
    }

    @Test
    void missingItemDoesNotRecordAnAccess() throws Exception {
        UUID run = UUID.randomUUID();
        UUID request = UUID.randomUUID();
        assertThat(execute(999, run, request).statusCode()).isEqualTo(404);
        assertThat(count(run, request)).isZero();
    }

    @Test
    void failureAfterJdbcInsertRollsBackTheWholeJpaTransaction() throws Exception {
        UUID run = UUID.randomUUID();
        UUID request = UUID.randomUUID();
        doAnswer(invocation -> {
            invocation.callRealMethod();
            throw new IllegalStateException("Forced failure after insert");
        }).when(adapter).appendEvent(any());
        assertThat(execute(1, run, request).statusCode()).isEqualTo(500);
        assertThat(count(run, request)).isZero();
    }

    private HttpResponse<String> execute(long item, UUID run, UUID request) throws Exception {
        String body = mapper.writeValueAsString(Map.of("itemId", item, "runId", run, "requestId", request));
        return client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/io"))
                .timeout(java.time.Duration.ofSeconds(15))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }

    private HttpResponse<String> executeMixed(long item, UUID run, UUID request) throws Exception {
        String body = mapper.writeValueAsString(Map.of("itemId", item, "runId", run, "requestId", request));
        return client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/mixed"))
                .timeout(java.time.Duration.ofSeconds(15)).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }

    private long count(UUID run, UUID request) {
        return jdbc.queryForObject("SELECT count(*) FROM access_event WHERE run_id = ? AND request_id = ?",
                Long.class, run, request);
    }
}
