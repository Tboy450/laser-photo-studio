"""Accept one Explorer file drop in the Windows Studio window."""
from __future__ import annotations

import os
import sys


def accept_files(root, on_file):
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32")
    shell32 = ctypes.WinDLL("shell32")
    comctl32 = ctypes.WinDLL("comctl32")
    pointer = ctypes.c_size_t
    signed_pointer = ctypes.c_ssize_t
    proc_type = ctypes.WINFUNCTYPE(signed_pointer, wintypes.HWND, wintypes.UINT,
                                   pointer, signed_pointer, pointer, pointer)
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    comctl32.SetWindowSubclass.argtypes = [wintypes.HWND, proc_type, pointer, pointer]
    comctl32.SetWindowSubclass.restype = wintypes.BOOL
    comctl32.RemoveWindowSubclass.argtypes = [wintypes.HWND, proc_type, pointer]
    comctl32.RemoveWindowSubclass.restype = wintypes.BOOL
    comctl32.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, pointer, signed_pointer]
    comctl32.DefSubclassProc.restype = signed_pointer
    shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
    shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragFinish.argtypes = [wintypes.HANDLE]

    @proc_type
    def drop(hwnd, msg, wparam, lparam, _subclass, _data):
        if msg == 0x0233:  # WM_DROPFILES
            try:
                quantity = shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                if quantity == 1:
                    length = shell32.DragQueryFileW(wparam, 0, None, 0)
                    name = ctypes.create_unicode_buffer(length + 1)
                    if shell32.DragQueryFileW(wparam, 0, name, length + 1) == length and length:
                        root.after_idle(on_file, name.value)
                else:
                    root.after_idle(on_file, None)
            except Exception:
                sys.excepthook(*sys.exc_info())
            finally:
                shell32.DragFinish(wparam)
            return 0
        return comctl32.DefSubclassProc(hwnd, msg, wparam, lparam)

    root.update_idletasks()
    hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT includes Tk's top-level wrapper.
    if hwnd and comctl32.SetWindowSubclass(hwnd, drop, 1, 0):
        shell32.DragAcceptFiles(hwnd, True)

        def release(event):
            if event.widget is root:
                shell32.DragAcceptFiles(hwnd, False)
                comctl32.RemoveWindowSubclass(hwnd, drop, 1)

        root.bind("<Destroy>", release, add="+")
