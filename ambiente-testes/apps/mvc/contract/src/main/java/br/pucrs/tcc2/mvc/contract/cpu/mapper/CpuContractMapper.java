package br.pucrs.tcc2.mvc.contract.cpu.mapper;

import br.pucrs.tcc2.mvc.contract.cpu.model.CpuResponse;
import br.pucrs.tcc2.mvc.domain.cpu.model.dto.CpuDto;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface CpuContractMapper {
    @Mapping(target = "iterations", source = "iterations")
    @Mapping(target = "digest", source = "digest")
    CpuResponse toResponse(CpuDto dto);
}
