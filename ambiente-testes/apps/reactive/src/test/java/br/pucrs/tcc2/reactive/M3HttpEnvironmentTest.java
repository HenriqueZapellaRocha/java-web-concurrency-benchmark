package br.pucrs.tcc2.reactive;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.embedded.netty.NettyWebServer;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
        "spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.r2dbc.R2dbcAutoConfiguration",
        "management.endpoint.health.group.readiness.include=readinessState"
})
class M3HttpEnvironmentTest {
    @LocalServerPort
    private int port;
    @Autowired
    private ObjectMapper mapper;
    @Autowired
    private ReactiveWebServerApplicationContext webContext;
    @MockitoBean
    private DatabaseClient databaseClient;

    @Test
    void actualHttpRequestUsesNettyAndNonBlockingThread() throws Exception {
        try (HttpClient client = HttpClient.newHttpClient()) {
            var request = HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/environment")).build();
            var response = client.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode body = mapper.readTree(response.body());
            assertThat(response.statusCode()).isEqualTo(200);
            assertThat(body.path("model").asText()).isEqualTo("m3");
            assertThat(body.path("virtual").asBoolean()).isFalse();
            assertThat(webContext.getWebServer()).isInstanceOf(NettyWebServer.class);
            assertThat(body.path("nonBlocking").asBoolean()).isTrue();
            assertThat(body.path("springBootVersion").asText()).isEqualTo("3.5.6");
        }
    }

    @Test
    void actualCpuRequestReturnsTheConfiguredWorkload() throws Exception {
        try (HttpClient client = HttpClient.newHttpClient()) {
            var request = HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/cpu"))
                    .POST(HttpRequest.BodyPublishers.noBody()).build();
            var response = client.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode body = mapper.readTree(response.body());
            assertThat(response.statusCode()).isEqualTo(200);
            assertThat(body.path("iterations").asInt()).isEqualTo(200000);
            assertThat(body.path("digest").asText()).matches("[0-9a-f]{64}");
        }
    }
}
