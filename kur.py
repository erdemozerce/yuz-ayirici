#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
kur.py — Yuz Ayirici kurulumu (.bat dosyasi gerektirmez).

NEDEN BU DOSYA VAR
  Windows 11'in "Akilli Uygulama Denetimi" (Smart App Control) imzasiz .bat
  dosyalarini engelleyebiliyor ve "yine de calistir" secenegi vermiyor.
  Bu betik dogrudan python.exe ile calistirilir - python.exe imzalidir,
  engellenmez.

CALISTIRMA
  Windows'ta PowerShell acip:
      py -3 "C:\\...\\yuz-ayirici\\kur.py"
  ya da kurulum klasorunde:
      py -3 kur.py
"""

import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def baslik(m):
    print()
    print("=" * 64)
    print("  " + m)
    print("=" * 64)


def calistir(argv, sessiz=False):
    try:
        r = subprocess.run(argv, capture_output=sessiz, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode == 0
    except Exception as e:
        print("  hata:", e)
        return False


def nvidia_var_mi():
    from shutil import which
    if not which("nvidia-smi"):
        return False
    return calistir(["nvidia-smi"], sessiz=True)


def mac_baslatici():
    """macOS icin cift tiklanabilir .command dosyasi + Masaustune kisayol."""
    try:
        betik = BASE / "BASLAT.command"
        betik.write_text(
            "#!/bin/bash\n"
            'cd "$(dirname "$0")"\n'
            '"%s" arayuz.py\n' % sys.executable,
            encoding="utf-8")
        os.chmod(betik, 0o755)
        masaustu = Path(os.path.expanduser("~/Desktop"))
        if masaustu.is_dir():
            bag = masaustu / "Yuz Ayirici.command"
            try:
                if bag.exists() or bag.is_symlink():
                    bag.unlink()
                os.symlink(betik, bag)
            except OSError:
                pass
        return betik
    except Exception:
        return None


def kisayol_olustur():
    """
    Masaustune kisayol koyar. Hedef: python.exe (IMZALI) + arayuz.py
    .bat kullanilmaz, boylece Akilli Uygulama Denetimi engellemez.
    """
    if os.name != "nt":
        return mac_baslatici()
    try:
        masaustu = Path(os.path.expanduser("~")) / "Desktop"
        if not masaustu.exists():
            masaustu = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
        lnk = masaustu / "Yuz Ayirici.lnk"
        hedef = sys.executable                      # python.exe - imzali
        betik = str(BASE / "arayuz.py")
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
            "$s.TargetPath='%s';"
            "$s.Arguments='\"%s\"';"
            "$s.WorkingDirectory='%s';"
            "$s.IconLocation='%%SystemRoot%%\\system32\\imageres.dll,109';"
            "$s.Description='Yuz Ayirici';"
            "$s.Save()"
        ) % (str(lnk), hedef, betik, str(BASE))
        ok = calistir(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                      sessiz=True)
        return lnk if (ok and lnk.exists()) else None
    except Exception:
        return None


def main():
    baslik("YUZ AYIRICI - KURULUM")
    print("  Python : %s" % sys.version.split()[0])
    print("  Konum  : %s" % BASE)
    if sys.version_info < (3, 9):
        print("\n  !! Python 3.9 veya ustu gerekiyor. python.org'dan guncelleyin.")
        return 1

    baslik("1/4  Temel araclar")
    calistir([sys.executable, "-m", "pip", "install", "--upgrade",
              "pip", "setuptools", "wheel", "--quiet", "--disable-pip-version-check"])
    print("  tamam")

    baslik("2/4  Gerekli paketler  (buyuk indirme, sabir)")
    gerek = BASE / "gereksinimler.txt"
    if not gerek.exists():
        print("  !! gereksinimler.txt bulunamadi - ZIP eksik cikarilmis olabilir.")
        return 1
    if not calistir([sys.executable, "-m", "pip", "install", "-r", str(gerek),
                     "--disable-pip-version-check"]):
        print("\n  !! Paket kurulumu basarisiz. Internet baglantisini kontrol edip")
        print("     bu betigi tekrar calistirin.")
        return 1

    baslik("3/4  Ekran karti")
    if os.name != "nt" and sys.platform == "darwin":
        print("  macOS - islemci modunda calisacak")
        try:
            (BASE / "gpu_var.txt").unlink()
        except OSError:
            pass
    elif nvidia_var_mi():
        print("  NVIDIA bulundu - hizlandirilmis surum kuruluyor...")
        calistir([sys.executable, "-m", "pip", "uninstall", "-y", "onnxruntime",
                  "--quiet"], sessiz=True)
        calistir([sys.executable, "-m", "pip", "install", "onnxruntime-gpu",
                  "--quiet", "--disable-pip-version-check"])
        (BASE / "gpu_var.txt").write_text("gpu", encoding="ascii")
    else:
        print("  NVIDIA yok - islemci modunda calisacak (daha yavas ama sorunsuz)")
        try:
            (BASE / "gpu_var.txt").unlink()
        except OSError:
            pass

    baslik("4/4  Yuz tanima modeli  (~300 MB, ilk seferde iner)")
    test = BASE / "kurulum_testi.py"
    if test.exists():
        if not calistir([sys.executable, str(test)]):
            print("\n  !! Test basarisiz. Ekran goruntusu alip gonderin.")
            return 1

    # gunluk kullanimda da .bat kullanilmasin diye python yolunu kaydet
    (BASE / "python_yolu.txt").write_text('"%s"' % sys.executable, encoding="utf-8")

    lnk = kisayol_olustur()
    baslik("KURULUM TAMAM")
    if lnk and os.name == "nt":
        print("  Masaustunde 'Yuz Ayirici' kisayolu olusturuldu.")
        print("  Programi acmak icin ona cift tiklayin.")
    elif lnk:
        print("  Masaustunde 'Yuz Ayirici.command' olusturuldu.")
        print("  Programi acmak icin ona cift tiklayin.")
        print("  (Ilk acilista macOS izin sorabilir: Sag tik > Ac > Ac)")
    else:
        print("  Kisayol olusturulamadi. Programi su komutla acabilirsiniz:")
        print('     py -3 "%s"' % (BASE / "arayuz.py"))
    print()
    print("  Kullanim kilavuzu: KARDESIM-ICIN.md")
    print()
    return 0


if __name__ == "__main__":
    kod = 0
    try:
        kod = main()
    except KeyboardInterrupt:
        print("\nIptal edildi.")
        kod = 1
    except Exception:
        import traceback
        traceback.print_exc()
        kod = 1
    try:
        input("Kapatmak icin Enter'a basin...")
    except EOFError:
        pass
    sys.exit(kod)
