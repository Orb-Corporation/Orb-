CC      ?= gcc
CFLAGS  ?= -O2 -std=gnu11 -Wall -Wextra -Wno-unused-parameter -Wno-clobbered -Wno-unknown-warning-option
PREFIX  ?= /usr/local
SRC      = src/util.c src/lexer.c src/parser.c src/types.c src/sema.c src/check.c src/lower.c src/opt.c src/emit.c src/platform.c src/main.c
STD      = std/core.orb std/math.orb std/strings.orb std/io.orb std/vec.orb std/os_linux.orb std/os_macos.orb std/os_windows.orb
BUILD    = build

all: $(BUILD)/orb

$(BUILD)/embed: tools/embed.c
	@mkdir -p $(BUILD)
	$(CC) -O1 -o $@ $<

$(BUILD)/stdlib_data.c: $(BUILD)/embed $(STD) Makefile
	$(BUILD)/embed $(STD) > $@

$(BUILD)/orb: $(SRC) $(BUILD)/stdlib_data.c src/*.h
	$(CC) $(CFLAGS) -Isrc -o $@ $(SRC) $(BUILD)/stdlib_data.c

test: $(BUILD)/orb
	sh tests/run.sh

bench: $(BUILD)/orb
	bash bench/run.sh

install: $(BUILD)/orb
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 755 $(BUILD)/orb $(DESTDIR)$(PREFIX)/bin/orb

vsix:
	python3 tools/package-vsix.py $(BUILD)/dist

clean:
	rm -rf $(BUILD)

.PHONY: all test bench install vsix clean
