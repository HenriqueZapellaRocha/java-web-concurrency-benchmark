package br.pucrs.tcc2.virtualthreads.infrastructure.io.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Immutable
@Table(name = "catalog_item")
public class CatalogItemEntity {
    @Id
    @Column(name = "id", nullable = false)
    private Long id;

    @Column(name = "category_id", nullable = false)
    private Long categoryId;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @Column(name = "name", nullable = false, length = 200)
    private String name;

    @Column(name = "description", nullable = false, columnDefinition = "text")
    private String description;

    @Column(name = "brand", nullable = false, length = 100)
    private String brand;

    @Column(name = "model", nullable = false, length = 100)
    private String model;

    @Column(name = "price", nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(name = "currency", nullable = false, length = 3)
    private String currency;

    @Column(name = "weight_grams", nullable = false)
    private Integer weightGrams;

    @Column(name = "status", nullable = false, length = 16)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected CatalogItemEntity() {}

    public Long getId() { return id; }

    public Long getCategoryId() { return categoryId; }

    public String getSku() { return sku; }

    public String getName() { return name; }

    public String getDescription() { return description; }

    public String getBrand() { return brand; }

    public String getModel() { return model; }

    public BigDecimal getPrice() { return price; }

    public String getCurrency() { return currency; }

    public Integer getWeightGrams() { return weightGrams; }

    public String getStatus() { return status; }

    public Instant getCreatedAt() { return createdAt; }

    public Instant getUpdatedAt() { return updatedAt; }
}
