package br.pucrs.tcc2.reactive.contract.mixed;

import br.pucrs.tcc2.reactive.IoFixtures;
import br.pucrs.tcc2.reactive.contract.config.exception.ApiExceptionHandler;
import br.pucrs.tcc2.reactive.contract.cpu.mapper.CpuContractMapperImpl;
import br.pucrs.tcc2.reactive.contract.io.mapper.IoContractMapperImpl;
import br.pucrs.tcc2.reactive.contract.mixed.mapper.MixedContractMapperImpl;
import br.pucrs.tcc2.reactive.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.reactive.domain.io.model.input.IoInput;
import br.pucrs.tcc2.reactive.domain.mixed.model.dto.MixedDto;
import br.pucrs.tcc2.reactive.domain.mixed.model.input.MixedInput;
import br.pucrs.tcc2.reactive.domain.mixed.port.api.MixedApiPort;
import org.junit.jupiter.api.Test;
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

@WebFluxTest(controllers = MixedController.class, properties = {
        "spring.jackson.deserialization.fail-on-unknown-properties=true",
        "spring.jackson.deserialization.accept-float-as-int=false"})
@ContextConfiguration(classes = MixedController.class)
@Import({MixedContractMapperImpl.class, CpuContractMapperImpl.class, IoContractMapperImpl.class,
        ApiExceptionHandler.class})
class MixedControllerTest {
    private static final String BODY = """
            {"itemId":1,"runId":"76ca367c-f087-4de1-bd2e-c4fe459699da",
             "requestId":"344e4a80-6f07-4bd7-bd9c-a090ece18c49"}
            """;
    @Autowired private WebTestClient client;
    @MockitoBean private MixedApiPort apiPort;

    @Test
    void returnsCpuAndIoResults() {
        when(apiPort.execute(any())).thenAnswer(call -> Mono.just(output(call.getArgument(0))));
        client.post().uri("/mixed").contentType(MediaType.APPLICATION_JSON).bodyValue(BODY)
                .exchange().expectStatus().isOk().expectBody()
                .jsonPath("$.cpu.iterations").isEqualTo(2)
                .jsonPath("$.cpu.digest").isEqualTo("digest")
                .jsonPath("$.io.item.id").isEqualTo(1)
                .jsonPath("$.io.category.id").isEqualTo(1)
                .jsonPath("$.io.event.eventType").isEqualTo("ITEM_VIEW");
    }

    @Test
    void rejectsInvalidBodyBeforeDomain() {
        client.post().uri("/mixed").contentType(MediaType.APPLICATION_JSON).bodyValue("{}")
                .exchange().expectStatus().isBadRequest()
                .expectBody().jsonPath("$.errors[0].code").isEqualTo("INVALID_REQUEST");
        verifyNoInteractions(apiPort);
    }

    private MixedDto output(MixedInput input) {
        var ioInput = new IoInput(input.itemId(), input.runId(), input.requestId());
        return new MixedDto(new CpuDto(2, "digest"), IoFixtures.output(ioInput));
    }
}
