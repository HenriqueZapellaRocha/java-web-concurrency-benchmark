package br.pucrs.tcc2.virtualthreads.domain.mixed.port.api;
import br.pucrs.tcc2.virtualthreads.domain.mixed.model.dto.MixedDto;
import br.pucrs.tcc2.virtualthreads.domain.mixed.model.input.MixedInput;
public interface MixedApiPort { MixedDto execute(MixedInput input); }
