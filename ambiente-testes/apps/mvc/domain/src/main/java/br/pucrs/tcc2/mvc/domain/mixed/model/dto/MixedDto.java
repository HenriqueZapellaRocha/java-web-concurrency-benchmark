package br.pucrs.tcc2.mvc.domain.mixed.model.dto;

import br.pucrs.tcc2.mvc.domain.cpu.model.dto.CpuDto;
import br.pucrs.tcc2.mvc.domain.io.model.dto.IoDto;

public record MixedDto(CpuDto cpu, IoDto io) {
}
