package br.pucrs.tcc2.mvc.domain.mixed;

import br.pucrs.tcc2.mvc.IoFixtures;
import br.pucrs.tcc2.mvc.domain.io.model.input.IoInput;
import br.pucrs.tcc2.mvc.domain.io.port.api.IoApiPort;
import br.pucrs.tcc2.mvc.domain.mixed.model.input.MixedInput;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class MixedServiceTest {
    @Test
    void computesShaBeforeDelegatingTheEquivalentIoWorkload() {
        var ioApiPort = mock(IoApiPort.class);
        var ioInput = IoFixtures.input();
        var mixedInput = new MixedInput(ioInput.itemId(), ioInput.runId(), ioInput.requestId());
        var expectedIo = IoFixtures.output(ioInput);
        when(ioApiPort.execute(ioInput)).thenReturn(expectedIo);

        var result = new MixedService(ioApiPort, 2).execute(mixedInput);

        assertThat(result.cpu().iterations()).isEqualTo(2);
        assertThat(result.cpu().digest()).isEqualTo(
                "58e23d6b458d9c012ecbb4262f25acc194378b35154dff0f487c4d4dc963591c");
        assertThat(result.io()).isEqualTo(expectedIo);
        verify(ioApiPort).execute(ioInput);
    }

    @Test
    void rejectsNonPositiveCpuCost() {
        assertThatThrownBy(() -> new MixedService(mock(IoApiPort.class), 0))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
