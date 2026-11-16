# Ambiente de testes e reprodução

Este diretório reúne o código e o protocolo executável do estudo comparativo de
M1 (Spring MVC e threads de plataforma), M2 (Spring MVC e threads virtuais) e
M3 (Spring WebFlux, Netty e R2DBC). Execute os comandos a partir de
`ambiente-testes/`, salvo indicação explícita. O fluxo é: conferir o Docker,
testar e compilar os três modelos, preparar o PostgreSQL e a massa sintética,
executar as seis campanhas e consolidar os resultados.

Há dois caminhos independentes:

1. **Auditar os resultados publicados:** extrair as evidências confirmatórias,
   recalcular os CSVs e regenerar tabelas e figuras. Não requer repetir a carga.
2. **Executar uma nova campanha:** gerar a massa, construir as aplicações e
   executar as mesmas matrizes e limites. Use uma cópia limpa do projeto, sem
   extrair as evidências originais nos diretórios de saída.

Os tempos e percentis de uma nova execução não serão necessariamente idênticos:
temperatura, escalonamento, caches e hardware influenciam o desempenho. Os
parâmetros, a massa sintética e a ordem pseudoaleatória são reproduzíveis.

## Estrutura

| Conteúdo | Local |
| --- | --- |
| Código completo de M1, M2 e M3, Gradle Wrapper e locks | [`apps/`](apps/) |
| Dockerfiles, Compose e schema PostgreSQL | [`infra/`](infra/) |
| Orquestradores, build, testes e gerador da massa | [`scripts/`](scripts/) |
| Scripts de carga e validação funcional k6 | [`tests/k6/`](tests/k6/) |
| Testes automatizados | [`tests/`](tests/) |
| Evidências das seis campanhas confirmatórias | [`evidence/evidencias-confirmatorias.tar.gz`](evidence/evidencias-confirmatorias.tar.gz) |
| Geradores de gráficos e tabelas dos resultados | [`analysis/scripts/`](analysis/scripts/) |
| Saídas criadas pelas campanhas | `results/raw/` e `results/processed/` |

O pacote de evidências contém `results/raw/` e `results/processed/` para as
seis campanhas da tabela abaixo, além do manifesto da massa `io-3m-v1`. Ele
não contém pilotos, a massa TSV de 3,3 GB nem caches de build. A massa é gerada
deterministicamente a partir do código e dos parâmetros desta página.

| Campanha | Workload e desenho | Rodadas |
| --- | --- | ---: |
| `cpu-pbkdf2-final` | CPU: 4 variantes, 4 taxas, 5 repetições | 80 |
| `cpu-concurrency-confirmation` | CPU: 5 variantes a 90 req/s, 5 repetições | 25 |
| `io-database-delay-final` | I/O: 3 variantes, 4 taxas, 5 repetições | 60 |
| `io-thread-limit-confirmation` | I/O: M1 com 200/250 threads, 5 repetições | 10 |
| `io-delay-sensitivity-confirmation` | I/O: 3 esperas, 3 variantes, 3 repetições | 27 |
| `mixed-final` | Misto: 4 variantes, 3 taxas, 5 repetições | 60 |
| **Total** | | **262** |

Os manifestos de `results/raw/<campanha>/manifest.json` são a fonte primária
para parâmetros, ordem das rodadas, versões e hashes. Cada
`results/processed/<campanha>/report.json` registra `plannedRuns`,
`completedRuns` e `failedRuns`.

## Ambiente da execução original

| Item | Configuração registrada |
| --- | --- |
| Hospedeiro | MacBook Air Apple M4, 24 GiB, macOS 26.6.2, ARM64 |
| Docker | Engine 29.2.0 e Compose 5.0.2; Docker Desktop com Linux ARM64 |
| Aplicação | Uma ativa por rodada; quota de 2 CPUs e limite de 2 GiB |
| JVM | Eclipse Temurin 21.0.11+10; heap fixo de 512 MiB; G1 |
| Build | Gradle Wrapper 8.14.3 e lockfiles por aplicação/módulo |
| Banco | PostgreSQL 16.14; quota de 2 CPUs e limite de 2 GiB |
| Carga | k6 1.8.0; `constant-arrival-rate`; timeout HTTP de 15 s |
| Persistência, I/O e misto | Pool de 250 conexões; PostgreSQL com até 300 conexões |

