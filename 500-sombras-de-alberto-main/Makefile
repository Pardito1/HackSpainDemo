PYTHON ?= python3
ERP_PORT ?= 8009
ERP_HOST ?= 127.0.0.1
LOTE2_ERP ?= ../lote_2_sorpresa/erp_export_lote2.csv
ERP := $(PYTHON) alberto_erp.py --puerto $(ERP_PORT)

.DEFAULT_GOAL := help
.PHONY: help erp erp-fast erp-lote2 erp-lote2-fast erp-status erp-login

help: ## Show participant commands.
	@printf '%s\n' '500 Sombras de Alberto' '' 'Commands:'
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_-]+:.*##/ {printf "  make %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

erp: ## Start the local ERP on port 8009.
	$(ERP)

erp-fast: ## Start the local ERP without artificial latency.
	$(ERP) --rapido

erp-lote2: ## Start the ERP with the Saturday data update.
	$(ERP) --lote2 "$(LOTE2_ERP)"

erp-lote2-fast: ## Start the updated ERP without artificial latency.
	$(ERP) --lote2 "$(LOTE2_ERP)" --rapido

erp-status: ## Check that the local ERP is running.
	@curl --fail --silent --show-error "http://$(ERP_HOST):$(ERP_PORT)/erp/estado"
	@printf '\n'

erp-login: ## Request and print a local ERP session token.
	@curl --fail --silent --show-error -X POST "http://$(ERP_HOST):$(ERP_PORT)/erp/login" \
		-d 'usuario=alberto' -d 'clave=FACTURAS2009'
	@printf '\n'
