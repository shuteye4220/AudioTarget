SRC := ../../src
CFLAGS := -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -O1 -g -I$(SRC) \
	-fsanitize=address,undefined -fno-omit-frame-pointer

test: test_main.c $(SRC)/proto.c $(SRC)/tonemap.c $(SRC)/fusion.c $(SRC)/mount.c
	$(CC) $(CFLAGS) -o $@ $^ -lm

run: test
	./test

clean:
	rm -f test

.PHONY: run clean
