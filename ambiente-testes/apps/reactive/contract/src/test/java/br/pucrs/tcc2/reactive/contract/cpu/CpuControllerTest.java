package br.pucrs.tcc2.reactive.contract.cpu;

import br.pucrs.tcc2.reactive.contract.cpu.mapper.CpuContractMapperImpl;
import br.pucrs.tcc2.reactive.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.reactive.domain.cpu.port.api.CpuApiPort;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;

@WebFluxTest(CpuController.class)
@ContextConfiguration(classes = CpuController.class)
@Import(CpuContractMapperImpl.class)
class CpuControllerTest {
    @org.springframework.beans.factory.annotation.Autowired private WebTestClient client;
    @MockitoBean private CpuApiPort apiPort;

    @Test
    void returnsIterationsAndDigest() {
        when(apiPort.execute()).thenReturn(Mono.just(new CpuDto(2, "digest")));
        client.post().uri("/cpu").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.iterations").isEqualTo(2)
                .jsonPath("$.digest").isEqualTo("digest");
    }
}
