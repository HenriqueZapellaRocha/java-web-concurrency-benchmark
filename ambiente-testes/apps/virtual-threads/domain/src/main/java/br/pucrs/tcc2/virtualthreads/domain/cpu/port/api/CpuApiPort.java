package br.pucrs.tcc2.virtualthreads.domain.cpu.port.api;

import br.pucrs.tcc2.virtualthreads.domain.cpu.model.dto.CpuDto;

public interface CpuApiPort {
    CpuDto execute();
}
