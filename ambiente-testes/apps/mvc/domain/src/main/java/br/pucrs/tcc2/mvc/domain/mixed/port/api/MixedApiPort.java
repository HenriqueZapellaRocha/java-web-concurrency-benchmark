package br.pucrs.tcc2.mvc.domain.mixed.port.api;

import br.pucrs.tcc2.mvc.domain.mixed.model.dto.MixedDto;
import br.pucrs.tcc2.mvc.domain.mixed.model.input.MixedInput;

public interface MixedApiPort {
    MixedDto execute(MixedInput input);
}
