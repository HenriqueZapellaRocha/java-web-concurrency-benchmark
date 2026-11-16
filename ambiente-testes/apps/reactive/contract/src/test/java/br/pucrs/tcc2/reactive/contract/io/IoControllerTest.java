package br.pucrs.tcc2.reactive.contract.io;

import br.pucrs.tcc2.reactive.IoFixtures;
import br.pucrs.tcc2.reactive.common.exception.ExceptionMaker;
import br.pucrs.tcc2.reactive.contract.config.exception.ApiExceptionHandler;
import br.pucrs.tcc2.reactive.contract.io.mapper.IoContractMapperImpl;
import br.pucrs.tcc2.reactive.domain.io.port.api.IoApiPort;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(controllers = IoController.class, properties = {
        "spring.jackson.deserialization.fail-on-unknown-properties=true",
        "spring.jackson.deserialization.accept-float-as-int=false"
})
@ContextConfiguration(classes = IoController.class)
@Import({IoContractMapperImpl.class, ApiExceptionHandler.class})
class IoControllerTest {
    private static final String BODY = """
            {"itemId":1,"runId":"76ca367c-f087-4de1-bd2e-c4fe459699da",
             "requestId":"344e4a80-6f07-4bd7-bd9c-a090ece18c49"}
            """;

    @Autowired private WebTestClient client;
    @MockitoBean private IoApiPort apiPort;

    @Test
    void mapsRequestAndAllThreeResponseObjects() {
        when(apiPort.execute(any())).thenAnswer(call -> Mono.just(IoFixtures.output(call.getArgument(0))));

        client.post().uri("/io").contentType(MediaType.APPLICATION_JSON).bodyValue(BODY)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.item.id").isEqualTo(1)
                .jsonPath("$.item.categoryId").isEqualTo(1)
                .jsonPath("$.item.description").isEqualTo("Item description")
                .jsonPath("$.item.price").isEqualTo(12.34)
                .jsonPath("$.category.active").isEqualTo(true)
                .jsonPath("$.category.description").isEqualTo("Category description")
                .jsonPath("$.event.runId").isEqualTo("76ca367c-f087-4de1-bd2e-c4fe459699da")
                .jsonPath("$.event.requestId").isEqualTo("344e4a80-6f07-4bd7-bd9c-a090ece18c49")
                .jsonPath("$.event.eventType").isEqualTo("ITEM_VIEW");
    }

    @ParameterizedTest
    @ValueSource(strings = {
            "{}", "null", "{", "{\"itemId\":0}",
            "{\"itemId\":1.5,\"runId\":\"76ca367c-f087-4de1-bd2e-c4fe459699da\",\"requestId\":\"344e4a80-6f07-4bd7-bd9c-a090ece18c49\"}",
            "{\"itemId\":1,\"runId\":\"invalid\",\"requestId\":null}",
            "{\"itemId\":-1,\"runId\":\"76ca367c-f087-4de1-bd2e-c4fe459699da\",\"requestId\":\"344e4a80-6f07-4bd7-bd9c-a090ece18c49\"}",
            "{\"itemId\":1,\"runId\":\"76ca367c-f087-4de1-bd2e-c4fe459699da\",\"requestId\":\"344e4a80-6f07-4bd7-bd9c-a090ece18c49\",\"extra\":true}"
    })
    void rejectsInvalidBodiesBeforeCallingDomain(String body) {
        client.post().uri("/io").contentType(MediaType.APPLICATION_JSON).bodyValue(body)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody().jsonPath("$.errors[0].code").isEqualTo("INVALID_REQUEST");
        verifyNoInteractions(apiPort);
    }

    @Test
    void preservesNotFoundAndConflictStatuses() {
        when(apiPort.execute(any())).thenReturn(
                Mono.error(ExceptionMaker.itemNotFound(1)),
                Mono.error(ExceptionMaker.duplicateRequest()));

        client.post().uri("/io").contentType(MediaType.APPLICATION_JSON).bodyValue(BODY)
                .exchange().expectStatus().isNotFound()
                .expectBody().jsonPath("$.errors[0].code").isEqualTo("ITEM_NOT_FOUND");
        client.post().uri("/io").contentType(MediaType.APPLICATION_JSON).bodyValue(BODY)
                .exchange().expectStatus().isEqualTo(409)
                .expectBody().jsonPath("$.errors[0].code").isEqualTo("DUPLICATE_REQUEST");
    }

    @Test
    void doesNotExposeInternalFailureDetails() {
        when(apiPort.execute(any())).thenReturn(Mono.error(new IllegalStateException("private SQL details")));

        client.post().uri("/io").contentType(MediaType.APPLICATION_JSON).bodyValue(BODY)
                .exchange().expectStatus().is5xxServerError()
                .expectBody().jsonPath("$.errors[0].message")
                .isEqualTo("The request could not be completed.");
    }

    @Test
    void databaseConnectionFailureReturnsServiceUnavailable() {
        when(apiPort.execute(any())).thenReturn(Mono.error(
                new org.springframework.transaction.CannotCreateTransactionException("private connection details")));

        client.post().uri("/io").contentType(MediaType.APPLICATION_JSON).bodyValue(BODY)
                .exchange().expectStatus().isEqualTo(503)
                .expectBody()
                .jsonPath("$.errors[0].code").isEqualTo("DATABASE_UNAVAILABLE")
                .jsonPath("$.errors[0].message").isEqualTo("The database is unavailable.");
    }

    @Test
    void preservesHttpMethodAndMediaTypeErrors() {
        client.get().uri("/io").exchange().expectStatus().isEqualTo(405);
        client.post().uri("/io").contentType(MediaType.TEXT_PLAIN).bodyValue(BODY)
                .exchange().expectStatus().isEqualTo(415);
        verifyNoInteractions(apiPort);
    }
}
