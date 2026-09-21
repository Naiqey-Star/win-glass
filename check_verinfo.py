# -*- coding: utf-8 -*-
"""读取 dist 下 exe 的版本资源（验证打包时 VSVersionInfo 是否正确嵌入）。"""
import ctypes
import os

v = ctypes.WinDLL("version")
v.GetFileVersionInfoSizeW.restype = ctypes.c_uint
v.VerQueryValueW.restype = ctypes.c_int


def query(path):
    size = v.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None, {}
    buf = ctypes.create_string_buffer(size)
    if not v.GetFileVersionInfoW(path, 0, size, buf):
        return None, {}
    ptr = ctypes.c_void_p()
    ln = ctypes.c_uint()

    v.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(ln))
    # VS_FIXEDFILEINFO 的 4 个前导 DWORD 依次是：
    #   [0] dwSignature (0xFEEF04BD)  [1] dwStrucVersion
    #   [2] dwFileVersionMS           [3] dwFileVersionLS   <-- 版本号在这两个
    # 早期版本这里直接读了 [0]/[1]，于是打出 65263.1213.1.0（= 签名被当成了版本）。
    ffi = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint * 4)).contents
    fixed = "%d.%d.%d.%d" % (ffi[2] >> 16, ffi[2] & 0xFFFF, ffi[3] >> 16, ffi[3] & 0xFFFF)

    info = {}
    for key in ("FileVersion", "ProductVersion", "FileDescription", "ProductName", "CompanyName"):
        sub = "\\StringFileInfo\\080404B0\\" + key
        if v.VerQueryValueW(buf, sub, ctypes.byref(ptr), ctypes.byref(ln)):
            info[key] = ctypes.wstring_at(ptr.value, ln.value)
    return fixed, info


def main():
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
    for name in sorted(os.listdir(d)):
        if not name.lower().endswith(".exe"):
            continue
        p = os.path.join(d, name)
        fixed, info = query(p)
        print("%-30s %8.2f MB  fixed=%s" % (name, os.path.getsize(p) / 1048576.0, fixed))
        if info:
            print("    FileVersion=%s  ProductVersion=%s" % (info.get("FileVersion"), info.get("ProductVersion")))
            print("    CompanyName=%s  Desc=%s" % (info.get("CompanyName"), info.get("FileDescription")))
        else:
            print("    (无版本资源)")


if __name__ == "__main__":
    main()
