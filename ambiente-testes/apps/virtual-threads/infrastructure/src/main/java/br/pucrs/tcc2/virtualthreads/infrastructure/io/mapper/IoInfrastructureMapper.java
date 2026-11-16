package br.pucrs.tcc2.virtualthreads.infrastructure.io.mapper;

import br.pucrs.tcc2.virtualthreads.domain.io.model.dto.CatalogItemDto;
import br.pucrs.tcc2.virtualthreads.domain.io.model.dto.CategoryDto;
import br.pucrs.tcc2.virtualthreads.infrastructure.io.model.CatalogItemEntity;
import br.pucrs.tcc2.virtualthreads.infrastructure.io.model.CategoryEntity;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;

@Mapper(componentModel = "spring", unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface IoInfrastructureMapper {
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
    CatalogItemDto toDomain(CatalogItemEntity entity);

    @Mapping(target = "id", source = "id")
    @Mapping(target = "name", source = "name")
    @Mapping(target = "slug", source = "slug")
    @Mapping(target = "description", source = "description")
    @Mapping(target = "displayOrder", source = "displayOrder")
    @Mapping(target = "active", source = "active")
    @Mapping(target = "createdAt", source = "createdAt")
    @Mapping(target = "updatedAt", source = "updatedAt")
    CategoryDto toDomain(CategoryEntity entity);
}
