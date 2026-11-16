package br.pucrs.tcc2.virtualthreads.domain.io.port.api;

import br.pucrs.tcc2.virtualthreads.domain.io.model.dto.IoDto;
import br.pucrs.tcc2.virtualthreads.domain.io.model.input.IoInput;

public interface IoApiPort {
    IoDto execute(IoInput input);
}
