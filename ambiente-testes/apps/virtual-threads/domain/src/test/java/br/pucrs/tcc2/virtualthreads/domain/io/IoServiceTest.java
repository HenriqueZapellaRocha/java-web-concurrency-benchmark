package br.pucrs.tcc2.virtualthreads.domain.io;

import br.pucrs.tcc2.virtualthreads.IoFixtures;
import br.pucrs.tcc2.virtualthreads.common.exception.ApplicationException;
import br.pucrs.tcc2.virtualthreads.domain.io.model.input.AccessEventInput;
import br.pucrs.tcc2.virtualthreads.domain.io.port.spi.IoSpiPort;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
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
        when(spiPort.findItemById(1)).thenReturn(Optional.of(expected.item()));
        when(spiPort.findCategoryById(1)).thenReturn(Optional.of(expected.category()));
        var event = new AccessEventInput(1L, input.runId(), input.requestId(), "ITEM_VIEW");
        when(spiPort.appendEvent(event)).thenReturn(expected.event());

        assertThat(service.execute(input)).isEqualTo(expected);
        var order = inOrder(spiPort);
        order.verify(spiPort).applyDatabaseDelay();
        order.verify(spiPort).findItemById(1);
        order.verify(spiPort).findCategoryById(1);
        order.verify(spiPort).appendEvent(event);
        verifyNoMoreInteractions(spiPort);
    }

    @Test
    void missingItemDoesNotReadCategoryOrWriteEvent() {
        when(spiPort.findItemById(1)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.execute(IoFixtures.input()))
                .isInstanceOfSatisfying(ApplicationException.class,
                        error -> assertThat(error.code()).isEqualTo("ITEM_NOT_FOUND"));
        verify(spiPort).findItemById(1);
        verify(spiPort).applyDatabaseDelay();
        verifyNoMoreInteractions(spiPort);
    }

    @Test
    void brokenCategoryReferenceDoesNotWriteEvent() {
        when(spiPort.findItemById(1)).thenReturn(Optional.of(IoFixtures.item()));
        when(spiPort.findCategoryById(1)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.execute(IoFixtures.input()))
                .isInstanceOfSatisfying(ApplicationException.class,
                        error -> assertThat(error.code()).isEqualTo("INCONSISTENT_CATALOG"));
        verify(spiPort, never()).appendEvent(any());
    }
}
