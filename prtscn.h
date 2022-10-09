#define PY_SSIZE_T_CLEAN
#include <Python.h>

static void getScreen(const int, const int, const int, const int, unsigned char *);

static PyObject *getScreenMethod(PyObject *, PyObject *);

PyMODINIT_FUNC PyInit_prtscn(void);