"""Keep one desktop instance per Windows session; OS releases the mutex on exit."""
import atexit
import ctypes
from ctypes import wintypes
import os


class AppLock:
    def __init__(self, name='Local\\GiulianoBotelho.DotaAtelier'):
        self.handle = None
        self.name = name

    def acquire(self):
        if os.name != 'nt':
            return True
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        handle = kernel.CreateMutexW(None, False, self.name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel.CloseHandle(handle)
            return False
        self.handle = handle
        atexit.register(self.release)
        return True

    def release(self):
        if self.handle is not None:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            kernel.CloseHandle(self.handle)
            self.handle = None
