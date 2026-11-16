package br.pucrs.tcc2.reactive.domain.io;

import br.pucrs.tcc2.reactive.IoFixtures;
import br.pucrs.tcc2.reactive.common.exception.ApplicationException;
import br.pucrs.tcc2.reactive.domain.io.model.input.AccessEventInput;
import br.pucrs.tcc2.reactive.domain.io.port.spi.IoSpiPort;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class IoServiceTest {
    @Mock private IoSpiPort spiPort;
    @InjectMocks private IoService service;

    @Test
    void readsItemAndCategorySeparatelyBeforeRecordingAccess() {
        var input = IoFixtures.input();
        var expected = IoFixtures.output(input);
        when(spiPort.applyDatabaseDelay()).thenReturn(Mono.empty());
        when(spiPort.findItemById(1)).thenReturn(Mono.just(expected.item()));
        when(spiPort.findCategoryById(1)).thenReturn(Mono.just(expected.category()));
        var event = new AccessEventInput(1L, input.runId(), input.requestId(), "ITEM_VIEW");
        when(spiPort.appendEvent(event)).thenReturn(Mono.just(expected.event()));

        StepVerifier.create(service.execute(input)).expectNext(expected).verifyComplete();

        var order = inOrder(spiPort);
        order.verify(spiPort).applyDatabaseDelay();
        order.verify(spiPort).findItemById(1);
        order.verify(spiPort).findCategoryById(1);
        order.verify(spiPort).appendEvent(event);
        verifyNoMoreInteractions(spiPort);
    }

    @Test
    void missingItemDoesNotReadCategoryOrWriteEvent() {
        when(spiPort.applyDatabaseDelay()).thenReturn(Mono.empty());
        when(spiPort.findItemById(1)).thenReturn(Mono.empty());

        StepVerifier.create(service.execute(IoFixtures.input()))
                .expectErrorSatisfies(error -> {
                    assertThat(error).isInstanceOf(ApplicationException.class);
                    assertThat(((ApplicationException) error).code()).isEqualTo("ITEM_NOT_FOUND");
                })
                .verify();

        verify(spiPort).findItemById(1);
        verify(spiPort).applyDatabaseDelay();
        verifyNoMoreInteractions(spiPort);
    }

    @Test
    void brokenCategoryReferenceDoesNotWriteEvent() {
        when(spiPort.applyDatabaseDelay()).thenReturn(Mono.empty());
        when(spiPort.findItemById(1)).thenReturn(Mono.just(IoFixtures.item()));
        when(spiPort.findCategoryById(1)).thenReturn(Mono.empty());

        StepVerifier.create(service.execute(IoFixtures.input()))
                .expectErrorSatisfies(error -> {
                    assertThat(error).isInstanceOf(ApplicationException.class);
                    assertThat(((ApplicationException) error).code()).isEqualTo("INCONSISTENT_CATALOG");
                })
                .verify();

        verify(spiPort, never()).appendEvent(any());
    }
}
