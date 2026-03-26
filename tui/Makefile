BINARY := etherion-tui
BUILD_DIR := bin

.PHONY: build run install clean tidy

build:
	mkdir -p $(BUILD_DIR)
	go build -o $(BUILD_DIR)/$(BINARY) ./...

run:
	go run ./...

install: build
	cp $(BUILD_DIR)/$(BINARY) $(GOPATH)/bin/

tidy:
	go mod tidy

clean:
	rm -rf $(BUILD_DIR)
