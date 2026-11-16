# Java web concurrency benchmark

Ambiente reproduzível do experimento que compara três implementações Java:

- **M1:** Spring MVC com threads de plataforma;
- **M2:** Spring MVC com threads virtuais;
- **M3:** Spring WebFlux/Netty/R2DBC.

O estudo executa cargas de CPU, I/O com PostgreSQL e uma carga mista. Todo o
código, os scripts de execução e análise, a infraestrutura Docker e as
evidências das seis campanhas confirmatórias estão em
[`ambiente-testes/`](ambiente-testes/README.md).

Para começar:

```bash
git clone git@github.com:HenriqueZapellaRocha/java-web-concurrency-benchmark.git
cd java-web-concurrency-benchmark/ambiente-testes
```

Siga o [guia do ambiente](ambiente-testes/README.md) para preparar o banco,
compilar, validar, executar as campanhas e reconstruir os resultados.