As imagens de JDK, PostgreSQL, Python e k6 estão fixadas por digest nos
Dockerfiles e arquivos Compose. O host precisa de Docker com Compose, Bash,
Python 3 e `curl`; Java, Gradle, PostgreSQL e k6 rodam em contêineres. Reserve
espaço para a massa gerada (3,3 GB), o banco e as imagens Docker. Para comparar
desempenho com o TCC, use o mesmo hardware e mantenha o computador ligado à
energia, com a tampa aberta e sem suspensão durante as campanhas. No macOS,
`caffeinate -dims` pode preceder cada comando `env.sh ... --execute`.

## A. Auditar os resultados originais

Faça esta etapa em uma cópia que não será usada para uma nova execução com os
mesmos identificadores. A extração cria os diretórios oficiais de resultados.

```bash
shasum -a 256 -c evidence/SHA256SUMS
tar -xzf evidence/evidencias-confirmatorias.tar.gz -C .
./scripts/env.sh cpu-study --consolidate cpu-pbkdf2-final
./scripts/env.sh cpu-study --consolidate cpu-concurrency-confirmation
./scripts/env.sh io-study --consolidate io-database-delay-final
./scripts/env.sh io-study --consolidate io-thread-limit-confirmation
./scripts/env.sh io-study --consolidate io-delay-sensitivity-confirmation
./scripts/env.sh mixed-study --consolidate mixed-final
```

No Linux, use `sha256sum -c evidence/SHA256SUMS` no lugar do primeiro comando.

As consolidações usam os resumos k6 e os registros por rodada. Os percentis
são calculados por rodada pelo k6; a análise agrega os percentis das rodadas,
sem tratar cada requisição como réplica independente. Confira os seis
`report.json`: todos devem mostrar `status: complete`, `failedRuns: 0` e a
quantidade de rodadas da tabela acima. Os dados de pilotos não entram nas
estimativas finais.

A consolidação foi testada em uma cópia isolada deste pacote: os valores de
todas as colunas presentes nos CSVs originais coincidiram nas seis campanhas.
Os scripts atuais acrescentam algumas colunas aos CSVs da CPU principal e das
duas primeiras campanhas de I/O; por isso, esses arquivos não são idênticos
byte a byte aos CSVs preservados no pacote.

Para regenerar gráficos e tabelas a partir dos CSVs, permaneça em
`ambiente-testes/`:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r analysis/scripts/requirements.txt
python3 analysis/scripts/gerar_graficos_cpu.py
python3 analysis/scripts/gerar_graficos_io.py
python3 analysis/scripts/gerar_graficos_mixed.py
python3 analysis/scripts/gerar_diagramas_c4.py
python3 analysis/scripts/gerar_tabelas_figuras.py
```

Os PNGs ficam em `analysis/output/figuras/` e as tabelas LaTeX em
`analysis/output/tabelas/`. Para gerar os diagramas C4 no Linux, instale a
fonte DejaVu Sans.

## B. Executar novamente as campanhas

Use uma cópia limpa. O arquivo `.env.example` serve para desenvolvimento e
contém valores de piloto; **os comandos abaixo fixam os parâmetros das campanhas
confirmatórias**. Se existir `.env`, confira se não sobrescreve os limites
comuns de 2 CPUs, 2 GiB e heap de 512 MiB. O orquestrador registra a configuração
efetiva no manifesto de cada execução.

```bash
./scripts/env.sh check
./scripts/test.sh all
./scripts/build.sh
./scripts/database.sh seed --items 3000000 --categories 1000 \
  --description-bytes 1024 --seed 42 --dataset /data/io-3m-v1
```

O catálogo original tem 3.000.000 de itens e 1.000 categorias. O SHA-256
esperado de `data/generated/io-3m-v1/catalog_item.tsv` é
`f2146adf481e8f23fba57cefe7bd50b1ccfee7c0d87a8e55cce8f99d9ce932de`;
o do gerador `scripts/lib/database/seed_data.py` é
`1e4a4f43af925e57e0d6603e71e165d370f36139dd4e65ec94ee3f982738691b`.
Confira o catálogo com `shasum -a 256 data/generated/io-3m-v1/catalog_item.tsv`
(ou `sha256sum` no Linux). O comando `seed` recusa um catálogo incompatível ou
tabelas já preenchidas.

Os comandos seguintes reproduzem as matrizes congeladas. Em uma primeira
conferência, troque `--execute` por `--dry-run`: isso mostra o plano sem iniciar
Docker. Os identificadores originais só devem ser usados quando não existirem
diretórios de resultado com esses nomes; se já existirem, o orquestrador pode
retomar a campanha em vez de começar outra.

### CPU principal: 80 rodadas

```bash
./scripts/env.sh cpu-study --execute --study-id cpu-pbkdf2-final \
  --rates 25,60,75,90 \
  --variants m1-platform,m2-virtual,m3-event-loop,m3-bounded-elastic \
  --repetitions 5 --iterations 200000 --warmup-rate 25 \
  --warmup-duration 30s --measurement-duration 60s --cooldown 20 \
  --pre-allocated-vus 100 --max-vus 1000 --request-timeout 15s --seed 42
