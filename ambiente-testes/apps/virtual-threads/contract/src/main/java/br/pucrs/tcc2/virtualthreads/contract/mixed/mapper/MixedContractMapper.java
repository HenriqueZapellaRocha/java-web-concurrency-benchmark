package br.pucrs.tcc2.virtualthreads.contract.mixed.mapper;
import br.pucrs.tcc2.virtualthreads.contract.cpu.mapper.CpuContractMapper;
import br.pucrs.tcc2.virtualthreads.contract.io.mapper.IoContractMapper;
import br.pucrs.tcc2.virtualthreads.contract.mixed.model.MixedRequest;
import br.pucrs.tcc2.virtualthreads.contract.mixed.model.MixedResponse;
import br.pucrs.tcc2.virtualthreads.domain.mixed.model.dto.MixedDto;
import br.pucrs.tcc2.virtualthreads.domain.mixed.model.input.MixedInput;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;
@Mapper(componentModel = "spring", uses = {CpuContractMapper.class, IoContractMapper.class}, unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface MixedContractMapper {
    @Mapping(target = "itemId", source = "itemId") @Mapping(target = "runId", source = "runId") @Mapping(target = "requestId", source = "requestId")
    MixedInput toInput(MixedRequest request);
    @Mapping(target = "cpu", source = "cpu") @Mapping(target = "io", source = "io")
    MixedResponse toResponse(MixedDto dto);
}
