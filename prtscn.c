#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "prtscn.h"
#include <stdio.h>
#include <X11/X.h>
#include <X11/Xutil.h>
//Compile hint: gcc -shared -O3 -lX11 -fPIC -Wl,-soname,prtscn `pkg-config --cflags --libs python3` -o prtscn.so prtscn.c

static void getScreen(const int xx, const int yy, const int W, const int H, /*out*/ unsigned char * data)
{
   Display *display = XOpenDisplay(NULL);
   Window root = DefaultRootWindow(display);

   XImage *image = XGetImage(display,root, xx,yy, W,H, AllPlanes, ZPixmap);

   unsigned long red_mask   = image->red_mask;
   unsigned long green_mask = image->green_mask;
   unsigned long blue_mask  = image->blue_mask;
   int x, y;
   int ii = 0;
   for (y = 0; y < H; y++) {
       for (x = 0; x < W; x++) {
         unsigned long pixel = XGetPixel(image,x,y);
         unsigned char blue  = (pixel & blue_mask);
         unsigned char green = (pixel & green_mask) >> 8;
         unsigned char red   = (pixel & red_mask) >> 16;

         data[ii + 2] = blue;
         data[ii + 1] = green;
         data[ii + 0] = red;
         ii += 3;
      }
   }
   XDestroyImage(image);
   XDestroyWindow(display, root);
   XCloseDisplay(display);
}

static PyObject *getScreenMethod(PyObject *self, PyObject *args) {
   int xx, yy, W, H;
    if (!PyArg_ParseTuple(args, "iiii", &xx, &yy, &W, &H)) {
        PyErr_SetString(PyExc_TypeError, "arguments exception");
        return Py_None;
    }
    int data_size = sizeof(unsigned char) * W * H * 3;
    unsigned char *data = (unsigned char *) malloc(data_size);
    getScreen(xx, yy, W, H, data);
    PyObject *result = Py_BuildValue("y#", data, data_size);
    return result;
}

static PyMethodDef prtscnMethods[] = {
    {"getScreen", getScreenMethod, METH_VARARGS, ""},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef prtscn = {
    PyModuleDef_HEAD_INIT,
    "prtscn",
    "",
    -1,
    prtscnMethods
};
PyMODINIT_FUNC PyInit_prtscn(void) {
   return PyModule_Create(&prtscn);
}