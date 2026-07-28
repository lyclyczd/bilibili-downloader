#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BilibiliDownloader 安装向导（tkinter，纯标准库）。

把 build/exe/BilibiliDownloader 复制到用户选择的目录，
并创建桌面 / 开始菜单快捷方式；可选同时打包便携版 zip。
需先运行 build_exe.py 生成 exe 目录。
"""
import os
import sys
import shutil
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "build", "exe", "BilibiliDownloader")


def default_dest():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(
            "~/AppData/Local")
        return os.path.join(base, "BilibiliDownloader")
    return os.path.expanduser("~/.local/share/BilibiliDownloader")


def make_shortcut_lnk(target, lnk_path, workdir, desc):
    """用 PowerShell 创建 .lnk 快捷方式（仅 Windows）。"""
    ps = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        f'$sc = $ws.CreateShortcut("{lnk_path}")\n'
        f'$sc.TargetPath = "{target}"\n'
        f'$sc.WorkingDirectory = "{workdir}"\n'
        f'$sc.Description = "{desc}"\n'
        f'$sc.IconLocation = "{target}"\n'
        "$sc.Save()\n"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
        return os.path.exists(lnk_path)
    except Exception:
        return False


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BilibiliDownloader 安装向导")
        self.geometry("560x380")
        self.resizable(False, False)
        self._build()
        self._check_src()

    def _build(self):
        tk.Label(self, text="哔哩哔哩视频下载 · 安装",
                 font=("Microsoft YaHei", 14, "bold"),
                 fg="#fb7299").pack(pady=(14, 6))
        f = tk.Frame(self)
        f.pack(fill="x", padx=18)
        tk.Label(f, text="安装位置：").pack(anchor="w")
        row = tk.Frame(f)
        row.pack(fill="x", pady=4)
        self.var_dest = tk.StringVar(value=default_dest())
        tk.Entry(row, textvariable=self.var_dest).pack(
            side="left", fill="x", expand=True)
        tk.Button(row, text="浏览…", command=self._browse).pack(
            side="left", padx=6)

        self.var_zip = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self, text="同时生成便携版 zip（无需安装，解压即用）",
            variable=self.var_zip).pack(anchor="w", padx=20, pady=(4, 0))

        btns = tk.Frame(self)
        btns.pack(pady=10)
        tk.Button(btns, text="安装", width=12, bg="#fb7299", fg="white",
                  command=self._install).pack(side="left", padx=8)
        tk.Button(btns, text="仅打包 zip", width=12,
                  command=self._only_zip).pack(side="left", padx=8)
        tk.Button(btns, text="退出", width=12,
                  command=self.destroy).pack(side="left", padx=8)

        self.log = tk.Text(self, height=9, state="disabled",
                           font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=18, pady=(4, 12))

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _check_src(self):
        exe = os.path.join(SRC, "BilibiliDownloader.exe")
        if not os.path.isfile(exe):
            self._log("⚠ 未找到 build/exe/BilibiliDownloader/BilibiliDownloader.exe")
            self._log("请先运行：python build_exe.py")
        else:
            self._log("已检测到 exe，可以开始安装。")

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.var_dest.get())
        if d:
            self.var_dest.set(d)

    def _install(self):
        dest = self.var_dest.get().strip()
        if not dest:
            messagebox.showerror("错误", "请选择安装目录")
            return
        threading.Thread(target=self._do_install, args=(dest,),
                         daemon=True).start()

    def _only_zip(self):
        threading.Thread(target=self._do_zip, daemon=True).start()

    def _do_zip(self):
        if not os.path.isdir(SRC):
            messagebox.showerror(
                "错误", "未找到 build/exe/BilibiliDownloader，"
                "请先运行 build_exe.py")
            return
        out = os.path.join(HERE, "build", "BilibiliDownloader_portable.zip")
        self._log("正在生成便携版 zip …")
        try:
            if os.path.exists(out):
                os.remove(out)
            shutil.make_archive(os.path.splitext(out)[0], "zip", SRC)
            self._log("✅ 便携版已生成：" + out)
            messagebox.showinfo("完成", "便携版 zip 已生成：\n" + out)
        except Exception as e:  # noqa
            self._log("❌ 打包失败：" + str(e))

    def _do_install(self, dest):
        exe = os.path.join(SRC, "BilibiliDownloader.exe")
        if not os.path.isfile(exe):
            messagebox.showerror("错误", "未找到 exe，请先运行 build_exe.py")
            return
        self._log("开始安装到：" + dest)
        try:
            if os.path.exists(dest):
                self._log("目标已存在，先清理…")
                shutil.rmtree(dest)
            shutil.copytree(SRC, dest)
            self._log("✅ 文件复制完成")
        except Exception as e:  # noqa
            self._log("❌ 复制失败：" + str(e))
            return

        if sys.platform == "win32":
            desk = os.path.join(os.path.expanduser("~"), "Desktop")
            if make_shortcut_lnk(exe, os.path.join(desk, "BiliDL.lnk"),
                                  dest, "哔哩哔哩视频下载"):
                self._log("✅ 桌面快捷方式已创建")
            start = os.environ.get("APPDATA")
            if start:
                sm = os.path.join(start, "Microsoft", "Windows",
                                  "Start Menu", "Programs")
                os.makedirs(sm, exist_ok=True)
                if make_shortcut_lnk(
                        exe, os.path.join(sm, "BiliDL.lnk"), dest,
                        "哔哩哔哩视频下载"):
                    self._log("✅ 开始菜单快捷方式已创建")

        self._write_uninstall(dest)
        if self.var_zip.get():
            self._do_zip()
        self._log("🎉 安装完成！双击桌面 BiliDL 图标即可使用。")
        messagebox.showinfo(
            "完成", "安装完成！\n桌面已创建 BiliDL 快捷方式。\n\n"
            "仅个人学习备份，请勿传播下载内容。")

    def _write_uninstall(self, dest):
        uninstall = os.path.join(dest, "uninstall.bat")
        try:
            with open(uninstall, "w", encoding="utf-8") as f:
                f.write("@echo off\n")
                f.write("echo 正在卸载 BilibiliDownloader …\n")
                f.write('rmdir /s /q "%~dp0"\n')
                f.write("echo 已卸载。请手动删除桌面 / 开始菜单的 BiliDL 快捷方式。\n")
                f.write("pause\n")
            self._log("✅ 卸载脚本已写入：" + uninstall)
        except Exception as e:  # noqa
            self._log("⚠ 卸载脚本写入失败：" + str(e))


if __name__ == "__main__":
    Installer().mainloop()
