package br.pucrs.tcc2.mvc.contract.io.mapper;

import br.pucrs.tcc2.mvc.contract.io.model.AccessEventResponse;
import br.pucrs.tcc2.mvc.contract.io.model.CatalogItemResponse;
import br.pucrs.tcc2.mvc.contract.io.model.CategoryResponse;
import br.pucrs.tcc2.mvc.contract.io.model.IoRequest;
import br.pucrs.tcc2.mvc.contract.io.model.IoResponse;
import br.pucrs.tcc2.mvc.domain.io.model.dto.AccessEventDto;
import br.pucrs.tcc2.mvc.domain.io.model.dto.CatalogItemDto;
import br.pucrs.tcc2.mvc.domain.io.model.dto.CategoryDto;
import br.pucrs.tcc2.mvc.domain.io.model.dto.IoDto;
import br.pucrs.tcc2.mvc.domain.io.model.input.IoInput;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface IoContractMapper {
    @Mapping(target = "itemId", source = "itemId")
    @Mapping(target = "runId", source = "runId")
    @Mapping(target = "requestId", source = "requestId")
    IoInput toInput(IoRequest request);

    @Mapping(target = "item", source = "item")
    @Mapping(target = "category", source = "category")
    @Mapping(target = "event", source = "event")
    IoResponse toResponse(IoDto dto);

    @Mapping(target = "id", source = "id")
    @Mapping(target = "categoryId", source = "categoryId")
    @Mapping(target = "sku", source = "sku")
    @Mapping(target = "name", source = "name")
    @Mapping(target = "description", source = "description")
    @Mapping(target = "brand", source = "brand")
    @Mapping(target = "model", source = "model")
    @Mapping(target = "price", source = "price")
    @Mapping(target = "currency", source = "currency")
    @Mapping(target = "weightGrams", source = "weightGrams")
    @Mapping(target = "status", source = "status")
    @Mapping(target = "createdAt", source = "createdAt")
    @Mapping(target = "updatedAt", source = "updatedAt")
    CatalogItemResponse toResponse(CatalogItemDto dto);

    @Mapping(target = "id", source = "id")
    @Mapping(target = "name", source = "name")
    @Mapping(target = "slug", source = "slug")
    @Mapping(target = "description", source = "description")
    @Mapping(target = "displayOrder", source = "displayOrder")
    @Mapping(target = "active", source = "active")
    @Mapping(target = "createdAt", source = "createdAt")
    @Mapping(target = "updatedAt", source = "updatedAt")
    CategoryResponse toResponse(CategoryDto dto);

    @Mapping(target = "id", source = "id")
    @Mapping(target = "itemId", source = "itemId")
    @Mapping(target = "runId", source = "runId")
    @Mapping(target = "requestId", source = "requestId")
    @Mapping(target = "eventType", source = "eventType")
    @Mapping(target = "createdAt", source = "createdAt")
    AccessEventResponse toResponse(AccessEventDto dto);
}
