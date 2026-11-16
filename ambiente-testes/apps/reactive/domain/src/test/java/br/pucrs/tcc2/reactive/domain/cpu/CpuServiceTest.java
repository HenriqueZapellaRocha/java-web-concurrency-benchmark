package br.pucrs.tcc2.reactive.domain.cpu;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CpuServiceTest {
    @Test
    void derivesPbkdf2KeyOnTheSubscriberThreadInEventLoopMode() {
        String subscriberThread = Thread.currentThread().getName();
        var executionThread = new AtomicReference<String>();
        StepVerifier.create(new CpuService(2, "event-loop").execute()
                        .doOnNext(result -> executionThread.set(Thread.currentThread().getName())))
                .assertNext(result -> {
                    assertThat(result.iterations()).isEqualTo(2);
                    assertThat(result.digest()).isEqualTo(
                            "5dd2ce6b5dc685aa0636648d7f9145f41d8fe11eb015e6446a12f63cb53979eb");
                })
                .verifyComplete();
        assertThat(executionThread).hasValue(subscriberThread);
    }

    @Test
    void canMoveTheWorkloadToBoundedElastic() {
        var executionThread = new AtomicReference<String>();
        StepVerifier.create(new CpuService(2, "bounded-elastic").execute()
                        .doOnNext(result -> executionThread.set(Thread.currentThread().getName())))
                .expectNextCount(1)
                .verifyComplete();
        assertThat(executionThread.get()).startsWith("boundedElastic-");
    }

    @Test
    void rejectsInvalidConfiguration() {
        assertThatThrownBy(() -> new CpuService(0, "event-loop")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new CpuService(1, "parallel")).isInstanceOf(IllegalArgumentException.class);
    }
}
