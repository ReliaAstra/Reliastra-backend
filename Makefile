# Reliastra Makefile
#
# Targets:
#   make build          build all binaries into bin/
#   make run-api        run the API locally
#   make migrate-up     apply migrations
#   make migrate-down   roll back one migration
#   make migrate-status show migration state
#   make seed           apply development seed data
#   make test           run unit tests
#   make test-integration  run integration tests (requires a running PostgreSQL)
#   make lint           run go vet
#   make docker-build   build the Docker image
#   make docker-up      start the full compose stack
#   make docker-down    stop the stack

GO      ?= go
BIN     := bin
VERSION ?= dev
LDFLAGS := -X main.version=$(VERSION) -s -w

.PHONY: all build run-api migrate-up migrate-down migrate-status seed test \
	test-integration lint docker-build docker-up docker-down clean

all: build

build:
	@mkdir -p $(BIN)
	$(GO) build -ldflags "$(LDFLAGS)" -o $(BIN)/api ./cmd/api
	$(GO) build -ldflags "$(LDFLAGS)" -o $(BIN)/scheduler ./cmd/scheduler
	$(GO) build -ldflags "$(LDFLAGS)" -o $(BIN)/worker ./cmd/worker
	$(GO) build -ldflags "$(LDFLAGS)" -o $(BIN)/notifier ./cmd/notifier
	$(GO) build -ldflags "$(LDFLAGS)" -o $(BIN)/migrate ./cmd/migrate

run-api: build
	./$(BIN)/api

migrate-up:
	$(GO) run ./cmd/migrate up

migrate-down:
	$(GO) run ./cmd/migrate down

migrate-status:
	$(GO) run ./cmd/migrate status

seed:
	$(GO) run ./cmd/migrate seed

test:
	$(GO) test ./pkg/... ./internal/...

test-integration:
	$(GO) test ./tests/integration/... -v -timeout 10m

lint:
	$(GO) vet ./...

docker-build:
	docker build -t reliastra:$(VERSION) .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	rm -rf $(BIN)
