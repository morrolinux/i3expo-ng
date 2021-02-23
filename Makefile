prtscn.so: prtscn.c
	gcc -shared -O3 -Wall -fPIC -Wl,-soname,prtscn -o prtscn.so prtscn.c -lX11

clean:
	rm prtscn.so

PHONY: clean
# TODO: install rule
