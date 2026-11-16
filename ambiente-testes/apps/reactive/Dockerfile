# Este contexto contém tudo que a aplicação precisa para compilar e executar.
FROM eclipse-temurin:21.0.11_10-jdk-noble@sha256:8a79c84cdf6967ae437eba13c8859d74d41aeccb1e65a42191ca57b1992ad0b8 AS build
WORKDIR /workspace
COPY . .
RUN bash docker/gradle.sh verifyEnvironment

FROM eclipse-temurin:21.0.11_10-jre-noble@sha256:b251c6e60516a48d6511a33b9afc2f8b1a427e53a598b16c1f29390c9bf916bd AS runtime-base
WORKDIR /app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/application.jar"]

# O orquestrador central pode reutilizar um jar já verificado em Docker.
FROM runtime-base AS runtime-prebuilt
COPY build/libs/reactive-app.jar /app/application.jar

# Alvo padrão: build independente usando apenas esta pasta.
FROM runtime-base AS runtime
COPY --from=build /workspace/build/libs/reactive-app.jar /app/application.jar
