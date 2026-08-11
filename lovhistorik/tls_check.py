"""Find ud af hvilken TLS-trust-konfiguration Python skal bruge paa denne maskine.

Windows' egen stak (Invoke-WebRequest) kan hente https://www.retsinformation.dk,
men Pythons OpenSSL afviser kaeden med "Basic Constraints of CA cert not marked
critical". Det peger paa et lokalt installeret CA-certifikat, typisk fra
antivirus- eller firewall-TLS-inspektion.

Scriptet afproever tre muligheder og rapporterer hvilken der virker.
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request

URL = "https://www.retsinformation.dk/robots.txt"
USER_AGENT = "JAILA-lovhistorik-probe/0.1"


def try_fetch(label: str, context: ssl.SSLContext | None) -> None:
    request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20, context=context) as response:
            body = response.read(200).decode("utf-8", errors="replace").strip()
            print(f"OK      {label}: status {response.status}, body: {body!r}")
    except urllib.error.URLError as error:
        print(f"FEJL    {label}: {error.reason}")
    except Exception as error:  # noqa: BLE001 - spike: vi vil se alt hvad der sker
        print(f"FEJL    {label}: {type(error).__name__}: {error}")


print("1) Standard-kontekst (Pythons indbyggede trust store)")
try_fetch("default", None)

print()
print("2) certifi-bundle")
try:
    import certifi

    print(f"        certifi fundet: {certifi.where()}")
    try_fetch("certifi", ssl.create_default_context(cafile=certifi.where()))
except ImportError:
    print("        certifi er ikke installeret")

print()
print("3) truststore (bruger Windows' eget trust store via OS-API)")
try:
    import truststore

    try_fetch("truststore", truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
except ImportError:
    print("        truststore er ikke installeret (pip install truststore)")

print()
print("4) Hvem udsteder certifikatet? (afsloerer om der er TLS-inspektion)")
try:
    unverified = ssl._create_unverified_context()  # noqa: SLF001 - kun diagnostik
    with unverified.wrap_socket(
        __import__("socket").create_connection(("www.retsinformation.dk", 443), timeout=20),
        server_hostname="www.retsinformation.dk",
    ) as sock:
        cert = sock.getpeercert()
        issuer = cert.get("issuer") if cert else None
        subject = cert.get("subject") if cert else None
        print(f"        subject: {subject}")
        print(f"        issuer:  {issuer}")
except Exception as error:  # noqa: BLE001 - diagnostik
    print(f"        kunne ikke laese certifikat: {type(error).__name__}: {error}")
