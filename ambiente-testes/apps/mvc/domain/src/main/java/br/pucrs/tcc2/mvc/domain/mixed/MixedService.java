package br.pucrs.tcc2.mvc.domain.mixed;

import br.pucrs.tcc2.mvc.domain.common.Sha256Workload;
import br.pucrs.tcc2.mvc.domain.io.model.input.IoInput;
import br.pucrs.tcc2.mvc.domain.io.port.api.IoApiPort;
import br.pucrs.tcc2.mvc.domain.mixed.model.dto.MixedDto;
import br.pucrs.tcc2.mvc.domain.mixed.model.input.MixedInput;
import br.pucrs.tcc2.mvc.domain.mixed.port.api.MixedApiPort;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class MixedService implements MixedApiPort {
    private final IoApiPort ioApiPort;
    private final int iterations;

    public MixedService(IoApiPort ioApiPort, @Value("${tcc.mixed.cpu-iterations:10000}") int iterations) {
        if (iterations <= 0) throw new IllegalArgumentException("tcc.mixed.cpu-iterations must be positive");
        this.ioApiPort = ioApiPort;
        this.iterations = iterations;
    }

    @Override
    public MixedDto execute(MixedInput input) {
        var cpu = Sha256Workload.execute(iterations);
        var io = ioApiPort.execute(new IoInput(input.itemId(), input.runId(), input.requestId()));
        return new MixedDto(cpu, io);
    }
}