```

### Sensibilidade de concorrência da CPU: 25 rodadas

```bash
./scripts/env.sh cpu-study --execute --study-id cpu-concurrency-confirmation \
  --rates 90 \
  --variants m1-platform,m1-platform-t2,m1-platform-t4,m2-virtual,m3-event-loop \
  --repetitions 5 --iterations 200000 --warmup-rate 25 \
  --warmup-duration 30s --measurement-duration 60s --cooldown 20 \
  --pre-allocated-vus 100 --max-vus 1000 --request-timeout 15s --seed 42 \
  --skip-build
```

### I/O principal: 60 rodadas

```bash
./scripts/env.sh io-study --execute --study-id io-database-delay-final \
  --rates 1000,1900,2100,2300 \
  --variants m1-platform,m2-virtual,m3-reactive --repetitions 5 \
  --warmup-rate 500 --warmup-duration 30s \
  --measurement-duration 60s --cooldown 20 \
  --pre-allocated-vus 500 --max-vus 5000 --request-timeout 15s \
  --db-pool-size 250 --database-delay 100ms \
  --postgres-max-connections 300 --seed 42 --skip-build
```

### Confirmação do limite de threads do M1: 10 rodadas

```bash
./scripts/env.sh io-study --execute --study-id io-thread-limit-confirmation \
  --rates 2100 --variants m1-platform,m1-platform-t250 --repetitions 5 \
  --warmup-rate 1000 --warmup-duration 60s \
  --measurement-duration 60s --cooldown 20 \
  --pre-allocated-vus 500 --max-vus 5000 --request-timeout 15s \
  --db-pool-size 250 --database-delay 100ms \
  --postgres-max-connections 300 --seed 42 --skip-build
```

### Sensibilidade à espera no banco: 27 rodadas

```bash
./scripts/env.sh io-study --execute --study-id io-delay-sensitivity-confirmation \
  --rates 1000 --variants m1-platform,m2-virtual,m3-reactive \
  --repetitions 3 --warmup-rate 500 --warmup-duration 30s \
  --measurement-duration 60s --cooldown 20 \
  --pre-allocated-vus 500 --max-vus 5000 --request-timeout 15s \
  --db-pool-size 250 --database-delays 50ms,100ms,200ms \
  --postgres-max-connections 300 --seed 42 --skip-build
```

### Workload misto: 60 rodadas

```bash
./scripts/env.sh mixed-study --execute --study-id mixed-final \
  --rates 1000,1500,1900 \
  --variants m1-platform,m2-virtual,m3-event-loop,m3-bounded-elastic \
  --repetitions 5 --cpu-iterations 10000 --warmup-rate 500 \
  --warmup-duration 30s --measurement-duration 60s --cooldown 20 \
  --pre-allocated-vus 500 --max-vus 5000 --request-timeout 15s \
  --db-pool-size 250 --database-delay 100ms \
  --postgres-max-connections 300 --seed 42 --skip-build
```

Ao terminar, examine `results/processed/<campanha>/report.json` e
`results/raw/<campanha>/manifest.json`. A execução preserva logs, resumo k6,
amostras de recursos, snapshots da aplicação/banco e configuração por rodada.
Use `./scripts/env.sh stop` para encerrar os serviços, mantendo o volume do
PostgreSQL.

## Limite da reprodução histórica exata

Os manifestos registram os hashes dos JARs e scripts das execuções originais.
Os scripts k6, o Compose e o schema publicados coincidem com esses registros.
Os JARs históricos não foram incluídos, e as versões anteriores dos
orquestradores de CPU/I/O não estão disponíveis com os mesmos hashes. Por isso,
os dados originais podem ser auditados pelo pacote acima e o protocolo pode
ser reexecutado com o código atual, mas não se deve prometer uma reconstrução
binária idêntica de todas as execuções de 2026. Os manifestos permitem
verificar essa diferença.

Os resultados e suas limitações metodológicas são discutidos no TCC. Este
repositório concentra a implementação, o protocolo e as evidências necessárias
para executar e auditar o experimento.
