#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tanima.py — AWS Rekognition ile taninmis kisi tanima.

ISTEGE BAGLI ozelliktir. Kullanilmadigi surece hicbir veri disari cikmaz.
Kullanildiginda SADECE kisi basina birkac yuz kirpmasi AWS'e gonderilir,
arsivin tamami degil.

NEDEN AWS?
  Google Vision "web detection" denendi ve bu is icin uygun olmadigi goruldu:
  o yontem GORSELI internette arar, YUZU tanimaz. Yayinlanmamis kareler icin
  hicbir sonuc dondurmuyor ("human", "girl" gibi genel etiketler).
  AWS Rekognition RecognizeCelebrities ise yuzu bir kisi veritabaniyla
  karsilastirir; fotografin daha once yayinlanmis olmasi gerekmez.

KIMLIK BILGISI NEREDEN OKUNUR (sirasiyla):
  1. AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY ortam degiskenleri
  2. ~/.aws/credentials  ('aws configure' ile olusur)
  3. program klasorundeki aws_anahtar.json:
        {"access_key": "...", "secret_key": "...", "bolge": "us-east-1"}

Anahtarlar kodun icine yazilmaz, GitHub'a gitmez (.gitignore'da).
"""

import json
import os
from pathlib import Path

VARSAYILAN_BOLGE = "us-east-1"


def _yerel_anahtar(klasor=None):
    """aws_anahtar.json dosyasini okur (varsa)."""
    klasor = Path(klasor or Path(__file__).resolve().parent)
    f = klasor / "aws_anahtar.json"
    if not f.exists():
        return {}
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def anahtar_yardimi():
    return (
        "AWS kimlik bilgisi bulunamadi. Uc yoldan biriyle verebilirsiniz:\n"
        "\n"
        "  A) En kolayi - program klasorune 'aws_anahtar.json' dosyasi olusturun:\n"
        '       {"access_key": "AKIA...", "secret_key": "...", "bolge": "us-east-1"}\n'
        "\n"
        "  B) AWS CLI kuruluysa:  aws configure\n"
        "\n"
        "  C) Ortam degiskeni:    setx AWS_ACCESS_KEY_ID \"AKIA...\"\n"
        "                         setx AWS_SECRET_ACCESS_KEY \"...\"\n"
        "\n"
        "Anahtari nereden alirsiniz:\n"
        "  console.aws.amazon.com > IAM > Users > (kullanici) > Security credentials\n"
        "  > Create access key.  Kullaniciya 'AmazonRekognitionReadOnlyAccess'\n"
        "  yetkisi yeterlidir - baska hicbir yetki gerekmez."
    )


def hazirla(bolge=None, klasor=None):
    """Rekognition istemcisi dondurur. Kimlik yoksa RuntimeError firlatir."""
    try:
        import boto3
        from botocore.exceptions import NoCredentialsError  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "'boto3' kutuphanesi kurulu degil. Su komutu calistirin:\n"
            "    pip install boto3"
        )

    yerel = _yerel_anahtar(klasor)
    bolge = bolge or yerel.get("bolge") or os.environ.get("AWS_DEFAULT_REGION") or VARSAYILAN_BOLGE

    if yerel.get("access_key") and yerel.get("secret_key"):
        istemci = boto3.client(
            "rekognition",
            region_name=bolge,
            aws_access_key_id=yerel["access_key"],
            aws_secret_access_key=yerel["secret_key"],
        )
    else:
        istemci = boto3.client("rekognition", region_name=bolge)

    # kimlik gercekten var mi, hemen anlasilsin (bos istek atmadan)
    kimlik = istemci._request_signer._credentials
    if kimlik is None:
        raise RuntimeError(anahtar_yardimi())
    return istemci


def sorgula(istemci, jpeg_baytlari):
    """
    Bir yuz kirpmasi icin taninan kisileri dondurur:
        [(isim, guven_yuzde, [baglantilar]), ...]  - en iyi eslesme basta
    """
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        cevap = istemci.recognize_celebrities(Image={"Bytes": jpeg_baytlari})
    except ClientError as e:
        kod = e.response.get("Error", {}).get("Code", "")
        mesaj = e.response.get("Error", {}).get("Message", "")
        if kod in ("UnrecognizedClientException", "InvalidSignatureException",
                   "AccessDeniedException", "AuthFailure"):
            raise RuntimeError("AWS kimlik/yetki hatasi (%s): %s" % (kod, mesaj))
        raise RuntimeError("AWS hatasi (%s): %s" % (kod, mesaj))
    except BotoCoreError as e:
        raise RuntimeError("AWS baglanti hatasi: %s" % e)

    sonuc = []
    for k in cevap.get("CelebrityFaces", []) or []:
        kutu = (k.get("Face") or {}).get("BoundingBox") or {}
        alan = float(kutu.get("Width", 0)) * float(kutu.get("Height", 0))
        sonuc.append((
            (k.get("Name") or "").strip(),
            float(k.get("MatchConfidence") or 0.0),
            list(k.get("Urls") or []),
            alan,
        ))
    # kirpmanin ortasindaki (en buyuk) yuz once gelsin
    sonuc.sort(key=lambda t: -t[3])
    return [(a, g, u) for a, g, u, _ in sonuc]


def taninmayan_sayisi(istemci_cevabi):
    return len(istemci_cevabi.get("UnrecognizedFaces", []) or [])
