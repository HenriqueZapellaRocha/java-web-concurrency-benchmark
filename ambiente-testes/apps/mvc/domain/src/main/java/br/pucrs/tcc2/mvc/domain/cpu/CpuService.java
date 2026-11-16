package br.pucrs.tcc2.mvc.domain.cpu;

import br.pucrs.tcc2.mvc.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.mvc.domain.cpu.port.api.CpuApiPort;
import br.pucrs.tcc2.mvc.domain.common.Pbkdf2Workload;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class CpuService implements CpuApiPort {
    private final int iterations;

    public CpuService(@Value("${tcc.cpu.iterations:200000}") int iterations) {
        if (iterations <= 0) {
            throw new IllegalArgumentException("tcc.cpu.iterations must be positive");
        }
        this.iterations = iterations;
    }

    @Override
    public CpuDto execute() {
        return Pbkdf2Workload.execute(iterations);
    }
}
