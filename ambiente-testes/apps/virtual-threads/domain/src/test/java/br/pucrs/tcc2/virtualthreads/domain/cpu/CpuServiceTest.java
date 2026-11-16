package br.pucrs.tcc2.virtualthreads.domain.cpu;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CpuServiceTest {
    @Test
    void derivesPbkdf2KeyAndReturnsTheConfiguredIterations() {
        var result = new CpuService(2).execute();
        assertThat(result.iterations()).isEqualTo(2);
        assertThat(result.digest()).isEqualTo("5dd2ce6b5dc685aa0636648d7f9145f41d8fe11eb015e6446a12f63cb53979eb");
    }

    @Test
    void rejectsNonPositiveIterations() {
        assertThatThrownBy(() -> new CpuService(0)).isInstanceOf(IllegalArgumentException.class);
    }
}
