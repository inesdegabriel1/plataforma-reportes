"""Genera el hash de la contraseña de la aplicación y un JWT_SECRET para el fichero .env.

Uso:  .venv\\Scripts\\python.exe hash_password.py
La contraseña se pide por teclado y no se guarda en ningún sitio.
"""
import getpass
import secrets

from argon2 import PasswordHasher

pw = getpass.getpass("Nueva contraseña de la aplicación: ")
if len(pw) < 12:
    raise SystemExit("Usa al menos 12 caracteres.")
if pw != getpass.getpass("Repítela: "):
    raise SystemExit("No coinciden.")

print("\nCopia estas dos líneas en backend/.env:\n")
print(f"APP_PASSWORD_HASH={PasswordHasher().hash(pw)}")
print(f"JWT_SECRET={secrets.token_urlsafe(48)}")
