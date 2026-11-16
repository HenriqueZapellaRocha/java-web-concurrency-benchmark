package br.pucrs.tcc2.reactive.domain.mixed;

import br.pucrs.tcc2.reactive.IoFixtures;
import br.pucrs.tcc2.reactive.domain.io.port.api.IoApiPort;
import br.pucrs.tcc2.reactive.domain.mixed.model.input.MixedInput;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class MixedServiceTest {
    @Test
    void computesShaThenExecutesIoInEventLoopMode() {
        var ioApiPort = mock(IoApiPort.class);
        var ioInput = IoFixtures.input();
        var mixedInput = new MixedInput(ioInput.itemId(), ioInput.runId(), ioInput.requestId());
        var expectedIo = IoFixtures.output(ioInput);
        when(ioApiPort.execute(ioInput)).thenReturn(Mono.just(expectedIo));

        StepVerifier.create(new MixedService(ioApiPort, 2, "event-loop").execute(mixedInput))
                .assertNext(result -> {
                    assertThat(result.cpu().digest()).isEqualTo(
                            "58e23d6b458d9c012ecbb4262f25acc194378b35154dff0f487c4d4dc963591c");
                    assertThat(result.io()).isEqualTo(expectedIo);
                })
                .verifyComplete();
    }

    @Test
    void canMoveCpuStageToBoundedElasticBeforeIo() {
        var ioApiPort = mock(IoApiPort.class);
        var ioInput = IoFixtures.input();
        var thread = new AtomicReference<String>();
        when(ioApiPort.execute(ioInput)).thenReturn(Mono.defer(() -> {
            thread.set(Thread.currentThread().getName());
            return Mono.just(IoFixtures.output(ioInput));
        }));

        StepVerifier.create(new MixedService(ioApiPort, 2, "bounded-elastic").execute(
                        new MixedInput(ioInput.itemId(), ioInput.runId(), ioInput.requestId())))
                .expectNextCount(1)
                .verifyComplete();
        assertThat(thread.get()).startsWith("boundedElastic-");
    }

    @Test
    void rejectsInvalidConfiguration() {
        var io = mock(IoApiPort.class);
        assertThatThrownBy(() -> new MixedService(io, 0, "event-loop"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new MixedService(io, 1, "parallel"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
